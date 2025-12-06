#!/usr/bin/env python3
"""
Data ingestion script for generating match candidates.

Ingests data from priority sources to generate match candidates for review.
Tracks ingestion metrics and supports configurable source selection.
"""
import sys
from pathlib import Path
import logging
from datetime import datetime
from typing import List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.resolution import EntityMatchCandidate
from src.processing.pipeline import ProcessingPipeline

# Set up logging
log_dir = project_root / 'data' / 'ingestion_logs'
log_dir.mkdir(parents=True, exist_ok=True)

log_file = log_dir / f'ingestion_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def ingest_clinicaltrials_gov(page_size: int = 500, days_back: Optional[int] = None) -> int:
    """Ingest ClinicalTrials.gov data."""
    try:
        from ingestion.clinicaltrials_gov import fetch_studies_sample
        
        logger.info(f"Ingesting ClinicalTrials.gov (page_size: {page_size}, days_back: {days_back})...")
        result = fetch_studies_sample(
            query_term="cancer",
            page_size=page_size,
            load_to_staging=True,
            days_back=days_back
        )
        
        studies = result.get('studies', []) if isinstance(result, dict) else []
        logger.info(f"ClinicalTrials.gov: Fetched {len(studies)} studies")
        return len(studies)
    except Exception as e:
        logger.error(f"Error ingesting ClinicalTrials.gov: {e}", exc_info=True)
        return 0


def ingest_pubmed(retmax: int = 300, days_back: Optional[int] = None) -> int:
    """Ingest PubMed data."""
    try:
        from ingestion.pubmed import fetch_sample
        
        logger.info(f"Ingesting PubMed (retmax: {retmax}, days_back: {days_back})...")
        result = fetch_sample(
            term="clinical trial AND cancer",
            retmax=retmax,
            load_to_staging=True,
            days_back=days_back
        )
        
        summary = result.get('summary', {}) if isinstance(result, dict) else {}
        records = summary.get('result', {})
        count = len([k for k in records.keys() if k != 'uids'])
        logger.info(f"PubMed: Fetched {count} publications")
        return count
    except Exception as e:
        logger.error(f"Error ingesting PubMed: {e}", exc_info=True)
        return 0


def ingest_fda_drugs() -> int:
    """Ingest FDA Drugs@FDA data."""
    try:
        from ingestion.fda_drugs import ingest_fda_drugs
        
        logger.info("Ingesting FDA Drugs@FDA...")
        result = ingest_fda_drugs(load_to_staging=True)
        
        inserted = result.get('inserted', 0) if isinstance(result, dict) else 0
        logger.info(f"FDA Drugs@FDA: Inserted {inserted} records")
        return inserted
    except Exception as e:
        logger.error(f"Error ingesting FDA Drugs@FDA: {e}", exc_info=True)
        return 0


def ingest_fda_breakthrough() -> int:
    """Ingest FDA Breakthrough Therapy Designations."""
    try:
        from ingestion.fda_breakthrough import scrape_designations
        
        logger.info("Ingesting FDA Breakthrough...")
        result = scrape_designations(load_to_staging=True)
        
        inserted = result.get('staging_stats', {}).get('inserted', 0) if isinstance(result, dict) else 0
        logger.info(f"FDA Breakthrough: Inserted {inserted} records")
        return inserted
    except Exception as e:
        logger.error(f"Error ingesting FDA Breakthrough: {e}", exc_info=True)
        return 0


def ingest_fda_orphan() -> int:
    """Ingest FDA Orphan Drug Designations."""
    try:
        from ingestion.fda_orphan import fetch_orphan_designations
        
        logger.info("Ingesting FDA Orphan...")
        result = fetch_orphan_designations(load_to_staging=True)
        
        inserted = result.get('staging_stats', {}).get('inserted', 0) if isinstance(result, dict) else 0
        logger.info(f"FDA Orphan: Inserted {inserted} records")
        return inserted
    except Exception as e:
        logger.error(f"Error ingesting FDA Orphan: {e}", exc_info=True)
        return 0


def process_sources(sources: List[str], batch_size: int = 50, limit_per_source: Optional[int] = None) -> dict:
    """Process staging records to generate match candidates."""
    logger.info("=" * 80)
    logger.info("PROCESSING STAGING RECORDS TO GENERATE MATCH CANDIDATES")
    logger.info("=" * 80)
    
    pipeline = ProcessingPipeline(batch_size=batch_size)
    
    stats = {
        'sources_processed': 0,
        'records_processed': 0,
        'entities_created': 0,
        'entities_matched': 0,
        'candidates_created': 0,
        'errors': []
    }
    
    for source in sources:
        if source not in pipeline.PROCESSOR_MAP:
            logger.warning(f"{source}: No processor found, skipping")
            continue
        
        # Check for unprocessed records
        with get_db_session() as session:
            unprocessed = session.query(StagingRawData).filter(
                StagingRawData.source_system == source,
                StagingRawData.processed == False,
                StagingRawData.deleted_at.is_(None)
            ).count()
            
            if unprocessed == 0:
                logger.info(f"{source}: No unprocessed records")
                continue
        
        # Process source
        try:
            logger.info(f"Processing {source}...")
            result = pipeline.process_source(source, limit=limit_per_source)
            
            if 'error' in result:
                logger.error(f"{source}: Processing error - {result['error']}")
                stats['errors'].append({'source': source, 'error': result['error']})
                continue
            
            # Count new candidates created
            with get_db_session() as session:
                # Count candidates created today
                today = datetime.now().date()
                new_candidates = session.query(EntityMatchCandidate).filter(
                    EntityMatchCandidate.status == 'needs_review',
                    EntityMatchCandidate.created_at >= today
                ).count()
            
            stats['sources_processed'] += 1
            stats['records_processed'] += result.get('records_processed', 0)
            stats['entities_created'] += result.get('entities_created', 0)
            stats['entities_matched'] += result.get('entities_matched', 0)
            stats['candidates_created'] += new_candidates
            
            logger.info(
                f"{source}: Processed {result.get('records_processed', 0)} records, "
                f"created {result.get('entities_created', 0)} entities, "
                f"matched {result.get('entities_matched', 0)} entities, "
                f"created ~{new_candidates} new candidates"
            )
                
        except Exception as e:
            logger.error(f"{source}: Processing failed - {e}", exc_info=True)
            stats['errors'].append({'source': source, 'error': str(e)})
    
    # Final count
    with get_db_session() as session:
        total_pending = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.status == 'needs_review',
            EntityMatchCandidate.deleted_at.is_(None)
        ).count()
    
    stats['total_candidates_pending'] = total_pending
    
    logger.info(f"\nTotal candidates now pending review: {total_pending}")
    return stats


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Ingest data from sources to generate match candidates"
    )
    parser.add_argument(
        '--sources',
        type=str,
        default='clinicaltrials_gov,pubmed,fda_drugs',
        help='Comma-separated list of sources to ingest (default: clinicaltrials_gov,pubmed,fda_drugs)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=1000,
        help='Limit per source for ingestion (default: 1000)'
    )
    parser.add_argument(
        '--days-back',
        type=int,
        help='Only ingest records from last N days'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Batch size for processing (default: 50)'
    )
    parser.add_argument(
        '--process-limit',
        type=int,
        help='Limit records to process per source (default: all unprocessed)'
    )
    parser.add_argument(
        '--skip-ingestion',
        action='store_true',
        help='Skip ingestion, only process existing staging records'
    )
    parser.add_argument(
        '--skip-processing',
        action='store_true',
        help='Skip processing, only ingest data'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("DATA INGESTION FOR REVIEW")
    print("=" * 80)
    print(f"Started at: {datetime.now()}")
    print(f"Sources: {args.sources}")
    print(f"Ingestion limit: {args.limit}")
    if args.days_back:
        print(f"Days back: {args.days_back}")
    print()
    
    source_list = [s.strip() for s in args.sources.split(',')]
    
    # Step 1: Ingest data
    ingestion_stats = {}
    if not args.skip_ingestion:
        logger.info("Step 1: Ingesting data...")
        
        if 'clinicaltrials_gov' in source_list:
            ingestion_stats['clinicaltrials_gov'] = ingest_clinicaltrials_gov(
                page_size=args.limit,
                days_back=args.days_back
            )
        
        if 'pubmed' in source_list:
            ingestion_stats['pubmed'] = ingest_pubmed(
                retmax=args.limit,
                days_back=args.days_back
            )
        
        if 'fda_drugs' in source_list:
            ingestion_stats['fda_drugs'] = ingest_fda_drugs()
        
        if 'fda_breakthrough' in source_list:
            ingestion_stats['fda_breakthrough'] = ingest_fda_breakthrough()
        
        if 'fda_orphan' in source_list:
            ingestion_stats['fda_orphan'] = ingest_fda_orphan()
        
        logger.info("Ingestion complete\n")
        logger.info("Ingestion Summary:")
        for source, count in ingestion_stats.items():
            logger.info(f"  {source}: {count} records")
    else:
        logger.info("Skipping ingestion (using existing staging records)")
    
    # Step 2: Process to generate candidates
    if not args.skip_processing:
        logger.info("Step 2: Processing staging records...")
        processing_stats = process_sources(
            sources=source_list,
            batch_size=args.batch_size,
            limit_per_source=args.process_limit
        )
        
        logger.info("\nProcessing Summary:")
        logger.info(f"  Sources processed: {processing_stats['sources_processed']}")
        logger.info(f"  Records processed: {processing_stats['records_processed']}")
        logger.info(f"  Entities created: {processing_stats['entities_created']}")
        logger.info(f"  Entities matched: {processing_stats['entities_matched']}")
        logger.info(f"  Candidates created: {processing_stats['candidates_created']}")
        logger.info(f"  Total candidates pending: {processing_stats['total_candidates_pending']}")
        
        if processing_stats['errors']:
            logger.warning(f"  Errors: {len(processing_stats['errors'])}")
            for error in processing_stats['errors']:
                logger.warning(f"    {error['source']}: {error['error']}")
    else:
        logger.info("Skipping processing")
    
    print("\n" + "=" * 80)
    print("INGESTION COMPLETE")
    print("=" * 80)
    print(f"Completed at: {datetime.now()}")
    print(f"Log file: {log_file}")


if __name__ == '__main__':
    main()





