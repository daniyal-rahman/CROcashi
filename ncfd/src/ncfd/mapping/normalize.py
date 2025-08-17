# ncfd/src/ncfd/mapping/normalize.py
from __future__ import annotations
import re
import unicodedata

# Only generic corporate designators (keep sector words like therapeutics, biopharma, pharma, etc.)
_CORP_SUFFIXES = {
    "inc", "inc.", "corp", "corp.", "co", "co.", "ltd", "ltd.", "plc", "plc.",
    "llc", "llp", "lp", "limited", "company", "companies", "holding", "holdings"
}

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")

def _strip_corp_suffixes(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in _CORP_SUFFIXES]

def norm_name(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    tokens = s.split(" ")
    tokens = _strip_corp_suffixes(tokens)
    out = " ".join(tokens).strip()
    return _WS.sub(" ", out)

def norm_ticker(t: str | None) -> str:
    return (t or "").upper()
