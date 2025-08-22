"""
Tests for the scoring system.

This module tests the core scoring functionality, calibration,
and integration with signals and gates.
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal

from ncfd.signals import (
    SignalResult, GateResult, evaluate_all_signals, evaluate_all_gates
)
from ncfd.scoring import (
    ScoreResult, ScoringEngine, score_single_trial,
    LikelihoodRatioCalibrator, PriorRateCalibrator,
    calibrate_scoring_system, get_calibrated_config
)


class TestScoreResult:
    """Test the ScoreResult dataclass."""
    
    def test_score_result_creation(self):
        """Test creating a ScoreResult instance."""
        score = ScoreResult(
            trial_id=123,
            run_id="test_run_001",
            prior_pi=0.15,
            logit_prior=-1.7346,
            sum_log_lr=0.6931,
            logit_post=-1.0415,
            p_fail=0.26
        )
        
        assert score.trial_id == 123
        assert score.run_id == "test_run_001"
        assert score.prior_pi == 0.15
        assert score.p_fail == 0.26
        assert score.scored_at is not None
        assert score.metadata == {}
    
    def test_score_result_defaults(self):
        """Test ScoreResult with default values."""
        score = ScoreResult(
            trial_id=456,
            run_id="test_run_002",
            prior_pi=0.20,
            logit_prior=-1.3863,
            sum_log_lr=0.0,
            logit_post=-1.3863,
            p_fail=0.20
        )
        
        assert score.scored_at is not None
        assert score.metadata == {}


class TestScoringEngine:
    """Test the ScoringEngine class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ScoringEngine()
        
        # Sample trial data
        self.trial_data = {
            "trial_id": 123,
            "is_pivotal": True,
            "indication": "oncology",
            "phase": "phase_3",
            "sponsor_experience": "experienced",
            "primary_endpoint_type": "survival",
            "est_primary_completion_date": date(2025, 12, 31)
        }
        
        # Sample gates (none fired)
        self.gates = {
            "G1": GateResult(
                fired=False, G_id="G1", supporting_S_ids=[],
                lr_used=None, rationale_text="No signals fired"
            ),
            "G2": GateResult(
                fired=False, G_id="G2", supporting_S_ids=[],
                lr_used=None, rationale_text="No signals fired"
            ),
            "G3": GateResult(
                fired=False, G_id="G3", supporting_S_ids=[],
                lr_used=None, rationale_text="No signals fired"
            ),
            "G4": GateResult(
                fired=False, G_id="G4", supporting_S_ids=[],
                lr_used=None, rationale_text="No signals fired"
            )
        }
    
    def test_calculate_prior_failure_rate_basic(self):
        """Test basic prior failure rate calculation."""
        prior = self.engine.calculate_prior_failure_rate(self.trial_data)
        
        # Should be higher than default due to pivotal + oncology + phase_3
        assert prior > 0.15
        assert prior <= 0.50  # Max prior
        assert prior >= 0.01  # Min prior
    
    def test_calculate_prior_failure_rate_non_pivotal(self):
        """Test prior calculation for non-pivotal trials."""
        trial_data = self.trial_data.copy()
        trial_data["is_pivotal"] = False
        
        prior = self.engine.calculate_prior_failure_rate(trial_data)
        assert prior < 0.20  # Should be lower than pivotal
    
    def test_calculate_prior_failure_rate_rare_disease(self):
        """Test prior calculation for rare disease trials."""
        trial_data = self.trial_data.copy()
        trial_data["indication"] = "rare_disease"
        
        prior = self.engine.calculate_prior_failure_rate(trial_data)
        assert prior < 0.20  # Should be lower than oncology
    
    def test_calculate_prior_failure_rate_phase_2(self):
        """Test prior calculation for phase 2 trials."""
        trial_data = self.trial_data.copy()
        trial_data["phase"] = "phase_2"
        
        prior = self.engine.calculate_prior_failure_rate(trial_data)
        assert prior < 0.25  # Should be lower than phase 3
    
    def test_apply_stop_rules_no_rules(self):
        """Test stop rules when none apply."""
        result = self.engine.apply_stop_rules(self.trial_data, self.gates)
        assert result is None
    
    def test_apply_stop_rules_endpoint_switched(self):
        """Test stop rule for endpoint switched after LPR."""
        trial_data = self.trial_data.copy()
        trial_data["endpoint_changed_after_lpr"] = True
        
        # Make G1 fire
        gates = self.gates.copy()
        gates["G1"] = GateResult(
            fired=True, G_id="G1", supporting_S_ids=["S1", "S2"],
            lr_used=10.0, rationale_text="Alpha meltdown"
        )
        
        result = self.engine.apply_stop_rules(trial_data, gates)
        assert result == 0.97  # Stop rule threshold
    
    def test_apply_stop_rules_pp_only_success(self):
        """Test stop rule for PP-only success with high dropout."""
        trial_data = self.trial_data.copy()
        trial_data["pp_only_success"] = True
        trial_data["dropout_asymmetry"] = 0.25  # > 0.20 threshold
        
        result = self.engine.apply_stop_rules(trial_data, self.gates)
        assert result == 0.97  # Stop rule threshold
    
    def test_apply_stop_rules_multiple_high_severity(self):
        """Test stop rule for multiple high severity gates."""
        # Make two gates fire with high severity
        gates = self.gates.copy()
        gates["G1"] = GateResult(
            fired=True, G_id="G1", supporting_S_ids=["S1", "S2"],
            lr_used=10.0, rationale_text="Alpha meltdown", severity="H"
        )
        gates["G2"] = GateResult(
            fired=True, G_id="G2", supporting_S_ids=["S3", "S4"],
            lr_used=15.0, rationale_text="Analysis gaming", severity="H"
        )
        
        result = self.engine.apply_stop_rules(self.trial_data, gates)
        assert result == 0.95  # Stop rule threshold
    
    def test_calculate_likelihood_ratios_no_gates_fired(self):
        """Test LR calculation when no gates fire."""
        lrs = self.engine.calculate_likelihood_ratios(self.gates)
        assert lrs == {}
    
    def test_calculate_likelihood_ratios_with_gates_fired(self):
        """Test LR calculation when gates fire."""
        # Make G1 fire
        gates = self.gates.copy()
        gates["G1"] = GateResult(
            fired=True, G_id="G1", supporting_S_ids=["S1", "S2"],
            lr_used=12.0, rationale_text="Alpha meltdown", severity="H"
        )
        
        lrs = self.engine.calculate_likelihood_ratios(gates)
        assert "G1" in lrs
        assert lrs["G1"] == 12.0
    
    def test_calculate_likelihood_ratios_fallback_to_calibrated(self):
        """Test LR calculation falls back to calibrated values."""
        # Make G1 fire without explicit LR
        gates = self.gates.copy()
        gates["G1"] = GateResult(
            fired=True, G_id="G1", supporting_S_ids=["S1", "S2"],
            lr_used=None, rationale_text="Alpha meltdown", severity="H"
        )
        
        lrs = self.engine.calculate_likelihood_ratios(gates)
        assert "G1" in lrs
        assert lrs["G1"] == 10.0  # Default calibrated value for G1-H
    
    def test_calculate_posterior_probability_no_lrs(self):
        """Test posterior calculation with no likelihood ratios."""
        prior = 0.15
        lrs = {}
        
        posterior = self.engine.calculate_posterior_probability(prior, lrs)
        assert posterior == prior  # Should equal prior when no LRs
    
    def test_calculate_posterior_probability_with_lrs(self):
        """Test posterior calculation with likelihood ratios."""
        prior = 0.15
        lrs = {"G1": 10.0, "G2": 15.0}
        
        posterior = self.engine.calculate_posterior_probability(prior, lrs)
        assert posterior > prior  # Should increase with risk-increasing LRs
        assert posterior <= 1.0  # Should not exceed 1.0
    
    def test_should_freeze_features_far_from_completion(self):
        """Test feature freezing when far from completion."""
        trial_data = self.trial_data.copy()
        trial_data["est_primary_completion_date"] = date(2026, 12, 31)  # Far future
        
        should_freeze = self.engine.should_freeze_features(trial_data)
        assert should_freeze is False
    
    def test_should_freeze_features_within_window(self):
        """Test feature freezing when within freeze window."""
        # Set completion date to be within freeze window
        freeze_date = datetime.now() + timedelta(days=10)  # Within 14-day window
        trial_data = self.trial_data.copy()
        trial_data["est_primary_completion_date"] = freeze_date.date()
        
        should_freeze = self.engine.should_freeze_features(trial_data)
        assert should_freeze is True
    
    def test_score_trial_normal_scoring(self):
        """Test normal trial scoring without stop rules."""
        score = self.engine.score_trial(123, self.trial_data, self.gates, "test_run")
        
        assert score.trial_id == 123
        assert score.run_id == "test_run"
        assert score.prior_pi > 0.15  # Should be higher due to trial characteristics
        assert score.p_fail >= score.prior_pi  # Should increase or stay the same with risk factors
        assert score.metadata["stop_rule_applied"] is False
    
    def test_score_trial_with_stop_rule(self):
        """Test trial scoring with stop rule applied."""
        trial_data = self.trial_data.copy()
        trial_data["endpoint_changed_after_lpr"] = True
        
        gates = self.gates.copy()
        gates["G1"] = GateResult(
            fired=True, G_id="G1", supporting_S_ids=["S1", "S2"],
            lr_used=10.0, rationale_text="Alpha meltdown"
        )
        
        score = self.engine.score_trial(123, trial_data, gates, "test_run")
        
        assert score.p_fail == 0.97  # Stop rule probability
        assert score.metadata["stop_rule_applied"] is True
        assert score.metadata["stop_rule_type"] == "manual_override"
    
    def test_batch_score_trials(self):
        """Test batch scoring of multiple trials."""
        trials_data = [
            self.trial_data.copy(),
            {**self.trial_data, "trial_id": 456, "is_pivotal": False}
        ]
        
        gates_data = {
            123: self.gates,
            456: self.gates
        }
        
        scores = self.engine.batch_score_trials(trials_data, gates_data, "batch_run")
        
        assert len(scores) == 2
        assert scores[0].trial_id == 123
        assert scores[1].trial_id == 456
        assert scores[0].p_fail > scores[1].p_fail  # Pivotal should have higher risk
    
    def test_get_scoring_summary(self):
        """Test scoring summary generation."""
        # Create some sample scores
        scores = [
            ScoreResult(123, "run1", 0.15, -1.7346, 0.0, -1.7346, 0.15),
            ScoreResult(456, "run1", 0.20, -1.3863, 0.6931, -0.6932, 0.33),
            ScoreResult(789, "run1", 0.25, -1.0986, 1.3863, 0.2877, 0.57)
        ]
        
        summary = self.engine.get_scoring_summary(scores)
        
        assert summary["total_trials"] == 3
        assert summary["risk_breakdown"]["low_risk"] == 2
        assert summary["risk_breakdown"]["medium_risk"] == 1
        assert summary["risk_breakdown"]["high_risk"] == 0
        assert summary["statistics"]["average_p_fail"] == 0.35


class TestLikelihoodRatioCalibrator:
    """Test the LikelihoodRatioCalibrator class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calibrator = LikelihoodRatioCalibrator()
        
        # Sample historical data
        self.historical_data = [
            {
                "trial_id": 1,
                "actual_outcome": True,  # Failed
                "gates_fired": ["G1"],
                "gate_severities": {"G1": "H"}
            },
            {
                "trial_id": 2,
                "actual_outcome": False,  # Succeeded
                "gates_fired": ["G1"],
                "gate_severities": {"G1": "H"}
            },
            {
                "trial_id": 3,
                "actual_outcome": True,  # Failed
                "gates_fired": ["G2"],
                "gate_severities": {"G2": "M"}
            },
            {
                "trial_id": 4,
                "actual_outcome": False,  # Succeeded
                "gates_fired": [],
                "gate_severities": {}
            }
        ]
    
    def test_calibrate_from_historical_data(self):
        """Test calibration from historical data."""
        calibrated_lrs = self.calibrator.calibrate_from_historical_data(self.historical_data)
        
        # Should have calibrated LRs for gates that fired
        assert "G1" in calibrated_lrs
        assert "G2" in calibrated_lrs
        
        # G1 should have both H and M severities
        assert "H" in calibrated_lrs["G1"]
        assert "M" in calibrated_lrs["G1"]
    
    def test_calibrate_from_empty_data(self):
        """Test calibration with empty historical data."""
        calibrated_lrs = self.calibrator.calibrate_from_historical_data([])
        
        # Should return default LRs
        assert "G1" in calibrated_lrs
        assert calibrated_lrs["G1"]["H"] == 10.0
        assert calibrated_lrs["G1"]["M"] == 5.0
    
    def test_save_and_load_calibration(self, tmp_path):
        """Test saving and loading calibration results."""
        # Calibrate first
        self.calibrator.calibrate_from_historical_data(self.historical_data)
        
        # Save to temporary file
        filepath = tmp_path / "calibration.json"
        self.calibrator.save_calibration(str(filepath))
        
        # Create new calibrator and load
        new_calibrator = LikelihoodRatioCalibrator()
        new_calibrator.load_calibration(str(filepath))
        
        # Should have same calibrated LRs
        assert new_calibrator.calibrated_lrs == self.calibrator.calibrated_lrs


class TestPriorRateCalibrator:
    """Test the PriorRateCalibrator class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calibrator = PriorRateCalibrator()
        
        # Sample historical data
        self.historical_data = [
            {"trial_id": 1, "actual_outcome": True, "is_pivotal": True, "indication": "oncology"},
            {"trial_id": 2, "actual_outcome": False, "is_pivotal": True, "indication": "oncology"},
            {"trial_id": 3, "actual_outcome": True, "is_pivotal": False, "indication": "rare_disease"},
            {"trial_id": 4, "actual_outcome": False, "is_pivotal": False, "indication": "rare_disease"},
            {"trial_id": 5, "actual_outcome": False, "is_pivotal": False, "indication": "rare_disease"}
        ]
    
    def test_calibrate_from_historical_data(self):
        """Test calibration from historical data."""
        calibrated_priors = self.calibrator.calibrate_from_historical_data(self.historical_data)
        
        # Should have calibrated priors for different categories
        assert "pivotal" in calibrated_priors
        assert "non_pivotal" in calibrated_priors
        assert "oncology" in calibrated_priors
        assert "rare_disease" in calibrated_priors
        
        # Pivotal should have higher prior than non-pivotal
        assert calibrated_priors["pivotal"] > calibrated_priors["non_pivotal"]
    
    def test_calibrate_from_empty_data(self):
        """Test calibration with empty historical data."""
        calibrated_priors = self.calibrator.calibrate_from_historical_data([])
        
        # Should return default priors
        assert "pivotal" in calibrated_priors
        assert calibrated_priors["pivotal"] == 0.18
    
    def test_save_and_load_calibration(self, tmp_path):
        """Test saving and loading calibration results."""
        # Calibrate first
        self.calibrator.calibrate_from_historical_data(self.historical_data)
        
        # Save to temporary file
        filepath = tmp_path / "priors_calibration.json"
        self.calibrator.save_calibration(str(filepath))
        
        # Create new calibrator and load
        new_calibrator = PriorRateCalibrator()
        new_calibrator.load_calibration(str(filepath))
        
        # Should have same calibrated priors
        assert new_calibrator.calibrated_priors == self.calibrator.calibrated_priors


class TestIntegration:
    """Test integration between scoring and signals/gates."""
    
    def test_full_pipeline_integration(self):
        """Test complete signal → gate → score pipeline."""
        # Create a study card that will trigger some signals
        study_card = {
            "study_id": "INT001",
            "is_pivotal": True,
            "primary_type": "proportion",
            "arms": {"t": {"n": 100, "dropout": 0.15}, "c": {"n": 100, "dropout": 0.08}},
            "analysis_plan": {
                "alpha": 0.025, "one_sided": True, "assumed_p_c": 0.25, "assumed_delta_abs": 0.15,
                "planned_interims": 2, "alpha_spending": None
            },
            "primary_result": {"ITT": {"p": 0.049, "estimate": 0.08}},
            "subgroups": [],
            "single_arm": False
        }
        
        # Evaluate signals
        signals = evaluate_all_signals(study_card)
        
        # Evaluate gates
        gates = evaluate_all_gates(signals)
        
        # Score the trial
        trial_data = {
            "trial_id": 999,
            "is_pivotal": True,
            "indication": "oncology",
            "phase": "phase_3",
            "sponsor_experience": "experienced",
            "primary_endpoint_type": "response"
        }
        
        score = score_single_trial(999, trial_data, gates, "integration_test")
        
        # Verify the scoring worked
        assert score.trial_id == 999
        assert score.run_id == "integration_test"
        assert score.prior_pi > 0
        assert score.p_fail > 0
        assert score.p_fail <= 1
    
    def test_calibration_integration(self):
        """Test calibration integration with scoring."""
        # Create historical data
        historical_data = [
            {
                "trial_id": 1,
                "actual_outcome": True,
                "gates_fired": ["G1"],
                "gate_severities": {"G1": "H"},
                "is_pivotal": True,
                "indication": "oncology"
            },
            {
                "trial_id": 2,
                "actual_outcome": False,
                "gates_fired": ["G1"],
                "gate_severities": {"G1": "H"},
                "is_pivotal": True,
                "indication": "oncology"
            }
        ]
        
        # Calibrate the system
        calibrated_lrs, calibrated_priors = calibrate_scoring_system(historical_data)
        
        # Get calibrated config
        calibrated_config = get_calibrated_config(historical_data)
        
        # Verify calibration worked
        assert "lr_calibration" in calibrated_config
        assert "G1" in calibrated_config["lr_calibration"]
        assert "H" in calibrated_config["lr_calibration"]["G1"]


if __name__ == "__main__":
    pytest.main([__file__])
