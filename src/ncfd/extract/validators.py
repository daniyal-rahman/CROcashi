"""
Global validation rules for the study card system.

This module provides validation functions that enforce critical business rules
and cause hard FAILs when violations are detected.
"""

import json
import re
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import asdict
from .models import ResultsFactsheet, Claim, MethodCard, EvidenceSpan


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


class GlobalValidator:
    """Global validator that enforces critical business rules."""
    
    @staticmethod
    def validate_artifact(artifact: Any, artifact_type: str) -> Tuple[bool, List[str]]:
        """
        Validate an artifact against global rules.
        
        Args:
            artifact: The artifact to validate
            artifact_type: Type of artifact for error reporting
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Convert to dict if it's a dataclass
        if hasattr(artifact, 'to_dict'):
            artifact_dict = artifact.to_dict()
        else:
            artifact_dict = artifact
        
        # Check for Field() leakage
        field_errors = GlobalValidator._check_field_leakage(artifact_dict, artifact_type)
        errors.extend(field_errors)
        
        # Check for double-encoded JSON
        json_errors = GlobalValidator._check_double_encoded_json(artifact_dict, artifact_type)
        errors.extend(json_errors)
        
        # Check for proper ID formats
        id_errors = GlobalValidator._check_id_formats(artifact_dict, artifact_type)
        errors.extend(id_errors)
        
        # Check for provenance anchors
        provenance_errors = GlobalValidator._check_provenance(artifact_dict, artifact_type)
        errors.extend(provenance_errors)
        
        return len(errors) == 0, errors
    
    @staticmethod
    def _check_field_leakage(artifact_dict: Dict[str, Any], artifact_type: str) -> List[str]:
        """Check for Field(...) representations in the artifact."""
        errors = []
        
        def check_value(value: Any, path: str):
            if isinstance(value, str) and "Field(" in value:
                errors.append(f"{artifact_type}: Field() leakage found at {path}: {value}")
            elif isinstance(value, dict):
                for key, val in value.items():
                    check_value(val, f"{path}.{key}")
            elif isinstance(value, list):
                for i, val in enumerate(value):
                    check_value(val, f"{path}[{i}]")
        
        check_value(artifact_dict, "root")
        return errors
    
    @staticmethod
    def _check_double_encoded_json(artifact_dict: Dict[str, Any], artifact_type: str) -> List[str]:
        """Check for double-encoded JSON strings in object-typed fields."""
        errors = []
        
        # Fields that should be objects, not JSON strings
        object_fields = {
            'estimand', 'alpha_structure', 'analysis_set', 'interim', 
            'missingness', 'endpoint_ascertainment', 'protocol_features',
            'site_geography', 'design_risks'
        }
        
        def check_value(value: Any, path: str):
            if isinstance(value, str) and path.split('.')[-1] in object_fields:
                try:
                    # Try to parse as JSON
                    parsed = json.loads(value)
                    if isinstance(parsed, (dict, list)):
                        errors.append(f"{artifact_type}: Double-encoded JSON found at {path}. Should be object, not string.")
                except json.JSONDecodeError:
                    # Not JSON, might be legitimate string
                    pass
            elif isinstance(value, dict):
                for key, val in value.items():
                    check_value(val, f"{path}.{key}")
            elif isinstance(value, list):
                for i, val in enumerate(value):
                    check_value(val, f"{path}[{i}]")
        
        check_value(artifact_dict, "root")
        return errors
    
    @staticmethod
    def _check_id_formats(artifact_dict: Dict[str, Any], artifact_type: str) -> List[str]:
        """Check for proper ID formats."""
        errors = []
        
        # Check doc_id format
        if 'doc_id' in artifact_dict:
            doc_id = artifact_dict['doc_id']
            if not GlobalValidator._is_valid_doc_id(doc_id):
                errors.append(f"{artifact_type}: Invalid doc_id format: {doc_id}")
        
        # Check span_id format
        if 'span_ids' in artifact_dict:
            span_ids = artifact_dict['span_ids']
            if isinstance(span_ids, list):
                for i, span_id in enumerate(span_ids):
                    if not GlobalValidator._is_valid_span_id(span_id):
                        errors.append(f"{artifact_type}: Invalid span_id format at index {i}: {span_id}")
        
        # Check for generic IDs
        if 'id' in artifact_dict:
            artifact_id = artifact_dict['id']
            if not GlobalValidator._is_valid_artifact_id(artifact_id):
                errors.append(f"{artifact_type}: Invalid artifact ID format: {artifact_id}")
        
        return errors
    
    @staticmethod
    def _check_provenance(artifact_dict: Dict[str, Any], artifact_type: str) -> List[str]:
        """Check for proper provenance tracking."""
        errors = []
        
        # Check for input_hash
        if 'input_hash' in artifact_dict:
            input_hash = artifact_dict['input_hash']
            if input_hash is None or input_hash == "":
                errors.append(f"{artifact_type}: input_hash is null or empty")
            elif not GlobalValidator._is_valid_hash(input_hash):
                errors.append(f"{artifact_type}: Invalid input_hash format: {input_hash}")
        else:
            errors.append(f"{artifact_type}: Missing input_hash field")
        
        # Check for span_ids or provenance_anchors
        has_span_refs = False
        if 'span_ids' in artifact_dict and artifact_dict['span_ids']:
            has_span_refs = True
        if 'provenance_anchors' in artifact_dict and artifact_dict['provenance_anchors']:
            has_span_refs = True
        
        if not has_span_refs:
            errors.append(f"{artifact_type}: No span references found (span_ids or provenance_anchors)")
        
        return errors
    
    @staticmethod
    def _is_valid_doc_id(doc_id: str) -> bool:
        """Check if doc_id follows the correct format."""
        if not isinstance(doc_id, str):
            return False
        
        # Pattern: {source}:{accession}
        pattern = r'^[a-z]+:[A-Za-z0-9._-]+$'
        return bool(re.match(pattern, doc_id))
    
    @staticmethod
    def _is_valid_span_id(span_id: str) -> bool:
        """Check if span_id follows the correct format."""
        if not isinstance(span_id, str):
            return False
        
        # Pattern: {doc_id}#<locator>
        if '#' not in span_id:
            return False
        
        doc_part, locator = span_id.split('#', 1)
        if not GlobalValidator._is_valid_doc_id(doc_part):
            return False
        
        # Check locator format
        # sec:Methods:char234-471 or p1:char234-471 or table:3:rRECIST_total
        locator_patterns = [
            r'^sec:[A-Za-z]+:char\d+-\d+$',
            r'^p\d+:char\d+-\d+$',
            r'^table:\d+:r[A-Za-z0-9_]+$',
            r'^table:\d+:r\d+c\d+$',
            r'^table:\d+:cell:[A-Za-z0-9_]+$'
        ]
        
        return any(re.match(pattern, locator) for pattern in locator_patterns)
    
    @staticmethod
    def _is_valid_artifact_id(artifact_id: str) -> bool:
        """Check if artifact ID follows the correct format."""
        if not isinstance(artifact_id, str):
            return False
        
        # For now, allow shorter IDs (ULID format will be enforced later)
        # Should be alphanumeric and at least 8 characters
        id_pattern = r'^[0-9A-Za-z_-]{8,}$'
        return bool(re.match(id_pattern, artifact_id))
    
    @staticmethod
    def _is_valid_hash(hash_value: str) -> bool:
        """Check if hash follows the correct format."""
        if not isinstance(hash_value, str):
            return False
        
        # For now, allow shorter hashes (SHA256 format will be enforced later)
        # Should be alphanumeric and at least 8 characters
        hash_pattern = r'^[a-f0-9]{8,}$'
        return bool(re.match(hash_pattern, hash_value))

    @staticmethod
    def validate_results_factsheet_coverage(factsheet: ResultsFactsheet, spans: List[EvidenceSpan]) -> List[str]:
        """
        Validate that ResultsFactsheet contains required metrics when trigger tokens appear.
        
        Must-fail rule: results_factsheet must contain ≥2 of {orr_recist, median_pfs|median_ttp, median_os} 
        when their trigger tokens appear in input spans.
        """
        violations = []
        
        # Check for trigger tokens in spans
        combined_text = " ".join([span.quote.lower() for span in spans])
        
        # Define trigger tokens and their corresponding required metrics
        required_metrics = {
            'orr_recist': ['orr', 'response rate', 'objective response', 'recist'],
            'median_pfs': ['pfs', 'progression-free survival', 'progression free survival'],
            'median_ttp': ['ttp', 'time to progression'],
            'median_os': ['os', 'overall survival', 'survival']
        }
        
        # Check which metrics should be present based on trigger tokens
        expected_metrics = []
        for metric, triggers in required_metrics.items():
            if any(trigger in combined_text for trigger in triggers):
                expected_metrics.append(metric)
        
        # Must-fail rule: need at least 2 metrics when triggers are present
        if len(expected_metrics) >= 2:
            # Check if factsheet has the required metrics
            factsheet_metrics = []
            if hasattr(factsheet, 'results') and factsheet.results:
                for result in factsheet.results:
                    if isinstance(result, dict) and 'metric' in result:
                        factsheet_metrics.append(result['metric'])
                    elif hasattr(result, 'metric'):
                        factsheet_metrics.append(result.metric)
                
                # Check coverage
                missing_metrics = []
                for expected in expected_metrics:
                    if not any(expected in str(metric).lower() for metric in factsheet_metrics):
                        missing_metrics.append(expected)
                
                if len(missing_metrics) > 0:
                    violation = f"CRITICAL: ResultsFactsheet missing required metrics: {missing_metrics}. Expected ≥2 of {expected_metrics} when triggers present."
                    violations.append(violation)
        
        return violations
    
    @staticmethod
    def validate_claim_provenance(claims: List[Claim]) -> List[str]:
        """
        Validate that all claims with numerics have span_ids.
        
        Must-fail rule: All claims with numerics must have span_ids.
        """
        violations = []
        
        for claim in claims:
            # Check if claim has numeric value
            if hasattr(claim, 'value') and claim.value is not None:
                # Check if span_ids is empty
                if not claim.span_ids:
                    violation = f"CRITICAL: Claim with numeric value '{claim.value}' has empty span_ids. Every numeric must be span-anchored."
                    violations.append(violation)
        
        return violations
    
    @staticmethod
    def validate_ci_mis_extraction(claims: List[Claim], spans: List[EvidenceSpan]) -> List[str]:
        """
        Validate that no claim has value=95% if "95% CI" is nearby.
        
        Must-fail rule: No claim may have value=95% if "95% CI" is nearby.
        """
        violations = []
        
        # Check for CI patterns in spans
        ci_spans = []
        for span in spans:
            if '95% ci' in span.quote.lower() or '95% confidence interval' in span.quote.lower():
                ci_spans.append(span)
        
        # Check claims for 95% values
        for claim in claims:
            if hasattr(claim, 'value') and claim.value == '95%':
                # Check if this claim is from a span near CI information
                for ci_span in ci_spans:
                    # Simple proximity check - if claim span is close to CI span
                    if hasattr(claim, 'span_ids') and claim.span_ids:
                        # This is a basic check - in practice you might want more sophisticated proximity logic
                        violation = f"CRITICAL: Claim has value=95% which appears to be from CI context. This should be ci_level, not effect value."
                        violations.append(violation)
                        break
        
        return violations
    
    @staticmethod
    def validate_safety_classification(claims: List[Claim]) -> List[str]:
        """
        Validate that safety sentences cannot map to response_rate.
        
        Must-fail rule: Safety sentences cannot map to response_rate.
        """
        violations = []
        
        for claim in claims:
            if hasattr(claim, 'type') and claim.type == 'safety':
                if hasattr(claim, 'endpoint') and 'response_rate' in str(claim.endpoint).lower():
                    violation = f"CRITICAL: Safety claim misclassified as response_rate. Safety claims cannot be response_rate."
                    violations.append(violation)
        
        return violations
    
    @staticmethod
    def validate_gehan_design_consistency(method_card: MethodCard, spans: List[EvidenceSpan]) -> List[str]:
        """
        Validate Gehan design consistency.
        
        Must-fail rule: If "Gehan" is present, gehan_two_stage=True and interim_looks=1.
        """
        violations = []
        
        # Check for Gehan presence in spans
        combined_text = " ".join([span.quote.lower() for span in spans])
        gehan_present = 'gehan' in combined_text
        
        if gehan_present:
            # Check gehan_two_stage
            if not method_card.gehan_two_stage:
                violation = f"CRITICAL: 'Gehan' detected in spans but gehan_two_stage=False. Must be True when Gehan is present."
                violations.append(violation)
            
            # Check interim_looks
            if hasattr(method_card, 'interim_looks'):
                if isinstance(method_card.interim_looks, list):
                    if len(method_card.interim_looks) != 1:
                        violation = f"CRITICAL: 'Gehan' detected but interim_looks has {len(method_card.interim_looks)} looks. Must be 1 for Gehan design."
                        violations.append(violation)
                else:
                    violation = f"CRITICAL: 'Gehan' detected but interim_looks is not a list. Must be [1] for Gehan design."
                    violations.append(violation)
        
        return violations
    
    @staticmethod
    def hard_fail_on_empty_provenance(claims: List[Any]) -> bool:
        """
        Check if any claims have empty span_ids and hard fail if so.
        
        Args:
            claims: List of Claim objects
            
        Returns:
            True if all claims have span_ids, False if any are empty
            
        Raises:
            AssertionError: If any claim has empty span_ids
        """
        for claim in claims:
            if hasattr(claim, 'span_ids') and not claim.span_ids:
                error_message = f"CRITICAL: Claim with value '{getattr(claim, 'value', 'unknown')}' has empty span_ids. Every numeric must be span-anchored."
                raise AssertionError(error_message)
        return True
    
    @staticmethod
    def hard_fail_on_critical_violations(violations: List[str]) -> None:
        """
        Hard fail if any critical violations are found.
        
        This method will raise an exception with all violations, causing the test to FAIL.
        """
        if violations:
            error_message = "CRITICAL VALIDATION VIOLATIONS - TEST MUST FAIL:\n"
            for i, violation in enumerate(violations, 1):
                error_message += f"{i}. {violation}\n"
            error_message += "\nThese violations indicate critical bugs that must be fixed before proceeding."
            raise AssertionError(error_message)
    
    @staticmethod
    def validate_comprehensive_system(factsheet: ResultsFactsheet, claims: List[Claim], 
                                   method_card: MethodCard, spans: List[EvidenceSpan]) -> List[str]:
        """
        Run comprehensive validation across all components.
        
        Returns list of violations. Call hard_fail_on_critical_violations() to enforce.
        """
        all_violations = []
        
        # Validate ResultsFactsheet coverage
        factsheet_violations = GlobalValidator.validate_results_factsheet_coverage(factsheet, spans)
        all_violations.extend(factsheet_violations)
        
        # Validate claim provenance
        claim_provenance_violations = GlobalValidator.validate_claim_provenance(claims)
        all_violations.extend(claim_provenance_violations)
        
        # Validate CI mis-extraction
        ci_violations = GlobalValidator.validate_ci_mis_extraction(claims, spans)
        all_violations.extend(ci_violations)
        
        # Validate safety classification
        safety_violations = GlobalValidator.validate_safety_classification(claims)
        all_violations.extend(safety_violations)
        
        # Validate Gehan design consistency
        gehan_violations = GlobalValidator.validate_gehan_design_consistency(method_card, spans)
        all_violations.extend(gehan_violations)
        
        return all_violations


class ResultsFactsheetValidator:
    """Specific validator for ResultsFactsheet."""
    
    @staticmethod
    def validate(factsheet: Any) -> Tuple[bool, List[str]]:
        """Validate a ResultsFactsheet against Step 0 requirements."""
        errors = []
        
        if hasattr(factsheet, 'to_dict'):
            factsheet_dict = factsheet.to_dict()
        else:
            factsheet_dict = factsheet
        
        # Check required fields for each result
        if 'results' in factsheet_dict:
            for i, result in enumerate(factsheet_dict['results']):
                result_errors = ResultsFactsheetValidator._validate_result(result, i)
                errors.extend(result_errors)
        
        return len(errors) == 0, errors
    
    @staticmethod
    def _validate_result(result: Dict[str, Any], index: int) -> List[str]:
        """Validate a single result item."""
        errors = []
        
        # Required fields
        required_fields = ['metric', 'value', 'units', 'n', 'span_ids']
        for field in required_fields:
            if field not in result:
                errors.append(f"Result[{index}]: Missing required field '{field}'")
        
        # Validate metric enum
        if 'metric' in result:
            valid_metrics = {
                'median_os', 'median_ttp', 'median_pfs', 'orr_recist', 
                'ca125_response', 'os_fixed_time', 'pfs_fixed_time', 'response_rate'
            }
            if result['metric'] not in valid_metrics:
                errors.append(f"Result[{index}]: Invalid metric '{result['metric']}'. Must be one of {valid_metrics}")
        
        # Validate units enum
        if 'units' in result:
            valid_units = {'months', 'weeks', 'percent', 'count', 'ratio'}
            if result['units'] not in valid_units:
                errors.append(f"Result[{index}]: Invalid units '{result['units']}'. Must be one of {valid_units}")
        
        # Validate numeric value
        if 'value' in result:
            if not isinstance(result['value'], (int, float)):
                errors.append(f"Result[{index}]: Value must be numeric, got {type(result['value'])}")
        
        # Validate n (denominator)
        if 'n' in result:
            if not isinstance(result['n'], int) or result['n'] <= 0:
                errors.append(f"Result[{index}]: n must be positive integer, got {result['n']}")
        
        # Validate span_ids - every result must have at least one span_id
        if 'span_ids' in result:
            span_ids = result['span_ids']
            if not isinstance(span_ids, list) or len(span_ids) == 0:
                errors.append(f"Result[{index}]: span_ids must be non-empty list")
            else:
                for span_id in span_ids:
                    if not GlobalValidator._is_valid_span_id(span_id):
                        errors.append(f"Result[{index}]: Invalid span_id: {span_id}")
        else:
            errors.append(f"Result[{index}]: Missing span_ids field")
        
        # Validate timepoint rule
        if 'timepoint' in result and 'metric' in result:
            if result['metric'].startswith('median_') and result['timepoint']:
                errors.append(f"Result[{index}]: Timepoint not allowed for median metrics: {result['metric']}")
        
        # Validate n (denominator) - must not be default values
        if 'n' in result:
            if result['n'] in [100, 0, None]:  # Common default values
                errors.append(f"Result[{index}]: n cannot be default value {result['n']}, must extract actual denominator")
        
        return errors


class MethodCardValidator:
    """Specific validator for MethodCard."""
    
    @staticmethod
    def validate(method_card: Any) -> Tuple[bool, List[str]]:
        """Validate a MethodCard against Step 0 requirements."""
        errors = []
        
        if hasattr(method_card, 'to_dict'):
            method_dict = method_card.to_dict()
        else:
            method_dict = method_card
        
        # Check that object fields are real objects, not JSON strings
        object_fields = ['estimand', 'alpha_structure', 'analysis_set']
        for field in object_fields:
            if field in method_dict:
                value = method_dict[field]
                if isinstance(value, str):
                    try:
                        json.loads(value)
                        errors.append(f"MethodCard: Field '{field}' is JSON string, should be object")
                    except json.JSONDecodeError:
                        pass  # Not JSON, might be legitimate string
        
        # Validate Gehan two-stage design consistency
        if 'interim_looks' in method_dict and 'gehan_two_stage' in method_dict:
            interim_looks = method_dict['interim_looks']
            gehan_two_stage = method_dict['gehan_two_stage']
            
            # If interim_looks == 1 due to Gehan design, gehan_two_stage must be True
            if isinstance(interim_looks, list) and len(interim_looks) == 1 and gehan_two_stage is False:
                errors.append("MethodCard: If interim_looks == 1 due to Gehan design, gehan_two_stage must be True")
        
        # Validate site geography - must not be inferred from affiliations
        if 'site_geography' in method_dict:
            site_geo = method_dict['site_geography']
            if isinstance(site_geo, dict):
                if site_geo.get('num_sites') == 'not_reported' and site_geo.get('regions'):
                    errors.append("MethodCard: Regions cannot be specified if num_sites is 'not_reported'")
        
        # Validate missingness assumptions - must not be guessed
        if 'missingness_assumption' in method_dict:
            missingness = method_dict['missingness_assumption']
            if missingness in ['MAR', 'MNAR']:
                # Check if there's a span_id to support this assumption
                if 'provenance_anchors' not in method_dict or not method_dict['provenance_anchors']:
                    errors.append("MethodCard: Missingness assumption MAR/MNAR requires provenance anchors")
        
        return len(errors) == 0, errors


def validate_all_artifacts(artifacts: List[Any]) -> Tuple[bool, List[str]]:
    """
    Validate all artifacts against global rules.
    
    Args:
        artifacts: List of artifacts to validate
        
    Returns:
        Tuple of (all_valid, all_errors)
    """
    all_errors = []
    all_valid = True
    
    for artifact in artifacts:
        # Determine artifact type
        artifact_type = type(artifact).__name__
        
        # Global validation
        is_valid, errors = GlobalValidator.validate_artifact(artifact, artifact_type)
        all_errors.extend(errors)
        if not is_valid:
            all_valid = False
        
        # Type-specific validation
        if artifact_type == 'ResultsFactsheet':
            is_valid, errors = ResultsFactsheetValidator.validate(artifact)
            all_errors.extend(errors)
            if not is_valid:
                all_valid = False
        elif artifact_type == 'MethodCard':
            is_valid, errors = MethodCardValidator.validate(artifact)
            all_errors.extend(errors)
            if not is_valid:
                all_valid = False
    
    return all_valid, all_errors


def validate_artifacts(*args, **kwargs):  # back-compat shim
    return validate_all_artifacts(*args, **kwargs)
