"""
Signal Evaluation Service for Study Card Pipeline.

This service converts pattern detections to signals (S1-S9) and evaluates gates (G1-G4)
for investment decision making.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

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
        
        logger.info(f"Initialized signal evaluation service with config: {self.signal_config}")
    
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
            signals = await self._convert_patterns_to_signals(
                trial_id, study_cards, factsheets, patterns, trial_versions
            )
            
            # Step 2: Evaluate gates
            logger.info(f"Evaluating gates for trial {trial_id}")
            gates = {}
            if self.enable_gates:
                gates = evaluate_all_gates(signals)
            
            # Step 3: Calculate score
            logger.info(f"Calculating score for trial {trial_id}")
            score = None
            if self.enable_scoring:
                score = score_trial(
                    trial_id=trial_id,
                    run_id=f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    gates=gates
                )
            
            # Extract fired signals and gates
            fired_signals = [sid for sid, signal in signals.items() if signal.fired]
            fired_gates = [gid for gid, gate in gates.items() if gate.fired]
            
            p_fail = score.p_fail if score else 0.0
            
            logger.info(f"Signal evaluation completed for trial {trial_id}: "
                       f"{len(fired_signals)} signals fired, {len(fired_gates)} gates fired, "
                       f"P_fail={p_fail:.3f}")
            
            return SignalEvaluationResult(
                trial_id=trial_id,
                signals=signals,
                gates=gates,
                score=score,
                fired_signals=fired_signals,
                fired_gates=fired_gates,
                p_fail=p_fail,
                success=True,
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
            study_card_data = self._build_study_card_data(study_cards, factsheets)
            
            # Run signal detection primitives
            if self.enable_signals:
                signals = {
                    "S1": S1_endpoint_changed(trial_versions or []),
                    "S2": S2_underpowered_pivotal(study_card_data),
                    "S3": S3_subgroup_only_no_multiplicity(study_card_data),
                    "S4": S4_itt_vs_pp_dropout(study_card_data),
                    "S5": S5_implausible_vs_graveyard(study_card_data, {}),  # Empty graveyard data
                    "S6": S6_many_interims_no_spending(study_card_data),
                    "S7": S7_single_arm_where_rct_standard(study_card_data, {}),  # Empty RCT data
                    "S8": S8_pvalue_cusp_or_heaping(study_card_data),
                    "S9": S9_os_pfs_contradiction(study_card_data),
                }
                
                # Override with pattern-based signals if patterns are detected
                pattern_signals = self._convert_patterns_to_signal_results(patterns)
                for signal_id, signal_result in pattern_signals.items():
                    if signal_id in signals:
                        signals[signal_id] = signal_result
                        logger.info(f"Overrode {signal_id} with pattern-based signal: {signal_result.fired}")
            
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
