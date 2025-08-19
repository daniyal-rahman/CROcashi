# ncfd/src/ncfd/mapping/deterministic.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Optional, Set, Dict
import re

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session

from ncfd.mapping.normalize import norm_name

# Tolerate closing punctuation after a domain
DOMAIN_RE = re.compile(
    r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})(?=[/\s\)\]\}\.,;:'\"!?]|$)",
    re.IGNORECASE,
)

DEFAULT_ALIAS_TYPES: Set[str] = {"aka", "dba", "former_name", "short", "subsidiary", "brand", "legal"}
DOMAIN_ALIAS_TYPE = "domain"

@dataclass(frozen=True)
class Resolution:
    company_id: int
    method: str
    evidence: Dict[str, str]

def _extract_domain_candidate(s: str) -> Optional[str]:
    if not s:
        return None
    m = DOMAIN_RE.search(s.strip())
    if not m:
        return None
    dom = m.group(1).lower()
    if dom.startswith("www."):
        dom = dom[4:]
    return dom

def resolve_company(
    session: Session,
    sponsor_text: str,
    allowed_alias_types: Optional[Iterable[str]] = None,
) -> Optional[Resolution]:
    if not sponsor_text or not sponsor_text.strip():
        return None

    allowed_alias_types = set(allowed_alias_types or DEFAULT_ALIAS_TYPES)
    sponsor_norm = norm_name(sponsor_text)
    dom = _extract_domain_candidate(sponsor_text)

    # 1) Exact alias_norm for allowed types (high-precision)
    if allowed_alias_types:
        q = (
            text("""
                SELECT DISTINCT company_id
                  FROM company_aliases
                 WHERE alias_norm = :norm
                   AND alias_type IN :types
            """).bindparams(bindparam("types", expanding=True))
        )
        rows = session.execute(q, {"norm": sponsor_norm, "types": tuple(allowed_alias_types)}).fetchall()
        if len(rows) == 1:
            return Resolution(rows[0][0], "alias_exact",
                              {"alias_norm": sponsor_norm, "raw": sponsor_text})

    # 2) Exact companies.name_norm
    rows = session.execute(
        text("SELECT company_id FROM companies WHERE name_norm = :norm"),
        {"norm": sponsor_norm},
    ).fetchall()
    if len(rows) == 1:
        return Resolution(rows[0][0], "company_name_exact",
                          {"name_norm": sponsor_norm, "raw": sponsor_text})

    # 3) Domain matches (alias_type='domain' or companies.website_domain)
    if dom:
        # alias table (use alias column only; strip leading www.)
        rows = session.execute(
            text("""
                SELECT DISTINCT company_id
                  FROM company_aliases
                 WHERE alias_type = :t
                   AND lower(regexp_replace(alias, '^www\\.', '')) = :dom
            """),
            {"t": DOMAIN_ALIAS_TYPE, "dom": dom},
        ).fetchall()
        if len(rows) == 1:
            return Resolution(rows[0][0], "domain_exact",
                              {"domain": dom, "raw": sponsor_text})

        # companies.website_domain fallback
        rows = session.execute(
            text("""
                SELECT company_id
                  FROM companies
                 WHERE lower(regexp_replace(COALESCE(website_domain, ''), '^www\\.', '')) = :dom
            """),
            {"dom": dom},
        ).fetchall()
        if len(rows) == 1:
            return Resolution(rows[0][0], "website_domain",
                              {"domain": dom, "raw": sponsor_text})

    return None
