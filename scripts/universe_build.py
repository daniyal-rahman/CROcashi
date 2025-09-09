#!/usr/bin/env python3
"""
Historical Universe Builder for Backtest System

Phase 1: Build CT.gov cohort of pivotal trials with company mapping
"""

import argparse
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import requests
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class TrialCandidate:
    """Candidate trial for backtest universe"""
    trial_id: str
    nct_id: str
    title: str
    phase: str
    indication: str
    primary_endpoint_text: str
    est_primary_completion_date: Optional[str]
    sponsor: str
    collaborator: Optional[str]
    public_status_at_event: str = "unknown"  # public/private/unknown
    cik: Optional[str] = None
    ticker: Optional[str] = None


class CTGovUniverseBuilder:
    """Builds universe of pivotal trials from CT.gov"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = "https://clinicaltrials.gov/api/v2/studies"
        self.company_aliases = self._load_company_aliases()
        self.ticker_map = self._load_ticker_map()
        
    def _load_company_aliases(self) -> Dict[str, List[str]]:
        """Load company aliases for sponsor resolution"""
        try:
            with open("data/company_aliases_seed.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("No company aliases found, using empty mapping")
            return {}
    
    def _load_ticker_map(self) -> Dict[str, str]:
        """Load SEC ticker mapping"""
        try:
            with open("data/sec/company_tickers_exchange.json", "r") as f:
                data = json.load(f)
                return {item["ticker"]: item["cik"] for item in data}
        except FileNotFoundError:
            logger.warning("No ticker map found, using empty mapping")
            return {}
    
    def search_trials(self, 
                     indication: str,
                     start_date: str = "2018-01-01",
                     end_date: str = "2023-12-31",
                     phase_filter: List[str] = None) -> List[TrialCandidate]:
        """Search CT.gov for pivotal trials"""
        
        if phase_filter is None:
            phase_filter = ["PHASE2", "PHASE3"]
        
        logger.info(f"Searching CT.gov for {indication} trials {start_date} to {end_date}")
        
        # Build search query
        query_params = {
            "format": "json",
            "query.term": indication,
            "query.phase": ",".join(phase_filter),
            "query.studyType": "INTERVENTIONAL",
            "query.completionDateFrom": start_date,
            "query.completionDateTo": end_date,
            "pageSize": 1000
        }
        
        trials = []
        page = 1
        
        while True:
            query_params["page"] = page
            logger.info(f"Fetching page {page}")
            
            try:
                response = requests.get(self.base_url, params=query_params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                studies = data.get("studies", [])
                if not studies:
                    break
                
                for study in studies:
                    trial = self._parse_study(study)
                    if trial:
                        trials.append(trial)
                
                page += 1
                
                # Safety check
                if page > 50:  # Max 50k trials
                    logger.warning("Hit page limit, stopping")
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break
        
        logger.info(f"Found {len(trials)} candidate trials")
        return trials
    
    def _parse_study(self, study: Dict[str, Any]) -> Optional[TrialCandidate]:
        """Parse a single study from CT.gov API"""
        try:
            protocol = study.get("protocolSection", {})
            identification = protocol.get("identificationModule", {})
            design = protocol.get("designModule", {})
            conditions = protocol.get("conditionsModule", {})
            outcomes = protocol.get("outcomesModule", {})
            sponsor = protocol.get("sponsorCollaboratorsModule", {})
            
            # Extract basic info
            nct_id = identification.get("nctId", "")
            title = identification.get("briefTitle", "")
            
            # Phase
            phases = design.get("phases", [])
            if not phases:
                return None
            
            # Only include Phase 2/3 trials
            phase_str = " ".join(phases)
            if "PHASE2" not in phase_str and "PHASE3" not in phase_str:
                return None
            
            # Indication
            condition_list = conditions.get("conditions", [])
            indication = condition_list[0] if condition_list else ""
            
            # Primary endpoint
            primary_outcomes = outcomes.get("primaryOutcomes", [])
            primary_endpoint_text = ""
            if primary_outcomes:
                primary_outcome = primary_outcomes[0]
                primary_endpoint_text = primary_outcome.get("title", "")
            
            # Skip if no primary endpoint
            if not primary_endpoint_text:
                return None
            
            # Completion date
            completion_date = None
            completion_module = protocol.get("completionDateModule", {})
            if completion_module:
                completion_date = completion_module.get("completionDateStruct", {}).get("date")
            
            # Sponsor info
            lead_sponsor = sponsor.get("leadSponsor", {})
            sponsor_name = lead_sponsor.get("name", "")
            
            # Collaborator
            collaborators = sponsor.get("collaborators", [])
            collaborator_name = collaborators[0].get("name") if collaborators else None
            
            # Resolve company mapping
            cik, ticker = self._resolve_company(sponsor_name, collaborator_name)
            
            return TrialCandidate(
                trial_id=f"TRIAL_{nct_id}",
                nct_id=nct_id,
                title=title,
                phase=phase_str,
                indication=indication,
                primary_endpoint_text=primary_endpoint_text,
                est_primary_completion_date=completion_date,
                sponsor=sponsor_name,
                collaborator=collaborator_name,
                cik=cik,
                ticker=ticker
            )
            
        except Exception as e:
            logger.error(f"Error parsing study: {e}")
            return None
    
    def _resolve_company(self, sponsor: str, collaborator: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Resolve sponsor/collaborator to CIK and ticker"""
        
        # Try sponsor first
        cik, ticker = self._match_company_name(sponsor)
        if cik:
            return cik, ticker
        
        # Try collaborator if sponsor failed
        if collaborator:
            cik, ticker = self._match_company_name(collaborator)
            if cik:
                return cik, ticker
        
        return None, None
    
    def _match_company_name(self, company_name: str) -> Tuple[Optional[str], Optional[str]]:
        """Match company name to CIK and ticker"""
        if not company_name:
            return None, None
        
        # Direct alias lookup
        for cik, aliases in self.company_aliases.items():
            for alias in aliases:
                if alias.lower() in company_name.lower() or company_name.lower() in alias.lower():
                    # Find ticker for this CIK
                    ticker = self._cik_to_ticker(cik)
                    return cik, ticker
        
        # Fuzzy matching could be added here
        return None, None
    
    def _cik_to_ticker(self, cik: str) -> Optional[str]:
        """Convert CIK to ticker"""
        for ticker, ticker_cik in self.ticker_map.items():
            if ticker_cik == cik:
                return ticker
        return None
    
    def save_trials(self, trials: List[TrialCandidate], output_dir: Path):
        """Save trials to JSONL format"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save trials
        trials_file = output_dir / "trials.jsonl"
        with open(trials_file, "w") as f:
            for trial in trials:
                f.write(json.dumps(asdict(trial)) + "\n")
        
        logger.info(f"Saved {len(trials)} trials to {trials_file}")
        
        # Save summary
        summary = {
            "total_trials": len(trials),
            "trials_with_cik": len([t for t in trials if t.cik]),
            "trials_with_ticker": len([t for t in trials if t.ticker]),
            "indications": list(set(t.indication for t in trials)),
            "phases": list(set(t.phase for t in trials)),
            "sponsors": list(set(t.sponsor for t in trials if t.sponsor))
        }
        
        summary_file = output_dir / "summary.json"
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"Saved summary to {summary_file}")


def main():
    parser = argparse.ArgumentParser(description="Build historical universe from CT.gov")
    parser.add_argument("--indication", required=True, help="Disease indication to search for")
    parser.add_argument("--start-date", default="2018-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2023-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="backtest/universe", help="Output directory")
    parser.add_argument("--phases", nargs="+", default=["PHASE2", "PHASE3"], 
                       help="Phase filters")
    
    args = parser.parse_args()
    
    config = {
        "indication": args.indication,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "phases": args.phases
    }
    
    builder = CTGovUniverseBuilder(config)
    
    # Search for trials
    trials = builder.search_trials(
        indication=args.indication,
        start_date=args.start_date,
        end_date=args.end_date,
        phase_filter=args.phases
    )
    
    # Save results
    output_dir = Path(args.output_dir)
    builder.save_trials(trials, output_dir)
    
    print(f"✅ Universe build completed!")
    print(f"📊 Found {len(trials)} trials")
    print(f"📁 Output: {output_dir}")


if __name__ == "__main__":
    main()
