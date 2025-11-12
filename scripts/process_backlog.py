#!/usr/bin/env python3
"""
Process backlog of unprocessed staging records.
Only processes after infrastructure is verified.
"""
import sys
from pathlib import Path
import logging
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from database.config import get_db_session
from database.models.staging import StagingRawData
from src.processing.pipeline import ProcessingPipeline

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def get_unprocessed_sources():
    """Get sources with unprocessed records."""
    with get_db_session() as session:
        sources = session.execute(
            text("""
            SELECT source_system, COUNT(*) as count
            FROM staging_raw_data
            WHERE processed = false
              AND deleted_at IS NULL
            GROUP BY source_system
            ORDER BY count DESC
            """)
        ).fetchall()
        
        return [(row[0], row[1]) for row in sources]


def process_backlog(limit_per_source=None, max_total=None):
    """Process backlog of unprocessed records."""
    logger.info("=" * 80)
    logger.info("PROCESSING BACKLOG")
    logger.info("=" * 80)
    
    # Get unprocessed sources
    unprocessed_sources = get_unprocessed_sources()
    
    if not unprocessed_sources:
        logger.info("No unprocessed records found")
        return
    
    total_unprocessed = sum(count for _, count in unprocessed_sources)
    logger.info(f"Total unprocessed records: {total_unprocessed}")
    logger.info(f"Sources with unprocessed records: {len(unprocessed_sources)}")
    
    pipeline = ProcessingPipeline(batch_size=50)
    
    total_processed = 0
    total_entities = 0
    total_relationships = 0
    
    for source_name, unprocessed_count in unprocessed_sources:
        # Check if processor exists
        if source_name not in pipeline.PROCESSOR_MAP:
            logger.warning(f"{source_name}: No processor found, skipping")
            continue
        
        # Determine limit for this source
        if limit_per_source:
            source_limit = min(limit_per_source, unprocessed_count)
        elif max_total:
            remaining = max_total - total_processed
            source_limit = min(remaining, unprocessed_count)
        else:
            source_limit = unprocessed_count
        
        if source_limit <= 0:
            continue
        
        logger.info(f"\nProcessing {source_name}: {source_limit} records (out of {unprocessed_count} unprocessed)")
        
        try:
            result = pipeline.process_source(source_name, limit=source_limit)
            
            if 'error' in result:
                logger.error(f"{source_name}: Error - {result['error']}")
                continue
            
            records = result.get('records_processed', 0)
            entities = result.get('entities_created', 0) + result.get('entities_matched', 0)
            relationships = result.get('relationships_created', 0)
            
            total_processed += records
            total_entities += entities
            total_relationships += relationships
            
            logger.info(f"{source_name}: Processed {records} records, created {entities} entities, {relationships} relationships")
            
            # Check if we've hit max_total limit
            if max_total and total_processed >= max_total:
                logger.info(f"Reached max_total limit ({max_total})")
                break
                
        except Exception as e:
            logger.error(f"{source_name}: Processing failed - {e}", exc_info=True)
    
    logger.info("\n" + "=" * 80)
    logger.info("BACKLOG PROCESSING SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total records processed: {total_processed}")
    logger.info(f"Total entities created/matched: {total_entities}")
    logger.info(f"Total relationships created: {total_relationships}")
    
    return {
        'records_processed': total_processed,
        'entities_created': total_entities,
        'relationships_created': total_relationships
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Process backlog of unprocessed staging records')
    parser.add_argument('--limit-per-source', type=int, help='Limit per source')
    parser.add_argument('--max-total', type=int, help='Maximum total records to process')
    parser.add_argument('--test', action='store_true', help='Test mode: process only 10 records')
    
    args = parser.parse_args()
    
    if args.test:
        logger.info("TEST MODE: Processing only 10 records")
        result = process_backlog(limit_per_source=10, max_total=10)
    elif args.limit_per_source or args.max_total:
        result = process_backlog(limit_per_source=args.limit_per_source, max_total=args.max_total)
    else:
        # Process all by default
        result = process_backlog()
    
    if result:
        logger.info(f"\n✓ Processing complete")
        sys.exit(0)
    else:
        logger.info(f"\n✗ Processing failed or no records to process")
        sys.exit(1)


if __name__ == '__main__':
    main()

