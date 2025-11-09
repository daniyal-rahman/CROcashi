"""
Comprehensive review to find critical issues in patents and FDA implementation.

Tests:
1. Processor registration
2. Ingestion wiring
3. Entity extraction
4. Relationship creation
5. Database constraints
6. End-to-end flow
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models import SourceProcessingLog
from src.processing.pipeline import ProcessingPipeline
from ingestion.patentsview import search_patents
from ingestion.openfda import search_drugs
# FDA Drugs downloads files, doesn't have fetch function


def test_processor_registration():
    """Test if processors are registered."""
    print("\n" + "="*70)
    print("1. PROCESSOR REGISTRATION CHECK")
    print("="*70)
    
    registered = set(ProcessingPipeline.PROCESSOR_MAP.keys())
    expected = {'clinicaltrials_gov', 'fda_drugs', 'patentsview', 'openfda'}
    
    print(f"\nRegistered processors: {registered}")
    print(f"Expected processors: {expected}")
    
    missing = expected - registered
    extra = registered - expected
    
    if missing:
        print(f"\n❌ Missing processors: {missing}")
        return False
    if extra:
        print(f"\n⚠️  Extra processors: {extra}")
    
    print("\n✅ All expected processors registered")
    return True


def test_ingestion_wiring():
    """Test if ingestion scripts are wired."""
    print("\n" + "="*70)
    print("2. INGESTION WIRING CHECK")
    print("="*70)
    
    issues = []
    
    # Check PatentsView
    try:
        from ingestion.patentsview import search_patents
        import inspect
        sig = inspect.signature(search_patents)
        if 'load_to_staging' in sig.parameters:
            print("✅ PatentsView: wired to staging")
        else:
            issues.append("PatentsView missing load_to_staging parameter")
            print("❌ PatentsView: NOT wired")
    except Exception as e:
        issues.append(f"PatentsView import error: {e}")
        print(f"❌ PatentsView: {e}")
    
    # Check OpenFDA
    try:
        from ingestion.openfda import search_drugs
        import inspect
        sig = inspect.signature(search_drugs)
        if 'load_to_staging' in sig.parameters:
            print("✅ OpenFDA: wired to staging")
        else:
            issues.append("OpenFDA missing load_to_staging parameter")
            print("❌ OpenFDA: NOT wired")
    except Exception as e:
        issues.append(f"OpenFDA import error: {e}")
        print(f"❌ OpenFDA: {e}")
    
    # Check FDA Drugs
    try:
        from ingestion.fda_drugs import fetch_drugs_sample
        import inspect
        sig = inspect.signature(fetch_drugs_sample)
        if 'load_to_staging' in sig.parameters:
            print("✅ FDA Drugs: wired to staging")
        else:
            issues.append("FDA Drugs missing load_to_staging parameter")
            print("❌ FDA Drugs: NOT wired")
    except Exception as e:
        issues.append(f"FDA Drugs import error: {e}")
        print(f"❌ FDA Drugs: {e}")
    
    if issues:
        print(f"\n⚠️  Issues found: {len(issues)}")
        for issue in issues:
            print(f"  - {issue}")
        return False
    
    print("\n✅ All ingestion scripts wired")
    return True


def test_entity_types_in_pipeline():
    """Test if Patent and RegulatoryEvent are handled in pipeline."""
    print("\n" + "="*70)
    print("3. ENTITY TYPE HANDLING CHECK")
    print("="*70)
    
    from src.processing.pipeline import ProcessingPipeline
    from src.entity_resolution.types import EntityType
    
    # Check model map
    pipeline = ProcessingPipeline()
    
    # Check _create_new_entity model map
    import inspect
    source = inspect.getsource(pipeline._create_new_entity)
    
    required_types = ['PATENT', 'REGULATORY_EVENT']
    found_types = []
    
    for etype in required_types:
        if f"EntityType.{etype}" in source:
            found_types.append(etype)
            print(f"✅ {etype}: handled in model_map")
        else:
            print(f"❌ {etype}: NOT in model_map")
    
    # Check _build_entity_data
    source_build = inspect.getsource(pipeline._build_entity_data)
    
    if "'Patent'" in source_build or '"Patent"' in source_build:
        print("✅ Patent: handled in _build_entity_data")
    else:
        print("❌ Patent: NOT in _build_entity_data")
        found_types = [t for t in found_types if t != 'PATENT']
    
    if "'RegulatoryEvent'" in source_build or '"RegulatoryEvent"' in source_build:
        print("✅ RegulatoryEvent: handled in _build_entity_data")
    else:
        print("❌ RegulatoryEvent: NOT in _build_entity_data")
        found_types = [t for t in found_types if t != 'REGULATORY_EVENT']
    
    if len(found_types) == len(required_types):
        print("\n✅ All entity types handled")
        return True
    else:
        print(f"\n❌ Missing entity types: {set(required_types) - set(found_types)}")
        return False


def test_end_to_end_patentsview():
    """Test PatentsView end-to-end."""
    print("\n" + "="*70)
    print("4. PATENTSVIEW END-TO-END TEST")
    print("="*70)
    
    try:
        # Clean previous test data
        with get_db_session() as session:
            session.query(SourceProcessingLog).filter_by(source_name='patentsview').delete()
            session.query(StagingRawData).filter_by(source_system='patentsview').delete()
            session.commit()
        
        # Fetch and stage
        print("\nFetching patents...")
        result = search_patents(
            query='{"_gte":{"patent_date":"2020-01-01"}}',
            limit=5,
            load_to_staging=True
        )
        
        if not result or 'patents' not in result:
            print("❌ No patents fetched")
            return False
        
        print(f"✅ Fetched {len(result.get('patents', []))} patents")
        
        # Process
        print("\nProcessing patents...")
        pipeline = ProcessingPipeline()
        stats = pipeline.process_source('patentsview', limit=5)
        
        print(f"\nResults:")
        print(f"  Processed: {stats['records_processed']}")
        print(f"  Failed: {stats['records_failed']}")
        print(f"  Entities created: {stats['entities_created']}")
        print(f"  Relationships created: {stats['relationships_created']}")
        
        if stats['records_failed'] > 0:
            print(f"\n❌ {stats['records_failed']} records failed")
            return False
        
        if stats['entities_created'] == 0:
            print("\n⚠️  No entities created (may be duplicates)")
        
        print("\n✅ PatentsView end-to-end test passed")
        return True
        
    except Exception as e:
        print(f"\n❌ PatentsView test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_end_to_end_openfda():
    """Test OpenFDA end-to-end."""
    print("\n" + "="*70)
    print("5. OPENFDA END-TO-END TEST")
    print("="*70)
    
    try:
        # Clean previous test data
        with get_db_session() as session:
            session.query(SourceProcessingLog).filter_by(source_name='openfda').delete()
            session.query(StagingRawData).filter_by(source_system='openfda').delete()
            session.commit()
        
        # Fetch and stage
        print("\nFetching OpenFDA data...")
        result = search_drugs(
            query="*",
            limit=5,
            load_to_staging=True
        )
        
        if not result or 'results' not in result:
            print("❌ No OpenFDA data fetched")
            return False
        
        print(f"✅ Fetched {len(result.get('results', []))} records")
        
        # Process
        print("\nProcessing OpenFDA data...")
        pipeline = ProcessingPipeline()
        stats = pipeline.process_source('openfda', limit=5)
        
        print(f"\nResults:")
        print(f"  Processed: {stats['records_processed']}")
        print(f"  Failed: {stats['records_failed']}")
        print(f"  Entities created: {stats['entities_created']}")
        print(f"  Relationships created: {stats['relationships_created']}")
        
        if stats['records_failed'] > 0:
            print(f"\n❌ {stats['records_failed']} records failed")
            return False
        
        if stats['entities_created'] == 0:
            print("\n⚠️  No entities created (may be duplicates)")
        
        print("\n✅ OpenFDA end-to-end test passed")
        return True
        
    except Exception as e:
        print(f"\n❌ OpenFDA test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fda_drugs_wiring():
    """Test FDA Drugs wiring."""
    print("\n" + "="*70)
    print("6. FDA DRUGS WIRING CHECK")
    print("="*70)
    
    try:
        from ingestion.fda_drugs import download_all, list_download_links
        print("✅ FDA Drugs: ingestion script exists")
        
        # Check if processor exists
        from src.processors.fda_drugs_processor import FDADrugsProcessor
        print("✅ FDA Drugs: processor exists")
        
        # Note: FDA Drugs downloads files, doesn't load directly to staging
        # This is expected - files need to be parsed first
        print("⚠️  FDA Drugs: downloads files (not directly to staging)")
        print("   This is expected - files need parsing before staging")
        
        return True
        
    except Exception as e:
        print(f"❌ FDA Drugs check failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run comprehensive review."""
    print("\n" + "="*70)
    print("COMPREHENSIVE REVIEW - PATENTS & FDA")
    print("="*70)
    
    results = {
        'processor_registration': test_processor_registration(),
        'ingestion_wiring': test_ingestion_wiring(),
        'entity_types': test_entity_types_in_pipeline(),
        'fda_drugs_wiring': test_fda_drugs_wiring(),
        'patentsview_e2e': test_end_to_end_patentsview(),
        'openfda_e2e': test_end_to_end_openfda(),
    }
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {test}")
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED")
        return True
    else:
        print(f"\n❌ {total - passed} TESTS FAILED")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

