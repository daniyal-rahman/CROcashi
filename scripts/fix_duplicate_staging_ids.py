"""
Fix duplicate source_record_ids in staging table.

Some sources have duplicate IDs from old ingestion runs with bad ID extractors.
This script helps identify and optionally clean them up.
"""
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from sqlalchemy import func, distinct, and_

logger = logging.getLogger(__name__)


def find_duplicate_ids(source_name: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    Find sources with duplicate source_record_ids.
    
    Args:
        source_name: Optional specific source to check (None = all sources)
    
    Returns:
        Dictionary mapping source names to list of duplicate ID info
    """
    duplicates = {}
    
    with get_db_session() as session:
        # Get all sources or specific source
        if source_name:
            sources = [source_name]
        else:
            sources_query = session.query(distinct(StagingRawData.source_system)).filter(
                StagingRawData.deleted_at.is_(None)
            ).all()
            sources = [s[0] for s in sources_query]
        
        for source in sources:
            # Find duplicate IDs
            dup_query = session.query(
                StagingRawData.source_record_id,
                func.count(StagingRawData.staging_id).label('count')
            ).filter(
                StagingRawData.source_system == source,
                StagingRawData.deleted_at.is_(None)
            ).group_by(StagingRawData.source_record_id).having(
                func.count(StagingRawData.staging_id) > 1
            ).all()
            
            if dup_query:
                dup_list = []
                for dup_id, count in dup_query:
                    # Get oldest and newest records with this ID
                    records = session.query(StagingRawData).filter(
                        StagingRawData.source_system == source,
                        StagingRawData.source_record_id == dup_id,
                        StagingRawData.deleted_at.is_(None)
                    ).order_by(StagingRawData.ingested_at).all()
                    
                    dup_list.append({
                        'source_record_id': dup_id,
                        'count': count,
                        'oldest_ingested': records[0].ingested_at if records else None,
                        'newest_ingested': records[-1].ingested_at if records else None,
                        'all_processed': all(r.processed for r in records),
                        'any_processed': any(r.processed for r in records)
                    })
                
                duplicates[source] = dup_list
    
    return duplicates


def clean_duplicate_ids(
    source_name: str,
    keep: str = 'oldest',
    dry_run: bool = True
) -> Dict[str, int]:
    """
    Clean up duplicate source_record_ids.
    
    Args:
        source_name: Source to clean
        keep: Which record to keep ('oldest', 'newest', 'processed', 'unprocessed')
        dry_run: If True, only report what would be deleted (don't actually delete)
    
    Returns:
        Statistics about what was/would be deleted
    """
    duplicates = find_duplicate_ids(source_name)
    
    if source_name not in duplicates:
        return {'deleted': 0, 'kept': 0, 'message': f'No duplicates found for {source_name}'}
    
    stats = {'deleted': 0, 'kept': 0}
    
    with get_db_session() as session:
        for dup_info in duplicates[source_name]:
            dup_id = dup_info['source_record_id']
            
            # Get all records with this ID
            records = session.query(StagingRawData).filter(
                StagingRawData.source_system == source_name,
                StagingRawData.source_record_id == dup_id,
                StagingRawData.deleted_at.is_(None)
            ).order_by(StagingRawData.ingested_at).all()
            
            if not records:
                continue
            
            # Determine which to keep
            if keep == 'oldest':
                keep_record = records[0]
            elif keep == 'newest':
                keep_record = records[-1]
            elif keep == 'processed':
                keep_record = next((r for r in records if r.processed), records[0])
            elif keep == 'unprocessed':
                keep_record = next((r for r in records if not r.processed), records[0])
            else:
                keep_record = records[0]
            
            # Delete the rest
            for record in records:
                if record.staging_id == keep_record.staging_id:
                    stats['kept'] += 1
                    continue
                
                if not dry_run:
                    # Soft delete
                    record.deleted_at = func.now()
                    session.add(record)
                stats['deleted'] += 1
        
        if not dry_run:
            session.commit()
            logger.info(f"Cleaned {stats['deleted']} duplicate records for {source_name}")
        else:
            logger.info(f"DRY RUN: Would delete {stats['deleted']} duplicate records for {source_name}")
    
    return stats


def print_duplicate_report(duplicates: Dict[str, List[Dict]]):
    """Print a report of duplicate IDs."""
    if not duplicates:
        print("✓ No duplicate source_record_ids found")
        return
    
    print(f"\n{'='*80}")
    print("Duplicate source_record_ids Report")
    print(f"{'='*80}\n")
    
    total_duplicates = 0
    for source, dup_list in duplicates.items():
        source_dups = sum(d['count'] - 1 for d in dup_list)  # -1 because we keep one
        total_duplicates += source_dups
        
        print(f"{source}: {len(dup_list)} duplicate IDs, {source_dups} extra records")
        for dup in dup_list[:5]:  # Show first 5
            print(f"  → '{dup['source_record_id'][:60]}...' ({dup['count']} copies)")
        if len(dup_list) > 5:
            print(f"  ... and {len(dup_list) - 5} more")
        print()
    
    print(f"Total duplicate records: {total_duplicates}")
    print(f"\nTo clean duplicates, run:")
    print(f"  python scripts/fix_duplicate_staging_ids.py --clean --source <source_name>")


if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Find and fix duplicate staging IDs')
    parser.add_argument('--source', type=str, default=None,
                       help='Specific source to check (default: all)')
    parser.add_argument('--clean', action='store_true',
                       help='Clean up duplicates (default: dry run)')
    parser.add_argument('--keep', choices=['oldest', 'newest', 'processed', 'unprocessed'],
                       default='oldest',
                       help='Which record to keep when cleaning (default: oldest)')
    parser.add_argument('--no-dry-run', action='store_true',
                       help='Actually delete (default: dry run)')
    
    args = parser.parse_args()
    
    try:
        duplicates = find_duplicate_ids(source_name=args.source)
        print_duplicate_report(duplicates)
        
        if args.clean:
            if args.source:
                stats = clean_duplicate_ids(
                    source_name=args.source,
                    keep=args.keep,
                    dry_run=not args.no_dry_run
                )
                print(f"\nCleanup stats: {stats}")
            else:
                print("\nError: --clean requires --source to be specified")
                sys.exit(1)
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

