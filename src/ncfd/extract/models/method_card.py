"""
MethodCard Model

Represents study methodology and design details derived from Methods/Protocol/SAP.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .base import BaseModel, ProvenanceMixin


@dataclass
class MethodCard(BaseModel, ProvenanceMixin):
    """Study methodology and design details."""
    estimand: Optional[Dict[str, Any]] = None
    population_description: Optional[str] = None
    primary_endpoint: Optional[str] = None
    secondary_endpoints: List[str] = field(default_factory=list)
    intercurrent_events_policy: Optional[str] = None
    summary_measure: Optional[str] = None
    alpha_structure: Optional[Dict[str, Any]] = None
    alpha_level: Optional[float] = None
    is_one_sided: Optional[bool] = None
    multiplicity_adjustment: Optional[str] = None
    gatekeeping_hierarchy: List[str] = field(default_factory=list)
    interim_looks: List[Dict[str, Any]] = field(default_factory=list)
    interim_timing: Optional[str] = None
    spending_function: Optional[str] = None
    sample_size_reassessment: Optional[bool] = None
    stop_rules: List[str] = field(default_factory=list)
    gehan_two_stage: Optional[bool] = None
    design_archetype: Optional[str] = None
    analysis_set: Optional[Dict[str, Any]] = None
    stratification_factors: List[str] = field(default_factory=list)
    covariate_adjustment: List[str] = field(default_factory=list)
    missingness_assumption: Optional[str] = None
    missingness_pattern: Optional[str] = None
    imputation_method: Optional[str] = None
    tipping_point_analysis: Optional[bool] = None
    endpoint_ascertainment: Optional[str] = None
    assessment_interval: Optional[str] = None  # e.g., "q6w", "every_6_weeks", "monthly"
    is_blinded: Optional[bool] = None
    adjudication_committee: Optional[str] = None
    protocol_features: List[str] = field(default_factory=list)
    run_in_period: Optional[str] = None
    enrichment_strategy: Optional[str] = None
    crossover_design: Optional[str] = None
    rescue_medication: Optional[str] = None
    assay_thresholds: List[Dict[str, Any]] = field(default_factory=list)
    dose_exposure_rationale: Optional[str] = None
    target_engagement: Optional[str] = None
    pkpd_relationship: Optional[str] = None
    site_geography: Dict[str, Any] = field(default_factory=dict)
    number_of_sites: Optional[int] = None
    regions: List[str] = field(default_factory=list)
    dispersion_flag: Optional[bool] = None
    design_risks: List[str] = field(default_factory=list)
    study_phase: Optional[str] = None
    randomization_ratio: Optional[str] = None
    blinding_level: Optional[str] = None
    treatment_duration: Optional[str] = None
    follow_up_duration: Optional[str] = None
    # Standardize provenance: use span_ids for machine checks, provenance_anchors as UI alias
    span_ids: List[str] = field(default_factory=list)  # Primary provenance field for machine checks
    provenance_anchors: List[str] = field(default_factory=list)  # UI alias, kept for backward compatibility
    warnings: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize provenance fields."""
        ProvenanceMixin.__init__(self)
        
        # Set default input_hash if not provided
        if not self.input_hash:
            import uuid
            self.input_hash = f"{uuid.uuid4().hex[:16]}"
        
        # Standardize provenance: ensure span_ids is populated for machine checks
        if not self.span_ids and self.provenance_anchors:
            self.span_ids = self.provenance_anchors.copy()
        elif not self.provenance_anchors and self.span_ids:
            self.provenance_anchors = self.span_ids.copy()
    
    def validate(self) -> bool:
        """Validate the MethodCard."""
        if not self.primary_endpoint:
            return False
        if self.alpha_level is not None and (self.alpha_level <= 0 or self.alpha_level >= 1):
            return False
        
        # Validate that method scalars carry span_ids for provenance
        if not self.span_ids:
            return False
        
        return True
    
    def add_endpoint(self, endpoint: str, is_primary: bool = False) -> None:
        """Add an endpoint."""
        if is_primary:
            self.primary_endpoint = endpoint
        else:
            if endpoint not in self.secondary_endpoints:
                self.secondary_endpoints.append(endpoint)
    
    def add_interim_look(self, timing: str, alpha_spent: float, 
                         stop_rules: Optional[List[str]] = None) -> None:
        """Add an interim analysis look."""
        look = {
            "timing": timing,
            "alpha_spent": alpha_spent,
            "stop_rules": stop_rules or []
        }
        self.interim_looks.append(look)
    
    def add_assay_threshold(self, assay_type: str, threshold: str, 
                           units: str, rationale: Optional[str] = None) -> None:
        """Add an assay threshold."""
        threshold_info = {
            "assay_type": assay_type,
            "threshold": threshold,
            "units": units,
            "rationale": rationale
        }
        self.assay_thresholds.append(threshold_info)
    
    def add_design_risk(self, risk: str) -> None:
        """Add a design risk."""
        if risk not in self.design_risks:
            self.design_risks.append(risk)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with all fields."""
        base_dict = super().to_dict()
        base_dict.update({
            "estimand": self.estimand,
            "population_description": self.population_description,
            "primary_endpoint": self.primary_endpoint,
            "secondary_endpoints": self.secondary_endpoints,
            "intercurrent_events_policy": self.intercurrent_events_policy,
            "summary_measure": self.summary_measure,
            "alpha_structure": self.alpha_structure,
            "alpha_level": self.alpha_level,
            "is_one_sided": self.is_one_sided,
            "multiplicity_adjustment": self.multiplicity_adjustment,
            "gatekeeping_hierarchy": self.gatekeeping_hierarchy,
            "interim_looks": self.interim_looks,
            "interim_timing": self.interim_timing,
            "spending_function": self.spending_function,
            "sample_size_reassessment": self.sample_size_reassessment,
            "stop_rules": self.stop_rules,
            "gehan_two_stage": self.gehan_two_stage,
            "analysis_set": self.analysis_set,
            "stratification_factors": self.stratification_factors,
            "covariate_adjustment": self.covariate_adjustment,
            "missingness_assumption": self.missingness_assumption,
            "missingness_pattern": self.missingness_pattern,
            "imputation_method": self.imputation_method,
            "tipping_point_analysis": self.tipping_point_analysis,
            "endpoint_ascertainment": self.endpoint_ascertainment,
            "is_blinded": self.is_blinded,
            "adjudication_committee": self.adjudication_committee,
            "protocol_features": self.protocol_features,
            "run_in_period": self.run_in_period,
            "enrichment_strategy": self.enrichment_strategy,
            "crossover_design": self.crossover_design,
            "rescue_medication": self.rescue_medication,
            "assay_thresholds": self.assay_thresholds,
            "dose_exposure_rationale": self.dose_exposure_rationale,
            "target_engagement": self.target_engagement,
            "pkpd_relationship": self.pkpd_relationship,
            "site_geography": self.site_geography,
            "number_of_sites": self.number_of_sites,
            "regions": self.regions,
            "dispersion_flag": self.dispersion_flag,
            "design_risks": self.design_risks,
            "study_phase": self.study_phase,
            "randomization_ratio": self.randomization_ratio,
            "blinding_level": self.blinding_level,
            "treatment_duration": self.treatment_duration,
            "follow_up_duration": self.follow_up_duration
        })
        return base_dict
