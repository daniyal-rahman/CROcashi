"""
Validation framework for trial failure detection system.

This module provides comprehensive validation utilities to assess the accuracy
and reliability of the signal detection, gate logic, and scoring systems using
both synthetic and real-world data.
"""

import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime
import json
from sklearn.metrics import confusion_matrix, classification_report, roc_auc_score, roc_curve
from sklearn.model_selection import cross_val_score, KFold
import warnings

from ..signals import evaluate_all_signals, evaluate_all_gates, get_fired_signals, get_fired_gates
from ..scoring import ScoringEngine, score_single_trial
from .synthetic_data import SyntheticDataGenerator, create_test_scenarios, TestScenario


@dataclass
class ValidationMetrics:
    """Validation assessment results."""
    component_name: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    specificity: float
    auc_score: Optional[float] = None
    confusion_matrix: Optional[np.ndarray] = None
    classification_report: Optional[str] = None
    sample_size: int = 0
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class CrossValidationResult:
    """Cross-validation results."""
    component_name: str
    cv_scores: List[float]
    mean_score: float
    std_score: float
    fold_count: int
    scoring_metric: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ValidationReport:
    """Complete validation report."""
    validation_name: str
    timestamp: datetime
    signal_metrics: List[ValidationMetrics]
    gate_metrics: List[ValidationMetrics]
    scoring_metrics: ValidationMetrics
    cross_validation_results: List[CrossValidationResult]
    overall_assessment: Dict[str, Any]
    recommendations: List[str]


class ValidationFramework:
    """Comprehensive validation framework for the trial failure detection system."""
    
    def __init__(self, random_seed: int = 42):
        """
        Initialize the validation framework.
        
        Args:
            random_seed: Random seed for reproducible results
        """
        self.random_seed = random_seed
        self.generator = SyntheticDataGenerator(seed=random_seed)
        self.scenarios = create_test_scenarios()
        
    def run_comprehensive_validation(self, 
                                   num_synthetic_trials: int = 1000,
                                   real_world_data: Optional[List[Dict[str, Any]]] = None) -> ValidationReport:
        """
        Run comprehensive validation across all system components.
        
        Args:
            num_synthetic_trials: Number of synthetic trials to generate
            real_world_data: Optional real-world trial data for validation
            
        Returns:
            Complete validation report
        """
        print("🔍 Starting Comprehensive Validation")
        print("=" * 50)
        
        timestamp = datetime.now()
        
        # Generate validation dataset
        validation_data = self._generate_validation_dataset(num_synthetic_trials)
        
        # Add real-world data if provided
        if real_world_data:
            validation_data.extend(self._prepare_real_world_data(real_world_data))
            print(f"📊 Using {len(validation_data)} total trials ({num_synthetic_trials} synthetic + {len(real_world_data)} real)")
        else:
            print(f"📊 Using {len(validation_data)} synthetic trials")
        
        # Validate signal accuracy
        print("\n🔍 Validating Signal Accuracy...")
        signal_metrics = self.validate_signal_accuracy(validation_data)
        
        # Validate gate logic
        print("\n🚪 Validating Gate Logic...")
        gate_metrics = self.validate_gate_logic(validation_data)
        
        # Validate scoring accuracy
        print("\n🎯 Validating Scoring Accuracy...")
        scoring_metrics = self.validate_scoring_accuracy(validation_data)
        
        # Cross-validation
        print("\n🔄 Running Cross-Validation...")
        cv_results = self.cross_validate_system(validation_data)
        
        # Overall assessment
        overall_assessment = self._generate_overall_assessment(
            signal_metrics, gate_metrics, scoring_metrics, cv_results
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            signal_metrics, gate_metrics, scoring_metrics, overall_assessment
        )
        
        print("\n✅ Validation completed successfully!")
        
        return ValidationReport(
            validation_name="Comprehensive System Validation",
            timestamp=timestamp,
            signal_metrics=signal_metrics,
            gate_metrics=gate_metrics,
            scoring_metrics=scoring_metrics,
            cross_validation_results=cv_results,
            overall_assessment=overall_assessment,
            recommendations=recommendations
        )
    
    def validate_signal_accuracy(self, validation_data: List[Dict[str, Any]]) -> List[ValidationMetrics]:
        """
        Validate signal detection accuracy.
        
        Args:
            validation_data: List of validation trial records
            
        Returns:
            List of validation metrics for each signal
        """
        signal_metrics = []
        
        # Evaluate signals for all trials
        signal_results = {}
        expected_signals = {}
        
        for trial in validation_data:
            trial_id = trial["trial_id"]
            study_card = trial["study_card"]
            
            # Evaluate signals
            signals = evaluate_all_signals(study_card)
            fired_signals = get_fired_signals(signals)
            
            signal_results[trial_id] = {s_id: s_id in fired_signals for s_id in ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]}
            expected_signals[trial_id] = {s_id: s_id in trial["expected_signals"] for s_id in ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]}
        
        # Calculate metrics for each signal
        for signal_id in ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]:
            y_true = [expected_signals[trial_id][signal_id] for trial_id in signal_results.keys()]
            y_pred = [signal_results[trial_id][signal_id] for trial_id in signal_results.keys()]
            
            metrics = self._calculate_classification_metrics(
                y_true, y_pred, f"Signal_{signal_id}"
            )
            signal_metrics.append(metrics)
            
            print(f"  {signal_id}: Acc={metrics.accuracy:.3f}, Prec={metrics.precision:.3f}, "
                  f"Rec={metrics.recall:.3f}, F1={metrics.f1_score:.3f}")
        
        return signal_metrics
    
    def validate_gate_logic(self, validation_data: List[Dict[str, Any]]) -> List[ValidationMetrics]:
        """
        Validate gate logic accuracy.
        
        Args:
            validation_data: List of validation trial records
            
        Returns:
            List of validation metrics for each gate
        """
        gate_metrics = []
        
        # Evaluate gates for all trials
        gate_results = {}
        expected_gates = {}
        
        for trial in validation_data:
            trial_id = trial["trial_id"]
            study_card = trial["study_card"]
            
            # Evaluate signals and gates
            signals = evaluate_all_signals(study_card)
            gates = evaluate_all_gates(signals)
            fired_gates = get_fired_gates(gates)
            
            gate_results[trial_id] = {g_id: g_id in fired_gates for g_id in ["G1", "G2", "G3", "G4"]}
            expected_gates[trial_id] = {g_id: g_id in trial["expected_gates"] for g_id in ["G1", "G2", "G3", "G4"]}
        
        # Calculate metrics for each gate
        for gate_id in ["G1", "G2", "G3", "G4"]:
            y_true = [expected_gates[trial_id][gate_id] for trial_id in gate_results.keys()]
            y_pred = [gate_results[trial_id][gate_id] for trial_id in gate_results.keys()]
            
            metrics = self._calculate_classification_metrics(
                y_true, y_pred, f"Gate_{gate_id}"
            )
            gate_metrics.append(metrics)
            
            print(f"  {gate_id}: Acc={metrics.accuracy:.3f}, Prec={metrics.precision:.3f}, "
                  f"Rec={metrics.recall:.3f}, F1={metrics.f1_score:.3f}")
        
        return gate_metrics
    
    def validate_scoring_accuracy(self, validation_data: List[Dict[str, Any]]) -> ValidationMetrics:
        """
        Validate scoring system accuracy.
        
        Args:
            validation_data: List of validation trial records
            
        Returns:
            Validation metrics for scoring system
        """
        engine = ScoringEngine()
        
        y_true = []  # Actual outcomes
        y_pred_proba = []  # Predicted probabilities
        y_pred_binary = []  # Binary predictions
        
        for trial in validation_data:
            trial_id = trial["trial_id"]
            study_card = trial["study_card"]
            actual_outcome = trial.get("actual_outcome", False)
            
            # Generate trial metadata
            trial_metadata = {
                "trial_id": trial_id,
                "is_pivotal": trial.get("is_pivotal", True),
                "indication": trial.get("indication", "oncology"),
                "phase": trial.get("phase", "phase_3"),
                "sponsor_experience": trial.get("sponsor_experience", "experienced"),
                "primary_endpoint_type": "response"
            }
            
            # Evaluate signals and gates
            signals = evaluate_all_signals(study_card)
            gates = evaluate_all_gates(signals)
            
            # Score trial
            score = engine.score_trial(trial_id, trial_metadata, gates, "validation")
            
            y_true.append(actual_outcome)
            y_pred_proba.append(score.p_fail)
            y_pred_binary.append(score.p_fail > 0.5)  # 50% threshold
        
        # Calculate metrics
        metrics = self._calculate_classification_metrics(y_true, y_pred_binary, "Scoring_System")
        
        # Add AUC score
        if len(set(y_true)) > 1:  # Need both classes for AUC
            try:
                metrics.auc_score = roc_auc_score(y_true, y_pred_proba)
            except Exception:
                metrics.auc_score = None
        
        print(f"  Scoring: Acc={metrics.accuracy:.3f}, Prec={metrics.precision:.3f}, "
              f"Rec={metrics.recall:.3f}, F1={metrics.f1_score:.3f}")
        if metrics.auc_score:
            print(f"           AUC={metrics.auc_score:.3f}")
        
        return metrics
    
    def cross_validate_system(self, validation_data: List[Dict[str, Any]], 
                            cv_folds: int = 5) -> List[CrossValidationResult]:
        """
        Perform cross-validation on the system.
        
        Args:
            validation_data: List of validation trial records
            cv_folds: Number of cross-validation folds
            
        Returns:
            List of cross-validation results
        """
        cv_results = []
        
        if len(validation_data) < cv_folds:
            print(f"  ⚠️  Insufficient data for {cv_folds}-fold CV (have {len(validation_data)} trials)")
            return cv_results
        
        # Prepare data for cross-validation
        X = []  # Features (study cards)
        y = []  # Outcomes
        
        for trial in validation_data:
            X.append(trial["study_card"])
            y.append(trial.get("actual_outcome", False))
        
        # Convert to numpy arrays
        y = np.array(y)
        
        # Cross-validate signal detection
        signal_scores = self._cross_validate_signals(X, y, cv_folds)
        cv_results.append(CrossValidationResult(
            component_name="Signal_Detection",
            cv_scores=signal_scores,
            mean_score=np.mean(signal_scores),
            std_score=np.std(signal_scores),
            fold_count=cv_folds,
            scoring_metric="f1_score"
        ))
        
        # Cross-validate gate logic
        gate_scores = self._cross_validate_gates(X, y, cv_folds)
        cv_results.append(CrossValidationResult(
            component_name="Gate_Logic",
            cv_scores=gate_scores,
            mean_score=np.mean(gate_scores),
            std_score=np.std(gate_scores),
            fold_count=cv_folds,
            scoring_metric="f1_score"
        ))
        
        # Cross-validate scoring system
        scoring_scores = self._cross_validate_scoring(X, y, cv_folds)
        cv_results.append(CrossValidationResult(
            component_name="Scoring_System",
            cv_scores=scoring_scores,
            mean_score=np.mean(scoring_scores),
            std_score=np.std(scoring_scores),
            fold_count=cv_folds,
            scoring_metric="auc"
        ))
        
        for result in cv_results:
            print(f"  {result.component_name}: {result.mean_score:.3f} ± {result.std_score:.3f}")
        
        return cv_results
    
    def _generate_validation_dataset(self, num_trials: int) -> List[Dict[str, Any]]:
        """Generate validation dataset using scenarios."""
        validation_data = []
        
        # Generate trials for each scenario
        trials_per_scenario = max(1, num_trials // len(self.scenarios))
        
        for scenario in self.scenarios:
            for i in range(trials_per_scenario):
                study_card = self.generator.generate_study_card(scenario)
                
                # Determine actual outcome based on scenario
                actual_outcome = self._determine_outcome_from_scenario(scenario)
                
                validation_data.append({
                    "trial_id": len(validation_data) + 1,
                    "study_card": study_card,
                    "scenario": scenario,
                    "expected_signals": scenario.expected_signals,
                    "expected_gates": scenario.expected_gates,
                    "expected_risk_level": scenario.expected_risk_level,
                    "actual_outcome": actual_outcome,
                    "is_pivotal": scenario.trial_type.value in ["pivotal", "phase_3"],
                    "indication": scenario.indication.value,
                    "phase": scenario.trial_type.value,
                    "sponsor_experience": "experienced"
                })
        
        # Fill remaining trials with random scenarios
        while len(validation_data) < num_trials:
            scenario = self.generator._random_scenario()
            study_card = self.generator.generate_study_card(scenario)
            actual_outcome = self._determine_outcome_from_scenario(scenario)
            
            validation_data.append({
                "trial_id": len(validation_data) + 1,
                "study_card": study_card,
                "scenario": scenario,
                "expected_signals": scenario.expected_signals,
                "expected_gates": scenario.expected_gates,
                "expected_risk_level": scenario.expected_risk_level,
                "actual_outcome": actual_outcome,
                "is_pivotal": scenario.trial_type.value in ["pivotal", "phase_3"],
                "indication": scenario.indication.value,
                "phase": scenario.trial_type.value,
                "sponsor_experience": "experienced"
            })
        
        return validation_data[:num_trials]
    
    def _prepare_real_world_data(self, real_world_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare real-world data for validation."""
        prepared_data = []
        
        for i, trial in enumerate(real_world_data):
            # Ensure required fields are present
            prepared_trial = {
                "trial_id": trial.get("trial_id", f"real_{i+1}"),
                "study_card": trial.get("study_card", {}),
                "actual_outcome": trial.get("actual_outcome", False),
                "expected_signals": trial.get("expected_signals", []),
                "expected_gates": trial.get("expected_gates", []),
                "expected_risk_level": trial.get("expected_risk_level", "L"),
                "is_pivotal": trial.get("is_pivotal", True),
                "indication": trial.get("indication", "unknown"),
                "phase": trial.get("phase", "phase_3"),
                "sponsor_experience": trial.get("sponsor_experience", "experienced")
            }
            prepared_data.append(prepared_trial)
        
        return prepared_data
    
    def _calculate_classification_metrics(self, y_true: List[bool], 
                                        y_pred: List[bool], 
                                        component_name: str) -> ValidationMetrics:
        """Calculate classification metrics."""
        y_true = np.array(y_true)
        y_pred = np.array(y_pred)
        
        # Handle edge cases
        if len(y_true) == 0:
            return ValidationMetrics(
                component_name=component_name,
                accuracy=0.0, precision=0.0, recall=0.0, f1_score=0.0, specificity=0.0,
                sample_size=0
            )
        
        # Calculate confusion matrix
        cm = confusion_matrix(y_true, y_pred)
        
        # Calculate metrics
        tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, len(y_true))
        
        accuracy = (tp + tn) / len(y_true) if len(y_true) > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        # Generate classification report
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                class_report = classification_report(y_true, y_pred, zero_division=0)
        except Exception:
            class_report = "Classification report unavailable"
        
        return ValidationMetrics(
            component_name=component_name,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1_score,
            specificity=specificity,
            confusion_matrix=cm,
            classification_report=class_report,
            sample_size=len(y_true)
        )
    
    def _cross_validate_signals(self, X: List[Dict[str, Any]], 
                              y: np.ndarray, cv_folds: int) -> List[float]:
        """Cross-validate signal detection."""
        kfold = KFold(n_splits=cv_folds, shuffle=True, random_state=self.random_seed)
        scores = []
        
        for train_idx, test_idx in kfold.split(X):
            # Get test data
            X_test = [X[i] for i in test_idx]
            y_test = y[test_idx]
            
            # Evaluate signals on test set
            y_pred = []
            for study_card in X_test:
                signals = evaluate_all_signals(study_card)
                fired_signals = get_fired_signals(signals)
                
                # Simple heuristic: predict failure if any high-severity signal fires
                has_high_severity = any(s.severity == "H" for s in fired_signals.values())
                y_pred.append(has_high_severity)
            
            # Calculate F1 score
            y_pred = np.array(y_pred)
            if len(set(y_test)) > 1 and len(set(y_pred)) > 1:
                metrics = self._calculate_classification_metrics(y_test, y_pred, "temp")
                scores.append(metrics.f1_score)
            else:
                scores.append(0.0)
        
        return scores
    
    def _cross_validate_gates(self, X: List[Dict[str, Any]], 
                            y: np.ndarray, cv_folds: int) -> List[float]:
        """Cross-validate gate logic."""
        kfold = KFold(n_splits=cv_folds, shuffle=True, random_state=self.random_seed)
        scores = []
        
        for train_idx, test_idx in kfold.split(X):
            # Get test data
            X_test = [X[i] for i in test_idx]
            y_test = y[test_idx]
            
            # Evaluate gates on test set
            y_pred = []
            for study_card in X_test:
                signals = evaluate_all_signals(study_card)
                gates = evaluate_all_gates(signals)
                fired_gates = get_fired_gates(gates)
                
                # Simple heuristic: predict failure if any gate fires
                y_pred.append(len(fired_gates) > 0)
            
            # Calculate F1 score
            y_pred = np.array(y_pred)
            if len(set(y_test)) > 1 and len(set(y_pred)) > 1:
                metrics = self._calculate_classification_metrics(y_test, y_pred, "temp")
                scores.append(metrics.f1_score)
            else:
                scores.append(0.0)
        
        return scores
    
    def _cross_validate_scoring(self, X: List[Dict[str, Any]], 
                              y: np.ndarray, cv_folds: int) -> List[float]:
        """Cross-validate scoring system."""
        kfold = KFold(n_splits=cv_folds, shuffle=True, random_state=self.random_seed)
        scores = []
        engine = ScoringEngine()
        
        for train_idx, test_idx in kfold.split(X):
            # Get test data
            X_test = [X[i] for i in test_idx]
            y_test = y[test_idx]
            
            # Score trials on test set
            y_pred_proba = []
            for i, study_card in enumerate(X_test):
                signals = evaluate_all_signals(study_card)
                gates = evaluate_all_gates(signals)
                
                trial_metadata = {
                    "trial_id": i + 1,
                    "is_pivotal": True,
                    "indication": "oncology",
                    "phase": "phase_3",
                    "sponsor_experience": "experienced",
                    "primary_endpoint_type": "response"
                }
                
                score = engine.score_trial(i + 1, trial_metadata, gates, "cv")
                y_pred_proba.append(score.p_fail)
            
            # Calculate AUC score
            y_pred_proba = np.array(y_pred_proba)
            if len(set(y_test)) > 1:
                try:
                    auc = roc_auc_score(y_test, y_pred_proba)
                    scores.append(auc)
                except Exception:
                    scores.append(0.5)  # Random performance
            else:
                scores.append(0.5)
        
        return scores
    
    def _determine_outcome_from_scenario(self, scenario: TestScenario) -> bool:
        """Determine outcome based on scenario characteristics."""
        # Base failure probability
        base_prob = 0.15
        
        # Increase based on failure modes
        failure_prob = base_prob + len(scenario.failure_modes) * 0.20
        
        # Adjust for risk level
        if scenario.expected_risk_level == "H":
            failure_prob *= 1.5
        elif scenario.expected_risk_level == "M":
            failure_prob *= 1.2
        
        # Cap at 90%
        failure_prob = min(failure_prob, 0.90)
        
        return np.random.random() < failure_prob
    
    def _generate_overall_assessment(self, signal_metrics: List[ValidationMetrics],
                                   gate_metrics: List[ValidationMetrics],
                                   scoring_metrics: ValidationMetrics,
                                   cv_results: List[CrossValidationResult]) -> Dict[str, Any]:
        """Generate overall system assessment."""
        # Calculate average metrics
        signal_avg_f1 = np.mean([m.f1_score for m in signal_metrics])
        gate_avg_f1 = np.mean([m.f1_score for m in gate_metrics])
        scoring_f1 = scoring_metrics.f1_score
        
        # Calculate average CV scores
        cv_signal = next((r for r in cv_results if r.component_name == "Signal_Detection"), None)
        cv_gate = next((r for r in cv_results if r.component_name == "Gate_Logic"), None)
        cv_scoring = next((r for r in cv_results if r.component_name == "Scoring_System"), None)
        
        # Overall assessment
        assessment = {
            "signal_performance": {
                "average_f1": signal_avg_f1,
                "rating": "excellent" if signal_avg_f1 >= 0.8 else "good" if signal_avg_f1 >= 0.6 else "needs_improvement",
                "cv_stability": cv_signal.std_score if cv_signal else 0.0
            },
            "gate_performance": {
                "average_f1": gate_avg_f1,
                "rating": "excellent" if gate_avg_f1 >= 0.8 else "good" if gate_avg_f1 >= 0.6 else "needs_improvement",
                "cv_stability": cv_gate.std_score if cv_gate else 0.0
            },
            "scoring_performance": {
                "f1_score": scoring_f1,
                "auc_score": scoring_metrics.auc_score,
                "rating": "excellent" if scoring_f1 >= 0.8 else "good" if scoring_f1 >= 0.6 else "needs_improvement",
                "cv_stability": cv_scoring.std_score if cv_scoring else 0.0
            },
            "overall_rating": "excellent" if min(signal_avg_f1, gate_avg_f1, scoring_f1) >= 0.7 else "good" if min(signal_avg_f1, gate_avg_f1, scoring_f1) >= 0.5 else "needs_improvement"
        }
        
        return assessment
    
    def _generate_recommendations(self, signal_metrics: List[ValidationMetrics],
                                gate_metrics: List[ValidationMetrics],
                                scoring_metrics: ValidationMetrics,
                                overall_assessment: Dict[str, Any]) -> List[str]:
        """Generate improvement recommendations."""
        recommendations = []
        
        # Signal recommendations
        low_performing_signals = [m for m in signal_metrics if m.f1_score < 0.6]
        if low_performing_signals:
            signal_names = [m.component_name for m in low_performing_signals]
            recommendations.append(f"Improve signal detection for: {', '.join(signal_names)}")
        
        # Gate recommendations
        low_performing_gates = [m for m in gate_metrics if m.f1_score < 0.6]
        if low_performing_gates:
            gate_names = [m.component_name for m in low_performing_gates]
            recommendations.append(f"Refine gate logic for: {', '.join(gate_names)}")
        
        # Scoring recommendations
        if scoring_metrics.f1_score < 0.7:
            recommendations.append("Consider recalibrating the scoring system")
        
        if scoring_metrics.auc_score and scoring_metrics.auc_score < 0.8:
            recommendations.append("Improve probability calibration for better discrimination")
        
        # Overall recommendations
        if overall_assessment["overall_rating"] == "needs_improvement":
            recommendations.append("Consider comprehensive system retuning with larger validation dataset")
        
        if not recommendations:
            recommendations.append("System performance is satisfactory - continue monitoring")
        
        return recommendations
    
    def save_validation_report(self, report: ValidationReport, filepath: str) -> None:
        """Save validation report to file."""
        # Convert report to serializable format
        report_dict = {
            "validation_name": report.validation_name,
            "timestamp": report.timestamp.isoformat(),
            "signal_metrics": [self._metrics_to_dict(m) for m in report.signal_metrics],
            "gate_metrics": [self._metrics_to_dict(m) for m in report.gate_metrics],
            "scoring_metrics": self._metrics_to_dict(report.scoring_metrics),
            "cross_validation_results": [self._cv_to_dict(cv) for cv in report.cross_validation_results],
            "overall_assessment": report.overall_assessment,
            "recommendations": report.recommendations
        }
        
        with open(filepath, 'w') as f:
            json.dump(report_dict, f, indent=2, default=str)
    
    def _metrics_to_dict(self, metrics: ValidationMetrics) -> Dict[str, Any]:
        """Convert ValidationMetrics to dictionary."""
        return {
            "component_name": metrics.component_name,
            "accuracy": metrics.accuracy,
            "precision": metrics.precision,
            "recall": metrics.recall,
            "f1_score": metrics.f1_score,
            "specificity": metrics.specificity,
            "auc_score": metrics.auc_score,
            "sample_size": metrics.sample_size,
            "confusion_matrix": metrics.confusion_matrix.tolist() if metrics.confusion_matrix is not None else None,
            "classification_report": metrics.classification_report,
            "metadata": metrics.metadata
        }
    
    def _cv_to_dict(self, cv_result: CrossValidationResult) -> Dict[str, Any]:
        """Convert CrossValidationResult to dictionary."""
        return {
            "component_name": cv_result.component_name,
            "cv_scores": cv_result.cv_scores,
            "mean_score": cv_result.mean_score,
            "std_score": cv_result.std_score,
            "fold_count": cv_result.fold_count,
            "scoring_metric": cv_result.scoring_metric,
            "metadata": cv_result.metadata
        }


# Convenience functions
def validate_signal_accuracy(validation_data: List[Dict[str, Any]]) -> List[ValidationMetrics]:
    """Validate signal accuracy."""
    framework = ValidationFramework()
    return framework.validate_signal_accuracy(validation_data)


def validate_gate_logic(validation_data: List[Dict[str, Any]]) -> List[ValidationMetrics]:
    """Validate gate logic."""
    framework = ValidationFramework()
    return framework.validate_gate_logic(validation_data)


def validate_scoring_accuracy(validation_data: List[Dict[str, Any]]) -> ValidationMetrics:
    """Validate scoring accuracy."""
    framework = ValidationFramework()
    return framework.validate_scoring_accuracy(validation_data)


def cross_validate_system(validation_data: List[Dict[str, Any]], 
                         cv_folds: int = 5) -> List[CrossValidationResult]:
    """Cross-validate the system."""
    framework = ValidationFramework()
    return framework.cross_validate_system(validation_data, cv_folds)
