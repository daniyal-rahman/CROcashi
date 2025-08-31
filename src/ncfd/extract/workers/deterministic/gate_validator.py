"""
Gate Validator Worker

Rule-based worker for validating gate candidates against the gate rubric.
Promotes GateCandidate → GateSpec with validation and rewriting.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict

from ..base_worker import BaseWorker, WorkerResult
from ...models import GateCandidate, GateSpec, Claim
from ...validators import GlobalValidator


class GateValidator(BaseWorker):
    """
    Rule-based worker for validating gate candidates.
    
    Implements the Post-Gate Validator from the Study Card Overhaul:
    - Enforces the gate rubric
    - Rewrites minor issues or rejects with reasons
    - Promotes GateCandidate → GateSpec
    """
    
    def __init__(self):
        super().__init__("GateValidator", "1.0.0")
        
        # Validation rules
        self.validation_rules = {
            'measurables': {
                'min_count': 2,
                'description': 'Each gate must have at least 2 measurables'
            },
            'thresholds': {
                'required': True,
                'description': 'Every measurable must have a numeric threshold or boolean rule'
            },
            'computations': {
                'required': True,
                'description': 'Computations must be feasible with available claims'
            },
            'counter_claims': {
                'min_count': 1,
                'description': 'Must include at least one counter-claim'
            },
            'dependencies': {
                'explicit': True,
                'description': 'Dependencies must be explicitly enumerated'
            },
            'provenance': {
                'required': True,
                'description': 'All measurables must point to existing claim_ids'
            }
        }
        
        # Vague language patterns to reject
        self.vague_patterns = [
            r'\b(generally|may|might|could|possibly|perhaps)\b',
            r'\b(suggestive|trending|directionally|promising)\b',
            r'\b(robust|strong|adequate|sufficient)\b',
            r'\b(well.?tolerated|acceptable|feasible)\b'
        ]
        
        # Required measurable fields
        self.required_measurable_fields = ['name', 'compute', 'threshold', 'claim_ids']

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required gate candidates."""
        required_keys = ['gate_candidates']
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs['gate_candidates'], list):
            return False
            
        if not inputs['gate_candidates']:
            return False
            
        # Validate that all candidates are GateCandidate objects
        for candidate in inputs['gate_candidates']:
            if not isinstance(candidate, GateCandidate):
                return False
                
        return True

    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process gate candidates to validate and promote to GateSpec.
        
        Args:
            inputs: Dict containing:
                - gate_candidates: List[GateCandidate] - Gate candidates to validate
                - referenced_claims: Optional[List[Claim]] - Claims referenced by candidates
                
        Returns:
            WorkerResult containing validated GateSpec objects and rejections
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required gate_candidates",
                    output={}
                )
            
            gate_candidates = inputs['gate_candidates']
            referenced_claims = inputs.get('referenced_claims', [])
            
            # Validate each candidate
            validated_gates = []
            rejected_gates = []
            
            for candidate in gate_candidates:
                validation_result = self._validate_gate_candidate(candidate, referenced_claims)
                
                if validation_result['is_valid']:
                    # Create GateSpec from validated candidate
                    gate_spec = self._create_gate_spec(candidate, validation_result)
                    validated_gates.append(gate_spec)
                else:
                    # Record rejection with reasons
                    rejected_gates.append({
                        'candidate': candidate,
                        'reasons': validation_result['errors'],
                        'suggestions': validation_result['suggestions']
                    })
            
            return WorkerResult(
                success=True,
                output={
                    'gate_specs': validated_gates,
                    'rejected_gates': rejected_gates,
                    'validation_summary': {
                        'total_candidates': len(gate_candidates),
                        'validated': len(validated_gates),
                        'rejected': len(rejected_gates)
                    }
                },
                metadata={
                    'worker': 'GateValidator',
                    'version': '1.0',
                    'validation_rules_applied': list(self.validation_rules.keys())
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                error_message=f"Error validating gates: {str(e)}",
                output={}
            )

    def _validate_gate_candidate(self, candidate: GateCandidate, referenced_claims: List[Claim]) -> Dict[str, Any]:
        """Validate a single gate candidate against all rules."""
        validation_result = {
            'is_valid': True,
            'errors': [],
            'suggestions': [],
            'warnings': []
        }
        
        # Rule 1: Check measurables count
        if not candidate.measurables or len(candidate.measurables) < self.validation_rules['measurables']['min_count']:
            validation_result['is_valid'] = False
            validation_result['errors'].append(
                f"Gate must have at least {self.validation_rules['measurables']['min_count']} measurables, got {len(candidate.measurables) if candidate.measurables else 0}"
            )
        
        # Rule 2: Validate each measurable
        if candidate.measurables:
            for i, measurable in enumerate(candidate.measurables):
                measurable_validation = self._validate_measurable(measurable, i, referenced_claims)
                if not measurable_validation['is_valid']:
                    validation_result['is_valid'] = False
                    validation_result['errors'].extend(measurable_validation['errors'])
                if measurable_validation['suggestions']:
                    validation_result['suggestions'].extend(measurable_validation['suggestions'])
        
        # Rule 3: Check for vague language
        if self._contains_vague_language(candidate.proposition):
            validation_result['warnings'].append(
                "Gate proposition contains vague language that should be made more specific"
            )
            validation_result['suggestions'].append(
                "Replace vague terms with specific, measurable criteria"
            )
        
        # Rule 4: Validate counter-claims
        if not candidate.counter_claims or len(candidate.counter_claims) < self.validation_rules['counter_claims']['min_count']:
            validation_result['is_valid'] = False
            validation_result['errors'].append(
                f"Gate must include at least {self.validation_rules['counter_claims']['min_count']} counter-claim(s)"
            )
        
        # Rule 5: Check dependencies
        if candidate.dependencies and not self._are_dependencies_explicit(candidate.dependencies):
            validation_result['warnings'].append(
                "Dependencies should be explicitly enumerated and clear"
            )
        
        # Rule 6: Validate provenance
        if not self._validate_provenance(candidate, referenced_claims):
            validation_result['is_valid'] = False
            validation_result['errors'].append(
                "All measurables must point to existing claim_ids with proper provenance"
            )
        
        return validation_result

    def _validate_measurable(self, measurable: Dict[str, Any], index: int, referenced_claims: List[Claim]) -> Dict[str, Any]:
        """Validate a single measurable."""
        validation_result = {
            'is_valid': True,
            'errors': [],
            'suggestions': []
        }
        
        # Check required fields
        for field in self.required_measurable_fields:
            if field not in measurable:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"Measurable[{index}] missing required field: {field}"
                )
        
        # Validate threshold
        if 'threshold' in measurable:
            threshold = measurable['threshold']
            if not self._is_valid_threshold(threshold):
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"Measurable[{index}] has invalid threshold: {threshold}"
                )
        
        # Validate computation
        if 'compute' in measurable:
            compute = measurable['compute']
            if not self._is_valid_computation(compute):
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"Measurable[{index}] has invalid computation: {compute}"
                )
        
        # Validate claim_ids
        if 'claim_ids' in measurable:
            claim_ids = measurable['claim_ids']
            if not self._are_claim_ids_valid(claim_ids, referenced_claims):
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"Measurable[{index}] references invalid or non-existent claim_ids"
                )
        
        return validation_result

    def _is_valid_threshold(self, threshold: Any) -> bool:
        """Check if a threshold is valid."""
        if threshold is None:
            return False
        
        # String thresholds should contain comparison operators
        if isinstance(threshold, str):
            comparison_operators = ['>=', '<=', '>', '<', '=', '==', '!=']
            return any(op in threshold for op in comparison_operators)
        
        # Numeric thresholds are valid
        if isinstance(threshold, (int, float)):
            return True
        
        # Boolean thresholds are valid
        if isinstance(threshold, bool):
            return True
        
        return False

    def _is_valid_computation(self, compute: Any) -> bool:
        """Check if a computation is valid."""
        if compute is None:
            return False
        
        if not isinstance(compute, str):
            return False
        
        # Valid computation patterns
        valid_patterns = [
            r'median\([^)]+\)',
            r'mean\([^)]+\)',
            r'sum\([^)]+\)',
            r'count\([^)]+\)',
            r'proportion\([^)]+\)',
            r'ratio\([^)]+\)',
            r'[a-zA-Z_][a-zA-Z0-9_]*\s*[+\-*/]\s*[a-zA-Z_][a-zA-Z0-9_]*',
            r'[a-zA-Z_][a-zA-Z0-9_]*\s*[<>=!]+\s*[0-9.]+'
        ]
        
        return any(re.match(pattern, compute) for pattern in valid_patterns)

    def _are_claim_ids_valid(self, claim_ids: List[str], referenced_claims: List[Claim]) -> bool:
        """Check if claim_ids reference valid claims."""
        if not claim_ids:
            return False
        
        # Get valid claim IDs from referenced claims
        valid_claim_ids = {claim.claim_id for claim in referenced_claims}
        
        # Check if all referenced claim_ids exist
        return all(claim_id in valid_claim_ids for claim_id in claim_ids)

    def _contains_vague_language(self, proposition: str) -> bool:
        """Check if proposition contains vague language."""
        if not proposition:
            return False
        
        return any(re.search(pattern, proposition, re.IGNORECASE) for pattern in self.vague_patterns)

    def _are_dependencies_explicit(self, dependencies: List[str]) -> bool:
        """Check if dependencies are explicitly enumerated."""
        if not dependencies:
            return True
        
        # Check if dependencies are specific and not vague
        vague_dependency_patterns = [
            r'\b(and|or|but)\b',
            r'\b(generally|usually|typically)\b',
            r'\b(may|might|could)\b'
        ]
        
        for dependency in dependencies:
            if any(re.search(pattern, dependency, re.IGNORECASE) for pattern in vague_dependency_patterns):
                return False
        
        return True

    def _validate_provenance(self, candidate: GateCandidate, referenced_claims: List[Claim]) -> bool:
        """Validate that all measurables have proper provenance."""
        if not candidate.measurables:
            return False
        
        for measurable in candidate.measurables:
            if 'claim_ids' not in measurable or not measurable['claim_ids']:
                return False
            
            # Check if all claim_ids reference existing claims
            if not self._are_claim_ids_valid(measurable['claim_ids'], referenced_claims):
                return False
        
        return True

    def _create_gate_spec(self, candidate: GateCandidate, validation_result: Dict[str, Any]) -> GateSpec:
        """Create a GateSpec from a validated GateCandidate."""
        # Import GateSpec here to avoid circular imports
        from ...models.gate_spec import GateSpec
        
        # Create the gate spec with validated data
        gate_spec = GateSpec(
            gate_id=candidate.gate_id,
            proposition=candidate.proposition,
            decision_rule=candidate.decision_rule,
            measurables=candidate.measurables,
            dependencies=candidate.dependencies or [],
            counter_claims=candidate.counter_claims or [],
            fda_next=candidate.fda_next,
            confidence=candidate.confidence,
            notes=candidate.notes or ""
        )
        
        # Add validation metadata
        if hasattr(gate_spec, 'validation_metadata'):
            gate_spec.validation_metadata = {
                'validated_by': self.name,
                'validation_version': self.version,
                'validation_warnings': validation_result.get('warnings', []),
                'validation_suggestions': validation_result.get('suggestions', [])
            }
        
        return gate_spec
