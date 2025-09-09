#!/usr/bin/env python3
"""
Label Building for Historical Universe

Phase 3: Build outcome classification and labeling system
"""

import argparse
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import re

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class Label:
    """Trial outcome label"""
    trial_id: str
    event_date: str  # ISO date
    primary_outcome_success_bool: bool
    label_source: str  # 8k, pr, abstract, ctgov
    label_source_url: str
    evidence_span: Optional[str] = None
    confidence: float = 1.0


class OutcomeClassifier:
    """Classify trial outcomes from document text"""
    
    def __init__(self):
        # Positive outcome phrases
        self.positive_phrases = [
            "met the primary endpoint",
            "achieved the primary endpoint", 
            "primary endpoint was met",
            "successfully met the primary endpoint",
            "demonstrated statistical significance",
            "statistically significant improvement",
            "primary endpoint achieved",
            "met its primary endpoint",
            "primary objective was met",
            "successfully achieved the primary endpoint"
        ]
        
        # Negative outcome phrases
        self.negative_phrases = [
            "did not meet the primary endpoint",
            "failed to meet the primary endpoint",
            "missed the primary endpoint",
            "primary endpoint was not met",
            "did not achieve the primary endpoint",
            "failed to achieve the primary endpoint",
            "primary endpoint not met",
            "did not demonstrate statistical significance",
            "not statistically significant",
            "failed to show statistical significance"
        ]
        
        # Co-primary handling phrases
        self.coprimary_phrases = [
            "co-primary endpoint",
            "co-primary endpoints",
            "primary endpoints",
            "multiple primary endpoints"
        ]
    
    def classify_outcome(self, text: str) -> Tuple[Optional[bool], Optional[str], float]:
        """
        Classify outcome from text
        
        Returns:
            (success_bool, evidence_phrase, confidence)
        """
        if not text:
            return None, None, 0.0
        
        text_lower = text.lower()
        
        # Check for co-primary endpoints
        has_coprimary = any(phrase in text_lower for phrase in self.coprimary_phrases)
        
        # Check positive outcomes
        positive_matches = []
        for phrase in self.positive_phrases:
            if phrase in text_lower:
                positive_matches.append(phrase)
        
        # Check negative outcomes
        negative_matches = []
        for phrase in self.negative_phrases:
            if phrase in text_lower:
                negative_matches.append(phrase)
        
        # Determine outcome
        if positive_matches and not negative_matches:
            # Clear positive
            evidence = positive_matches[0]
            confidence = 0.9 if not has_coprimary else 0.7
            return True, evidence, confidence
            
        elif negative_matches and not positive_matches:
            # Clear negative
            evidence = negative_matches[0]
            confidence = 0.9 if not has_coprimary else 0.7
            return False, evidence, confidence
            
        elif positive_matches and negative_matches:
            # Conflicting signals - check context
            return self._resolve_conflict(text_lower, positive_matches, negative_matches)
        
        else:
            # No clear outcome
            return None, None, 0.0
    
    def _resolve_conflict(self, text: str, positive_matches: List[str], negative_matches: List[str]) -> Tuple[Optional[bool], Optional[str], float]:
        """Resolve conflicting positive/negative signals"""
        
        # Look for context clues
        if "however" in text or "but" in text or "although" in text:
            # Check which comes after the contrast word
            for contrast_word in ["however", "but", "although"]:
                contrast_pos = text.find(contrast_word)
                if contrast_pos != -1:
                    after_contrast = text[contrast_pos:]
                    
                    # Check what comes after the contrast
                    for phrase in self.negative_phrases:
                        if phrase in after_contrast:
                            return False, phrase, 0.8
                    
                    for phrase in self.positive_phrases:
                        if phrase in after_contrast:
                            return True, phrase, 0.8
        
        # Default to negative if conflicting (conservative)
        return False, negative_matches[0], 0.6


class CTGovResultsParser:
    """Parse CT.gov Results module for outcomes"""
    
    def __init__(self):
        self.classifier = OutcomeClassifier()
    
    def parse_results_module(self, results_text: str) -> Tuple[Optional[bool], Optional[str], float]:
        """Parse CT.gov Results module text"""
        if not results_text:
            return None, None, 0.0
        
        # Look for primary outcome results
        primary_pattern = r'primary\s+outcome.*?(?=secondary|$|statistical)'
        primary_match = re.search(primary_pattern, results_text, re.IGNORECASE | re.DOTALL)
        
        if primary_match:
            primary_text = primary_match.group(0)
            return self.classifier.classify_outcome(primary_text)
        
        # Fallback to full text
        return self.classifier.classify_outcome(results_text)


class LabelBuilder:
    """Main label building coordinator"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.classifier = OutcomeClassifier()
        self.ctgov_parser = CTGovResultsParser()
    
    def build_labels(self, trials_file: Path, documents_file: Path) -> List[Label]:
        """Build labels for all trials"""
        labels = []
        
        # Load trials
        trials = {}
        with open(trials_file, "r") as f:
            for line in f:
                trial_data = json.loads(line.strip())
                trials[trial_data["trial_id"]] = trial_data
        
        # Load documents
        documents = []
        with open(documents_file, "r") as f:
            for line in f:
                doc_data = json.loads(line.strip())
                documents.append(doc_data)
        
        logger.info(f"Building labels for {len(trials)} trials using {len(documents)} documents")
        
        # Group documents by trial
        trial_docs = {}
        for doc in documents:
            trial_id = doc.get("trial_id")
            if trial_id:
                if trial_id not in trial_docs:
                    trial_docs[trial_id] = []
                trial_docs[trial_id].append(doc)
        
        # Build labels for each trial
        for trial_id, trial_data in trials.items():
            trial_docs_list = trial_docs.get(trial_id, [])
            
            if not trial_docs_list:
                logger.warning(f"No documents found for trial {trial_id}")
                continue
            
            # Sort documents by published_at
            trial_docs_list.sort(key=lambda x: x["published_at"])
            
            # Find earliest document with outcome
            label = self._find_earliest_outcome(trial_id, trial_docs_list)
            if label:
                labels.append(label)
            else:
                logger.warning(f"No outcome found for trial {trial_id}")
        
        logger.info(f"Built {len(labels)} labels")
        return labels
    
    def _find_earliest_outcome(self, trial_id: str, documents: List[Dict[str, Any]]) -> Optional[Label]:
        """Find earliest document with clear outcome"""
        
        # Priority order: 8-K > PR > abstract > CT.gov
        source_priority = {"sec_8k": 1, "pr": 2, "abstract": 3, "ctgov_results": 4}
        
        # Sort by source priority, then by date
        documents.sort(key=lambda x: (source_priority.get(x["source"], 5), x["published_at"]))
        
        for doc in documents:
            text = doc.get("text", "")
            source = doc.get("source", "")
            
            # Classify outcome
            if source == "ctgov_results":
                success_bool, evidence, confidence = self.ctgov_parser.parse_results_module(text)
            else:
                success_bool, evidence, confidence = self.classifier.classify_outcome(text)
            
            if success_bool is not None and confidence >= 0.6:
                # Found clear outcome
                return Label(
                    trial_id=trial_id,
                    event_date=doc["published_at"][:10],  # Extract date part
                    primary_outcome_success_bool=success_bool,
                    label_source=source,
                    label_source_url=doc["url"],
                    evidence_span=evidence,
                    confidence=confidence
                )
        
        return None
    
    def save_labels(self, labels: List[Label], output_dir: Path):
        """Save labels to JSONL format"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        labels_file = output_dir / "labels.jsonl"
        with open(labels_file, "w") as f:
            for label in labels:
                f.write(json.dumps(asdict(label)) + "\n")
        
        logger.info(f"Saved {len(labels)} labels to {labels_file}")
        
        # Save summary
        summary = {
            "total_labels": len(labels),
            "success_count": len([l for l in labels if l.primary_outcome_success_bool]),
            "failure_count": len([l for l in labels if not l.primary_outcome_success_bool]),
            "by_source": {},
            "by_confidence": {
                "high": len([l for l in labels if l.confidence >= 0.8]),
                "medium": len([l for l in labels if 0.6 <= l.confidence < 0.8]),
                "low": len([l for l in labels if l.confidence < 0.6])
            },
            "date_range": {
                "earliest": min(l.event_date for l in labels) if labels else None,
                "latest": max(l.event_date for l in labels) if labels else None
            }
        }
        
        for label in labels:
            source = label.label_source
            if source not in summary["by_source"]:
                summary["by_source"][source] = 0
            summary["by_source"][source] += 1
        
        summary_file = output_dir / "labels_summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Saved label summary to {summary_file}")


def main():
    parser = argparse.ArgumentParser(description="Build labels for historical universe")
    parser.add_argument("--trials-file", required=True, help="Path to trials.jsonl")
    parser.add_argument("--documents-file", required=True, help="Path to documents.jsonl")
    parser.add_argument("--output-dir", default="backtest/universe", help="Output directory")
    parser.add_argument("--prefer-sources", nargs="+", default=["8k", "pr", "abstract", "ctgov"], 
                       help="Preferred label sources in order")
    parser.add_argument("--strict-coprimary", action="store_true", 
                       help="Require all co-primary endpoints to be met")
    
    args = parser.parse_args()
    
    config = {
        "prefer_sources": args.prefer_sources,
        "strict_coprimary": args.strict_coprimary
    }
    
    builder = LabelBuilder(config)
    
    # Build labels
    trials_file = Path(args.trials_file)
    documents_file = Path(args.documents_file)
    labels = builder.build_labels(trials_file, documents_file)
    
    # Save results
    output_dir = Path(args.output_dir)
    builder.save_labels(labels, output_dir)
    
    print(f"✅ Label building completed!")
    print(f"📊 Built {len(labels)} labels")
    print(f"📈 Success rate: {len([l for l in labels if l.primary_outcome_success_bool]) / len(labels) * 100:.1f}%")
    print(f"📁 Output: {output_dir}")


if __name__ == "__main__":
    main()
