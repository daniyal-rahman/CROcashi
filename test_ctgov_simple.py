#!/usr/bin/env python3
"""
Simple test for ClinicalTrials.gov functionality.
"""

import json
import sys
from pathlib import Path

from ncfd.ingest.ctgov import CTGovIngester
from ncfd.config import get_config

def test_simple_ctgov():
    """Test CTGov with simple API call."""
    print("=== Simple CTGov Test ===")
    
    # Direct API call to get any trial
    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {"pageSize": 5}
    
    try:
        response = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=30)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            studies = data.get("studies", [])
            print(f"Got {len(studies)} studies")
            
            # Test the client's extraction on each study
            client = CtgovClient()
            
            for i, study in enumerate(studies):
                print(f"\n--- Study {i+1} ---")
                
                # Get basic info
                nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
                print(f"NCT ID: {nct_id}")
                
                # Get sponsor info
                sponsor_module = study.get("protocolSection", {}).get("sponsorCollaboratorsModule", {})
                lead_sponsor = sponsor_module.get("leadSponsor", {})
                sponsor_name = lead_sponsor.get("name")
                print(f"Sponsor: {sponsor_name}")
                
                # Test extraction
                try:
                    fields = client.extract_comprehensive_fields(study)
                    print(f"✅ Extracted fields successfully")
                    print(f"  Extracted sponsor: {fields.sponsor_info.lead_sponsor_name if fields.sponsor_info else 'None'}")
                    print(f"  Phase: {fields.phase}")
                    print(f"  Indication: {fields.indication}")
                except Exception as e:
                    print(f"❌ Extraction error: {e}")
                
                # Only test first 2 to avoid too much output
                if i >= 1:
                    break
                    
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Run simple test."""
    print("🧪 Simple CTGov Test")
    print("=" * 30)
    
    test_simple_ctgov()

if __name__ == "__main__":
    main()
