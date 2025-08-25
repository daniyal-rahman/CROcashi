#!/usr/bin/env python
"""
Debug script to test Phase 1 trial ingestion without API calls.
This simulates the exact scenario that's failing in production.
"""

import json
import hashlib
import os
from datetime import datetime, date
from pathlib import Path
import sys

# Set environment variables for database connection
os.environ["POSTGRES_DSN"] = "postgresql+psycopg2://ncfd:ncfd@localhost:5433/ncfd"
os.environ["CONFIG_PROFILE"] = "local"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.ingest.ctgov import CtgovClient
from ncfd.db.session import session_scope
from ncfd.db.models import Trial, TrialVersion

def create_mock_phase1_trial():
    """Create a mock trial with only PHASE1 to test the constraint violation."""
    
    # This is a simplified version of what CTGov returns
    mock_trial = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT12345678",
                "briefTitle": "Test Phase 1 Trial",
                "officialTitle": "A Phase 1 Study of Test Drug"
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {
                    "name": "Test Pharma Inc"
                }
            },
            "designModule": {
                "phases": ["PHASE1", "PHASE2"],  # Only Phase 1 - this should cause the issue
                "enrollmentInfo": {
                    "count": 50
                }
            },
            "armsInterventionsModule": {
                "interventions": [
                    {
                        "type": "DRUG",
                        "name": "Test Drug"
                    }
                ]
            },
            "outcomesModule": {
                "primaryOutcomes": [
                    {
                        "measure": "Safety and Tolerability",
                        "timeFrame": "Up to 28 days"
                    }
                ]
            },
            "statusModule": {
                "overallStatus": "RECRUITING",
                "studyFirstPostDateStruct": {"date": "2025-01-01"},
                "lastUpdatePostDateStruct": {"date": "2025-08-25"}
            }
        }
    }
    
    return mock_trial

def test_phase1_ingestion():
    """Test ingesting a Phase 1 trial to reproduce the constraint violation."""
    
    print("=== Testing Phase 1 Trial Ingestion ===")
    
    # Create mock trial data
    raw_trial = create_mock_phase1_trial()
    nct_id = raw_trial["protocolSection"]["identificationModule"]["nctId"]
    
    print(f"Mock trial NCT ID: {nct_id}")
    print(f"Phases: {raw_trial['protocolSection']['designModule']['phases']}")
    
    # Test the filter logic
    client = CtgovClient()
    
    print("\n=== Testing Filter Logic ===")
    is_interventional = client._is_interventional(raw_trial)
    has_drug_biologic = client._has_drug_or_biologic(raw_trial)
    is_phase_2_3 = client._is_phase_2_or_3(raw_trial)
    
    print(f"Is interventional: {is_interventional}")
    print(f"Has drug/biologic: {has_drug_biologic}")
    print(f"Is Phase 2/3: {is_phase_2_3}")
    
    # Test field extraction
    print("\n=== Testing Field Extraction ===")
    try:
        fields = client.extract_fields(raw_trial)
        print(f"Extracted phase: {fields.phase}")
        print(f"Extracted sponsor: {fields.sponsor_text}")
        print(f"Extracted status: {fields.status}")
    except Exception as e:
        print(f"Field extraction failed: {e}")
        return
    
    # Test database insertion
    print("\n=== Testing Database Insertion ===")
    try:
        with session_scope() as session:
            # Check if trial already exists
            existing_trial = session.query(Trial).filter(Trial.nct_id == nct_id).one_or_none()
            
            if existing_trial:
                print(f"Trial {nct_id} already exists, deleting for clean test")
                session.delete(existing_trial)
                session.commit()
            
            # Create raw JSON string and hash
            raw_json_str = json.dumps(raw_trial, sort_keys=True, ensure_ascii=False)
            sha256 = hashlib.sha256(raw_json_str.encode("utf-8")).hexdigest()
            
            print(f"Creating new trial with phase: {fields.phase}")
            
            # Try to create the trial
            trial = Trial(
                nct_id=fields.nct_id,
                sponsor_text=fields.sponsor_text,
                phase=fields.phase,
                status=fields.status,
                primary_endpoint_text=fields.primary_endpoint_text,
                first_posted_date=fields.first_posted_date,
                last_update_posted_date=fields.last_update_posted_date,
                intervention_types=fields.intervention_types,
                current_sha256=sha256,
                last_seen_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            session.add(trial)
            print("Trial added to session, attempting commit...")
            
            # This should fail with the constraint violation
            session.commit()
            print("SUCCESS: Trial was inserted (this shouldn't happen!)")
            
    except Exception as e:
        print(f"Database insertion failed as expected: {e}")
        print(f"Error type: {type(e).__name__}")
        
        # Check if it's the constraint violation we expect
        if "CheckViolation" in str(e) or "ck_trials_phase_allowed" in str(e):
            print("✅ CORRECT: Got the expected constraint violation for Phase 1 trial")
        else:
            print("❌ UNEXPECTED: Got a different error than expected")

if __name__ == "__main__":
    test_phase1_ingestion()
