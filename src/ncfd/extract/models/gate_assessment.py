"""
GateAssessment Model

Represents the assessment results of a gate evaluation.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .base import BaseModel, ProvenanceMixin


@dataclass
class GateAssessment(BaseModel, ProvenanceMixin):
    """Assessment results of a gate evaluation."""
    
    gate_id: str = ""
    status: str = "UNCERTAIN"  # PASS, FAIL, UNCERTAIN
    
    # Assessment details
    p_gate: Optional[float] = None  # Probability if quantified
    rationale: List[str] = field(default_factory=list)  # Sentence list with claim_ids
    
    # Sensitivity analysis
    sensitivity: List[Dict[str, Any]] = field(default_factory=list)  # 1-2 knobs that move it
    
    # Computed values
    computed_values: Dict[str, Any] = field(default_factory=dict)  # Intermediate calculations
    threshold_comparisons: Dict[str, Any] = field(default_factory=dict)  # How values compare to thresholds
    
    # Assessment metadata
    assessment_method: str = "deterministic"  # deterministic, llm_assisted, hybrid
    confidence_in_assessment: float = 0.5  # 0-1 confidence in this assessment
    
    # Additional metadata
    assessment_notes: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize provenance fields and validate status."""
        ProvenanceMixin.__init__(self)
        
        # Ensure status is valid
        if self.status not in ["PASS", "FAIL", "UNCERTAIN"]:
            self.status = "UNCERTAIN"
        
        # Ensure confidence is in valid range
        self.confidence_in_assessment = max(0.0, min(1.0, self.confidence_in_assessment))
    
    def validate(self) -> bool:
        """Validate the GateAssessment."""
        if not self.gate_id or not self.status:
            return False
        if self.p_gate is not None and (self.p_gate < 0.0 or self.p_gate > 1.0):
            return False
        if self.confidence_in_assessment < 0.0 or self.confidence_in_assessment > 1.0:
            return False
        return True
    
    def add_rationale(self, sentence: str) -> None:
        """Add a rationale sentence."""
        if sentence not in self.rationale:
            self.rationale.append(sentence)
    
    def add_sensitivity_knob(self, parameter: str, range_min: float, range_max: float, 
                            impact: str, current_value: Optional[float] = None) -> None:
        """Add a sensitivity analysis knob."""
        knob = {
            "parameter": parameter,
            "range_min": range_min,
            "range_max": range_max,
            "impact": impact,
            "current_value": current_value
        }
        self.sensitivity.append(knob)
    
    def add_computed_value(self, name: str, value: Any, units: Optional[str] = None,
                          description: Optional[str] = None) -> None:
        """Add a computed value."""
        self.computed_values[name] = {
            "value": value,
            "units": units,
            "description": description
        }
    
    def add_threshold_comparison(self, measurable_name: str, computed_value: Any,
                                threshold: str, comparison: str, passed: bool) -> None:
        """Add a threshold comparison result."""
        self.threshold_comparisons[measurable_name] = {
            "computed_value": computed_value,
            "threshold": threshold,
            "comparison": comparison,
            "passed": passed
        }
    
    def add_assessment_note(self, note: str) -> None:
        """Add an assessment note."""
        if note not in self.assessment_notes:
            self.assessment_notes.append(note)
    
    def add_next_step(self, step: str) -> None:
        """Add a next step."""
        if step not in self.next_steps:
            self.next_steps.append(step)
    
    def set_status(self, status: str, rationale: Optional[str] = None) -> None:
        """Set the assessment status."""
        if status in ["PASS", "FAIL", "UNCERTAIN"]:
            self.status = status
            if rationale:
                self.add_rationale(rationale)
    
    def set_probability(self, p_gate: float) -> None:
        """Set the gate probability."""
        if 0.0 <= p_gate <= 1.0:
            self.p_gate = p_gate
    
    @property
    def is_pass(self) -> bool:
        """Check if the gate passed."""
        return self.status == "PASS"
    
    @property
    def is_fail(self) -> bool:
        """Check if the gate failed."""
        return self.status == "FAIL"
    
    @property
    def is_uncertain(self) -> bool:
        """Check if the gate status is uncertain."""
        return self.status == "UNCERTAIN"
    
    @property
    def has_sensitivity_analysis(self) -> bool:
        """Check if sensitivity analysis was performed."""
        return len(self.sensitivity) > 0
    
    @property
    def has_computed_values(self) -> bool:
        """Check if computed values are available."""
        return len(self.computed_values) > 0
    
    def get_sensitivity_summary(self) -> str:
        """Get a summary of sensitivity analysis."""
        if not self.sensitivity:
            return "No sensitivity analysis performed"
        
        summary_parts = []
        for knob in self.sensitivity:
            param = knob["parameter"]
            impact = knob["impact"]
            summary_parts.append(f"{param}: {impact}")
        
        return "; ".join(summary_parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with all fields."""
        base_dict = super().to_dict()
        base_dict.update({
            "gate_id": self.gate_id,
            "status": self.status,
            "p_gate": self.p_gate,
            "rationale": self.rationale,
            "sensitivity": self.sensitivity,
            "computed_values": self.computed_values,
            "threshold_comparisons": self.threshold_comparisons,
            "assessment_method": self.assessment_method,
            "confidence_in_assessment": self.confidence_in_assessment,
            "assessment_notes": self.assessment_notes,
            "next_steps": self.next_steps
        })
        return base_dict
