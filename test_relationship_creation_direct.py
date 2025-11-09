"""
Test relationship creation directly to see if it works.
"""
import sys
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.DEBUG)

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.entities import Drug
from database.models.relationships import TrialDrug
from src.entity_resolution.relationship_builder import RelationshipBuilder
from src.entity_resolution.types import RelationshipExtraction, ExtractedEntity, EntityType

# Get a real trial and drug
with get_db_session() as session:
    trial = session.query(ClinicalTrial).filter_by(nct_id='NCT00496353').first()
    drug = session.query(Drug).filter_by(primary_name='MK2461').first()
    
    if not trial or not drug:
        print("Trial or drug not found")
        sys.exit(1)
    
    print(f"Trial: {trial.nct_id} ({trial.trial_id})")
    print(f"Drug: {drug.primary_name} ({drug.drug_id})")
    
    # Check if relationship already exists
    existing = session.query(TrialDrug).filter_by(
        trial_id=trial.trial_id,
        drug_id=drug.drug_id
    ).first()
    
    if existing:
        print("Relationship already exists, deleting it first")
        session.delete(existing)
        session.commit()
    
    # Create relationship
    builder = RelationshipBuilder(session)
    
    rel_extraction = RelationshipExtraction(
        relationship_type='trial_drug',
        source_entity=ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name=trial.trial_title,
            identifiers={'nct_id': trial.nct_id},
            context={},
            source_name='test',
            source_identifier=trial.nct_id
        ),
        target_entity=ExtractedEntity(
            entity_type=EntityType.DRUG,
            name=drug.primary_name,
            identifiers={},
            context={},
            source_name='test',
            source_identifier=trial.nct_id
        ),
        attributes={'arm_name': 'experimental'},
        temporal={}
    )
    
    print("\nCreating relationship...")
    result = builder.create_relationship(
        rel_extraction,
        trial.trial_id,
        drug.drug_id,
        'test'
    )
    
    print(f"Result: {result}")
    print(f"Stats: {builder.get_stats()}")
    
    # Check if it's in the session
    print(f"\nObjects in session.new: {len(session.new)}")
    for obj in session.new:
        if isinstance(obj, TrialDrug):
            print(f"  TrialDrug: trial_id={obj.trial_id}, drug_id={obj.drug_id}")
    
    # Try to commit
    try:
        session.commit()
        print("\n✅ Commit successful")
        
        # Verify it's in database
        created = session.query(TrialDrug).filter_by(
            trial_id=trial.trial_id,
            drug_id=drug.drug_id
        ).first()
        
        if created:
            print(f"✅ Relationship exists in database")
            print(f"   arm_name: {created.arm_name}")
        else:
            print("❌ Relationship not in database after commit")
    except Exception as e:
        print(f"\n❌ Commit failed: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()

