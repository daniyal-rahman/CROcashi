"""
DecisionRecord Model

Represents the final decision record combining all gate assessments.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .base import BaseModel, ProvenanceMixin


@dataclass
class DecisionRecord(BaseModel, ProvenanceMixin):
    """Final decision record combining all gate assessments."""
    
    trial_id: str = ""
    gates: List[Dict[str, Any]] = field(default_factory=list)  # Gate assessments with statuses/probs
    
    # Decision logic
    combination_rule: str = "AND"  # AND, OR, custom
    posterior_success: Optional[float] = None  # Overall success probability if quantified
    decision: str = "UNCERTAIN"  # APPROVE, REJECT, UNCERTAIN, NEEDS_MORE_DATA
    
    # Coverage gaps
    coverage_gaps: List[Dict[str, Any]] = field(default_factory=list)  # Missing evidence that would be decision-moving
    
    # Links and references
    links: Dict[str, str] = field(default_factory=dict)  # Links to memo, plots, etc.
    
    # Decision metadata
    decision_rationale: List[str] = field(default_factory=list)  # Overall decision rationale
    risk_factors: List[str] = field(default_factory=list)  # Key risk factors
    mitigation_strategies: List[str] = field(default_factory=list)  # Risk mitigation strategies
    
    # Additional metadata
    decision_date: Optional[str] = None
    decision_maker: Optional[str] = None
    review_committee: Optional[str] = None
    
    def __post_init__(self):
        """Initialize provenance fields and validate decision."""
        ProvenanceMixin.__init__(self)
        
        # Ensure decision is valid
        valid_decisions = ["APPROVE", "REJECT", "UNCERTAIN", "NEEDS_MORE_DATA"]
        if self.decision not in valid_decisions:
            self.decision = "UNCERTAIN"
    
    def validate(self) -> bool:
        """Validate the DecisionRecord."""
        if not self.trial_id:
            return False
        if self.posterior_success is not None and (self.posterior_success < 0.0 or self.posterior_success > 1.0):
            return False
        if self.combination_rule not in ["AND", "OR", "custom"]:
            return False
        return True
    
    def add_gate_assessment(self, gate_id: str, status: str, p_gate: Optional[float] = None,
                           rationale: Optional[str] = None) -> None:
        """Add a gate assessment."""
        gate_assessment = {
            "gate_id": gate_id,
            "status": status,
            "p_gate": p_gate,
            "rationale": rationale or ""
        }
        self.gates.append(gate_assessment)
        
        # Automatically update decision based on gate statuses
        self._update_decision_from_gates()
    
    def add_coverage_gap(self, gap_description: str, impact: str, 
                         evidence_type: str, priority: str = "medium") -> None:
        """Add a coverage gap."""
        gap = {
            "description": gap_description,
            "impact": impact,
            "evidence_type": evidence_type,
            "priority": priority
        }
        self.coverage_gaps.append(gap)
    
    def add_link(self, link_type: str, url: str) -> None:
        """Add a link."""
        self.links[link_type] = url
    
    def add_decision_rationale(self, rationale: str) -> None:
        """Add decision rationale."""
        if rationale not in self.decision_rationale:
            self.decision_rationale.append(rationale)
    
    def add_risk_factor(self, risk: str) -> None:
        """Add a risk factor."""
        if risk not in self.risk_factors:
            self.risk_factors.append(risk)
    
    def add_mitigation_strategy(self, strategy: str) -> None:
        """Add a risk mitigation strategy."""
        if strategy not in self.mitigation_strategies:
            self.mitigation_strategies.append(strategy)
    
    def set_decision(self, decision: str, rationale: Optional[str] = None) -> None:
        """Set the decision."""
        valid_decisions = ["APPROVE", "REJECT", "UNCERTAIN", "NEEDS_MORE_DATA"]
        if decision in valid_decisions:
            self.decision = decision
            if rationale:
                self.add_decision_rationale(rationale)
    
    def set_posterior_success(self, probability: float) -> None:
        """Set the posterior success probability."""
        if 0.0 <= probability <= 1.0:
            self.posterior_success = probability
    
    def calculate_overall_success(self) -> Optional[float]:
        """Calculate overall success probability based on combination rule."""
        if not self.gates:
            return None
        
        if self.combination_rule == "AND":
            # All gates must pass
            probabilities = [gate.get("p_gate", 0.0) for gate in self.gates if gate.get("p_gate") is not None]
            if probabilities:
                return min(probabilities) if probabilities else None
        
        elif self.combination_rule == "OR":
            # At least one gate must pass
            probabilities = [gate.get("p_gate", 0.0) for gate in self.gates if gate.get("p_gate") is not None]
            if probabilities:
                # P(A or B) = P(A) + P(B) - P(A and B)
                # For independent events, P(A and B) = P(A) * P(B)
                if len(probabilities) == 1:
                    return probabilities[0]
                elif len(probabilities) == 2:
                    p1, p2 = probabilities
                    return p1 + p2 - (p1 * p2)
                else:
                    # For more than 2, use inclusion-exclusion principle approximation
                    return max(probabilities)
        
        return None
    
    def _update_decision_from_gates(self) -> None:
        """Automatically update decision based on gate statuses."""
        if not self.gates:
            self.decision = "UNCERTAIN"
            return
        
        # Check if any gates failed
        if self.failed_gates > 0:
            self.decision = "REJECT"
            return
        
        # Check if all gates passed
        if self.passed_gates == self.gate_count:
            self.decision = "APPROVE"
            return
        
        # Check if there are uncertain gates
        if self.uncertain_gates > 0:
            self.decision = "UNCERTAIN"
            return
        
        # Default to uncertain if no clear pattern
        self.decision = "UNCERTAIN"
    
    @property
    def gate_count(self) -> int:
        """Get the number of gates."""
        return len(self.gates)
    
    @property
    def passed_gates(self) -> int:
        """Get the number of passed gates."""
        return sum(1 for gate in self.gates if gate.get("status") == "PASS")
    
    @property
    def failed_gates(self) -> int:
        """Get the number of failed gates."""
        return sum(1 for gate in self.gates if gate.get("status") == "FAIL")
    
    @property
    def uncertain_gates(self) -> int:
        """Get the number of uncertain gates."""
        return sum(1 for gate in self.gates if gate.get("status") == "UNCERTAIN")
    
    @property
    def coverage_gap_count(self) -> int:
        """Get the number of coverage gaps."""
        return len(self.coverage_gaps)
    
    def get_gate_status_summary(self) -> Dict[str, int]:
        """Get a summary of gate statuses."""
        return {
            "total": self.gate_count,
            "passed": self.passed_gates,
            "failed": self.failed_gates,
            "uncertain": self.uncertain_gates
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with all fields."""
        base_dict = super().to_dict()
        base_dict.update({
            "trial_id": self.trial_id,
            "gates": self.gates,
            "combination_rule": self.combination_rule,
            "posterior_success": self.posterior_success,
            "decision": self.decision,
            "coverage_gaps": self.coverage_gaps,
            "links": self.links,
            "decision_rationale": self.decision_rationale,
            "risk_factors": self.risk_factors,
            "mitigation_strategies": self.mitigation_strategies,
            "decision_date": self.decision_date,
            "decision_maker": self.decision_maker,
            "review_committee": self.review_committee
        })
        return base_dict
