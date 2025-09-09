"""
Tests for gates G1-G4 and scoring system.

Validates specification-compliant gate logic and traceable scoring.
"""

import pytest
import math
from ncfd.signals.types import SignalResult, GateResult, ScoreResult, GateConfig
from ncfd.signals.gates import (
    G1_alpha_meltdown,
    G2_analysis_gaming,
    G3_plausibility,
    G4_p_hacking,
    evaluate_all_gates,
    get_fired_gates,
    calculate_total_likelihood_ratio
)
from ncfd.signals.scoring import (
    score_trial,
    compute_p_fail,
    load_gate_lr_config,
    logit,
    inv_logit,
    get_default_prior_pi,
    interpret_score,
    format_score_summary
)


class TestGateLogic:
    """Test gate logic matches specification."""
    
    def test_G1_alpha_meltdown_spec_compliance(self):
        """Test G1 = S1 & S2 (both required)."""
        # Both S1 and S2 fired -> G1 should fire
        signals = {
            "S1": SignalResult(id="S1", fired=True, value=0.05),
            "S2": SignalResult(id="S2", fired=True, value=0.65)
        }
        result = G1_alpha_meltdown(signals)
        assert result.fired
        assert result.id == "G1"
        assert result.status == "ok"
        assert "S1" in result.supporting_signals
        assert "S2" in result.supporting_signals
        
        # Only S1 fired -> G1 should not fire
        signals = {
            "S1": SignalResult(id="S1", fired=True, value=0.05),
            "S2": SignalResult(id="S2", fired=False)
        }
        result = G1_alpha_meltdown(signals)
        assert not result.fired
        assert result.status == "ok"
        
        # Only S2 fired -> G1 should not fire
        signals = {
            "S1": SignalResult(id="S1", fired=False),
            "S2": SignalResult(id="S2", fired=True, value=0.65)
        }
        result = G1_alpha_meltdown(signals)
        assert not result.fired
        assert result.status == "ok"
        
        # Neither fired -> G1 should not fire
        signals = {
            "S1": SignalResult(id="S1", fired=False),
            "S2": SignalResult(id="S2", fired=False)
        }
        result = G1_alpha_meltdown(signals)
        assert not result.fired
        assert result.status == "ok"
    
    def test_G1_alpha_meltdown_missing_inputs(self):
        """Test G1 handles missing inputs correctly."""
        # Missing S1
        signals = {
            "S2": SignalResult(id="S2", fired=True)
        }
        result = G1_alpha_meltdown(signals)
        assert not result.fired
        assert result.status == "insufficient_inputs"
        assert "S1" in result.rationale
        
        # Missing S2
        signals = {
            "S1": SignalResult(id="S1", fired=True)
        }
        result = G1_alpha_meltdown(signals)
        assert not result.fired
        assert result.status == "insufficient_inputs"
        assert "S2" in result.rationale
        
        # S1.fired is None
        signals = {
            "S1": SignalResult(id="S1", fired=None),
            "S2": SignalResult(id="S2", fired=True)
        }
        result = G1_alpha_meltdown(signals)
        assert not result.fired
        assert result.status == "insufficient_inputs"
    
    def test_G2_analysis_gaming_spec_compliance(self):
        """Test G2 = S3 & S4 (both required)."""
        # Both S3 and S4 fired -> G2 should fire
        signals = {
            "S3": SignalResult(id="S3", fired=True, value=0.02),
            "S4": SignalResult(id="S4", fired=True, value=0.25)
        }
        result = G2_analysis_gaming(signals)
        assert result.fired
        assert result.id == "G2"
        assert result.status == "ok"
        assert "S3" in result.supporting_signals
        assert "S4" in result.supporting_signals
        
        # Only S3 fired -> G2 should not fire
        signals = {
            "S3": SignalResult(id="S3", fired=True),
            "S4": SignalResult(id="S4", fired=False)
        }
        result = G2_analysis_gaming(signals)
        assert not result.fired
        assert result.status == "ok"
    
    def test_G3_plausibility_spec_compliance(self):
        """Test G3 = S5 & (S7 | S6)."""
        # S5 and S6 fired -> G3 should fire
        signals = {
            "S5": SignalResult(id="S5", fired=True, value=0.85),
            "S6": SignalResult(id="S6", fired=True),
            "S7": SignalResult(id="S7", fired=False)
        }
        result = G3_plausibility(signals)
        assert result.fired
        assert result.id == "G3"
        assert "S5" in result.supporting_signals
        assert "S6" in result.supporting_signals
        
        # S5 and S7 fired -> G3 should fire
        signals = {
            "S5": SignalResult(id="S5", fired=True),
            "S6": SignalResult(id="S6", fired=False),
            "S7": SignalResult(id="S7", fired=True)
        }
        result = G3_plausibility(signals)
        assert result.fired
        assert "S5" in result.supporting_signals
        assert "S7" in result.supporting_signals
        
        # Only S5 fired -> G3 should not fire
        signals = {
            "S5": SignalResult(id="S5", fired=True),
            "S6": SignalResult(id="S6", fired=False),
            "S7": SignalResult(id="S7", fired=False)
        }
        result = G3_plausibility(signals)
        assert not result.fired
        assert result.status == "ok"
    
    def test_G4_p_hacking_spec_compliance(self):
        """Test G4 = S8 & (S1 | S3)."""
        # S8 and S1 fired -> G4 should fire
        signals = {
            "S1": SignalResult(id="S1", fired=True),
            "S3": SignalResult(id="S3", fired=False),
            "S8": SignalResult(id="S8", fired=True, value=0.047)
        }
        result = G4_p_hacking(signals)
        assert result.fired
        assert result.id == "G4"
        assert "S1" in result.supporting_signals
        assert "S8" in result.supporting_signals
        
        # S8 and S3 fired -> G4 should fire
        signals = {
            "S1": SignalResult(id="S1", fired=False),
            "S3": SignalResult(id="S3", fired=True),
            "S8": SignalResult(id="S8", fired=True)
        }
        result = G4_p_hacking(signals)
        assert result.fired
        assert "S3" in result.supporting_signals
        assert "S8" in result.supporting_signals
        
        # Only S8 fired -> G4 should not fire
        signals = {
            "S1": SignalResult(id="S1", fired=False),
            "S3": SignalResult(id="S3", fired=False),
            "S8": SignalResult(id="S8", fired=True)
        }
        result = G4_p_hacking(signals)
        assert not result.fired
        assert result.status == "ok"
    
    def test_evaluate_all_gates(self):
        """Test evaluating all gates together."""
        signals = {
            "S1": SignalResult(id="S1", fired=True, value=0.05),
            "S2": SignalResult(id="S2", fired=True, value=0.65),
            "S3": SignalResult(id="S3", fired=True, value=0.02),
            "S4": SignalResult(id="S4", fired=True, value=0.25),
            "S5": SignalResult(id="S5", fired=True, value=0.85),
            "S6": SignalResult(id="S6", fired=True),
            "S7": SignalResult(id="S7", fired=False),
            "S8": SignalResult(id="S8", fired=True, value=0.047)
        }
        
        gates = evaluate_all_gates(signals)
        
        assert len(gates) == 4
        assert gates["G1"].fired  # S1 & S2
        assert gates["G2"].fired  # S3 & S4
        assert gates["G3"].fired  # S5 & (S6 | S7)
        assert gates["G4"].fired  # S8 & (S1 | S3)
        
        # Check all gates have correct IDs
        for gate_id in ["G1", "G2", "G3", "G4"]:
            assert gates[gate_id].id == gate_id


class TestScoringMath:
    """Test scoring mathematics."""
    
    def test_logit_functions(self):
        """Test logit and inverse logit functions."""
        # Test edge cases
        assert logit(0.0) == float('-inf')
        assert logit(1.0) == float('inf')
        assert inv_logit(float('-inf')) == 0.0
        assert inv_logit(float('inf')) == 1.0
        
        # Test round trip
        p = 0.65
        z = logit(p)
        p_recovered = inv_logit(z)
        assert abs(p - p_recovered) < 1e-10
        
        # Test symmetry
        p = 0.3
        z = logit(p)
        assert abs(z + logit(1 - p)) < 1e-10
    
    def test_compute_p_fail_basic(self):
        """Test basic posterior computation."""
        prior_pi = 0.65
        gates = {
            "G1": GateResult(id="G1", fired=True),
            "G2": GateResult(id="G2", fired=False),
            "G3": GateResult(id="G3", fired=True),
            "G4": GateResult(id="G4", fired=False)
        }
        lr_table = {"G1": 3.5, "G2": 3.0, "G3": 4.2, "G4": 2.5}
        
        result = compute_p_fail(prior_pi, gates, lr_table)
        
        # Manual calculation
        z_prior = logit(0.65)
        z_post = z_prior + math.log(3.5) + math.log(4.2)
        expected_p = inv_logit(z_post)
        
        assert abs(result.p_fail - expected_p) < 1e-10
        assert result.fired_gates == ["G1", "G3"]
        assert abs(result.sum_log_lr - (math.log(3.5) + math.log(4.2))) < 1e-10
    
    def test_compute_p_fail_no_gates_fired(self):
        """Test posterior when no gates fire."""
        prior_pi = 0.65
        gates = {
            "G1": GateResult(id="G1", fired=False),
            "G2": GateResult(id="G2", fired=False)
        }
        lr_table = {"G1": 3.5, "G2": 3.0}
        
        result = compute_p_fail(prior_pi, gates, lr_table)
        
        assert abs(result.p_fail - prior_pi) < 1e-10
        assert result.fired_gates == []
        assert result.sum_log_lr == 0.0
    
    def test_compute_p_fail_stop_rule_override(self):
        """Test stop rule override."""
        prior_pi = 0.65
        gates = {
            "G1": GateResult(id="G1", fired=True)
        }
        lr_table = {"G1": 3.5}
        
        result = compute_p_fail(prior_pi, gates, lr_table, stop_rule="endpoint_switch_after_LPR")
        
        assert result.p_fail == 0.99  # Max cap
        assert result.stop_rule_applied == "endpoint_switch_after_LPR"
        assert result.sum_log_lr == 0.0  # Stop rule ignores LRs
    
    def test_compute_p_fail_caps(self):
        """Test probability capping."""
        prior_pi = 0.01  # Very low prior
        gates = {
            "G1": GateResult(id="G1", fired=True),
            "G2": GateResult(id="G2", fired=True),
            "G3": GateResult(id="G3", fired=True)
        }
        lr_table = {"G1": 10.0, "G2": 10.0, "G3": 10.0}  # Very high LRs
        
        result = compute_p_fail(prior_pi, gates, lr_table, cap=(0.01, 0.99))
        
        # With prior=0.01 and 3 gates with LR=10.0 each:
        # z_prior = logit(0.01) ≈ -4.595
        # sum_log_lr = 3 * log(10.0) ≈ 6.908
        # z_post = -4.595 + 6.908 ≈ 2.313
        # p_fail = inv_logit(2.313) ≈ 0.91
        # This should NOT be capped since 0.91 < 0.99
        assert abs(result.p_fail - 0.91) < 0.01  # Should be around 0.91
        assert result.p_fail <= 0.99  # Should not exceed cap
        
        # Test actual capping with even higher LRs
        lr_table_extreme = {"G1": 100.0, "G2": 100.0, "G3": 100.0}
        result_extreme = compute_p_fail(prior_pi, gates, lr_table_extreme, cap=(0.01, 0.99))
        assert result_extreme.p_fail == 0.99  # Should be capped at max


class TestWorkedExample:
    """Test worked example from specification."""
    
    def test_worked_example_from_spec(self):
        """
        Test worked example: prior 0.65, G1+G3 fired with LR_G1=3.5, LR_G3=4.2.
        Expected: P_fail ≈ 0.97
        """
        prior_pi = 0.65
        gates = {
            "G1": GateResult(id="G1", fired=True),
            "G2": GateResult(id="G2", fired=False),
            "G3": GateResult(id="G3", fired=True),
            "G4": GateResult(id="G4", fired=False)
        }
        lr_table = {"G1": 3.5, "G2": 3.0, "G3": 4.2, "G4": 2.5}
        
        result = compute_p_fail(prior_pi, gates, lr_table)
        
        # Manual calculation
        z_prior = logit(0.65)
        z_post = z_prior + math.log(3.5) + math.log(4.2)
        expected_p = inv_logit(z_post)
        
        # Should be very high (close to 0.97)
        assert result.p_fail > 0.95
        assert abs(result.p_fail - expected_p) < 1e-10
        assert result.fired_gates == ["G1", "G3"]
        assert abs(result.sum_log_lr - (math.log(3.5) + math.log(4.2))) < 1e-10


class TestConfiguration:
    """Test configuration loading and validation."""
    
    def test_load_gate_lr_config(self):
        """Test loading gate LR configuration."""
        config = load_gate_lr_config("config/gate_lrs.yaml")
        
        assert isinstance(config, GateConfig)
        assert config.version == "2025-08-21"  # Should be string
        assert config.gates["G1"] == 3.5
        assert config.gates["G2"] == 3.0
        assert config.gates["G3"] == 4.2
        assert config.gates["G4"] == 2.5
        assert config.p_cap["min"] == 0.01
        assert config.p_cap["max"] == 0.99
        assert config.lr_caps["min"] == 0.25
        assert config.lr_caps["max"] == 10.0
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Test missing file
        with pytest.raises(ValueError):
            load_gate_lr_config("nonexistent.yaml")


class TestIntegration:
    """Test end-to-end integration."""
    
    def test_full_scoring_workflow(self):
        """Test complete scoring workflow."""
        # Create signals
        signals = {
            "S1": SignalResult(id="S1", fired=True, value=0.05),
            "S2": SignalResult(id="S2", fired=True, value=0.65),
            "S3": SignalResult(id="S3", fired=True, value=0.02),
            "S4": SignalResult(id="S4", fired=True, value=0.25),
            "S5": SignalResult(id="S5", fired=True, value=0.85),
            "S6": SignalResult(id="S6", fired=True),
            "S7": SignalResult(id="S7", fired=False),
            "S8": SignalResult(id="S8", fired=True, value=0.047)
        }
        
        # Evaluate gates
        gates = evaluate_all_gates(signals)
        
        # Load config
        config = load_gate_lr_config("config/gate_lrs.yaml")
        
        # Score trial
        result = score_trial(
            trial_id="NCT123456",
            run_id="run_2024_12_01",
            prior_pi=0.65,
            signals=signals,
            gates=gates,
            config=config
        )
        
        # Validate result
        assert result.trial_id == "NCT123456"
        assert result.run_id == "run_2024_12_01"
        assert result.prior_pi == 0.65
        assert result.config_version == "2025-08-21"  # Should be string
        assert len(result.fired_gates) == 4  # All gates should fire
        assert result.p_fail > 0.95  # Should be very high with all gates
        
        # Test interpretation
        interpretation = interpret_score(result)
        assert "CRITICAL" in interpretation
        assert "P_fail" in interpretation
    
    def test_score_summary(self):
        """Test score summary formatting."""
        # Create ScoreResult objects with all required fields
        scores = [
            ScoreResult(
                trial_id="T1", 
                run_id="R1", 
                prior_pi=0.65, 
                logit_prior=logit(0.65),
                p_fail=0.95, 
                fired_gates=["G1", "G2"]
            ),
            ScoreResult(
                trial_id="T2", 
                run_id="R1", 
                prior_pi=0.65, 
                logit_prior=logit(0.65),
                p_fail=0.75, 
                fired_gates=["G1"]
            ),
            ScoreResult(
                trial_id="T3", 
                run_id="R1", 
                prior_pi=0.65, 
                logit_prior=logit(0.65),
                p_fail=0.45, 
                fired_gates=[]
            )
        ]
        
        summary = format_score_summary(scores)
        
        assert "Score Summary (3 trials)" in summary
        assert "Critical (P≥0.9): 1" in summary
        assert "High (0.7≤P<0.9): 1" in summary
        assert "Low (P<0.5): 1" in summary
        assert "G1: 2 trials" in summary


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_signals(self):
        """Test gates with empty signals."""
        signals = {}
        gates = evaluate_all_gates(signals)
        
        for gate in gates.values():
            assert not gate.fired
            assert gate.status == "insufficient_inputs"
    
    def test_none_fired_values(self):
        """Test handling of None fired values."""
        signals = {
            "S1": SignalResult(id="S1", fired=None),
            "S2": SignalResult(id="S2", fired=True)
        }
        
        result = G1_alpha_meltdown(signals)
        assert not result.fired
        assert result.status == "insufficient_inputs"
    
    def test_missing_gate_in_lr_table(self):
        """Test handling of missing gates in LR table."""
        prior_pi = 0.65
        gates = {
            "G1": GateResult(id="G1", fired=True),
            "G99": GateResult(id="G99", fired=True)  # Not in LR table
        }
        lr_table = {"G1": 3.5}
        
        result = compute_p_fail(prior_pi, gates, lr_table)
        
        # G99 should use default LR of 1.0 (no effect)
        assert result.fired_gates == ["G1", "G99"]
        assert abs(result.sum_log_lr - math.log(3.5)) < 1e-10  # Only G1 contributes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
