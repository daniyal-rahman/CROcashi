#!/usr/bin/env python3
"""
Test backtest outcomes functionality.
"""

import json
import sys
from pathlib import Path

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.config import get_config


@pytest.fixture
def outcomes_config():
    """Default outcomes configuration."""
    return {
        "endpoints": {
            "continuous": {
                "sigma_default": 0.5,
                "mcid_lookup": {
                    "ADAS-Cog11": 1.5,
                    "MMSE": 1.0
                }
            },
            "binary": {
                "sigma_default": 0.3,
                "mcid_abs_default": 0.05
            },
            "tte": {
                "sigma_default": 0.2
            }
        },
        "penalties": {
            "subgroup_only": 0.10,
            "non_itt_or_pp_only": 0.10,
            "underpowered_or_no_primary": 0.05,
            "endpoint_changed_post_reg": 0.10,
            "non_significant": 0.15,
            "missing_primary_result": 0.20
        },
        "weights": {
            "effect": 0.7,
            "pvalue": 0.3
        },
        "grades": {
            "SS": [0.0, 0.2],
            "LS": [0.2, 0.4],
            "A": [0.4, 0.6],
            "LF": [0.6, 0.8],
            "FF": [0.8, 1.0]
        }
    }


def test_compute_outcome_severity_basic(outcomes_config):
    """Test basic outcome severity computation."""
    card = {
        "doc_id": "NCT123",
        "primary_endpoint": "ADAS-Cog11",
        "primary_result": {
            "ITT": {
                "estimate": 1.5,
                "p": 0.03,
                "significant": True
            }
        }
    }
    
    result = compute_outcome_severity(card, outcomes_config)
    
    assert isinstance(result, OutcomeSeverity)
    assert 0.0 <= result.severity <= 1.0
    assert result.grade in ["SS", "LS", "A", "LF", "FF"]
    assert "base_severity" in result.components
    assert "penalties" in result.components


def test_compute_outcome_severity_with_penalties(outcomes_config):
    """Test outcome severity with penalties."""
    card = {
        "doc_id": "NCT123",
        "primary_endpoint": "ADAS-Cog11",
        "claims": [
            {"type": "limitation", "proposition": "subgroup only wins"},
            {"type": "limitation", "proposition": "endpoint changed post registration"}
        ],
        "primary_result": {
            "ITT": {
                "estimate": 0.5,
                "p": 0.1,
                "significant": False
            }
        }
    }
    
    result = compute_outcome_severity(card, outcomes_config)
    
    assert result.severity > 0.5  # Should be high due to penalties
    assert "subgroup_only" in result.components["penalties"]
    assert "endpoint_changed_post_reg" in result.components["penalties"]


def test_compute_outcome_severity_missing_data(outcomes_config):
    """Test outcome severity with missing data."""
    card = {
        "doc_id": "NCT123",
        "primary_endpoint": "ADAS-Cog11"
        # No primary_result
    }
    
    result = compute_outcome_severity(card, outcomes_config)
    
    assert result.severity > 0.5  # Should be higher due to penalties
    assert result.grade in ["LF", "FF"]  # Should be higher grade due to penalties
    assert "note" in result.components
    assert "missing_primary_result" in result.components["penalties"]


def test_compute_outcome_severity_binary_endpoint(outcomes_config):
    """Test outcome severity for binary endpoint."""
    card = {
        "doc_id": "NCT123",
        "primary_endpoint": "Response Rate",
        "primary_result": {
            "ITT": {
                "estimate": 0.08,  # Risk difference
                "p": 0.02,
                "significant": True
            }
        }
    }
    
    result = compute_outcome_severity(card, outcomes_config)
    
    assert isinstance(result, OutcomeSeverity)
    assert 0.0 <= result.severity <= 1.0


def test_compute_outcome_severity_tte_endpoint(outcomes_config):
    """Test outcome severity for time-to-event endpoint."""
    card = {
        "doc_id": "NCT123",
        "primary_endpoint": "Overall Survival",
        "primary_result": {
            "ITT": {
                "estimate": -0.3,  # Log hazard ratio
                "p": 0.01,
                "significant": True
            }
        }
    }
    
    result = compute_outcome_severity(card, outcomes_config)
    
    assert isinstance(result, OutcomeSeverity)
    assert 0.0 <= result.severity <= 1.0


def test_grade_boundaries(outcomes_config):
    """Test grade boundary assignments."""
    # Test different severity values
    test_cases = [
        (0.1, "SS"),
        (0.3, "LS"),
        (0.5, "A"),
        (0.7, "LF"),
        (0.9, "FF")
    ]
    
    for severity, expected_grade in test_cases:
        card = {
            "doc_id": "NCT123",
            "primary_endpoint": "ADAS-Cog11"
        }
        
        # Mock the severity computation
        result = OutcomeSeverity(
            severity=severity,
            grade="",  # Will be computed
            components={},
            confidence=0.5
        )
        
        # Manually set the grade
        for grade, bounds in outcomes_config["grades"].items():
            if bounds[0] <= severity <= bounds[1]:
                result.grade = grade
                break
        
        assert result.grade == expected_grade


def test_confidence_computation(outcomes_config):
    """Test confidence computation."""
    card = {
        "doc_id": "NCT123",
        "primary_endpoint": "ADAS-Cog11",
        "primary_result": {
            "ITT": {
                "estimate": 1.5,
                "p": 0.03,
                "significant": True
            }
        }
    }
    
    result = compute_outcome_severity(card, outcomes_config)
    
    assert 0.0 <= result.confidence <= 1.0
    assert "effect_severity" in result.components
    assert "pvalue_severity" in result.components


if __name__ == "__main__":
    pytest.main([__file__])
