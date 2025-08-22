"""Data models for Phase 10 Catalyst System."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Literal, Dict, Any
from decimal import Decimal


@dataclass
class SlipStats:
    """Sponsor-specific slip factor statistics."""
    company_id: int
    mean_slip_days: int
    p10_days: int
    p90_days: int
    n_events: int
    updated_at: datetime


@dataclass
class StudyHint:
    """Study hint for catalyst window inference."""
    kind: Literal["exact_date", "conference", "quarter", "half", "year", "freeform"]
    start: date
    end: date
    weight: float
    raw_text: str
    study_id: int
    url: Optional[str] = None
    evidence_spans: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CatalystWindow:
    """Inferred catalyst window for a trial."""
    trial_id: int
    window_start: date
    window_end: date
    certainty: float
    sources: List[StudyHint] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class StudyCardRanking:
    """Study card ranking from evaluator."""
    trial_id: int
    evaluator_id: str
    score_1_10: int
    ranking_id: Optional[int] = None
    confidence_level: Optional[int] = None  # 1-5 scale
    reasoning_text: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not 1 <= self.score_1_10 <= 10:
            raise ValueError("score_1_10 must be between 1 and 10")
        if self.confidence_level is not None and not 1 <= self.confidence_level <= 5:
            raise ValueError("confidence_level must be between 1 and 5")


@dataclass
class LLMResolutionScore:
    """LLM-based resolution score expansion."""
    trial_id: int
    base_score_1_10: int
    expanded_score_1_100: int
    llm_provider: str
    resolution_id: Optional[int] = None
    llm_model: Optional[str] = None
    prompt_version: Optional[str] = None
    reasoning_text: Optional[str] = None
    confidence_score: Optional[Decimal] = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not 1 <= self.base_score_1_10 <= 10:
            raise ValueError("base_score_1_10 must be between 1 and 10")
        if not 1 <= self.expanded_score_1_100 <= 100:
            raise ValueError("expanded_score_1_100 must be between 1 and 100")
        if self.confidence_score is not None and not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError("confidence_score must be between 0.0 and 1.0")


@dataclass
class RankedTrial:
    """Trial with ranking information for sorting."""
    trial_id: int
    nct_id: str
    ticker: str
    phase: str
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    certainty: float = 0.0
    p_fail: float = 0.0
    study_card_score: float = 0.0
    llm_resolution_score: float = 0.0
    gates: List[str] = field(default_factory=list)
    proximity_score: int = 0

    def get_ranking_key(self, today: date) -> tuple[float, int, float, str]:
        """Generate ranking key for sorting: (-p_fail, proximity_score, -certainty, ticker)."""
        if self.window_end and self.window_end >= today:
            if self.window_start and self.window_end:
                window_mid = self.window_start + (self.window_end - self.window_start) // 2
                self.proximity_score = max(0, (window_mid - today).days)
        else:
            self.proximity_score = 9999  # Large penalty for past windows
        
        return (-self.p_fail, self.proximity_score, -self.certainty, self.ticker)


@dataclass
class BacktestRun:
    """Backtest run configuration."""
    run_name: str
    start_date: date
    end_date: date
    run_id: Optional[int] = None
    description: Optional[str] = None
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


@dataclass
class BacktestSnapshot:
    """Snapshot of trial state at a specific date."""
    run_id: int
    trial_id: int
    snapshot_date: date
    snapshot_id: Optional[int] = None
    study_card_rank: Optional[int] = None
    llm_resolution_score: Optional[int] = None
    p_fail: Optional[Decimal] = None
    catalyst_window_start: Optional[date] = None
    catalyst_window_end: Optional[date] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class BacktestResult:
    """Backtest performance metrics."""
    run_id: int
    k_value: int
    result_id: Optional[int] = None
    precision_at_k: Optional[Decimal] = None
    recall_at_k: Optional[Decimal] = None
    f1_at_k: Optional[Decimal] = None
    created_at: datetime = field(default_factory=datetime.now)
