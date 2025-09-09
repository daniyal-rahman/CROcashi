#!/usr/bin/env python3
"""
Document Harvesting for Historical Universe

Phase 2: Harvest SEC 8-Ks, PRs, and conference abstracts with timestamps
"""

import argparse
import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import requests
from dataclasses import dataclass, asdict
import re
from urllib.parse import urljoin, urlparse

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Document with timestamp for backtest"""
    doc_id: str
    trial_id: Optional[str]
    source: str  # sec_8k, pr, abstract, ctgov_results
    published_at: str  # ISO timestamp
    url: str
    text: str
    linkage_confidence: float  # 0.0-1.0
    metadata: Dict[str, Any]


class SECHarvester:
    """Harvest SEC 8-K filings"""
    
    def __init__(self):
        self.base_url = "https://www.sec.gov/Archives/edgar/data"
        self.search_url = "https://www.sec.gov/cgi-bin/browse-edgar"
    
    def search_8k_filings(self, cik: str, start_date: str, end_date: str) -> List[Document]:
        """Search for 8-K filings for a CIK"""
        documents = []
        
        try:
            # Search for 8-K filings
            params = {
                "action": "getcompany",
                "CIK": cik,
                "type": "8-K",
                "dateb": end_date.replace("-", ""),
                "datea": start_date.replace("-", ""),
                "count": 100,
                "output": "atom"
            }
            
            response = requests.get(self.search_url, params=params, timeout=30)
            response.raise_for_status()
            
            # Parse atom feed (simplified)
            content = response.text
            documents.extend(self._parse_sec_feed(content, cik))
            
        except Exception as e:
            logger.error(f"Error searching SEC filings for CIK {cik}: {e}")
        
        return documents
    
    def _parse_sec_feed(self, content: str, cik: str) -> List[Document]:
        """Parse SEC atom feed to extract filing info"""
        documents = []
        
        # Extract filing URLs and dates (simplified regex parsing)
        url_pattern = r'href="([^"]*\.txt)"'
        date_pattern = r'<updated>([^<]+)</updated>'
        
        urls = re.findall(url_pattern, content)
        dates = re.findall(date_pattern, content)
        
        for i, url in enumerate(urls):
            if i < len(dates):
                try:
                    # Fetch document content
                    doc_url = urljoin("https://www.sec.gov", url)
                    doc_content = self._fetch_document_content(doc_url)
                    
                    if doc_content:
                        doc_id = f"SEC_{cik}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}"
                        
                        document = Document(
                            doc_id=doc_id,
                            trial_id=None,  # Will be linked later
                            source="sec_8k",
                            published_at=dates[i],
                            url=doc_url,
                            text=doc_content,
                            linkage_confidence=0.8,  # High confidence for SEC docs
                            metadata={
                                "cik": cik,
                                "filing_type": "8-K",
                                "accession": self._extract_accession(url)
                            }
                        )
                        documents.append(document)
                        
                except Exception as e:
                    logger.error(f"Error fetching document {url}: {e}")
        
        return documents
    
    def _fetch_document_content(self, url: str) -> Optional[str]:
        """Fetch document content from SEC URL"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error fetching document content from {url}: {e}")
            return None
    
    def _extract_accession(self, url: str) -> Optional[str]:
        """Extract accession number from SEC URL"""
        match = re.search(r'/([^/]+)\.txt$', url)
        return match.group(1) if match else None


class PRHarvester:
    """Harvest press releases (placeholder implementation)"""
    
    def __init__(self):
        self.pr_sources = [
            "https://www.businesswire.com",
            "https://www.prnewswire.com",
            "https://www.globenewswire.com"
        ]
    
    def search_prs(self, company_name: str, start_date: str, end_date: str) -> List[Document]:
        """Search for press releases (simplified implementation)"""
        documents = []
        
        # This is a placeholder - in practice you'd need to:
        # 1. Use PR wire APIs
        # 2. Scrape company IR pages
        # 3. Use news APIs
        
        logger.info(f"PR harvesting for {company_name} not fully implemented")
        
        return documents


class AbstractHarvester:
    """Harvest conference abstracts (placeholder implementation)"""
    
    def __init__(self):
        self.conference_sources = {
            "ASCO": "https://meetings.asco.org",
            "ESMO": "https://www.esmo.org",
            "AAIC": "https://www.alz.org"
        }
    
    def search_abstracts(self, indication: str, start_date: str, end_date: str) -> List[Document]:
        """Search for conference abstracts (simplified implementation)"""
        documents = []
        
        # This is a placeholder - in practice you'd need to:
        # 1. Use conference APIs
        # 2. Scrape abstract databases
        # 3. Use academic search APIs
        
        logger.info(f"Abstract harvesting for {indication} not fully implemented")
        
        return documents


class DocumentHarvester:
    """Main document harvesting coordinator"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sec_harvester = SECHarvester()
        self.pr_harvester = PRHarvester()
        self.abstract_harvester = AbstractHarvester()
    
    def harvest_for_trials(self, trials_file: Path, start_date: str, end_date: str) -> List[Document]:
        """Harvest documents for all trials"""
        documents = []
        
        # Load trials
        trials = []
        with open(trials_file, "r") as f:
            for line in f:
                trial_data = json.loads(line.strip())
                trials.append(trial_data)
        
        logger.info(f"Harvesting documents for {len(trials)} trials")
        
        # Group trials by CIK for efficient SEC harvesting
        cik_trials = {}
        for trial in trials:
            if trial.get("cik"):
                cik = trial["cik"]
                if cik not in cik_trials:
                    cik_trials[cik] = []
                cik_trials[cik].append(trial)
        
        # Harvest SEC 8-Ks
        for cik, trial_list in cik_trials.items():
            logger.info(f"Harvesting SEC filings for CIK {cik}")
            sec_docs = self.sec_harvester.search_8k_filings(cik, start_date, end_date)
            
            # Link documents to trials
            for doc in sec_docs:
                doc.trial_id = self._link_document_to_trials(doc, trial_list)
                documents.append(doc)
        
        # Harvest PRs (placeholder)
        for trial in trials:
            if trial.get("sponsor"):
                pr_docs = self.pr_harvester.search_prs(
                    trial["sponsor"], start_date, end_date
                )
                for doc in pr_docs:
                    doc.trial_id = trial["trial_id"]
                    documents.append(doc)
        
        # Harvest abstracts (placeholder)
        indications = list(set(trial["indication"] for trial in trials))
        for indication in indications:
            abstract_docs = self.abstract_harvester.search_abstracts(
                indication, start_date, end_date
            )
            for doc in abstract_docs:
                doc.trial_id = self._link_document_to_trials(doc, trials)
                documents.append(doc)
        
        logger.info(f"Harvested {len(documents)} documents")
        return documents
    
    def _link_document_to_trials(self, doc: Document, trials: List[Dict[str, Any]]) -> Optional[str]:
        """Link document to most relevant trial"""
        # Simple keyword matching (could be improved with NLP)
        doc_text_lower = doc.text.lower()
        
        best_trial = None
        best_score = 0
        
        for trial in trials:
            score = 0
            
            # Match indication
            if trial.get("indication"):
                indication_words = trial["indication"].lower().split()
                for word in indication_words:
                    if word in doc_text_lower:
                        score += 1
            
            # Match sponsor
            if trial.get("sponsor"):
                sponsor_words = trial["sponsor"].lower().split()
                for word in sponsor_words:
                    if word in doc_text_lower:
                        score += 2
            
            if score > best_score:
                best_score = score
                best_trial = trial
        
        return best_trial["trial_id"] if best_trial and best_score > 0 else None
    
    def save_documents(self, documents: List[Document], output_dir: Path):
        """Save documents to JSONL format"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        documents_file = output_dir / "documents.jsonl"
        with open(documents_file, "w") as f:
            for doc in documents:
                f.write(json.dumps(asdict(doc)) + "\n")
        
        logger.info(f"Saved {len(documents)} documents to {documents_file}")
        
        # Save summary
        summary = {
            "total_documents": len(documents),
            "by_source": {},
            "by_trial": {},
            "date_range": {
                "earliest": min(doc.published_at for doc in documents) if documents else None,
                "latest": max(doc.published_at for doc in documents) if documents else None
            }
        }
        
        for doc in documents:
            source = doc.source
            if source not in summary["by_source"]:
                summary["by_source"][source] = 0
            summary["by_source"][source] += 1
            
            trial_id = doc.trial_id
            if trial_id:
                if trial_id not in summary["by_trial"]:
                    summary["by_trial"][trial_id] = 0
                summary["by_trial"][trial_id] += 1
        
        summary_file = output_dir / "documents_summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Saved document summary to {summary_file}")


def main():
    parser = argparse.ArgumentParser(description="Harvest documents for historical universe")
    parser.add_argument("--trials-file", required=True, help="Path to trials.jsonl")
    parser.add_argument("--start-date", default="2017-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2024-01-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="backtest/universe", help="Output directory")
    parser.add_argument("--sources", nargs="+", default=["sec", "pr", "abstracts"], 
                       help="Document sources to harvest")
    
    args = parser.parse_args()
    
    config = {
        "sources": args.sources,
        "start_date": args.start_date,
        "end_date": args.end_date
    }
    
    harvester = DocumentHarvester(config)
    
    # Harvest documents
    trials_file = Path(args.trials_file)
    documents = harvester.harvest_for_trials(trials_file, args.start_date, args.end_date)
    
    # Save results
    output_dir = Path(args.output_dir)
    harvester.save_documents(documents, output_dir)
    
    print(f"✅ Document harvesting completed!")
    print(f"📊 Harvested {len(documents)} documents")
    print(f"📁 Output: {output_dir}")


if __name__ == "__main__":
    main()
