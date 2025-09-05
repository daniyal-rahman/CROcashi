#!/usr/bin/env python3
"""
Debug Cassava trial processing.
"""

import json
import sys
from pathlib import Path

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.config import get_config

def debug_cassava_trial():
    """Debug the Cassava trial NCT05352763."""
    print("🔍 Debugging Cassava Trial NCT05352763")
    print("=" * 50)
    
    # Get the trial data
    url = "https://clinicaltrials.gov/api/v2/studies/NCT05352763"
    response = requests.get(url, headers={"Accept": "application/json"})
    trial_data = response.json()
    
    print(f"📋 Trial Title: {trial_data.get('protocolSection', {}).get('identificationModule', {}).get('briefTitle', 'Unknown')}")
    print(f"📋 Sponsor: {trial_data.get('protocolSection', {}).get('identificationModule', {}).get('organization', {}).get('fullName', 'Unknown')}")
    
    # Check interventions
    protocol = trial_data.get('protocolSection', {})
    arms = protocol.get('armsModule', {}).get('arms', [])
    
    print(f"\n🔬 Arms found: {len(arms)}")
    for i, arm in enumerate(arms):
        print(f"  Arm {i+1}: {arm.get('name', 'Unknown')}")
        interventions = arm.get('interventions', [])
        print(f"    Interventions: {len(interventions)}")
        
        for j, intervention in enumerate(interventions):
            print(f"      Intervention {j+1}:")
            print(f"        Type: {intervention.get('type', 'Unknown')}")
            print(f"        Name: {intervention.get('name', 'Unknown')}")
            print(f"        Other Names: {intervention.get('otherNames', [])}")
            print(f"        Description: {intervention.get('description', 'Unknown')}")
    
    # Test asset resolver
    print(f"\n🔧 Testing Asset Resolver:")
    resolver = AssetResolver()
    drug_names = resolver.extract_drug_names(trial_data)
    
    print(f"  Drug names extracted: {len(drug_names)}")
    for drug in drug_names:
        print(f"    - Original: {drug.original}")
        print(f"      Normalized: {drug.normalized}")
        print(f"      Type: {drug.name_type}")
        print(f"      Confidence: {drug.confidence}")
        print(f"      Source: {drug.source_field}")
    
    # Save raw data for inspection
    with open('cassava_trial_debug.json', 'w') as f:
        json.dump(trial_data, f, indent=2, default=str)
    
    print(f"\n💾 Raw trial data saved to cassava_trial_debug.json")

if __name__ == "__main__":
    debug_cassava_trial()
