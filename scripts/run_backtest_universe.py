#!/usr/bin/env python3
"""
Historical Universe Backtest Runner

Phase 7: Run backtest with existing gates/scoring on historical universe
"""

import argparse
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import sys

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

from ncfd.signals import (
    S1_endpoint_changed, S2_underpowered_pivotal, S3_subgroup_only_no_multiplicity,
    S4_itt_vs_pp_dropout, S5_implausible_vs_graveyard, S6_many_interims_no_spending,
    S7_single_arm_where_rct_standard, S7b_randomized_withdrawal_after_OLE,
    S8_pvalue_cusp_or_heaping, S9_os_pfs_contradiction,
    evaluate_all_gates, score_trial, get_default_prior_pi
)
from ncfd.signals.study_card_mapper import build_study_card

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Result for a single trial in backtest"""
    trial_id: str
    event_date: str
    p_fail_at_T: float
    gates_fired: List[str]
    signals_fired: Dict[str, bool]
    evidence_urls: List[str]
    label: bool  # True = success, False = failure
    coverage_score: float
    scoreable: bool


@dataclass
class BacktestMetrics:
    """Aggregate backtest metrics"""
    total_trials: int
    scoreable_trials: int
    coverage_rate: float
    precision_at_k: Dict[int, float]
    hit_rate_at_threshold: Dict[float, float]
    miss_audit: List[Dict[str, Any]]


class HistoricalBacktestRunner:
    """Run backtest on historical universe"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.k_values = config.get("k_values", [1, 3, 5])
        self.thresholds = config.get("thresholds", [0.8, 0.9, 0.95])
        self.freeze_days = config.get("freeze_days", 14)
    
    def run_backtest(self, 
                    snapshots_dir: Path, 
                    coverage_file: Path, 
                    labels_file: Path,
                    splits_file: Path) -> Tuple[List[BacktestResult], BacktestMetrics]:
        """Run backtest on historical universe"""
        
        # Load data
        labels = {}
        with open(labels_file, "r") as f:
            for line in f:
                label_data = json.loads(line.strip())
                labels[label_data["trial_id"]] = label_data
        
        coverage = {}
        with open(coverage_file, "r") as f:
            for line in f:
                coverage_data = json.loads(line.strip())
                coverage[coverage_data["trial_id"]] = coverage_data
        
        splits = {}
        with open(splits_file, "r") as f:
            splits_data = json.load(f)
            splits = splits_data
        
        logger.info(f"Running backtest on {len(splits.get('test', []))} test trials")
        
        # Run backtest on test split only
        test_trial_ids = splits.get("test", [])
        results = []
        
        for trial_id in test_trial_ids:
            result = self._process_trial(trial_id, snapshots_dir, labels, coverage)
            if result:
                results.append(result)
        
        # Calculate metrics
        metrics = self._calculate_metrics(results)
        
        logger.info(f"Backtest completed: {len(results)} trials processed")
        return results, metrics
    
    def _process_trial(self, 
                      trial_id: str, 
                      snapshots_dir: Path, 
                      labels: Dict[str, Any], 
                      coverage: Dict[str, Any]) -> Optional[BacktestResult]:
        """Process a single trial"""
        
        # Load snapshot
        snapshot_file = snapshots_dir / f"{trial_id}.json"
        if not snapshot_file.exists():
            logger.warning(f"No snapshot found for trial {trial_id}")
            return None
        
        with open(snapshot_file, "r") as f:
            snapshot_data = json.load(f)
        
        # Check if scoreable
        coverage_data = coverage.get(trial_id)
        if not coverage_data or not coverage_data["scoreable"]:
            logger.warning(f"Trial {trial_id} not scoreable")
            return None
        
        # Get label
        label_data = labels.get(trial_id)
        if not label_data:
            logger.warning(f"No label found for trial {trial_id}")
            return None
        
        try:
            # Build Study Card from snapshot
            study_card = self._build_study_card_from_snapshot(snapshot_data)
            
            # Run signals
            signals = self._run_signals(study_card, snapshot_data)
            
            # Run gates
            gates = evaluate_all_gates(signals)
            
            # Calculate prior
            indication = study_card.get("indication", "unknown")
            phase = study_card.get("analysis_plan", {}).get("phase", "phase_2")
            design_type = "single_arm" if study_card.get("single_arm") else "rct"
            prior_pi = get_default_prior_pi(indication, phase, design_type)
            
            # Score trial
            score = score_trial(
                trial_id=trial_id,
                prior_pi=prior_pi,
                signals=signals,
                gates=gates,
                evidence_span="snapshot_span",
                source_study_id=trial_id
            )
            
            # Extract results
            gates_fired = [gate_id for gate_id, gate in gates.items() if gate.fired]
            signals_fired = {signal_id: signal.fired for signal_id, signal in signals.items()}
            evidence_urls = [doc["url"] for doc in snapshot_data["documents"]]
            
            return BacktestResult(
                trial_id=trial_id,
                event_date=label_data["event_date"],
                p_fail_at_T=score.p_fail,
                gates_fired=gates_fired,
                signals_fired=signals_fired,
                evidence_urls=evidence_urls,
                label=label_data["primary_outcome_success_bool"],
                coverage_score=coverage_data["coverage_score"],
                scoreable=True
            )
            
        except Exception as e:
            logger.error(f"Error processing trial {trial_id}: {e}")
            return None
    
    def _build_study_card_from_snapshot(self, snapshot_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build Study Card from snapshot data"""
        
        study_card_inputs = snapshot_data["study_card_inputs"]
        
        # Build basic Study Card structure
        study_card = {
            "study_id": study_card_inputs["trial_id"],
            "nct_id": study_card_inputs["nct_id"],
            "indication": study_card_inputs["indication"],
            "phase": study_card_inputs["phase"],
            "primary_endpoint": study_card_inputs["primary_endpoint"],
            "sponsor": study_card_inputs["sponsor"],
            "analysis_plan": {
                "phase": study_card_inputs["phase"],
                "primary_endpoint": study_card_inputs["primary_endpoint"]
            },
            "documents": study_card_inputs["documents"]
        }
        
        # Add trial versions if available (placeholder)
        study_card["trial_versions"] = []
        
        return study_card
    
    def _run_signals(self, study_card: Dict[str, Any], snapshot_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run all signals on Study Card"""
        
        signals = {
            "S1": S1_endpoint_changed(study_card.get("trial_versions", [])),
            "S2": S2_underpowered_pivotal(study_card),
            "S3": S3_subgroup_only_no_multiplicity(study_card),
            "S4": S4_itt_vs_pp_dropout(study_card),
            "S5": S5_implausible_vs_graveyard(study_card, {}),  # Empty graveyard data
            "S6": S6_many_interims_no_spending(study_card),
            "S7": S7_single_arm_where_rct_standard(study_card, {}),  # Empty RCT data
            "S7b": S7b_randomized_withdrawal_after_OLE(study_card),
            "S8": S8_pvalue_cusp_or_heaping(study_card),
            "S9": S9_os_pfs_contradiction(study_card),
        }
        
        return signals
    
    def _calculate_metrics(self, results: List[BacktestResult]) -> BacktestMetrics:
        """Calculate backtest metrics"""
        
        # Sort by p_fail (descending)
        ranked_results = sorted(results, key=lambda x: x.p_fail_at_T, reverse=True)
        
        # Calculate Precision@K
        precision_at_k = {}
        for k in self.k_values:
            if k <= len(ranked_results):
                top_k = ranked_results[:k]
                failures_in_top_k = sum(1 for r in top_k if not r.label)
                precision = failures_in_top_k / k
                precision_at_k[k] = precision
        
        # Calculate hit rate at thresholds
        hit_rate_at_threshold = {}
        for threshold in self.thresholds:
            selected = [r for r in ranked_results if r.p_fail_at_T >= threshold]
            if selected:
                failures_in_selected = sum(1 for r in selected if not r.label)
                hit_rate = failures_in_selected / len(selected)
                hit_rate_at_threshold[threshold] = hit_rate
        
        # Miss audit - failures not flagged
        miss_audit = []
        for result in ranked_results:
            if not result.label:  # Failure
                if result.p_fail_at_T < 0.8:  # Not flagged
                    miss_audit.append({
                        "trial_id": result.trial_id,
                        "p_fail": result.p_fail_at_T,
                        "reason": "Below threshold",
                        "gates_fired": result.gates_fired,
                        "signals_fired": result.signals_fired
                    })
        
        return BacktestMetrics(
            total_trials=len(results),
            scoreable_trials=len([r for r in results if r.scoreable]),
            coverage_rate=len([r for r in results if r.scoreable]) / len(results) if results else 0,
            precision_at_k=precision_at_k,
            hit_rate_at_threshold=hit_rate_at_threshold,
            miss_audit=miss_audit
        )
    
    def save_results(self, results: List[BacktestResult], metrics: BacktestMetrics, output_dir: Path):
        """Save backtest results"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save ranked results
        ranked_file = output_dir / "ranked.jsonl"
        with open(ranked_file, "w") as f:
            for result in results:
                f.write(json.dumps(asdict(result)) + "\n")
        
        logger.info(f"Saved {len(results)} ranked results to {ranked_file}")
        
        # Save metrics
        metrics_file = output_dir / "metrics.json"
        with open(metrics_file, "w") as f:
            json.dump(asdict(metrics), f, indent=2)
        
        logger.info(f"Saved metrics to {metrics_file}")
        
        # Save miss audit
        miss_audit_file = output_dir / "miss_audit.csv"
        import pandas as pd
        if metrics.miss_audit:
            df = pd.DataFrame(metrics.miss_audit)
            df.to_csv(miss_audit_file, index=False)
            logger.info(f"Saved miss audit to {miss_audit_file}")


def main():
    parser = argparse.ArgumentParser(description="Run backtest on historical universe")
    parser.add_argument("--snapshots-dir", required=True, help="Path to snapshots directory")
    parser.add_argument("--coverage-file", required=True, help="Path to coverage.jsonl")
    parser.add_argument("--labels-file", required=True, help="Path to labels.jsonl")
    parser.add_argument("--splits-file", required=True, help="Path to all_splits.json")
    parser.add_argument("--output-dir", default="backtest/results", help="Output directory")
    parser.add_argument("--k-values", nargs="+", type=int, default=[1, 3, 5], help="K values for Precision@K")
    parser.add_argument("--thresholds", nargs="+", type=float, default=[0.8, 0.9, 0.95], help="Thresholds for hit rate")
    parser.add_argument("--freeze-days", type=int, default=14, help="Days before event to freeze")
    
    args = parser.parse_args()
    
    config = {
        "k_values": args.k_values,
        "thresholds": args.thresholds,
        "freeze_days": args.freeze_days
    }
    
    runner = HistoricalBacktestRunner(config)
    
    # Run backtest
    snapshots_dir = Path(args.snapshots_dir)
    coverage_file = Path(args.coverage_file)
    labels_file = Path(args.labels_file)
    splits_file = Path(args.splits_file)
    
    results, metrics = runner.run_backtest(snapshots_dir, coverage_file, labels_file, splits_file)
    
    # Save results
    output_dir = Path(args.output_dir)
    runner.save_results(results, metrics, output_dir)
    
    print(f"✅ Historical backtest completed!")
    print(f"📊 Processed {metrics.total_trials} trials")
    print(f"📈 Coverage rate: {metrics.coverage_rate * 100:.1f}%")
    print(f"🎯 Precision@1: {metrics.precision_at_k.get(1, 0):.3f}")
    print(f"🎯 Precision@3: {metrics.precision_at_k.get(3, 0):.3f}")
    print(f"📁 Output: {output_dir}")


if __name__ == "__main__":
    main()
