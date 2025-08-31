"""
Claim Model

Represents atomic, testable claims with evidence and metadata.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from .base import BaseModel, ProvenanceMixin


@dataclass
class Claim(BaseModel, ProvenanceMixin):
    """Atomic, testable claim with evidence and metadata."""
    
    claim_id: str = ""
    doc_id: str = ""
    span_ids: List[str] = field(default_factory=list)  # Evidence spans supporting this claim
    
    # Claim classification
    type: str = ""  # design_fact, effect_size, prevalence, assay_cutoff, pkpd, operational, limitation
    proposition: str = ""  # Plain English description
    stance: str = ""  # supports, contradicts, neutral
    
    # Value and statistics
    value: Optional[Union[float, str]] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    p_value: Optional[float] = None
    units: Optional[str] = None
    timepoint: Optional[str] = None
    
    # Analysis set and population
    analysis_set: Optional[str] = None  # ITT, mITT, PP
    n_events: Optional[int] = None
    denominator: Optional[int] = None
    population: Optional[str] = None  # Key inclusions/exclusions summary
    
    # Intervention details
    intervention: Optional[str] = None  # Vector/route/dose
    intervention_normalized: Optional[str] = None  # Normalized intervention description
    
    # Quality metrics
    quality_score: float = 0.5  # 0.0-1.0
    applicability_score: float = 0.5  # 0.0-1.0
    
    # Additional metadata
    endpoint: Optional[str] = None
    arm: Optional[str] = None
    phase: Optional[str] = None
    is_primary: bool = False
    is_posthoc: bool = False
    is_subgroup: bool = False
    
    def __post_init__(self):
        """Initialize provenance fields and validate scores."""
        # Initialize ProvenanceMixin without overwriting our span_ids
        ProvenanceMixin.__init__(self)
        
        # Ensure scores are in valid range
        self.quality_score = max(0.0, min(1.0, self.quality_score))
        self.applicability_score = max(0.0, min(1.0, self.applicability_score))
        
        # Set provenance_span_ids to match our span_ids for lineage tracking
        if self.span_ids:
            self.provenance_span_ids = self.span_ids.copy()
    
    def validate(self) -> bool:
        """Validate the Claim."""
        if not self.claim_id or not self.doc_id or not self.type or not self.proposition:
            return False
        if not self.span_ids:
            return False
        if self.type not in ["design_fact", "effect_size", "prevalence", "assay_cutoff", "pkpd", "operational", "limitation"]:
            return False
        if self.stance not in ["supports", "contradicts", "neutral"]:
            return False
        return True
    
    @property
    def has_numeric_value(self) -> bool:
        """Check if the claim has a numeric value."""
        return self.value is not None and isinstance(self.value, (int, float))
    
    @property
    def has_confidence_interval(self) -> bool:
        """Check if the claim has a confidence interval."""
        return self.ci_lower is not None and self.ci_upper is not None
    
    @property
    def is_statistically_significant(self) -> bool:
        """Check if the claim is statistically significant."""
        return self.p_value is not None and self.p_value < 0.05
    
    @property
    def composite_score(self) -> float:
        """Calculate composite quality score."""
        return (self.quality_score + self.applicability_score) / 2
    
    def add_span(self, span_id: str) -> None:
        """Add an evidence span."""
        if span_id not in self.span_ids:
            self.span_ids.append(span_id)
    
    def remove_span(self, span_id: str) -> None:
        """Remove an evidence span."""
        if span_id in self.span_ids:
            self.span_ids.remove(span_id)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with all fields."""
        base_dict = super().to_dict()
        base_dict.update({
            "claim_id": self.claim_id,
            "doc_id": self.doc_id,
            "span_ids": self.span_ids,
            "type": self.type,
            "proposition": self.proposition,
            "stance": self.stance,
            "value": self.value,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "p_value": self.p_value,
            "units": self.units,
            "timepoint": self.timepoint,
            "analysis_set": self.analysis_set,
            "n_events": self.n_events,
            "denominator": self.denominator,
            "population": self.population,
            "intervention": self.intervention,
            "intervention_normalized": self.intervention_normalized,
            "quality_score": self.quality_score,
            "applicability_score": self.applicability_score,
            "endpoint": self.endpoint,
            "arm": self.arm,
            "phase": self.phase,
            "is_primary": self.is_primary,
            "is_posthoc": self.is_posthoc,
            "is_subgroup": self.is_subgroup
        })
        return base_dict
