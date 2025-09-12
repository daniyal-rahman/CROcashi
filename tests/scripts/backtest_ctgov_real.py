#!/usr/bin/env python3
"""
Backtest real ClinicalTrials.gov data.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any
import logging

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.ingest.ctgov import CTGovIngester
from ncfd.config import get_config
from ncfd.pipeline.orchestrator import PipelineOrchestrator

def get_logger(name: str) -> logging.Logger:
    """Get logger instance."""
    return logging.getLogger(name)


def fetch_real_ctgov_trials(limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch real trials from CT.gov API."""
    logger = get_logger(__name__)
    logger.info(f"Fetching {limit} real trials from CT.gov")
    
    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {"pageSize": limit * 2}  # Get more to account for filtering
    
    trials = []
    
    try:
        response = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=30)
        if response.status_code == 200:
            data = response.json()
            studies = data.get("studies", [])
            
            for trial_data in studies:
                if len(trials) >= limit:
                    break
                    
                # Extract basic info
                nct_id = trial_data.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
                if not nct_id:
                    continue
                    
                # Extract sponsor info
                sponsor_module = trial_data.get("protocolSection", {}).get("sponsorCollaboratorsModule", {})
                lead_sponsor = sponsor_module.get("leadSponsor", {})
                sponsor_name = lead_sponsor.get("name")
                
                # Extract phase info
                design_module = trial_data.get("protocolSection", {}).get("designModule", {})
                phases = design_module.get("phases", [])
                
                # Extract indication
                conditions_module = trial_data.get("protocolSection", {}).get("conditionsModule", {})
                conditions = conditions_module.get("conditions", [])
                indication = conditions[0] if conditions and isinstance(conditions[0], str) else None
                
                trial_info = {
                    "nct_id": nct_id,
                    "sponsor_name": sponsor_name,
                    "phases": phases,
                    "indication": indication,
                    "raw_data": trial_data
                }
                
                trials.append(trial_info)
                logger.info(f"Fetched {nct_id}: {sponsor_name} - {indication}")
                
    except Exception as e:
        logger.error(f"Error fetching trials: {e}")
    
    logger.info(f"Fetched {len(trials)} trials")
    return trials


def test_ctgov_pipeline(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Test the CTGov pipeline with real trial data."""
    logger = get_logger(__name__)
    logger.info("Testing CTGov pipeline with real data")
    
    # Create orchestrator
    config = {
        'ctgov': {
            'api_base_url': 'https://clinicaltrials.gov/api/v2',
            'batch_size': 100
        }
    }
    
    orchestrator = PipelineOrchestrator(config)
    
    # Test processing each trial
    results = []
    for trial_info in trials:
        nct_id = trial_info["nct_id"]
        sponsor_name = trial_info["sponsor_name"]
        
        try:
            # Extract comprehensive fields using orchestrator's CT.gov pipeline
            fields = orchestrator.ctgov_pipeline.client.extract_comprehensive_fields(trial_info["raw_data"])
            
            result = {
                "nct_id": nct_id,
                "sponsor_name": sponsor_name,
                "extracted_sponsor": fields.sponsor_info.lead_sponsor_name if fields.sponsor_info else None,
                "phase": fields.phase,
                "conditions": [c.name for c in fields.conditions],
                "has_sponsor_info": fields.sponsor_info is not None,
                "success": True
            }
            
            results.append(result)
            logger.info(f"✅ Processed {nct_id}: {result['extracted_sponsor']} -> {result['phase']}")
            
        except Exception as e:
            logger.error(f"❌ Error processing {nct_id}: {e}")
            results.append({
                "nct_id": nct_id,
                "sponsor_name": sponsor_name,
                "error": str(e),
                "success": False
            })
    
    return results


def test_sponsor_resolution(trials: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    """Test sponsor resolution with real sponsor names."""
    logger = get_logger(__name__)
    logger.info("Testing sponsor resolution with real data")
    
    # Load resolver config
    cfg_path = Path("config/resolver.yaml")
    if not cfg_path.exists():
        logger.error("No resolver config found")
        return {"error": "No resolver config"}
    
    with open(cfg_path, "r") as f:
        resolver_config = yaml.safe_load(f) or {}
    
    # Test resolution for each sponsor
    resolution_results = []
    
    for trial_info in trials:
        nct_id = trial_info["nct_id"]
        sponsor_name = trial_info["sponsor_name"]
        
        if sponsor_name:
            logger.info(f"Testing sponsor resolution for {nct_id}: {sponsor_name}")
            
            # Note: This would need a database session to work fully
            # For now, just test the config and sponsor names
            resolution_results.append({
                "nct_id": nct_id,
                "sponsor_name": sponsor_name,
                "status": "ready_for_resolution",
                "config_loaded": len(resolver_config) > 0
            })
        else:
            resolution_results.append({
                "nct_id": nct_id,
                "sponsor_name": None,
                "status": "no_sponsor",
                "config_loaded": False
            })
    
    return {
        "resolution_results": resolution_results,
        "config_loaded": len(resolver_config) > 0
    }


def run_ctgov_backtest(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run the real CTGov backtest."""
    logger = get_logger(__name__)
    logger.info("Starting real CTGov backtest")
    
    # Fetch real trials
    trials = fetch_real_ctgov_trials(limit=config.get("ctgov", {}).get("trial_limit", 5))
    
    if not trials:
        return {"error": "No trials fetched"}
    
    # Test pipeline
    pipeline_results = test_ctgov_pipeline(trials)
    
    # Test sponsor resolution
    resolution_results = test_sponsor_resolution(trials, config)
    
    # Calculate metrics
    total_trials = len(pipeline_results)
    successful_trials = sum(1 for r in pipeline_results if r.get("success", False))
    trials_with_sponsor = sum(1 for r in pipeline_results if r.get("has_sponsor_info", False))
    ready_for_resolution = sum(1 for r in resolution_results.get("resolution_results", []) 
                              if r.get("status") == "ready_for_resolution")
    
    metrics = {
        "total_trials": total_trials,
        "successful_trials": successful_trials,
        "trials_with_sponsor": trials_with_sponsor,
        "ready_for_resolution": ready_for_resolution,
        "pipeline_success_rate": successful_trials / total_trials if total_trials > 0 else 0,
        "sponsor_coverage": trials_with_sponsor / total_trials if total_trials > 0 else 0,
        "resolution_ready_rate": ready_for_resolution / total_trials if total_trials > 0 else 0
    }
    
    # Create detailed results
    results = {
        "metrics": metrics,
        "pipeline_results": pipeline_results,
        "resolution_results": resolution_results,
        "trials": trials
    }
    
    logger.info(f"CTGov backtest completed: {metrics}")
    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Real CTGov Backtest")
    parser.add_argument("--config", default="config/backtest.yaml", help="Config file path")
    parser.add_argument("--output", default="backtest/ctgov_real_results.json", help="Output file path")
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    logger = get_logger(__name__)
    
    # Load config
    try:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return 1
    
    # Run backtest
    results = run_ctgov_backtest(config)
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    logger.info(f"Results saved to {output_path}")
    
    # Print summary
    if "error" not in results:
        metrics = results["metrics"]
        print(f"\n🎯 CTGov Backtest Summary:")
        print(f"  Total trials: {metrics['total_trials']}")
        print(f"  Pipeline success rate: {metrics['pipeline_success_rate']:.1%}")
        print(f"  Sponsor coverage: {metrics['sponsor_coverage']:.1%}")
        print(f"  Ready for resolution: {metrics['resolution_ready_rate']:.1%}")
        print(f"  Results saved to: {output_path}")
    else:
        print(f"❌ Backtest failed: {results['error']}")
    
    return 0


if __name__ == "__main__":
    exit(main())
