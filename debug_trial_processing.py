"""
Debug a specific trial to see where drug relationships are being lost.
"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialDrug
from database.models.staging import StagingRawData
from database.models import SourceProcessingLog
from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.relationship_builder import RelationshipBuilder


def debug_trial(nct_id: str):
    """Debug a specific trial's processing."""
    print(f"\n{'='*70}")
    print(f"DEBUGGING TRIAL: {nct_id}")
    print('='*70)
    
    with get_db_session() as session:
        # Get trial
        trial = session.query(ClinicalTrial).filter_by(nct_id=nct_id).first()
        if not trial:
            print(f"Trial {nct_id} not found")
            return
        
        print(f"\nTrial: {trial.trial_title}")
        
        # Get staging data
        staging = session.query(StagingRawData).filter_by(
            source_system='clinicaltrials_gov',
            source_record_id=nct_id
        ).first()
        
        if not staging:
            print("No staging data found")
            return
        
        raw_data = staging.raw_data
        
        # Step 1: Check raw data
        print("\n1. RAW DATA CHECK")
        print("-" * 70)
        
        interventions = []
        if 'protocolSection' in raw_data:
            protocol = raw_data.get('protocolSection', {})
            arms_module = protocol.get('armsInterventionsModule', {})
            interventions = arms_module.get('interventions', [])
        elif 'interventions' in raw_data:
            interventions = raw_data.get('interventions', [])
            if not isinstance(interventions, list):
                interventions = [interventions]
        
        print(f"Interventions in raw data: {len(interventions)}")
        drug_interventions = []
        for i, interv in enumerate(interventions):
            interv_type = interv.get('intervention_type', interv.get('type', 'unknown')).lower()
            interv_name = interv.get('intervention_name', interv.get('name', 'unknown'))
            print(f"  {i+1}. Type: {interv_type} - {interv_name}")
            if interv_type in ['drug', 'biological', 'biologic']:
                drug_interventions.append(interv)
        
        print(f"\nDrug-type interventions: {len(drug_interventions)}")
        
        # Step 2: Test entity extraction
        print("\n2. ENTITY EXTRACTION TEST")
        print("-" * 70)
        
        processor = ClinicalTrialsProcessor(session)
        entities = processor.extract_entities(raw_data)
        
        print(f"Entities extracted:")
        print(f"  Trials: {len(entities.get('trials', []))}")
        print(f"  Drugs: {len(entities.get('drugs', []))}")
        print(f"  Diseases: {len(entities.get('diseases', []))}")
        print(f"  Companies: {len(entities.get('companies', []))}")
        
        if entities.get('drugs'):
            print(f"\nExtracted drugs:")
            for i, drug in enumerate(entities['drugs'][:5]):
                print(f"  {i+1}. {drug.name} (type: {drug.entity_type.value})")
        
        # Step 3: Test entity resolution
        print("\n3. ENTITY RESOLUTION TEST")
        print("-" * 70)
        
        resolver = EntityResolver(session)
        resolved_drugs = []
        
        if entities.get('drugs'):
            for drug_entity in entities['drugs']:
                resolution = resolver.resolve(drug_entity)
                print(f"  Drug: {drug_entity.name}")
                print(f"    Status: {resolution.status.value}")
                print(f"    Entity ID: {resolution.entity_id}")
                if resolution.entity_id:
                    resolved_drugs.append(resolution.entity_id)
        
        print(f"\nResolved drug IDs: {len(resolved_drugs)}")
        
        # Step 4: Test relationship extraction
        print("\n4. RELATIONSHIP EXTRACTION TEST")
        print("-" * 70)
        
        # Simulate what pipeline does
        resolved_entities = {}
        id_to_entity = {}
        
        # Resolve trial
        if entities.get('trials'):
            trial_entity = entities['trials'][0]
            trial_resolution = resolver.resolve(trial_entity)
            if trial_resolution.entity_id:
                resolved_entities['trial'] = trial_resolution.entity_id
                id_to_entity[trial_resolution.entity_id] = trial_entity
        
        # Resolve drugs
        drug_ids = []
        for drug_entity in entities.get('drugs', []):
            resolution = resolver.resolve(drug_entity)
            if resolution.entity_id:
                drug_ids.append(resolution.entity_id)
                id_to_entity[resolution.entity_id] = drug_entity
        
        resolved_entities['drugs'] = drug_ids
        
        print(f"Resolved entities:")
        print(f"  Trial: {resolved_entities.get('trial')}")
        print(f"  Drugs: {len(resolved_entities.get('drugs', []))}")
        
        # Extract relationships
        relationships = processor.extract_relationships(
            raw_data,
            resolved_entities,
            id_to_entity
        )
        
        print(f"\nRelationships extracted: {len(relationships)}")
        for i, rel in enumerate(relationships):
            print(f"  {i+1}. {rel.relationship_type}")
            print(f"     Source: {rel.source_entity.entity_type.value} - {rel.source_entity.name}")
            print(f"     Target: {rel.target_entity.entity_type.value} - {rel.target_entity.name}")
        
        # Step 5: Check actual relationships in database
        print("\n5. DATABASE RELATIONSHIPS")
        print("-" * 70)
        
        db_relationships = session.query(TrialDrug).filter_by(
            trial_id=trial.trial_id
        ).all()
        
        print(f"Trial-drug relationships in database: {len(db_relationships)}")
        for rel in db_relationships:
            drug = session.query(Drug).filter_by(drug_id=rel.drug_id).first()
            if drug:
                print(f"  - {drug.primary_name}")
        
        # Step 6: Check processing log
        print("\n6. PROCESSING LOG")
        print("-" * 70)
        
        log = session.query(SourceProcessingLog).filter_by(
            source_name='clinicaltrials_gov',
            source_identifier=nct_id
        ).first()
        
        if log:
            print(f"Status: {log.processing_status}")
            print(f"Entities created: {log.entities_created or 0}")
            print(f"Entities matched: {log.entities_matched or 0}")
            print(f"Relationships created: {log.relationships_created or 0}")
            if log.errors:
                print(f"Errors: {log.errors}")
        
        # Step 7: Summary
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        
        print(f"Raw data interventions: {len(drug_interventions)}")
        print(f"Extracted drug entities: {len(entities.get('drugs', []))}")
        print(f"Resolved drug IDs: {len(resolved_drugs)}")
        print(f"Relationships extracted: {len(relationships)}")
        print(f"Database relationships: {len(db_relationships)}")
        
        if len(drug_interventions) > 0 and len(entities.get('drugs', [])) == 0:
            print("\n❌ ISSUE: Interventions in raw data but not extracted")
            print("   → Problem in processor.extract_entities()")
        elif len(entities.get('drugs', [])) > 0 and len(resolved_drugs) == 0:
            print("\n❌ ISSUE: Drugs extracted but not resolved")
            print("   → Problem in entity resolution")
        elif len(resolved_drugs) > 0 and len(relationships) == 0:
            print("\n❌ ISSUE: Drugs resolved but no relationships extracted")
            print("   → Problem in processor.extract_relationships()")
        elif len(relationships) > 0 and len(db_relationships) == 0:
            print("\n❌ ISSUE: Relationships extracted but not created in database")
            print("   → Problem in relationship builder or pipeline mapping")
        else:
            print("\n✅ All steps working correctly")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        nct_id = sys.argv[1]
    else:
        # Use the example from diagnostic
        nct_id = "NCT01946867"
    
    debug_trial(nct_id)

