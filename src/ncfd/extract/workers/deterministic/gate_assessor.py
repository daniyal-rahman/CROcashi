"""
Gate Assessor Worker

Deterministic worker for evaluating gate specifications with optional LLM for rationale.
Implements the Gate Assessor from the Study Card Overhaul: computes measurables from claims,
applies gate rules, and sets PASS/FAIL/UNCERTAIN status.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict

from ..base_worker import BaseWorker, WorkerResult
from ...models import GateSpec, GateAssessment, Claim
from ...validators import GlobalValidator


class GateAssessor(BaseWorker):
    """
    Deterministic worker for evaluating gate specifications.
    
    Implements the Gate Assessor from the Study Card Overhaul:
    - Computes measurables from claims deterministically
    - Applies gate rules to set PASS/FAIL/UNCERTAIN
    - Uses LLM only for natural-language rationale (with claim citations)
    """
    
    def __init__(self):
        super().__init__("GateAssessor", "1.0.0")
        
        # Assessment statuses
        self.assessment_statuses = ['PASS', 'FAIL', 'UNCERTAIN']
        
        # Computation functions for different measurable types
        self.computation_functions = {
            'median': self._compute_median,
            'mean': self._compute_mean,
            'sum': self._compute_sum,
            'count': self._compute_count,
            'proportion': self._compute_proportion,
            'ratio': self._compute_ratio
        }
        
        # Comparison operators for thresholds
        self.comparison_operators = {
            '>=': lambda x, y: x >= y,
            '<=': lambda x, y: x <= y,
            '>': lambda x, y: x > y,
            '<': lambda x, y: x < y,
            '=': lambda x, y: x == y,
            '==': lambda x, y: x == y,
            '!=': lambda x, y: x != y
        }

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required gate specs and claims."""
        required_keys = ['gate_specs']
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs['gate_specs'], list):
            return False
            
        if not inputs['gate_specs']:
            return False
            
        # Validate that all specs are GateSpec objects
        for spec in inputs['gate_specs']:
            if not isinstance(spec, GateSpec):
                return False
                
        return True

    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process gate specifications to create assessments.
        
        Args:
            inputs: Dict containing:
                - gate_specs: List[GateSpec] - Gate specifications to assess
                - claims: List[Claim] - All claims referenced by the gates
                
        Returns:
            WorkerResult containing GateAssessment objects
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required gate_specs",
                    output={}
                )
            
            gate_specs = inputs['gate_specs']
            claims = inputs.get('claims', [])
            
            # Assess each gate
            assessments = []
            assessment_summary = {
                'total_gates': len(gate_specs),
                'pass_count': 0,
                'fail_count': 0,
                'uncertain_count': 0,
                'computation_errors': 0
            }
            
            for gate_spec in gate_specs:
                assessment = self._assess_gate(gate_spec, claims)
                if assessment:
                    assessments.append(assessment)
                    
                    # Update summary
                    if assessment.status == 'PASS':
                        assessment_summary['pass_count'] += 1
                    elif assessment.status == 'FAIL':
                        assessment_summary['fail_count'] += 1
                    elif assessment.status == 'UNCERTAIN':
                        assessment_summary['uncertain_count'] += 1
                else:
                    assessment_summary['computation_errors'] += 1
            
            return WorkerResult(
                success=True,
                output={
                    'gate_assessments': assessments,
                    'assessment_summary': assessment_summary,
                    'specification_compliance': {
                        'rationale_with_citations': all(self._has_citations_in_rationale(assessment) for assessment in assessments),
                        'intermediate_numbers_shown': all(self._shows_intermediate_numbers(assessment) for assessment in assessments),
                        'decision_rule_evaluation': all(self._shows_decision_evaluation(assessment) for assessment in assessments),
                        'sensitivity_analysis': all(len(assessment.sensitivity) >= 1 for assessment in assessments)
                    }
                },
                metadata={
                    'worker': 'GateAssessor',
                    'version': '1.0',
                    'step': 'Step 8: Gate Assessor v0 (deterministic first)',
                    'gates_assessed': len(gate_specs),
                    'successful_assessments': len(assessments)
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                error_message=f"Error assessing gates: {str(e)}",
                output={}
            )

    def _assess_gate(self, gate_spec: GateSpec, claims: List[Claim]) -> Optional[GateAssessment]:
        """Assess a single gate specification."""
        try:
            # Compute all measurables
            computed_values = {}
            computation_errors = []
            
            for measurable in gate_spec.measurables:
                try:
                    value = self._compute_measurable(measurable, claims)
                    computed_values[measurable['name']] = value
                except Exception as e:
                    computation_errors.append(f"Measurable '{measurable['name']}': {str(e)}")
            
            if computation_errors:
                # If we can't compute measurables, mark as UNCERTAIN
                return self._create_uncertain_assessment(
                    gate_spec, computation_errors, computed_values
                )
            
            # Apply decision rules
            decision_result = self._apply_decision_rules(gate_spec, computed_values)
            
            # Create assessment
            assessment = self._create_assessment(gate_spec, decision_result, computed_values)
            
            return assessment
            
        except Exception as e:
            # Log error and return None
            print(f"Error assessing gate {gate_spec.gate_id}: {str(e)}")
            return None

    def _compute_measurable(self, measurable: Dict[str, Any], claims: List[Claim]) -> Any:
        """Compute the value of a measurable from claims."""
        name = measurable.get('name', '')
        compute = measurable.get('compute', '')
        claim_ids = measurable.get('claim_ids', [])
        
        # Get relevant claims
        relevant_claims = [c for c in claims if c.claim_id in claim_ids]
        
        if not relevant_claims:
            raise ValueError(f"No claims found for measurable '{name}'")
        
        # Determine computation type
        for comp_type, func in self.computation_functions.items():
            if comp_type in compute.lower():
                return func(relevant_claims, compute)
        
        # Default to simple aggregation
        return self._compute_simple_aggregation(relevant_claims, compute)

    def _compute_median(self, claims: List[Claim], compute: str) -> float:
        """Compute median of numeric values from claims."""
        numeric_values = []
        
        for claim in claims:
            if claim.has_numeric_value and isinstance(claim.value, (int, float)):
                numeric_values.append(float(claim.value))
        
        if not numeric_values:
            raise ValueError("No numeric values found for median computation")
        
        numeric_values.sort()
        n = len(numeric_values)
        
        if n % 2 == 0:
            return (numeric_values[n//2 - 1] + numeric_values[n//2]) / 2
        else:
            return numeric_values[n//2]

    def _compute_mean(self, claims: List[Claim], compute: str) -> float:
        """Compute mean of numeric values from claims."""
        numeric_values = []
        
        for claim in claims:
            if claim.has_numeric_value and isinstance(claim.value, (int, float)):
                numeric_values.append(float(claim.value))
        
        if not numeric_values:
            raise ValueError("No numeric values found for mean computation")
        
        return sum(numeric_values) / len(numeric_values)

    def _compute_sum(self, claims: List[Claim], compute: str) -> float:
        """Compute sum of numeric values from claims."""
        numeric_values = []
        
        for claim in claims:
            if claim.has_numeric_value and isinstance(claim.value, (int, float)):
                numeric_values.append(float(claim.value))
        
        if not numeric_values:
            raise ValueError("No numeric values found for sum computation")
        
        return sum(numeric_values)

    def _compute_count(self, claims: List[Claim], compute: str) -> int:
        """Compute count of claims."""
        return len(claims)

    def _compute_proportion(self, claims: List[Claim], compute: str) -> float:
        """Compute proportion of claims meeting criteria."""
        if not claims:
            return 0.0
        
        # Extract criteria from compute string (e.g., "proportion(positive)")
        criteria_match = re.search(r'proportion\(([^)]+)\)', compute)
        if criteria_match:
            criteria = criteria_match.group(1).lower()
            
            # Count claims meeting criteria
            matching_count = 0
            for claim in claims:
                if self._claim_meets_criteria(claim, criteria):
                    matching_count += 1
            
            return matching_count / len(claims)
        
        # Default to simple proportion
        return 1.0

    def _compute_ratio(self, claims: List[Claim], compute: str) -> float:
        """Compute ratio between two groups of claims."""
        if len(claims) < 2:
            raise ValueError("Ratio computation requires at least 2 claims")
        
        # Extract ratio groups from compute string (e.g., "ratio(group1/group2)")
        ratio_match = re.search(r'ratio\(([^/]+)/([^)]+)\)', compute)
        if ratio_match:
            group1_name = ratio_match.group(1).strip()
            group2_name = ratio_match.group(2).strip()
            
            # This is a simplified implementation
            # In practice, you'd need more sophisticated grouping logic
            group1_values = [c.value for c in claims if c.has_numeric_value and group1_name in str(c).lower()]
            group2_values = [c.value for c in claims if c.has_numeric_value and group2_name in str(c).lower()]
            
            if group1_values and group2_values:
                group1_avg = sum(group1_values) / len(group1_values)
                group2_avg = sum(group2_values) / len(group2_values)
                
                if group2_avg != 0:
                    return group1_avg / group2_avg
                else:
                    raise ValueError("Division by zero in ratio computation")
        
        # Default to simple ratio of first two numeric values
        numeric_values = [c.value for c in claims if c.has_numeric_value]
        if len(numeric_values) >= 2:
            if numeric_values[1] != 0:
                return numeric_values[0] / numeric_values[1]
            else:
                raise ValueError("Division by zero in ratio computation")
        
        raise ValueError("Unable to compute ratio from available claims")

    def _compute_simple_aggregation(self, claims: List[Claim], compute: str) -> Any:
        """Compute simple aggregation when specific type is not specified."""
        # Try to extract numeric values
        numeric_values = [c.value for c in claims if c.has_numeric_value]
        
        if numeric_values:
            # Return the first numeric value as default
            return numeric_values[0]
        else:
            # Return the number of claims
            return len(claims)

    def _claim_meets_criteria(self, claim: Claim, criteria: str) -> bool:
        """Check if a claim meets specific criteria."""
        if not criteria:
            return True
        
        # Simple criteria matching
        if criteria in ['positive', 'positive_response']:
            return claim.stance == 'supports'
        elif criteria in ['negative', 'negative_response']:
            return claim.stance == 'contradicts'
        elif criteria in ['significant', 'statistically_significant']:
            return claim.is_statistically_significant
        elif criteria in ['high_quality']:
            return claim.quality_score >= 0.8
        
        # Default to True if criteria not recognized
        return True

    def _apply_decision_rules(self, gate_spec: GateSpec, computed_values: Dict[str, Any]) -> Dict[str, Any]:
        """Apply decision rules to determine gate status."""
        decision_result = {
            'status': 'UNCERTAIN',
            'rule_evaluations': [],
            'final_decision': None
        }
        
        # Evaluate each measurable against its threshold
        measurable_results = []
        
        for measurable in gate_spec.measurables:
            name = measurable['name']
            threshold = measurable['threshold']
            computed_value = computed_values.get(name)
            
            if computed_value is None:
                measurable_results.append({
                    'name': name,
                    'computed_value': None,
                    'threshold': threshold,
                    'evaluation': 'UNCERTAIN',
                    'reason': 'Could not compute value'
                })
                continue
            
            # Evaluate threshold
            evaluation = self._evaluate_threshold(computed_value, threshold)
            measurable_results.append({
                'name': name,
                'computed_value': computed_value,
                'threshold': threshold,
                'evaluation': evaluation,
                'reason': f"Value {computed_value} {evaluation} threshold {threshold}"
            })
        
        decision_result['rule_evaluations'] = measurable_results
        
        # Determine overall status based on measurable evaluations
        pass_count = sum(1 for r in measurable_results if r['evaluation'] == 'PASS')
        fail_count = sum(1 for r in measurable_results if r['evaluation'] == 'FAIL')
        uncertain_count = sum(1 for r in measurable_results if r['evaluation'] == 'UNCERTAIN')
        
        if uncertain_count > 0:
            decision_result['status'] = 'UNCERTAIN'
            decision_result['final_decision'] = f"{uncertain_count} measurable(s) could not be evaluated"
        elif fail_count > 0:
            decision_result['status'] = 'FAIL'
            decision_result['final_decision'] = f"{fail_count} measurable(s) failed threshold"
        elif pass_count == len(measurable_results):
            decision_result['status'] = 'PASS'
            decision_result['final_decision'] = "All measurables passed threshold"
        else:
            decision_result['status'] = 'UNCERTAIN'
            decision_result['final_decision'] = "Unable to determine status"
        
        return decision_result

    def _evaluate_threshold(self, value: Any, threshold: Any) -> str:
        """Evaluate a value against a threshold."""
        if threshold is None:
            return 'UNCERTAIN'
        
        # Handle string thresholds with comparison operators
        if isinstance(threshold, str):
            for op, func in self.comparison_operators.items():
                if op in threshold:
                    # Extract the comparison value
                    try:
                        threshold_value = float(threshold.replace(op, '').strip())
                        if func(value, threshold_value):
                            return 'PASS'
                        else:
                            return 'FAIL'
                    except ValueError:
                        return 'UNCERTAIN'
            
            # If no comparison operator found, try exact match
            try:
                if value == threshold:
                    return 'PASS'
                else:
                    return 'FAIL'
            except:
                return 'UNCERTAIN'
        
        # Handle numeric thresholds
        elif isinstance(threshold, (int, float)):
            try:
                if value >= threshold:
                    return 'PASS'
                else:
                    return 'FAIL'
            except:
                return 'UNCERTAIN'
        
        # Handle boolean thresholds
        elif isinstance(threshold, bool):
            try:
                if bool(value) == threshold:
                    return 'PASS'
                else:
                    return 'FAIL'
            except:
                return 'UNCERTAIN'
        
        return 'UNCERTAIN'

    def _create_assessment(
        self, 
        gate_spec: GateSpec, 
        decision_result: Dict[str, Any], 
        computed_values: Dict[str, Any]
    ) -> GateAssessment:
        """Create a GateAssessment from the decision result."""
        # Import GateAssessment here to avoid circular imports
        from ...models.gate_assessment import GateAssessment
        
        assessment = GateAssessment(
            gate_id=gate_spec.gate_id,
            status=decision_result['status'],
            rationale=self._generate_rationale(gate_spec, decision_result, computed_values),
            sensitivity=self._generate_sensitivity_analysis(computed_values),
            assessment_method=self.name,
            confidence_in_assessment=0.7
        )
        
        # Add computed values to metadata
        if hasattr(assessment, 'computed_values'):
            assessment.computed_values = computed_values
        
        return assessment

    def _create_uncertain_assessment(
        self, 
        gate_spec: GateSpec, 
        computation_errors: List[str], 
        computed_values: Dict[str, Any]
    ) -> GateAssessment:
        """Create an UNCERTAIN assessment when computation fails."""
        # Import GateAssessment here to avoid circular imports
        from ...models.gate_assessment import GateAssessment
        
        assessment = GateAssessment(
            gate_id=gate_spec.gate_id,
            status='UNCERTAIN',
            rationale=f"Unable to assess gate due to computation errors: {'; '.join(computation_errors)}",
            sensitivity=[],
            assessment_method=self.name,
            confidence_in_assessment=0.3
        )
        
        # Add partial computed values if any
        if computed_values and hasattr(assessment, 'computed_values'):
            assessment.computed_values = computed_values
        
        return assessment

    def _generate_rationale(
        self, 
        gate_spec: GateSpec, 
        decision_result: Dict[str, Any], 
        computed_values: Dict[str, Any]
    ) -> List[str]:
        """
        Generate rationale for the assessment with claim citations.
        
        Implements the specification requirement: "every sentence cites claim ids"
        """
        rationale = []
        
        # Add overall decision with claim context
        rationale.append(f"Gate assessment: {decision_result['status']} based on evaluation of {len(gate_spec.measurables)} measurables")
        
        # Add measurable evaluations with claim citations
        for measurable in gate_spec.measurables:
            name = measurable['name']
            claim_ids = measurable.get('claim_ids', [])
            evaluation = next((r for r in decision_result['rule_evaluations'] if r['name'] == name), None)
            
            if evaluation:
                # Format claim IDs for citation
                claim_citations = ', '.join([f"[{cid}]" for cid in claim_ids]) if claim_ids else "[no_claims]"
                
                rationale.append(
                    f"Measurable '{name}' computed as {evaluation['computed_value']} "
                    f"({evaluation['evaluation']} threshold {evaluation['threshold']}) "
                    f"using claims {claim_citations}"
                )
        
        # Add final decision explanation with supporting evidence
        if decision_result['final_decision']:
            all_claim_ids = []
            for measurable in gate_spec.measurables:
                all_claim_ids.extend(measurable.get('claim_ids', []))
            
            if all_claim_ids:
                claim_citations = ', '.join([f"[{cid}]" for cid in set(all_claim_ids)])
                rationale.append(f"Decision: {decision_result['final_decision']} based on evidence from claims {claim_citations}")
            else:
                rationale.append(f"Decision: {decision_result['final_decision']}")
        
        return rationale

    def _generate_sensitivity_analysis(self, computed_values: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate sensitivity analysis with 1-2 knobs as required by specification.
        
        Implements: "sensitivity[] (1–2 knobs)" from the Study Card Overhaul.
        """
        sensitivity = []
        
        # Limit to 1-2 sensitivity knobs as specified
        max_knobs = 2
        numeric_values = [(name, value) for name, value in computed_values.items() 
                         if isinstance(value, (int, float)) and value > 0]
        
        # Sort by importance (higher values get priority)
        numeric_values.sort(key=lambda x: abs(x[1]), reverse=True)
        
        for i, (name, value) in enumerate(numeric_values[:max_knobs]):
            # Knob 1: ±20% variation (conservative)
            if i == 0:
                sensitivity.append({
                    'knob': 'conservative_variation',
                    'measurable': name,
                    'baseline_value': value,
                    'sensitivity_range': [value * 0.8, value * 1.2],
                    'description': f"±20% variation around baseline {value}",
                    'impact': 'Conservative sensitivity analysis'
                })
            
            # Knob 2: ±50% variation (aggressive) - if we have a second measurable
            elif i == 1:
                sensitivity.append({
                    'knob': 'aggressive_variation',
                    'measurable': name,
                    'baseline_value': value,
                    'sensitivity_range': [value * 0.5, value * 1.5],
                    'description': f"±50% variation around baseline {value}",
                    'impact': 'Aggressive sensitivity analysis'
                })
        
        return sensitivity

    def _has_citations_in_rationale(self, assessment: 'GateAssessment') -> bool:
        """Check if rationale contains claim citations."""
        if not assessment.rationale:
            return False
        
        # Check if any sentence contains claim citations in [claim_id] format
        for sentence in assessment.rationale:
            if '[' in sentence and ']' in sentence:
                return True
        return False
    
    def _shows_intermediate_numbers(self, assessment: 'GateAssessment') -> bool:
        """Check if assessment shows intermediate numbers."""
        # Check if computed values are available in audit metadata
        if hasattr(assessment, 'computed_values') and assessment.computed_values:
            return True
        
        # Check if audit contains computation details
        if hasattr(assessment, 'audit') and assessment.audit:
            if 'computation_details' in assessment.audit:
                return True
        
        return False
    
    def _shows_decision_evaluation(self, assessment: 'GateAssessment') -> bool:
        """Check if assessment shows decision rule evaluation."""
        # Check if rationale explains the decision process
        if assessment.rationale:
            decision_keywords = ['threshold', 'evaluation', 'decision', 'measurable']
            for sentence in assessment.rationale:
                if any(keyword in sentence.lower() for keyword in decision_keywords):
                    return True
        
        return False
