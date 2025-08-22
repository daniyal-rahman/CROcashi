"""Deterministic short-circuit + persistence for resolver CLI."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ncfd.mapping.det import det_resolve
from ncfd.mapping.normalize import norm_name as _basic_norm


def _persist_det_decision(
    session: Session,
    *,
    run_id: str,
    nct_id: str,
    sponsor_text: str,
    company_id: int,
    decided_by: str = "auto",
    evidence: Optional[dict] = None,
) -> None:
    """
    Write a deterministic decision into resolver_decisions.
    Upserts on (run_id, nct_id, sponsor_text_norm).
    """
    sponsor_norm = _basic_norm(sponsor_text)
    evidence_json = json.dumps(evidence or {"method": "det_rule"})

    session.execute(
        text(
            """
            INSERT INTO resolver_decisions (
                run_id, nct_id, sponsor_text, sponsor_text_norm,
                company_id, match_type, p_match, top2_margin,
                features_jsonb, evidence_jsonb, decided_by
            )
            VALUES (
                :run_id, :nct_id, :sponsor_text, :sponsor_norm,
                :company_id, 'deterministic:rule', NULL, NULL,
                '{}'::jsonb, :evidence_jsonb, :decided_by
            )
            ON CONFLICT (run_id, nct_id, sponsor_text_norm) DO UPDATE
            SET company_id      = EXCLUDED.company_id,
                match_type      = EXCLUDED.match_type,
                p_match         = EXCLUDED.p_match,
                top2_margin     = EXCLUDED.top2_margin,
                features_jsonb  = EXCLUDED.features_jsonb,
                evidence_jsonb  = EXCLUDED.evidence_jsonb,
                decided_by      = EXCLUDED.decided_by,
                decided_at      = now()
            ;
            """
        ),
        {
            "run_id": run_id,
            "nct_id": nct_id,
            "sponsor_text": sponsor_text,
            "sponsor_norm": sponsor_norm,
            "company_id": company_id,
            "evidence_jsonb": evidence_json,
            "decided_by": decided_by,
        },
    )


def det_short_circuit(
    session: Session,
    *,
    nct_id: str,
    sponsor_text: str,
    run_id: str,
    persist: bool,
    apply_trial: bool,
) -> bool:
    """
    If a det rule matches, optionally persist + apply, print a one-line summary,
    and return True (meaning: caller should STOP and not run probabilistic).
    Otherwise return False so caller continues as usual.
    """
    det = det_resolve(session, sponsor_text)
    if not getattr(det, "company_id", None):
        return False

    cid = det.company_id
    print(f"[det] {nct_id} :: {sponsor_text!r} -> cid={cid} method={det.method}")

    if persist:
        _persist_det_decision(
            session,
            run_id=run_id,
            nct_id=nct_id,
            sponsor_text=sponsor_text,
            company_id=cid,
            decided_by="auto",
            evidence={"method": det.method},
        )
        if apply_trial:
            session.execute(
                text("UPDATE trials SET sponsor_company_id = :cid WHERE nct_id = :nct_id"),
                {"cid": cid, "nct_id": nct_id},
            )
    return True
