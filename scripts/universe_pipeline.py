#!/usr/bin/env python3
"""
Historical Universe Pipeline

Master CLI that orchestrates the entire historical universe backtest pipeline
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import subprocess
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class UniversePipeline:
    """Master pipeline for historical universe backtest"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_dir = Path(config.get("base_dir", "backtest"))
        self.universe_dir = self.base_dir / "universe"
        self.splits_dir = self.base_dir / "splits"
        self.snapshots_dir = self.base_dir / "snapshots"
        self.results_dir = self.base_dir / "results"
    
    def run_full_pipeline(self, indication: str, start_date: str = "2018-01-01", end_date: str = "2023-12-31"):
        """Run the complete pipeline"""
        
        logger.info(f"Starting full pipeline for {indication} trials {start_date} to {end_date}")
        
        # Phase 1: Build universe
        logger.info("Phase 1: Building universe from CT.gov")
        self._run_universe_build(indication, start_date, end_date)
        
        # Phase 2: Harvest documents
        logger.info("Phase 2: Harvesting documents")
        self._run_document_harvest()
        
        # Phase 3: Build labels
        logger.info("Phase 3: Building labels")
        self._run_label_building()
        
        # Phase 4: Public status
        logger.info("Phase 4: Building public status")
        self._run_public_status()
        
        # Phase 5: Time splits
        logger.info("Phase 5: Creating time-based splits")
        self._run_time_splits()
        
        # Phase 6: T-14 snapshots
        logger.info("Phase 6: Building T-14 snapshots")
        self._run_snapshots()
        
        # Phase 7: Backtest
        logger.info("Phase 7: Running backtest")
        self._run_backtest()
        
        logger.info("Pipeline completed successfully!")
        self._print_summary()
    
    def _run_universe_build(self, indication: str, start_date: str, end_date: str):
        """Run universe building"""
        cmd = [
            sys.executable, "scripts/universe_build.py",
            "--indication", indication,
            "--start-date", start_date,
            "--end-date", end_date,
            "--output-dir", str(self.universe_dir)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Universe build failed: {result.stderr}")
        
        logger.info("Universe build completed")
    
    def _run_document_harvest(self):
        """Run document harvesting"""
        trials_file = self.universe_dir / "trials.jsonl"
        if not trials_file.exists():
            raise FileNotFoundError(f"Trials file not found: {trials_file}")
        
        cmd = [
            sys.executable, "scripts/harvest_docs.py",
            "--trials-file", str(trials_file),
            "--output-dir", str(self.universe_dir)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Document harvest failed: {result.stderr}")
        
        logger.info("Document harvest completed")
    
    def _run_label_building(self):
        """Run label building"""
        trials_file = self.universe_dir / "trials.jsonl"
        documents_file = self.universe_dir / "documents.jsonl"
        
        if not trials_file.exists() or not documents_file.exists():
            raise FileNotFoundError("Required files not found for label building")
        
        cmd = [
            sys.executable, "scripts/build_labels.py",
            "--trials-file", str(trials_file),
            "--documents-file", str(documents_file),
            "--output-dir", str(self.universe_dir)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Label building failed: {result.stderr}")
        
        logger.info("Label building completed")
    
    def _run_public_status(self):
        """Run public status building"""
        trials_file = self.universe_dir / "trials.jsonl"
        labels_file = self.universe_dir / "labels.jsonl"
        
        if not trials_file.exists() or not labels_file.exists():
            raise FileNotFoundError("Required files not found for public status")
        
        cmd = [
            sys.executable, "scripts/public_status.py",
            "--trials-file", str(trials_file),
            "--labels-file", str(labels_file),
            "--output-dir", str(self.universe_dir)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Public status building failed: {result.stderr}")
        
        logger.info("Public status building completed")
    
    def _run_time_splits(self):
        """Run time-based splits"""
        labels_file = self.universe_dir / "labels.jsonl"
        
        if not labels_file.exists():
            raise FileNotFoundError(f"Labels file not found: {labels_file}")
        
        cmd = [
            sys.executable, "scripts/make_splits.py",
            "--labels-file", str(labels_file),
            "--output-dir", str(self.splits_dir)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Time splits failed: {result.stderr}")
        
        logger.info("Time splits completed")
    
    def _run_snapshots(self):
        """Run T-14 snapshots"""
        trials_file = self.universe_dir / "trials.jsonl"
        documents_file = self.universe_dir / "documents.jsonl"
        labels_file = self.universe_dir / "labels.jsonl"
        
        if not all(f.exists() for f in [trials_file, documents_file, labels_file]):
            raise FileNotFoundError("Required files not found for snapshots")
        
        cmd = [
            sys.executable, "scripts/make_snapshots.py",
            "--trials-file", str(trials_file),
            "--documents-file", str(documents_file),
            "--labels-file", str(labels_file),
            "--output-dir", str(self.snapshots_dir)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Snapshots failed: {result.stderr}")
        
        logger.info("Snapshots completed")
    
    def _run_backtest(self):
        """Run backtest"""
        snapshots_dir = self.snapshots_dir / "snapshots"
        coverage_file = self.snapshots_dir / "coverage.jsonl"
        labels_file = self.universe_dir / "labels.jsonl"
        splits_file = self.splits_dir / "all_splits.json"
        
        if not all(f.exists() for f in [snapshots_dir, coverage_file, labels_file, splits_file]):
            raise FileNotFoundError("Required files not found for backtest")
        
        cmd = [
            sys.executable, "scripts/run_backtest_universe.py",
            "--snapshots-dir", str(snapshots_dir),
            "--coverage-file", str(coverage_file),
            "--labels-file", str(labels_file),
            "--splits-file", str(splits_file),
            "--output-dir", str(self.results_dir)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Backtest failed: {result.stderr}")
        
        logger.info("Backtest completed")
    
    def _print_summary(self):
        """Print pipeline summary"""
        print("\n" + "="*60)
        print("HISTORICAL UNIVERSE BACKTEST PIPELINE SUMMARY")
        print("="*60)
        
        # Load and display key metrics
        try:
            # Universe summary
            universe_summary = self.universe_dir / "summary.json"
            if universe_summary.exists():
                with open(universe_summary, "r") as f:
                    universe_data = json.load(f)
                print(f"📊 Universe: {universe_data['total_trials']} trials")
                print(f"🏢 With CIK: {universe_data['trials_with_cik']}")
            
            # Labels summary
            labels_summary = self.universe_dir / "labels_summary.json"
            if labels_summary.exists():
                with open(labels_summary, "r") as f:
                    labels_data = json.load(f)
                print(f"🏷️  Labels: {labels_data['total_labels']} trials")
                print(f"✅ Success rate: {labels_data['success_count'] / labels_data['total_labels'] * 100:.1f}%")
            
            # Splits summary
            splits_summary = self.splits_dir / "splits_summary.json"
            if splits_summary.exists():
                with open(splits_summary, "r") as f:
                    splits_data = json.load(f)
                print(f"📈 Splits: Train={splits_data['split_sizes']['train']}, "
                      f"Val={splits_data['split_sizes']['val']}, "
                      f"Test={splits_data['split_sizes']['test']}")
            
            # Snapshots summary
            snapshots_summary = self.snapshots_dir / "snapshots_summary.json"
            if snapshots_summary.exists():
                with open(snapshots_summary, "r") as f:
                    snapshots_data = json.load(f)
                print(f"📸 Snapshots: {snapshots_data['scoreable_trials']} scoreable "
                      f"({snapshots_data['coverage_rate'] * 100:.1f}% coverage)")
            
            # Results summary
            metrics_file = self.results_dir / "metrics.json"
            if metrics_file.exists():
                with open(metrics_file, "r") as f:
                    metrics_data = json.load(f)
                print(f"🎯 Precision@1: {metrics_data['precision_at_k'].get('1', 0):.3f}")
                print(f"🎯 Precision@3: {metrics_data['precision_at_k'].get('3', 0):.3f}")
                print(f"📊 Hit rate @0.9: {metrics_data['hit_rate_at_threshold'].get('0.9', 0):.3f}")
            
        except Exception as e:
            logger.warning(f"Could not load summary data: {e}")
        
        print(f"\n📁 Output directories:")
        print(f"   Universe: {self.universe_dir}")
        print(f"   Splits: {self.splits_dir}")
        print(f"   Snapshots: {self.snapshots_dir}")
        print(f"   Results: {self.results_dir}")
        print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Run historical universe backtest pipeline")
    parser.add_argument("--indication", required=True, help="Disease indication to analyze")
    parser.add_argument("--start-date", default="2018-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2023-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--base-dir", default="backtest", help="Base output directory")
    parser.add_argument("--phase", choices=["all", "universe", "harvest", "labels", "status", "splits", "snapshots", "backtest"],
                       default="all", help="Phase to run")
    
    args = parser.parse_args()
    
    config = {
        "base_dir": args.base_dir,
        "indication": args.indication,
        "start_date": args.start_date,
        "end_date": args.end_date
    }
    
    pipeline = UniversePipeline(config)
    
    if args.phase == "all":
        pipeline.run_full_pipeline(args.indication, args.start_date, args.end_date)
    elif args.phase == "universe":
        pipeline._run_universe_build(args.indication, args.start_date, args.end_date)
    elif args.phase == "harvest":
        pipeline._run_document_harvest()
    elif args.phase == "labels":
        pipeline._run_label_building()
    elif args.phase == "status":
        pipeline._run_public_status()
    elif args.phase == "splits":
        pipeline._run_time_splits()
    elif args.phase == "snapshots":
        pipeline._run_snapshots()
    elif args.phase == "backtest":
        pipeline._run_backtest()


if __name__ == "__main__":
    main()
