# ncfd/mapping/alias_promotion.py
from __future__ import annotations
import re
from sqlalchemy import text
from sqlalchemy.orm import Session
from ncfd.mapping.normalize import norm_name

# very lightweight "looks like a registered name" heuristic
LEGAL_SUFFIX_RE = re.compile(
    r"""
    \b(
      inc|inc\.|incorporated|
      corp|corporation|
      ltd|ltd\.|limited|
      llc|plc|ag|gmbh|
      s\.?a\.?|s\.p\.a\.|
      nv|bv|oy|ab|kk|
      co\.?,?\s*ltd\.?|
      co\.|company
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

def _alias_type_for_sponsor(raw: str) -> str:
    return "legal" if (raw and LEGAL_SUFFIX_RE.search(raw)) else "aka"

def _is_ignored_sponsor(session: Session, sponsor_text: str) -> bool:
    if not sponsor_text:
        return False
    # Skip academic/gov patterns you store in resolver_ignore_sponsor
    hit = session.execute(
        text("""
            SELECT 1
              FROM resolver_ignore_sponsor
             WHERE :sponsor ~* pattern
             LIMIT 1
        """),
        {"sponsor": sponsor_text},
    ).first()
    return bool(hit)

def upsert_alias_from_sponsor(session: Session, company_id: int, sponsor_text: str) -> bool:
    """
    Promote the sponsor_text as an alias for the resolved company.
    Returns True if we inserted a new row, False if it already existed or was skipped.
    """
    if not sponsor_text or not sponsor_text.strip():
        return False
    if _is_ignored_sponsor(session, sponsor_text):
        return False

    atype = _alias_type_for_sponsor(sponsor_text)
    nrm = norm_name(sponsor_text)

    res = session.execute(
        text("""
            WITH ins AS (
              INSERT INTO company_aliases (company_id, alias, alias_norm, alias_type)
              SELECT :cid, :alias, :norm, :atype
              WHERE NOT EXISTS (
                  SELECT 1
                    FROM company_aliases
                   WHERE company_id = :cid
                     AND alias_norm = :norm
                     AND alias_type = :atype
              )
              RETURNING 1
            )
            SELECT EXISTS (SELECT 1 FROM ins) AS inserted;
        """),
        {"cid": company_id, "alias": sponsor_text, "norm": nrm, "atype": atype},
    ).scalar()
    return bool(res)
