# ncfd/src/ncfd/mapping/resolve_service.py
from __future__ import annotations
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from ncfd.mapping.deterministic import resolve_company
from ncfd.mapping.normalize import norm_name
from ncfd.mapping.candidates import candidate_retrieval
from ncfd.mapping.probabilistic import score_candidates, decide_probabilistic

def resolve_sponsor(session: Session, sponsor_text: str, cfg: Dict[str, Any], context: Optional[Dict[str, Any]] = None):
    det = resolve_company(session, sponsor_text)
    if det:
        return {
            "mode": f"deterministic:{det.method}",
            "company_id": det.company_id,
            "p": 1.0,
            "top2_margin": 1.0,
            "features": {},
            "evidence": det.evidence,
        }
    cands = candidate_retrieval(session, norm_name(sponsor_text), k=50)
    scored = score_candidates(cands, sponsor_text, cfg["model"]["weights"], cfg["model"]["intercept"], context=context)
    th = cfg["thresholds"]
    dec = decide_probabilistic(scored, th["tau_accept"], th["review_low"], th["min_top2_margin"])
    return {
        "mode": f"probabilistic:{dec.mode}",
        "company_id": dec.company_id,
        "p": dec.p,
        "top2_margin": dec.top2_margin,
        "features": dec.features,
        "leader_meta": dec.leader_meta,
    }
