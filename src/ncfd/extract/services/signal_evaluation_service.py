"""
Signal Evaluation Service for Study Card Pipeline.

This service converts pattern detections to signals (S1-S9) and evaluates gates (G1-G4)
for investment decision making.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import yaml

from ncfd.signals.primitives import (
    S1_endpoint_changed, S2_underpowered_pivotal, S3_subgroup_only_no_multiplicity,
    S4_itt_vs_pp_dropout, S5_implausible_vs_graveyard, S6_many_interims_no_spending,
    S7_single_arm_where_rct_standard, S8_pvalue_cusp_or_heaping, S9_os_pfs_contradiction,
    SignalResult
)
from ncfd.signals.gates import evaluate_all_gates
from ncfd.signals.scoring import score_trial, get_default_prior_pi

logger = logging.getLogger(__name__)


@dataclass
class SignalEvaluationResult:
    """Result of signal evaluation."""
    trial_id: str
    signals: Dict[str, SignalResult]
    gates: Dict[str, Any]
    score: Any  # ScoreResult
    fired_signals: List[str]
    fired_gates: List[str]
    p_fail: float
    success: bool
    errors: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class SignalEvaluationService:
    """
    Service for evaluating signals and gates from study card data.
    
    This service:
    - Converts pattern detections to signals (S1-S9)
    - Evaluates gates (G1-G4) based on fired signals
    - Calculates posterior probability (P_fail) for investment decisions
    - Integrates with the existing signals/gates system
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the signal evaluation service.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.signal_config = config.get('signals', {})
        
        # Configuration values
        self.enable_signals = self.signal_config.get('enable_signals', True)
        self.enable_gates = self.signal_config.get('enable_gates', True)
        self.enable_scoring = self.signal_config.get('enable_scoring', True)
        
        # Load signal thresholds
        self.thresholds = self._load_signal_thresholds()
        
        logger.info(f"Initialized signal evaluation service with config: {self.signal_config}")
        logger.info(f"Loaded signal thresholds: {self.thresholds}")
    
    async def evaluate_signals_and_gates(
        self,
        trial_id: str,
        study_cards: List[Dict[str, Any]],
        factsheets: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        trial_versions: Optional[List[Dict[str, Any]]] = None
    ) -> SignalEvaluationResult:
        """
        Evaluate signals and gates for a trial.
        
        Args:
            trial_id: Trial identifier
            study_cards: List of study cards
            factsheets: List of factsheets
            patterns: List of pattern detections
            trial_versions: List of trial versions (for S1 endpoint change detection)
            
        Returns:
            SignalEvaluationResult with signals, gates, and scoring
        """
        errors = []
        warnings = []
        
        try:
            # Step 1: Convert patterns to signals
            logger.info(f"Converting patterns to signals for trial {trial_id}")
            try:
                signals = await self._convert_patterns_to_signals(
                    trial_id, study_cards, factsheets, patterns, trial_versions
                )
                logger.info(f"Successfully converted patterns to {len(signals)} signals")
            except Exception as e:
                error_msg = f"Failed to convert patterns to signals: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                signals = {}
            
            # Step 2: Evaluate gates
            logger.info(f"Evaluating gates for trial {trial_id}")
            gates = {}
            if self.enable_gates:
                try:
                    gates = evaluate_all_gates(signals)
                    logger.info(f"Successfully evaluated {len(gates)} gates")
                except Exception as e:
                    error_msg = f"Failed to evaluate gates: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    gates = {}
            
            # Step 3: Calculate score
            logger.info(f"Calculating score for trial {trial_id}")
            score = None
            if self.enable_scoring:
                try:
                    score = score_trial(
                        trial_id=trial_id,
                        run_id=f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        gates=gates
                    )
                    logger.info(f"Successfully calculated score: P_fail={score.p_fail:.3f}")
                except Exception as e:
                    error_msg = f"Failed to calculate score: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    score = None
            
            # Extract fired signals and gates
            fired_signals = [sid for sid, signal in signals.items() if signal.fired]
            fired_gates = [gid for gid, gate in gates.items() if gate.fired]
            
            p_fail = score.p_fail if score else 0.0
            
            logger.info(f"Signal evaluation completed for trial {trial_id}: "
                       f"{len(fired_signals)} signals fired, {len(fired_gates)} gates fired, "
                       f"P_fail={p_fail:.3f}")
            
            # Determine overall success
            success = len(errors) == 0
            
            return SignalEvaluationResult(
                trial_id=trial_id,
                signals=signals,
                gates=gates,
                score=score,
                fired_signals=fired_signals,
                fired_gates=fired_gates,
                p_fail=p_fail,
                success=success,
                errors=errors,
                warnings=warnings
            )
            
        except Exception as e:
            logger.error(f"Error evaluating signals and gates for trial {trial_id}: {e}")
            return SignalEvaluationResult(
                trial_id=trial_id,
                signals={},
                gates={},
                score=None,
                fired_signals=[],
                fired_gates=[],
                p_fail=0.0,
                success=False,
                errors=[str(e)],
                warnings=warnings
            )
    
    async def _convert_patterns_to_signals(
        self,
        trial_id: str,
        study_cards: List[Dict[str, Any]],
        factsheets: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        trial_versions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, SignalResult]:
        """
        Convert pattern detections to signals (S1-S9).
        
        This method maps F1-F9 patterns to S1-S9 signals and runs the signal
        detection primitives on the study card data.
        """
        signals = {}
        
        try:
            # Build study card data for signal evaluation
            try:
                study_card_data = self._build_study_card_data(study_cards, factsheets)
                logger.debug(f"Built study card data with keys: {list(study_card_data.keys())}")
            except Exception as e:
                logger.error(f"Failed to build study card data: {e}")
                return {}
            
            # Run signal detection primitives
            signals = {}
            if self.enable_signals:
                try:
                    # Get class metadata for S5 (graveyard data)
                    class_meta = self._get_class_metadata(study_card_data)
                    
                    # Evaluate each signal individually with error handling
                    signal_functions = {
                        "S1": lambda: S1_endpoint_changed(trial_versions or []),
                        "S2": lambda: S2_underpowered_pivotal(study_card_data),
                        "S3": lambda: S3_subgroup_only_no_multiplicity(study_card_data, self.thresholds),
                        "S4": lambda: S4_itt_vs_pp_dropout(study_card_data),
                        "S5": lambda: S5_implausible_vs_graveyard(study_card_data, class_meta),
                        "S6": lambda: S6_many_interims_no_spending(study_card_data),
                        "S7": lambda: S7_single_arm_where_rct_standard(study_card_data, rct_required=True),
                        "S8": lambda: S8_pvalue_cusp_or_heaping(study_card_data),
                        "S9": lambda: S9_os_pfs_contradiction(study_card_data),
                    }
                    
                    for signal_id, signal_func in signal_functions.items():
                        try:
                            signals[signal_id] = signal_func()
                            logger.debug(f"Successfully evaluated {signal_id}: {signals[signal_id].fired}")
                        except Exception as e:
                            logger.error(f"Failed to evaluate {signal_id}: {e}")
                            # Create a default failed signal result
                            from ncfd.signals.primitives import SignalResult
                            signals[signal_id] = SignalResult(False, "L", f"Evaluation failed: {e}")
                    
                    # Override with pattern-based signals if patterns are detected
                    try:
                        pattern_signals = self._convert_patterns_to_signal_results(patterns)
                        for signal_id, signal_result in pattern_signals.items():
                            if signal_id in signals:
                                signals[signal_id] = signal_result
                                logger.info(f"Overrode {signal_id} with pattern-based signal: {signal_result.fired}")
                    except Exception as e:
                        logger.error(f"Failed to convert patterns to signals: {e}")
                
                except Exception as e:
                    logger.error(f"Failed to evaluate signals: {e}")
                    return {}
            
            logger.info(f"Generated {len(signals)} signals for trial {trial_id}")
            return signals
            
        except Exception as e:
            logger.error(f"Error converting patterns to signals for trial {trial_id}: {e}")
            return {}
    
    def _build_study_card_data(
        self, 
        study_cards: List[Dict[str, Any]], 
        factsheets: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Build study card data structure for signal evaluation.
        
        Combines study cards and factsheets into a format expected by signal primitives.
        """
        # Use the first study card as the primary data source
        if not study_cards:
            return {}
        
        primary_study_card = study_cards[0]
        
        # Derive is_pivotal from design_archetype
        design_archetype = primary_study_card.get("design_archetype", "").lower()
        is_pivotal = (
            "phase 3" in design_archetype or 
            "phase 2a" in design_archetype or 
            "phase 2b" in design_archetype or
            "pivotal" in design_archetype
        )
        
        logger.info(f"Derived is_pivotal={is_pivotal} from design_archetype='{design_archetype}'")
        
        # Build the study card data structure
        study_card_data = {
            "trial_id": primary_study_card.get("trial_id"),
            "indication": primary_study_card.get("indication"),
            "phase": primary_study_card.get("phase"),
            "primary_endpoint": primary_study_card.get("primary_endpoint"),
            "secondary_endpoints": primary_study_card.get("secondary_endpoints", []),
            "n_total": primary_study_card.get("n_total"),
            "n_primary": primary_study_card.get("n_primary"),
            "dropout_rate": primary_study_card.get("dropout_rate"),
            "single_arm": primary_study_card.get("single_arm", False),
            "randomized": primary_study_card.get("randomized", True),
            "blinded": primary_study_card.get("blinded", True),
            "p_value": primary_study_card.get("p_value"),
            "effect_size": primary_study_card.get("effect_size"),
            "confidence_interval": primary_study_card.get("confidence_interval"),
            "interim_analyses": primary_study_card.get("interim_analyses", []),
            "alpha_spending": primary_study_card.get("alpha_spending"),
            "subgroup_analyses": primary_study_card.get("subgroup_analyses", []),
            "multiplicity_control": primary_study_card.get("multiplicity_control"),
            "itt_status": primary_study_card.get("itt_status"),
            "pp_status": primary_study_card.get("pp_status"),
            "analysis_plan": primary_study_card.get("analysis_plan", {}),
            "is_pivotal": is_pivotal,  # Derive from design_archetype
        }
        
        # Add factsheet data if available
        if factsheets:
            primary_factsheet = factsheets[0]
            factsheet_sections = primary_factsheet.get("factsheet_sections", {})
            
            # Map factsheet sections to study card fields
            if "EFFICACY_DATA" in factsheet_sections:
                efficacy_data = factsheet_sections["EFFICACY_DATA"]
                if isinstance(efficacy_data, dict):
                    study_card_data.update({
                        "primary_endpoint_results": efficacy_data.get("primary_endpoint_results"),
                        "secondary_endpoint_results": efficacy_data.get("secondary_endpoint_results"),
                    })
            
            if "POPULATION_DATA" in factsheet_sections:
                population_data = factsheet_sections["POPULATION_DATA"]
                if isinstance(population_data, dict):
                    study_card_data.update({
                        "total_enrolled": population_data.get("total_enrolled"),
                        "dropout_rate": population_data.get("dropout_rate"),
                    })
        
        # Aggregate analysis claims from all factsheets
        analysis_claims = []
        for factsheet in factsheets:
            claims = factsheet.get('analysis_claims', [])
            if isinstance(claims, list):
                analysis_claims.extend(claims)
        
        study_card_data['analysis_claims'] = analysis_claims
        
        return study_card_data
    
    def _load_signal_thresholds(self) -> Dict[str, Any]:
        """
        Load signal thresholds from configuration file.
        
        Returns:
            Dictionary of signal thresholds
        """
        try:
            config_path = Path("config/signal_thresholds.yaml")
            if not config_path.exists():
                logger.warning(f"Signal thresholds config not found at {config_path}, using defaults")
                return self._get_default_thresholds()
            
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            thresholds = config.get('signal_thresholds', {})
            logger.info(f"Loaded signal thresholds from {config_path}")
            return thresholds
            
        except Exception as e:
            logger.error(f"Failed to load signal thresholds: {e}")
            return self._get_default_thresholds()
    
    def _get_default_thresholds(self) -> Dict[str, Any]:
        """Get default signal thresholds."""
        return {
            's3': {
                'p_value_threshold': 0.05,
                'interaction_p_threshold': 0.05
            },
            's2': {
                'power_threshold': 0.80
            },
            's8': {
                'cusp_threshold': 0.05,
                'heaping_threshold': 0.01
            },
            's6': {
                'max_interims_without_spending': 2,
                'max_extra_peeks': 0
            },
            's5': {
                'percentile_threshold': 0.75,
                'multiplier_threshold': 1.5
            },
            'general': {
                'effect_size_precision': 3,
                'confidence_precision': 2
            }
        }
    
    def _get_class_metadata(self, study_card_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get class metadata for S5 signal evaluation.
        
        For now, return a default structure. In a real implementation,
        this would query a database of class graveyard data.
        """
        # Default class metadata - in production this would come from a database
        return {
            "graveyard": False,  # Set to True for classes known to be graveyards
            "winners_pctl": {
                "p75": 0.5,  # 75th percentile effect size for this class
                "p90": 0.8,  # 90th percentile effect size for this class
            },
            "class_name": study_card_data.get("indication", "Unknown"),
            "total_trials": 0,
            "success_rate": 0.0
        }
    
    def _convert_patterns_to_signal_results(self, patterns: List[Dict[str, Any]]) -> Dict[str, SignalResult]:
        """
        Convert F1-F9 pattern detections to S1-S9 signal results.
        
        This is a simplified mapping - in practice, you'd need more sophisticated conversion
        based on the specific pattern families and their severity/confidence.
        """
        signal_results = {}
        
        for pattern in patterns:
            family_id = pattern.get("family_id")
            pattern_id = pattern.get("pattern_id")
            severity = pattern.get("severity", 0)
            confidence = pattern.get("confidence", 0.0)
            rationale = pattern.get("rationale", "")
            
            # Map pattern families to signals
            if family_id == "F1":  # Endpoint Validity
                signal_results["S1"] = SignalResult(
                    fired=True,
                    severity="H" if severity >= 2 else "M",
                    reason=f"Endpoint validity pattern detected: {rationale}",
                    value=confidence,
                    evidence_ids=[pattern.get("pattern_id", "")]
                )
            elif family_id == "F2":  # Power & Analysis
                signal_results["S2"] = SignalResult(
                    fired=True,
                    severity="H" if severity >= 2 else "M",
                    reason=f"Power/analysis pattern detected: {rationale}",
                    value=confidence,
                    evidence_ids=[pattern.get("pattern_id", "")]
                )
            elif family_id == "F3":  # Control & Blinding
                signal_results["S7"] = SignalResult(
                    fired=True,
                    severity="H" if severity >= 2 else "M",
                    reason=f"Control/blinding pattern detected: {rationale}",
                    value=confidence,
                    evidence_ids=[pattern.get("pattern_id", "")]
                )
            # Add more mappings as needed...
        
        return signal_results
