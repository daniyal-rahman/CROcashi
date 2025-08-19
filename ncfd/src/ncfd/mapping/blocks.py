# ncfd/src/ncfd/mapping/blocks.py
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from ncfd.mapping.normalize import norm_name, tokens_of
from ncfd.mapping.probabilistic import extract_domains

_DRUG_CODE_RE = re.compile(r"\b[A-Z]{1,5}-\d{2,5}[A-Z]?\b")  # e.g., AB-123, ABCD-0012A

_GENERIC_WEAK = {
    "bio","biosciences","biotech","pharma","pharmaceutical","pharmaceuticals",
    "therapeutic","therapeutics","inc","corp","ltd","plc","llc","company","holding","holdings"
}

def strong_tokens(s: str) -> List[str]:
    toks = tokens_of(s)
    return [t for t in toks if len(t) >= 6 and t not in _GENERIC_WEAK]

@dataclass
class TrialParty:
    nct_id: str
    texts: List[str]         # sponsor + collaborators + responsible party
    interventions: List[str] # intervention names (for codes)

@dataclass
class CandidateContext:
    nct_id: str
    domains: List[str]
    drug_codes: List[str]
    strong_token_pairs: List[Tuple[str, str]]  # for optional stricter blocking

def _latest_version_row(session: Session, trial_id: int) -> Optional[Dict[str, Any]]:
    row = session.execute(text("""
      SELECT raw_jsonb
      FROM trial_versions
      WHERE trial_id = :tid
      ORDER BY captured_at DESC
      LIMIT 1
    """), {"tid": trial_id}).fetchone()
    return dict(row[0]) if row else None

def _extract_ctgov_parties(raw: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    if not raw:
        return out
    # Typical CT.gov JSON shapes (defensive)
    lead = (((raw.get("sponsors") or {}).get("lead_sponsor") or {}).get("name"))
    collabs = (raw.get("sponsors") or {}).get("collaborators") or []
    resp = ((raw.get("responsible_party") or {}).get("name"))
    agency_class = (raw.get("agency_class"))  # often "Industry", etc.
    for v in [lead, resp, agency_class] + [c.get("name") for c in collabs if isinstance(c, dict)]:
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return list(dict.fromkeys(out))  # dedupe/preserve order

def _extract_interventions(raw: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    if not raw:
        return out
    for it in raw.get("interventions") or []:
        if isinstance(it, dict):
            nm = it.get("name") or ""
            if nm:
                out.append(nm)
    return list(dict.fromkeys(out))

def load_trial_party(session: Session, trial_id: int, nct_id: str, sponsor_text: str) -> TrialParty:
    raw = _latest_version_row(session, trial_id) or {}
    texts = [sponsor_text] if sponsor_text else []
    texts += _extract_ctgov_parties(raw)
    intervs = _extract_interventions(raw)
    # minimal cleanup
    texts = [t for t in texts if t and t.strip()]
    return TrialParty(nct_id=nct_id, texts=list(dict.fromkeys(texts)), interventions=intervs)

def derive_context(tp: TrialParty) -> CandidateContext:
    # domains from any party text
    doms = []
    for t in tp.texts:
        doms.extend(extract_domains(t))
    doms = list(dict.fromkeys([d.lower() for d in doms]))

    # drug codes from interventions + party text (rare)
    codes = []
    txt = " ; ".join(tp.texts + tp.interventions)
    for m in _DRUG_CODE_RE.finditer(txt.upper()):
        codes.append(m.group(0))
    codes = list(dict.fromkeys(codes))

    # strong token pairs (blocking key)
    stoks = strong_tokens(" ".join(tp.texts))
    pairs: List[Tuple[str, str]] = []
    for i in range(len(stoks)):
        for j in range(i+1, len(stoks)):
            pairs.append(tuple(sorted((stoks[i], stoks[j]))))
    return CandidateContext(nct_id=tp.nct_id, domains=doms, drug_codes=codes, strong_token_pairs=pairs)
