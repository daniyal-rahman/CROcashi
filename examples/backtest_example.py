#!/usr/bin/env python3
"""
Example of running backtests on the system.
"""

import json
import sys
from pathlib import Path

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.catalyst.backtest import BacktestRunner
from ncfd.config import get_config


def create_example_trial():
    """Create an example trial card for demonstration."""
    return {
        "doc_id": "NCT123456",
        "primary_endpoint": "ADAS-Cog11",
        "method_card": {
            "primary_endpoint": "ADAS-Cog11",
            "is_pivotal": True,
            "arms": {
                "t": {"n": 150, "dropout": 0.15},
                "c": {"n": 150, "dropout": 0.10}
            }
        },
        "primary_result": {
            "ITT": {
                "estimate": 0.8,  # Small positive effect
                "p": 0.12,        # Not significant
                "significant": False
            }
        },
        "claims": [
            {"type": "limitation", "proposition": "primary endpoint not significant"},
            {"type": "limitation", "proposition": "subgroup analysis shows benefit in mild AD only"},
            {"type": "design_fact", "proposition": "endpoint changed from ADAS-Cog14 to ADAS-Cog11 post-registration"}
        ],
        "subgroups": [
            {
                "name": "Mild AD",
                "p": 0.03,
                "significant": True,
                "adjusted": False
            },
            {
                "name": "Moderate AD", 
                "p": 0.45,
                "significant": False,
                "adjusted": False
            }
        ]
    }


def create_example_outcomes_config():
    """Create example outcomes configuration."""
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


def main():
    """Run the example."""
    print("🔬 NCFD Backtest System Example")
    print("=" * 50)
    
    # Create example trial
    trial = create_example_trial()
    outcomes_cfg = create_example_outcomes_config()
    
    print(f"📋 Trial: {trial['doc_id']}")
    print(f"🎯 Endpoint: {trial['primary_endpoint']}")
    print(f"📊 Effect: {trial['primary_result']['ITT']['estimate']} points")
    print(f"📈 P-value: {trial['primary_result']['ITT']['p']}")
    print(f"✅ Significant: {trial['primary_result']['ITT']['significant']}")
    
    # Compute outcome severity
    outcome = BacktestOutcomes.compute_outcome_severity(trial, outcomes_cfg)
    
    print("\n📊 Outcome Analysis")
    print("-" * 30)
    print(f"Severity: {outcome.severity:.3f}")
    print(f"Grade: {outcome.grade}")
    print(f"Confidence: {outcome.confidence:.3f}")
    
    print("\n🔍 Components")
    print("-" * 30)
    print(f"Base Severity: {outcome.components['base_severity']:.3f}")
    print(f"Total Penalties: {outcome.components['total_penalty']:.3f}")
    
    if outcome.components['penalties']:
        print("\n⚠️  Applied Penalties:")
        for penalty, value in outcome.components['penalties'].items():
            print(f"  - {penalty}: +{value:.2f}")
    
    # Grade interpretation
    grade_meanings = {
        "SS": "Clear Success",
        "LS": "Likely Success", 
        "A": "Ambiguous",
        "LF": "Likely Failure",
        "FF": "Clear Failure"
    }
    
    print(f"\n🎯 Interpretation: {grade_meanings[outcome.grade]}")
    
    if outcome.grade in ["LF", "FF"]:
        print("🚨 This trial shows signs of potential failure modes")
    elif outcome.grade in ["SS", "LS"]:
        print("✅ This trial appears robust")
    else:
        print("❓ Insufficient evidence for clear assessment")
    
    print("\n" + "=" * 50)
    print("✅ Example completed successfully!")


if __name__ == "__main__":
    main()
