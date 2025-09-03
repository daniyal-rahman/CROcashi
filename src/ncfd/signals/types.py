"""
Signal types and dataclasses for precision-first failure detection.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


@dataclass
class SignalResult:
    """Result from a signal primitive (S1-S9)."""
    id: str  # e.g., "S1", "S2", etc.
    fired: Optional[bool] = None  # None = insufficient inputs
    value: Optional[float] = None
    severity: Optional[str] = None  # 'H' | 'M' | 'L'
    evidence_span: Optional[Dict[str, Any]] = None  # page/line spans, quotes, etc.
    source_study_id: Optional[str] = None
    notes: Optional[str] = None
    fired_at_run: Optional[str] = None


@dataclass 
class GateResult:
    """Result from a gate evaluation (G1-G4)."""
    id: str  # e.g., "G1", "G2", etc.
    fired: bool = False
    supporting_signals: List[str] = field(default_factory=list)
    lr_used: Optional[float] = None
    rationale: str = ""
    status: Literal["ok", "insufficient_inputs"] = "ok"


@dataclass
class ScoreResult:
    """Final scoring result with traceability."""
    trial_id: str
    run_id: str
    prior_pi: float
    logit_prior: float
    fired_gates: List[str] = field(default_factory=list)
    sum_log_lr: float = 0.0
    logit_post: float = 0.0
    p_fail: float = 0.0
    stop_rule_applied: Optional[str] = None
    config_version: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GateConfig:
    """Configuration for gate evaluation and scoring."""
    version: str
    gates: Dict[str, float]  # Gate ID -> LR
    primitive_lrs: Dict[str, float] = field(default_factory=dict)
    lr_caps: Dict[str, float] = field(default_factory=lambda: {"min": 1.0, "max": 10.0})
    stop_rules: Dict[str, bool] = field(default_factory=dict)
    p_cap: Dict[str, float] = field(default_factory=lambda: {"min": 0.01, "max": 0.99})
