"""
GateCandidate Model

Represents initial gate proposals before validation and assessment.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .base import BaseModel, ProvenanceMixin


@dataclass
class GateCandidate(BaseModel, ProvenanceMixin):
    """Initial gate proposal with basic structure."""
    
    gate_id: str = ""
    proposition: str = ""  # Necessary condition in plain English
    decision_rule: str = ""  # Falsifiable; numeric thresholds or crisp boolean
    
    # Measurables that can be computed from claims
    measurables: List[Dict[str, Any]] = field(default_factory=list)
    
    # Dependencies and relationships
    dependencies: List[str] = field(default_factory=list)  # Other gates/subgates
    gate_family: Optional[str] = None  # G1 signal, G2 mechanism/delivery, G3 design
    
    # Counter-evidence
    counter_claims: List[str] = field(default_factory=list)  # Top 1-3 contradicting claims
    
    # FDA perspective
    fda_next: Optional[str] = None  # What would increase confidence next study
    
    # Quality metrics
    confidence: float = 0.5  # 0-1 confidence in this gate
    priority: str = "medium"  # high, medium, low
    
    # Additional metadata
    rationale: Optional[str] = None  # Why this gate is necessary
    notes: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize provenance fields and validate confidence."""
        ProvenanceMixin.__init__(self)
        self.confidence = max(0.0, min(1.0, self.confidence))
    
    def validate(self) -> bool:
        """Validate the GateCandidate."""
        if not self.gate_id or not self.proposition or not self.decision_rule:
            return False
        if not self.measurables:
            return False
        if self.confidence < 0.0 or self.confidence > 1.0:
            return False
        if self.priority not in ["high", "medium", "low"]:
            return False
        return True
    
    def add_measurable(self, name: str, compute: str, threshold: str, 
                       claim_ids: Optional[List[str]] = None) -> None:
        """Add a measurable for this gate."""
        measurable = {
            "name": name,
            "compute": compute,
            "threshold": threshold,
            "claim_ids": claim_ids or []
        }
        self.measurables.append(measurable)
    
    def add_dependency(self, gate_id: str) -> None:
        """Add a dependency on another gate."""
        if gate_id not in self.dependencies:
            self.dependencies.append(gate_id)
    
    def add_counter_claim(self, claim_id: str) -> None:
        """Add a counter-claim."""
        if claim_id not in self.counter_claims:
            self.counter_claims.append(claim_id)
    
    def add_note(self, note: str) -> None:
        """Add a note."""
        if note not in self.notes:
            self.notes.append(note)
    
    @property
    def has_numeric_thresholds(self) -> bool:
        """Check if all measurables have numeric thresholds."""
        for measurable in self.measurables:
            threshold = measurable.get("threshold", "")
            if not any(char.isdigit() for char in str(threshold)):
                return False
        return True
    
    @property
    def is_high_priority(self) -> bool:
        """Check if this gate is high priority."""
        return self.priority == "high"
    
    @property
    def measurable_count(self) -> int:
        """Get the number of measurables."""
        return len(self.measurables)
    
    def get_measurable_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a measurable by name."""
        for measurable in self.measurables:
            if measurable.get("name") == name:
                return measurable
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with all fields."""
        base_dict = super().to_dict()
        base_dict.update({
            "gate_id": self.gate_id,
            "proposition": self.proposition,
            "decision_rule": self.decision_rule,
            "measurables": self.measurables,
            "dependencies": self.dependencies,
            "gate_family": self.gate_family,
            "counter_claims": self.counter_claims,
            "fda_next": self.fda_next,
            "confidence": self.confidence,
            "priority": self.priority,
            "rationale": self.rationale,
            "notes": self.notes
        })
        return base_dict
