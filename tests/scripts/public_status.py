#!/usr/bin/env python3
"""
Public Status Detection for Historical Universe

Phase 4: Implement survivorship-safe public status detection
"""

import argparse
import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import requests
import re

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class PublicStatus:
    """Public status at event date"""
    trial_id: str
    cik: Optional[str]
    ticker: Optional[str]
    public_status_at_event: str  # public/private/unknown
    confidence: float
    evidence: str
    event_date: str


class SECPublicStatusDetector:
    """Detect public status using SEC filings"""
    
    def __init__(self):
        self.base_url = "https://www.sec.gov/Archives/edgar/data"
        self.search_url = "https://www.sec.gov/cgi-bin/browse-edgar"
        self.submissions_url = "https://data.sec.gov/submissions"
    
    def detect_public_status(self, cik: str, event_date: str, window_days: int = 90) -> Tuple[str, float, str]:
        """
        Detect if company was public at event date
        
        Returns:
            (status, confidence, evidence)
        """
        if not cik:
            return "unknown", 0.0, "No CIK provided"
        
        try:
            # Method 1: Check for 8-K filings around event date
            status, confidence, evidence = self._check_8k_filings(cik, event_date)
            if status == "public":
                return status, confidence, evidence
            
            # Method 2: Check submissions data
            status, confidence, evidence = self._check_submissions_data(cik, event_date, window_days)
            if status == "public":
                return status, confidence, evidence
            
            # Method 3: Check for any recent filings
            status, confidence, evidence = self._check_recent_filings(cik, event_date, window_days)
            return status, confidence, evidence
            
        except Exception as e:
            logger.error(f"Error detecting public status for CIK {cik}: {e}")
            return "unknown", 0.0, f"Error: {str(e)}"
    
    def _check_8k_filings(self, cik: str, event_date: str) -> Tuple[str, float, str]:
        """Check for 8-K filings around event date"""
        try:
            # Search for 8-K filings within ±14 days
            start_date = (datetime.strptime(event_date, "%Y-%m-%d") - timedelta(days=14)).strftime("%Y%m%d")
            end_date = (datetime.strptime(event_date, "%Y-%m-%d") + timedelta(days=14)).strftime("%Y%m%d")
            
            params = {
                "action": "getcompany",
                "CIK": cik,
                "type": "8-K",
                "dateb": end_date,
                "datea": start_date,
                "count": 10,
                "output": "atom"
            }
            
            response = requests.get(self.search_url, params=params, timeout=30)
            response.raise_for_status()
            
            # Parse response for filings
            content = response.text
            if "8-K" in content and "filing" in content.lower():
                return "public", 0.9, f"8-K filing found within ±14 days of {event_date}"
            
            return "unknown", 0.0, "No 8-K filings found within ±14 days"
            
        except Exception as e:
            return "unknown", 0.0, f"Error checking 8-K filings: {str(e)}"
    
    def _check_submissions_data(self, cik: str, event_date: str, window_days: int) -> Tuple[str, float, str]:
        """Check SEC submissions data"""
        try:
            # Fetch submissions data
            url = f"{self.submissions_url}/CIK{cik.zfill(10)}.json"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for recent filings
            recent_filings = data.get("filings", {}).get("recent", {})
            if not recent_filings:
                return "unknown", 0.0, "No recent filings data available"
            
            # Check filing dates
            filing_dates = recent_filings.get("filingDate", [])
            if not filing_dates:
                return "unknown", 0.0, "No filing dates available"
            
            # Check if any filings are within window
            event_dt = datetime.strptime(event_date, "%Y-%m-%d")
            window_start = event_dt - timedelta(days=window_days)
            window_end = event_dt + timedelta(days=window_days)
            
            for filing_date in filing_dates:
                try:
                    filing_dt = datetime.strptime(filing_date, "%Y-%m-%d")
                    if window_start <= filing_dt <= window_end:
                        return "public", 0.8, f"Filing found on {filing_date} within ±{window_days} days"
                except ValueError:
                    continue
            
            return "unknown", 0.0, f"No filings found within ±{window_days} days"
            
        except Exception as e:
            return "unknown", 0.0, f"Error checking submissions data: {str(e)}"
    
    def _check_recent_filings(self, cik: str, event_date: str, window_days: int) -> Tuple[str, float, str]:
        """Check for any recent filings"""
        try:
            # Search for any filings within window
            start_date = (datetime.strptime(event_date, "%Y-%m-%d") - timedelta(days=window_days)).strftime("%Y%m%d")
            end_date = (datetime.strptime(event_date, "%Y-%m-%d") + timedelta(days=window_days)).strftime("%Y%m%d")
            
            params = {
                "action": "getcompany",
                "CIK": cik,
                "dateb": end_date,
                "datea": start_date,
                "count": 5,
                "output": "atom"
            }
            
            response = requests.get(self.search_url, params=params, timeout=30)
            response.raise_for_status()
            
            content = response.text
            if "filing" in content.lower() and "edgar" in content.lower():
                return "public", 0.7, f"Recent filings found within ±{window_days} days"
            
            return "private", 0.6, f"No recent filings found within ±{window_days} days"
            
        except Exception as e:
            return "unknown", 0.0, f"Error checking recent filings: {str(e)}"


class PublicStatusBuilder:
    """Main public status building coordinator"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.detector = SECPublicStatusDetector()
        self.manual_overrides = self._load_manual_overrides()
    
    def _load_manual_overrides(self) -> Dict[str, Dict[str, Any]]:
        """Load manual overrides for edge cases"""
        try:
            with open("data/manual_public_status_overrides.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.info("No manual overrides found")
            return {}
    
    def build_public_status(self, trials_file: Path, labels_file: Path) -> List[PublicStatus]:
        """Build public status for all trials"""
        statuses = []
        
        # Load trials
        trials = {}
        with open(trials_file, "r") as f:
            for line in f:
                trial_data = json.loads(line.strip())
                trials[trial_data["trial_id"]] = trial_data
        
        # Load labels
        labels = {}
        with open(labels_file, "r") as f:
            for line in f:
                label_data = json.loads(line.strip())
                labels[label_data["trial_id"]] = label_data
        
        logger.info(f"Building public status for {len(trials)} trials")
        
        # Build status for each trial
        for trial_id, trial_data in trials.items():
            label_data = labels.get(trial_id)
            if not label_data:
                logger.warning(f"No label found for trial {trial_id}")
                continue
            
            event_date = label_data["event_date"]
            cik = trial_data.get("cik")
            ticker = trial_data.get("ticker")
            
            # Check manual overrides first
            if trial_id in self.manual_overrides:
                override = self.manual_overrides[trial_id]
                status = PublicStatus(
                    trial_id=trial_id,
                    cik=cik,
                    ticker=ticker,
                    public_status_at_event=override["status"],
                    confidence=override.get("confidence", 1.0),
                    evidence=override.get("evidence", "Manual override"),
                    event_date=event_date
                )
                statuses.append(status)
                continue
            
            # Detect public status
            if cik:
                status_str, confidence, evidence = self.detector.detect_public_status(
                    cik, event_date, self.config.get("window_days", 90)
                )
            else:
                status_str, confidence, evidence = "unknown", 0.0, "No CIK available"
            
            status = PublicStatus(
                trial_id=trial_id,
                cik=cik,
                ticker=ticker,
                public_status_at_event=status_str,
                confidence=confidence,
                evidence=evidence,
                event_date=event_date
            )
            statuses.append(status)
        
        logger.info(f"Built {len(statuses)} public status records")
        return statuses
    
    def save_public_status(self, statuses: List[PublicStatus], output_dir: Path):
        """Save public status to CSV format"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save as CSV
        import pandas as pd
        df = pd.DataFrame([asdict(status) for status in statuses])
        csv_file = output_dir / "public_status.csv"
        df.to_csv(csv_file, index=False)
        
        logger.info(f"Saved {len(statuses)} public status records to {csv_file}")
        
        # Save summary
        summary = {
            "total_trials": len(statuses),
            "public_count": len([s for s in statuses if s.public_status_at_event == "public"]),
            "private_count": len([s for s in statuses if s.public_status_at_event == "private"]),
            "unknown_count": len([s for s in statuses if s.public_status_at_event == "unknown"]),
            "by_confidence": {
                "high": len([s for s in statuses if s.confidence >= 0.8]),
                "medium": len([s for s in statuses if 0.6 <= s.confidence < 0.8]),
                "low": len([s for s in statuses if s.confidence < 0.6])
            },
            "coverage_rate": len([s for s in statuses if s.public_status_at_event != "unknown"]) / len(statuses) if statuses else 0
        }
        
        summary_file = output_dir / "public_status_summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Saved public status summary to {summary_file}")


def main():
    parser = argparse.ArgumentParser(description="Build public status for historical universe")
    parser.add_argument("--trials-file", required=True, help="Path to trials.jsonl")
    parser.add_argument("--labels-file", required=True, help="Path to labels.jsonl")
    parser.add_argument("--output-dir", default="backtest/universe", help="Output directory")
    parser.add_argument("--window-days", type=int, default=90, 
                       help="Window in days to check for filings")
    
    args = parser.parse_args()
    
    config = {
        "window_days": args.window_days
    }
    
    builder = PublicStatusBuilder(config)
    
    # Build public status
    trials_file = Path(args.trials_file)
    labels_file = Path(args.labels_file)
    statuses = builder.build_public_status(trials_file, labels_file)
    
    # Save results
    output_dir = Path(args.output_dir)
    builder.save_public_status(statuses, output_dir)
    
    print(f"✅ Public status building completed!")
    print(f"📊 Built {len(statuses)} status records")
    print(f"🏢 Public coverage: {len([s for s in statuses if s.public_status_at_event == 'public']) / len(statuses) * 100:.1f}%")
    print(f"📁 Output: {output_dir}")


if __name__ == "__main__":
    main()
