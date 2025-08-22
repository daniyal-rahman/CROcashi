#!/usr/bin/env python3
"""
Demo script for signals and gates system.

This script demonstrates how to use the trial failure detection
signals (S1-S9) and gates (G1-G4) with example data.
"""

import sys
import os
from datetime import datetime, date
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from ncfd.signals import (
    evaluate_all_signals, evaluate_all_gates,
    get_fired_signals, get_fired_gates,
    get_gate_summary
)


def create_example_study_card():
    """Create an example study card for demonstration."""
    return {
        "study_id": "DEMO001",
        "is_pivotal": True,
        "primary_type": "proportion",
        "arms": {
            "t": {"n": 150, "dropout": 0.15},
            "c": {"n": 150, "dropout": 0.08}
        },
        "analysis_plan": {
            "alpha": 0.025,
            "one_sided": True,
            "assumed_p_c": 0.25,
            "assumed_delta_abs": 0.12,
            "planned_interims": 2,
            "alpha_spending": None  # No alpha spending plan
        },
        "primary_result": {
            "ITT": {"p": 0.049, "estimate": 0.08},
            "PP": {"p": 0.02, "estimate": 0.15}
        },
        "subgroups": [
            {"name": "Age < 65", "p": 0.03, "adjusted": False, "pre_specified_interaction": False},
            {"name": "Region A", "p": 0.08, "adjusted": False, "pre_specified_interaction": False}
        ],
        "narrative_highlights_subgroup": True,
        "endpoint_subjective_unblinded": False,
        "single_arm": False,
        "N_total": 300,
        "events_observed": 180
    }


def create_example_trial_versions():
    """Create example trial versions for S1 testing."""
    return [
        {
            "version_id": 1,
            "primary_endpoint_text": "Primary: PFS at 12 months, superiority, blinded",
            "captured_at": datetime(2024, 1, 15),
            "est_primary_completion_date": date(2025, 12, 31),
            "changes_jsonb": {"endpoint_changed": False}
        },
        {
            "version_id": 2,
            "primary_endpoint_text": "Primary: Overall Survival at 24 months, superiority, open-label",
            "captured_at": datetime(2024, 8, 20),  # ~8 months before completion
            "est_primary_completion_date": date(2025, 12, 31),
            "changes_jsonb": {"endpoint_changed": True, "reason": "protocol amendment"}
        }
    ]


def create_example_class_metadata():
    """Create example class metadata for S5 testing."""
    return {
        "graveyard": True,
        "winners_pctl": {
            "p75": 0.28,
            "p90": 0.35
        }
    }


def demo_signals_only():
    """Demonstrate signal evaluation without gates."""
    print("🔍 DEMO: SIGNAL EVALUATION ONLY")
    print("=" * 50)
    
    card = create_example_study_card()
    trial_versions = create_example_trial_versions()
    class_meta = create_example_class_metadata()
    
    # Evaluate all signals
    signals = evaluate_all_signals(
        card=card,
        trial_versions=trial_versions,
        class_meta=class_meta,
        rct_required=True
    )
    
    print(f"Evaluated {len(signals)} signals:")
    for signal_id, result in signals.items():
        status = "🚨 FIRED" if result.fired else "✅ CLEAR"
        print(f"  {signal_id}: {status} ({result.severity}) - {result.reason}")
    
    # Show fired signals
    fired = get_fired_signals(signals)
    if fired:
        print(f"\n🚨 {len(fired)} signals fired:")
        for signal_id, result in fired.items():
            print(f"  {signal_id}: {result.severity} - {result.reason}")
            if result.metadata:
                print(f"    Metadata: {result.metadata}")
    else:
        print("\n✅ No signals fired - trial looks clean!")
    
    return signals


def demo_gates_only(signals):
    """Demonstrate gate evaluation using pre-computed signals."""
    print("\n🚪 DEMO: GATE EVALUATION")
    print("=" * 50)
    
    # Evaluate all gates
    gates = evaluate_all_gates(signals)
    
    print(f"Evaluated {len(gates)} gates:")
    for gate_id, result in gates.items():
        status = "🚨 FIRED" if result.fired else "✅ CLEAR"
        print(f"  {gate_id}: {status} ({result.severity}) - {result.rationale_text}")
    
    # Show fired gates
    fired_gates = get_fired_gates(gates)
    if fired_gates:
        print(f"\n🚨 {len(fired_gates)} gates fired:")
        for gate_id, result in fired_gates.items():
            print(f"  {gate_id}: {result.severity} - {result.rationale_text}")
            print(f"    Supporting signals: {', '.join(result.supporting_S_ids)}")
            print(f"    Likelihood ratio: {result.lr_used}")
            if result.metadata:
                print(f"    Metadata: {result.metadata}")
    else:
        print("\n✅ No gates fired - no major failure patterns detected!")
    
    return gates


def demo_full_pipeline():
    """Demonstrate the complete signal → gate pipeline."""
    print("\n🔄 DEMO: FULL SIGNAL → GATE PIPELINE")
    print("=" * 50)
    
    # Step 1: Evaluate signals
    signals = demo_signals_only()
    
    # Step 2: Evaluate gates
    gates = demo_gates_only(signals)
    
    # Step 3: Get summary
    summary = get_gate_summary(gates)
    print(f"\n📊 PIPELINE SUMMARY:")
    print(f"  Total gates evaluated: {summary['total_gates']}")
    print(f"  Gates fired: {summary['fired_gates']}")
    print(f"  High severity gates: {summary['high_severity_gates']}")
    print(f"  Overall severity: {summary['overall_severity']}")
    print(f"  Total likelihood ratio: {summary['total_likelihood_ratio']:.2f}")
    
    if summary['fired_gates'] > 0:
        print(f"  Fired gate IDs: {', '.join(summary['fired_gate_ids'])}")
    
    if summary['high_severity_gates'] > 0:
        print(f"  High severity gate IDs: {', '.join(summary['high_severity_gate_ids'])}")
    
    return signals, gates


def demo_edge_cases():
    """Demonstrate edge cases and error handling."""
    print("\n⚠️ DEMO: EDGE CASES & ERROR HANDLING")
    print("=" * 50)
    
    # Test with minimal data
    minimal_card = {"is_pivotal": False}
    signals = evaluate_all_signals(minimal_card)
    
    print("Minimal study card (non-pivotal):")
    for signal_id, result in signals.items():
        if result.fired:
            print(f"  {signal_id}: {result.reason}")
        else:
            print(f"  {signal_id}: {result.reason}")
    
    # Test with missing required fields
    incomplete_card = {
        "is_pivotal": True,
        "primary_type": "proportion",
        "arms": {"t": {}, "c": {}}  # Missing sample sizes
    }
    
    signals = evaluate_all_signals(incomplete_card)
    print(f"\nIncomplete study card:")
    for signal_id, result in signals.items():
        if result.fired:
            print(f"  {signal_id}: {result.reason}")
        else:
            print(f"  {signal_id}: {result.reason}")


def main():
    """Main demo function."""
    print("🎯 TRIAL FAILURE DETECTION SYSTEM DEMO")
    print("=" * 60)
    print("This demo shows how the signals (S1-S9) and gates (G1-G4)")
    print("work together to detect potential trial failures.")
    print()
    
    try:
        # Run full pipeline demo
        signals, gates = demo_full_pipeline()
        
        # Show edge cases
        demo_edge_cases()
        
        print("\n✅ Demo completed successfully!")
        print("\nKey takeaways:")
        print("  • Signals detect individual red flags")
        print("  • Gates combine signals to identify failure patterns")
        print("  • System is robust to missing/incomplete data")
        print("  • All results include metadata for audit trails")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
