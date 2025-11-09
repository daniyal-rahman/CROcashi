"""
Re-process trials that were processed but have no drug relationships to verify the fix.
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialDrug
from database.models.staging import StagingRawData
from database.models import SourceProcessingLog
from src.processing.pipeline import ProcessingPipeline
from sqlalchemy import and_


def reprocess_trials_without_drugs(limit: int = 10):
    """Re-process trials that have no drug relationships."""
    print("\n" + "="*70)
    print("RE-PROCESSING TRIALS WITHOUT DRUG RELATIONSHIPS")
    print("="*70)
    
    with get_db_session() as session:
        # Find trials without drug relationships that were successfully processed
        trials_without_drugs = session.query(ClinicalTrial).outerjoin(
            TrialDrug
        ).filter(
            TrialDrug.trial_id == None
        ).join(
            StagingRawData,
            ClinicalTrial.nct_id == StagingRawData.source_record_id
        ).filter(
            StagingRawData.source_system == 'clinicaltrials_gov',
            StagingRawData.processed == True
        ).limit(limit).all()
        
        print(f"\nFound {len(trials_without_drugs)} trials without drug relationships")
        
        if not trials_without_drugs:
            print("No trials to re-process")
            return
        
        # Mark them as unprocessed
        nct_ids = [trial.nct_id for trial in trials_without_drugs]
        print(f"\nRe-processing trials: {', '.join(nct_ids[:5])}...")
        
        # Reset processing status
        session.query(StagingRawData).filter(
            StagingRawData.source_record_id.in_(nct_ids)
        ).update({
            'processed': False,
            'processed_at': None
        })
        
        # Delete old processing logs
        session.query(SourceProcessingLog).filter(
            and_(
                SourceProcessingLog.source_name == 'clinicaltrials_gov',
                SourceProcessingLog.source_identifier.in_(nct_ids)
            )
        ).delete()
        
        session.commit()
        print(f"✅ Reset {len(nct_ids)} trials for re-processing")
    
    # Process them
    print("\nProcessing trials...")
    pipeline = ProcessingPipeline(batch_size=50)
    stats = pipeline.process_source('clinicaltrials_gov', limit=len(nct_ids))
    
    print(f"\nProcessing Results:")
    print(f"  Processed: {stats['records_processed']}/{len(nct_ids)}")
    print(f"  Failed: {stats['records_failed']}")
    print(f"  Relationships created: {stats['relationships_created']}")
    
    # Verify results
    print("\n" + "="*70)
    print("VERIFICATION")
    print("="*70)
    
    with get_db_session() as session:
        # Check how many now have drug relationships
        trials_now_with_drugs = session.query(ClinicalTrial).join(
            TrialDrug
        ).filter(
            ClinicalTrial.nct_id.in_(nct_ids)
        ).distinct().count()
        
        print(f"\nTrials now with drug relationships: {trials_now_with_drugs}/{len(nct_ids)}")
        
        if trials_now_with_drugs > 0:
            print(f"✅ SUCCESS: {trials_now_with_drugs} trials now have drug relationships!")
            print(f"   Improvement: {trials_now_with_drugs}/{len(nct_ids)} = {trials_now_with_drugs/len(nct_ids)*100:.1f}%")
        else:
            print(f"❌ No improvement - relationships still not being created")
        
        # Show example
        if trials_now_with_drugs > 0:
            example_trial = session.query(ClinicalTrial).join(
                TrialDrug
            ).filter(
                ClinicalTrial.nct_id.in_(nct_ids)
            ).first()
            
            if example_trial:
                drug_count = session.query(TrialDrug).filter_by(
                    trial_id=example_trial.trial_id
                ).count()
                print(f"\nExample: {example_trial.nct_id} now has {drug_count} drug relationship(s)")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Re-process trials to verify fix')
    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Number of trials to re-process (default: 10)'
    )
    
    args = parser.parse_args()
    reprocess_trials_without_drugs(limit=args.limit)

