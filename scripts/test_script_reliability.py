#!/usr/bin/env python3
"""
Test script reliability before automating.
Tests ingestion and processing scripts on small samples.
"""
import sys
from pathlib import Path
import time
import traceback

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from src.processing.pipeline import ProcessingPipeline


def test_ingestion_script(source_name, limit=10):
    """Test an ingestion script."""
    print(f"\nTesting {source_name} ingestion (limit: {limit})...")
    
    try:
        # Import the ingestion module
        ingestion_module = __import__(f'ingestion.{source_name}', fromlist=[''])
        
        # Try different function name patterns
        ingest_func = None
        func_names = [
            'ingest',
            f'ingest_{source_name}',
            f'fetch_{source_name}',
            'fetch_studies_sample',  # clinicaltrials_gov
            'fetch_sample',  # pubmed
            'fetch_8k_filings_for_biotech_companies',  # sec_edgar
            'ingest_termination_8ks',  # sec_edgar alternative
        ]
        
        for func_name in func_names:
            if hasattr(ingestion_module, func_name):
                ingest_func = getattr(ingestion_module, func_name)
                break
        
        if not ingest_func:
            print(f"  ⚠ No ingestion function found (tried: {', '.join(func_names)})")
            return {'status': 'skipped', 'reason': 'no_ingest_function'}
        
        # Run ingestion
        start_time = time.time()
        # Try calling with limit parameter, or without if it doesn't accept it
        try:
            result = ingest_func(limit=limit)
        except TypeError:
            # Function might not accept limit parameter
            result = ingest_func()
        elapsed = time.time() - start_time
        
        # Check result
        if isinstance(result, dict):
            records_fetched = result.get('parsed', 0) or result.get('count', 0) or 0
            records_inserted = result.get('inserted', 0) or result.get('staging_stats', {}).get('inserted', 0)
            
            print(f"  ✓ Completed in {elapsed:.2f}s")
            print(f"    Records fetched: {records_fetched}")
            print(f"    Records inserted: {records_inserted}")
            
            return {
                'status': 'success',
                'elapsed': elapsed,
                'records_fetched': records_fetched,
                'records_inserted': records_inserted
            }
        else:
            print(f"  ⚠ Unexpected result type: {type(result)}")
            return {'status': 'warning', 'reason': 'unexpected_result_type'}
            
    except ImportError as e:
        print(f"  ✗ Import error: {e}")
        return {'status': 'error', 'error': str(e)}
    except Exception as e:
        print(f"  ✗ Error: {e}")
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def test_processing_pipeline(source_name, limit=10):
    """Test processing pipeline."""
    print(f"\nTesting {source_name} processing (limit: {limit})...")
    
    try:
        pipeline = ProcessingPipeline(batch_size=10)
        
        # Check if processor exists
        if source_name not in pipeline.PROCESSOR_MAP:
            print(f"  ⚠ No processor found for {source_name}")
            return {'status': 'skipped', 'reason': 'no_processor'}
        
        # Count unprocessed records
        with get_db_session() as session:
            unprocessed = session.query(StagingRawData).filter(
                StagingRawData.source_system == source_name,
                StagingRawData.processed == False,
                StagingRawData.deleted_at.is_(None)
            ).count()
            
            if unprocessed == 0:
                print(f"  ⚠ No unprocessed records found")
                return {'status': 'skipped', 'reason': 'no_unprocessed_records'}
        
        # Run processing
        start_time = time.time()
        result = pipeline.process_source(source_name, limit=limit)
        elapsed = time.time() - start_time
        
        # Check result
        if 'error' in result:
            print(f"  ✗ Error: {result['error']}")
            return {'status': 'error', 'error': result['error']}
        
        records_processed = result.get('records_processed', 0)
        entities_created = result.get('entities_created', 0)
        relationships_created = result.get('relationships_created', 0)
        
        print(f"  ✓ Completed in {elapsed:.2f}s")
        print(f"    Records processed: {records_processed}")
        print(f"    Entities created: {entities_created}")
        print(f"    Relationships created: {relationships_created}")
        
        return {
            'status': 'success',
            'elapsed': elapsed,
            'records_processed': records_processed,
            'entities_created': entities_created,
            'relationships_created': relationships_created
        }
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def measure_resource_usage():
    """Measure resource usage (basic)."""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    
    memory_mb = process.memory_info().rss / 1024 / 1024
    cpu_percent = process.cpu_percent(interval=1)
    
    return {
        'memory_mb': memory_mb,
        'cpu_percent': cpu_percent
    }


def main():
    print("=" * 80)
    print("SCRIPT RELIABILITY TESTING")
    print("=" * 80)
    
    # Test sources
    test_sources = [
        'clinicaltrials_gov',
        'sec_edgar',
        'pubmed',
        'fda_drugs'
    ]
    
    results = {
        'ingestion': {},
        'processing': {}
    }
    
    # Test ingestion scripts
    print("\n[1] TESTING INGESTION SCRIPTS")
    print("-" * 80)
    
    for source in test_sources:
        result = test_ingestion_script(source, limit=10)
        results['ingestion'][source] = result
    
    # Test processing pipeline
    print("\n[2] TESTING PROCESSING PIPELINE")
    print("-" * 80)
    
    for source in test_sources:
        result = test_processing_pipeline(source, limit=10)
        results['processing'][source] = result
    
    # Measure resource usage
    print("\n[3] RESOURCE USAGE")
    print("-" * 80)
    
    try:
        resources = measure_resource_usage()
        print(f"  Memory: {resources['memory_mb']:.1f} MB")
        print(f"  CPU: {resources['cpu_percent']:.1f}%")
    except Exception as e:
        print(f"  ⚠ Could not measure resources: {e}")
    
    # Summary
    print("\n[4] SUMMARY")
    print("-" * 80)
    
    ingestion_success = sum(1 for r in results['ingestion'].values() if r.get('status') == 'success')
    processing_success = sum(1 for r in results['processing'].values() if r.get('status') == 'success')
    
    print(f"\nIngestion tests:")
    print(f"  Successful: {ingestion_success}/{len(test_sources)}")
    for source, result in results['ingestion'].items():
        status = result.get('status', 'unknown')
        print(f"    {source}: {status}")
    
    print(f"\nProcessing tests:")
    print(f"  Successful: {processing_success}/{len(test_sources)}")
    for source, result in results['processing'].items():
        status = result.get('status', 'unknown')
        print(f"    {source}: {status}")
    
    # Overall assessment
    print(f"\nOverall assessment:")
    if ingestion_success == len(test_sources) and processing_success == len(test_sources):
        print(f"  ✅ All tests passed - scripts are reliable")
    elif ingestion_success + processing_success >= len(test_sources):
        print(f"  ⚠ Some tests passed - review failures before automating")
    else:
        print(f"  ❌ Multiple failures - fix issues before automating")


if __name__ == '__main__':
    main()

