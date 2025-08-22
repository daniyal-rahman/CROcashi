"""
Tests for signal primitives and gates.

This module tests the core signal detection logic and gate evaluation.
"""

import pytest
from datetime import datetime, date
from ncfd.signals import (
    SignalResult, GateResult,
    S1_endpoint_changed, S2_underpowered_pivotal,
    S3_subgroup_only_no_multiplicity, S4_itt_vs_pp_dropout,
    S5_implausible_vs_graveyard, S6_many_interims_no_spending,
    S7_single_arm_where_rct_standard, S8_pvalue_cusp_or_heaping,
    S9_os_pfs_contradiction,
    G1_alpha_meltdown, G2_analysis_gaming, G3_plausibility, G4_p_hacking,
    evaluate_all_signals, evaluate_all_gates
)


class TestSignalPrimitives:
    """Test individual signal primitives."""
    
    def test_S1_endpoint_changed_no_versions(self):
        """Test S1 with no trial versions."""
        result = S1_endpoint_changed([])
        assert not result.fired
        assert result.severity == "L"
        assert "single version" in result.reason
    
    def test_S1_endpoint_changed_single_version(self):
        """Test S1 with single trial version."""
        versions = [{
            "version_id": 1,
            "primary_endpoint_text": "PFS at 12 months",
            "captured_at": datetime(2025, 1, 1),
            "est_primary_completion_date": date(2026, 1, 1)
        }]
        result = S1_endpoint_changed(versions)
        assert not result.fired
        assert result.severity == "L"
    
    def test_S2_underpowered_pivotal_not_pivotal(self):
        """Test S2 with non-pivotal trial."""
        card = {"is_pivotal": False}
        result = S2_underpowered_pivotal(card)
        assert not result.fired
        assert result.severity == "L"
        assert "not pivotal" in result.reason
    
    def test_S2_underpowered_pivotal_missing_sample_sizes(self):
        """Test S2 with missing sample sizes."""
        card = {
            "is_pivotal": True,
            "primary_type": "proportion",
            "arms": {"t": {}, "c": {}}
        }
        result = S2_underpowered_pivotal(card)
        assert not result.fired
        assert result.severity == "L"
        assert "missing sample sizes" in result.reason
    
    def test_S3_subgroup_only_no_multiplicity_overall_sig(self):
        """Test S3 with overall significant result."""
        card = {
            "primary_result": {"ITT": {"p": 0.03}},
            "subgroups": []
        }
        result = S3_subgroup_only_no_multiplicity(card)
        assert not result.fired
        assert result.severity == "L"
        assert "overall ITT significant" in result.reason
    
    def test_S4_itt_vs_pp_dropout_no_pp(self):
        """Test S4 with no per-protocol analysis."""
        card = {
            "primary_result": {"ITT": {"p": 0.1, "estimate": 0.05}},
            "arms": {"t": {"dropout": 0.1}, "c": {"dropout": 0.05}}
        }
        result = S4_itt_vs_pp_dropout(card)
        assert not result.fired
        assert result.severity == "L"
        assert "no PP set" in result.reason
    
    def test_S5_implausible_vs_graveyard_not_graveyard(self):
        """Test S5 with non-graveyard class."""
        card = {"primary_result": {"effect_size": 0.5}}
        class_meta = {"graveyard": False}
        result = S5_implausible_vs_graveyard(card, class_meta)
        assert not result.fired
        assert result.severity == "L"
        assert "class not graveyard" in result.reason
    
    def test_S6_many_interims_no_spending_adequate_control(self):
        """Test S6 with adequate interim control."""
        card = {
            "analysis_plan": {
                "planned_interims": 1,
                "alpha_spending": "O'Brien-Fleming"
            }
        }
        result = S6_many_interims_no_spending(card)
        assert not result.fired
        assert result.severity == "L"
        assert "interim control adequate" in result.reason
    
    def test_S7_single_arm_where_rct_standard_not_pivotal(self):
        """Test S7 with non-pivotal trial."""
        card = {"is_pivotal": False, "single_arm": True}
        result = S7_single_arm_where_rct_standard(card, True)
        assert not result.fired
        assert result.severity == "L"
        assert "not pivotal" in result.reason
    
    def test_S8_pvalue_cusp_or_heaping_no_cusp(self):
        """Test S8 with p-value not in cusp range."""
        card = {"primary_result": {"ITT": {"p": 0.1}}}
        result = S8_pvalue_cusp_or_heaping(card)
        assert not result.fired
        assert result.severity == "L"
        assert "no cusp/heaping" in result.reason
    
    def test_S9_os_pfs_contradiction_missing_endpoints(self):
        """Test S9 with missing endpoint data."""
        card = {"primary_result": {"ITT": {"p": 0.05}}}
        result = S9_os_pfs_contradiction(card)
        assert not result.fired
        assert result.severity == "L"
        assert "missing endpoints" in result.reason


class TestGateLogic:
    """Test gate evaluation logic."""
    
    def test_G1_alpha_meltdown_missing_signals(self):
        """Test G1 with missing signals."""
        signals = {}
        result = G1_alpha_meltdown(signals)
        assert not result.fired
        assert "Missing S1 or S2 signals" in result.rationale_text
    
    def test_G1_alpha_meltdown_not_both_fired(self):
        """Test G1 when not both S1 and S2 fire."""
        signals = {
            "S1": SignalResult(True, "H", reason="Endpoint changed"),
            "S2": SignalResult(False, "L", reason="Adequate power")
        }
        result = G1_alpha_meltdown(signals)
        assert not result.fired
        assert "S1 and S2 not both fired" in result.rationale_text
    
    def test_G2_analysis_gaming_both_fired(self):
        """Test G2 when both S3 and S4 fire."""
        signals = {
            "S3": SignalResult(True, "M", reason="Subgroup-only wins"),
            "S4": SignalResult(True, "H", reason="ITT/PP contradiction")
        }
        result = G2_analysis_gaming(signals)
        assert result.fired
        assert result.severity == "H"  # Should be H due to S4 being H
        assert result.lr_used == 15.0
        assert "Analysis gaming" in result.rationale_text
    
    def test_G3_plausibility_missing_S5(self):
        """Test G3 with missing S5 signal."""
        signals = {
            "S6": SignalResult(True, "M", reason="Interim issues")
        }
        result = G3_plausibility(signals)
        assert not result.fired
        assert "Missing S5 signal" in result.rationale_text
    
    def test_G4_p_hacking_S8_not_fired(self):
        """Test G4 when S8 doesn't fire."""
        signals = {
            "S8": SignalResult(False, "L", reason="No p-value issues"),
            "S1": SignalResult(True, "M", reason="Endpoint changed")
        }
        result = G4_p_hacking(signals)
        assert not result.fired
        assert "S8 not fired" in result.rationale_text


class TestIntegration:
    """Test integration of signals and gates."""
    
    def test_evaluate_all_signals(self):
        """Test evaluation of all signals."""
        card = {
            "is_pivotal": True,
            "primary_type": "proportion",
            "arms": {"t": {"n": 100, "dropout": 0.1}, "c": {"n": 100, "dropout": 0.1}},
            "analysis_plan": {"alpha": 0.025, "one_sided": True, "assumed_p_c": 0.2, "assumed_delta_abs": 0.15},
            "primary_result": {"ITT": {"p": 0.1, "estimate": 0.05}},
            "subgroups": []
        }
        
        results = evaluate_all_signals(card)
        
        # Should have results for all signals that don't require additional data
        assert "S2" in results
        assert "S3" in results
        assert "S4" in results
        assert "S6" in results
        assert "S7" in results
        assert "S8" in results
        assert "S9" in results
        
        # S1 and S5 require additional data
        assert "S1" not in results
        assert "S5" not in results
    
    def test_evaluate_all_gates(self):
        """Test evaluation of all gates."""
        signals = {
            "S1": SignalResult(True, "H", reason="Endpoint changed"),
            "S2": SignalResult(True, "M", reason="Underpowered"),
            "S3": SignalResult(False, "L", reason="No subgroup issues"),
            "S4": SignalResult(False, "L", reason="No ITT/PP issues"),
            "S5": SignalResult(False, "L", reason="Effect size OK"),
            "S6": SignalResult(False, "L", reason="Interim control OK"),
            "S7": SignalResult(False, "L", reason="RCT design"),
            "S8": SignalResult(False, "L", reason="No p-value issues"),
            "S9": SignalResult(False, "L", reason="No OS/PFS contradiction")
        }
        
        gates = evaluate_all_gates(signals)
        
        # G1 should fire (S1 and S2 both fired)
        assert gates["G1"].fired
        assert gates["G1"].severity == "H"  # S1 is H
        
        # Other gates should not fire
        assert not gates["G2"].fired
        assert not gates["G3"].fired
        assert not gates["G4"].fired


if __name__ == "__main__":
    pytest.main([__file__])
