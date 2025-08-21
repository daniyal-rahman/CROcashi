# ncfd/src/ncfd/mapping/deterministic.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Set, Dict
import re

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session

# Strict and loose normalizers:
# - norm_name(): existing behavior (unchanged)
# - norm_name_loose(): additionally drops joiners like "and" so "&" ≡ "and"
from ncfd.mapping.normalize import norm_name, norm_name_loose

# Tolerate closing punctuation after a domain
DOMAIN_RE = re.compile(
    r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})(?=[/\s\)\]\}\.,;:'\"!?]|$)",
    re.IGNORECASE,
)

DEFAULT_ALIAS_TYPES: Set[str] = {
    "aka", "dba", "former_name", "short", "subsidiary", "brand", "legal"
}
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
    """
    High-precision deterministic resolver:
      1) exact alias_norm within allowed alias types (strict, then loose)
      2) exact companies.name_norm (strict, then loose)
      3) exact domain match (alias_type='domain' or companies.website_domain)

    The *loose* fallback treats 'and' ≡ '&' (and removes whole-word 'and'),
    fixing cases like "Organon and Co" vs stored "Organon & Co." → "organon co".
    """
    if not sponsor_text or not sponsor_text.strip():
        return None

    allowed_alias_types = set(allowed_alias_types or DEFAULT_ALIAS_TYPES)

    sponsor_norm_strict = norm_name(sponsor_text)
    sponsor_norm_loose = norm_name_loose(sponsor_text)
    dom = _extract_domain_candidate(sponsor_text)

    # ---------------------------------------------------------------------- #
    # 1) alias_exact (strict), then alias_exact_loose
    # ---------------------------------------------------------------------- #
    if allowed_alias_types:
        q_alias = text(
            """
            SELECT DISTINCT company_id
              FROM company_aliases
             WHERE alias_norm = :norm
               AND alias_type IN :types
            """
        ).bindparams(bindparam("types", expanding=True))

        # strict
        rows = session.execute(
            q_alias, {"norm": sponsor_norm_strict, "types": tuple(allowed_alias_types)}
        ).fetchall()
        if len(rows) == 1:
            return Resolution(
                company_id=int(rows[0][0]),
                method="alias_exact",
                evidence={"alias_norm": sponsor_norm_strict, "raw": sponsor_text},
            )

        # loose fallback (only if different)
        if sponsor_norm_loose != sponsor_norm_strict:
            rows = session.execute(
                q_alias, {"norm": sponsor_norm_loose, "types": tuple(allowed_alias_types)}
            ).fetchall()
            if len(rows) == 1:
                return Resolution(
                    company_id=int(rows[0][0]),
                    method="alias_exact_loose",
                    evidence={"alias_norm": sponsor_norm_loose, "raw": sponsor_text},
                )

    # ---------------------------------------------------------------------- #
    # 2) company_name_exact (strict), then company_name_exact_loose
    # ---------------------------------------------------------------------- #
    q_company = text("SELECT company_id FROM companies WHERE name_norm = :norm")

    # strict
    rows = session.execute(q_company, {"norm": sponsor_norm_strict}).fetchall()
    if len(rows) == 1:
        return Resolution(
            company_id=int(rows[0][0]),
            method="company_name_exact",
            evidence={"name_norm": sponsor_norm_strict, "raw": sponsor_text},
        )

    # loose fallback
    if sponsor_norm_loose != sponsor_norm_strict:
        rows = session.execute(q_company, {"norm": sponsor_norm_loose}).fetchall()
        if len(rows) == 1:
            return Resolution(
                company_id=int(rows[0][0]),
                method="company_name_exact_loose",
                evidence={"name_norm": sponsor_norm_loose, "raw": sponsor_text},
            )

    # ---------------------------------------------------------------------- #
    # 3) domain matches (alias_type='domain') or companies.website_domain
    # ---------------------------------------------------------------------- #
    if dom:
        # alias table (strip leading www.)
        rows = session.execute(
            text(
                """
                SELECT DISTINCT company_id
                  FROM company_aliases
                 WHERE alias_type = :t
                   AND lower(regexp_replace(alias, '^www\\.', '')) = :dom
                """
            ),
            {"t": DOMAIN_ALIAS_TYPE, "dom": dom},
        ).fetchall()
        if len(rows) == 1:
            return Resolution(
                company_id=int(rows[0][0]),
                method="domain_exact",
                evidence={"domain": dom, "raw": sponsor_text},
            )

        # companies.website_domain fallback
        rows = session.execute(
            text(
                """
                SELECT company_id
                  FROM companies
                 WHERE lower(regexp_replace(COALESCE(website_domain, ''), '^www\\.', '')) = :dom
                """
            ),
            {"dom": dom},
        ).fetchall()
        if len(rows) == 1:
            return Resolution(
                company_id=int(rows[0][0]),
                method="website_domain",
                evidence={"domain": dom, "raw": sponsor_text},
            )

    return None
