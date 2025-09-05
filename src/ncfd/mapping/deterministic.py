# ncfd/src/ncfd/mapping/deterministic.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Set, Dict
import re

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session

from ncfd.mapping.normalize import norm_name, norm_name_loose, has_academic_keywords

# ---------------------------------------------------------------------------
# Regexes and normalizers
# ---------------------------------------------------------------------------

# Tolerate closing punctuation after a domain
DOMAIN_RE = re.compile(
    r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})(?=[/\s\)\]\}\.,;:'\"!?]|$)",
    re.IGNORECASE,
)

DEFAULT_ALIAS_TYPES: Set[str] = {
    "aka", "dba", "former_name", "short", "subsidiary", "brand", "legal"
}
DOMAIN_ALIAS_TYPE = "domain"

# Unicode folding for dash/space (for regex rule fallback)
_DASHES = dict.fromkeys(
    map(ord, "\u2010\u2011\u2012\u2013\u2014\u2212\u2043\uFE58\uFE63\uFF0D"),
    ord('-')
)
_SPACES = dict.fromkeys(map(ord, "\u00A0\u2007\u202F"), ord(' '))


@dataclass(frozen=True)
class Resolution:
    company_id: int
    method: str
    evidence: Dict[str, str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _det_by_rules(session: Session, sponsor_text: str) -> Optional[Resolution]:
    """
    Fallback: regex-based deterministic rules stored in resolver_det_rules.
    Applies patterns against raw, folded, and normalized sponsor text.
    """
    rows = session.execute(
        text("""
            SELECT rule_id, pattern, company_id
              FROM resolver_det_rules
             ORDER BY priority DESC, rule_id ASC
        """)
    ).fetchall()

    raw = sponsor_text or ""
    folded = raw.translate(_DASHES).translate(_SPACES)
    norm_strict = norm_name(raw)

    for rule_id, pattern, company_id in rows:
        try:
            rx = re.compile(pattern)
        except re.error:
            continue
        for probe in (raw, folded, norm_strict):
            if rx.search(probe):
                return Resolution(
                    company_id=int(company_id),
                    method="det_rule",
                    evidence={
                        "rule_id": str(rule_id),
                        "pattern": pattern,
                        "matched": probe,
                    },
                )
    return None


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def resolve_company(
    session: Session,
    sponsor_text: str,
    allowed_alias_types: Optional[Iterable[str]] = None,
) -> Optional[Resolution]:
    """
    Deterministic resolver:
      1) alias_exact (strict, then loose)
      2) company_name_exact (strict, then loose)
      3) domain_exact or website_domain
      4) rule-based regex fallback (resolver_det_rules)

    Returns Resolution(company_id, method, evidence) or None.
    """
    if not sponsor_text or not sponsor_text.strip():
        return None

    # Skip academic/government sponsors
    if has_academic_keywords(sponsor_text):
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

        # loose fallback
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

    rows = session.execute(q_company, {"norm": sponsor_norm_strict}).fetchall()
    if len(rows) == 1:
        return Resolution(
            company_id=int(rows[0][0]),
            method="company_name_exact",
            evidence={"name_norm": sponsor_norm_strict, "raw": sponsor_text},
        )

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

    # ---------------------------------------------------------------------- #
    # 4) regex rules fallback
    # ---------------------------------------------------------------------- #
    rule_hit = _det_by_rules(session, sponsor_text)
    if rule_hit:
        return rule_hit

    return None
