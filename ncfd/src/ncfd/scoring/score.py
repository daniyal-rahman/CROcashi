"""
Advanced scoring system for trial failure detection.

This module implements the scoring system that calculates trial failure
probabilities using calibrated likelihood ratios from gates, prior failure rates,
and posterior probability calculations with stop rules.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timedelta, date
import math
import json
import yaml
from pathlib import Path

from ..signals.gates import GateEval, SignalEvidence, load_gate_config


@dataclass
class StopRuleHit:
    """Result of a stop rule evaluation."""
    rule_id: str
    level: float
    evidence: List[SignalEvidence]


@dataclass
class ScoreResult:
    """Result of a trial scoring evaluation with comprehensive audit trail."""
    trial_id: int
    run_id: str
    prior_pi: float  # Prior failure probability
    logit_prior: float  # log(prior_pi/(1-prior_pi))
    sum_log_lr: float  # Sum of log likelihood ratios from gates
    logit_post: float  # logit_prior + sum_log_lr
    p_fail: float  # Posterior failure probability
    features_frozen_at: Optional[datetime] = None
    scored_at: datetime = None
    metadata: Optional[Dict[str, Any]] = None
    gate_evals: Optional[Dict[str, GateEval]] = None
    stop_rules_applied: Optional[List[StopRuleHit]] = None
    
    def __post_init__(self):
        if self.scored_at is None:
            self.scored_at = datetime.now()
        if self.metadata is None:
            self.metadata = {}
        if self.stop_rules_applied is None:
            self.stop_rules_applied = []


class AdvancedScoringEngine:
    """Advanced engine for calculating trial failure probabilities with stop rules."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the advanced scoring engine.
        
        Args:
            config: Configuration dictionary with scoring parameters
        """
        self.config = config or {}
        
        # Load gate configuration
        try:
            self.gate_config = load_gate_config()
        except Exception as e:
            print(f"Warning: Could not load gate config: {e}")
            self.gate_config = {}
        
        # Default configuration
        self.default_prior = self.config.get("default_prior", 0.15)  # 15% baseline failure rate
        self.min_prior = self.config.get("min_prior", 0.01)  # 1% minimum
        self.max_prior = self.config.get("max_prior", 0.50)  # 50% maximum
        
        # Feature freezing rules
        self.feature_freeze_days = self.config.get("feature_freeze_days", 14)
        
        # Calibration parameters (legacy - will use YAML config instead)
        self.lr_calibration = self.config.get("lr_calibration", {
            "G1": {"H": 10.0, "M": 5.0},   # Alpha-Meltdown
            "G2": {"H": 15.0, "M": 8.0},   # Analysis-Gaming
            "G3": {"H": 12.0, "M": 6.0},   # Plausibility
            "G4": {"H": 20.0, "M": 10.0},  # p-Hacking
        })
    
    def _clamp(self, x: float, lo: float, hi: float) -> float:
        """Clamp value between lower and upper bounds."""
        return max(lo, min(hi, x))
    
    def _logit(self, p: float) -> float:
        """Convert probability to logit (log odds)."""
        return math.log(p / (1.0 - p))
    
    def _logistic(self, z: float) -> float:
        """Convert logit to probability (sigmoid)."""
        return 1.0 / (1.0 + math.exp(-z))
    
    def _safe_log_lr(self, lr: float, lr_min: float, lr_max: float) -> float:
        """Calculate log likelihood ratio with bounds."""
        clamped_lr = self._clamp(lr, lr_min, lr_max)
        return math.log(clamped_lr)
    
    def apply_stop_rules(
        self,
        present_signals: Set[str],
        evidence_by_signal: Dict[str, List[SignalEvidence]],
        cfg: Optional[dict] = None,
    ) -> List[StopRuleHit]:
        """
        Apply stop rules to detect hard failure patterns.
        
        Args:
            present_signals: Set of present signal IDs
            evidence_by_signal: Map S_id -> [SignalEvidence,...]
            cfg: Gate configuration (uses self.gate_config if None)
        
        Returns:
            List of stop rule hits with their forced probability levels
        """
        if cfg is None:
            cfg = self.gate_config
        
        hits: List[StopRuleHit] = []
        sr_cfg = cfg.get("stop_rules", {})

        def _maybe(rule_id: str, cond: bool, sigs: List[str]):
            """Helper to conditionally add stop rule hits."""
            if not cond or rule_id not in sr_cfg:
                return
            ev = []
            for s in sigs:
                ev.extend(evidence_by_signal.get(s, []))
            hits.append(StopRuleHit(
                rule_id=rule_id, 
                level=float(sr_cfg[rule_id]["level"]), 
                evidence=ev
            ))

        # Endpoint switched post-LPR (we assume S1 encodes endpoint change + a sub-flag you set upstream)
        # If you have a dedicated signal like S1a for "post-LPR", prefer that here.
        _maybe("endpoint_switched_after_LPR", 
               "S1" in present_signals and "S1_post_LPR" in present_signals, 
               ["S1"])

        # PP-only success & ITT missing >20%: assume upstream emits S4 plus S4_gt20_missing
        _maybe("pp_only_success_with_missing_itt_gt20", 
               "S4" in present_signals and "S4_gt20_missing" in present_signals, 
               ["S4"])

        # Unblinded subjective primary where blinding feasible: assume upstream emits S8_subj_unblinded
        _maybe("unblinded_subjective_primary_feasible_blinding", 
               "S8_subj_unblinded" in present_signals, 
               ["S8_subj_unblinded"])

        return hits
    
    def compute_posterior(
        self,
        prior_pi: float,
        gate_evals: Dict[str, GateEval],
        primitive_lrs: Optional[List[float]] = None,
        cfg: Optional[dict] = None,
    ) -> ScoreResult:
        """
        Compute posterior failure probability using logit-based Bayesian inference.
        
        Args:
            prior_pi: Prior failure probability
            gate_evals: Dictionary of gate evaluation results
            primitive_lrs: Optional list of primitive signal LRs
            cfg: Gate configuration (uses self.gate_config if None)
        
        Returns:
            ScoreResult with computed posterior probability
        """
        if cfg is None:
            cfg = self.gate_config
        
        g = cfg.get("global", {})
        
        # Clamp prior probability
        pi = self._clamp(prior_pi, g.get("prior_floor", 0.01), g.get("prior_ceil", 0.99))
        logit_prior = self._logit(pi)

        # Sum log LRs from *fired* gates
        lr_min = float(g.get("lr_min", 0.25))
        lr_max = float(g.get("lr_max", 10.0))
        logs: List[float] = []
        
        for ge in gate_evals.values():
            if ge.fired:
                logs.append(self._safe_log_lr(ge.lr_used, lr_min, lr_max))

        # Optionally include primitives (default 1.0 -> log 0). Keep tiny if used later.
        if primitive_lrs:
            for lr in primitive_lrs:
                logs.append(self._safe_log_lr(float(lr), lr_min, lr_max))

        sum_log_lr = sum(logs)
        
        # Clamp logit posterior to avoid numeric blow-ups
        logit_min = float(g.get("logit_min", -8.0))
        logit_max = float(g.get("logit_max", 8.0))
        logit_post = self._clamp(logit_prior + sum_log_lr, logit_min, logit_max)
        
        p = self._logistic(logit_post)

        return ScoreResult(
            trial_id=0,  # Will be set by caller
            run_id="",   # Will be set by caller
            prior_pi=pi,
            logit_prior=logit_prior,
            sum_log_lr=sum_log_lr,
            logit_post=logit_post,
            p_fail=p,
            gate_evals=gate_evals,
            stop_rules_applied=[],
        )
    
    def compute_posterior_with_stops(
        self,
        prior_pi: float,
        present_signals: Set[str],
        evidence_by_signal: Dict[str, List[SignalEvidence]],
        gate_evals: Dict[str, GateEval],
        primitive_lrs: Optional[List[float]] = None,
        cfg: Optional[dict] = None,
    ) -> ScoreResult:
        """
        Compute posterior with stop rule application.
        
        Args:
            prior_pi: Prior failure probability
            present_signals: Set of present signal IDs
            evidence_by_signal: Map S_id -> [SignalEvidence,...]
            gate_evals: Dictionary of gate evaluation results
            primitive_lrs: Optional list of primitive signal LRs
            cfg: Gate configuration (uses self.gate_config if None)
        
        Returns:
            ScoreResult with stop rules applied
        """
        res = self.compute_posterior(prior_pi, gate_evals, primitive_lrs, cfg)
        hits = self.apply_stop_rules(present_signals, evidence_by_signal, cfg)
        
        if hits:
            # Monotone override: no stop rule can *decrease* risk
            forced = max(h.level for h in hits)
            res.p_fail = max(res.p_fail, forced)
        
        res.stop_rules_applied = hits
        return res
    
    def calculate_prior_failure_rate(self, trial_data: Dict[str, Any]) -> float:
        """
        Calculate prior failure rate for a trial (legacy method).
        
        Args:
            trial_data: Trial metadata and historical information
            
        Returns:
            Prior failure probability (0.0 to 1.0)
        """
        # Start with baseline prior
        prior = self.default_prior
        
        # Adjust based on trial characteristics
        if trial_data.get("is_pivotal", False):
            # Pivotal trials have higher baseline risk
            prior *= 1.2
        else:
            # Non-pivotal trials have lower baseline risk
            prior *= 0.8
        
        # Adjust based on indication
        indication = trial_data.get("indication", "").lower()
        if "oncology" in indication:
            prior *= 1.1  # Oncology trials historically more challenging
        elif "rare_disease" in indication or "ultra_rare" in indication:
            prior *= 0.9  # Rare disease trials often have different risk profiles
        
        # Adjust based on phase
        phase = trial_data.get("phase", "").lower()
        if "phase_3" in phase or "phase_3" in phase:
            prior *= 1.1  # Phase 3 trials have higher risk
        elif "phase_1" in phase or "phase_1" in phase:
            prior *= 0.8  # Phase 1 trials have lower risk
        
        # Clamp to reasonable bounds
        return self._clamp(prior, self.min_prior, self.max_prior)
    
    def score_trial(
        self,
        trial_id: int,
        run_id: str,
        trial_data: Dict[str, Any],
        gate_evals: Dict[str, GateEval],
        present_signals: Set[str],
        evidence_by_signal: Dict[str, List[SignalEvidence]],
        primitive_lrs: Optional[List[float]] = None,
    ) -> ScoreResult:
        """
        Score a trial using the advanced scoring system.
        
        Args:
            trial_id: Trial identifier
            run_id: Run identifier
            trial_data: Trial metadata
            gate_evals: Gate evaluation results
            present_signals: Set of present signal IDs
            evidence_by_signal: Map S_id -> [SignalEvidence,...]
            primitive_lrs: Optional list of primitive signal LRs
        
        Returns:
            Complete scoring result with audit trail
        """
        # Calculate prior
        prior_pi = self.calculate_prior_failure_rate(trial_data)
        
        # Compute posterior with stop rules
        result = self.compute_posterior_with_stops(
            prior_pi=prior_pi,
            present_signals=present_signals,
            evidence_by_signal=evidence_by_signal,
            gate_evals=gate_evals,
            primitive_lrs=primitive_lrs,
        )
        
        # Set trial and run IDs
        result.trial_id = trial_id
        result.run_id = run_id
        
        return result
    
    def create_audit_trail(
        self,
        score_result: ScoreResult,
        config_revision: str,
        evidence_by_signal: Dict[str, List[SignalEvidence]],
    ) -> Dict[str, Any]:
        """
        Create comprehensive audit trail for scoring results.
        
        Args:
            score_result: Scoring result to audit
            config_revision: Configuration version used
            evidence_by_signal: Map S_id -> [SignalEvidence,...]
        
        Returns:
            Audit trail as JSON-serializable dictionary
        """
        audit = {
            "config_revision": config_revision,
            "lr_bounds": {
                "lr_min": self.gate_config.get("global", {}).get("lr_min", 0.25),
                "lr_max": self.gate_config.get("global", {}).get("lr_max", 10.0)
            },
            "logit_bounds": {
                "logit_min": self.gate_config.get("global", {}).get("logit_min", -8.0),
                "logit_max": self.gate_config.get("global", {}).get("logit_max", 8.0)
            },
            "prior": {
                "raw": score_result.prior_pi,
                "clamped": score_result.prior_pi,  # Already clamped
                "logit": score_result.logit_prior
            },
            "gates": [],
            "primitives": {
                "used": False,
                "lr_values": []
            },
            "sum_log_lr": score_result.sum_log_lr,
            "logit_post": score_result.logit_post,
            "p_fail": score_result.p_fail,
            "stop_rules_applied": []
        }
        
        # Add gate details
        if score_result.gate_evals:
            for gate_id, gate_eval in score_result.gate_evals.items():
                gate_audit = {
                    "gate_id": gate_id,
                    "fired": gate_eval.fired,
                    "lr_used": gate_eval.lr_used,
                    "supporting_S": gate_eval.supporting_S,
                    "evidence_spans": []
                }
                
                # Add evidence spans
                for evidence in gate_eval.supporting_evidence:
                    span = {
                        "S_id": evidence.S_id,
                        "source_study_id": evidence.evidence_span.get("source_study_id"),
                        "quote": evidence.evidence_span.get("quote"),
                        "page": evidence.evidence_span.get("page"),
                        "start": evidence.evidence_span.get("start"),
                        "end": evidence.evidence_span.get("end")
                    }
                    gate_audit["evidence_spans"].append(span)
                
                gate_audit["rationale"] = gate_eval.rationale
                audit["gates"].append(gate_audit)
        
        # Add stop rule details
        if score_result.stop_rules_applied:
            for stop_rule in score_result.stop_rules_applied:
                audit["stop_rules_applied"].append({
                    "rule_id": stop_rule.rule_id,
                    "level": stop_rule.level,
                    "evidence_count": len(stop_rule.evidence)
                })
        
        return audit


# ---- Legacy compatibility ----

class ScoringEngine(AdvancedScoringEngine):
    """Legacy compatibility class - will be deprecated."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        # Keep legacy configuration for backward compatibility
        self.stop_rule_thresholds = self.config.get("stop_rule_thresholds", {
            "endpoint_switched_after_lpr": 0.97,
            "pp_only_success_high_dropout": 0.97,
            "unblinded_subjective_primary": 0.97,
            "multiple_high_severity_gates": 0.95
        })
    
    def calculate_score(self, trial_data: Dict[str, Any], gates: List['GateResult']) -> ScoreResult:
        """
        Legacy scoring method for backward compatibility.
        
        Args:
            trial_data: Trial metadata
            gates: List of gate results (legacy format)
        
        Returns:
            ScoreResult with computed probability
        """
        # Convert legacy gates to new format
        gate_evals = {}
        present_signals = set()
        evidence_by_signal = {}
        
        for gate in gates:
            if gate.fired:
                gate_eval = GateEval(
                    gate_id=gate.G_id,
                    fired=True,
                    supporting_S=gate.supporting_S_ids,
                    supporting_evidence=[],
                    lr_used=gate.lr_used or 1.0,
                    rationale=gate.rationale_text
                )
                gate_evals[gate.G_id] = gate_eval
                
                # Add supporting signals
                for s_id in gate.supporting_S_ids:
                    present_signals.add(s_id)
                    if s_id not in evidence_by_signal:
                        evidence_by_signal[s_id] = []
        
        # Calculate prior
        prior_pi = self.calculate_prior_failure_rate(trial_data)
        
        # Compute posterior
        result = self.compute_posterior(prior_pi, gate_evals)
        
        # Set basic metadata
        result.trial_id = trial_data.get("trial_id", 0)
        result.run_id = trial_data.get("run_id", "legacy")
        
        return result
