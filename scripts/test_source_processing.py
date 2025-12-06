"""
Test source processing script.

Tests processing for a specific source to diagnose issues.
"""
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from src.processing.pipeline import ProcessingPipeline


def check_staging_records(source_name: str) -> Dict[str, Any]:
    """Check staging records for a source."""
    with get_db_session() as session:
        records = session.query(StagingRawData).filter(
            StagingRawData.source_system == source_name,
            StagingRawData.deleted_at.is_(None)
        ).all()
        
        processed_count = sum(1 for r in records if r.processed)
        unprocessed_count = len(records) - processed_count
        
        # Sample a record to check structure
        sample_record = None
        if records:
            sample_record = records[0]
        
        return {
            'total_records': len(records),
            'processed': processed_count,
            'unprocessed': unprocessed_count,
            'sample_record_id': str(sample_record.staging_id) if sample_record else None,
            'sample_source_identifier': sample_record.source_record_id if sample_record else None,
            'sample_raw_data_keys': list(sample_record.raw_data.keys()) if sample_record and sample_record.raw_data else None
        }


def check_processing_logs(source_name: str) -> Dict[str, Any]:
    """Check processing logs for a source."""
    with get_db_session() as session:
        logs = session.query(SourceProcessingLog).filter(
            SourceProcessingLog.source_name == source_name,
            SourceProcessingLog.deleted_at.is_(None)
        ).all()
        
        status_counts = {}
        error_examples = []
        
        for log in logs:
            status = log.processing_status
            status_counts[status] = status_counts.get(status, 0) + 1
            
            if log.errors and len(error_examples) < 5:
                error_examples.append({
                    'source_identifier': log.source_identifier,
                    'status': status,
                    'errors': log.errors
                })
        
        return {
            'total_logs': len(logs),
            'status_counts': status_counts,
            'error_examples': error_examples
        }


def test_processing(source_name: str, limit: int = 1) -> Dict[str, Any]:
    """Test processing a source with a small limit."""
    try:
        pipeline = ProcessingPipeline(batch_size=10)
        result = pipeline.process_source(source_name=source_name, limit=limit)
        return result
    except Exception as e:
        return {
            'error': str(e),
            'error_type': type(e).__name__
        }


def diagnose_source(source_name: str) -> Dict[str, Any]:
    """Diagnose issues with a source."""
    print(f"\n{'='*60}")
    print(f"Diagnosing: {source_name}")
    print(f"{'='*60}\n")
    
    # Check staging records
    print("1. Checking staging records...")
    staging_info = check_staging_records(source_name)
    print(f"   Total records: {staging_info['total_records']}")
    print(f"   Processed: {staging_info['processed']}")
    print(f"   Unprocessed: {staging_info['unprocessed']}")
    
    if staging_info['sample_record_id']:
        print(f"   Sample record ID: {staging_info['sample_record_id']}")
        print(f"   Sample source identifier: {staging_info['sample_source_identifier']}")
        if staging_info['sample_raw_data_keys']:
            print(f"   Raw data keys: {', '.join(staging_info['sample_raw_data_keys'][:10])}")
    
    # Check processing logs
    print("\n2. Checking processing logs...")
    log_info = check_processing_logs(source_name)
    print(f"   Total logs: {log_info['total_logs']}")
    if log_info['status_counts']:
        print("   Status breakdown:")
        for status, count in log_info['status_counts'].items():
            print(f"     - {status}: {count}")
    
    if log_info['error_examples']:
        print("\n   Error examples:")
        for example in log_info['error_examples']:
            print(f"     - {example['source_identifier']} ({example['status']}):")
            for error in example['errors'][:2]:  # Show first 2 errors
                print(f"       {error}")
    
    # Test processing
    print("\n3. Testing processing (limit=1)...")
    if staging_info['unprocessed'] > 0:
        test_result = test_processing(source_name, limit=1)
        if 'error' in test_result:
            print(f"   ✗ Processing failed: {test_result['error']}")
            print(f"   Error type: {test_result.get('error_type', 'Unknown')}")
        else:
            print(f"   ✓ Processing completed")
            print(f"   Records processed: {test_result.get('records_processed', 0)}")
            print(f"   Entities created: {test_result.get('entities_created', 0)}")
            print(f"   Relationships created: {test_result.get('relationships_created', 0)}")
    else:
        print("   ⚠ No unprocessed records to test")
    
    return {
        'staging': staging_info,
        'logs': log_info,
        'test_result': test_result if staging_info['unprocessed'] > 0 else None
    }


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test and diagnose source processing')
    parser.add_argument('source_name', help='Source name to diagnose')
    parser.add_argument('--limit', type=int, default=1, help='Limit for test processing')
    args = parser.parse_args()
    
    try:
        result = diagnose_source(args.source_name)
        
        # Summary
        print(f"\n{'='*60}")
        print("Summary")
        print(f"{'='*60}")
        
        if result['staging']['unprocessed'] > 0 and result.get('test_result') and 'error' in result['test_result']:
            print(f"⚠️  Processing issue detected: {result['test_result']['error']}")
            print("\nRecommendations:")
            print("1. Check processor implementation")
            print("2. Verify raw_data structure matches processor expectations")
            print("3. Check for missing required fields")
        elif result['staging']['unprocessed'] == 0:
            print("⚠️  No unprocessed records to test")
        else:
            print("✓ Processing appears to work")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

