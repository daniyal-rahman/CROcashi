"""
Comprehensive check for all missing field mappings.

Principle: Fields extracted into context but not saved to database in _build_entity_data()
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.staging import StagingRawData
from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
from src.processing.pipeline import ProcessingPipeline

# Expected mappings for ClinicalTrial
EXPECTED_MAPPINGS = {
    'phase': 'phase',
    'phase_numeric': 'phase_numeric',
    'status': 'status',
    'study_type': 'study_type',
    'enrollment': 'enrollment_target',  # enrollment in context -> enrollment_target in DB
    'start_date': 'start_date',
    'completion_date': 'completion_date',
    'why_stopped': 'why_stopped',
    'eudract_number': 'eudract_number',  # from identifiers
}

print("="*70)
print("COMPREHENSIVE FIELD MAPPING CHECK")
print("="*70)

# Check ClinicalTrial
print("\n1. ClinicalTrial Field Mappings:")
print("-" * 70)

with get_db_session() as session:
    # Get a sample trial
    trial = session.query(ClinicalTrial).first()
    if trial:
        staging = session.query(StagingRawData).filter_by(
            source_system='clinicaltrials_gov',
            source_record_id=trial.nct_id
        ).first()
        
        if staging:
            processor = ClinicalTrialsProcessor(session)
            entities = processor.extract_entities(staging.raw_data)
            
            if entities.get('trials'):
                trial_entity = entities['trials'][0]
                
                # Check what's in context
                context_fields = set(trial_entity.context.keys())
                identifier_fields = set(trial_entity.identifiers.keys())
                
                print(f"Context fields extracted: {sorted(context_fields)}")
                print(f"Identifier fields extracted: {sorted(identifier_fields)}")
                
                # Test _build_entity_data
                from database.models.clinical import ClinicalTrial as ClinicalTrialModel
                built_data = ProcessingPipeline._build_entity_data(trial_entity, ClinicalTrialModel)
                
                print(f"\nFields mapped in _build_entity_data:")
                mapped_fields = set(built_data.keys())
                # Remove ID and data_sources (always present)
                mapped_fields.discard('trial_id')
                mapped_fields.discard('data_sources')
                print(f"  {sorted(mapped_fields)}")
                
                # Find missing mappings
                missing = []
                
                # Check context fields
                for context_field, db_field in EXPECTED_MAPPINGS.items():
                    if context_field in context_fields:
                        if db_field not in mapped_fields:
                            missing.append(f"{context_field} (context) -> {db_field} (DB)")
                
                # Check identifier fields
                if 'eudract_number' in identifier_fields:
                    if 'eudract_number' not in mapped_fields:
                        missing.append("eudract_number (identifiers) -> eudract_number (DB)")
                
                if missing:
                    print(f"\n❌ Missing mappings:")
                    for m in missing:
                        print(f"  - {m}")
                else:
                    print(f"\n✅ All expected fields mapped")
                
                # Also check for fields that exist in DB but not extracted
                db_model_fields = {
                    'phase', 'phase_numeric', 'study_type', 'status',
                    'enrollment_target', 'enrollment_actual',
                    'start_date', 'completion_date', 'primary_completion_date',
                    'why_stopped', 'eudract_number'
                }
                
                print(f"\n2. Fields in DB model but potentially missing:")
                print("-" * 70)
                potentially_missing = []
                for db_field in db_model_fields:
                    if db_field not in mapped_fields:
                        # Check if it's in context or identifiers
                        context_key = None
                        for ctx_key, db_key in EXPECTED_MAPPINGS.items():
                            if db_key == db_field:
                                context_key = ctx_key
                                break
                        
                        if context_key and context_key in context_fields:
                            potentially_missing.append(f"{db_field} (extracted as '{context_key}' but not mapped)")
                        elif db_field in identifier_fields:
                            potentially_missing.append(f"{db_field} (in identifiers but not mapped)")
                        else:
                            # Field exists in DB but not extracted at all
                            pass
                
                if potentially_missing:
                    print("❌ Fields extracted but not mapped:")
                    for m in potentially_missing:
                        print(f"  - {m}")
                else:
                    print("✅ All extracted fields are mapped")

