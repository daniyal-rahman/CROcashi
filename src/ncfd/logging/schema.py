"""
Log record schema definitions for structured logging.

Defines the required fields and structure for all log records
following the comprehensive logging guidance.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
import hashlib
import json


class LogLevel(str, enum.Enum):
    """Log levels following standard conventions."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class Outcome(str, enum.Enum):
    """Task execution outcomes."""
    SUCCESS = "success"
    FAIL = "fail"
    PARTIAL = "partial"


class LogRecord(BaseModel):
    """
    Comprehensive log record schema.
    
    Every log line should carry these fields to answer:
    - What ran, on which data, with which code/config
    - What decisions were made (and why)
    - How long/costly it was, and where it broke
    """
    
    # Core identification
    ts: datetime = Field(default_factory=datetime.utcnow)
    level: LogLevel
    module: str = Field(..., description="Module name (e.g., ncfd.ingest.pubmed)")
    event: str = Field(..., description="Canonical event name")
    
    # Execution context
    run_id: Optional[str] = Field(None, description="Unique run identifier")
    flow_id: Optional[str] = Field(None, description="Flow identifier")
    task_id: Optional[str] = Field(None, description="Task identifier")
    attempt: Optional[int] = Field(None, description="Retry index (0-based)")
    duration_ms: Optional[int] = Field(None, description="Execution duration in milliseconds")
    outcome: Optional[Outcome] = Field(None, description="Task outcome")
    
    # Code/Config versioning
    code_version: Optional[str] = Field(None, description="Git SHA")
    git_dirty: Optional[bool] = Field(None, description="Git dirty flag")
    docker_image: Optional[str] = Field(None, description="Docker image tag")
    py_version: Optional[str] = Field(None, description="Python version")
    env: Optional[str] = Field(None, description="Environment (prod/stage/dev)")
    config_hash: Optional[str] = Field(None, description="Configuration hash")
    
    # Data identifiers
    nct_id: Optional[str] = Field(None, description="Clinical trial ID")
    trial_id: Optional[str] = Field(None, description="Internal trial ID")
    doc_id: Optional[str] = Field(None, description="Document ID")
    pmid: Optional[str] = Field(None, description="PubMed ID")
    pmcid: Optional[str] = Field(None, description="PubMed Central ID")
    doi: Optional[str] = Field(None, description="DOI")
    cik: Optional[str] = Field(None, description="SEC CIK")
    ticker: Optional[str] = Field(None, description="Stock ticker")
    sponsor_id: Optional[str] = Field(None, description="Sponsor ID")
    study_card_id: Optional[str] = Field(None, description="Study card ID")
    signal_id: Optional[str] = Field(None, description="Signal ID")
    gate_id: Optional[str] = Field(None, description="Gate ID")
    evidence_id: Optional[str] = Field(None, description="Evidence ID")
    
    # Performance metrics
    processed_n: Optional[int] = Field(None, description="Items processed")
    success_n: Optional[int] = Field(None, description="Items succeeded")
    fail_n: Optional[int] = Field(None, description="Items failed")
    latency_ms: Optional[int] = Field(None, description="Latency in milliseconds")
    cache_hit: Optional[bool] = Field(None, description="Cache hit flag")
    retries: Optional[int] = Field(None, description="Number of retries")
    
    # Error information (only if failing)
    err_type: Optional[str] = Field(None, description="Error type")
    err_msg: Optional[str] = Field(None, description="Error message")
    stack: Optional[str] = Field(None, description="Full stack trace")
    root_cause: Optional[str] = Field(None, description="Root cause tag")
    retry_in_s: Optional[int] = Field(None, description="Retry delay in seconds")
    
    # LLM metrics
    model: Optional[str] = Field(None, description="LLM model name")
    prompt_id: Optional[str] = Field(None, description="Prompt template ID")
    prompt_hash: Optional[str] = Field(None, description="Prompt hash")
    temperature: Optional[float] = Field(None, description="LLM temperature")
    top_p: Optional[float] = Field(None, description="LLM top_p")
    input_tokens: Optional[int] = Field(None, description="Input tokens")
    output_tokens: Optional[int] = Field(None, description="Output tokens")
    usd_cost: Optional[float] = Field(None, description="Cost in USD")
    truncated: Optional[bool] = Field(None, description="Truncation flag")
    
    # Decision transparency (Signals/Gates)
    rule_id: Optional[str] = Field(None, description="Rule identifier")
    rule_version: Optional[str] = Field(None, description="Rule version")
    features: Optional[Dict[str, Any]] = Field(None, description="Features used")
    thresholds: Optional[Dict[str, Any]] = Field(None, description="Thresholds applied")
    decision: Optional[str] = Field(None, description="Decision made")
    confidence: Optional[float] = Field(None, description="Confidence score")
    why: Optional[str] = Field(None, description="Decision explanation")
    evidence_refs: Optional[List[List[Union[str, int]]]] = Field(
        None, 
        description="Evidence references [(doc_id, pmid/pmcid, char_range)]"
    )
    
    # Additional context
    message: Optional[str] = Field(None, description="Human-readable message")
    extra: Optional[Dict[str, Any]] = Field(None, description="Additional fields")
    
    @validator('ts', pre=True)
    def parse_timestamp(cls, v):
        """Ensure timestamp is properly formatted."""
        if isinstance(v, str):
            return v
        elif isinstance(v, datetime):
            return v.isoformat() + "Z"
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON logging."""
        return self.dict(exclude_none=True)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


class LLMLogRecord(LogRecord):
    """Specialized log record for LLM operations."""
    
    provider: Optional[str] = Field(None, description="LLM provider")
    api_mode: Optional[str] = Field(None, description="API mode (responses vs structured)")
    provider_request_id: Optional[str] = Field(None, description="Provider request ID")
    tool_calls_n: Optional[int] = Field(None, description="Number of tool calls")
    safety_outcome: Optional[str] = Field(None, description="Safety/guardrail outcome")


class DecisionLogRecord(LogRecord):
    """Specialized log record for decision-making operations."""
    
    decision_type: Optional[str] = Field(None, description="Type of decision")
    decision_context: Optional[Dict[str, Any]] = Field(None, description="Decision context")
    alternatives: Optional[List[Dict[str, Any]]] = Field(None, description="Alternative options")
    reasoning_chain: Optional[List[str]] = Field(None, description="Reasoning steps")


class IOTraceRecord(LogRecord):
    """Specialized log record for IO tracing."""
    
    io_type: str = Field(..., description="Type of IO operation")
    input_hash: Optional[str] = Field(None, description="Input hash")
    output_hash: Optional[str] = Field(None, description="Output hash")
    bytes_in: Optional[int] = Field(None, description="Input bytes")
    bytes_out: Optional[int] = Field(None, description="Output bytes")
    preview_in: Optional[str] = Field(None, description="Input preview")
    preview_out: Optional[str] = Field(None, description="Output preview")
    blob_uri_in: Optional[str] = Field(None, description="Input blob URI")
    blob_uri_out: Optional[str] = Field(None, description="Output blob URI")
    schema_ok: Optional[bool] = Field(None, description="Schema validation result")
    validator_errors: Optional[List[str]] = Field(None, description="Validation errors")
