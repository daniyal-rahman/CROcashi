"""
Comprehensive data types for ClinicalTrials.gov data extraction.

This module provides enhanced data structures for extracting and tracking
detailed trial information from the CT.gov API v2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Set
from enum import Enum


class TrialPhase(Enum):
    """Trial phase enumeration."""
    PHASE1 = "PHASE1"
    PHASE2 = "PHASE2"
    PHASE3 = "PHASE3"
    PHASE2_PHASE3 = "PHASE2_PHASE3"
    PHASE4 = "PHASE4"
    EARLY_PHASE1 = "EARLY_PHASE1"
    PHASE1_PHASE2 = "PHASE1_PHASE2"
    PHASE3_PHASE4 = "PHASE3_PHASE4"


class TrialStatus(Enum):
    """Trial status enumeration."""
    ACTIVE_NOT_RECRUITING = "ACTIVE_NOT_RECRUITING"
    COMPLETED = "COMPLETED"
    ENROLLING_BY_INVITATION = "ENROLLING_BY_INVITATION"
    NOT_YET_RECRUITING = "NOT_YET_RECRUITING"
    RECRUITING = "RECRUITING"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    WITHDRAWN = "WITHDRAWN"
    UNKNOWN = "UNKNOWN"


class InterventionType(Enum):
    """Intervention type enumeration."""
    DRUG = "DRUG"
    BIOLOGICAL = "BIOLOGICAL"
    DEVICE = "DEVICE"
    PROCEDURE = "PROCEDURE"
    RADIATION = "RADIATION"
    BEHAVIORAL = "BEHAVIORAL"
    GENETIC = "GENETIC"
    DIETARY_SUPPLEMENT = "DIETARY_SUPPLEMENT"
    COMBINATION_PRODUCT = "COMBINATION_PRODUCT"
    DIAGNOSTIC_TEST = "DIAGNOSTIC_TEST"
    OTHER = "OTHER"


class StudyType(Enum):
    """Study type enumeration."""
    INTERVENTIONAL = "INTERVENTIONAL"
    OBSERVATIONAL = "OBSERVATIONAL"
    EXPANDED_ACCESS = "EXPANDED_ACCESS"


@dataclass
class SponsorInfo:
    """Detailed sponsor information."""
    lead_sponsor_name: Optional[str] = None
    lead_sponsor_cik: Optional[str] = None
    lead_sponsor_lei: Optional[str] = None
    lead_sponsor_country: Optional[str] = None
    collaborators: List[str] = field(default_factory=list)
    responsible_party_name: Optional[str] = None
    responsible_party_type: Optional[str] = None
    agency_class: Optional[str] = None


@dataclass
class TrialDesign:
    """Trial design information."""
    allocation: Optional[str] = None  # RANDOMIZED, NON_RANDOMIZED
    masking: Optional[str] = None    # NONE, SINGLE, DOUBLE, TRIPLE, QUADRUPLE
    masking_description: Optional[str] = None
    primary_purpose: Optional[str] = None  # TREATMENT, PREVENTION, DIAGNOSTIC, SUPPORTIVE_CARE
    intervention_model: Optional[str] = None  # PARALLEL, CROSSOVER, FACTORIAL, SEQUENTIAL
    time_perspective: Optional[str] = None
    observational_model: Optional[str] = None


@dataclass
class Intervention:
    """Intervention details."""
    name: str
    type: InterventionType
    description: Optional[str] = None
    arm_labels: List[str] = field(default_factory=list)
    other_names: List[str] = field(default_factory=list)
    drug_codes: List[str] = field(default_factory=list)  # INN, internal codes, etc.


@dataclass
class Condition:
    """Trial condition/indication."""
    name: str
    mesh_terms: List[str] = field(default_factory=list)
    synonyms: List[str] = field(default_factory=list)


@dataclass
class Outcome:
    """Trial outcome definition."""
    measure: str
    description: Optional[str] = None
    time_frame: Optional[str] = None
    type: str = "PRIMARY"  # PRIMARY, SECONDARY, OTHER
    unit_of_measure: Optional[str] = None
    safety_issue: bool = False


@dataclass
class EnrollmentInfo:
    """Trial enrollment information."""
    count: Optional[int] = None
    type: Optional[str] = None  # ACTUAL, ESTIMATED
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    age_unit: Optional[str] = None
    sex: Optional[str] = None  # ALL, MALE, FEMALE
    healthy_volunteers: Optional[bool] = None


@dataclass
class StatisticalAnalysis:
    """Statistical analysis information."""
    analysis_plan: Optional[str] = None
    statistical_method: Optional[str] = None
    alpha_level: Optional[float] = None
    power: Optional[float] = None
    sample_size_calculation: Optional[str] = None
    interim_analyses: Optional[str] = None
    multiplicity_adjustment: Optional[str] = None


@dataclass
class Location:
    """Trial location information."""
    facility_name: str
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    zip_code: Optional[str] = None
    status: Optional[str] = None  # RECRUITING, NOT_RECRUITING, etc.


@dataclass
class ComprehensiveTrialFields:
    """Comprehensive trial information extracted from CT.gov."""
    # Basic identification
    nct_id: str
    brief_title: Optional[str] = None
    official_title: Optional[str] = None
    acronym: Optional[str] = None
    
    # Sponsor and organization
    sponsor_info: SponsorInfo = field(default_factory=SponsorInfo)
    
    # Trial design
    study_type: StudyType = field(default_factory=StudyType)
    phase: Optional[TrialPhase] = None
    trial_design: TrialDesign = field(default_factory=TrialDesign)
    
    # Interventions and conditions
    interventions: List[Intervention] = field(default_factory=list)
    conditions: List[Condition] = field(default_factory=list)
    
    # Outcomes and endpoints
    outcomes: List[Outcome] = field(default_factory=list)
    primary_endpoint_text: Optional[str] = None
    sample_size: Optional[int] = None
    analysis_plan_text: Optional[str] = None
    
    # Enrollment and population
    enrollment_info: EnrollmentInfo = field(default_factory=EnrollmentInfo)
    eligibility_criteria: Optional[str] = None
    
    # Statistical analysis
    statistical_analysis: StatisticalAnalysis = field(default_factory=StatisticalAnalysis)
    
    # Status and dates
    status: Optional[TrialStatus] = None
    first_posted_date: Optional[date] = None
    last_update_posted_date: Optional[date] = None
    study_start_date: Optional[date] = None
    primary_completion_date: Optional[date] = None
    study_completion_date: Optional[date] = None
    
    # Locations
    locations: List[Location] = field(default_factory=list)
    
    # Additional metadata
    keywords: List[str] = field(default_factory=list)
    mesh_terms: List[str] = field(default_factory=list)
    study_documents: List[str] = field(default_factory=list)
    
    # Raw data for change detection
    raw_jsonb: Optional[Dict[str, Any]] = None
    extracted_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Change:
    """Represents a change detected between trial versions."""
    field_name: str
    old_value: Any
    new_value: Any
    change_type: str  # ADDED, REMOVED, MODIFIED
    significance: str  # HIGH, MEDIUM, LOW
    description: str
    detected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TrialChangeSummary:
    """Summary of changes detected for a trial."""
    nct_id: str
    version_from: str
    version_to: str
    changes: List[Change] = field(default_factory=list)
    significant_changes: List[Change] = field(default_factory=list)
    change_count: int = 0
    significant_change_count: int = 0
    detected_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Calculate change counts after initialization."""
        self.change_count = len(self.changes)
        self.significant_changes = [c for c in self.changes if c.significance in ["HIGH", "MEDIUM"]]
        self.significant_change_count = len(self.significant_changes)


@dataclass
class IngestionResult:
    """Result of a CT.gov ingestion operation."""
    success: bool
    trials_processed: int = 0
    trials_updated: int = 0
    trials_new: int = 0
    changes_detected: int = 0
    significant_changes: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    processing_time_seconds: float = 0.0
    run_id: Optional[str] = None
    completed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DataQualityMetrics:
    """Data quality metrics for ingested trials."""
    total_trials: int = 0
    complete_trials: int = 0
    incomplete_trials: int = 0
    missing_sponsor: int = 0
    missing_phase: int = 0
    missing_endpoints: int = 0
    missing_enrollment: int = 0
    quality_score: float = 0.0
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Calculate quality score after initialization."""
        if self.total_trials > 0:
            self.quality_score = self.complete_trials / self.total_trials
