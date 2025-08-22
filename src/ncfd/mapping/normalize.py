# ncfd/src/ncfd/mapping/normalize.py
from __future__ import annotations
import re
import unicodedata
from typing import List

# --- corp/legal tails (keep sector terms like therapeutics/biopharma/etc.) ----
_LEGAL_TAILS = {
    "inc", "inc.", "incorporated",
    "corp", "corp.", "corporation",
    "co", "co.", "company", "companies",
    "ltd", "ltd.", "limited",
    "llc", "l.l.c", "llp", "l.l.p", "lp", "l.p",
    "plc", "plc.",
    "holding", "holdings",
    # common intl forms you'll see on US filings
    "ag", "nv", "sa", "s.a", "spa", "s.p.a", "gmbh", "oyj", "ab", "publ",
    "kabushiki", "kaisha", "kabushiki kaisha"
}

_ACADEMIC_WORDS = {
    "university", "hospital", "institute", "foundation", "college",
    "medical", "clinic", "centre", "center", "health", "system",
    "nhs", "trust", "school"
}

# --- regexes: preserve hyphens to keep asset codes like AB-123 intact ----------
_WS = re.compile(r"\s+")
_PUNCT_TO_SPACE = re.compile(r"[^\w\-]+", flags=re.UNICODE)  # hyphen is preserved
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*")         # tokens incl. hyphens (AB-123)
_JOINER_WORDS = {"and"}              # keep tiny & surgical for now
_JOINER_RE = re.compile(r"\b(?:and)\b", flags=re.IGNORECASE)

def _drop_joiners(s: str) -> str:
    """
    Remove whole-word joiners like 'and' so that 'X and Y' == 'X Y'.
    Run this AFTER _norm_text() so we only see word tokens.
    """
    # pad with spaces to make boundary handling trivial
    s2 = " " + s + " "
    s2 = _JOINER_RE.sub(" ", s2)
    return norm_spaces(s2)
def ascii_fold(s: str) -> str:
    """ASCII-fold (NFKD) and drop non-ascii."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if ord(ch) < 128)

def norm_spaces(s: str) -> str:
    return _WS.sub(" ", s).strip()

def _norm_text(s: str) -> str:
    """Lowercase, ASCII-fold, map punctuation (except '-') to spaces, collapse spaces."""
    s = ascii_fold(s)
    s = s.lower()
    s = _PUNCT_TO_SPACE.sub(" ", s)
    return norm_spaces(s)

# --- public API ---------------------------------------------------------------

def norm_name(s: str | None) -> str:
    """
    General normalization for names (does NOT strip legal tails).
    Use strip_legal() if you want tail removal.
    """
    if not s:
        return ""
    return _norm_text(s)

def norm_name_loose(s: str | None) -> str:
    """
    Normalization for deterministic matching:
      - same as norm_name()
      - additionally drops joiners like 'and' (so '&' and 'and' become equivalent)
    """
    if not s:
        return ""
    base = _norm_text(s)
    return _drop_joiners(base)

def strip_legal(s: str | None) -> str:
    """
    Remove trailing legal/corporate tail words only at the END of the string.
    Does not remove sector words (therapeutics/biopharma/etc.).
    """
    if not s:
        return ""
    s_norm = _norm_text(s)
    parts = s_norm.split(" ")
    # peel off legal tails from the end
    while parts:
        tail = parts[-1].strip(".,()")
        if tail in _LEGAL_TAILS:
            parts.pop()
            continue
        # two-word tails like "kabushiki kaisha"
        if len(parts) >= 2:
            pair = (parts[-2] + " " + parts[-1]).strip()
            if pair in _LEGAL_TAILS:
                parts.pop(); parts.pop()
                continue
        break
    return " ".join(parts)

def tokens_of(s: str, *, drop_generics: bool = False) -> list[str]:
    """
    Tokenize normalized text into alnum/hyphen tokens; preserves codes like AB-123.
    """
    s = _norm_text(s)
    toks = _WORD_RE.findall(s)
    # We intentionally do NOT drop sector generics here; caller can post-filter if desired.
    return toks

def acronym_of(s: str) -> str:
    """
    Build an acronym from significant tokens (ignores obvious legal tails and stop words).
    Hyphenated words contribute their first letter (e.g., 'Dana-Farber' -> 'D').
    """
    toks = tokens_of(s)
    stop = {"the", "and", "&", "of", "for", "at", "to", "in"} | _LEGAL_TAILS | _ACADEMIC_WORDS
    letters: List[str] = []
    for t in toks:
        base = t.split("-")[0]
        if base in stop or not base:
            continue
        letters.append(base[0])
    return "".join(letters).upper()

def has_academic_keywords(s: str) -> bool:
    s_norm = _norm_text(s)
    # simple contains; avoids stemming by using space padding
    return any(f" {w} " in f" {s_norm} " for w in _ACADEMIC_WORDS)

def ticker_in_text(ticker: str | None, text: str | None) -> bool:
    """
    Detects a ticker mention with token boundaries or common prefixes (NASDAQ: XYZ).
    """
    if not ticker or not text:
        return False
    t = _norm_text(ticker).upper()
    s = _norm_text(text)
    # simple patterns in normalized space; OK since we kept hyphens
    pats = (
        rf"\b{t}\b",
        rf"\b(?:nasdaq|nyse|amex|ticker)\s+{t}\b",
        rf"\(\s*{t}\s*\)"
    )
    return any(re.search(p, s, flags=re.IGNORECASE) for p in pats)

def norm_ticker(t: str | None) -> str:
    return (t or "").upper()
