"""
Re-process all trials that are missing sponsor relationships.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialSponsor
from database.models.staging import StagingRawData
from database.models import SourceProcessingLog
from src.processing.pipeline import ProcessingPipeline

def reprocess_missing_sponsors(limit=None):
    """Re-process trials missing sponsor relationships."""
    with get_db_session() as session:
        # Find trials without sponsors
        trials_without = session.query(ClinicalTrial).outerjoin(
            TrialSponsor
        ).filter(TrialSponsor.trial_id == None).all()
        
        if limit:
            trials_without = trials_without[:limit]
        
        print(f"\n{'='*70}")
        print(f"RE-PROCESSING TRIALS WITHOUT SPONSOR RELATIONSHIPS")
        print(f"{'='*70}\n")
        print(f"Found {len(trials_without)} trials without sponsors")
        
        if not trials_without:
            print("✅ All trials have sponsors!")
            return
        
        # Reset processing status
        nct_ids = [trial.nct_id for trial in trials_without]
        print(f"\nRe-processing trials: {', '.join(nct_ids[:5])}...")
        
        for trial in trials_without:
            # Delete processing log
            session.query(SourceProcessingLog).filter_by(
                source_name='clinicaltrials_gov',
                source_identifier=trial.nct_id
            ).delete()
            
            # Mark as unprocessed
            staging = session.query(StagingRawData).filter_by(
                source_system='clinicaltrials_gov',
                source_record_id=trial.nct_id
            ).first()
            if staging:
                staging.processed = False
                staging.processed_at = None
        
        session.commit()
        print(f"✅ Reset {len(trials_without)} trials for re-processing\n")
        
        # Process in batches
        pipeline = ProcessingPipeline(batch_size=50)
        stats = pipeline.process_source('clinicaltrials_gov', limit=len(trials_without))
        
        print(f"\nProcessing Results:")
        print(f"  Processed: {stats.get('records_processed', 0)}/{len(trials_without)}")
        print(f"  Failed: {stats.get('records_failed', 0)}")
        print(f"  Relationships created: {stats.get('relationships_created', 0)}")
        
        # Verify
        print(f"\n{'='*70}")
        print("VERIFICATION")
        print(f"{'='*70}\n")
        
        trials_now_with = session.query(ClinicalTrial).join(
            TrialSponsor
        ).filter(ClinicalTrial.nct_id.in_(nct_ids)).distinct().count()
        
        print(f"Trials now with sponsors: {trials_now_with}/{len(trials_without)}")
        if trials_now_with > 0:
            print(f"✅ SUCCESS: {trials_now_with} trials now have sponsor relationships!")
            print(f"   Improvement: {trials_now_with}/{len(trials_without)} = {trials_now_with/len(trials_without)*100:.1f}%")
            
            # Show example
            example = session.query(ClinicalTrial).join(
                TrialSponsor
            ).filter(ClinicalTrial.nct_id.in_(nct_ids)).first()
            if example:
                sponsor = session.query(TrialSponsor).filter_by(
                    trial_id=example.trial_id
                ).first()
                print(f"\nExample: {example.nct_id} now has sponsor (type: {sponsor.entity_type})")
        else:
            print("❌ No new sponsor relationships created")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Limit number of trials to process')
    args = parser.parse_args()
    
    reprocess_missing_sponsors(limit=args.limit)

