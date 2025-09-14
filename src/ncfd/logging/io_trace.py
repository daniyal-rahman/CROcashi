"""
IO tracing decorator for boundary logging.

Provides safe, cheap, and findable logging of function inputs/outputs
at important boundaries (LLM calls, parsers, validators, etc.).
"""

from __future__ import annotations

import hashlib
import json
import os
import inspect
import functools
import time
import contextvars
from typing import Any, Callable, Optional, Dict, Tuple, Union
import random

from .context import ctx_run_id, ctx_task_id
from .schema import IOTraceRecord, LogLevel
from .structured_logger import get_logger

log = get_logger(__name__)


def _sha256(b: bytes) -> str:
    """Generate SHA256 hash of bytes."""
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def _to_bytes(x: Any) -> bytes:
    """Convert any object to bytes for hashing."""
    if x is None:
        return b"null"
    if isinstance(x, (bytes, bytearray)):
        return bytes(x)
    try:
        return json.dumps(x, default=str, ensure_ascii=False).encode("utf-8")
    except Exception:
        return str(x).encode("utf-8", errors="replace")


def default_redactor(text: str) -> str:
    """
    Default redactor for sensitive information.
    
    Replace with your PHI/PII maskers for production use.
    """
    return (text
        .replace("@", "[at]")
        .replace("http", "hxxp")
        .replace("https", "hxxps")
        # Add more redaction patterns as needed
    )


def _maybe_store_blob(kind: str, b: bytes, sha: str) -> Optional[str]:
    """
    Persist full payload for deep-dive; return URI or None.
    
    Args:
        kind: Type of blob (in/out)
        b: Bytes to store
        sha: SHA hash for filename
        
    Returns:
        URI to stored blob or None
    """
    mode = os.getenv("IO_TRACE_BLOBS", "off")  # off|on
    if mode != "on":
        return None
    
    base = os.getenv("IO_TRACE_BLOB_DIR", "/tmp/ncfd_io_blobs")
    os.makedirs(base, exist_ok=True)
    path = f"{base}/{kind}_{sha}.jsonl"
    
    try:
        with open(path, "wb") as f:
            f.write(b)
        return f"file://{path}"
    except Exception:
        return None


def _preview(b: bytes, limit: int = 280) -> str:
    """Generate preview of bytes with redaction."""
    t = b.decode("utf-8", errors="replace")
    t = default_redactor(t)
    return (t[:limit] + "…") if len(t) > limit else t


def _should_trace(qual: str) -> bool:
    """
    Determine if a function should be traced based on configuration.
    
    Args:
        qual: Qualified function name
        
    Returns:
        True if function should be traced
    """
    mode = os.getenv("IO_TRACE", "errors")  # off|errors|sample:0.05|all
    if mode == "off":
        return False
    
    # Check exclusions
    excl = os.getenv("TRACE_EXCLUDE", "")
    if excl.strip():
        exclude_patterns = [p.strip() for p in excl.split(",") if p.strip()]
        if any(qual.startswith(pattern) for pattern in exclude_patterns):
            return False
    
    # Check inclusions
    incl = os.getenv("TRACE_INCLUDE", "")
    if incl.strip():
        include_patterns = [p.strip() for p in incl.split(",") if p.strip()]
        if not any(qual.startswith(pattern) for pattern in include_patterns):
            return False
    
    return True


def _sampled() -> bool:
    """
    Determine if current execution should be sampled for full blob storage.
    
    Returns:
        True if should be sampled
    """
    mode = os.getenv("IO_TRACE", "errors")
    if mode == "all":
        return True
    if mode.startswith("sample:"):
        try:
            p = float(mode.split(":")[1])
            return random.random() < p
        except Exception:
            return False
    return False  # errors-only default


def io_trace(
    name: Optional[str] = None,
    capture_args: Optional[Tuple[str, ...]] = None,
    io_type: str = "function_call"
) -> Callable:
    """
    Decorator for logging function input/output summaries and optionally storing full blobs.
    
    Args:
        name: Custom event name (defaults to qualified function name)
        capture_args: Whitelist of argument names to log fully; others are length-only
        io_type: Type of IO operation for categorization
        
    Returns:
        Decorator function
    """
    def deco(fn: Callable) -> Callable:
        qual = f"{fn.__module__}.{fn.__name__}"
        event_name = name or f"io.trace.{qual}"
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _should_trace(qual):
                return fn(*args, **kwargs)

            # Bind arguments
            bargs = sig.bind_partial(*args, **kwargs)
            bargs.apply_defaults()
            
            # Prepare input object
            in_obj: Dict[str, Any] = {}
            for k, v in bargs.arguments.items():
                if capture_args and k not in capture_args:
                    # Summarize instead of logging raw
                    try:
                        n = len(v)  # type: ignore
                    except Exception:
                        n = None
                    in_obj[k] = {
                        "__summary__": True,
                        "type": type(v).__name__,
                        "len": n
                    }
                else:
                    in_obj[k] = v

            # Hash input
            in_bytes = _to_bytes(in_obj)
            in_sha = _sha256(in_bytes)
            in_uri = _maybe_store_blob("in", in_bytes, in_sha) if _sampled() else None

            # Execute function
            t0 = time.perf_counter()
            try:
                out = fn(*args, **kwargs)
                ok = True
                return out
            except Exception as e:
                ok = False
                out = {
                    "__error__": type(e).__name__,
                    "msg": str(e)
                }
                raise
            finally:
                # Hash output
                dur_ms = int((time.perf_counter() - t0) * 1000)
                out_bytes = _to_bytes(out)
                out_sha = _sha256(out_bytes)
                out_uri = _maybe_store_blob("out", out_bytes, out_sha) if _sampled() else None

                # Create log record
                record = IOTraceRecord(
                    level=LogLevel.INFO if ok else LogLevel.ERROR,
                    module=fn.__module__,
                    event=event_name,
                    run_id=ctx_run_id.get(),
                    task_id=ctx_task_id.get(),
                    duration_ms=dur_ms,
                    outcome="success" if ok else "fail",
                    io_type=io_type,
                    input_hash=in_sha,
                    output_hash=out_sha,
                    bytes_in=len(in_bytes),
                    bytes_out=len(out_bytes),
                    preview_in=_preview(in_bytes),
                    preview_out=_preview(out_bytes),
                    blob_uri_in=in_uri,
                    blob_uri_out=out_uri,
                )
                
                # Log the record
                if ok:
                    log.info(record.to_dict())
                else:
                    log.error(record.to_dict())
        
        return wrapper
    return deco


# Convenience decorators for common IO types
def llm_trace(name: Optional[str] = None, capture_args: Optional[Tuple[str, ...]] = None):
    """IO trace decorator specifically for LLM calls."""
    return io_trace(name=name, capture_args=capture_args, io_type="llm_call")


def parse_trace(name: Optional[str] = None, capture_args: Optional[Tuple[str, ...]] = None):
    """IO trace decorator specifically for parsing operations."""
    return io_trace(name=name, capture_args=capture_args, io_type="parse")


def validate_trace(name: Optional[str] = None, capture_args: Optional[Tuple[str, ...]] = None):
    """IO trace decorator specifically for validation operations."""
    return io_trace(name=name, capture_args=capture_args, io_type="validate")


def db_trace(name: Optional[str] = None, capture_args: Optional[Tuple[str, ...]] = None):
    """IO trace decorator specifically for database operations."""
    return io_trace(name=name, capture_args=capture_args, io_type="db")


def api_trace(name: Optional[str] = None, capture_args: Optional[Tuple[str, ...]] = None):
    """IO trace decorator specifically for API calls."""
    return io_trace(name=name, capture_args=capture_args, io_type="api")
