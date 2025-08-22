"""Field Validation System for Study Card Quality Assessment."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime
import re
from enum import Enum

from .extractor import ExtractedField, ExtractionStatus, FieldType


class ValidationLevel(Enum):
    """Levels of validation severity."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationRule(Enum):
    """Types of validation rules."""
    REQUIRED_FIELD = "required_field"
    FIELD_FORMAT = "field_format"
    FIELD_RANGE = "field_range"
    FIELD_CONSISTENCY = "field_consistency"
    EVIDENCE_PRESENCE = "evidence_presence"
    DATA_QUALITY = "data_quality"


@dataclass
class ValidationIssue:
    """A validation issue found during field validation."""
    field_name: str
    field_path: str
    rule_type: ValidationRule
    level: ValidationLevel
    message: str
    suggestion: Optional[str] = None
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class FieldValidationResult:
    """Result of field validation for a study card."""
    study_id: int
    trial_id: int
    validation_issues: List[ValidationIssue] = field(default_factory=list)
    validation_summary: Dict[str, Any] = field(default_factory=dict)
    overall_quality_score: float = 0.0
    validated_at: datetime = field(default_factory=datetime.now)


class StudyCardFieldValidator:
    """Validates extracted fields for quality and consistency."""
    
    # Validation rules for different field types
    VALIDATION_RULES = {
        # Trial Information Validation
        "nct_id": {
            "format": r"^NCT\d{8}$",
            "required": True,
            "description": "NCT ID must be in format NCT followed by 8 digits"
        },
        "phase": {
            "allowed_values": ["1", "2", "3", "4", "1/2", "2/3", "1b", "2a", "2b"],
            "required": True,
            "description": "Trial phase must be a valid phase designation"
        },
        "indication": {
            "min_length": 3,
            "max_length": 200,
            "required": True,
            "description": "Indication must be 3-200 characters"
        },
        "is_pivotal": {
            "type": bool,
            "required": True,
            "description": "Pivotal status must be boolean"
        },
        
        # Endpoint Validation
        "primary_endpoints": {
            "min_count": 1,
            "required": True,
            "description": "Must have at least one primary endpoint"
        },
        "endpoint_evidence": {
            "min_evidence": 1,
            "required": True,
            "description": "Each endpoint must have evidence"
        },
        
        # Population Validation
        "itt_population": {
            "required": True,
            "description": "ITT population must be defined"
        },
        "population_consistency": {
            "rule": "itt_pp_consistency",
            "description": "ITT and PP populations must be consistent"
        },
        
        # Results Validation
        "primary_results": {
            "min_count": 1,
            "required": True,
            "description": "Must have primary results"
        },
        "result_evidence": {
            "min_evidence": 1,
            "required": True,
            "description": "Each result must have evidence"
        },
        
        # Statistical Validation
        "sample_size": {
            "min_value": 1,
            "required": True,
            "description": "Sample size must be positive"
        },
        "power_calculation": {
            "min_value": 0.5,
            "max_value": 1.0,
            "description": "Power must be between 0.5 and 1.0"
        },
        
        # Evidence Validation
        "evidence_location": {
            "required": True,
            "description": "Evidence must have location information"
        },
        "evidence_text": {
            "min_length": 10,
            "description": "Evidence text must be at least 10 characters"
        }
    }
    
    def __init__(self):
        """Initialize the field validator."""
        self.issue_counters = {
            ValidationLevel.INFO: 0,
            ValidationLevel.WARNING: 0,
            ValidationLevel.ERROR: 0,
            ValidationLevel.CRITICAL: 0
        }
    
    def validate_extracted_fields(self, extracted_fields: Dict[str, ExtractedField], study_id: int, trial_id: int) -> FieldValidationResult:
        """
        Validate all extracted fields for quality and consistency.
        
        Args:
            extracted_fields: Dictionary of extracted fields
            study_id: Study ID
            trial_id: Trial ID
            
        Returns:
            FieldValidationResult with validation issues and quality score
        """
        validation_issues = []
        
        # Reset issue counters
        for level in ValidationLevel:
            self.issue_counters[level] = 0
        
        try:
            # Validate individual fields
            for field_name, field_data in extracted_fields.items():
                field_issues = self._validate_single_field(field_name, field_data)
                validation_issues.extend(field_issues)
            
            # Validate field consistency across categories
            consistency_issues = self._validate_field_consistency(extracted_fields)
            validation_issues.extend(consistency_issues)
            
            # Validate evidence quality
            evidence_issues = self._validate_evidence_quality(extracted_fields)
            validation_issues.extend(evidence_issues)
            
            # Generate validation summary
            validation_summary = self._generate_validation_summary(validation_issues)
            
            # Calculate overall quality score
            overall_quality_score = self._calculate_quality_score(validation_issues, extracted_fields)
            
            return FieldValidationResult(
                study_id=study_id,
                trial_id=trial_id,
                validation_issues=validation_issues,
                validation_summary=validation_summary,
                overall_quality_score=overall_quality_score
            )
            
        except Exception as e:
            # Add critical validation error
            validation_issues.append(ValidationIssue(
                field_name="validation_system",
                field_path="system",
                rule_type=ValidationRule.DATA_QUALITY,
                level=ValidationLevel.CRITICAL,
                message=f"Critical validation error: {str(e)}"
            ))
            
            return FieldValidationResult(
                study_id=study_id,
                trial_id=trial_id,
                validation_issues=validation_issues,
                validation_summary={"error": "Validation system failure"},
                overall_quality_score=0.0
            )
    
    def _validate_single_field(self, field_name: str, field_data: ExtractedField) -> List[ValidationIssue]:
        """Validate a single extracted field."""
        issues = []
        
        # Check if field is missing when required
        if field_data.extraction_status == ExtractionStatus.MISSING:
            if self._is_field_required(field_name):
                issues.append(ValidationIssue(
                    field_name=field_name,
                    field_path=field_data.field_path,
                    rule_type=ValidationRule.REQUIRED_FIELD,
                    level=ValidationLevel.ERROR,
                    message=f"Required field '{field_name}' is missing",
                    suggestion="Extract this field from the source document"
                ))
                self.issue_counters[ValidationLevel.ERROR] += 1
        
        # Check field format and content
        if field_data.value is not None:
            format_issues = self._validate_field_format(field_name, field_data)
            issues.extend(format_issues)
        
        # Check evidence presence for complex fields
        if field_data.field_type in [FieldType.ARRAY, FieldType.OBJECT]:
            evidence_issues = self._validate_field_evidence(field_name, field_data)
            issues.extend(evidence_issues)
        
        return issues
    
    def _validate_field_format(self, field_name: str, field_data: ExtractedField) -> List[ValidationIssue]:
        """Validate field format and content."""
        issues = []
        
        if field_name == "nct_id":
            if not self._validate_nct_format(field_data.value):
                issues.append(ValidationIssue(
                    field_name=field_name,
                    field_path=field_data.field_path,
                    rule_type=ValidationRule.FIELD_FORMAT,
                    level=ValidationLevel.ERROR,
                    message="Invalid NCT ID format",
                    suggestion="NCT ID should be in format NCT followed by 8 digits"
                ))
                self.issue_counters[ValidationLevel.ERROR] += 1
        
        elif field_name == "phase":
            if not self._validate_phase_value(field_data.value):
                issues.append(ValidationIssue(
                    field_name=field_name,
                    field_path=field_data.field_path,
                    rule_type=ValidationRule.FIELD_FORMAT,
                    level=ValidationLevel.WARNING,
                    message="Unusual trial phase value",
                    suggestion="Verify phase designation is correct"
                ))
                self.issue_counters[ValidationLevel.WARNING] += 1
        
        elif field_name == "indication":
            if not self._validate_indication_length(field_data.value):
                issues.append(ValidationIssue(
                    field_name=field_name,
                    field_path=field_data.field_path,
                    rule_type=ValidationRule.FIELD_FORMAT,
                    level=ValidationLevel.WARNING,
                    message="Indication text may be too short or too long",
                    suggestion="Ensure indication is descriptive but concise"
                ))
                self.issue_counters[ValidationLevel.WARNING] += 1
        
        elif field_name == "sample_size":
            if not self._validate_sample_size(field_data.value):
                issues.append(ValidationIssue(
                    field_name=field_name,
                    field_path=field_data.field_path,
                    rule_type=ValidationRule.FIELD_RANGE,
                    level=ValidationLevel.ERROR,
                    message="Invalid sample size value",
                    suggestion="Sample size must be a positive integer"
                ))
                self.issue_counters[ValidationLevel.ERROR] += 1
        
        elif field_name == "power_calculation":
            if not self._validate_power_value(field_data.value):
                issues.append(ValidationIssue(
                    field_name=field_name,
                    field_path=field_data.field_path,
                    rule_type=ValidationRule.FIELD_RANGE,
                    level=ValidationLevel.WARNING,
                    message="Power calculation outside expected range",
                    suggestion="Power should typically be between 0.7 and 0.95"
                ))
                self.issue_counters[ValidationLevel.WARNING] += 1
        
        return issues
    
    def _validate_field_evidence(self, field_name: str, field_data: ExtractedField) -> List[ValidationIssue]:
        """Validate evidence presence for complex fields."""
        issues = []
        
        if field_name in ["primary_endpoints", "primary_results"]:
            if not field_data.evidence_spans:
                issues.append(ValidationIssue(
                    field_name=field_name,
                    field_path=field_data.field_path,
                    rule_type=ValidationRule.EVIDENCE_PRESENCE,
                    level=ValidationLevel.WARNING,
                    message=f"No evidence spans found for {field_name}",
                    suggestion="Extract evidence locations and text previews"
                ))
                self.issue_counters[ValidationLevel.WARNING] += 1
        
        return issues
    
    def _validate_field_consistency(self, extracted_fields: Dict[str, ExtractedField]) -> List[ValidationIssue]:
        """Validate consistency between related fields."""
        issues = []
        
        # Check ITT vs PP population consistency
        itt_field = extracted_fields.get("itt_definition")
        pp_field = extracted_fields.get("pp_definition")
        analysis_field = extracted_fields.get("analysis_population")
        
        if itt_field and pp_field and analysis_field:
            if analysis_field.value == "PP" and itt_field.value and pp_field.value:
                # Check if PP population is properly defined
                if not self._validate_pp_definition(pp_field.value):
                    issues.append(ValidationIssue(
                        field_name="population_consistency",
                        field_path="populations",
                        rule_type=ValidationRule.FIELD_CONSISTENCY,
                        level=ValidationLevel.WARNING,
                        message="PP population analysis without proper PP definition",
                        suggestion="Ensure PP population is clearly defined when used for primary analysis"
                    ))
                    self.issue_counters[ValidationLevel.WARNING] += 1
        
        # Check endpoint and result consistency
        endpoints_field = extracted_fields.get("primary_endpoints")
        results_field = extracted_fields.get("primary_results")
        
        if endpoints_field and results_field:
            if endpoints_field.value and results_field.value:
                endpoint_count = len(endpoints_field.value) if isinstance(endpoints_field.value, list) else 0
                result_count = len(results_field.value) if isinstance(results_field.value, list) else 0
                
                if endpoint_count != result_count:
                    issues.append(ValidationIssue(
                        field_name="endpoint_result_consistency",
                        field_path="endpoints_results",
                        rule_type=ValidationRule.FIELD_CONSISTENCY,
                        level=ValidationLevel.WARNING,
                        message=f"Mismatch between endpoints ({endpoint_count}) and results ({result_count})",
                        suggestion="Ensure each primary endpoint has a corresponding result"
                    ))
                    self.issue_counters[ValidationLevel.WARNING] += 1
        
        return issues
    
    def _validate_evidence_quality(self, extracted_fields: Dict[str, ExtractedField]) -> List[ValidationIssue]:
        """Validate evidence quality across all fields."""
        issues = []
        
        total_evidence_spans = 0
        low_quality_evidence = 0
        
        for field_data in extracted_fields.values():
            if field_data.evidence_spans:
                total_evidence_spans += len(field_data.evidence_spans)
                
                for evidence in field_data.evidence_spans:
                    if not self._is_evidence_high_quality(evidence):
                        low_quality_evidence += 1
        
        if total_evidence_spans > 0:
            quality_ratio = low_quality_evidence / total_evidence_spans
            
            if quality_ratio > 0.3:
                issues.append(ValidationIssue(
                    field_name="evidence_quality",
                    field_path="evidence",
                    rule_type=ValidationRule.EVIDENCE_PRESENCE,
                    level=ValidationLevel.WARNING,
                    message=f"Low quality evidence detected ({quality_ratio:.1%})",
                    suggestion="Improve evidence extraction with better location and text data"
                ))
                self.issue_counters[ValidationLevel.WARNING] += 1
        
        return issues
    
    def _is_field_required(self, field_name: str) -> bool:
        """Check if a field is required based on validation rules."""
        if field_name in self.VALIDATION_RULES:
            return self.VALIDATION_RULES[field_name].get("required", False)
        return False
    
    def _validate_nct_format(self, value: Any) -> bool:
        """Validate NCT ID format."""
        if not isinstance(value, str):
            return False
        return bool(re.match(r"^NCT\d{8}$", value))
    
    def _validate_phase_value(self, value: Any) -> bool:
        """Validate trial phase value."""
        if not isinstance(value, str):
            return False
        allowed_phases = ["1", "2", "3", "4", "1/2", "2/3", "1b", "2a", "2b"]
        return value in allowed_phases
    
    def _validate_indication_length(self, value: Any) -> bool:
        """Validate indication text length."""
        if not isinstance(value, str):
            return False
        return 3 <= len(value.strip()) <= 200
    
    def _validate_sample_size(self, value: Any) -> bool:
        """Validate sample size value."""
        if isinstance(value, dict) and "total_n" in value:
            value = value["total_n"]
        
        if isinstance(value, (int, float)):
            return value > 0
        return False
    
    def _validate_power_value(self, value: Any) -> bool:
        """Validate power calculation value."""
        if isinstance(value, (int, float)):
            return 0.5 <= value <= 1.0
        return False
    
    def _validate_pp_definition(self, pp_value: Any) -> bool:
        """Validate PP population definition."""
        if isinstance(pp_value, dict):
            required_keys = ["defined", "criteria"]
            return all(key in pp_value and pp_value[key] for key in required_keys)
        return False
    
    def _is_evidence_high_quality(self, evidence: Dict[str, Any]) -> bool:
        """Check if evidence span is high quality."""
        evidence_type = evidence.get("evidence_type", "")
        value = evidence.get("value", "")
        
        if evidence_type == "loc":
            return bool(value and len(str(value)) > 0)
        elif evidence_type == "text_preview":
            return bool(value and len(str(value)) > 10)
        elif evidence_type == "source":
            return bool(value and len(str(value)) > 0)
        
        return False
    
    def _generate_validation_summary(self, validation_issues: List[ValidationIssue]) -> Dict[str, Any]:
        """Generate summary statistics for validation issues."""
        total_issues = len(validation_issues)
        
        # Count issues by level
        level_counts = {
            level.value: self.issue_counters[level] for level in ValidationLevel
        }
        
        # Count issues by rule type
        rule_counts = {}
        for issue in validation_issues:
            rule_type = issue.rule_type.value
            rule_counts[rule_type] = rule_counts.get(rule_type, 0) + 1
        
        # Calculate quality metrics
        critical_issues = level_counts.get("critical", 0)
        error_issues = level_counts.get("error", 0)
        warning_issues = level_counts.get("warning", 0)
        
        # Quality score calculation (0-100)
        base_score = 100
        critical_penalty = critical_issues * 25
        error_penalty = error_issues * 10
        warning_penalty = warning_issues * 2
        
        quality_score = max(0, base_score - critical_penalty - error_penalty - warning_penalty)
        
        return {
            "total_issues": total_issues,
            "level_counts": level_counts,
            "rule_counts": rule_counts,
            "critical_issues": critical_issues,
            "error_issues": error_issues,
            "warning_issues": warning_issues,
            "info_issues": level_counts.get("info", 0),
            "quality_score": quality_score,
            "quality_grade": self._score_to_grade(quality_score)
        }
    
    def _score_to_grade(self, score: float) -> str:
        """Convert quality score to letter grade."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"
    
    def _calculate_quality_score(self, validation_issues: List[ValidationIssue], extracted_fields: Dict[str, ExtractedField]) -> float:
        """Calculate overall quality score based on validation and extraction."""
        # Start with validation quality score
        validation_summary = self._generate_validation_summary(validation_issues)
        validation_score = validation_summary["quality_score"]
        
        # Adjust based on field extraction completeness
        if extracted_fields:
            total_fields = len(extracted_fields)
            extracted_count = sum(1 for f in extracted_fields.values() if f.extraction_status == ExtractionStatus.EXTRACTED)
            partial_count = sum(1 for f in extracted_fields.values() if f.extraction_status == ExtractionStatus.PARTIAL)
            
            completeness_score = (extracted_count + partial_count * 0.5) / total_fields * 100
            
            # Weighted combination: 70% validation, 30% completeness
            final_score = validation_score * 0.7 + completeness_score * 0.3
        else:
            final_score = validation_score
        
        return min(100.0, max(0.0, final_score))
