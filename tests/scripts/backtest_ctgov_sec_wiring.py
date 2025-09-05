#!/usr/bin/env python3
"""
Backtest ClinicalTrials.gov SEC wiring.
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
            
            # Rate limiting
            if total_fetched % 100 == 0:
                time.sleep(1)  # Be nice to the API
                
    except Exception as e:
        logger.error(f"Error fetching trials: {e}")
    
    logger.info(f"Final count: {len(trials)} trials from {total_fetched} processed")
    return trials


def test_sponsor_resolution_with_database(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Test sponsor resolution with actual database."""
    logger = get_logger(__name__)
    logger.info("Testing sponsor resolution with database")
    
    # Reset engine to ensure environment variables are picked up
    reset_engine()
    
    # Get the PostgreSQL URL from environment
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not db_url:
        logger.error("No database URL found in environment")
        return {"error": "No database URL found"}
    
    logger.info(f"Using database URL: {db_url}")
    
    # Load resolver config
    cfg_path = Path("config/resolver.yaml")
    if not cfg_path.exists():
        logger.error("No resolver config found")
        return {"error": "No resolver config"}
    
    with open(cfg_path, "r") as f:
        resolver_config = yaml.safe_load(f) or {}
    
    # Test resolution for each sponsor
    resolution_results = []
    
    # Explicitly pass the database URL
    with session_scope(db_url) as session:
        for i, trial_info in enumerate(trials):
            nct_id = trial_info["nct_id"]
            sponsor_name = trial_info["sponsor_name"]
            
            if not sponsor_name:
                resolution_results.append({
                    "nct_id": nct_id,
                    "sponsor_name": None,
                    "resolved": False,
                    "company_id": None,
                    "confidence": 0.0,
                    "method": "no_sponsor",
                    "error": None
                })
                continue
            
            try:
                if i % 50 == 0:  # Log every 50th sponsor to avoid spam
                    logger.info(f"Resolving sponsor {i+1}/{len(trials)}: {sponsor_name}")
                
                # Attempt resolution
                result = resolve_sponsor(session, sponsor_name, resolver_config)
                
                if result and result.get("company_id"):
                    resolution_results.append({
                        "nct_id": nct_id,
                        "sponsor_name": sponsor_name,
                        "resolved": True,
                        "company_id": result.get("company_id"),
                        "confidence": result.get("p", 0.0),
                        "method": result.get("mode", "unknown"),
                        "error": None
                    })
                    if i % 50 == 0:  # Log successful resolutions
                        logger.info(f"✅ Resolved {sponsor_name} -> Company {result.get('company_id')} (p={result.get('p', 0.0):.3f})")
                else:
                    resolution_results.append({
                        "nct_id": nct_id,
                        "sponsor_name": sponsor_name,
                        "resolved": False,
                        "company_id": None,
                        "confidence": 0.0,
                        "method": result.get("mode", "unknown") if result else "no_match",
                        "error": None
                    })
                    if i % 50 == 0:  # Log failed resolutions
                        logger.info(f"❌ No resolution for {sponsor_name}")
                    
            except Exception as e:
                logger.error(f"Error resolving {sponsor_name}: {e}")
                resolution_results.append({
                    "nct_id": nct_id,
                    "sponsor_name": sponsor_name,
                    "resolved": False,
                    "company_id": None,
                    "confidence": 0.0,
                    "method": "error",
                    "error": str(e)
                })
    
    return {
        "resolution_results": resolution_results,
        "config_loaded": len(resolver_config) > 0
    }


def analyze_wiring_results(trials: List[Dict[str, Any]], resolution_results: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze the wiring results."""
    logger = get_logger(__name__)
    logger.info("Analyzing wiring results")
    
    results = resolution_results.get("resolution_results", [])
    
    # Basic metrics
    total_trials = len(results)
    resolved_trials = sum(1 for r in results if r.get("resolved", False))
    error_trials = sum(1 for r in results if r.get("error"))
    
    # Confidence analysis
    high_confidence = sum(1 for r in results if r.get("resolved") and r.get("confidence", 0) >= 0.9)
    medium_confidence = sum(1 for r in results if r.get("resolved") and 0.7 <= r.get("confidence", 0) < 0.9)
    low_confidence = sum(1 for r in results if r.get("resolved") and r.get("confidence", 0) < 0.7)
    
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
    
    # Top unresolved sponsors
    unresolved_sponsors = {}
    for r in results:
        if not r.get("resolved") and r.get("sponsor_name"):
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
        "high_confidence_resolutions": high_confidence,
        "medium_confidence_resolutions": medium_confidence,
        "low_confidence_resolutions": low_confidence,
        "method_distribution": method_counts,
        "unique_sponsors": len(sponsor_counts),
        "top_unresolved_sponsors": dict(sorted(unresolved_sponsors.items(), key=lambda x: x[1], reverse=True)[:10]),
        "top_resolved_sponsors": dict(sorted(resolved_sponsors.items(), key=lambda x: x[1], reverse=True)[:10])
    }
    
    logger.info(f"Wiring analysis complete: {resolved_trials}/{total_trials} resolved ({metrics['wiring_success_rate']:.1%})")
    
    return {
        "metrics": metrics,
        "detailed_results": results
    }


def generate_verification_suggestions(metrics: Dict[str, Any]) -> List[str]:
    """Generate suggestions for verifying the wiring results."""
    logger = get_logger(__name__)
    logger.info("Generating verification suggestions")
    
    suggestions = []
    
    # Based on success rate
    success_rate = metrics.get("wiring_success_rate", 0)
    if success_rate < 0.5:
        suggestions.append("LOW SUCCESS RATE: Consider improving sponsor resolution algorithms")
    elif success_rate < 0.8:
        suggestions.append("MODERATE SUCCESS RATE: Review unresolved sponsors for patterns")
    else:
        suggestions.append("HIGH SUCCESS RATE: Focus on edge cases and verification")
    
    # Based on confidence distribution
    high_conf = metrics.get("high_confidence_resolutions", 0)
    total_resolved = metrics.get("resolved_trials", 0)
    if total_resolved > 0:
        high_conf_rate = high_conf / total_resolved
        if high_conf_rate < 0.7:
            suggestions.append("LOW CONFIDENCE: Many low-confidence matches - verify manually")
    
    # Based on unresolved sponsors
    top_unresolved = metrics.get("top_unresolved_sponsors", {})
    if top_unresolved:
        suggestions.append(f"TOP UNRESOLVED: Focus on {list(top_unresolved.keys())[:3]} for manual review")
    
    # Based on resolved sponsors
    top_resolved = metrics.get("top_resolved_sponsors", {})
    if top_resolved:
        suggestions.append(f"TOP RESOLVED: Verify {list(top_resolved.keys())[:3]} are correct matches")
    
    # Verification methods
    verification_methods = [
        "MANUAL SAMPLING: Randomly sample 100 resolved sponsors and verify manually",
        "KNOWN COMPANIES: Test with known public companies (e.g., Pfizer, Biogen)",
        "CROSS-REFERENCE: Compare with SEC EDGAR database for known companies",
        "ALIAS TESTING: Test common company aliases and variations",
        "CONFIDENCE THRESHOLD: Only accept resolutions above 0.9 confidence",
        "DUPLICATE CHECK: Verify no duplicate company assignments",
        "GEOGRAPHIC VERIFICATION: Check if resolved companies match trial locations",
        "INDUSTRY VERIFICATION: Verify companies are in relevant industries",
        "SEC FILING VERIFICATION: Check SEC filings for sponsor mentions",
        "MARKET CAP VERIFICATION: Verify resolved companies are public US companies"
    ]
    
    suggestions.extend(verification_methods)
    
    return suggestions


def run_comprehensive_wiring_test() -> Dict[str, Any]:
    """Run the comprehensive CTGov + SEC wiring test."""
    logger = get_logger(__name__)
    logger.info("Starting comprehensive CTGov + SEC wiring test")
    
    # Fetch 2 months of CTGov data
    trials = fetch_2_months_ctgov_data()
    
    if not trials:
        return {"error": "No trials fetched"}
    
    # Test sponsor resolution
    resolution_results = test_sponsor_resolution_with_database(trials)
    
    if "error" in resolution_results:
        return resolution_results
    
    # Analyze results
    analysis = analyze_wiring_results(trials, resolution_results)
    
    # Generate verification suggestions
    verification_suggestions = generate_verification_suggestions(analysis["metrics"])
    
    # Create comprehensive report
    report = {
        "test_info": {
            "date": datetime.now().isoformat(),
            "trials_fetched": len(trials),
            "date_range": "2 months",
            "test_type": "CTGov + SEC wiring"
        },
        "metrics": analysis["metrics"],
        "verification_suggestions": verification_suggestions,
        "detailed_results": analysis["detailed_results"],
        "sample_trials": trials[:10]  # Include sample for verification
    }
    
    return report


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Comprehensive CTGov + SEC Wiring Test")
    parser.add_argument("--output", default="backtest/ctgov_sec_wiring_report.json", help="Output file path")
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    logger = get_logger(__name__)
    
    # Run comprehensive test
    report = run_comprehensive_wiring_test()
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    logger.info(f"Report saved to {output_path}")
    
    # Print summary
    if "error" not in report:
        metrics = report["metrics"]
        suggestions = report["verification_suggestions"]
        
        print(f"\n🎯 CTGov + SEC Wiring Test Summary:")
        print(f"  Total trials: {metrics['total_trials']}")
        print(f"  Resolved trials: {metrics['resolved_trials']}")
        print(f"  Wiring success rate: {metrics['wiring_success_rate']:.1%}")
        print(f"  High confidence: {metrics['high_confidence_resolutions']}")
        print(f"  Unique sponsors: {metrics['unique_sponsors']}")
        print(f"  Report saved to: {output_path}")
        
        print(f"\n🔍 Top Verification Suggestions:")
        for i, suggestion in enumerate(suggestions[:5], 1):
            print(f"  {i}. {suggestion}")
        
        print(f"\n📊 Method Distribution:")
        for method, count in metrics.get("method_distribution", {}).items():
            print(f"  {method}: {count}")
        
        if metrics.get("top_resolved_sponsors"):
            print(f"\n✅ Top Resolved Sponsors:")
            for sponsor, count in list(metrics["top_resolved_sponsors"].items())[:5]:
                print(f"  {sponsor}: {count}")
            
    else:
        print(f"❌ Test failed: {report['error']}")
    
    return 0


if __name__ == "__main__":
    exit(main())
