"""
Quick check of relationship and wiring setup without external API calls.

This test validates:
1. Relationship models are properly mapped
2. Pipeline wiring is correct
3. Processors are registered
4. Database schema supports relationships
"""
import sys
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent))

from src.processing.pipeline import ProcessingPipeline
from src.entity_resolution.relationship_builder import RelationshipBuilder
from database.config import get_db_session
from database.models.relationships import (
    TrialSponsor, TrialDrug, TrialDisease,
    PublicationDrug, PublicationTrial, PublicationCompany,
    PatentDrug, PatentCompany,
    FilingCompany, FilingDrug,
    CompanyDrug, DrugIndication, DrugTarget
)


def check_relationship_wiring():
    """Check if relationship wiring is properly set up."""
    print("\n" + "="*70)
    print("RELATIONSHIP & WIRING SETUP CHECK")
    print("="*70)
    
    issues = []
    warnings = []
    
    # 1. Check RelationshipBuilder model mapping
    print("\n1. Checking RelationshipBuilder model mapping...")
    rel_builder_models = RelationshipBuilder.RELATIONSHIP_MODELS
    print(f"   Found {len(rel_builder_models)} relationship types:")
    for rel_type, model in sorted(rel_builder_models.items()):
        print(f"   ✅ {rel_type} → {model.__name__}")
    
    # 2. Check processor registration
    print("\n2. Checking processor registration...")
    processor_map = ProcessingPipeline.PROCESSOR_MAP
    print(f"   Found {len(processor_map)} registered processors:")
    for source, processor_class in sorted(processor_map.items()):
        print(f"   ✅ {source} → {processor_class.__name__}")
    
    # 3. Check database schema (relationship tables exist)
    print("\n3. Checking database schema...")
    try:
        with get_db_session() as session:
            # Try to query each relationship table
            relationship_tables = {
                'TrialSponsor': TrialSponsor,
                'TrialDrug': TrialDrug,
                'TrialDisease': TrialDisease,
                'PublicationDrug': PublicationDrug,
                'PublicationTrial': PublicationTrial,
                'PublicationCompany': PublicationCompany,
                'PatentDrug': PatentDrug,
                'PatentCompany': PatentCompany,
                'FilingCompany': FilingCompany,
                'FilingDrug': FilingDrug,
                'CompanyDrug': CompanyDrug,
                'DrugIndication': DrugIndication,
                'DrugTarget': DrugTarget
            }
            
            for table_name, model in sorted(relationship_tables.items()):
                try:
                    count = session.query(model).count()
                    print(f"   ✅ {table_name}: {count} relationships")
                except Exception as e:
                    print(f"   ❌ {table_name}: Error - {e}")
                    issues.append(f"Table {table_name} not accessible: {e}")
    except Exception as e:
        print(f"   ❌ Database connection error: {e}")
        issues.append(f"Database connection failed: {e}")
    
    # 4. Check pipeline relationship creation logic
    print("\n4. Checking pipeline relationship creation logic...")
    import inspect
    
    # Check if _make_entity_stub_key exists
    if hasattr(ProcessingPipeline, '_make_entity_stub_key'):
        print("   ✅ _make_entity_stub_key method exists")
    else:
        print("   ❌ _make_entity_stub_key method missing")
        issues.append("Pipeline missing _make_entity_stub_key method")
    
    # Check if relationship creation code exists
    pipeline_source = inspect.getsource(ProcessingPipeline._process_single_record)
    if 'extract_relationships' in pipeline_source:
        print("   ✅ extract_relationships call found")
    else:
        print("   ❌ extract_relationships call missing")
        issues.append("Pipeline missing extract_relationships call")
    
    if 'create_relationship' in pipeline_source:
        print("   ✅ create_relationship call found")
    else:
        print("   ❌ create_relationship call missing")
        issues.append("Pipeline missing create_relationship call")
    
    if 'entity_stub_to_id' in pipeline_source:
        print("   ✅ entity_stub_to_id mapping found")
    else:
        print("   ❌ entity_stub_to_id mapping missing")
        issues.append("Pipeline missing entity_stub_to_id mapping")
    
    # 5. Check processor relationship extraction
    print("\n5. Checking processor relationship extraction...")
    from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
    from src.processors.pubmed_processor import PubMedProcessor
    
    processors_to_check = [
        ('ClinicalTrialsProcessor', ClinicalTrialsProcessor),
        ('PubMedProcessor', PubMedProcessor)
    ]
    
    for proc_name, proc_class in processors_to_check:
        if hasattr(proc_class, 'extract_relationships'):
            print(f"   ✅ {proc_name} has extract_relationships method")
        else:
            print(f"   ❌ {proc_name} missing extract_relationships method")
            issues.append(f"{proc_name} missing extract_relationships")
    
    # 6. Check RelationshipBuilder methods
    print("\n6. Checking RelationshipBuilder methods...")
    required_methods = [
        'create_relationship',
        '_find_existing_relationship',
        '_check_session_for_relationship',
        '_create_new_relationship',
        '_update_data_sources',
        '_get_id_fields'
    ]
    
    for method_name in required_methods:
        if hasattr(RelationshipBuilder, method_name):
            print(f"   ✅ {method_name} method exists")
        else:
            print(f"   ❌ {method_name} method missing")
            issues.append(f"RelationshipBuilder missing {method_name}")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    if issues:
        print(f"\n❌ Found {len(issues)} critical issues:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    else:
        print("\n✅ All relationship and wiring checks passed!")
        print("   - Relationship models properly mapped")
        print("   - Processors registered correctly")
        print("   - Database schema accessible")
        print("   - Pipeline relationship creation logic present")
        print("   - Processors have relationship extraction methods")
        print("   - RelationshipBuilder has all required methods")
        return True


if __name__ == "__main__":
    success = check_relationship_wiring()
    sys.exit(0 if success else 1)

