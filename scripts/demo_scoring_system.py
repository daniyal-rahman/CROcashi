#!/usr/bin/env python3
"""
Demo script for the trial failure detection scoring system.

This script demonstrates the complete pipeline from signals → gates → scoring,
showing how trial failure probabilities are calculated using likelihood ratios
and prior failure rates.
"""

import sys
import json
from datetime import datetime, date, timedelta
from typing import Dict, Any, List

# Add src to path for imports
sys.path.insert(0, 'src')

from ncfd.signals import (
    evaluate_all_signals, evaluate_all_gates, get_fired_signals, get_fired_gates
)
from ncfd.scoring import (
    ScoringEngine, ScoreResult, score_single_trial, batch_score_trials,
    LikelihoodRatioCalibrator, PriorRateCalibrator, get_default_config,
    calibrate_scoring_system, get_calibrated_config
)


def create_sample_study_cards() -> List[Dict[str, Any]]:
    """Create sample study cards for demonstration."""
    return [
        # Study 1: High-risk oncology trial with multiple issues
        {
            "study_id": "ONC001",
            "is_pivotal": True,
            "primary_type": "proportion",
            "arms": {"t": {"n": 150, "dropout": 0.20}, "c": {"n": 150, "dropout": 0.08}},
            "analysis_plan": {
                "alpha": 0.025, "one_sided": True, "assumed_p_c": 0.25, "assumed_delta_abs": 0.12,
                "planned_interims": 3, "alpha_spending": None
            },
            "primary_result": {"ITT": {"p": 0.049, "estimate": 0.08}},
            "subgroups": [
                {"name": "biomarker_positive", "n": 80, "p": 0.035, "estimate": 0.12}
            ],
            "single_arm": False,
            "endpoint_changed_after_lpr": False,
            "pp_only_success": False,
            "dropout_asymmetry": 0.12,
            "unblinded_subjective_primary": False,
            "blinding_feasible": True
        },
        
        # Study 2: Medium-risk rare disease trial
        {
            "study_id": "RARE001",
            "is_pivotal": True,
            "primary_type": "proportion",
            "arms": {"t": {"n": 80, "dropout": 0.10}, "c": {"n": 80, "dropout": 0.08}},
            "analysis_plan": {
                "alpha": 0.025, "one_sided": True, "assumed_p_c": 0.30, "assumed_delta_abs": 0.20,
                "planned_interims": 1, "alpha_spending": "O'Brien-Fleming"
            },
            "primary_result": {"ITT": {"p": 0.032, "estimate": 0.15}},
            "subgroups": [],
            "single_arm": False,
            "endpoint_changed_after_lpr": False,
            "pp_only_success": False,
            "dropout_asymmetry": 0.02,
            "unblinded_subjective_primary": False,
            "blinding_feasible": True
        },
        
        # Study 3: Low-risk phase 2 trial
        {
            "study_id": "P2_001",
            "is_pivotal": False,
            "primary_type": "proportion",
            "arms": {"t": {"n": 60, "dropout": 0.05}, "c": {"n": 60, "dropout": 0.05}},
            "analysis_plan": {
                "alpha": 0.05, "one_sided": False, "assumed_p_c": 0.40, "assumed_delta_abs": 0.25,
                "planned_interims": 0, "alpha_spending": None
            },
            "primary_result": {"ITT": {"p": 0.028, "estimate": 0.22}},
            "subgroups": [],
            "single_arm": False,
            "endpoint_changed_after_lpr": False,
            "pp_only_success": False,
            "dropout_asymmetry": 0.0,
            "unblinded_subjective_primary": False,
            "blinding_feasible": True
        },
        
        # Study 4: Stop rule trigger (endpoint changed after LPR)
        {
            "study_id": "STOP001",
            "is_pivotal": True,
            "primary_type": "survival",
            "arms": {"t": {"n": 200, "dropout": 0.15}, "c": {"n": 200, "dropout": 0.12}},
            "analysis_plan": {
                "alpha": 0.025, "one_sided": True, "assumed_p_c": 0.20, "assumed_delta_abs": 0.15,
                "planned_interims": 2, "alpha_spending": "Pocock"
            },
            "primary_result": {"ITT": {"p": 0.041, "estimate": 0.12}},
            "subgroups": [],
            "single_arm": False,
            "endpoint_changed_after_lpr": True,  # This will trigger stop rule
            "pp_only_success": False,
            "dropout_asymmetry": 0.03,
            "unblinded_subjective_primary": False,
            "blinding_feasible": True
        }
    ]


def create_trial_metadata() -> Dict[int, Dict[str, Any]]:
    """Create trial metadata for scoring."""
    return {
        1: {
            "trial_id": 1,
            "is_pivotal": True,
            "indication": "oncology",
            "phase": "phase_3",
            "sponsor_experience": "experienced",
            "primary_endpoint_type": "proportion",
            "est_primary_completion_date": date(2025, 6, 30)
        },
        2: {
            "trial_id": 2,
            "is_pivotal": True,
            "indication": "rare_disease",
            "phase": "phase_3",
            "sponsor_experience": "experienced",
            "primary_endpoint_type": "proportion",
            "est_primary_completion_date": date(2025, 8, 15)
        },
        3: {
            "trial_id": 3,
            "is_pivotal": False,
            "indication": "cardiovascular",
            "phase": "phase_2",
            "sponsor_experience": "experienced",
            "primary_endpoint_type": "proportion",
            "est_primary_completion_date": date(2025, 12, 31)
        },
        4: {
            "trial_id": 4,
            "is_pivotal": True,
            "indication": "oncology",
            "phase": "phase_3",
            "sponsor_experience": "experienced",
            "primary_endpoint_type": "survival",
            "est_primary_completion_date": date(2025, 5, 15)
        }
    }


def create_historical_data() -> List[Dict[str, Any]]:
    """Create sample historical data for calibration."""
    return [
        {
            "trial_id": 101,
            "actual_outcome": True,  # Failed
            "gates_fired": ["G1"],
            "gate_severities": {"G1": "H"},
            "is_pivotal": True,
            "indication": "oncology"
        },
        {
            "trial_id": 102,
            "actual_outcome": False,  # Succeeded
            "gates_fired": ["G1"],
            "gate_severities": {"G1": "H"},
            "is_pivotal": True,
            "indication": "oncology"
        },
        {
            "trial_id": 103,
            "actual_outcome": True,  # Failed
            "gates_fired": ["G2"],
            "gate_severities": {"G2": "M"},
            "is_pivotal": True,
            "indication": "oncology"
        },
        {
            "trial_id": 104,
            "actual_outcome": False,  # Succeeded
            "gates_fired": [],
            "gate_severities": {},
            "is_pivotal": False,
            "indication": "cardiovascular"
        },
        {
            "trial_id": 105,
            "actual_outcome": False,  # Succeeded
            "gates_fired": [],
            "gate_severities": {},
            "is_pivotal": False,
            "indication": "cardiovascular"
        }
    ]


def demo_signal_evaluation():
    """Demonstrate signal evaluation."""
    print("🔍 DEMO: SIGNAL EVALUATION")
    print("=" * 50)
    
    study_cards = create_sample_study_cards()
    
    for i, study_card in enumerate(study_cards, 1):
        print(f"\n📊 Study {i}: {study_card['study_id']}")
        print(f"   Type: {'Pivotal' if study_card['is_pivotal'] else 'Non-pivotal'}")
        print(f"   Indication: {study_card.get('indication', 'Unknown')}")
        
        # Evaluate signals
        signals = evaluate_all_signals(study_card)
        fired_signals = get_fired_signals(signals)
        
        print(f"   Signals fired: {len(fired_signals)}/{len(signals)}")
        
        for signal_id, signal in fired_signals.items():
            print(f"     {signal_id}: {signal.severity} - {signal.reason}")
    
    return study_cards


def demo_gate_evaluation(study_cards: List[Dict[str, Any]]):
    """Demonstrate gate evaluation."""
    print("\n🚪 DEMO: GATE EVALUATION")
    print("=" * 50)
    
    all_gates = {}
    
    for i, study_card in enumerate(study_cards, 1):
        print(f"\n📊 Study {i}: {study_card['study_id']}")
        
        # Evaluate signals and gates
        signals = evaluate_all_signals(study_card)
        gates = evaluate_all_gates(signals)
        
        # Store gates for scoring
        all_gates[i] = gates
        
        fired_gates = get_fired_gates(gates)
        print(f"   Gates fired: {len(fired_gates)}/{len(gates)}")
        
        for gate_id, gate in fired_gates.items():
            print(f"     {gate_id}: {gate.severity} - {gate.rationale_text}")
            if gate.supporting_S_ids:
                print(f"       Supporting signals: {', '.join(gate.supporting_S_ids)}")
    
    return all_gates


def demo_scoring_engine():
    """Demonstrate the scoring engine."""
    print("\n🎯 DEMO: SCORING ENGINE")
    print("=" * 50)
    
    # Create scoring engine with custom config
    config = {
        "default_prior": 0.12,  # Lower baseline for demo
        "feature_freeze_days": 30,  # Longer freeze window
        "stop_rule_thresholds": {
            "endpoint_switched_after_lpr": 0.95,
            "pp_only_success_high_dropout": 0.95,
            "unblinded_subjective_primary": 0.95,
            "multiple_high_severity_gates": 0.90
        }
    }
    
    engine = ScoringEngine(config)
    
    print(f"Default prior: {engine.default_prior}")
    print(f"Feature freeze days: {engine.feature_freeze_days}")
    print(f"Stop rule thresholds: {engine.stop_rule_thresholds}")
    
    return engine


def demo_prior_calculation(engine: ScoringEngine):
    """Demonstrate prior failure rate calculation."""
    print("\n📈 DEMO: PRIOR FAILURE RATE CALCULATION")
    print("=" * 50)
    
    trial_metadata = create_trial_metadata()
    
    for trial_id, metadata in trial_metadata.items():
        prior = engine.calculate_prior_failure_rate(metadata)
        
        print(f"\nTrial {trial_id}:")
        print(f"  Pivotal: {metadata['is_pivotal']}")
        print(f"  Indication: {metadata['indication']}")
        print(f"  Phase: {metadata['phase']}")
        print(f"  Sponsor: {metadata['sponsor_experience']}")
        print(f"  Calculated prior: {prior:.3f}")
        
        # Show the reasoning
        if metadata['is_pivotal']:
            print(f"    → Higher risk due to pivotal design")
        if metadata['indication'] == 'oncology':
            print(f"    → Higher risk due to oncology indication")
        if metadata['phase'] == 'phase_3':
            print(f"    → Higher risk due to phase 3")


def demo_stop_rules(engine: ScoringEngine):
    """Demonstrate stop rule application."""
    print("\n🛑 DEMO: STOP RULES")
    print("=" * 50)
    
    # Create a trial that will trigger stop rules
    trial_data = {
        "trial_id": 999,
        "endpoint_changed_after_lpr": True,
        "pp_only_success": False,
        "dropout_asymmetry": 0.0,
        "unblinded_subjective_primary": False,
        "blinding_feasible": True
    }
    
    # Create gates where G1 fires
    from ncfd.signals import GateResult
    gates = {
        "G1": GateResult(
            fired=True, G_id="G1", supporting_S_ids=["S1", "S2"],
            lr_used=10.0, rationale_text="Alpha meltdown"
        )
    }
    
    print("Testing stop rule: Endpoint changed after LPR + G1 fired")
    stop_rule_prob = engine.apply_stop_rules(trial_data, gates)
    
    if stop_rule_prob:
        print(f"✅ Stop rule triggered: p_fail = {stop_rule_prob}")
    else:
        print("❌ No stop rules triggered")
    
    # Test another stop rule
    trial_data2 = {
        "trial_id": 998,
        "pp_only_success": True,
        "dropout_asymmetry": 0.25  # > 0.20 threshold
    }
    
    print("\nTesting stop rule: PP-only success with high dropout asymmetry")
    stop_rule_prob2 = engine.apply_stop_rules(trial_data2, gates)
    
    if stop_rule_prob2:
        print(f"✅ Stop rule triggered: p_fail = {stop_rule_prob2}")
    else:
        print("❌ No stop rules triggered")


def demo_scoring_pipeline(engine: ScoringEngine, study_cards: List[Dict[str, Any]], 
                         all_gates: Dict[int, Dict[str, Any]]):
    """Demonstrate the complete scoring pipeline."""
    print("\n🎯 DEMO: COMPLETE SCORING PIPELINE")
    print("=" * 50)
    
    trial_metadata = create_trial_metadata()
    
    # Score each trial
    scores = []
    for i, (study_card, gates) in enumerate(zip(study_cards, all_gates.values()), 1):
        trial_id = i
        metadata = trial_metadata[trial_id]
        
        print(f"\n📊 Scoring Trial {trial_id}: {study_card['study_id']}")
        
        # Score the trial
        score = engine.score_trial(trial_id, metadata, gates, f"demo_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        print(f"  Prior failure rate: {score.prior_pi:.3f}")
        print(f"  Posterior probability: {score.p_fail:.3f}")
        print(f"  Risk increase: {(score.p_fail / score.prior_pi - 1) * 100:.1f}%")
        
        if score.metadata.get("stop_rule_applied"):
            print(f"  ⚠️  Stop rule applied: {score.metadata.get('stop_rule_type')}")
        
        if score.features_frozen_at:
            print(f"  🔒 Features frozen at: {score.features_frozen_at}")
        
        scores.append(score)
    
    # Generate summary
    print(f"\n📊 SCORING SUMMARY")
    print("=" * 30)
    summary = engine.get_scoring_summary(scores)
    
    print(f"Total trials: {summary['total_trials']}")
    print(f"Risk breakdown:")
    print(f"  High risk: {summary['risk_breakdown']['high_risk']}")
    print(f"  Medium risk: {summary['risk_breakdown']['medium_risk']}")
    print(f"  Low risk: {summary['risk_breakdown']['low_risk']}")
    print(f"Stop rules applied: {summary['stop_rules_applied']}")
    print(f"Features frozen: {summary['features_frozen']}")
    print(f"Average failure probability: {summary['statistics']['average_p_fail']:.3f}")
    
    return scores


def demo_calibration():
    """Demonstrate the calibration system."""
    print("\n🔧 DEMO: CALIBRATION SYSTEM")
    print("=" * 50)
    
    # Create historical data
    historical_data = create_historical_data()
    
    print(f"Historical data: {len(historical_data)} trials")
    
    # Calibrate likelihood ratios
    lr_calibrator = LikelihoodRatioCalibrator()
    calibrated_lrs = lr_calibrator.calibrate_from_historical_data(historical_data)
    
    print(f"\nCalibrated likelihood ratios:")
    for gate_id, severities in calibrated_lrs.items():
        for severity, lr in severities.items():
            print(f"  {gate_id}-{severity}: {lr}")
    
    # Calibrate prior rates
    prior_calibrator = PriorRateCalibrator()
    calibrated_priors = prior_calibrator.calibrate_from_historical_data(historical_data)
    
    print(f"\nCalibrated prior rates:")
    for category, prior in calibrated_priors.items():
        print(f"  {category}: {prior:.3f}")
    
    # Get calibrated config
    calibrated_config = get_calibrated_config(historical_data)
    print(f"\nCalibrated config keys: {list(calibrated_config.keys())}")
    
    return calibrated_config


def demo_batch_scoring():
    """Demonstrate batch scoring functionality."""
    print("\n📦 DEMO: BATCH SCORING")
    print("=" * 50)
    
    # Create multiple trials
    trials_data = [
        {
            "trial_id": 201,
            "is_pivotal": True,
            "indication": "oncology",
            "phase": "phase_3",
            "sponsor_experience": "experienced"
        },
        {
            "trial_id": 202,
            "is_pivotal": False,
            "indication": "cardiovascular",
            "phase": "phase_2",
            "sponsor_experience": "experienced"
        },
        {
            "trial_id": 203,
            "is_pivotal": True,
            "indication": "rare_disease",
            "phase": "phase_3",
            "sponsor_experience": "novice"
        }
    ]
    
    # Create gates for each trial (simplified)
    from ncfd.signals import GateResult
    gates_data = {
        201: {"G1": GateResult(fired=True, G_id="G1", supporting_S_ids=["S1"], lr_used=8.0)},
        202: {"G2": GateResult(fired=False, G_id="G2", supporting_S_ids=[], lr_used=None)},
        203: {"G3": GateResult(fired=True, G_id="G3", supporting_S_ids=["S5"], lr_used=12.0)}
    }
    
    # Batch score
    scores = batch_score_trials(trials_data, gates_data, "batch_demo")
    
    print(f"Batch scored {len(scores)} trials:")
    for score in scores:
        print(f"  Trial {score.trial_id}: prior={score.prior_pi:.3f}, posterior={score.p_fail:.3f}")


def main():
    """Run the complete scoring system demo."""
    print("🎯 TRIAL FAILURE DETECTION SCORING SYSTEM DEMO")
    print("=" * 60)
    print("This demo shows how the scoring system calculates trial failure")
    print("probabilities using signals, gates, and likelihood ratios.\n")
    
    try:
        # Run all demos
        study_cards = demo_signal_evaluation()
        all_gates = demo_gate_evaluation(study_cards)
        engine = demo_scoring_engine()
        demo_prior_calculation(engine)
        demo_stop_rules(engine)
        scores = demo_scoring_pipeline(engine, study_cards, all_gates)
        demo_calibration()
        demo_batch_scoring()
        
        print("\n✅ Demo completed successfully!")
        print("\nKey takeaways:")
        print("  • Signals detect individual red flags")
        print("  • Gates combine signals to identify failure patterns")
        print("  • Scoring calculates posterior failure probabilities")
        print("  • Stop rules provide immediate high-risk assessments")
        print("  • Calibration improves accuracy with historical data")
        print("  • Feature freezing prevents data leakage")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
