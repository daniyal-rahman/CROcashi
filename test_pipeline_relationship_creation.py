"""
Test relationship creation through the actual pipeline to see where it fails.
"""
import sys
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialDrug
from database.models.staging import StagingRawData
from database.models import SourceProcessingLog
from src.processing.pipeline import ProcessingPipeline
from sqlalchemy import and_

# Get a trial that should have drugs
nct_id = 'NCT00496353'

with get_db_session() as session:
    # Delete processing log to force re-processing
    session.query(SourceProcessingLog).filter_by(
        source_name='clinicaltrials_gov',
        source_identifier=nct_id
    ).delete()
    
    # Mark as unprocessed
    staging = session.query(StagingRawData).filter_by(
        source_system='clinicaltrials_gov',
        source_record_id=nct_id
    ).first()
    
    if staging:
        staging.processed = False
        staging.processed_at = None
        session.commit()
        print(f"✅ Reset {nct_id} for re-processing")
    
    # Get initial count
    trial = session.query(ClinicalTrial).filter_by(nct_id=nct_id).first()
    if trial:
        initial_count = session.query(TrialDrug).filter_by(trial_id=trial.trial_id).count()
        print(f"Initial drug relationships: {initial_count}")

# Process with detailed logging
print("\nProcessing trial...")
pipeline = ProcessingPipeline(batch_size=1)

# Add custom logging to see what's happening
import logging
logging.getLogger('src.processing.pipeline').setLevel(logging.DEBUG)
logging.getLogger('src.entity_resolution.relationship_builder').setLevel(logging.DEBUG)

stats = pipeline.process_source('clinicaltrials_gov', limit=1)

print(f"\nProcessing stats: {stats}")

# Check final count
with get_db_session() as session:
    trial = session.query(ClinicalTrial).filter_by(nct_id=nct_id).first()
    if trial:
        final_count = session.query(TrialDrug).filter_by(trial_id=trial.trial_id).count()
        print(f"\nFinal drug relationships: {final_count}")
        
        if final_count > initial_count:
            print(f"✅ SUCCESS: Relationships created!")
        else:
            print(f"❌ FAILED: No relationships created")
            
            # Check processing log
            log = session.query(SourceProcessingLog).filter_by(
                source_name='clinicaltrials_gov',
                source_identifier=nct_id
            ).order_by(SourceProcessingLog.processing_started_at.desc()).first()
            
            if log:
                print(f"\nProcessing log:")
                print(f"  Status: {log.processing_status}")
                print(f"  Relationships created (log): {log.relationships_created}")
                if log.errors:
                    print(f"  Errors: {log.errors}")

