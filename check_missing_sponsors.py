"""
Check why trials are missing sponsors - do they have sponsor data in raw data?
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialSponsor
from database.models.staging import StagingRawData
from sqlalchemy import func

with get_db_session() as session:
    # Get trials without sponsors
    trials_without = session.query(ClinicalTrial).outerjoin(
        TrialSponsor
    ).filter(TrialSponsor.trial_id == None).limit(20).all()
    
    print(f"Checking {len(trials_without)} trials without sponsors...")
    print("="*70)
    
    has_sponsor_data = 0
    missing_sponsor_data = 0
    
    for trial in trials_without:
        staging = session.query(StagingRawData).filter_by(
            source_system='clinicaltrials_gov',
            source_record_id=trial.nct_id
        ).first()
        
        if staging:
            raw_data = staging.raw_data
            
            # Check for sponsor data
            sponsor_data = None
            if 'protocolSection' in raw_data:
                protocol = raw_data.get('protocolSection', {})
                sponsor_module = protocol.get('sponsorCollaboratorsModule', {})
                lead_sponsor = sponsor_module.get('leadSponsor', {})
                if lead_sponsor:
                    sponsor_data = lead_sponsor
            elif 'sponsor' in raw_data:
                sponsor_data = raw_data.get('sponsor', {})
            
            if sponsor_data:
                sponsor_name = sponsor_data.get('agency', sponsor_data.get('name', ''))
                if sponsor_name:
                    has_sponsor_data += 1
                    print(f"✅ {trial.nct_id}: Has sponsor '{sponsor_name}' in raw data")
                else:
                    missing_sponsor_data += 1
                    print(f"⚠️  {trial.nct_id}: Has sponsor object but no name")
            else:
                missing_sponsor_data += 1
                print(f"❌ {trial.nct_id}: No sponsor data in raw data")
    
    print("\n" + "="*70)
    print(f"Summary:")
    print(f"  Trials with sponsor data: {has_sponsor_data}")
    print(f"  Trials missing sponsor data: {missing_sponsor_data}")
    print(f"  Total checked: {len(trials_without)}")

