# src/ncfd/ingest/aliases.py
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Tuple, Dict, Any, Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ncfd.db.models import CompanyAlias


@dataclass(frozen=True)
class AliasInput:
    company_id: int
    text: str
    source: Optional[str] = None
    source_url: Optional[str] = None


__all__ = ["AliasInput", "ingest_aliases_from_text"]


# Conservative suffixes to trim from END when normalizing
_SUFFIXES: Tuple[str, ...] = (
    "inc", "inc.", "incorporated",
    "corp", "corp.", "corporation",
    "co", "co.", "company",
    "ltd", "ltd.", "limited",
    "plc", "nv", "ag", "sa", "s.a.", "bv",
    "holdings", "group",
    "therapeutics", "pharmaceuticals", "biosciences",
    "biopharma", "bioscience", "biotech", "sciences", "pharma",
    "bio",
)


def _ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def normalize_name(name: str) -> str:
    """
    Lowercase, ASCII-fold, remove punctuation, collapse spaces,
    then drop trailing corporate/suffix tokens.
    """
    s = _ascii_fold(name or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return s
    parts = s.split(" ")
    while parts and parts[-1] in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


# ---- helpers ---------------------------------------------------------------

# Trim trailing punctuation but **preserve a final period** if the last token
# is an abbreviation like "Inc." / "Co." / "Corp." etc.
_ABBR_LAST_WORDS = {"inc.", "co.", "corp.", "ltd.", "s.a."}


def _smart_rtrim(alias: str) -> str:
    a = alias.strip()
    # remove trailing commas/semicolons/colons/closing parens/spaces
    a = re.sub(r"[\s,;:)\]]+$", "", a)
    # if endswith ".", keep it if part of an abbreviation token
    if a.endswith("."):
        tokens = a.split()
        if tokens and tokens[-1].lower() in _ABBR_LAST_WORDS:
            return a
        # else drop a bare trailing dot (rare)
        return a[:-1]
    return a


# --------- High-precision extractors (DOTALL to cross line breaks) ----------

_FKA_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"\(\s*formerly\s+known\s+as\s+([^)]+?)\s*\)", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bformerly\s+known\s+as\s+(.+?)(?:[);,\.]|$)", re.IGNORECASE | re.DOTALL),
)

_DBA_PATTERN = re.compile(
    r"\b(?:is\s+)?(?:doing\s+business\s+as|d/b/a)\s+([A-Z][A-Za-z0-9&.\- ]+?)(?:(?:\s+(?:in|within|for)\b)|[),.;]|$)",
    re.IGNORECASE | re.DOTALL,
)

# Capture the subsidiary *name* before ", a wholly-owned subsidiary of ..."
# Be flexible about hyphen/space between wholly and owned, and allow optional "a".
_SUBSIDIARY_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(
        r"""
        (?P<name>
            [A-Z][^,]+?                              # name up to first comma
            (?:,\s*(?:Inc\.|Incorporated|Corp\.|Corporation|
                     Co\.|Company|Ltd\.|LLC|PLC|N\.V\.|S\.A\.)  # optional suffix
            )?
        )
        \s*,\s*
        (?:an?\s+)?(?:indirect\s+)?(?:wholly(?:-| )?owned\s+)?subsidiary\s+of\b
        """,
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    ),
    re.compile(
        r"""
        (?P<name>[A-Z][A-Za-z0-9&.\- ]+?)            # plain name
        \s+is\s+(?:an?\s+)?(?:indirect\s+)?(?:wholly(?:-| )?owned\s+)?subsidiary\s+of\b
        """,
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    ),
)

def _extract_fka(text_body: str) -> List[str]:
    out: List[str] = []
    t = text_body or ""
    for pat in _FKA_PATTERNS:
        for m in pat.finditer(t):
            alias = _smart_rtrim(m.group(1))
            if alias:
                out.append(alias)
    return out


def _extract_dba(text_body: str) -> List[str]:
    out: List[str] = []
    t = text_body or ""
    for m in _DBA_PATTERN.finditer(t):
        alias = _smart_rtrim(m.group(1))
        if alias:
            out.append(alias)
    return out


def _extract_subsidiary(text_body: str) -> List[str]:
    t = text_body or ""
    out: List[str] = []
    for pat in _SUBSIDIARY_PATTERNS:
        for m in pat.finditer(t):
            alias = _smart_rtrim(m.group("name"))
            if alias:
                out.append(alias)
    return out


def _dedupe_candidates(
    cands: Iterable[Tuple[str, str, Dict[str, Any]]]
) -> List[Tuple[str, str, Dict[str, Any]]]:
    seen: set[Tuple[str, str]] = set()
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    for alias, atype, extra in cands:
        key = (normalize_name(alias), atype)
        if key in seen:
            continue
        seen.add(key)
        out.append((alias, atype, extra))
    return out


def ingest_aliases_from_text(session: Session, items: Iterable[AliasInput]) -> Dict[str, int]:
    """
    Extract aliases from free text (FKA / DBA / subsidiary), normalize, and
    upsert into company_aliases. Returns {'inserted': N, 'skipped': M}.
    """
    inserted = 0
    skipped = 0

    for item in items:
        parent_norm = session.execute(
            text("SELECT name_norm FROM companies WHERE company_id=:cid"),
            {"cid": item.company_id},
        ).scalar_one_or_none()

        t = item.text or ""
        candidates: List[Tuple[str, str, Dict[str, Any]]] = []

        for alias in _extract_fka(t):
            candidates.append((alias, "former_name", {}))

        for alias in _extract_dba(t):
            candidates.append((alias, "dba", {}))

        for alias in _extract_subsidiary(t):
            candidates.append((alias, "subsidiary", {}))

        candidates = _dedupe_candidates(candidates)

        for alias, alias_type, extra in candidates:
            alias_norm = normalize_name(alias)
            if not alias_norm:
                skipped += 1
                continue
            if parent_norm and alias_norm == parent_norm:
                skipped += 1
                continue

            alias_company_id = None
            if alias_type == "subsidiary":
                alias_company_id = session.execute(
                    text("SELECT company_id FROM companies WHERE name_norm=:nn LIMIT 1"),
                    {"nn": alias_norm},
                ).scalar_one_or_none()

            ins = (
                insert(CompanyAlias.__table__)
                .values(
                    company_id=item.company_id,
                    alias=alias,
                    alias_norm=alias_norm,
                    alias_type=alias_type,  # labels match PG enum
                    source=item.source,
                    source_url=item.source_url,
                    alias_company_id=alias_company_id,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        CompanyAlias.__table__.c.company_id,
                        CompanyAlias.__table__.c.alias_norm,
                        CompanyAlias.__table__.c.alias_type,
                    ]
                )
                .returning(CompanyAlias.__table__.c.alias_id)
            )

            res = session.execute(ins)
            if res.fetchone() is not None:
                inserted += 1
            else:
                skipped += 1

    return {"inserted": inserted, "skipped": skipped}
