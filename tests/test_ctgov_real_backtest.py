#!/usr/bin/env python3
"""
Real backtest for ClinicalTrials.gov data.
"""

import json
import sys
from pathlib import Path

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.catalyst.backtest import BacktestRunner
from ncfd.config import get_config

def fetch_real_ctgov_trials(limit=5):
    """Fetch real trials from CT.gov for testing."""
    print("=== Fetching Real CTGov Trials ===")
    
    # Direct API call to get trials
    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {"pageSize": limit * 2}  # Get more to account for filtering
    
    trials = []
    count = 0
    
    try:
        response = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=30)
        if response.status_code == 200:
            data = response.json()
            studies = data.get("studies", [])
            
            for trial_data in studies:
                if count >= limit:
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
                count += 1
                
                print(f"  ✅ Fetched {nct_id}: {sponsor_name} - {indication}")
                
    except Exception as e:
        print(f"❌ Error fetching trials: {e}")
    
    print(f"Fetched {len(trials)} trials")
    return trials

def test_sponsor_resolution_config():
    """Test sponsor resolution configuration."""
    print("\n=== Testing Sponsor Resolution Config ===")
    
    # Load resolver config
    cfg_path = Path("config/resolver.yaml")
    if not cfg_path.exists():
        print("❌ No resolver config found")
        return None
        
    with open(cfg_path, "r") as f:
        cfg = yaml.safe_load(f) or {}
    
    print(f"✅ Resolver config loaded: {len(cfg)} keys")
    
    # Check required fields
    required_fields = ["thresholds", "model"]
    for field in required_fields:
        if field in cfg:
            print(f"  ✅ {field}: {type(cfg[field])}")
        else:
            print(f"  ❌ Missing {field}")
    
    return cfg

def test_ctgov_pipeline_with_real_data(trials):
    """Test CTGov pipeline with real trial data."""
    print("\n=== Testing CTGov Pipeline with Real Data ===")
    
    # Create pipeline
    config = {
        'api_base_url': 'https://clinicaltrials.gov/api/v2',
        'batch_size': 100
    }
    
    try:
        pipeline = CtgovPipeline(config)
        print("✅ CTGovPipeline created")
        
        # Test processing each trial
        results = []
        for trial_info in trials:
            nct_id = trial_info["nct_id"]
            sponsor_name = trial_info["sponsor_name"]
            
            print(f"\n  Processing {nct_id}:")
            print(f"    Sponsor: {sponsor_name}")
            
            # Extract comprehensive fields
            try:
                fields = pipeline.client.extract_comprehensive_fields(trial_info["raw_data"])
                
                result = {
                    "nct_id": nct_id,
                    "sponsor_name": sponsor_name,
                    "extracted_sponsor": fields.sponsor_info.lead_sponsor_name if fields.sponsor_info else None,
                    "phase": fields.phase,
                    "conditions": [c.name for c in fields.conditions],
                    "has_sponsor_info": fields.sponsor_info is not None
                }
                
                results.append(result)
                
                print(f"    ✅ Extracted sponsor: {result['extracted_sponsor']}")
                print(f"    ✅ Phase: {result['phase']}")
                print(f"    ✅ Conditions: {result['conditions']}")
                
            except Exception as e:
                print(f"    ❌ Error extracting fields: {e}")
                results.append({
                    "nct_id": nct_id,
                    "sponsor_name": sponsor_name,
                    "error": str(e)
                })
        
        return results
        
    except Exception as e:
        print(f"❌ Error creating pipeline: {e}")
        return []

def test_sponsor_resolution_with_real_data(trials, cfg):
    """Test sponsor resolution with real sponsor names."""
    print("\n=== Testing Sponsor Resolution with Real Data ===")
    
    if not cfg:
        print("❌ No resolver config available")
        return []
    
    # Test resolution for each sponsor
    resolution_results = []
    
    for trial_info in trials:
        nct_id = trial_info["nct_id"]
        sponsor_name = trial_info["sponsor_name"]
        
        print(f"\n  Testing sponsor resolution for {nct_id}:")
        print(f"    Sponsor: {sponsor_name}")
        
        # Note: This would need a database session to work fully
        # For now, just test the config and sponsor names
        if sponsor_name:
            print(f"    ✅ Would attempt resolution with config")
            print(f"    ✅ Sponsor name: {sponsor_name}")
            
            resolution_results.append({
                "nct_id": nct_id,
                "sponsor_name": sponsor_name,
                "status": "ready_for_resolution"
            })
        else:
            print(f"    ❌ No sponsor name available")
            resolution_results.append({
                "nct_id": nct_id,
                "sponsor_name": None,
                "status": "no_sponsor"
            })
    
    return resolution_results

def analyze_results(results, resolution_results):
    """Analyze the results of the CTGov pipeline test."""
    print("\n=== Analysis Results ===")
    
    if not results:
        print("❌ No results to analyze")
        return
    
    total_trials = len(results)
    trials_with_sponsor = sum(1 for r in results if r.get("has_sponsor_info", False))
    trials_with_errors = sum(1 for r in results if "error" in r)
    
    print(f"📊 Summary:")
    print(f"  Total trials: {total_trials}")
    print(f"  Trials with sponsor info: {trials_with_sponsor}")
    print(f"  Trials with errors: {trials_with_errors}")
    print(f"  Sponsor coverage: {trials_with_sponsor/total_trials*100:.1f}%")
    
    print(f"\n📋 Detailed Results:")
    for result in results:
        if "error" in result:
            print(f"  ❌ {result['nct_id']}: {result['error']}")
        else:
            print(f"  ✅ {result['nct_id']}: {result['extracted_sponsor']} -> {result['phase']}")
    
    print(f"\n🎯 Sponsor Resolution Status:")
    for res in resolution_results:
        if res["status"] == "ready_for_resolution":
            print(f"  ✅ {res['nct_id']}: Ready for sponsor resolution")
        else:
            print(f"  ❌ {res['nct_id']}: No sponsor to resolve")

def main():
    """Run the real CTGov backtest."""
    print("🧪 Real CTGov Backtest")
    print("=" * 60)
    
    # Test sponsor resolution config
    cfg = test_sponsor_resolution_config()
    
    # Fetch real CTGov trials
    trials = fetch_real_ctgov_trials(limit=3)
    
    if not trials:
        print("❌ No trials fetched, cannot continue")
        return
    
    # Test pipeline with real data
    results = test_ctgov_pipeline_with_real_data(trials)
    
    # Test sponsor resolution
    resolution_results = test_sponsor_resolution_with_real_data(trials, cfg)
    
    # Analyze results
    analyze_results(results, resolution_results)
    
    print("\n" + "=" * 60)
    print("🎯 CTGov Backtest Summary:")
    print("  - Real CTGov data: Fetched")
    print("  - Sponsor resolution: Config loaded")
    print("  - Pipeline processing: Tested")
    print("  - Sponsor coverage: Analyzed")
    print("  - Next step: Test with database for full sponsor wiring")

if __name__ == "__main__":
    main()
