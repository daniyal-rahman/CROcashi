# ncfd/src/ncfd/mapping/persist.py
from __future__ import annotations

from dataclasses import is_dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB

from ncfd.mapping.normalize import norm_name

# ----- Optional type hints (do not create hard deps) -------------------------
try:
    from ncfd.mapping.probabilistic import ProbDecision, Scored  # type: ignore
except Exception:  # pragma: no cover
    ProbDecision = Any  # type: ignore
    Scored = Any        # type: ignore

try:
    from ncfd.mapping.deterministic import Resolution  # type: ignore
except Exception:  # pragma: no cover
    Resolution = Any  # type: ignore


# ============================== helpers =====================================

def sponsor_is_ignored(session: Session, sponsor_text: str) -> bool:
    """
    True if this sponsor should be ignored per resolver_ignore_sponsor(pattern).
    Uses a case-insensitive regex match: :s ~* pattern
    """
    return session.execute(
        text("""
            SELECT EXISTS (
              SELECT 1
              FROM resolver_ignore_sponsor
              WHERE :s ~* pattern
            )
        """),
        {"s": sponsor_text or ""},
    ).scalar_one()


def _as_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj):
        return asdict(obj)
    # Best-effort: pick common attributes
    out: Dict[str, Any] = {}
    for k in ("company_id", "p", "features", "meta", "leader_meta", "mode", "top2_margin"):
        if hasattr(obj, k):
            out[k] = getattr(obj, k)
    return out


def _coerce_scored(item: Any) -> Tuple[int, float, Dict[str, Any], Dict[str, Any]]:
    """
    Normalize a Scored-like object/dict to (company_id, p, features, meta).
    """
    d = _as_dict(item)
    cid = int(d.get("company_id"))
    p = float(d.get("p", 0.0) or 0.0)
    feats = dict(d.get("features") or {})
    meta = dict(d.get("meta") or {})
    return cid, p, feats, meta


def _decision_payload(
    decision: Any,
    leader_features: Optional[Dict[str, Any]] = None,
    leader_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convert a deterministic/probabilistic decision into the resolver_decisions payload.
    """
    if decision is None:
        return {
            "company_id": None,
            "match_type": "no_match",
            "p_match": 0.0,
            "top2_margin": 0.0,
            "features_jsonb": {},
            "evidence_jsonb": {},
        }

    # Deterministic: has method + company_id
    if hasattr(decision, "method") and hasattr(decision, "company_id"):
        ev = dict(getattr(decision, "evidence", {}) or {})
        return {
            "company_id": int(decision.company_id),
            "match_type": f"deterministic:{decision.method}",
            "p_match": 1.0,
            "top2_margin": 1.0,
            "features_jsonb": dict(leader_features or {}),
            "evidence_jsonb": {"evidence": ev},
        }

    # Probabilistic
    d = _as_dict(decision)
    mode = str(d.get("mode") or "unknown")
    cid = d.get("company_id")
    p = float(d.get("p", 0.0) or 0.0)
    margin = float(d.get("top2_margin", 0.0) or 0.0)
    feats = dict(leader_features or d.get("features") or {})
    meta = dict(leader_meta or d.get("leader_meta") or {})

    return {
        "company_id": (int(cid) if cid is not None else None),
        "match_type": f"probabilistic:{mode}",
        "p_match": p,
        "top2_margin": margin,
        "features_jsonb": feats,
        "evidence_jsonb": {"leader_meta": meta},
    }


# =============================== writers ====================================

def persist_candidate_features(
    session: Session,
    *,
    run_id: str,
    nct_id: str,
    sponsor_text: str,
    scored_candidates: Iterable[Any],
) -> None:
    """
    Write per-candidate features to resolver_features.

    Table expected columns (as in your schema):
      run_id, nct_id, sponsor_text_norm, company_id, features_jsonb, score_precal, p_calibrated
    """
    s_norm = norm_name(sponsor_text or "")

    sql = text("""
        INSERT INTO resolver_features
            (run_id, nct_id, sponsor_text_norm, company_id, features_jsonb, score_precal, p_calibrated)
        VALUES
            (:run_id, :nct_id, :s_norm, :company_id, :features, NULL, :p)
    """).bindparams(bindparam("features", type_=JSONB))

    for item in scored_candidates:
        cid, p, feats, _meta = _coerce_scored(item)
        session.execute(
            sql,
            {
                "run_id": run_id,
                "nct_id": nct_id,
                "s_norm": s_norm,
                "company_id": cid,
                "features": feats,  # JSONB-bound (no ::jsonb cast in SQL)
                "p": p,
            },
        )
    # commit handled by caller (context manager)


def persist_decision(
    session: Session,
    *,
    run_id: str,
    nct_id: str,
    sponsor_text: str,
    decision: Any,
    decided_by: str = "auto",  # auto|human|llm
    leader_features: Optional[Dict[str, Any]] = None,
    leader_meta: Optional[Dict[str, Any]] = None,
    notes_md: Optional[str] = None,
) -> None:
    """
    Upsert into resolver_decisions for this (run_id, nct_id, sponsor_text_norm).
    """
    s_norm = norm_name(sponsor_text or "")
    payload = _decision_payload(decision, leader_features, leader_meta)

    sql = text("""
        INSERT INTO resolver_decisions
            (run_id, nct_id, sponsor_text, sponsor_text_norm,
             company_id, match_type, p_match, top2_margin,
             features_jsonb, evidence_jsonb, decided_by, notes_md)
        VALUES
            (:run_id, :nct_id, :s_text, :s_norm,
             :company_id, :match_type, :p_match, :top2_margin,
             :features_jsonb, :evidence_jsonb, :decided_by, :notes_md)
        ON CONFLICT (run_id, nct_id, sponsor_text_norm)
        DO UPDATE SET
            company_id   = EXCLUDED.company_id,
            match_type   = EXCLUDED.match_type,
            p_match      = EXCLUDED.p_match,
            top2_margin  = EXCLUDED.top2_margin,
            features_jsonb = EXCLUDED.features_jsonb,
            evidence_jsonb = EXCLUDED.evidence_jsonb,
            decided_by   = EXCLUDED.decided_by,
            notes_md     = COALESCE(EXCLUDED.notes_md, resolver_decisions.notes_md)
    """).bindparams(
        bindparam("features_jsonb", type_=JSONB),
        bindparam("evidence_jsonb", type_=JSONB),
    )

    session.execute(
        sql,
        {
            "run_id": run_id,
            "nct_id": nct_id,
            "s_text": sponsor_text,
            "s_norm": s_norm,
            "company_id": payload["company_id"],
            "match_type": payload["match_type"],
            "p_match": payload["p_match"],
            "top2_margin": payload["top2_margin"],
            "features_jsonb": payload["features_jsonb"],
            "evidence_jsonb": payload["evidence_jsonb"],
            "decided_by": decided_by,
            "notes_md": notes_md,
        },
    )
    # commit handled by caller


from typing import Any, Dict, Iterable, List
import sqlalchemy as sa
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

def _norm(s: str | None) -> str:
    """lower + collapse whitespace; mirrors the SQL backfill we used."""
    if not s:
        return ""
    return " ".join(s.split()).lower()

def enqueue_review(
    session: sa.orm.Session,
    *,
    run_id: str,
    nct_id: str,
    sponsor_text: str,
    candidates: Iterable[Any],
    reason: str = "prob_review",
) -> None:
    """
    Insert a *pending* item into review_queue.

    review_queue columns used:
      run_id, nct_id, sponsor_text, sponsor_text_norm, candidates(JSONB), reason, status='pending'
    Partial-unique guard in DB: (run_id, nct_id, sponsor_text_norm) WHERE status='pending'
    """
    # --- serialize candidates ---
    serial: List[Dict[str, Any]] = []
    for item in candidates:
        cid, p, feats, meta = _coerce_scored(item)
        row: Dict[str, Any] = {"company_id": cid, "p": p, "features": feats, "meta": meta}
        if "name" in meta:
            row["name"] = meta["name"]
        serial.append(row)
    serial.sort(key=lambda x: x.get("p", 0.0), reverse=True)

    s_norm = _norm(sponsor_text)

    # --- insert, but skip if a pending duplicate already exists ---
    sql = text("""
        INSERT INTO review_queue
            (run_id, nct_id, sponsor_text, sponsor_text_norm, candidates, reason, status)
        SELECT
            :run_id, :nct_id, :s_text, :s_norm, :cands, :reason, 'pending'
        WHERE NOT EXISTS (
            SELECT 1 FROM review_queue
            WHERE status = 'pending'
              AND run_id = :run_id
              AND nct_id = :nct_id
              AND sponsor_text_norm = :s_norm
        )
    """).bindparams(bindparam("cands", type_=JSONB))

    params = {
        "run_id": run_id,
        "nct_id": nct_id,
        "s_text": sponsor_text,
        "s_norm": s_norm,
        "cands": serial,
        "reason": reason,
    }

    try:
        session.execute(sql, params)
    except IntegrityError:
        # Race with the partial-unique index: safe to ignore for idempotency
        session.rollback()
        return
    # commit handled by caller
