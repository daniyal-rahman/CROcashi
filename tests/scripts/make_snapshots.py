#!/usr/bin/env python3
"""
T-14 Snapshots and Coverage for Historical Universe

Phase 6: Build T-14 freeze snapshots and coverage tracking
"""

import argparse
import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class CoverageRecord:
    """Coverage record for a trial"""
    trial_id: str
    has_primary_endpoint: bool
    has_n_total: bool
    has_itt_status: bool
    has_effect_size: bool
    has_p_value: bool
    scoreable: bool
    missing_fields: List[str]
    coverage_score: float  # 0.0-1.0


@dataclass
class SnapshotDocument:
    """Document in T-14 snapshot"""
    doc_id: str
    source: str
    published_at: str
    url: str
    text: str
    relevance_score: float


@dataclass
class TrialSnapshot:
    """T-14 snapshot for a trial"""
    trial_id: str
    event_date: str
    freeze_date: str
    documents: List[SnapshotDocument]
    coverage: CoverageRecord
    study_card_inputs: Dict[str, Any]


class CoverageAnalyzer:
    """Analyze coverage for Study Card building"""
    
    def __init__(self):
        self.required_fields = [
            "primary_endpoint",
            "n_total", 
            "itt_status"
        ]
        
        self.optional_fields = [
            "effect_size",
            "p_value",
            "phase",
            "indication"
        ]
    
    def analyze_coverage(self, trial_data: Dict[str, Any], documents: List[Dict[str, Any]]) -> CoverageRecord:
        """Analyze coverage for a trial"""
        
        # Check required fields
        has_primary_endpoint = bool(trial_data.get("primary_endpoint_text"))
        has_n_total = self._extract_n_total(trial_data, documents)
        has_itt_status = self._extract_itt_status(trial_data, documents)
        
        # Check optional fields
        has_effect_size = self._extract_effect_size(documents)
        has_p_value = self._extract_p_value(documents)
        
        # Determine if scoreable
        scoreable = has_primary_endpoint and has_n_total and has_itt_status
        
        # Calculate coverage score
        required_score = sum([has_primary_endpoint, has_n_total, has_itt_status]) / 3.0
        optional_score = sum([has_effect_size, has_p_value]) / 2.0
        coverage_score = 0.7 * required_score + 0.3 * optional_score
        
        # Identify missing fields
        missing_fields = []
        if not has_primary_endpoint:
            missing_fields.append("primary_endpoint")
        if not has_n_total:
            missing_fields.append("n_total")
        if not has_itt_status:
            missing_fields.append("itt_status")
        if not has_effect_size:
            missing_fields.append("effect_size")
        if not has_p_value:
            missing_fields.append("p_value")
        
        return CoverageRecord(
            trial_id=trial_data["trial_id"],
            has_primary_endpoint=has_primary_endpoint,
            has_n_total=has_n_total,
            has_itt_status=has_itt_status,
            has_effect_size=has_effect_size,
            has_p_value=has_p_value,
            scoreable=scoreable,
            missing_fields=missing_fields,
            coverage_score=coverage_score
        )
    
    def _extract_n_total(self, trial_data: Dict[str, Any], documents: List[Dict[str, Any]]) -> bool:
        """Extract N total from trial data or documents"""
        # Check trial data first
        if "n_total" in trial_data and trial_data["n_total"]:
            return True
        
        # Check documents for enrollment info
        for doc in documents:
            text = doc.get("text", "").lower()
            if any(phrase in text for phrase in ["enrolled", "randomized", "patients", "subjects"]):
                # Look for numbers
                import re
                numbers = re.findall(r'\b\d+\b', text)
                if numbers and any(int(n) >= 10 for n in numbers):
                    return True
        
        return False
    
    def _extract_itt_status(self, trial_data: Dict[str, Any], documents: List[Dict[str, Any]]) -> bool:
        """Extract ITT status from trial data or documents"""
        # Check trial data first
        if "itt_status" in trial_data and trial_data["itt_status"]:
            return True
        
        # Check documents for ITT/PP mentions
        for doc in documents:
            text = doc.get("text", "").lower()
            if any(phrase in text for phrase in ["intent to treat", "itt", "per protocol", "pp"]):
                return True
        
        return False
    
    def _extract_effect_size(self, documents: List[Dict[str, Any]]) -> bool:
        """Extract effect size from documents"""
        for doc in documents:
            text = doc.get("text", "").lower()
            if any(phrase in text for phrase in ["effect size", "hazard ratio", "hr", "odds ratio", "or", "relative risk", "rr"]):
                return True
        return False
    
    def _extract_p_value(self, documents: List[Dict[str, Any]]) -> bool:
        """Extract p-value from documents"""
        for doc in documents:
            text = doc.get("text", "").lower()
            if any(phrase in text for phrase in ["p-value", "p value", "p<", "p =", "statistical significance"]):
                return True
        return False


class SnapshotBuilder:
    """Build T-14 snapshots for trials"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.freeze_days = config.get("freeze_days", 14)
        self.coverage_analyzer = CoverageAnalyzer()
    
    def build_snapshots(self, 
                       trials_file: Path, 
                       documents_file: Path, 
                       labels_file: Path) -> List[TrialSnapshot]:
        """Build T-14 snapshots for all trials"""
        
        # Load data
        trials = {}
        with open(trials_file, "r") as f:
            for line in f:
                trial_data = json.loads(line.strip())
                trials[trial_data["trial_id"]] = trial_data
        
        documents = []
        with open(documents_file, "r") as f:
            for line in f:
                doc_data = json.loads(line.strip())
                documents.append(doc_data)
        
        labels = {}
        with open(labels_file, "r") as f:
            for line in f:
                label_data = json.loads(line.strip())
                labels[label_data["trial_id"]] = label_data
        
        logger.info(f"Building snapshots for {len(trials)} trials")
        
        snapshots = []
        
        # Group documents by trial
        trial_docs = {}
        for doc in documents:
            trial_id = doc.get("trial_id")
            if trial_id:
                if trial_id not in trial_docs:
                    trial_docs[trial_id] = []
                trial_docs[trial_id].append(doc)
        
        # Build snapshot for each trial
        for trial_id, trial_data in trials.items():
            label_data = labels.get(trial_id)
            if not label_data:
                logger.warning(f"No label found for trial {trial_id}")
                continue
            
            event_date = datetime.strptime(label_data["event_date"], "%Y-%m-%d").date()
            freeze_date = event_date - timedelta(days=self.freeze_days)
            
            # Get documents before freeze date
            trial_docs_list = trial_docs.get(trial_id, [])
            snapshot_docs = []
            
            for doc in trial_docs_list:
                doc_date = datetime.strptime(doc["published_at"][:10], "%Y-%m-%d").date()
                if doc_date <= freeze_date:
                    snapshot_doc = SnapshotDocument(
                        doc_id=doc["doc_id"],
                        source=doc["source"],
                        published_at=doc["published_at"],
                        url=doc["url"],
                        text=doc["text"],
                        relevance_score=doc.get("linkage_confidence", 0.5)
                    )
                    snapshot_docs.append(snapshot_doc)
            
            # Analyze coverage
            coverage = self.coverage_analyzer.analyze_coverage(trial_data, trial_docs_list)
            
            # Build study card inputs
            study_card_inputs = self._build_study_card_inputs(trial_data, snapshot_docs)
            
            snapshot = TrialSnapshot(
                trial_id=trial_id,
                event_date=label_data["event_date"],
                freeze_date=freeze_date.strftime("%Y-%m-%d"),
                documents=snapshot_docs,
                coverage=coverage,
                study_card_inputs=study_card_inputs
            )
            snapshots.append(snapshot)
        
        logger.info(f"Built {len(snapshots)} snapshots")
        return snapshots
    
    def _build_study_card_inputs(self, trial_data: Dict[str, Any], documents: List[SnapshotDocument]) -> Dict[str, Any]:
        """Build Study Card inputs from trial data and documents"""
        
        inputs = {
            "trial_id": trial_data["trial_id"],
            "nct_id": trial_data["nct_id"],
            "indication": trial_data["indication"],
            "phase": trial_data["phase"],
            "primary_endpoint": trial_data["primary_endpoint_text"],
            "sponsor": trial_data["sponsor"],
            "documents": []
        }
        
        # Add document summaries
        for doc in documents:
            inputs["documents"].append({
                "source": doc.source,
                "published_at": doc.published_at,
                "url": doc.url,
                "text_length": len(doc.text),
                "relevance_score": doc.relevance_score
            })
        
        return inputs
    
    def save_snapshots(self, snapshots: List[TrialSnapshot], output_dir: Path):
        """Save snapshots to files"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save individual snapshots
        snapshots_dir = output_dir / "snapshots"
        snapshots_dir.mkdir(exist_ok=True)
        
        for snapshot in snapshots:
            snapshot_file = snapshots_dir / f"{snapshot.trial_id}.json"
            with open(snapshot_file, "w") as f:
                json.dump(asdict(snapshot), f, indent=2)
        
        logger.info(f"Saved {len(snapshots)} snapshots to {snapshots_dir}")
        
        # Save coverage summary
        coverage_records = [snapshot.coverage for snapshot in snapshots]
        coverage_file = output_dir / "coverage.jsonl"
        with open(coverage_file, "w") as f:
            for coverage in coverage_records:
                f.write(json.dumps(asdict(coverage)) + "\n")
        
        logger.info(f"Saved coverage records to {coverage_file}")
        
        # Save summary
        summary = {
            "total_trials": len(snapshots),
            "scoreable_trials": len([s for s in snapshots if s.coverage.scoreable]),
            "coverage_rate": len([s for s in snapshots if s.coverage.scoreable]) / len(snapshots) if snapshots else 0,
            "field_coverage": {
                "primary_endpoint": len([s for s in snapshots if s.coverage.has_primary_endpoint]),
                "n_total": len([s for s in snapshots if s.coverage.has_n_total]),
                "itt_status": len([s for s in snapshots if s.coverage.has_itt_status]),
                "effect_size": len([s for s in snapshots if s.coverage.has_effect_size]),
                "p_value": len([s for s in snapshots if s.coverage.has_p_value])
            },
            "average_coverage_score": sum(s.coverage.coverage_score for s in snapshots) / len(snapshots) if snapshots else 0,
            "freeze_days": self.freeze_days
        }
        
        summary_file = output_dir / "snapshots_summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Saved snapshots summary to {summary_file}")


def main():
    parser = argparse.ArgumentParser(description="Build T-14 snapshots and coverage")
    parser.add_argument("--trials-file", required=True, help="Path to trials.jsonl")
    parser.add_argument("--documents-file", required=True, help="Path to documents.jsonl")
    parser.add_argument("--labels-file", required=True, help="Path to labels.jsonl")
    parser.add_argument("--output-dir", default="backtest/snapshots", help="Output directory")
    parser.add_argument("--freeze-days", type=int, default=14, help="Days before event to freeze")
    
    args = parser.parse_args()
    
    config = {
        "freeze_days": args.freeze_days
    }
    
    builder = SnapshotBuilder(config)
    
    # Build snapshots
    trials_file = Path(args.trials_file)
    documents_file = Path(args.documents_file)
    labels_file = Path(args.labels_file)
    snapshots = builder.build_snapshots(trials_file, documents_file, labels_file)
    
    # Save results
    output_dir = Path(args.output_dir)
    builder.save_snapshots(snapshots, output_dir)
    
    print(f"✅ T-14 snapshots built!")
    print(f"📊 Built {len(snapshots)} snapshots")
    print(f"📈 Scoreable rate: {len([s for s in snapshots if s.coverage.scoreable]) / len(snapshots) * 100:.1f}%")
    print(f"📁 Output: {output_dir}")


if __name__ == "__main__":
    main()
