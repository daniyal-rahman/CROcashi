"""
GateSpec Model

Represents validated and normalized gate specifications.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .base import BaseModel, ProvenanceMixin


@dataclass
class GateSpec(BaseModel, ProvenanceMixin):
    """Validated and normalized gate specification."""
    
    gate_id: str = ""
    proposition: str = ""  # Canonical wording of the necessary condition
    decision_rule: str = ""  # Normalized decision rule with explicit thresholds
    
    # Measurables with validated computations
    measurables: List[Dict[str, Any]] = field(default_factory=list)
    
    # Dependencies and relationships
    dependencies: List[str] = field(default_factory=list)  # Other gates/subgates
    gate_family: Optional[str] = None  # G1 signal, G2 mechanism/delivery, G3 design
    
    # Counter-evidence
    counter_claims: List[str] = field(default_factory=list)  # Validated counter-claims
    
    # FDA perspective
    fda_next: Optional[str] = None  # What would increase confidence next study
    
    # Validation metadata
    validation_status: str = "validated"  # validated, rejected, needs_revision
    validation_errors: List[str] = field(default_factory=list)
    validation_notes: List[str] = field(default_factory=list)
    
    # Additional metadata
    rationale: Optional[str] = None  # Why this gate is necessary
    notes: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize provenance fields."""
        ProvenanceMixin.__init__(self)
    
    def validate(self) -> bool:
        """Validate the GateSpec."""
        if not self.gate_id or not self.proposition or not self.decision_rule:
            return False
        if not self.measurables:
            return False
        if self.validation_status not in ["validated", "rejected", "needs_revision"]:
            return False
        return True
    
    def add_measurable(self, name: str, compute: str, threshold: str, 
                       claim_ids: List[str], units: Optional[str] = None,
                       description: Optional[str] = None) -> None:
        """Add a validated measurable for this gate."""
        measurable = {
            "name": name,
            "compute": compute,
            "threshold": threshold,
            "claim_ids": claim_ids,
            "units": units,
            "description": description
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
    
    def add_validation_error(self, error: str) -> None:
        """Add a validation error."""
        if error not in self.validation_errors:
            self.validation_errors.append(error)
    
    def add_validation_note(self, note: str) -> None:
        """Add a validation note."""
        if note not in self.validation_notes:
            self.validation_notes.append(note)
    
    def add_note(self, note: str) -> None:
        """Add a general note."""
        if note not in self.notes:
            self.notes.append(note)
    
    def mark_as_validated(self) -> None:
        """Mark this gate as validated."""
        self.validation_status = "validated"
        self.validation_errors.clear()
    
    def mark_as_rejected(self, reason: str) -> None:
        """Mark this gate as rejected."""
        self.validation_status = "rejected"
        self.add_validation_error(reason)
    
    def mark_as_needs_revision(self, reason: str) -> None:
        """Mark this gate as needing revision."""
        self.validation_status = "needs_revision"
        self.add_validation_note(reason)
    
    @property
    def is_validated(self) -> bool:
        """Check if this gate is validated."""
        return self.validation_status == "validated"
    
    @property
    def is_rejected(self) -> bool:
        """Check if this gate is rejected."""
        return self.validation_status == "rejected"
    
    @property
    def needs_revision(self) -> bool:
        """Check if this gate needs revision."""
        return self.validation_status == "needs_revision"
    
    @property
    def has_numeric_thresholds(self) -> bool:
        """Check if all measurables have numeric thresholds."""
        for measurable in self.measurables:
            threshold = measurable.get("threshold", "")
            if not any(char.isdigit() for char in str(threshold)):
                return False
        return True
    
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
    
    def get_all_claim_ids(self) -> List[str]:
        """Get all claim IDs referenced by this gate."""
        claim_ids = []
        for measurable in self.measurables:
            claim_ids.extend(measurable.get("claim_ids", []))
        claim_ids.extend(self.counter_claims)
        return list(set(claim_ids))  # Remove duplicates
    
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
            "validation_status": self.validation_status,
            "validation_errors": self.validation_errors,
            "validation_notes": self.validation_notes,
            "rationale": self.rationale,
            "notes": self.notes
        })
        return base_dict
