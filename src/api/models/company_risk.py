"""
Pydantic models for company risk API responses.
"""
from datetime import date, datetime
from typing import Dict, List, Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field


class RiskCategory(str):
    """Risk category enum."""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ComponentDetails(BaseModel):
    """Details for a risk score component."""
    score: float = Field(..., description="Component score")
    weight: int = Field(..., description="Component weight (max points)")
    details: Dict[str, Any] = Field(..., description="Component-specific details")


class RiskScoreComponents(BaseModel):
    """Breakdown of risk score components."""
    failure_rate: ComponentDetails
    recent_failures: ComponentDetails
    pipeline_stagnation: ComponentDetails
    warning_signals: ComponentDetails


class CompanyRiskProfile(BaseModel):
    """Company risk profile response."""
    company_id: str = Field(..., description="Company UUID")
    company_name: Optional[str] = Field(None, description="Company name")
    risk_score: float = Field(..., ge=0, le=100, description="Risk score (0-100)")
    risk_category: str = Field(..., description="Risk category (LOW, MODERATE, HIGH, CRITICAL)")
    components: RiskScoreComponents = Field(..., description="Risk score component breakdown")
    calculated_at: str = Field(..., description="ISO timestamp of calculation")


class CompanyMetrics(BaseModel):
    """Company metrics response."""
    company_id: str
    company_name: Optional[str] = None
    total_trials: int = Field(..., ge=0)
    active_trials: int = Field(..., ge=0)
    terminated_count: int = Field(..., ge=0)
    success_rate_phase_1: Optional[float] = Field(None, ge=0, le=1)
    success_rate_phase_2: Optional[float] = Field(None, ge=0, le=1)
    success_rate_phase_3: Optional[float] = Field(None, ge=0, le=1)
    pipeline_velocity: float = Field(..., ge=0)
    days_since_last_update: Optional[int] = Field(None, ge=0)
    failure_clustering: Dict[str, Any] = Field(default_factory=dict)
    # New metrics from inferred relationships
    publications_count: int = Field(default=0, ge=0, description="Publications mentioning this company")
    publications_with_trials: int = Field(default=0, ge=0, description="Publications about company's trials")
    publications_with_drugs: int = Field(default=0, ge=0, description="Publications mentioning company's drugs")
    filings_with_drugs: int = Field(default=0, ge=0, description="SEC filings mentioning company's drugs")
    total_drugs: int = Field(default=0, ge=0, description="Total drugs in company pipeline")
    calculated_at: str


class TimelineEvent(BaseModel):
    """Timeline event response."""
    event_id: str
    event_type: str
    event_date: str
    event_significance: str
    entities_involved: List[str]
    event_data: Optional[Dict[str, Any]] = None
    source_id: Optional[str] = None
    confidence_score: Optional[float] = None


class CompanyTimelineResponse(BaseModel):
    """Company timeline response."""
    company_id: str
    events: List[TimelineEvent]
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total_events: int


class WarningSignal(BaseModel):
    """Warning signal."""
    type: str
    event_type: Optional[str] = None
    event_date: Optional[str] = None
    severity: str
    cluster_size: Optional[int] = None
    period_days: Optional[int] = None


class CompanySearchResult(BaseModel):
    """Company search result."""
    company_id: str
    company_name: str
    risk_score: float
    risk_category: str
    total_trials: int
    active_trials: int
    terminated_count: int


class CompanySearchResponse(BaseModel):
    """Company search response."""
    companies: List[CompanySearchResult]
    total: int
    limit: int
    offset: int

