#!/usr/bin/env python3
"""
CLI runner to demo S1-S9 signals, gates, and scoring on extraction results.

Usage:
    python scripts/run_signals_from_extraction.py --extraction-json test_outputs/pmc2978916_debug/extraction_results.json
"""

import json
import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.signals.study_card_mapper import build_study_card
from ncfd.signals.primitives import (
    S1_endpoint_changed, 
    S2_underpowered_pivotal, 
    S3_subgroup_only_no_multiplicity, 
    S4_itt_vs_pp_dropout,
    S5_implausible_vs_graveyard,
    S6_many_interims_no_spending,
    S7_single_arm_where_rct_standard,
    S7b_randomized_withdrawal_after_OLE,
    S8_pvalue_cusp_or_heaping,
    S9_os_pfs_contradiction
)
from ncfd.signals.types import SignalResult
from ncfd.signals.gates import evaluate_all_gates
from ncfd.signals.scoring import score_trial, get_default_prior_pi, interpret_score, format_score_summary


def main():
    parser = argparse.ArgumentParser(description="Run S1-S9 signals, gates, and scoring on extraction results")
    parser.add_argument("--extraction-json", required=True, help="Path to extraction_results.json")
    parser.add_argument("--trial-versions-json", help="Path to trial_versions.json (optional)")
    parser.add_argument("--graveyard-json", help="Path to graveyard_data.json (optional)")
    parser.add_argument("--rct-required-json", help="Path to rct_required_data.json (optional)")
    parser.add_argument("--output-json", help="Path to output signals JSON")
    args = parser.parse_args()

    # Load extraction results
    try:
        with open(args.extraction_json, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading extraction JSON: {e}")
        return 1

    # Extract artifacts
    mc = data.get("method_card")
    rf = data.get("results_factsheet") 
    claims = data.get("claims", [])
    doc_id = data.get("doc_id") or mc.get("doc_id") if mc else "unknown"

    # Load trial versions if provided
    trial_versions = []
    if args.trial_versions_json:
        try:
            with open(args.trial_versions_json, 'r') as f:
                trial_versions = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load trial versions: {e}")

    # Load graveyard data if provided
    graveyard_data = {}
    if args.graveyard_json:
        try:
            with open(args.graveyard_json, 'r') as f:
                graveyard_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load graveyard data: {e}")

    # Load RCT required data if provided
    rct_required_data = {}
    if args.rct_required_json:
        try:
            with open(args.rct_required_json, 'r') as f:
                rct_required_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load RCT required data: {e}")

    # Build Study Card
    try:
        card = build_study_card(doc_id, mc, rf, claims)
    except Exception as e:
        print(f"Error building Study Card: {e}")
        return 1

    # Run all signals
    signals = {
        "S1": S1_endpoint_changed(trial_versions) if trial_versions else SignalResult(
            fired=False, 
            severity="L", 
            reason="no trial versions provided",
            value=None,
            evidence_ids=[],
            low_cert_inputs=False
        ),
        "S2": S2_underpowered_pivotal(card),
        "S3": S3_subgroup_only_no_multiplicity(card),
        "S4": S4_itt_vs_pp_dropout(card),
        "S5": S5_implausible_vs_graveyard(card, graveyard_data),
        "S6": S6_many_interims_no_spending(card),
        "S7": S7_single_arm_where_rct_standard(card, rct_required_data),
        "S7b": S7b_randomized_withdrawal_after_OLE(card),
        "S8": S8_pvalue_cusp_or_heaping(card),
        "S9": S9_os_pfs_contradiction(card),
    }

    # Evaluate gates
    gates = evaluate_all_gates(signals)

    # Calculate default prior
    indication = card.get("indication", "unknown")
    phase = card.get("analysis_plan", {}).get("phase", "phase_2")
    design_type = "single_arm" if card.get("single_arm") else "rct"
    prior_pi = get_default_prior_pi(indication, phase, design_type)

    # Score trial
    score = score_trial(
        trial_id=doc_id,
        prior_pi=prior_pi,
        signals=signals,
        gates=gates,
        evidence_span="extraction_span",
        source_study_id=doc_id
    )

    # Prepare results
    results = {
        "doc_id": doc_id,
        "study_card": card,
        "signals": {k: v.__dict__ if hasattr(v, '__dict__') else v for k, v in signals.items()},
        "gates": {k: v.__dict__ for k, v in gates.items()},
        "scoring": {
            "score": score.__dict__,
            "summary": format_score_summary(score)
        }
    }

    # Print results
    print("=== SIGNALS RESULTS ===")
    print(f"Document: {doc_id}")
    print(f"Study Card: {json.dumps(card, indent=2)}")
    print()
    
    print("=== SIGNAL EVALUATIONS ===")
    for signal_id, result in signals.items():
        if hasattr(result, 'fired'):
            status = "🔥 FIRED" if result.fired else "✅ CLEAR"
            print(f"{signal_id}: {status} ({result.severity}) - {result.reason}")
            if result.value is not None:
                print(f"  Value: {result.value}")
            if hasattr(result, 'evidence_ids') and result.evidence_ids:
                print(f"  Evidence: {result.evidence_ids}")
        else:
            print(f"{signal_id}: {result['fired']} ({result['severity']}) - {result['reason']}")
        print()

    print("=== GATE EVALUATIONS ===")
    for gate_id, gate in gates.items():
        status = "🔥 FIRED" if gate.fired else "✅ CLEAR"
        print(f"{gate_id}: {status} ({gate.severity}) - {gate.reason}")
        if gate.supporting_signals:
            print(f"  Supporting signals: {gate.supporting_signals}")
        print(f"  Likelihood ratio: {gate.likelihood_ratio:.2f}")
        print()

    print("=== SCORING RESULTS ===")
    summary = format_score_summary(score)
    print(f"Risk Level: {summary['risk_level']}")
    print(f"P(Failure): {summary['p_failure']}")
    print(f"Prior P(Failure): {summary['prior_pi']}")
    print(f"Logit Change: {summary['logit_change']}")
    print(f"Total Likelihood Ratio: {summary['total_lr']}")
    print(f"Fired Gates: {summary['fired_gates']}")
    print(f"Fired Signals: {summary['fired_signals']}")

    # Summary
    fired_signals = [s for s in signals.values() if hasattr(s, 'fired') and s.fired]
    fired_gates = [g for g in gates.values() if g.fired]
    high_severity_signals = [s for s in fired_signals if s.severity == "H"]
    high_severity_gates = [g for g in fired_gates if g.severity == "H"]
    
    print("\n=== SUMMARY ===")
    print(f"Total signals evaluated: {len(signals)}")
    print(f"Signals fired: {len(fired_signals)}")
    print(f"High severity signals: {len(high_severity_signals)}")
    print(f"Total gates evaluated: {len(gates)}")
    print(f"Gates fired: {len(fired_gates)}")
    print(f"High severity gates: {len(high_severity_gates)}")
    
    if fired_signals:
        print("\n🔥 FIRED SIGNALS:")
        for signal_id, result in signals.items():
            if hasattr(result, 'fired') and result.fired:
                print(f"  {signal_id}: {result.severity} - {result.reason}")

    if fired_gates:
        print("\n🔥 FIRED GATES:")
        for gate_id, gate in gates.items():
            if gate.fired:
                print(f"  {gate_id}: {gate.severity} - {gate.reason}")

    # Save to JSON if requested
    if args.output_json:
        try:
            with open(args.output_json, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to: {args.output_json}")
        except Exception as e:
            print(f"Error saving results: {e}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
