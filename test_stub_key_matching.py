"""
Test if entity stub keys match between extraction and relationship creation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialDrug
from database.models.staging import StagingRawData
from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
from src.entity_resolution.entity_resolver import EntityResolver
from src.processing.pipeline import ProcessingPipeline
from src.entity_resolution.types import EntityType


def test_stub_key_matching(nct_id: str):
    """Test if stub keys match for a specific trial."""
    print(f"\n{'='*70}")
    print(f"TESTING STUB KEY MATCHING: {nct_id}")
    print('='*70)
    
    with get_db_session() as session:
        # Get staging data
        staging = session.query(StagingRawData).filter_by(
            source_system='clinicaltrials_gov',
            source_record_id=nct_id
        ).first()
        
        if not staging:
            print("No staging data found")
            return
        
        raw_data = staging.raw_data
        
        # Extract entities
        processor = ClinicalTrialsProcessor(session)
        entities = processor.extract_entities(raw_data)
        
        # Resolve entities and build stub mapping
        resolver = EntityResolver(session)
        entity_stub_to_id = {}
        id_to_entity = {}
        
        print("\n1. ENTITY RESOLUTION AND STUB KEY CREATION")
        print("-" * 70)
        
        for entity_type, entity_list in entities.items():
            for extracted_entity in entity_list:
                resolution = resolver.resolve(extracted_entity)
                
                if resolution.entity_id:
                    # Create stub key (same as pipeline does)
                    stub_key = ProcessingPipeline._make_entity_stub_key(extracted_entity)
                    entity_stub_to_id[stub_key] = resolution.entity_id
                    id_to_entity[resolution.entity_id] = extracted_entity
                    
                    print(f"\n{entity_type}: {extracted_entity.name}")
                    print(f"  Resolved ID: {resolution.entity_id}")
                    print(f"  Stub key: {stub_key}")
                    print(f"  Normalized name in stub: {stub_key[1]}")
        
        # Extract relationships
        resolved_entities = {}
        if entities.get('trials'):
            trial_entity = entities['trials'][0]
            trial_resolution = resolver.resolve(trial_entity)
            if trial_resolution.entity_id:
                resolved_entities['trial'] = trial_resolution.entity_id
        
        drug_ids = []
        for drug_entity in entities.get('drugs', []):
            resolution = resolver.resolve(drug_entity)
            if resolution.entity_id:
                drug_ids.append(resolution.entity_id)
        resolved_entities['drugs'] = drug_ids
        
        print("\n2. RELATIONSHIP EXTRACTION")
        print("-" * 70)
        
        relationships = processor.extract_relationships(
            raw_data,
            resolved_entities,
            id_to_entity
        )
        
        print(f"Relationships extracted: {len(relationships)}")
        
        for i, rel in enumerate(relationships):
            print(f"\nRelationship {i+1}: {rel.relationship_type}")
            
            # Get source stub key
            source_stub_key = ProcessingPipeline._make_entity_stub_key(rel.source_entity)
            source_id = entity_stub_to_id.get(source_stub_key)
            
            # Get target stub key
            target_stub_key = ProcessingPipeline._make_entity_stub_key(rel.target_entity)
            target_id = entity_stub_to_id.get(target_stub_key)
            
            print(f"  Source entity:")
            print(f"    Name: {rel.source_entity.name}")
            print(f"    Type: {rel.source_entity.entity_type.value}")
            print(f"    Stub key: {source_stub_key}")
            print(f"    Found in mapping: {'✅' if source_id else '❌'}")
            if source_id:
                print(f"    Mapped ID: {source_id}")
            
            print(f"  Target entity:")
            print(f"    Name: {rel.target_entity.name}")
            print(f"    Type: {rel.target_entity.entity_type.value}")
            print(f"    Stub key: {target_stub_key}")
            print(f"    Found in mapping: {'✅' if target_id else '❌'}")
            if target_id:
                print(f"    Mapped ID: {target_id}")
            
            # Check if keys match
            if not source_id:
                print(f"\n  ❌ SOURCE KEY MISMATCH:")
                print(f"     Looking for: {source_stub_key}")
                print(f"     Available keys:")
                for key in sorted(entity_stub_to_id.keys()):
                    if key[0] == source_stub_key[0]:  # Same entity type
                        print(f"       {key}")
            
            if not target_id:
                print(f"\n  ❌ TARGET KEY MISMATCH:")
                print(f"     Looking for: {target_stub_key}")
                print(f"     Available keys:")
                for key in sorted(entity_stub_to_id.keys()):
                    if key[0] == target_stub_key[0]:  # Same entity type
                        print(f"       {key}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        nct_id = sys.argv[1]
    else:
        nct_id = "NCT00496353"
    
    test_stub_key_matching(nct_id)

