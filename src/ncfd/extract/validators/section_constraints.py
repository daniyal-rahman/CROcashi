"""
Section Constraints Validator

Enforces field-level section constraints for artifacts.
"""

import yaml
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import Counter

from ..models import MethodCard, ResultsFactsheet, EvidenceSpan
from .section_resolver import SectionResolver, create_section_resolver


@dataclass
class ConstraintViolation:
    """Represents a section constraint violation."""
    artifact_type: str
    field_name: str
    expected_sections: List[str]
    actual_sections: List[str]
    severity: str
    message: str
    span_ids: List[str]


class SectionConstraintsValidator:
    """Validates that artifact fields come from appropriate sections."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the validator.
        
        Args:
            config_path: Path to section constraints configuration file
        """
        self.config = self._load_config(config_path)
        self.resolver = create_section_resolver(config_path)
        
        # Extract configuration
        self.constraints = self.config.get('constraints', {})
        self.severity = self.config.get('severity', {})
        self.validation_policy = self.config.get('validation_policy', {})
        
        # Policy settings
        self.min_allowed_fraction = self.validation_policy.get('min_allowed_fraction', 0.8)
        self.min_allowed_primary = self.validation_policy.get('min_allowed_primary', 1)
        self.auto_repair_attempts = self.validation_policy.get('auto_repair_attempts', 1)
        self.unknown_section_allowed = self.validation_policy.get('unknown_section_allowed', False)
    
    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from file."""
        if not config_path:
            config_path = "config/section_constraints.yaml"
        
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load section constraints config from {config_path}: {e}")
            return {}
    
    def enforce_section_constraints(self, method_card: Optional[MethodCard] = None,
                                  results_factsheet: Optional[ResultsFactsheet] = None,
                                  evidence_spans: Optional[List[EvidenceSpan]] = None) -> Tuple[bool, List[str], List[str]]:
        """
        Enforce section constraints for all artifacts.
        
        Args:
            method_card: MethodCard to validate
            results_factsheet: ResultsFactsheet to validate
            evidence_spans: Evidence spans for context
            
        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        errors = []
        warnings = []
        
        # Convert evidence spans to base spans for resolver
        base_spans = self._convert_evidence_spans_to_base_spans(evidence_spans) if evidence_spans else []
        
        # Validate MethodCard
        if method_card:
            method_errors, method_warnings = self._validate_method_card(method_card, base_spans)
            errors.extend(method_errors)
            warnings.extend(method_warnings)
        
        # Validate ResultsFactsheet
        if results_factsheet:
            results_errors, results_warnings = self._validate_results_factsheet(results_factsheet, base_spans)
            errors.extend(results_errors)
            warnings.extend(results_warnings)
        
        return len(errors) == 0, errors, warnings
    
    def _validate_method_card(self, method_card: MethodCard, base_spans: List[Any]) -> Tuple[List[str], List[str]]:
        """Validate MethodCard section constraints."""
        errors = []
        warnings = []
        
        methodcard_constraints = self.constraints.get('MethodCard', {})
        methodcard_severity = self.severity.get('MethodCard', {})
        
        # Get all fields from method card
        method_card_dict = method_card.to_dict() if hasattr(method_card, 'to_dict') else method_card.__dict__
        
        for field_name, allowed_sections in methodcard_constraints.items():
            if field_name not in method_card_dict:
                continue
            
            field_value = method_card_dict[field_name]
            if not field_value:
                continue
            
            # Get span IDs for this field
            span_ids = self._extract_span_ids_from_field(field_value)
            if not span_ids:
                continue
            
            # Validate section constraints
            violation = self._validate_field_sections(
                "MethodCard", field_name, span_ids, allowed_sections, 
                methodcard_severity.get(field_name, "hard"), base_spans
            )
            
            if violation:
                message = f"MethodCard.{field_name}: {violation.message}"
                if violation.severity == "hard":
                    errors.append(message)
                else:
                    warnings.append(message)
        
        return errors, warnings
    
    def _validate_results_factsheet(self, results_factsheet: ResultsFactsheet, base_spans: List[Any]) -> Tuple[List[str], List[str]]:
        """Validate ResultsFactsheet section constraints."""
        errors = []
        warnings = []
        
        results_constraints = self.constraints.get('ResultsFactsheet', {})
        results_severity = self.severity.get('ResultsFactsheet', {})
        
        # Handle results list
        if hasattr(results_factsheet, 'results') and results_factsheet.results:
            for i, result in enumerate(results_factsheet.results):
                if isinstance(result, dict):
                    # Check metric field
                    metric = result.get('metric')
                    if metric and metric in results_constraints:
                        allowed_sections = results_constraints[metric]
                        span_ids = result.get('span_ids', [])
                        
                        if span_ids:
                            violation = self._validate_field_sections(
                                f"ResultsFactsheet[result_{i}]", metric, span_ids, allowed_sections,
                                results_severity.get(metric, "hard"), base_spans
                            )
                            
                            if violation:
                                message = f"ResultsFactsheet.result_{i}.{metric}: {violation.message}"
                                if violation.severity == "hard":
                                    errors.append(message)
                                else:
                                    warnings.append(message)
        
        return errors, warnings
    
    def _validate_field_sections(self, artifact_type: str, field_name: str, span_ids: List[str],
                               allowed_sections: List[str], severity: str, base_spans: List[Any]) -> Optional[ConstraintViolation]:
        """
        Validate that a field's spans come from allowed sections.
        
        Args:
            artifact_type: Type of artifact
            field_name: Name of the field
            span_ids: List of span IDs supporting this field
            allowed_sections: List of allowed section names
            severity: Severity level ("hard" or "warn")
            base_spans: List of base spans for resolution
            
        Returns:
            ConstraintViolation if validation fails, None otherwise
        """
        if not span_ids:
            return None
        
        # Get resolved sections for all spans
        actual_sections = self.resolver.get_span_sections(span_ids, base_spans)
        
        # Count sections
        section_counts = Counter(actual_sections)
        total_spans = len(actual_sections)
        
        # Check if any sections are not allowed
        disallowed_sections = [s for s in actual_sections if s not in allowed_sections and s != "unknown"]
        
        # Apply fraction rule
        allowed_count = sum(section_counts.get(section, 0) for section in allowed_sections)
        allowed_fraction = allowed_count / total_spans if total_spans > 0 else 0
        
        # Check primary section requirement
        primary_section_ok = False
        if allowed_sections:
            primary_section = allowed_sections[0]  # First section is primary
            primary_section_ok = section_counts.get(primary_section, 0) >= self.min_allowed_primary
        
        # Determine if validation passes
        validation_passes = (
            allowed_fraction >= self.min_allowed_fraction and
            primary_section_ok and
            (self.unknown_section_allowed or "unknown" not in actual_sections)
        )
        
        if validation_passes:
            return None
        
        # Create violation message
        message_parts = []
        if allowed_fraction < self.min_allowed_fraction:
            message_parts.append(f"only {allowed_fraction:.1%} spans in allowed sections (need {self.min_allowed_fraction:.1%})")
        
        if not primary_section_ok:
            message_parts.append(f"no spans in primary section '{allowed_sections[0]}'")
        
        if disallowed_sections:
            message_parts.append(f"spans from disallowed sections: {disallowed_sections}")
        
        if "unknown" in actual_sections and not self.unknown_section_allowed:
            message_parts.append("spans from unknown sections")
        
        message = f"Section constraint violation: {', '.join(message_parts)}. "
        message += f"Expected: {allowed_sections}, Got: {dict(section_counts)}"
        
        return ConstraintViolation(
            artifact_type=artifact_type,
            field_name=field_name,
            expected_sections=allowed_sections,
            actual_sections=actual_sections,
            severity=severity,
            message=message,
            span_ids=span_ids
        )
    
    def _extract_span_ids_from_field(self, field_value: Any) -> List[str]:
        """Extract span IDs from a field value."""
        span_ids = []
        
        if isinstance(field_value, dict):
            # Check for span_ids key
            if 'span_ids' in field_value:
                span_ids.extend(field_value['span_ids'])
            
            # Check for provenance_anchors key
            if 'provenance_anchors' in field_value:
                span_ids.extend(field_value['provenance_anchors'])
        
        elif isinstance(field_value, list):
            # Handle list of objects
            for item in field_value:
                if isinstance(item, dict):
                    span_ids.extend(self._extract_span_ids_from_field(item))
        
        elif hasattr(field_value, 'span_ids'):
            # Handle object with span_ids attribute
            span_ids.extend(getattr(field_value, 'span_ids', []))
        
        elif hasattr(field_value, 'provenance_anchors'):
            # Handle object with provenance_anchors attribute
            span_ids.extend(getattr(field_value, 'provenance_anchors', []))
        
        return span_ids
    
    def _convert_evidence_spans_to_base_spans(self, evidence_spans: List[EvidenceSpan]) -> List[Any]:
        """Convert EvidenceSpan objects to BaseSpan-like objects for the resolver."""
        # This is a simplified conversion - in practice, you'd want to load actual BaseSpans
        base_spans = []
        
        for span in evidence_spans:
            # Create a mock BaseSpan-like object
            mock_span = type('MockBaseSpan', (), {
                'span_id': span.span_id,
                'doc_id': span.doc_id,
                'section': span.section,
                'page': span.page,
                'char_start': span.char_start,
                'char_end': span.char_end,
                'text': span.quote,
                'is_table_cell': span.is_table_cell_span,
                'table_id': span.table_id,
                'row': span.table_row,
                'col': span.table_col,
                'kind': span.kind,
                'parent_span_ids': span.parent_span_ids
            })()
            base_spans.append(mock_span)
        
        return base_spans
    
    def attempt_auto_repair(self, violation: ConstraintViolation, 
                          available_spans: List[Any]) -> Optional[List[str]]:
        """
        Attempt to auto-repair a constraint violation by finding better spans.
        
        Args:
            violation: The constraint violation to repair
            available_spans: Available spans to search through
            
        Returns:
            List of better span IDs if repair successful, None otherwise
        """
        # This is a placeholder for auto-repair logic
        # In practice, you'd implement targeted retrieval for the missing sections
        
        # For now, just return None (no repair attempted)
        return None


# Convenience function for external use
def enforce_section_constraints(method_card: Optional[MethodCard] = None,
                              results_factsheet: Optional[ResultsFactsheet] = None,
                              evidence_spans: Optional[List[EvidenceSpan]] = None,
                              config_path: Optional[str] = None) -> Tuple[bool, List[str]]:
    """
    Enforce section constraints for artifacts.
    
    Args:
        method_card: MethodCard to validate
        results_factsheet: ResultsFactsheet to validate
        evidence_spans: Evidence spans for context
        config_path: Path to configuration file
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    validator = SectionConstraintsValidator(config_path)
    is_valid, errors, warnings = validator.enforce_section_constraints(
        method_card, results_factsheet, evidence_spans
    )
    
    # Return hard errors only (warnings are logged but don't cause failure)
    return is_valid, errors
