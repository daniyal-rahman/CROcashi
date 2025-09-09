#!/usr/bin/env python3
"""
Time-based Splits for Historical Universe

Phase 5: Create time-based train/val/test splits
"""

import argparse
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class SplitConfig:
    """Configuration for time-based splits"""
    train_start: str = "2018-01-01"
    train_end: str = "2020-12-31"
    val_start: str = "2021-01-01"
    val_end: str = "2021-12-31"
    test_start: str = "2022-01-01"
    test_end: str = "2023-12-31"


class TimeSplitBuilder:
    """Build time-based splits for backtest"""
    
    def __init__(self, config: SplitConfig):
        self.config = config
        self.train_start = datetime.strptime(config.train_start, "%Y-%m-%d").date()
        self.train_end = datetime.strptime(config.train_end, "%Y-%m-%d").date()
        self.val_start = datetime.strptime(config.val_start, "%Y-%m-%d").date()
        self.val_end = datetime.strptime(config.val_end, "%Y-%m-%d").date()
        self.test_start = datetime.strptime(config.test_start, "%Y-%m-%d").date()
        self.test_end = datetime.strptime(config.test_end, "%Y-%m-%d").date()
    
    def create_splits(self, labels_file: Path) -> Dict[str, List[str]]:
        """Create time-based splits from labels"""
        
        # Load labels
        labels = []
        with open(labels_file, "r") as f:
            for line in f:
                label_data = json.loads(line.strip())
                labels.append(label_data)
        
        logger.info(f"Creating splits for {len(labels)} labeled trials")
        
        # Group by split
        splits = {
            "train": [],
            "val": [],
            "test": []
        }
        
        for label in labels:
            trial_id = label["trial_id"]
            event_date = datetime.strptime(label["event_date"], "%Y-%m-%d").date()
            
            # Assign to split based on event_date
            if self.train_start <= event_date <= self.train_end:
                splits["train"].append(trial_id)
            elif self.val_start <= event_date <= self.val_end:
                splits["val"].append(trial_id)
            elif self.test_start <= event_date <= self.test_end:
                splits["test"].append(trial_id)
            else:
                logger.warning(f"Trial {trial_id} with event_date {event_date} outside split ranges")
        
        logger.info(f"Split sizes: Train={len(splits['train'])}, Val={len(splits['val'])}, Test={len(splits['test'])}")
        
        return splits
    
    def save_splits(self, splits: Dict[str, List[str]], output_dir: Path):
        """Save splits to JSONL files"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save each split
        for split_name, trial_ids in splits.items():
            split_file = output_dir / f"{split_name}_ids.jsonl"
            with open(split_file, "w") as f:
                for trial_id in trial_ids:
                    f.write(json.dumps({"trial_id": trial_id}) + "\n")
            
            logger.info(f"Saved {len(trial_ids)} trials to {split_file}")
        
        # Save split summary
        summary = {
            "split_config": asdict(self.config),
            "split_sizes": {
                "train": len(splits["train"]),
                "val": len(splits["val"]),
                "test": len(splits["test"])
            },
            "total_trials": sum(len(split) for split in splits.values()),
            "date_ranges": {
                "train": f"{self.config.train_start} to {self.config.train_end}",
                "val": f"{self.config.val_start} to {self.config.val_end}",
                "test": f"{self.config.test_start} to {self.config.test_end}"
            }
        }
        
        summary_file = output_dir / "splits_summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Saved split summary to {summary_file}")
        
        # Save all splits in one file
        all_splits_file = output_dir / "all_splits.json"
        with open(all_splits_file, "w") as f:
            json.dump(splits, f, indent=2)
        
        logger.info(f"Saved all splits to {all_splits_file}")
    
    def validate_splits(self, splits: Dict[str, List[str]], labels_file: Path) -> Dict[str, Any]:
        """Validate splits for leakage and balance"""
        
        # Load labels for validation
        labels = {}
        with open(labels_file, "r") as f:
            for line in f:
                label_data = json.loads(line.strip())
                labels[label_data["trial_id"]] = label_data
        
        validation = {
            "leakage_check": True,
            "balance_check": {},
            "temporal_check": True,
            "issues": []
        }
        
        # Check for leakage (no overlap)
        all_trials = set()
        for split_name, trial_ids in splits.items():
            split_set = set(trial_ids)
            overlap = all_trials.intersection(split_set)
            if overlap:
                validation["leakage_check"] = False
                validation["issues"].append(f"Leakage detected: {overlap} in {split_name}")
            all_trials.update(split_set)
        
        # Check balance
        total_trials = len(all_trials)
        for split_name, trial_ids in splits.items():
            split_size = len(trial_ids)
            percentage = split_size / total_trials * 100 if total_trials > 0 else 0
            validation["balance_check"][split_name] = {
                "size": split_size,
                "percentage": percentage
            }
            
            # Check if split is too small
            if split_size < 5:
                validation["issues"].append(f"{split_name} split too small: {split_size} trials")
        
        # Check temporal ordering
        for split_name, trial_ids in splits.items():
            if not trial_ids:
                continue
                
            event_dates = []
            for trial_id in trial_ids:
                if trial_id in labels:
                    event_date = datetime.strptime(labels[trial_id]["event_date"], "%Y-%m-%d").date()
                    event_dates.append(event_date)
            
            if event_dates:
                min_date = min(event_dates)
                max_date = max(event_dates)
                
                # Check if dates are within expected range
                if split_name == "train" and (min_date < self.train_start or max_date > self.train_end):
                    validation["temporal_check"] = False
                    validation["issues"].append(f"Train split dates outside range: {min_date} to {max_date}")
                elif split_name == "val" and (min_date < self.val_start or max_date > self.val_end):
                    validation["temporal_check"] = False
                    validation["issues"].append(f"Val split dates outside range: {min_date} to {max_date}")
                elif split_name == "test" and (min_date < self.test_start or max_date > self.test_end):
                    validation["temporal_check"] = False
                    validation["issues"].append(f"Test split dates outside range: {min_date} to {max_date}")
        
        return validation


def main():
    parser = argparse.ArgumentParser(description="Create time-based splits for historical universe")
    parser.add_argument("--labels-file", required=True, help="Path to labels.jsonl")
    parser.add_argument("--output-dir", default="backtest/splits", help="Output directory")
    parser.add_argument("--train-start", default="2018-01-01", help="Train start date")
    parser.add_argument("--train-end", default="2020-12-31", help="Train end date")
    parser.add_argument("--val-start", default="2021-01-01", help="Val start date")
    parser.add_argument("--val-end", default="2021-12-31", help="Val end date")
    parser.add_argument("--test-start", default="2022-01-01", help="Test start date")
    parser.add_argument("--test-end", default="2023-12-31", help="Test end date")
    
    args = parser.parse_args()
    
    config = SplitConfig(
        train_start=args.train_start,
        train_end=args.train_end,
        val_start=args.val_start,
        val_end=args.val_end,
        test_start=args.test_start,
        test_end=args.test_end
    )
    
    builder = TimeSplitBuilder(config)
    
    # Create splits
    labels_file = Path(args.labels_file)
    splits = builder.create_splits(labels_file)
    
    # Validate splits
    validation = builder.validate_splits(splits, labels_file)
    if validation["issues"]:
        logger.warning("Split validation issues:")
        for issue in validation["issues"]:
            logger.warning(f"  - {issue}")
    else:
        logger.info("Split validation passed")
    
    # Save results
    output_dir = Path(args.output_dir)
    builder.save_splits(splits, output_dir)
    
    print(f"✅ Time-based splits created!")
    print(f"📊 Train: {len(splits['train'])} trials")
    print(f"📊 Val: {len(splits['val'])} trials")
    print(f"📊 Test: {len(splits['test'])} trials")
    print(f"📁 Output: {output_dir}")


if __name__ == "__main__":
    main()
