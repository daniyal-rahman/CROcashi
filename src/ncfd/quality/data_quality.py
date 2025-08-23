"""
Comprehensive Data Quality Framework for CROcashi.

This module provides:
- Trial data validation
- Company data validation
- Data consistency checks
- Business rule validation
- Quality metrics and reporting
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Validation severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ValidationStatus(Enum):
    """Validation result status."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    SKIP = "SKIP"


@dataclass
class ValidationRule:
    """Data validation rule definition."""
    rule_id: str
    name: str
    description: str
    severity: ValidationSeverity
    category: str  # "trial", "company", "consistency", "business"
    
    # Rule parameters
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Rule metadata
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Set last_updated to current time."""
        self.last_updated = datetime.utcnow()


@dataclass
class ValidationResult:
    """Result of a validation rule execution."""
    rule_id: str
    rule_name: str
    status: ValidationStatus
    severity: ValidationSeverity
    message: str
    
    # Validation details
    field_name: Optional[str] = None
    expected_value: Optional[Any] = None
    actual_value: Optional[Any] = None
    
    # Metadata
    validated_at: datetime = field(default_factory=datetime.utcnow)
    execution_time_ms: float = 0.0
    
    # Context
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    source: Optional[str] = None


@dataclass
class QualityMetrics:
    """Data quality metrics for a dataset."""
    dataset_name: str
    total_records: int = 0
    validated_records: int = 0
    
    # Validation results
    passed_validations: int = 0
    failed_validations: int = 0
    warning_validations: int = 0
    skipped_validations: int = 0
    
    # Quality scores
    overall_quality_score: float = 0.0
    completeness_score: float = 0.0
    accuracy_score: float = 0.0
    consistency_score: float = 0.0
    
    # Severity breakdown
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0
    
    # Metadata
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    validation_duration_seconds: float = 0.0
    
    def __post_init__(self):
        """Calculate derived metrics."""
        if self.total_records > 0:
            self.overall_quality_score = self.passed_validations / (self.passed_validations + self.failed_validations)
            self.completeness_score = self.validated_records / self.total_records


class DataQualityFramework:
    """
    Comprehensive data quality framework for CROcashi.
    
    Features:
    - Rule-based validation
    - Multi-source data validation
    - Quality metrics calculation
    - Trend analysis and reporting
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the data quality framework.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Validation rules
        self.validation_rules: Dict[str, ValidationRule] = {}
        self.rule_categories: Dict[str, List[ValidationRule]] = {}
        
        # Quality metrics
        self.quality_history: List[QualityMetrics] = []
        
        # Configuration
        self.min_quality_score = config.get('min_quality_score', 0.6)
        self.max_error_rate = config.get('max_error_rate', 0.05)
        self.enable_auto_validation = config.get('enable_auto_validation', True)
        
        # Initialize validation rules
        self._initialize_validation_rules()
        
        self.logger.info("Data Quality Framework initialized")
    
    def _initialize_validation_rules(self):
        """Initialize built-in validation rules."""
        # Trial data validation rules
        trial_rules = [
            ValidationRule(
                rule_id="trial_required_fields",
                name="Required Trial Fields",
                description="Check that all required trial fields are present",
                severity=ValidationSeverity.CRITICAL,
                category="trial",
                parameters={"required_fields": ["nct_id", "brief_title", "sponsor_name", "phase"]}
            ),
            ValidationRule(
                rule_id="trial_phase_valid",
                name="Valid Trial Phase",
                description="Check that trial phase is a valid value",
                severity=ValidationSeverity.HIGH,
                category="trial",
                parameters={"valid_phases": ["PHASE1", "PHASE2", "PHASE3", "PHASE4", "PHASE2_PHASE3"]}
            ),
            ValidationRule(
                rule_id="trial_dates_consistent",
                name="Trial Date Consistency",
                description="Check that trial dates are logically consistent",
                severity=ValidationSeverity.MEDIUM,
                category="trial",
                parameters={"date_fields": ["study_start", "primary_completion", "study_completion"]}
            ),
            ValidationRule(
                rule_id="trial_enrollment_positive",
                name="Positive Enrollment",
                description="Check that enrollment numbers are positive",
                severity=ValidationSeverity.MEDIUM,
                category="trial",
                parameters={"enrollment_field": "enrollment_count"}
            )
        ]
        
        # Company data validation rules
        company_rules = [
            ValidationRule(
                rule_id="company_required_fields",
                name="Required Company Fields",
                description="Check that all required company fields are present",
                severity=ValidationSeverity.CRITICAL,
                category="company",
                parameters={"required_fields": ["cik", "company_name", "ticker"]}
            ),
            ValidationRule(
                rule_id="company_cik_format",
                name="Valid CIK Format",
                description="Check that CIK is a valid 10-digit number",
                severity=ValidationSeverity.HIGH,
                category="company",
                parameters={"cik_pattern": r"^\d{10}$"}
            ),
            ValidationRule(
                rule_id="company_ticker_format",
                name="Valid Ticker Format",
                description="Check that ticker symbol is valid",
                severity=ValidationSeverity.MEDIUM,
                category="company",
                parameters={"ticker_pattern": r"^[A-Z]{1,5}$"}
            )
        ]
        
        # Data consistency rules
        consistency_rules = [
            ValidationRule(
                rule_id="sponsor_company_link",
                name="Sponsor-Company Link",
                description="Check that trial sponsors link to valid companies",
                severity=ValidationSeverity.HIGH,
                category="consistency",
                parameters={"link_table": "company_trials"}
            ),
            ValidationRule(
                rule_id="trial_status_consistency",
                name="Trial Status Consistency",
                description="Check that trial status is consistent with dates",
                severity=ValidationSeverity.MEDIUM,
                category="consistency",
                parameters={"status_date_fields": ["status", "completion_date"]}
            ),
            ValidationRule(
                rule_id="enrollment_consistency",
                name="Enrollment Consistency",
                description="Check that enrollment numbers are consistent across sources",
                severity=ValidationSeverity.MEDIUM,
                category="consistency",
                parameters={"enrollment_sources": ["ctgov", "sec_filings"]}
            )
        ]
        
        # Business rule validation
        business_rules = [
            ValidationRule(
                rule_id="trial_phase_progression",
                name="Trial Phase Progression",
                description="Check that trial phases progress logically",
                severity=ValidationSeverity.MEDIUM,
                category="business",
                parameters={"phase_order": ["PHASE1", "PHASE2", "PHASE3", "PHASE4"]}
            ),
            ValidationRule(
                rule_id="enrollment_targets",
                name="Enrollment Target Validation",
                description="Check that enrollment targets are reasonable",
                severity=ValidationSeverity.LOW,
                category="business",
                parameters={"min_enrollment": 10, "max_enrollment": 100000}
            ),
            ValidationRule(
                rule_id="trial_duration",
                name="Trial Duration Validation",
                description="Check that trial durations are reasonable",
                severity=ValidationSeverity.LOW,
                category="business",
                parameters={"min_duration_days": 30, "max_duration_days": 3650}
            )
        ]
        
        # Add all rules
        all_rules = trial_rules + company_rules + consistency_rules + business_rules
        
        for rule in all_rules:
            self.add_validation_rule(rule)
    
    def add_validation_rule(self, rule: ValidationRule):
        """Add a validation rule to the framework."""
        self.validation_rules[rule.rule_id] = rule
        
        if rule.category not in self.rule_categories:
            self.rule_categories[rule.category] = []
        
        self.rule_categories[rule.category].append(rule)
        
        self.logger.info(f"Added validation rule: {rule.name} ({rule.category})")
    
    def remove_validation_rule(self, rule_id: str):
        """Remove a validation rule from the framework."""
        if rule_id in self.validation_rules:
            rule = self.validation_rules[rule_id]
            
            # Remove from categories
            if rule.category in self.rule_categories:
                self.rule_categories[rule.category] = [
                    r for r in self.rule_categories[rule.category] if r.rule_id != rule_id
                ]
            
            # Remove from main rules
            del self.validation_rules[rule_id]
            
            self.logger.info(f"Removed validation rule: {rule_id}")
    
    def validate_trial_data(self, trial_data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate trial data against all applicable rules."""
        results = []
        
        # Get trial validation rules
        trial_rules = self.rule_categories.get("trial", [])
        
        for rule in trial_rules:
            if not rule.enabled:
                continue
            
            try:
                result = self._execute_validation_rule(rule, trial_data)
                if result:
                    results.append(result)
                    
            except Exception as e:
                self.logger.error(f"Error executing rule {rule.rule_id}: {e}")
                # Create error result
                error_result = ValidationResult(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    status=ValidationStatus.FAIL,
                    severity=rule.severity,
                    message=f"Rule execution error: {e}",
                    entity_id=trial_data.get("nct_id"),
                    entity_type="trial",
                    source="validation_framework"
                )
                results.append(error_result)
        
        return results
    
    def validate_company_data(self, company_data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate company data against all applicable rules."""
        results = []
        
        # Get company validation rules
        company_rules = self.rule_categories.get("company", [])
        
        for rule in company_rules:
            if not rule.enabled:
                continue
            
            try:
                result = self._execute_validation_rule(rule, company_data)
                if result:
                    results.append(result)
                    
            except Exception as e:
                self.logger.error(f"Error executing rule {rule.rule_id}: {e}")
                # Create error result
                error_result = ValidationResult(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    status=ValidationStatus.FAIL,
                    severity=rule.severity,
                    message=f"Rule execution error: {e}",
                    entity_id=company_data.get("cik"),
                    entity_type="company",
                    source="validation_framework"
                )
                results.append(error_result)
        
        return results
    
    def validate_data_consistency(self, data_sources: Dict[str, Any]) -> List[ValidationResult]:
        """Validate data consistency across multiple sources."""
        results = []
        
        # Get consistency validation rules
        consistency_rules = self.rule_categories.get("consistency", [])
        
        for rule in consistency_rules:
            if not rule.enabled:
                continue
            
            try:
                result = self._execute_validation_rule(rule, data_sources)
                if result:
                    results.append(result)
                    
            except Exception as e:
                self.logger.error(f"Error executing rule {rule.rule_id}: {e}")
                # Create error result
                error_result = ValidationResult(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    status=ValidationStatus.FAIL,
                    severity=rule.severity,
                    message=f"Rule execution error: {e}",
                    source="validation_framework"
                )
                results.append(error_result)
        
        return results
    
    def _execute_validation_rule(self, rule: ValidationRule, data: Any) -> Optional[ValidationResult]:
        """Execute a specific validation rule."""
        start_time = datetime.utcnow()
        
        try:
            if rule.rule_id == "trial_required_fields":
                return self._validate_required_fields(rule, data)
            elif rule.rule_id == "trial_phase_valid":
                return self._validate_trial_phase(rule, data)
            elif rule.rule_id == "trial_dates_consistent":
                return self._validate_trial_dates(rule, data)
            elif rule.rule_id == "trial_enrollment_positive":
                return self._validate_enrollment_positive(rule, data)
            elif rule.rule_id == "company_required_fields":
                return self._validate_required_fields(rule, data)
            elif rule.rule_id == "company_cik_format":
                return self._validate_cik_format(rule, data)
            elif rule.rule_id == "company_ticker_format":
                return self._validate_ticker_format(rule, data)
            elif rule.rule_id == "sponsor_company_link":
                return self._validate_sponsor_company_link(rule, data)
            elif rule.rule_id == "trial_status_consistency":
                return self._validate_trial_status_consistency(rule, data)
            elif rule.rule_id == "enrollment_consistency":
                return self._validate_enrollment_consistency(rule, data)
            elif rule.rule_id == "trial_phase_progression":
                return self._validate_trial_phase_progression(rule, data)
            elif rule.rule_id == "enrollment_targets":
                return self._validate_enrollment_targets(rule, data)
            elif rule.rule_id == "trial_duration":
                return self._validate_trial_duration(rule, data)
            else:
                self.logger.warning(f"Unknown validation rule: {rule.rule_id}")
                return None
                
        finally:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Update execution time if result exists
            # This would be done in the specific validation methods
    
    def _validate_required_fields(self, rule: ValidationRule, data: Dict[str, Any]) -> ValidationResult:
        """Validate that required fields are present."""
        required_fields = rule.parameters.get("required_fields", [])
        missing_fields = []
        
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == "":
                missing_fields.append(field)
        
        if missing_fields:
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.FAIL,
                severity=rule.severity,
                message=f"Missing required fields: {', '.join(missing_fields)}",
                field_name=", ".join(missing_fields),
                expected_value="present",
                actual_value="missing"
            )
        else:
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.PASS,
                severity=rule.severity,
                message="All required fields present"
            )
    
    def _validate_trial_phase(self, rule: ValidationRule, data: Dict[str, Any]) -> ValidationResult:
        """Validate trial phase value."""
        valid_phases = rule.parameters.get("valid_phases", [])
        phase = data.get("phase")
        
        if not phase:
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.WARNING,
                severity=rule.severity,
                message="No phase information available",
                field_name="phase"
            )
        
        if phase not in valid_phases:
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.FAIL,
                severity=rule.severity,
                message=f"Invalid trial phase: {phase}",
                field_name="phase",
                expected_value=valid_phases,
                actual_value=phase
            )
        
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.PASS,
            severity=rule.severity,
            message=f"Valid trial phase: {phase}"
        )
    
    def _validate_trial_dates(self, rule: ValidationRule, data: Dict[str, Any]) -> ValidationResult:
        """Validate trial date consistency."""
        date_fields = rule.parameters.get("date_fields", [])
        
        # Get dates
        dates = {}
        for field in date_fields:
            date_value = data.get(field)
            if date_value:
                try:
                    if isinstance(date_value, str):
                        dates[field] = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    else:
                        dates[field] = date_value
                except:
                    pass
        
        if len(dates) < 2:
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.SKIP,
                severity=rule.severity,
                message="Insufficient date data for validation"
            )
        
        # Check date consistency
        issues = []
        if "study_start" in dates and "study_completion" in dates:
            if dates["study_start"] > dates["study_completion"]:
                issues.append("Study start date is after completion date")
        
        if "primary_completion" in dates and "study_completion" in dates:
            if dates["primary_completion"] > dates["study_completion"]:
                issues.append("Primary completion date is after study completion date")
        
        if issues:
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.FAIL,
                severity=rule.severity,
                message=f"Date consistency issues: {'; '.join(issues)}",
                field_name="dates"
            )
        
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.PASS,
            severity=rule.severity,
            message="All trial dates are consistent"
        )
    
    def _validate_enrollment_positive(self, rule: ValidationRule, data: Dict[str, Any]) -> ValidationResult:
        """Validate that enrollment numbers are positive."""
        enrollment_field = rule.parameters.get("enrollment_field", "enrollment_count")
        enrollment = data.get(enrollment_field)
        
        if enrollment is None:
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.SKIP,
                severity=rule.severity,
                message="No enrollment data available"
            )
        
        try:
            enrollment_num = int(enrollment)
            if enrollment_num <= 0:
                return ValidationResult(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    status=ValidationStatus.FAIL,
                    severity=rule.severity,
                    message=f"Enrollment number must be positive: {enrollment_num}",
                    field_name=enrollment_field,
                    expected_value="> 0",
                    actual_value=enrollment_num
                )
        except (ValueError, TypeError):
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.FAIL,
                severity=rule.severity,
                message=f"Invalid enrollment value: {enrollment}",
                field_name=enrollment_field,
                expected_value="positive integer",
                actual_value=enrollment
            )
        
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.PASS,
            severity=rule.severity,
            message=f"Valid enrollment number: {enrollment_num}"
        )
    
    def _validate_cik_format(self, rule: ValidationRule, data: Dict[str, Any]) -> ValidationResult:
        """Validate CIK format."""
        import re
        
        cik_pattern = rule.parameters.get("cik_pattern", r"^\d{10}$")
        cik = data.get("cik")
        
        if not cik:
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.FAIL,
                severity=rule.severity,
                message="No CIK provided",
                field_name="cik"
            )
        
        if not re.match(cik_pattern, str(cik)):
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.FAIL,
                severity=rule.severity,
                message=f"Invalid CIK format: {cik}",
                field_name="cik",
                expected_value="10-digit number",
                actual_value=cik
            )
        
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.PASS,
            severity=rule.severity,
            message=f"Valid CIK format: {cik}"
        )
    
    def _validate_ticker_format(self, rule: ValidationRule, data: Dict[str, Any]) -> ValidationResult:
        """Validate ticker symbol format."""
        import re
        
        ticker_pattern = rule.parameters.get("ticker_pattern", r"^[A-Z]{1,5}$")
        ticker = data.get("ticker")
        
        if not ticker:
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.SKIP,
                severity=rule.severity,
                message="No ticker symbol provided"
            )
        
        if not re.match(ticker_pattern, str(ticker)):
            return ValidationResult(
                rule_id=rule.rule_id,
                rule_name=rule.name,
                status=ValidationStatus.FAIL,
                severity=rule.severity,
                message=f"Invalid ticker format: {ticker}",
                field_name="ticker",
                expected_value="1-5 uppercase letters",
                actual_value=ticker
            )
        
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.PASS,
            severity=rule.severity,
            message=f"Valid ticker format: {ticker}"
        )
    
    def _validate_sponsor_company_link(self, rule: ValidationRule, data: Any) -> ValidationResult:
        """Validate sponsor-company link (placeholder)."""
        # TODO: Implement actual database lookup
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.SKIP,
            severity=rule.severity,
            message="Sponsor-company link validation not yet implemented"
        )
    
    def _validate_trial_status_consistency(self, rule: ValidationRule, data: Any) -> ValidationResult:
        """Validate trial status consistency (placeholder)."""
        # TODO: Implement actual validation logic
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.SKIP,
            severity=rule.severity,
            message="Trial status consistency validation not yet implemented"
        )
    
    def _validate_enrollment_consistency(self, rule: ValidationRule, data: Any) -> ValidationResult:
        """Validate enrollment consistency across sources (placeholder)."""
        # TODO: Implement actual validation logic
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.SKIP,
            severity=rule.severity,
            message="Enrollment consistency validation not yet implemented"
        )
    
    def _validate_trial_phase_progression(self, rule: ValidationRule, data: Any) -> ValidationResult:
        """Validate trial phase progression (placeholder)."""
        # TODO: Implement actual validation logic
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.SKIP,
            severity=rule.severity,
            message="Trial phase progression validation not yet implemented"
        )
    
    def _validate_enrollment_targets(self, rule: ValidationRule, data: Any) -> ValidationResult:
        """Validate enrollment targets (placeholder)."""
        # TODO: Implement actual validation logic
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.SKIP,
            severity=rule.severity,
            message="Enrollment target validation not yet implemented"
        )
    
    def _validate_trial_duration(self, rule: ValidationRule, data: Any) -> ValidationResult:
        """Validate trial duration (placeholder)."""
        # TODO: Implement actual validation logic
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.SKIP,
            severity=rule.severity,
            message="Trial duration validation not yet implemented"
        )
    
    def calculate_quality_metrics(self, validation_results: List[ValidationResult]) -> QualityMetrics:
        """Calculate quality metrics from validation results."""
        start_time = datetime.utcnow()
        
        metrics = QualityMetrics(
            dataset_name="validation_results",
            total_records=len(validation_results),
            validated_records=len(validation_results)
        )
        
        # Count validation results by status
        for result in validation_results:
            if result.status == ValidationStatus.PASS:
                metrics.passed_validations += 1
            elif result.status == ValidationStatus.FAIL:
                metrics.failed_validations += 1
            elif result.status == ValidationStatus.WARNING:
                metrics.warning_validations += 1
            elif result.status == ValidationStatus.SKIP:
                metrics.skipped_validations += 1
            
            # Count by severity
            if result.severity == ValidationSeverity.CRITICAL:
                metrics.critical_issues += 1
            elif result.severity == ValidationSeverity.HIGH:
                metrics.high_issues += 1
            elif result.severity == ValidationSeverity.MEDIUM:
                metrics.medium_issues += 1
            elif result.severity == ValidationSeverity.LOW:
                metrics.low_issues += 1
        
        # Calculate duration
        metrics.validation_duration_seconds = (datetime.utcnow() - start_time).total_seconds()
        
        # Store in history
        self.quality_history.append(metrics)
        
        return metrics
    
    def get_quality_trends(self, days: int = 30) -> Dict[str, Any]:
        """Get quality trends over the specified period."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        recent_metrics = [m for m in self.quality_history if m.calculated_at >= cutoff_date]
        
        if not recent_metrics:
            return {"error": "No quality data available for the specified period"}
        
        # Calculate trends
        trends = {
            "period_days": days,
            "total_datasets": len(recent_metrics),
            "average_quality_score": sum(m.overall_quality_score for m in recent_metrics) / len(recent_metrics),
            "quality_score_trend": "stable",  # TODO: Implement trend calculation
            "critical_issues_trend": "stable",  # TODO: Implement trend calculation
            "high_issues_trend": "stable"  # TODO: Implement trend calculation
        }
        
        return trends
    
    def generate_quality_report(self, format: str = "json") -> str:
        """Generate a comprehensive quality report."""
        if not self.quality_history:
            return "No quality data available"
        
        # Get latest metrics
        latest_metrics = self.quality_history[-1]
        
        # Get trends
        trends = self.get_quality_trends(30)
        
        # Generate report
        report_data = {
            "report_generated_at": datetime.utcnow().isoformat(),
            "latest_metrics": vars(latest_metrics),
            "trends": trends,
            "validation_rules": {
                rule_id: {
                    "name": rule.name,
                    "category": rule.category,
                    "severity": rule.severity.value,
                    "enabled": rule.enabled
                }
                for rule_id, rule in self.validation_rules.items()
            }
        }
        
        if format == "json":
            import json
            return json.dumps(report_data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported report format: {format}")
    
    def get_validation_rules(self, category: Optional[str] = None) -> List[ValidationRule]:
        """Get validation rules, optionally filtered by category."""
        if category:
            return self.rule_categories.get(category, [])
        return list(self.validation_rules.values())
    
    def enable_validation_rule(self, rule_id: str):
        """Enable a validation rule."""
        if rule_id in self.validation_rules:
            self.validation_rules[rule_id].enabled = True
            self.logger.info(f"Enabled validation rule: {rule_id}")
    
    def disable_validation_rule(self, rule_id: str):
        """Disable a validation rule."""
        if rule_id in self.validation_rules:
            self.validation_rules[rule_id].enabled = False
            self.logger.info(f"Disabled validation rule: {rule_id}")
    
    def clear_quality_history(self, keep_last: int = 100):
        """Clear quality history, keeping the last N entries."""
        if len(self.quality_history) > keep_last:
            self.quality_history = self.quality_history[-keep_last:]
            self.logger.info(f"Cleared quality history, keeping last {keep_last} entries")
