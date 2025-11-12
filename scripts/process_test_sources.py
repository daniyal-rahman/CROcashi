"""
Process test sources through the pipeline with reprocessing options.

Handles different reprocessing strategies for testing scenarios.
"""
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from src.processing.pipeline import ProcessingPipeline
from sqlalchemy import and_, or_

logger = logging.getLogger(__name__)

# List of all test sources
TEST_SOURCES = [
    'clinicaltrials_gov',
    'fda_drugs',
    'fda_clinical_hold',
    'fda_breakthrough',
    'fda_orphan',
    'fda_orange_book',
    'fda_purple_book',
    'fda_warning_letters',
    'fda_guidance',
    'fda_eua',
    'fda_expanded_access',
    'fda_faers',
    'california_warn',
    'federal_warn',
    'biospace_layoff_tracker',
    'fierce_layoff_tracker',
    'ema_epar',
    'ema_prime',
    'ema_trials',
    'ema_guidelines',
    'who_ictrp',
    'who_outbreak_news',
    'uspto_public_pair',
    'health_canada',
    'mhra_uk',
    'tga_australia',
    'nih_reporter',
    'nsf_awards',
    'vaers',
    'ich_guidelines',
    'anvisa_brazil',
    'cdsco_india',
    'mfds_korea',
    'hsa_singapore',
]


def process_test_sources(
    sources: Optional[List[str]] = None,
    reprocess_strategy: str = 'new_only',
    test_run_id: Optional[str] = None,
    limit_per_source: Optional[int] = None
) -> Dict[str, Any]:
    """
    Process test sources through the pipeline.
    
    Args:
        sources: List of source names to process (default: all test sources)
        reprocess_strategy: One of:
            - 'new_only': Only process processed=False records (default)
            - 'reprocess_all': Reset processed=False, clear logs, reprocess everything
            - 'reprocess_failed': Only reprocess records with processing_status='failed'
            - 'reprocess_since <date>': Reprocess records ingested after date (not implemented)
        test_run_id: Optional test run ID for tracking
        limit_per_source: Optional limit on records per source
    
    Returns:
        Dictionary with processing statistics
    """
    if sources is None:
        sources = TEST_SOURCES
    
    if test_run_id is None:
        test_run_id = str(uuid4())
    
    logger.info(f"Processing test sources (test_run_id={test_run_id}, strategy={reprocess_strategy}, sources={len(sources)})")
    
    # Apply reprocessing strategy
    if reprocess_strategy == 'reprocess_all':
        logger.info("Resetting processed flags and clearing processing logs...")
        with get_db_session() as session:
            # Reset processed flag
            staging_reset = session.query(StagingRawData).filter(
                and_(
                    StagingRawData.source_system.in_(sources),
                    StagingRawData.processed == True,
                    StagingRawData.deleted_at.is_(None)
                )
            ).update({
                'processed': False,
                'processed_at': None
            }, synchronize_session=False)
            
            # Clear processing logs
            logs_cleared = session.query(SourceProcessingLog).filter(
                and_(
                    SourceProcessingLog.source_name.in_(sources),
                    SourceProcessingLog.deleted_at.is_(None)
                )
            ).delete(synchronize_session=False)
            
            session.commit()
            logger.info(f"Reset {staging_reset} staging records, cleared {logs_cleared} processing logs")
    
    elif reprocess_strategy == 'reprocess_failed':
        logger.info("Resetting failed records for reprocessing...")
        with get_db_session() as session:
            # Find failed processing logs
            failed_logs = session.query(SourceProcessingLog).filter(
                and_(
                    SourceProcessingLog.source_name.in_(sources),
                    SourceProcessingLog.processing_status == 'failed',
                    SourceProcessingLog.deleted_at.is_(None)
                )
            ).all()
            
            # Reset staging records for failed processing
            failed_identifiers = [log.source_identifier for log in failed_logs]
            if failed_identifiers:
                staging_reset = session.query(StagingRawData).filter(
                    and_(
                        StagingRawData.source_system.in_(sources),
                        StagingRawData.source_record_id.in_(failed_identifiers),
                        StagingRawData.deleted_at.is_(None)
                    )
                ).update({
                    'processed': False,
                    'processed_at': None
                }, synchronize_session=False)
                
                session.commit()
                logger.info(f"Reset {staging_reset} failed staging records for reprocessing")
    
    # Process sources
    pipeline = ProcessingPipeline(batch_size=50)
    
    start_time = datetime.now()
    total_stats = {
        'test_run_id': test_run_id,
        'reprocess_strategy': reprocess_strategy,
        'start_time': start_time,
        'sources_processed': 0,
        'sources_failed': 0,
        'total_records_processed': 0,
        'total_records_failed': 0,
        'total_entities_created': 0,
        'total_entities_matched': 0,
        'total_relationships_created': 0,
        'total_needs_review': 0,
        'source_results': []
    }
    
    for source_name in sources:
        logger.info(f"Processing {source_name}...")
        try:
            result = pipeline.process_source(
                source_name=source_name,
                limit=limit_per_source
            )
            
            if 'error' in result:
                logger.error(f"  ✗ {source_name}: {result['error']}")
                total_stats['sources_failed'] += 1
                total_stats['source_results'].append({
                    'source_name': source_name,
                    'status': 'failed',
                    'error': result['error']
                })
            else:
                logger.info(f"  ✓ {source_name}: {result.get('records_processed', 0)} records, "
                          f"{result.get('entities_created', 0)} entities, "
                          f"{result.get('relationships_created', 0)} relationships")
                
                total_stats['sources_processed'] += 1
                total_stats['total_records_processed'] += result.get('records_processed', 0)
                total_stats['total_records_failed'] += result.get('records_failed', 0)
                total_stats['total_entities_created'] += result.get('entities_created', 0)
                total_stats['total_entities_matched'] += result.get('entities_matched', 0)
                total_stats['total_relationships_created'] += result.get('relationships_created', 0)
                total_stats['total_needs_review'] += result.get('needs_review', 0)
                
                total_stats['source_results'].append({
                    'source_name': source_name,
                    'status': 'success',
                    'records_processed': result.get('records_processed', 0),
                    'records_failed': result.get('records_failed', 0),
                    'entities_created': result.get('entities_created', 0),
                    'entities_matched': result.get('entities_matched', 0),
                    'relationships_created': result.get('relationships_created', 0),
                    'needs_review': result.get('needs_review', 0)
                })
                
        except Exception as e:
            logger.error(f"  ✗ {source_name}: Exception - {e}", exc_info=True)
            total_stats['sources_failed'] += 1
            total_stats['source_results'].append({
                'source_name': source_name,
                'status': 'failed',
                'error': str(e)
            })
    
    total_stats['end_time'] = datetime.now()
    total_stats['duration_seconds'] = (total_stats['end_time'] - total_stats['start_time']).total_seconds()
    
    logger.info(f"Processing complete: {total_stats['sources_processed']} successful, {total_stats['sources_failed']} failed")
    
    return total_stats


def print_processing_summary(stats: Dict[str, Any]):
    """Print processing summary."""
    print(f"\n{'='*60}")
    print(f"Processing Summary")
    print(f"{'='*60}")
    print(f"Test Run ID: {stats['test_run_id']}")
    print(f"Reprocessing Strategy: {stats['reprocess_strategy']}")
    print(f"Duration: {stats['duration_seconds']:.1f} seconds")
    print(f"\nSources: {stats['sources_processed']} successful, {stats['sources_failed']} failed")
    print(f"Records: {stats['total_records_processed']:,} processed, {stats['total_records_failed']:,} failed")
    print(f"Entities: {stats['total_entities_created']:,} created, {stats['total_entities_matched']:,} matched")
    print(f"Relationships: {stats['total_relationships_created']:,} created")
    print(f"Needs Review: {stats['total_needs_review']:,}")
    
    if stats['source_results']:
        print(f"\nPer-Source Results:")
        print(f"{'-'*60}")
        for result in stats['source_results']:
            if result['status'] == 'success':
                print(f"  ✓ {result['source_name']}: "
                      f"{result.get('records_processed', 0)} records, "
                      f"{result.get('entities_created', 0)} entities, "
                      f"{result.get('relationships_created', 0)} relationships")
            else:
                print(f"  ✗ {result['source_name']}: {result.get('error', 'Unknown error')}")


if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Process test sources')
    parser.add_argument('--sources', nargs='+', default=None,
                       help='Specific sources to process (default: all test sources)')
    parser.add_argument('--reprocess-strategy', 
                       choices=['new_only', 'reprocess_all', 'reprocess_failed'],
                       default='new_only',
                       help='Reprocessing strategy')
    parser.add_argument('--test-run-id', type=str, default=None,
                       help='Test run ID for tracking')
    parser.add_argument('--limit', type=int, default=None,
                       help='Limit records per source (default: all)')
    
    args = parser.parse_args()
    
    try:
        stats = process_test_sources(
            sources=args.sources,
            reprocess_strategy=args.reprocess_strategy,
            test_run_id=args.test_run_id,
            limit_per_source=args.limit
        )
        print_processing_summary(stats)
        
        # Exit with error code if any sources failed
        if stats['sources_failed'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Error processing test sources: {e}", exc_info=True)
        sys.exit(1)

