# ncfd/src/ncfd/mapping/persist.py
from __future__ import annotations
from typing import Any, Dict, Iterable, Optional, List

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql

from ncfd.mapping.normalize import norm_name


def persist_decision(
    session: Session,
    *,
    run_id: str,
    nct_id: str,
    sponsor_text: str,
    decision: Any,  # deterministic Resolution or probabilistic Decision
    leader_features: Optional[Dict[str, float]] = None,
    leader_meta: Optional[Dict[str, Any]] = None,
    decided_by: str = "auto",  # auto|human|llm
    notes_md: Optional[str] = None,
) -> None:
    """Upsert a resolver decision (deterministic or probabilistic accept)."""
    s_norm = norm_name(sponsor_text)

    if hasattr(decision, "method"):  # deterministic Resolution
        match_type = f"deterministic:{decision.method}"
        company_id = int(decision.company_id)
        p_match = 1.0
        top2_margin = 1.0
        features_jsonb = leader_features or {}
        evidence_jsonb = {
            "deterministic": True,
            "evidence": getattr(decision, "evidence", {}),
            "leader_meta": leader_meta or {},
        }
    else:  # probabilistic Decision (accept path)
        match_type = "probabilistic:accept"
        company_id = int(decision.company_id)
        p_match = float(getattr(decision, "p", 0.0) or 0.0)
        top2_margin = float(getattr(decision, "top2_margin", 0.0) or 0.0)
        features_jsonb = leader_features or getattr(decision, "features", {}) or {}
        evidence_jsonb = {
            "deterministic": False,
            "leader_meta": leader_meta or getattr(decision, "leader_meta", {}) or {},
        }

    sql = text("""
        INSERT INTO resolver_decisions
            (run_id, nct_id, sponsor_text, sponsor_text_norm,
             company_id, match_type, p_match, top2_margin,
             features_jsonb, evidence_jsonb, decided_by, notes_md)
        VALUES
            (:run_id, :nct_id, :s_raw, :s_norm,
             :company_id, :match_type, :p_match, :top2_margin,
             :features, :evidence, :decided_by, :notes_md)
        ON CONFLICT ON CONSTRAINT uq_resolver_decision_key
        DO UPDATE SET
            company_id = EXCLUDED.company_id,
            match_type = EXCLUDED.match_type,
            p_match = EXCLUDED.p_match,
            top2_margin = EXCLUDED.top2_margin,
            features_jsonb = EXCLUDED.features_jsonb,
            evidence_jsonb = EXCLUDED.evidence_jsonb,
            decided_by = EXCLUDED.decided_by,
            decided_at = now(),
            notes_md = COALESCE(EXCLUDED.notes_md, resolver_decisions.notes_md)
    """).bindparams(
        bindparam("features", type_=postgresql.JSONB),
        bindparam("evidence", type_=postgresql.JSONB),
    )

    session.execute(sql, {
        "run_id": run_id,
        "nct_id": nct_id,
        "s_raw": sponsor_text,
        "s_norm": s_norm,
        "company_id": company_id,
        "match_type": match_type,
        "p_match": p_match,
        "top2_margin": top2_margin,
        "features": features_jsonb,
        "evidence": evidence_jsonb,
        "decided_by": decided_by,
        "notes_md": notes_md,
    })


def persist_candidate_features(
    session: Session,
    *,
    run_id: str,
    nct_id: str,
    sponsor_text: str,
    scored_candidates: Iterable[Any],  # objects with .company_id, .p, .features
) -> None:
    """Append per-candidate feature rows for audit/calibration."""
    s_norm = norm_name(sponsor_text)
    sql = text("""
        INSERT INTO resolver_features
            (run_id, nct_id, sponsor_text_norm, company_id,
             features_jsonb, score_precal, p_calibrated)
        VALUES
            (:run_id, :nct_id, :s_norm, :company_id,
             :features, :score_precal, :p)
    """).bindparams(
        bindparam("features", type_=postgresql.JSONB),
    )
    for s in scored_candidates:
        session.execute(sql, {
            "run_id": run_id,
            "nct_id": nct_id,
            "s_norm": s_norm,
            "company_id": int(s.company_id),
            "features": dict(s.features or {}),
            "score_precal": None,  # optionally store raw logit later
            "p": float(getattr(s, "p", 0.0) or 0.0),
        })


def enqueue_review(
    session: Session,
    *,
    run_id: str,
    nct_id: str,
    sponsor_text: str,
    candidates: Iterable[Any],  # objects with .company_id, .p, .features
    reason: str = "prob_review",
) -> None:
    """Push gray-zone candidates to the review queue."""
    s_norm = norm_name(sponsor_text)
    pack: List[Dict[str, Any]] = []
    for s in candidates:
        pack.append({
            "company_id": int(s.company_id),
            "p": float(getattr(s, "p", 0.0) or 0.0),
            "features": dict(s.features or {}),
        })

    sql = text("""
        INSERT INTO resolver_review_queue
            (run_id, nct_id, sponsor_text, sponsor_text_norm,
             candidates_jsonb, reason, status)
        VALUES
            (:run_id, :nct_id, :s_raw, :s_norm,
             :cands, :reason, 'pending')
    """).bindparams(
        bindparam("cands", type_=postgresql.JSONB),
    )

    session.execute(sql, {
        "run_id": run_id,
        "nct_id": nct_id,
        "s_raw": sponsor_text,
        "s_norm": s_norm,
        "cands": pack,
        "reason": reason,
    })
