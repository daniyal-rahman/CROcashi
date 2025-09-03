"""
End-to-end test for signals pipeline from extraction results.
"""

import json
import tempfile
import os
from pathlib import Path

# Add src to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.signals.study_card_mapper import build_study_card
from ncfd.signals.primitives import (
    S1_endpoint_changed, S2_underpowered_pivotal, S3_subgroup_only_no_multiplicity,
    S4_itt_vs_pp_dropout, S5_implausible_vs_graveyard, S6_many_interims_no_spending,
    S7_single_arm_where_rct_standard, S7b_randomized_withdrawal_after_OLE, S8_pvalue_cusp_or_heaping, S9_os_pfs_contradiction
)
from ncfd.signals.gates import evaluate_all_gates
from ncfd.signals.scoring import score_trial, get_default_prior_pi
from ncfd.signals.types import SignalResult


def test_signals_pipeline_from_extraction():
    """Test full signals pipeline from extraction results."""
    
    # Load PMC2978916 extraction results
    extraction_file = "test_outputs/pmc2978916_debug/extraction_results.json"
    if not os.path.exists(extraction_file):
        print(f"Warning: {extraction_file} not found, skipping e2e test")
        return
    
    with open(extraction_file, 'r') as f:
        data = json.load(f)
    
    # Extract artifacts
    mc = data.get("method_card")
    rf = data.get("results_factsheet") 
    claims = data.get("claims", [])
    doc_id = data.get("doc_id") or mc.get("doc_id") if mc else "unknown"
    
    # Build Study Card
    card = build_study_card(doc_id, mc, rf, claims)
    
    # Verify Study Card structure
    assert card["study_id"] == doc_id
    assert card["single_arm"] == True
    assert card["primary_type"] == "proportion"
    assert card["analysis_plan"]["planned_interims"] == 1  # From Gehan claim
    
    # Run all signals
    signals = {
        "S1": SignalResult(fired=False, severity="L", reason="no trial versions"),
        "S2": S2_underpowered_pivotal(card),
        "S3": S3_subgroup_only_no_multiplicity(card),
        "S4": S4_itt_vs_pp_dropout(card),
        "S5": S5_implausible_vs_graveyard(card, {}),
        "S6": S6_many_interims_no_spending(card),
        "S7": S7_single_arm_where_rct_standard(card, {}),
        "S7b": S7b_randomized_withdrawal_after_OLE(card),
        "S8": S8_pvalue_cusp_or_heaping(card),
        "S9": S9_os_pfs_contradiction(card),
    }
    
    # Verify all signals ran
    assert len(signals) == 10
    for signal_id, signal in signals.items():
        assert hasattr(signal, 'fired')
        assert hasattr(signal, 'severity')
        assert hasattr(signal, 'reason')
    
    # Evaluate gates
    gates = evaluate_all_gates(signals)
    
    # Verify all gates evaluated
    assert len(gates) == 4
    assert "G1" in gates
    assert "G2" in gates
    assert "G3" in gates
    assert "G4" in gates
    
    # Score trial
    prior_pi = get_default_prior_pi("unknown", "phase_2", "single_arm")
    score = score_trial(
        trial_id=doc_id,
        prior_pi=prior_pi,
        signals=signals,
        gates=gates,
        evidence_span="test_span",
        source_study_id=doc_id
    )
    
    # Verify scoring results
    assert score.trial_id == doc_id
    assert score.prior_pi == prior_pi
    assert score.p_fail >= 0.0 and score.p_fail <= 1.0
    assert len(score.fired_signals) >= 0
    assert len(score.fired_gates) >= 0
    
    # For PMC2978916, we expect no signals to fire (Phase II study)
    fired_signals = [s for s in signals.values() if s.fired]
    fired_gates = [g for g in gates.values() if g.fired]
    
    print(f"PMC2978916 Results:")
    print(f"  Signals fired: {len(fired_signals)}")
    print(f"  Gates fired: {len(fired_gates)}")
    print(f"  P(Failure): {score.p_fail:.1%}")
    print(f"  Prior P(Failure): {score.prior_pi:.1%}")
    
    # Verify the system correctly identified this as a low-risk Phase II study
    assert len(fired_signals) == 0, f"Expected no signals to fire for Phase II study, got {len(fired_signals)}"
    assert len(fired_gates) == 0, f"Expected no gates to fire for Phase II study, got {len(fired_gates)}"


def test_signals_pipeline_with_mock_data():
    """Test signals pipeline with synthetic high-risk data."""
    
    # Create mock high-risk trial data
    mock_method_card = {
        "primary_endpoint": "ORR_RECIST",
        "is_pivotal": True,
        "design_archetype": "rct_phase3",
        "alpha_level": 0.025,
        "is_one_sided": True,
        "arms": {"t": {"n": 90, "dropout": 0.22}, "c": {"n": 90, "dropout": 0.06}},
        "primary_result": {
            "ITT": {"estimate": 0.02, "p": 0.12},
            "PP": {"estimate": 0.15, "p": 0.02}
        },
        "subgroups": [
            {"name": "Region A", "p": 0.03, "adjusted": False, "pre_specified_interaction": False}
        ],
        "analysis_plan": {
            "planned_interims": 4,  # Many interims without alpha spending
            "assumed_p_c": 0.20,
            "assumed_delta_abs": 0.08
        }
    }
    
    mock_results = {
        "results": [
            {"metric": "orr_recist", "value": 15.8, "units": "percent"}
        ]
    }
    
    mock_claims = [
        {"type": "design_fact", "proposition": "blinding: open-label"}
    ]
    
    # Build Study Card
    card = build_study_card("MOCK_HIGH_RISK", mock_method_card, mock_results, mock_claims)
    
    # Run signals
    signals = {
        "S1": SignalResult(fired=False, severity="L", reason="no trial versions"),
        "S2": S2_underpowered_pivotal(card),
        "S3": S3_subgroup_only_no_multiplicity(card),
        "S4": S4_itt_vs_pp_dropout(card),
        "S5": S5_implausible_vs_graveyard(card, {}),
        "S6": S6_many_interims_no_spending(card),
        "S7": S7_single_arm_where_rct_standard(card, {}),
        "S8": S8_pvalue_cusp_or_heaping(card),
        "S9": S9_os_pfs_contradiction(card),
    }
    
    # Evaluate gates
    gates = evaluate_all_gates(signals)
    
    # Score trial
    prior_pi = get_default_prior_pi("unknown", "phase_3", "rct")
    score = score_trial(
        trial_id="MOCK_HIGH_RISK",
        prior_pi=prior_pi,
        signals=signals,
        gates=gates
    )
    
    # This mock trial should trigger multiple signals
    fired_signals = [s for s in signals.values() if s.fired]
    fired_gates = [g for g in gates.values() if g.fired]
    
    print(f"Mock High-Risk Trial Results:")
    print(f"  Signals fired: {len(fired_signals)}")
    print(f"  Gates fired: {len(fired_gates)}")
    print(f"  P(Failure): {score.p_fail:.1%}")
    print(f"  Prior P(Failure): {score.prior_pi:.1%}")
    
    # Should have multiple signals firing
    assert len(fired_signals) > 0, "Expected signals to fire for high-risk mock trial"
    assert len(fired_gates) > 0, "Expected gates to fire for high-risk mock trial"
    assert score.p_fail > prior_pi, "Expected posterior to be higher than prior for high-risk trial"


if __name__ == "__main__":
    test_signals_pipeline_from_extraction()
    test_signals_pipeline_with_mock_data()
    print("All e2e tests passed!")
