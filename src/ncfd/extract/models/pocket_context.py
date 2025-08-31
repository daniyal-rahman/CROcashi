"""
PocketContextCard Model

Provides zoom-out guardrails and context for study evaluation.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .base import BaseModel, ProvenanceMixin


@dataclass
class PocketContextCard(BaseModel, ProvenanceMixin):
    """Disease and intervention context for study evaluation."""
    
    # Disease context
    disease: str = ""
    disease_stage: Optional[str] = None
    disease_severity: Optional[str] = None
    event_volatility: Optional[str] = None  # High, medium, low
    
    # Intervention context
    intervention_class: str = ""
    mechanism_of_action: Optional[str] = None
    vector_type: Optional[str] = None  # AAV, lentivirus, etc.
    route: Optional[str] = None
    dose_form: Optional[str] = None
    
    # Clinical context
    typical_mcid: Optional[str] = None  # Minimal clinically important difference
    regulator_preferences: List[str] = field(default_factory=list)
    common_pitfalls: List[str] = field(default_factory=list)
    minimal_plausible_effect_size: Optional[str] = None
    
    # Intervention class quirks
    class_quirks: List[str] = field(default_factory=list)  # e.g., "no redose for AAV"
    redose_feasibility: Optional[str] = None
    immunogenicity_concerns: Optional[str] = None
    manufacturing_constraints: Optional[str] = None
    
    # Market and regulatory context
    competitive_landscape: Optional[str] = None
    regulatory_pathway: Optional[str] = None
    orphan_drug_status: Optional[bool] = None
    breakthrough_therapy_designation: Optional[bool] = None
    
    # Evidence standards
    evidence_thresholds: Dict[str, Any] = field(default_factory=dict)
    surrogate_endpoints: List[str] = field(default_factory=list)
    required_safety_data: List[str] = field(default_factory=list)
    
    # Additional context
    population_characteristics: Optional[str] = None
    biomarker_requirements: List[str] = field(default_factory=list)
    companion_diagnostics: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize provenance fields."""
        ProvenanceMixin.__init__(self)
    
    def validate(self) -> bool:
        """Validate the PocketContextCard."""
        if not self.disease or not self.intervention_class:
            return False
        return True
    
    def add_regulator_preference(self, preference: str) -> None:
        """Add a regulator preference."""
        if preference not in self.regulator_preferences:
            self.regulator_preferences.append(preference)
    
    def add_common_pitfall(self, pitfall: str) -> None:
        """Add a common pitfall."""
        if pitfall not in self.common_pitfalls:
            self.common_pitfalls.append(pitfall)
    
    def add_class_quirk(self, quirk: str) -> None:
        """Add an intervention class quirk."""
        if quirk not in self.class_quirks:
            self.class_quirks.append(quirk)
    
    def add_surrogate_endpoint(self, endpoint: str) -> None:
        """Add a surrogate endpoint."""
        if endpoint not in self.surrogate_endpoints:
            self.surrogate_endpoints.append(endpoint)
    
    def add_required_safety_data(self, safety_data: str) -> None:
        """Add required safety data."""
        if safety_data not in self.required_safety_data:
            self.required_safety_data.append(safety_data)
    
    def add_biomarker_requirement(self, biomarker: str) -> None:
        """Add a biomarker requirement."""
        if biomarker not in self.biomarker_requirements:
            self.biomarker_requirements.append(biomarker)
    
    def get_context_summary(self) -> str:
        """Get a summary of the context."""
        summary_parts = [
            f"Disease: {self.disease}",
            f"Intervention: {self.intervention_class}"
        ]
        
        if self.disease_stage:
            summary_parts.append(f"Stage: {self.disease_stage}")
        if self.mechanism_of_action:
            summary_parts.append(f"MOA: {self.mechanism_of_action}")
        if self.typical_mcid:
            summary_parts.append(f"MCID: {self.typical_mcid}")
        
        return "; ".join(summary_parts)
    
    def is_high_risk_intervention(self) -> bool:
        """Check if this is a high-risk intervention."""
        high_risk_indicators = [
            "gene therapy",
            "cell therapy", 
            "oncolytic virus",
            "crispr",
            "gene editing"
        ]
        return any(indicator in self.intervention_class.lower() for indicator in high_risk_indicators)
    
    def requires_special_monitoring(self) -> bool:
        """Check if this intervention requires special monitoring."""
        return (self.is_high_risk_intervention() or 
                "immunogenicity" in str(self.immunogenicity_concerns).lower() or
                "redose" in str(self.redose_feasibility).lower())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with all fields."""
        base_dict = super().to_dict()
        base_dict.update({
            "disease": self.disease,
            "disease_stage": self.disease_stage,
            "disease_severity": self.disease_severity,
            "event_volatility": self.event_volatility,
            "intervention_class": self.intervention_class,
            "mechanism_of_action": self.mechanism_of_action,
            "vector_type": self.vector_type,
            "route": self.route,
            "dose_form": self.dose_form,
            "typical_mcid": self.typical_mcid,
            "regulator_preferences": self.regulator_preferences,
            "common_pitfalls": self.common_pitfalls,
            "minimal_plausible_effect_size": self.minimal_plausible_effect_size,
            "class_quirks": self.class_quirks,
            "redose_feasibility": self.redose_feasibility,
            "immunogenicity_concerns": self.immunogenicity_concerns,
            "manufacturing_constraints": self.manufacturing_constraints,
            "competitive_landscape": self.competitive_landscape,
            "regulatory_pathway": self.regulatory_pathway,
            "orphan_drug_status": self.orphan_drug_status,
            "breakthrough_therapy_designation": self.breakthrough_therapy_designation,
            "evidence_thresholds": self.evidence_thresholds,
            "surrogate_endpoints": self.surrogate_endpoints,
            "required_safety_data": self.required_safety_data,
            "population_characteristics": self.population_characteristics,
            "biomarker_requirements": self.biomarker_requirements,
            "companion_diagnostics": self.companion_diagnostics
        })
        return base_dict
