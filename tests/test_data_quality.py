"""
Unit tests for the Data Quality Framework.

Tests all validation rules, quality metrics calculation, and framework functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.ncfd.quality.data_quality import (
    DataQualityFramework, ValidationRule, ValidationResult, QualityMetrics,
    ValidationSeverity, ValidationStatus
)


class TestValidationRule:
    """Test ValidationRule class."""
    
    def test_validation_rule_creation(self):
        """Test creating a validation rule."""
        rule = ValidationRule(
            rule_id="test_rule",
            name="Test Rule",
            description="Test description",
            severity=ValidationSeverity.HIGH,
            category="test"
        )
        
        assert rule.rule_id == "test_rule"
        assert rule.name == "Test Rule"
        assert rule.severity == ValidationSeverity.HIGH
        assert rule.category == "test"
        assert rule.enabled is True
        assert rule.created_at is not None
        assert rule.last_updated is not None
    
    def test_validation_rule_parameters(self):
        """Test validation rule with parameters."""
        rule = ValidationRule(
            rule_id="test_rule",
            name="Test Rule",
            description="Test description",
            severity=ValidationSeverity.MEDIUM,
            category="test",
            parameters={"field": "value", "threshold": 0.8}
        )
        
        assert rule.parameters["field"] == "value"
        assert rule.parameters["threshold"] == 0.8


class TestValidationResult:
    """Test ValidationResult class."""
    
    def test_validation_result_creation(self):
        """Test creating a validation result."""
        result = ValidationResult(
            rule_id="test_rule",
            rule_name="Test Rule",
            status=ValidationStatus.PASS,
            severity=ValidationSeverity.HIGH,
            message="Test passed"
        )
        
        assert result.rule_id == "test_rule"
        assert result.status == ValidationStatus.PASS
        assert result.severity == ValidationSeverity.HIGH
        assert result.validated_at is not None
    
    def test_validation_result_with_context(self):
        """Test validation result with additional context."""
        result = ValidationResult(
            rule_id="test_rule",
            rule_name="Test Rule",
            status=ValidationStatus.FAIL,
            severity=ValidationSeverity.CRITICAL,
            message="Test failed",
            field_name="test_field",
            expected_value="expected",
            actual_value="actual",
            entity_id="test_entity",
            entity_type="test_type"
        )
        
        assert result.field_name == "test_field"
        assert result.expected_value == "expected"
        assert result.actual_value == "actual"
        assert result.entity_id == "test_entity"
        assert result.entity_type == "test_type"


class TestQualityMetrics:
    """Test QualityMetrics class."""
    
    def test_quality_metrics_creation(self):
        """Test creating quality metrics."""
        metrics = QualityMetrics(
            dataset_name="test_dataset",
            total_records=100,
            validated_records=95
        )
        
        assert metrics.dataset_name == "test_dataset"
        assert metrics.total_records == 100
        assert metrics.validated_records == 95
        assert metrics.calculated_at is not None
    
    def test_quality_metrics_calculation(self):
        """Test quality metrics calculation."""
        metrics = QualityMetrics(
            dataset_name="test_dataset",
            total_records=100,
            validated_records=100,
            passed_validations=80,
            failed_validations=20
        )
        
        assert metrics.overall_quality_score == 0.8  # 80/(80+20)
        assert metrics.completeness_score == 1.0     # 100/100


class TestDataQualityFramework:
    """Test DataQualityFramework class."""
    
    @pytest.fixture
    def framework(self):
        """Create a test framework instance."""
        config = {
            'min_quality_score': 0.6,
            'max_error_rate': 0.05,
            'enable_auto_validation': True
        }
        return DataQualityFramework(config)
    
    def test_framework_initialization(self, framework):
        """Test framework initialization."""
        assert framework.min_quality_score == 0.6
        assert framework.max_error_rate == 0.05
        assert framework.enable_auto_validation is True
        assert len(framework.validation_rules) > 0
        assert len(framework.rule_categories) > 0
    
    def test_validation_rules_categories(self, framework):
        """Test that validation rules are properly categorized."""
        expected_categories = ["trial", "company", "consistency", "business"]
        
        for category in expected_categories:
            assert category in framework.rule_categories
            assert len(framework.rule_categories[category]) > 0
    
    def test_add_validation_rule(self, framework):
        """Test adding a custom validation rule."""
        custom_rule = ValidationRule(
            rule_id="custom_rule",
            name="Custom Rule",
            description="Custom validation rule",
            severity=ValidationSeverity.LOW,
            category="custom"
        )
        
        framework.add_validation_rule(custom_rule)
        
        assert "custom_rule" in framework.validation_rules
        assert custom_rule in framework.rule_categories["custom"]
    
    def test_remove_validation_rule(self, framework):
        """Test removing a validation rule."""
        rule_id = "trial_required_fields"
        assert rule_id in framework.validation_rules
        
        framework.remove_validation_rule(rule_id)
        
        assert rule_id not in framework.validation_rules
        assert rule_id not in [r.rule_id for r in framework.rule_categories["trial"]]
    
    def test_validate_trial_data(self, framework):
        """Test trial data validation."""
        trial_data = {
            "nct_id": "NCT12345678",
            "brief_title": "Test Trial",
            "sponsor_name": "Test Sponsor",
            "phase": "PHASE2",
            "study_start": "2023-01-01",
            "study_completion": "2024-01-01",
            "enrollment_count": 100
        }
        
        results = framework.validate_trial_data(trial_data)
        
        assert len(results) > 0
        
        # Check that required fields validation passed
        required_fields_result = next(
            (r for r in results if r.rule_id == "trial_required_fields"), None
        )
        assert required_fields_result is not None
        assert required_fields_result.status == ValidationStatus.PASS
    
    def test_validate_trial_data_missing_fields(self, framework):
        """Test trial data validation with missing required fields."""
        trial_data = {
            "nct_id": "NCT12345678",
            # Missing brief_title, sponsor_name, phase
            "enrollment_count": 100
        }
        
        results = framework.validate_trial_data(trial_data)
        
        # Check that required fields validation failed
        required_fields_result = next(
            (r for r in results if r.rule_id == "trial_required_fields"), None
        )
        assert required_fields_result is not None
        assert required_fields_result.status == ValidationStatus.FAIL
    
    def test_validate_trial_data_invalid_phase(self, framework):
        """Test trial data validation with invalid phase."""
        trial_data = {
            "nct_id": "NCT12345678",
            "brief_title": "Test Trial",
            "sponsor_name": "Test Sponsor",
            "phase": "INVALID_PHASE",
            "enrollment_count": 100
        }
        
        results = framework.validate_trial_data(trial_data)
        
        # Check that phase validation failed
        phase_result = next(
            (r for r in results if r.rule_id == "trial_phase_valid"), None
        )
        assert phase_result is not None
        assert phase_result.status == ValidationStatus.FAIL
    
    def test_validate_trial_data_inconsistent_dates(self, framework):
        """Test trial data validation with inconsistent dates."""
        trial_data = {
            "nct_id": "NCT12345678",
            "brief_title": "Test Trial",
            "sponsor_name": "Test Sponsor",
            "phase": "PHASE2",
            "study_start": "2024-01-01",  # After completion
            "study_completion": "2023-01-01",
            "enrollment_count": 100
        }
        
        results = framework.validate_trial_data(trial_data)
        
        # Check that date consistency validation failed
        date_result = next(
            (r for r in results if r.rule_id == "trial_dates_consistent"), None
        )
        assert date_result is not None
        assert date_result.status == ValidationStatus.FAIL
    
    def test_validate_trial_data_negative_enrollment(self, framework):
        """Test trial data validation with negative enrollment."""
        trial_data = {
            "nct_id": "NCT12345678",
            "brief_title": "Test Trial",
            "sponsor_name": "Test Sponsor",
            "phase": "PHASE2",
            "enrollment_count": -50
        }
        
        results = framework.validate_trial_data(trial_data)
        
        # Check that enrollment validation failed
        enrollment_result = next(
            (r for r in results if r.rule_id == "trial_enrollment_positive"), None
        )
        assert enrollment_result is not None
        assert enrollment_result.status == ValidationStatus.FAIL
    
    def test_validate_company_data(self, framework):
        """Test company data validation."""
        company_data = {
            "cik": "0001234567",
            "company_name": "Test Company",
            "ticker": "TEST"
        }
        
        results = framework.validate_company_data(company_data)
        
        assert len(results) > 0
        
        # Check that required fields validation passed
        required_fields_result = next(
            (r for r in results if r.rule_id == "company_required_fields"), None
        )
        assert required_fields_result is not None
        assert required_fields_result.status == ValidationStatus.PASS
    
    def test_validate_company_data_invalid_cik(self, framework):
        """Test company data validation with invalid CIK."""
        company_data = {
            "cik": "123",  # Too short
            "company_name": "Test Company",
            "ticker": "TEST"
        }
        
        results = framework.validate_company_data(company_data)
        
        # Check that CIK validation failed
        cik_result = next(
            (r for r in results if r.rule_id == "company_cik_format"), None
        )
        assert cik_result is not None
        assert cik_result.status == ValidationStatus.FAIL
    
    def test_validate_company_data_invalid_ticker(self, framework):
        """Test company data validation with invalid ticker."""
        company_data = {
            "cik": "0001234567",
            "company_name": "Test Company",
            "ticker": "test"  # Lowercase
        }
        
        results = framework.validate_company_data(company_data)
        
        # Check that ticker validation failed
        ticker_result = next(
            (r for r in results if r.rule_id == "company_ticker_format"), None
        )
        assert ticker_result is not None
        assert ticker_result.status == ValidationStatus.FAIL
    
    def test_validate_data_consistency(self, framework):
        """Test data consistency validation."""
        data_sources = {
            "ctgov": {"enrollment": 100},
            "sec_filings": {"enrollment": 100}
        }
        
        results = framework.validate_data_consistency(data_sources)
        
        # Note: Most consistency rules are placeholders, so they should return SKIP
        assert len(results) > 0
        for result in results:
            assert result.status in [ValidationStatus.SKIP, ValidationStatus.PASS]
    
    def test_calculate_quality_metrics(self, framework):
        """Test quality metrics calculation."""
        validation_results = [
            ValidationResult(
                rule_id="rule1",
                rule_name="Rule 1",
                status=ValidationStatus.PASS,
                severity=ValidationSeverity.HIGH,
                message="Passed"
            ),
            ValidationResult(
                rule_id="rule2",
                rule_name="Rule 2",
                status=ValidationStatus.FAIL,
                severity=ValidationSeverity.CRITICAL,
                message="Failed"
            ),
            ValidationResult(
                rule_id="rule3",
                rule_name="Rule 3",
                status=ValidationStatus.WARNING,
                severity=ValidationSeverity.MEDIUM,
                message="Warning"
            )
        ]
        
        metrics = framework.calculate_quality_metrics(validation_results)
        
        assert metrics.total_records == 3
        assert metrics.validated_records == 3
        assert metrics.passed_validations == 1
        assert metrics.failed_validations == 1
        assert metrics.warning_validations == 1
        assert metrics.overall_quality_score == 0.5  # 1/(1+1)
        assert metrics.critical_issues == 1
        assert metrics.high_issues == 1
        assert metrics.medium_issues == 1
    
    def test_get_quality_trends(self, framework):
        """Test quality trends calculation."""
        # Add some historical metrics
        for i in range(5):
            metrics = QualityMetrics(
                dataset_name=f"dataset_{i}",
                total_records=100,
                validated_records=100,
                passed_validations=80 + i * 2,  # Improving quality
                failed_validations=20 - i * 2
            )
            metrics.calculated_at = datetime.utcnow() - timedelta(days=i)
            framework.quality_history.append(metrics)
        
        trends = framework.get_quality_trends(days=7)
        
        assert trends['period_days'] == 7
        assert trends['total_datasets'] == 5
        assert trends['average_quality_score'] > 0.8  # Should be high due to improvement
    
    def test_generate_quality_report(self, framework):
        """Test quality report generation."""
        # Add some metrics first
        metrics = QualityMetrics(
            dataset_name="test_dataset",
            total_records=100,
            validated_records=100,
            passed_validations=90,
            failed_validations=10
        )
        framework.quality_history.append(metrics)
        
        report = framework.generate_quality_report()
        
        assert "report_generated_at" in report
        assert "latest_metrics" in report
        assert "trends" in report
        assert "validation_rules" in report
    
    def test_enable_disable_validation_rule(self, framework):
        """Test enabling and disabling validation rules."""
        rule_id = "trial_required_fields"
        
        # Initially enabled
        assert framework.validation_rules[rule_id].enabled is True
        
        # Disable
        framework.disable_validation_rule(rule_id)
        assert framework.validation_rules[rule_id].enabled is False
        
        # Enable
        framework.enable_validation_rule(rule_id)
        assert framework.validation_rules[rule_id].enabled is True
    
    def test_get_validation_rules_filtered(self, framework):
        """Test getting validation rules filtered by category."""
        trial_rules = framework.get_validation_rules("trial")
        company_rules = framework.get_validation_rules("company")
        
        assert len(trial_rules) > 0
        assert len(company_rules) > 0
        
        for rule in trial_rules:
            assert rule.category == "trial"
        
        for rule in company_rules:
            assert rule.category == "company"
    
    def test_clear_quality_history(self, framework):
        """Test clearing quality history."""
        # Add some metrics
        for i in range(15):
            metrics = QualityMetrics(
                dataset_name=f"dataset_{i}",
                total_records=100,
                validated_records=100,
                passed_validations=80,
                failed_validations=20
            )
            framework.quality_history.append(metrics)
        
        assert len(framework.quality_history) == 15
        
        # Clear, keeping last 10
        framework.clear_quality_history(keep_last=10)
        
        assert len(framework.quality_history) == 10
    
    def test_export_events(self, framework):
        """Test events export functionality."""
        # Add some metrics first
        metrics = QualityMetrics(
            dataset_name="test_dataset",
            total_records=100,
            validated_records=100,
            passed_validations=90,
            failed_validations=10
        )
        framework.quality_history.append(metrics)
        
        export = framework.export_events("json")
        
        assert "exported_at" in export
        assert "trial_events" in export
        assert "clinical_updates" in export
    
    def test_export_events_invalid_format(self, framework):
        """Test events export with invalid format."""
        with pytest.raises(ValueError, match="Unsupported export format"):
            framework.export_events("invalid_format")


class TestDataQualityFrameworkIntegration:
    """Integration tests for the data quality framework."""
    
    @pytest.fixture
    def framework(self):
        """Create a test framework instance."""
        config = {
            'min_quality_score': 0.6,
            'max_error_rate': 0.05,
            'enable_auto_validation': True
        }
        return DataQualityFramework(config)
    
    def test_end_to_end_validation_workflow(self, framework):
        """Test complete validation workflow."""
        # Test data
        trial_data = {
            "nct_id": "NCT12345678",
            "brief_title": "Test Trial",
            "sponsor_name": "Test Sponsor",
            "phase": "PHASE2",
            "study_start": "2023-01-01",
            "study_completion": "2024-01-01",
            "enrollment_count": 100
        }
        
        company_data = {
            "cik": "0001234567",
            "company_name": "Test Company",
            "ticker": "TEST"
        }
        
        # Validate trial data
        trial_results = framework.validate_trial_data(trial_data)
        
        # Validate company data
        company_results = framework.validate_company_data(company_data)
        
        # Validate consistency
        consistency_results = framework.validate_data_consistency({
            "trial": trial_data,
            "company": company_data
        })
        
        # Combine all results
        all_results = trial_results + company_results + consistency_results
        
        # Calculate quality metrics
        metrics = framework.calculate_quality_metrics(all_results)
        
        # Generate report
        report = framework.generate_quality_report()
        
        # Assertions
        assert len(trial_results) > 0
        assert len(company_results) > 0
        assert len(consistency_results) > 0
        assert metrics.total_records > 0
        assert "report_generated_at" in report
    
    def test_validation_rule_management(self, framework):
        """Test complete validation rule management workflow."""
        # Create custom rule
        custom_rule = ValidationRule(
            rule_id="custom_test_rule",
            name="Custom Test Rule",
            description="Custom validation rule for testing",
            severity=ValidationSeverity.LOW,
            category="custom",
            parameters={"threshold": 0.5}
        )
        
        # Add rule
        framework.add_validation_rule(custom_rule)
        assert "custom_test_rule" in framework.validation_rules
        
        # Test rule execution (should be skipped as it's not implemented)
        test_data = {"test_field": "test_value"}
        results = framework.validate_data_consistency(test_data)
        
        # Remove rule
        framework.remove_validation_rule("custom_test_rule")
        assert "custom_test_rule" not in framework.validation_rules


if __name__ == "__main__":
    pytest.main([__file__])
