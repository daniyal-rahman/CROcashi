# ncfd/mapping/det.py

from dataclasses import dataclass
from typing import Optional, Dict, Any
import re
from sqlalchemy import text

# import the alias/domain resolver
from .deterministic import resolve_company as _resolve_company
from ncfd.mapping.normalize import norm_name as _basic_norm

# Fold Unicode dashes to ASCII hyphen
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2212\u2043\uFE58\uFE63\uFF0D"), ord('-'))
# Fold NBSP / figure / narrow NBSP to regular space
_SPACES = dict.fromkeys(map(ord, "\u00A0\u2007\u202F"), ord(' '))

@dataclass
class DetDecision:
    company_id: int
    method: str = "det_rule"
    evidence: Dict[str, Any] | None = None

# --- keep your _basic_norm / dash+space folding helpers here (omitted for brevity) ---

def _det_by_rules(session, sponsor_text: str) -> Optional[DetDecision]:
    rows = session.execute(
        text("""
            SELECT rule_id, pattern, company_id
              FROM resolver_det_rules
             ORDER BY priority DESC, rule_id ASC
        """)
    ).fetchall()

    raw = sponsor_text or ""
    folded = raw.translate(_DASHES).translate(_SPACES)
    normalized = _basic_norm(raw)

    for rule_id, pattern, company_id in rows:
        try:
            rx = re.compile(pattern)
        except re.error:
            continue
        for probe in (raw, folded, normalized):
            if rx.search(probe):
                return DetDecision(
                    company_id=int(company_id),
                    method="det_rule",
                    evidence={"rule_id": int(rule_id), "pattern": pattern, "matched": probe},
                )
    return None

def det_resolve(session, sponsor_text: str) -> Optional[DetDecision]:
    # 1) exact alias / company / domain
    alias_hit = _resolve_company(session, sponsor_text)
    if alias_hit:
        return DetDecision(
            company_id=int(alias_hit.company_id),
            method=f"det_alias:{alias_hit.method}",
            evidence=alias_hit.evidence,
        )

    # 2) rule-based Python regex
    return _det_by_rules(session, sponsor_text)
