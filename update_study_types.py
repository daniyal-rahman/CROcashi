"""
Update existing trials with study_type from raw data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.staging import StagingRawData
from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor

def update_study_types():
    """Update study_type for all trials from raw data."""
    with get_db_session() as session:
        # Get all trials with NULL study_type
        trials = session.query(ClinicalTrial).filter(
            ClinicalTrial.study_type == None
        ).all()
        
        print(f"Found {len(trials)} trials with NULL study_type")
        print("Updating from raw data...")
        
        processor = ClinicalTrialsProcessor(session)
        updated = 0
        
        for trial in trials:
            staging = session.query(StagingRawData).filter_by(
                source_system='clinicaltrials_gov',
                source_record_id=trial.nct_id
            ).first()
            
            if staging:
                # Extract study_type from raw data
                entities = processor.extract_entities(staging.raw_data)
                if entities.get('trials'):
                    trial_entity = entities['trials'][0]
                    study_type = trial_entity.context.get('study_type')
                    
                    if study_type:
                        # Normalize to lowercase (database constraint)
                        trial.study_type = study_type.lower()
                        updated += 1
        
        session.commit()
        print(f"✅ Updated {updated} trials with study_type")
        
        # Show breakdown
        from sqlalchemy import func
        breakdown = session.query(
            ClinicalTrial.study_type,
            func.count().label('count')
        ).group_by(ClinicalTrial.study_type).all()
        
        total = session.query(ClinicalTrial).count()
        print(f"\nUpdated breakdown:")
        for study_type, count in breakdown:
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {study_type or 'NULL'}: {count} ({pct:.1f}%)")

if __name__ == "__main__":
    update_study_types()

