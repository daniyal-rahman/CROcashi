#!/usr/bin/env python3
"""
Backtest ClinicalTrials.gov SEC wiring with LLM.
"""

import json
import sys
from pathlib import Path

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.ingest.ctgov import CTGovIngester
from ncfd.mapping.resolve_service import ResolveService
from ncfd.config import get_config


def fetch_2_months_ctgov_data() -> List[Dict[str, Any]]:
    """Fetch 2 months of CTGov data."""
    logger = get_logger(__name__)
    logger.info("Fetching 2 months of CTGov data")
    
    # Calculate date range (2 months ago to now)
    end_date = date.today()
    start_date = end_date - timedelta(days=60)
    
    logger.info(f"Fetching trials from {start_date} to {end_date}")
    
    # Use CTGov client to fetch data
    client = CtgovClient()
    
    trials = []
    total_fetched = 0
    page_count = 0
    
    try:
        # Fetch trials in batches
        for trial_data in client.iter_raw(since=start_date, page_size=100):
            total_fetched += 1
            
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
            
            # Extract dates
            status_module = trial_data.get("protocolSection", {}).get("statusModule", {})
            first_posted = status_module.get("studyFirstPostDateStruct", {}).get("date")
            last_update = status_module.get("lastUpdatePostDateStruct", {}).get("date")
            
            trial_info = {
                "nct_id": nct_id,
                "sponsor_name": sponsor_name,
                "phases": phases,
                "indication": indication,
                "first_posted": first_posted,
                "last_update": last_update,
                "raw_data": trial_data
            }
            
            trials.append(trial_info)
            
            # Log progress every 100 trials
            if len(trials) % 100 == 0:
                logger.info(f"Fetched {len(trials)} trials (total processed: {total_fetched})")
            
            # Limit to reasonable number for testing (can be increased)
            if len(trials) >= 1000:
                logger.info(f"Reached limit of {len(trials)} trials")
                break
                
    except Exception as e:
        logger.error(f"Error fetching trials: {e}")
    
    logger.info(f"Fetched {len(trials)} trials total")
    return trials


def test_sponsor_resolution_with_llm(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Test sponsor resolution including LLM research."""
    logger = get_logger(__name__)
    logger.info("Testing sponsor resolution with LLM research")
    
    # Load resolver config
    cfg_path = Path("config/resolver.yaml")
    if not cfg_path.exists():
        logger.error("No resolver config found")
        return {"error": "No resolver config found"}
    
    with open(cfg_path, "r") as f:
        resolver_config = yaml.safe_load(f) or {}
    
    # Reset engine
    reset_engine()
    
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not db_url:
        logger.error("No database URL found in environment")
        return {"error": "No database URL found"}
    
    logger.info(f"Using database URL: {db_url}")
    
    resolution_results = []
    llm_calls = 0
    deterministic_matches = 0
    probabilistic_matches = 0
    
    with session_scope(db_url) as session:
        for i, trial in enumerate(trials):
            nct_id = trial.get("nct_id")
            sponsor_name = trial.get("sponsor_name")
            
            if not sponsor_name:
                resolution_results.append({
                    "nct_id": nct_id,
                    "sponsor_name": None,
                    "resolved": False,
                    "company_id": None,
                    "confidence": 0.0,
                    "method": "no_sponsor",
                    "error": None,
                    "llm_called": False
                })
                continue
            
            try:
                if i % 50 == 0:  # Log every 50th sponsor to avoid spam
                    logger.info(f"Resolving sponsor {i+1}/{len(trials)}: {sponsor_name}")
                
                # Use the full resolution flow with LLM research
                run_id = f"backtest-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
                options = FlowOptions(
                    cfg=resolver_config,
                    run_id=run_id,
                    persist=False,  # Don't persist for backtest
                    decider="auto",  # Enable LLM research
                    apply_trial=False,
                    skip_det=False,
                    k=25,
                    json_out=False
                )
                
                # Capture the resolution result by temporarily redirecting stdout
                import io
                import contextlib
                
                captured_output = io.StringIO()
                with contextlib.redirect_stdout(captured_output):
                    run_resolution(
                        session=session,
                        sponsor_text=sponsor_name,
                        nct_id=nct_id,
                        options=options,
                        ctx_override=None
                    )
                
                output = captured_output.getvalue()
                
                # Parse the output to extract resolution details
                resolved = False
                company_id = None
                confidence = 0.0
                method = "unknown"
                llm_called = "LLM" in output
                
                if llm_called:
                    llm_calls += 1
                
                # Extract resolution details from output
                if "Academic/Government Sponsor - Skipping" in output:
                    # Academic sponsor was correctly filtered out
                    resolved = False
                    method = "academic_skip"
                    confidence = 0.0
                    company_id = None
                elif "mode: deterministic:" in output:
                    deterministic_matches += 1
                    resolved = True
                    method = "deterministic"
                    confidence = 1.0
                    # Extract company_id from output
                    import re
                    company_match = re.search(r"company_id: (\d+)", output)
                    if company_match:
                        company_id = int(company_match.group(1))
                elif "mode: probabilistic:accept" in output:
                    probabilistic_matches += 1
                    resolved = True
                    method = "probabilistic:accept"
                    # Extract confidence from output
                    import re
                    conf_match = re.search(r"p: ([\d.]+)", output)
                    if conf_match:
                        confidence = float(conf_match.group(1))
                    company_match = re.search(r"company_id: (\d+)", output)
                    if company_match:
                        company_id = int(company_match.group(1))
                elif "mode: accept" in output and "source: llm" in output:
                    resolved = True
                    method = "llm:accept"
                    confidence = 1.0
                    # Extract company_id from output
                    import re
                    company_match = re.search(r"company_id: (\d+)", output)
                    if company_match:
                        company_id = int(company_match.group(1))
                
                resolution_results.append({
                    "nct_id": nct_id,
                    "sponsor_name": sponsor_name,
                    "resolved": resolved,
                    "company_id": company_id,
                    "confidence": confidence,
                    "method": method,
                    "error": None,
                    "llm_called": llm_called,
                    "output": output[:500]  # Store first 500 chars for debugging
                })
                
                if i % 50 == 0:  # Log every 50th resolution
                    if resolved:
                        logger.info(f"✅ Resolved {sponsor_name} -> Company {company_id} ({method}, p={confidence:.3f})")
                    else:
                        logger.info(f"❌ No resolution for {sponsor_name} ({method})")
                    
            except Exception as e:
                import traceback
                error_details = f"{type(e).__name__}: {str(e)}"
                logger.error(f"Error resolving {sponsor_name}: {error_details}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                resolution_results.append({
                    "nct_id": nct_id,
                    "sponsor_name": sponsor_name,
                    "resolved": False,
                    "company_id": None,
                    "confidence": 0.0,
                    "method": "error",
                    "error": error_details,
                    "llm_called": False
                })
    
    logger.info(f"Resolution complete: {deterministic_matches} deterministic, {probabilistic_matches} probabilistic, {llm_calls} LLM calls")
    
    return {
        "resolution_results": resolution_results,
        "config_loaded": len(resolver_config) > 0,
        "llm_calls": llm_calls,
        "deterministic_matches": deterministic_matches,
        "probabilistic_matches": probabilistic_matches
    }


def analyze_wiring_results_with_llm(trials: List[Dict[str, Any]], resolution_results: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze the wiring results including LLM usage."""
    logger = get_logger(__name__)
    logger.info("Analyzing wiring results with LLM")
    
    results = resolution_results.get("resolution_results", [])
    
    # Basic metrics
    total_trials = len(results)
    resolved_trials = sum(1 for r in results if r.get("resolved", False))
    error_trials = sum(1 for r in results if r.get("error"))
    llm_calls = sum(1 for r in results if r.get("llm_called", False))
    
    # Method analysis
    method_counts = {}
    for r in results:
        method = r.get("method", "unknown")
        method_counts[method] = method_counts.get(method, 0) + 1
    
    # Sponsor analysis
    sponsor_counts = {}
    for r in results:
        sponsor = r.get("sponsor_name")
        if sponsor:
            sponsor_counts[sponsor] = sponsor_counts.get(sponsor, 0) + 1
    
    # Top unresolved sponsors (excluding academic skips)
    unresolved_sponsors = {}
    for r in results:
        if not r.get("resolved") and r.get("sponsor_name") and r.get("method") != "academic_skip":
            sponsor = r.get("sponsor_name")
            unresolved_sponsors[sponsor] = unresolved_sponsors.get(sponsor, 0) + 1
    
    # Top resolved sponsors
    resolved_sponsors = {}
    for r in results:
        if r.get("resolved") and r.get("sponsor_name"):
            sponsor = r.get("sponsor_name")
            resolved_sponsors[sponsor] = resolved_sponsors.get(sponsor, 0) + 1
    
    metrics = {
        "total_trials": total_trials,
        "resolved_trials": resolved_trials,
        "error_trials": error_trials,
        "wiring_success_rate": resolved_trials / total_trials if total_trials > 0 else 0,
        "error_rate": error_trials / total_trials if total_trials > 0 else 0,
        "llm_calls": llm_calls,
        "llm_call_rate": llm_calls / total_trials if total_trials > 0 else 0,
        "method_distribution": method_counts,
        "unique_sponsors": len(sponsor_counts),
        "top_unresolved_sponsors": dict(sorted(unresolved_sponsors.items(), key=lambda x: x[1], reverse=True)[:10]),
        "top_resolved_sponsors": dict(sorted(resolved_sponsors.items(), key=lambda x: x[1], reverse=True)[:10])
    }
    
    logger.info(f"Wiring analysis complete: {resolved_trials}/{total_trials} resolved ({metrics['wiring_success_rate']:.1%}), {llm_calls} LLM calls")
    
    return {
        "metrics": metrics,
        "detailed_results": results
    }


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="CTGov + SEC Wiring Test with LLM Research")
    parser.add_argument("--output", default="backtest/ctgov_sec_wiring_with_llm_report.json", help="Output file path")
    parser.add_argument("--limit", type=int, default=1000, help="Limit number of trials to test")
    args = parser.parse_args()
    
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("Starting CTGov + SEC Wiring Test with LLM Research")
    
    # Fetch trials
    trials = fetch_2_months_ctgov_data()
    if len(trials) > args.limit:
        trials = trials[:args.limit]
        logger.info(f"Limited to {args.limit} trials for testing")
    
    # Test resolution
    resolution_results = test_sponsor_resolution_with_llm(trials)
    
    # Analyze results
    analysis = analyze_wiring_results_with_llm(trials, resolution_results)
    
    # Combine results
    final_results = {
        "test_info": {
            "date": datetime.now(UTC).isoformat(),
            "trials_fetched": len(trials),
            "date_range": "2 months",
            "test_type": "CTGov + SEC wiring with LLM research"
        },
        "resolution_stats": {
            "llm_calls": resolution_results.get("llm_calls", 0),
            "deterministic_matches": resolution_results.get("deterministic_matches", 0),
            "probabilistic_matches": resolution_results.get("probabilistic_matches", 0)
        },
        **analysis
    }
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(final_results, f, indent=2, default=str)
    
    # Print summary
    metrics = final_results["metrics"]
    print(f"\n🎯 CTGov + SEC Wiring Test with LLM Summary:")
    print(f"  Total trials: {metrics['total_trials']}")
    print(f"  Resolved trials: {metrics['resolved_trials']}")
    print(f"  Wiring success rate: {metrics['wiring_success_rate']:.1%}")
    print(f"  LLM calls: {metrics['llm_calls']}")
    print(f"  LLM call rate: {metrics['llm_call_rate']:.1%}")
    print(f"  Report saved to: {args.output}")
    
    # Print method distribution
    print(f"\n📊 Method Distribution:")
    for method, count in metrics['method_distribution'].items():
        print(f"  {method}: {count}")
    
    # Print top resolved sponsors
    print(f"\n✅ Top Resolved Sponsors:")
    for sponsor, count in list(metrics['top_resolved_sponsors'].items())[:5]:
        print(f"  {sponsor}: {count}")
    
    # Print top unresolved sponsors
    print(f"\n❌ Top Unresolved Sponsors:")
    for sponsor, count in list(metrics['top_unresolved_sponsors'].items())[:5]:
        print(f"  {sponsor}: {count}")


if __name__ == "__main__":
    main()
