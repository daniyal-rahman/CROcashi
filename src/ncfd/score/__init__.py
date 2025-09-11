from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ScoreResult:
    trial_id: str
    run_id: str
    prior_pi: float
    logit_prior: float
    sum_log_lr: float
    logit_post: float
    p_fail: float


class ScoringEngine:
    """Minimal scoring engine shim for orchestrator compatibility."""

    def __init__(self) -> None:
        pass

    def score_trial(
        self,
        trial_id: str,
        metadata: Dict[str, Any],
        gates: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> ScoreResult:
        # Very simple placeholder logic: if any gates provided and any 'FAIL', set high p_fail
        has_fail = any(getattr(g, "status", "").upper() == "FAIL" for g in gates.values()) if gates else False
        p_fail = 0.9 if has_fail else 0.5
        return ScoreResult(
            trial_id=str(trial_id),
            run_id=run_id or "default",
            prior_pi=0.5,
            logit_prior=0.0,
            sum_log_lr=-2.0 if has_fail else 0.0,
            logit_post=-2.0 if has_fail else 0.0,
            p_fail=p_fail,
        )
