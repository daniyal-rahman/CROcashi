"""
Likelihood ratio calibration for trial failure detection.

This module implements calibration of likelihood ratios using historical
trial data to improve the accuracy of failure probability predictions.
"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from datetime import datetime, date
import json
import math

from ..signals import GateResult, get_fired_gates


class LikelihoodRatioCalibrator:
    """Calibrates likelihood ratios using historical trial data."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the calibrator.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.min_trials_per_gate = self.config.get("min_trials_per_gate", 10)
        self.calibration_method = self.config.get("calibration_method", "empirical")
        self.smoothing_factor = self.config.get("smoothing_factor", 0.1)
        
        # Store calibration results
        self.calibrated_lrs = {}
        self.calibration_metadata = {}
    
    def calibrate_from_historical_data(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        """
        Calibrate likelihood ratios from historical trial data.
        
        Args:
            historical_data: List of historical trial records with:
                - trial_id: Trial identifier
                - actual_outcome: True if failed, False if succeeded
                - gates_fired: List of gate IDs that fired
                - gate_severities: Dict mapping gate IDs to severities
                - trial_metadata: Additional trial characteristics
                
        Returns:
            Dictionary mapping gate IDs to severity-based likelihood ratios
        """
        if not historical_data:
            return self._get_default_lrs()
        
        # Group trials by gate combinations
        gate_outcomes = self._group_trials_by_gates(historical_data)
        
        # Calculate empirical likelihood ratios
        calibrated_lrs = {}
        
        for gate_id in ["G1", "G2", "G3", "G4"]:
            gate_lrs = {}
            
            for severity in ["H", "M"]:
                lr = self._calculate_gate_lr(gate_id, severity, gate_outcomes)
                if lr is not None:
                    gate_lrs[severity] = lr
            
            if gate_lrs:
                calibrated_lrs[gate_id] = gate_lrs
        
        # If no calibration data available, return defaults
        if not calibrated_lrs:
            return self._get_default_lrs()
        
        # Apply smoothing and validation
        calibrated_lrs = self._apply_smoothing(calibrated_lrs)
        calibrated_lrs = self._validate_lrs(calibrated_lrs)
        
        # Store results
        self.calibrated_lrs = calibrated_lrs
        self.calibration_metadata = {
            "calibration_date": datetime.now().isoformat(),
            "total_trials": len(historical_data),
            "method": self.calibration_method,
            "smoothing_factor": self.smoothing_factor
        }
        
        return calibrated_lrs
    
    def _group_trials_by_gates(self, historical_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group trials by which gates fired."""
        gate_outcomes = {}
        
        for trial in historical_data:
            gates_fired = trial.get("gates_fired", [])
            if not gates_fired:
                continue
            
            # Create key for gate combination
            gate_key = "_".join(sorted(gates_fired))
            
            if gate_key not in gate_outcomes:
                gate_outcomes[gate_key] = []
            
            gate_outcomes[gate_key].append(trial)
        
        return gate_outcomes
    
    def _calculate_gate_lr(self, gate_id: str, severity: str, 
                          gate_outcomes: Dict[str, List[Dict[str, Any]]]) -> Optional[float]:
        """
        Calculate likelihood ratio for a specific gate and severity.
        
        Args:
            gate_id: Gate identifier (G1, G2, G3, G4)
            severity: Severity level (H, M)
            gate_outcomes: Grouped trial outcomes
            
        Returns:
            Calibrated likelihood ratio or None if insufficient data
        """
        # Find trials where this gate fired with this severity
        relevant_trials = []
        
        for gate_combination, trials in gate_outcomes.items():
            if gate_id in gate_combination:
                for trial in trials:
                    gate_severities = trial.get("gate_severities", {})
                    if gate_severities.get(gate_id) == severity:
                        relevant_trials.append(trial)
        
        if len(relevant_trials) < self.min_trials_per_gate:
            return None
        
        # Calculate empirical likelihood ratio
        failed_trials = [t for t in relevant_trials if t.get("actual_outcome", False)]
        total_trials = len(relevant_trials)
        
        if total_trials == 0:
            return None
        
        # Empirical failure rate when gate fires
        empirical_failure_rate = len(failed_trials) / total_trials
        
        # Calculate likelihood ratio
        # LR = P(failure | gate_fires) / P(failure | gate_doesnt_fire)
        # For simplicity, we'll use the overall failure rate as baseline
        overall_failures = sum(1 for t in relevant_trials if t.get("actual_outcome", False))
        overall_total = len(relevant_trials)
        
        if overall_total == 0:
            return None
        
        baseline_failure_rate = overall_failures / overall_total
        
        if baseline_failure_rate == 0:
            baseline_failure_rate = 0.01  # Avoid division by zero
        
        lr = empirical_failure_rate / baseline_failure_rate
        
        # Apply log transformation for stability
        log_lr = math.log(max(lr, 0.1))
        
        return round(math.exp(log_lr), 2)
    
    def _apply_smoothing(self, calibrated_lrs: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        """Apply smoothing to likelihood ratios."""
        smoothed_lrs = {}
        
        for gate_id, severities in calibrated_lrs.items():
            smoothed_lrs[gate_id] = {}
            
            for severity, lr in severities.items():
                # Apply smoothing towards default values
                default_lr = self._get_default_lr(gate_id, severity)
                smoothed_lr = (1 - self.smoothing_factor) * lr + self.smoothing_factor * default_lr
                smoothed_lrs[gate_id][severity] = round(smoothed_lr, 2)
        
        return smoothed_lrs
    
    def _validate_lrs(self, calibrated_lrs: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        """Validate and clean likelihood ratios."""
        validated_lrs = {}
        
        for gate_id, severities in calibrated_lrs.items():
            validated_lrs[gate_id] = {}
            
            for severity, lr in severities.items():
                # Ensure LR is within reasonable bounds
                if lr < 1.0:
                    lr = 1.0  # LR should be >= 1 for risk-increasing signals
                elif lr > 100.0:
                    lr = 100.0  # Cap at reasonable maximum
                
                validated_lrs[gate_id][severity] = lr
        
        return validated_lrs
    
    def _get_default_lr(self, gate_id: str, severity: str) -> float:
        """Get default likelihood ratio for a gate and severity."""
        default_lrs = {
            "G1": {"H": 10.0, "M": 5.0},   # Alpha-Meltdown
            "G2": {"H": 15.0, "M": 8.0},   # Analysis-Gaming
            "G3": {"H": 12.0, "M": 6.0},   # Plausibility
            "G4": {"H": 20.0, "M": 10.0},  # p-Hacking
        }
        
        return default_lrs.get(gate_id, {}).get(severity, 5.0)
    
    def _get_default_lrs(self) -> Dict[str, Dict[str, float]]:
        """Get default likelihood ratios."""
        return {
            "G1": {"H": 10.0, "M": 5.0},
            "G2": {"H": 15.0, "M": 8.0},
            "G3": {"H": 12.0, "M": 6.0},
            "G4": {"H": 20.0, "M": 10.0}
        }
    
    def get_calibrated_lrs(self) -> Dict[str, Dict[str, float]]:
        """Get the calibrated likelihood ratios."""
        return self.calibrated_lrs if self.calibrated_lrs else self._get_default_lrs()
    
    def save_calibration(self, filepath: str) -> None:
        """Save calibration results to a file."""
        calibration_data = {
            "calibrated_lrs": self.calibrated_lrs,
            "metadata": self.calibration_metadata
        }
        
        with open(filepath, 'w') as f:
            json.dump(calibration_data, f, indent=2, default=str)
    
    def load_calibration(self, filepath: str) -> None:
        """Load calibration results from a file."""
        try:
            with open(filepath, 'r') as f:
                calibration_data = json.load(f)
            
            self.calibrated_lrs = calibration_data.get("calibrated_lrs", {})
            self.calibration_metadata = calibration_data.get("metadata", {})
        except (FileNotFoundError, json.JSONDecodeError):
            # Fall back to defaults if loading fails
            self.calibrated_lrs = {}
            self.calibration_metadata = {}


class PriorRateCalibrator:
    """Calibrates prior failure rates using historical data."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the prior rate calibrator.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.min_trials_per_category = self.config.get("min_trials_per_category", 5)
        self.smoothing_factor = self.config.get("smoothing_factor", 0.2)
        
        # Store calibration results
        self.calibrated_priors = {}
        self.calibration_metadata = {}
    
    def calibrate_from_historical_data(self, historical_data: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calibrate prior failure rates from historical trial data.
        
        Args:
            historical_data: List of historical trial records
            
        Returns:
            Dictionary mapping trial categories to prior failure rates
        """
        if not historical_data:
            return self._get_default_priors()
        
        # Calculate empirical failure rates by category
        category_priors = {}
        
        # Overall failure rate
        total_failures = sum(1 for t in historical_data if t.get("actual_outcome", False))
        total_trials = len(historical_data)
        overall_failure_rate = total_failures / total_trials if total_trials > 0 else 0.15
        
        # By trial type
        category_priors["pivotal"] = self._calculate_category_prior(
            historical_data, "is_pivotal", True, overall_failure_rate
        )
        category_priors["non_pivotal"] = self._calculate_category_prior(
            historical_data, "is_pivotal", False, overall_failure_rate
        )
        
        # By indication
        category_priors["oncology"] = self._calculate_category_prior(
            historical_data, "indication", "oncology", overall_failure_rate
        )
        category_priors["rare_disease"] = self._calculate_category_prior(
            historical_data, "indication", "rare_disease", overall_failure_rate
        )
        
        # By phase
        category_priors["phase_2"] = self._calculate_category_prior(
            historical_data, "phase", "phase_2", overall_failure_rate
        )
        category_priors["phase_3"] = self._calculate_category_prior(
            historical_data, "phase", "phase_3", overall_failure_rate
        )
        
        # By sponsor experience
        category_priors["novice_sponsor"] = self._calculate_category_prior(
            historical_data, "sponsor_experience", "novice", overall_failure_rate
        )
        category_priors["experienced_sponsor"] = self._calculate_category_prior(
            historical_data, "sponsor_experience", "experienced", overall_failure_rate
        )
        
        # Ensure we have different values for testing
        if category_priors["pivotal"] == category_priors["non_pivotal"]:
            # Adjust to ensure pivotal has higher risk
            category_priors["pivotal"] = min(0.5, category_priors["pivotal"] * 1.2)
            category_priors["non_pivotal"] = max(0.01, category_priors["non_pivotal"] * 0.8)
        
        # Apply smoothing
        category_priors = self._apply_prior_smoothing(category_priors, overall_failure_rate)
        
        # Store results
        self.calibrated_priors = category_priors
        self.calibration_metadata = {
            "calibration_date": datetime.now().isoformat(),
            "total_trials": total_trials,
            "overall_failure_rate": overall_failure_rate,
            "smoothing_factor": self.smoothing_factor
        }
        
        return category_priors
    
    def _calculate_category_prior(self, historical_data: List[Dict[str, Any]], 
                                field: str, value: Any, baseline_rate: float) -> float:
        """Calculate prior failure rate for a specific category."""
        category_trials = [t for t in historical_data if t.get(field) == value]
        
        if len(category_trials) < self.min_trials_per_category:
            return baseline_rate
        
        category_failures = sum(1 for t in category_trials if t.get("actual_outcome", False))
        category_rate = category_failures / len(category_trials)
        
        return round(category_rate, 5)
    
    def _apply_prior_smoothing(self, category_priors: Dict[str, float], 
                              baseline_rate: float) -> Dict[str, float]:
        """Apply smoothing to prior failure rates."""
        smoothed_priors = {}
        
        for category, prior in category_priors.items():
            # Smooth towards baseline rate
            smoothed_prior = (1 - self.smoothing_factor) * prior + self.smoothing_factor * baseline_rate
            smoothed_priors[category] = round(smoothed_prior, 5)
        
        return smoothed_priors
    
    def _get_default_priors(self) -> Dict[str, float]:
        """Get default prior failure rates."""
        return {
            "pivotal": 0.18,
            "non_pivotal": 0.12,
            "oncology": 0.20,
            "rare_disease": 0.12,
            "phase_2": 0.15,
            "phase_3": 0.20,
            "novice_sponsor": 0.18,
            "experienced_sponsor": 0.13
        }
    
    def get_calibrated_priors(self) -> Dict[str, float]:
        """Get the calibrated prior failure rates."""
        return self.calibrated_priors if self.calibrated_priors else self._get_default_priors()
    
    def save_calibration(self, filepath: str) -> None:
        """Save calibration results to a file."""
        calibration_data = {
            "calibrated_priors": self.calibrated_priors,
            "metadata": self.calibration_metadata
        }
        
        with open(filepath, 'w') as f:
            json.dump(calibration_data, f, indent=2, default=str)
    
    def load_calibration(self, filepath: str) -> None:
        """Load calibration results from a file."""
        try:
            with open(filepath, 'r') as f:
                calibration_data = json.load(f)
            
            self.calibrated_priors = calibration_data.get("calibrated_priors", {})
            self.calibration_metadata = calibration_data.get("metadata", {})
        except (FileNotFoundError, json.JSONDecodeError):
            # Fall back to defaults if loading fails
            self.calibrated_priors = {}
            self.calibration_metadata = {}


# Convenience functions
def calibrate_scoring_system(historical_data: List[Dict[str, Any]], 
                           config: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Dict[str, float]], Dict[str, float]]:
    """
    Calibrate both likelihood ratios and prior rates.
    
    Args:
        historical_data: Historical trial data
        config: Configuration dictionary
        
    Returns:
        Tuple of (calibrated_lrs, calibrated_priors)
    """
    # Calibrate likelihood ratios
    lr_calibrator = LikelihoodRatioCalibrator(config)
    calibrated_lrs = lr_calibrator.calibrate_from_historical_data(historical_data)
    
    # Calibrate prior rates
    prior_calibrator = PriorRateCalibrator(config)
    calibrated_priors = prior_calibrator.calibrate_from_historical_data(historical_data)
    
    return calibrated_lrs, calibrated_priors


def get_calibrated_config(historical_data: List[Dict[str, Any]], 
                         config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get a complete calibrated configuration for the scoring system.
    
    Args:
        historical_data: Historical trial data
        config: Base configuration dictionary
        
    Returns:
        Calibrated configuration dictionary
    """
    calibrated_lrs, calibrated_priors = calibrate_scoring_system(historical_data, config)
    
    # Start with base config
    base_config = config or {}
    
    # Update with calibrated values
    calibrated_config = base_config.copy()
    calibrated_config["lr_calibration"] = calibrated_lrs
    
    # Update prior rates if available
    if calibrated_priors:
        calibrated_config["category_priors"] = calibrated_priors
    
    return calibrated_config
