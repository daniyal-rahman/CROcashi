#!/usr/bin/env python3
"""
Demo script for running backtests on ClinicalTrials.gov data.
"""

import json
import sys
from pathlib import Path

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.catalyst.backtest import BacktestRunner
from ncfd.config import get_config


def create_demo_trial_data():
    """Create demo trial data with proper sponsor information."""
    return [
        {
            "doc_id": "NCT04388254",
            "sponsor": "Cassava Sciences, Inc.",
            "phase": "phase_2",
            "indication": "alzheimers_disease",
            "completion_date": "2023-12-01",
            "method_card": {
                "primary_endpoint": "ADAS-Cog11",
                "is_pivotal": False,
                "study_phase": "phase_2",
                "indication": "alzheimers_disease"
            },
            "claims": [
                {"type": "design_fact", "proposition": "endpoint: ADAS-Cog11 mean change over 6 months"},
                {"type": "limitation", "proposition": "endpoint changed post-registration"}
            ]
        },
        {
            "doc_id": "NCT01234567",
            "sponsor": "Biogen Inc.",
            "phase": "phase_3",
            "indication": "multiple_sclerosis",
            "completion_date": "2024-06-01",
            "method_card": {
                "primary_endpoint": "EDSS",
                "is_pivotal": True,
                "study_phase": "phase_3",
                "indication": "multiple_sclerosis"
            }
        },
        {
            "doc_id": "NCT09876543",
            "sponsor": "Private Biotech LLC",
            "phase": "phase_2",
            "indication": "oncology",
            "completion_date": "2024-03-01",
            "method_card": {
                "primary_endpoint": "PFS",
                "is_pivotal": False,
                "study_phase": "phase_2",
                "indication": "oncology"
            }
        },
        {
            "doc_id": "NCT05555555",
            "sponsor": "Eli Lilly and Company",
            "phase": "phase_3",
            "indication": "diabetes",
            "completion_date": "2024-09-01",
            "method_card": {
                "primary_endpoint": "HbA1c",
                "is_pivotal": True,
                "study_phase": "phase_3",
                "indication": "diabetes"
            }
        }
    ]


def analyze_ctgov_discovery(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze CTGov discovery and public company wiring."""
    
    # Public US company indicators
    public_us_indicators = [
        "inc", "corp", "corporation", "company", "ltd", "limited",
        "pharmaceuticals", "pharma", "biotech", "therapeutics"
    ]
    
    # Known public US companies (in production, this would come from SEC database)
    known_public_companies = {
        "Cassava Sciences, Inc.": {"exchange": "NASDAQ", "cik": "0001341762"},
        "Biogen Inc.": {"exchange": "NASDAQ", "cik": "0000875040"},
        "Eli Lilly and Company": {"exchange": "NYSE", "cik": "0000059478"},
        "Private Biotech LLC": {"exchange": None, "cik": None}
    }
    
    metrics = {
        "total_trials_discovered": len(trials),
        "trials_with_nct_id": 0,
        "trials_with_sponsor_info": 0,
        "trials_with_phase_info": 0,
        "trials_with_indication": 0,
        "trials_with_completion_date": 0,
        "trials_with_public_us_sponsor": 0,
        "public_us_sponsors": [],
        "non_public_us_sponsors": []
    }
    
    for trial in trials:
        # Check NCT ID
        if trial.get("doc_id"):
            metrics["trials_with_nct_id"] += 1
        
        # Check sponsor information
        sponsor_name = trial.get("sponsor")
        if sponsor_name:
            metrics["trials_with_sponsor_info"] += 1
            
            # Check if it's a known public US company
            if sponsor_name in known_public_companies:
                company_info = known_public_companies[sponsor_name]
                if company_info["exchange"]:
                    metrics["trials_with_public_us_sponsor"] += 1
                    metrics["public_us_sponsors"].append({
                        "nct_id": trial.get("doc_id"),
                        "sponsor": sponsor_name,
                        "exchange": company_info["exchange"],
                        "cik": company_info["cik"]
                    })
                else:
                    metrics["non_public_us_sponsors"].append({
                        "nct_id": trial.get("doc_id"),
                        "sponsor": sponsor_name,
                        "reason": "Private company"
                    })
            else:
                # Use heuristic for unknown companies
                sponsor_lower = sponsor_name.lower()
                is_public_us = any(indicator in sponsor_lower for indicator in public_us_indicators)
                
                if is_public_us:
                    metrics["trials_with_public_us_sponsor"] += 1
                    metrics["public_us_sponsors"].append({
                        "nct_id": trial.get("doc_id"),
                        "sponsor": sponsor_name,
                        "exchange": "Unknown",
                        "cik": None
                    })
                else:
                    metrics["non_public_us_sponsors"].append({
                        "nct_id": trial.get("doc_id"),
                        "sponsor": sponsor_name,
                        "reason": "Not identified as public US company"
                    })
        
        # Check other fields
        if trial.get("phase") or trial.get("method_card", {}).get("study_phase"):
            metrics["trials_with_phase_info"] += 1
        
        if trial.get("indication") or trial.get("method_card", {}).get("indication"):
            metrics["trials_with_indication"] += 1
        
        if trial.get("completion_date"):
            metrics["trials_with_completion_date"] += 1
    
    # Calculate coverage percentages
    total_trials = metrics["total_trials_discovered"]
    if total_trials > 0:
        metrics["nct_id_coverage"] = metrics["trials_with_nct_id"] / total_trials
        metrics["sponsor_info_coverage"] = metrics["trials_with_sponsor_info"] / total_trials
        metrics["phase_info_coverage"] = metrics["trials_with_phase_info"] / total_trials
        metrics["indication_coverage"] = metrics["trials_with_indication"] / total_trials
        metrics["completion_date_coverage"] = metrics["trials_with_completion_date"] / total_trials
        metrics["public_us_sponsor_rate"] = metrics["trials_with_public_us_sponsor"] / total_trials
    
    if metrics["trials_with_sponsor_info"] > 0:
        metrics["public_us_filter_rate"] = metrics["trials_with_public_us_sponsor"] / metrics["trials_with_sponsor_info"]
    
    return metrics


def main():
    """Run the CTGov backtest demo."""
    print("🔬 CTGov Discovery & Public Company Wiring Backtest Demo")
    print("=" * 60)
    
    # Create demo data
    trials = create_demo_trial_data()
    print(f"📋 Analyzing {len(trials)} demo trials...")
    
    # Run analysis
    metrics = analyze_ctgov_discovery(trials)
    
    print("\n📊 CTGov Discovery Metrics")
    print("-" * 40)
    print(f"Total Trials Discovered: {metrics['total_trials_discovered']}")
    print(f"NCT ID Coverage: {metrics['nct_id_coverage']:.1%}")
    print(f"Sponsor Info Coverage: {metrics['sponsor_info_coverage']:.1%}")
    print(f"Phase Info Coverage: {metrics['phase_info_coverage']:.1%}")
    print(f"Indication Coverage: {metrics['indication_coverage']:.1%}")
    print(f"Completion Date Coverage: {metrics['completion_date_coverage']:.1%}")
    
    print("\n🏢 Public Company Wiring Analysis")
    print("-" * 40)
    print(f"Public US Sponsor Rate: {metrics['public_us_sponsor_rate']:.1%}")
    print(f"Public US Filter Rate: {metrics['public_us_filter_rate']:.1%}")
    
    print(f"\n✅ Public US Sponsors Found: {len(metrics['public_us_sponsors'])}")
    for sponsor in metrics['public_us_sponsors']:
        print(f"  - {sponsor['sponsor']} ({sponsor['exchange']}) - {sponsor['nct_id']}")
    
    print(f"\n❌ Non-Public US Sponsors: {len(metrics['non_public_us_sponsors'])}")
    for sponsor in metrics['non_public_us_sponsors']:
        print(f"  - {sponsor['sponsor']} - {sponsor['reason']}")
    
    print("\n🎯 Key Insights")
    print("-" * 40)
    print("✅ With proper sponsor data, we can identify public US companies")
    print("✅ Public US filter can be applied effectively")
    print("✅ Company database integration is critical")
    print("✅ Trial version handling needs improvement")
    
    print("\n" + "=" * 60)
    print("✅ Demo completed successfully!")


if __name__ == "__main__":
    main()
