"""
Batch processing script for all active sources.

Processes all active sources through the pipeline and generates a report.
"""
import sys
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.sources import Source
from src.processing.pipeline import ProcessingPipeline


def process_all_active_sources(limit_per_source: int = None) -> Dict[str, Any]:
    """
    Process all active sources.
    
    Args:
        limit_per_source: Optional limit on records per source (None = all)
    
    Returns:
        Dictionary with processing statistics
    """
    pipeline = ProcessingPipeline(batch_size=50)
    
    total_stats = {
        'sources_processed': 0,
        'sources_failed': 0,
        'total_records_processed': 0,
        'total_entities_created': 0,
        'total_entities_matched': 0,
        'total_relationships_created': 0,
        'source_results': []
    }
    
    with get_db_session() as session:
        # Get all active sources
        active_sources = session.query(Source).filter(
            Source.is_active == True,
            Source.deleted_at.is_(None)
        ).order_by(Source.source_name).all()
        
        print(f"Found {len(active_sources)} active sources")
        print("="*60)
        
        for source in active_sources:
            print(f"\nProcessing {source.source_name}...")
            try:
                result = pipeline.process_source(
                    source_name=source.source_name,
                    limit=limit_per_source
                )
                
                if 'error' in result:
                    print(f"  ✗ Error: {result['error']}")
                    total_stats['sources_failed'] += 1
                    total_stats['source_results'].append({
                        'source_name': source.source_name,
                        'status': 'failed',
                        'error': result['error']
                    })
                else:
                    print(f"  ✓ Records processed: {result.get('records_processed', 0)}")
                    print(f"  ✓ Entities created: {result.get('entities_created', 0)}")
                    print(f"  ✓ Entities matched: {result.get('entities_matched', 0)}")
                    print(f"  ✓ Relationships created: {result.get('relationships_created', 0)}")
                    
                    total_stats['sources_processed'] += 1
                    total_stats['total_records_processed'] += result.get('records_processed', 0)
                    total_stats['total_entities_created'] += result.get('entities_created', 0)
                    total_stats['total_entities_matched'] += result.get('entities_matched', 0)
                    total_stats['total_relationships_created'] += result.get('relationships_created', 0)
                    
                    total_stats['source_results'].append({
                        'source_name': source.source_name,
                        'status': 'success',
                        'records_processed': result.get('records_processed', 0),
                        'entities_created': result.get('entities_created', 0),
                        'entities_matched': result.get('entities_matched', 0),
                        'relationships_created': result.get('relationships_created', 0)
                    })
                    
            except Exception as e:
                print(f"  ✗ Exception: {e}")
                total_stats['sources_failed'] += 1
                total_stats['source_results'].append({
                    'source_name': source.source_name,
                    'status': 'failed',
                    'error': str(e)
                })
    
    return total_stats


def print_summary(stats: Dict[str, Any]):
    """Print processing summary."""
    print("\n" + "="*60)
    print("Processing Summary")
    print("="*60)
    print(f"Sources processed: {stats['sources_processed']}")
    print(f"Sources failed: {stats['sources_failed']}")
    print(f"Total records processed: {stats['total_records_processed']:,}")
    print(f"Total entities created: {stats['total_entities_created']:,}")
    print(f"Total entities matched: {stats['total_entities_matched']:,}")
    print(f"Total relationships created: {stats['total_relationships_created']:,}")
    print()
    
    if stats['source_results']:
        print("Per-Source Results:")
        print("-" * 60)
        for result in stats['source_results']:
            if result['status'] == 'success':
                print(f"  ✓ {result['source_name']}: "
                      f"{result['records_processed']} records, "
                      f"{result['entities_created']} entities, "
                      f"{result['relationships_created']} relationships")
            else:
                print(f"  ✗ {result['source_name']}: {result.get('error', 'Unknown error')}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Process all active sources')
    parser.add_argument('--limit', type=int, default=None,
                       help='Limit records per source (default: all)')
    args = parser.parse_args()
    
    try:
        stats = process_all_active_sources(limit_per_source=args.limit)
        print_summary(stats)
        
        # Exit with error code if any sources failed
        if stats['sources_failed'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

