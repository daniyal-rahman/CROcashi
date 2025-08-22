# src/ncfd/extract/aliases.py
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class AliasHit:
    alias: str
    alias_type: str          # "former_name" | "dba" | "aka" | "subsidiary"
    raw_span: str            # evidence span (for traceability)
    start_char: int
    end_char: int


# Token-ish company name: letters, digits, select punctuation; stops at strong delimiters.
_NAME = r"[A-Z0-9][A-Za-z0-9&,\.\-'/ ]{1,120}?"

# Very conservative patterns to keep precision high.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("former_name", re.compile(
        rf"(?:formerly\s+known\s+as|f/k/a|f\.k\.a\.)\s+(?P<alias>{_NAME})(?=[\)\.;,]|$)",
        re.IGNORECASE
    )),
    ("dba", re.compile(
        rf"(?:doing\s+business\s+as|d/b/a)\s+(?P<alias>{_NAME})(?=[\)\.;,]|$)",
        re.IGNORECASE
    )),
    ("aka", re.compile(
        rf"(?:also\s+known\s+as|a/k/a|a\.k\.a\.)\s+(?P<alias>{_NAME})(?=[\)\.;,]|$)",
        re.IGNORECASE
    )),
    # "<SUB>, a wholly-owned subsidiary of <PARENT>" — we'll capture SUB; caller will decide if it applies.
    ("subsidiary_leading", re.compile(
        rf"(?P<alias>{_NAME})\s*,?\s+a\s+(?:wholly[- ]owned\s+)?subsidiary\s+of\s+{_NAME}",
        re.IGNORECASE
    )),
    # "<PARENT>'s wholly-owned subsidiary, <SUB>," — capture SUB
    ("subsidiary_trailing", re.compile(
        rf"(?:wholly[- ]owned\s+)?subsidiary\s*,?\s+(?:named\s+)?(?P<alias>{_NAME})\s*,",
        re.IGNORECASE
    )),
]


def extract_aliases(text: str, *, context_company: Optional[str] = None) -> List[AliasHit]:
    """
    Extract high-precision aliases from free text.
    We avoid clever NER; just surgical regex with short spans.
    """
    hits: list[AliasHit] = []
    if not text:
        return hits

    for kind, rx in _PATTERNS:
        for m in rx.finditer(text):
            alias = m.group("alias").strip()
            # Guardrails: ignore 2-char junk etc.
            if len(alias) < 3 or alias.count(" ") == 0:
                continue
            # Avoid capturing the context company's own name as alias (common in '... formerly known as <same>').
            if context_company and alias.lower().strip() == context_company.lower().strip():
                continue
            hits.append(AliasHit(
                alias=alias,
                alias_type="subsidiary" if kind.startswith("subsidiary") else kind,
                raw_span=text[max(0, m.start()-40): min(len(text), m.end()+40)],
                start_char=m.start(),
                end_char=m.end(),
            ))
    return hits
