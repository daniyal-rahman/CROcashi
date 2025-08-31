"""
Gate Proposer LLM Worker

Implements Step 6 from the Study Card Overhaul: proposes 3-5 necessary gates with numeric rules
and computable measurables. Converts MethodCard + ResultsFactsheet into GateCandidate objects.
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict

from ..base_worker import BaseWorker, WorkerResult
from ...models import (
    MethodCard, ResultsFactsheet, Claim, GateCandidate, PocketContextCard
)
from ...validators import GlobalValidator


class GateProposer(BaseWorker):
    """
    Worker for proposing necessary gates with numeric rules and computable measurables.
    
    Implements Step 6 from the Study Card Overhaul: "Convert MethodCard + ResultsFactsheet 
    (+ Pocket Context) into 3-5 necessary gates with falsifiable numeric rules and 
    compute-from-claims measurables."
    """
    
    def __init__(self):
        super().__init__("GateProposer", "1.0.0")
        
        # Gate family definitions for systematic gate generation
        self.gate_families = {
            'G1_signal': {
                'description': 'Primary efficacy signal (ORR, PFS, OS)',
                'required_measurables': ['efficacy_metric', 'statistical_significance'],
                'typical_thresholds': ['ORR >= 15%', 'median_OS >= 12 months', 'p < 0.05']
            },
            'G2_mechanism_delivery': {
                'description': 'Mechanism of action and delivery (vector, dose, exposure)',
                'required_measurables': ['target_engagement', 'dose_response', 'safety_profile'],
                'typical_thresholds': ['target_engagement >= 70%', 'DLT < 20%', 'no_grade4_events']
            },
            'G3_design': {
                'description': 'Study design and methodology quality',
                'required_measurables': ['sample_size', 'study_power', 'bias_control'],
                'typical_thresholds': ['n >= 100', 'power >= 80%', 'blinded_assessment']
            }
        }
        
        # Measurable computation templates
        self.computation_templates = {
            'efficacy_metric': {
                'ORR': 'proportion(positive_response)',
                'median_OS': 'median(survival_values)',
                'median_PFS': 'median(progression_values)',
                'HR': 'hazard_ratio(survival_curves)'
            },
            'statistical_significance': {
                'p_value': 'p_value(primary_endpoint)',
                'confidence_interval': 'ci_width(primary_endpoint)'
            },
            'target_engagement': {
                'biomarker_level': 'median(biomarker_values)',
                'target_binding': 'proportion(target_positive)'
            },
            'safety_profile': {
                'DLT_rate': 'proportion(dose_limiting_toxicity)',
                'grade4_events': 'count(grade4_adverse_events)'
            }
        }
    
    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required data for gate proposal."""
        required_keys = ['method_card', 'results_factsheet']
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs['method_card'], MethodCard):
            return False
            
        if not isinstance(inputs['results_factsheet'], ResultsFactsheet):
            return False
            
        # Optional inputs
        if 'claims' in inputs and not isinstance(inputs['claims'], list):
            return False
            
        if 'pocket_context' in inputs and not isinstance(inputs['pocket_context'], PocketContextCard):
            return False
            
        return True
    
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process inputs to propose necessary gates with numeric rules.
        
        Implements Step 6 from Study Card Overhaul: "Convert MethodCard + ResultsFactsheet 
        (+ Pocket Context) into 3-5 necessary gates with falsifiable numeric rules and 
        compute-from-claims measurables."
        
        Args:
            inputs: Dict containing:
                - method_card: MethodCard - Study methodology and design details
                - results_factsheet: ResultsFactsheet - Normalized results data
                - claims: Optional[List[Claim]] - Supportive and contradicting claims
                - pocket_context: Optional[PocketContextCard] - Disease and intervention context
                
        Returns:
            WorkerResult containing GateCandidate objects
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required method_card or results_factsheet",
                    output={}
                )
            
            method_card = inputs['method_card']
            results_factsheet = inputs['results_factsheet']
            claims = inputs.get('claims', [])
            pocket_context = inputs.get('pocket_context')
            
            # Generate gates for each family
            gate_candidates = []
            
            for family, family_config in self.gate_families.items():
                gate_candidate = self._generate_gate_for_family(
                    family, family_config, method_card, results_factsheet, claims, pocket_context
                )
                if gate_candidate:
                    gate_candidates.append(gate_candidate)
            
            # Validate that we have sufficient gates
            if len(gate_candidates) < 3:
                return WorkerResult(
                    success=False,
                    error_message=f"Insufficient gates generated: {len(gate_candidates)} (minimum 3 required)",
                    output={}
                )
            
            # Validate each gate meets specification requirements
            validation_results = self._validate_gate_candidates(gate_candidates, claims)
            
            return WorkerResult(
                success=True,
                output={
                    'gate_candidates': gate_candidates,
                    'validation_results': validation_results,
                    'total_gates': len(gate_candidates),
                    'families_covered': list(self.gate_families.keys()),
                    'specification_compliance': {
                        'min_gates_met': len(gate_candidates) >= 3,
                        'max_gates_met': len(gate_candidates) <= 5,
                        'numeric_rules_present': all(g.has_numeric_thresholds for g in gate_candidates),
                        'measurables_computable': all(g.measurable_count >= 2 for g in gate_candidates)
                    }
                },
                metadata={
                    'worker': 'GateProposer',
                    'version': '1.0',
                    'step': 'Step 6: Gate Proposer v0 (necessary & falsifiable)',
                    'method_card_id': getattr(method_card, 'id', 'unknown'),
                    'results_factsheet_id': getattr(results_factsheet, 'id', 'unknown')
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                error_message=f"Error proposing gates: {str(e)}",
                output={}
            )
    
    def _generate_gate_for_family(
        self, 
        family: str, 
        family_config: Dict[str, Any],
        method_card: MethodCard,
        results_factsheet: ResultsFactsheet,
        claims: List[Claim],
        pocket_context: Optional[PocketContextCard]
    ) -> Optional[GateCandidate]:
        """Generate a gate candidate for a specific gate family."""
        try:
            # Create gate ID
            gate_id = f"gate_{family}_{len(claims)}"
            
            # Generate proposition based on family
            proposition = self._generate_proposition(family, family_config, method_card)
            
            # Generate decision rule with numeric thresholds
            decision_rule = self._generate_decision_rule(family, family_config, results_factsheet)
            
            # Generate measurables with computations and thresholds
            measurables = self._generate_measurables(family, family_config, results_factsheet, claims)
            
            # Ensure we have at least 2 measurables as required by specification
            if len(measurables) < 2:
                return None
            
            # Generate dependencies
            dependencies = self._generate_dependencies(family, method_card)
            
            # Find counter-claims for this family
            counter_claims = self._find_counter_claims(family, claims)
            
            # Generate FDA next steps
            fda_next = self._generate_fda_next(family, method_card, pocket_context)
            
            # Calculate confidence
            confidence = self._calculate_confidence(family, measurables, method_card)
            
            # Create the gate candidate
            gate_candidate = GateCandidate(
                gate_id=gate_id,
                proposition=proposition,
                decision_rule=decision_rule,
                measurables=measurables,
                dependencies=dependencies,
                gate_family=family,
                counter_claims=counter_claims,
                fda_next=fda_next,
                confidence=confidence,
                priority="high" if family == 'G1_signal' else "medium",
                rationale=f"Gate {family} is necessary for {family_config['description']}",
                notes=[f"Generated from {family} family requirements"]
            )
            
            return gate_candidate
            
        except Exception as e:
            print(f"Error generating gate for family {family}: {e}")
            return None
    
    def _generate_proposition(self, family: str, family_config: Dict[str, Any], method_card: MethodCard) -> str:
        """Generate a necessary condition proposition for the gate."""
        if family == 'G1_signal':
            return f"Primary efficacy signal demonstrates clinical benefit with statistical significance"
        elif family == 'G2_mechanism_delivery':
            return f"Mechanism of action and delivery demonstrate target engagement with acceptable safety"
        elif family == 'G3_design':
            return f"Study design and methodology provide sufficient power and bias control"
        else:
            return f"Gate {family} requirements are met"
    
    def _generate_decision_rule(self, family: str, family_config: Dict[str, Any], results_factsheet: ResultsFactsheet) -> str:
        """Generate a falsifiable decision rule with numeric thresholds."""
        if family == 'G1_signal':
            # Look for primary endpoint results
            primary_results = results_factsheet.get_primary_endpoint_result()
            if primary_results:
                metric = primary_results.get('metric', '')
                if 'orr' in metric.lower():
                    return "ORR >= 15% AND p < 0.05"
                elif 'median_os' in metric.lower():
                    return "median_OS >= 12 months AND p < 0.05"
                else:
                    return "primary_endpoint >= threshold AND p < 0.05"
            return "efficacy_metric >= threshold AND statistical_significance"
        
        elif family == 'G2_mechanism_delivery':
            return "target_engagement >= 70% AND DLT_rate < 20%"
        
        elif family == 'G3_design':
            return "sample_size >= 100 AND power >= 80%"
        
        return "measurable1 >= threshold1 AND measurable2 >= threshold2"
    
    def _generate_measurables(
        self, 
        family: str, 
        family_config: Dict[str, Any],
        results_factsheet: ResultsFactsheet,
        claims: List[Claim]
    ) -> List[Dict[str, Any]]:
        """Generate measurables with computations and thresholds."""
        measurables = []
        
        if family == 'G1_signal':
            # Efficacy metric
            efficacy_measurable = {
                "name": "efficacy_metric",
                "compute": "extract_primary_endpoint(results_factsheet)",
                "threshold": ">= threshold_value",
                "claim_ids": [c.claim_id for c in claims if c.type == 'effect_size']
            }
            measurables.append(efficacy_measurable)
            
            # Statistical significance
            stat_measurable = {
                "name": "statistical_significance",
                "compute": "extract_p_value(results_factsheet, 'primary_endpoint')",
                "threshold": "< 0.05",
                "claim_ids": [c.claim_id for c in claims if c.type == 'effect_size' and c.p_value]
            }
            measurables.append(stat_measurable)
        
        elif family == 'G2_mechanism_delivery':
            # Target engagement
            target_measurable = {
                "name": "target_engagement",
                "compute": "extract_biomarker_data(results_factsheet)",
                "threshold": ">= 70%",
                "claim_ids": [c.claim_id for c in claims if c.type == 'pkpd']
            }
            measurables.append(target_measurable)
            
            # Safety profile
            safety_measurable = {
                "name": "safety_profile",
                "compute": "extract_safety_data(results_factsheet)",
                "threshold": "DLT < 20%",
                "claim_ids": [c.claim_id for c in claims if c.type == 'prevalence']
            }
            measurables.append(safety_measurable)
        
        elif family == 'G3_design':
            # Sample size
            sample_measurable = {
                "name": "sample_size",
                "compute": "extract_enrollment_data(method_card)",
                "threshold": ">= 100",
                "claim_ids": [c.claim_id for c in claims if c.type == 'design_fact']
            }
            measurables.append(sample_measurable)
            
            # Study power
            power_measurable = {
                "name": "study_power",
                "compute": "calculate_power(method_card, results_factsheet)",
                "threshold": ">= 80%",
                "claim_ids": [c.claim_id for c in claims if c.type == 'design_fact']
            }
            measurables.append(power_measurable)
        
        return measurables
    
    def _generate_dependencies(self, family: str, method_card: MethodCard) -> List[str]:
        """Generate dependencies for the gate."""
        dependencies = []
        
        # G1 depends on G3 (design quality)
        if family == 'G1_signal':
            dependencies.append("gate_G3_design")
        
        # G2 depends on G1 (efficacy signal)
        elif family == 'G2_mechanism_delivery':
            dependencies.append("gate_G1_signal")
        
        return dependencies
    
    def _find_counter_claims(self, family: str, claims: List[Claim]) -> List[str]:
        """Find counter-claims for this gate family."""
        counter_claim_ids = []
        
        for claim in claims:
            if claim.stance == 'contradicts' and claim.endpoint == family:
                counter_claim_ids.append(claim.claim_id)
        
        # Limit to top 1-3 as specified
        return counter_claim_ids[:3]
    
    def _generate_fda_next(self, family: str, method_card: MethodCard, pocket_context: Optional[PocketContextCard]) -> str:
        """Generate FDA next steps for the gate."""
        if family == 'G1_signal':
            return "Larger phase 3 study with control arm and longer follow-up"
        elif family == 'G2_mechanism_delivery':
            return "Comprehensive safety monitoring and dose optimization in phase 2b"
        elif family == 'G3_design':
            return "Multi-center study with independent endpoint adjudication"
        else:
            return "Additional studies to address identified gaps"
    
    def _calculate_confidence(self, family: str, measurables: List[Dict[str, Any]], method_card: MethodCard) -> float:
        """Calculate confidence in the gate proposal."""
        base_confidence = 0.5
        
        # Higher confidence for more measurables
        if len(measurables) >= 3:
            base_confidence += 0.2
        elif len(measurables) >= 2:
            base_confidence += 0.1
        
        # Higher confidence for G1 (primary endpoint)
        if family == 'G1_signal':
            base_confidence += 0.1
        
        # Adjust based on method card completeness
        if hasattr(method_card, 'primary_endpoint') and method_card.primary_endpoint:
            base_confidence += 0.1
        
        return min(1.0, base_confidence)
    
    def _validate_gate_candidates(self, gate_candidates: List[GateCandidate], claims: List[Claim]) -> Dict[str, Any]:
        """Validate that gate candidates meet specification requirements."""
        validation_results = {}
        
        for gate in gate_candidates:
            gate_validation = {
                'gate_id': gate.gate_id,
                'proposition_present': bool(gate.proposition),
                'decision_rule_present': bool(gate.decision_rule),
                'measurables_count': gate.measurable_count,
                'min_measurables_met': gate.measurable_count >= 2,
                'numeric_thresholds_present': gate.has_numeric_thresholds,
                'claim_references_valid': self._validate_claim_references(gate, claims),
                'overall_valid': True
            }
            
            # Check overall validity
            gate_validation['overall_valid'] = all([
                gate_validation['proposition_present'],
                gate_validation['decision_rule_present'],
                gate_validation['min_measurables_met'],
                gate_validation['numeric_thresholds_present'],
                gate_validation['claim_references_valid']
            ])
            
            validation_results[gate.gate_id] = gate_validation
        
        return validation_results
    
    def _validate_claim_references(self, gate: GateCandidate, claims: List[Claim]) -> bool:
        """Validate that all claim references in measurables are valid."""
        claim_ids = [c.claim_id for c in claims]
        
        for measurable in gate.measurables:
            measurable_claim_ids = measurable.get('claim_ids', [])
            for claim_id in measurable_claim_ids:
                if claim_id not in claim_ids:
                    return False
        
        return True
