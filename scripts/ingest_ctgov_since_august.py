#!/usr/bin/env python3
"""
Ingest ClinicalTrials.gov data since August.
"""

import json
import sys
from pathlib import Path

from ncfd.ingest.ctgov import CTGovIngester
from ncfd.config import get_config


def load_ctgov_config() -> Dict[str, Any]:
    """Load CTGov configuration."""
    config_path = Path("config/ctgov_config.yaml")
    if not config_path.exists():
        # Fallback to pipeline config
        config_path = Path("config/pipeline_config.yaml")
        if not config_path.exists():
            raise FileNotFoundError("No CTGov configuration found")
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f) or {}
    
    # Extract CTGov-specific config
    if "ctgov" in config:
        return config["ctgov"]
    else:
        return config


def ingest_ctgov_since_august(max_trials: Optional[int] = None) -> Dict[str, Any]:
    """Ingest CTGov data since August 1st, 2025."""
    logger = get_logger(__name__)
    logger.info("Starting CTGov ingestion since August 1st, 2025")
    
    # Load configuration
    config = load_ctgov_config()
    
    # Initialize pipeline
    pipeline = CtgovPipeline(config)
    
    # Set since date to August 1st, 2025
    since_date = "2025-08-01"
    
    # Run ingestion
    if max_trials:
        logger.info(f"Running limited ingestion: max_trials={max_trials}, since_date={since_date}")
        result = pipeline.run_limited_ingestion(
            max_studies=max_trials,
            since_date=since_date
        )
    else:
        logger.info(f"Running full ingestion since {since_date}")
        # For full ingestion, we'll use a large number
        result = pipeline.run_limited_ingestion(
            max_studies=10000,  # Large number to get all trials
            since_date=since_date
        )
    
    # Log results
    logger.info(f"Ingestion completed:")
    logger.info(f"  Success: {result.success}")
    logger.info(f"  Trials processed: {result.trials_processed}")
    logger.info(f"  Trials new: {result.trials_new}")
    logger.info(f"  Trials updated: {result.trials_updated}")
    logger.info(f"  Changes detected: {result.changes_detected}")
    logger.info(f"  Processing time: {result.processing_time_seconds:.2f} seconds")
    
    if result.errors:
        logger.error(f"Errors: {result.errors}")
    
    return {
        "success": result.success,
        "trials_processed": result.trials_processed,
        "trials_new": result.trials_new,
        "trials_updated": result.trials_updated,
        "changes_detected": result.changes_detected,
        "processing_time_seconds": result.processing_time_seconds,
        "errors": result.errors,
        "warnings": result.warnings
    }


def get_trials_for_wiring_test(limit: int = 100) -> List[Dict[str, Any]]:
    """Get trials for wiring test."""
    logger = get_logger(__name__)
    logger.info(f"Getting {limit} trials for wiring test")
    
    reset_engine()
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    
    trials = []
    with session_scope(db_url) as session:
        # Get trials with sponsor information
        trial_records = session.query(Trial).filter(
            Trial.sponsor_text.isnot(None)
        ).limit(limit).all()
        
        for trial in trial_records:
            trials.append({
                "nct_id": trial.nct_id,
                "sponsor_name": trial.sponsor_text,
                "trial_id": trial.trial_id,
                "created_at": trial.created_at.isoformat() if trial.created_at else None
            })
    
    logger.info(f"Retrieved {len(trials)} trials for wiring test")
    return trials


def run_wiring_test_on_trials(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run wiring test on the provided trials."""
    logger = get_logger(__name__)
    logger.info(f"Running wiring test on {len(trials)} trials")
    
    # Import the wiring test function
    from tests.scripts.backtest_ctgov_sec_wiring_with_llm import test_sponsor_resolution_with_llm, analyze_wiring_results_with_llm
    
    # Run the wiring test
    resolution_results = test_sponsor_resolution_with_llm(trials)
    
    # Analyze results
    analysis = analyze_wiring_results_with_llm(trials, resolution_results)
    
    return {
        "resolution_results": resolution_results,
        "analysis": analysis
    }


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="CTGov Ingestion Since August 1st, 2025")
    parser.add_argument("--max-trials", type=int, help="Maximum number of trials to ingest (default: all)")
    parser.add_argument("--wiring-test-limit", type=int, default=100, help="Number of trials to test wiring on")
    parser.add_argument("--output", default="backtest/ctgov_august_ingestion_report.json", help="Output file path")
    parser.add_argument("--skip-ingestion", action="store_true", help="Skip ingestion and only run wiring test")
    args = parser.parse_args()
    
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("Starting CTGov ingestion and wiring test")
    
    results = {
        "ingestion": None,
        "wiring_test": None,
        "test_info": {
            "date": datetime.now(UTC).isoformat(),
            "since_date": "2025-08-01",
            "max_trials": args.max_trials,
            "wiring_test_limit": args.wiring_test_limit
        }
    }
    
    # Step 1: Ingest CTGov data
    if not args.skip_ingestion:
        logger.info("Step 1: Ingesting CTGov data since August 1st, 2025")
        ingestion_results = ingest_ctgov_since_august(args.max_trials)
        results["ingestion"] = ingestion_results
        
        if not ingestion_results["success"]:
            logger.error("Ingestion failed, stopping")
            return
    else:
        logger.info("Skipping ingestion as requested")
    
    # Step 2: Get trials for wiring test
    logger.info("Step 2: Getting trials for wiring test")
    trials = get_trials_for_wiring_test(args.wiring_test_limit)
    
    if not trials:
        logger.error("No trials found for wiring test")
        return
    
    # Step 3: Run wiring test
    logger.info("Step 3: Running wiring test")
    wiring_results = run_wiring_test_on_trials(trials)
    results["wiring_test"] = wiring_results
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    # Print summary
    print(f"\n🎯 CTGov Ingestion and Wiring Test Summary:")
    print(f"  Since date: 2025-08-01")
    
    if results["ingestion"]:
        ingestion = results["ingestion"]
        print(f"  Trials ingested: {ingestion['trials_processed']}")
        print(f"  New trials: {ingestion['trials_new']}")
        print(f"  Updated trials: {ingestion['trials_updated']}")
        print(f"  Processing time: {ingestion['processing_time_seconds']:.2f} seconds")
    
    if results["wiring_test"]:
        wiring = results["wiring_test"]["analysis"]
        metrics = wiring["metrics"]
        print(f"  Wiring test trials: {metrics['total_trials']}")
        print(f"  Resolved trials: {metrics['resolved_trials']}")
        print(f"  Success rate: {metrics['wiring_success_rate']:.1%}")
        print(f"  LLM calls: {metrics['llm_calls']}")
        print(f"  LLM call rate: {metrics['llm_call_rate']:.1%}")
    
    print(f"  Report saved to: {args.output}")


if __name__ == "__main__":
    main()
