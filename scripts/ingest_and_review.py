#!/usr/bin/env python3
"""
Ingest data, process it to generate match candidates, then review them.

This script:
1. Ingests data from multiple sources
2. Processes staging records to create match candidates
3. Reviews at least the specified number of candidates
"""
import sys
from pathlib import Path
import logging
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.resolution import EntityMatchCandidate
from src.processing.pipeline import ProcessingPipeline

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def ingest_clinicaltrials_gov(page_size=500):
    """Ingest ClinicalTrials.gov data."""
    try:
        from ingestion.clinicaltrials_gov import fetch_studies_sample
        
        logger.info(f"Ingesting ClinicalTrials.gov (page_size: {page_size})...")
        result = fetch_studies_sample(query_term="cancer", page_size=page_size, load_to_staging=True)
        
        # Count studies in result
        studies = result.get('studies', []) if isinstance(result, dict) else []
        logger.info(f"ClinicalTrials.gov: Fetched {len(studies)} studies")
        return len(studies)
    except Exception as e:
        logger.error(f"Error ingesting ClinicalTrials.gov: {e}")
        return 0


def ingest_pubmed(retmax=300):
    """Ingest PubMed data."""
    try:
        from ingestion.pubmed import fetch_sample
        
        logger.info(f"Ingesting PubMed (retmax: {retmax})...")
        result = fetch_sample(term="clinical trial AND cancer", retmax=retmax, load_to_staging=True)
        
        # Count records from summary
        summary = result.get('summary', {}) if isinstance(result, dict) else {}
        records = summary.get('result', {})
        count = len([k for k in records.keys() if k != 'uids'])
        logger.info(f"PubMed: Fetched {count} publications")
        return count
    except Exception as e:
        logger.error(f"Error ingesting PubMed: {e}")
        return 0


def ingest_fda_sources():
    """Ingest FDA sources."""
    total = 0
    
    # FDA Breakthrough
    try:
        from ingestion.fda_breakthrough import scrape_designations
        logger.info("Ingesting FDA Breakthrough...")
        result = scrape_designations(load_to_staging=True)
        inserted = result.get('staging_stats', {}).get('inserted', 0) if isinstance(result, dict) else 0
        logger.info(f"FDA Breakthrough: Inserted {inserted} records")
        total += inserted
    except Exception as e:
        logger.error(f"Error ingesting FDA Breakthrough: {e}")
    
    # FDA Orphan
    try:
        from ingestion.fda_orphan import fetch_orphan_designations
        logger.info("Ingesting FDA Orphan...")
        result = fetch_orphan_designations(load_to_staging=True)
        inserted = result.get('staging_stats', {}).get('inserted', 0) if isinstance(result, dict) else 0
        logger.info(f"FDA Orphan: Inserted {inserted} records")
        total += inserted
    except Exception as e:
        logger.error(f"Error ingesting FDA Orphan: {e}")
    
    return total


def process_sources_to_generate_candidates(min_candidates=100):
    """Process sources to generate match candidates."""
    logger.info("=" * 80)
    logger.info("PROCESSING SOURCES TO GENERATE MATCH CANDIDATES")
    logger.info("=" * 80)
    
    pipeline = ProcessingPipeline(batch_size=50)
    
    sources = [
        'clinicaltrials_gov',
        'pubmed',
        'fda_breakthrough',
        'fda_orphan',
        'fda_eua',
        'fda_guidance',
    ]
    
    total_candidates = 0
    
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
            result = pipeline.process_source(source, limit=200)
            
            if 'error' in result:
                logger.error(f"{source}: Processing error - {result['error']}")
                continue
            
            # Count new candidates created
            with get_db_session() as session:
                new_candidates = session.query(EntityMatchCandidate).filter(
                    EntityMatchCandidate.status == 'needs_review',
                    EntityMatchCandidate.created_at >= datetime.now().date()
                ).count()
            
            total_candidates += new_candidates
            logger.info(f"{source}: Processed {result.get('records_processed', 0)} records, created ~{new_candidates} new candidates")
            
            if total_candidates >= min_candidates:
                logger.info(f"Reached target of {min_candidates} candidates!")
                break
                
        except Exception as e:
            logger.error(f"{source}: Processing failed - {e}", exc_info=True)
    
    # Final count
    with get_db_session() as session:
        total_pending = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.status == 'needs_review',
            EntityMatchCandidate.deleted_at.is_(None)
        ).count()
    
    logger.info(f"\nTotal candidates now pending review: {total_pending}")
    return total_pending


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Ingest data and review match candidates"
    )
    parser.add_argument(
        '--min-candidates',
        type=int,
        default=100,
        help='Minimum number of candidates to generate (default: 100)'
    )
    parser.add_argument(
        '--skip-ingestion',
        action='store_true',
        help='Skip ingestion, only process existing staging records'
    )
    parser.add_argument(
        '--skip-review',
        action='store_true',
        help='Skip review, only ingest and process'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("INGEST AND REVIEW WORKFLOW")
    print("=" * 80)
    print(f"Started at: {datetime.now()}")
    print(f"Target candidates: {args.min_candidates}")
    print()
    
    # Step 1: Ingest data
    if not args.skip_ingestion:
        logger.info("Step 1: Ingesting data...")
        ingest_clinicaltrials_gov(page_size=500)
        ingest_pubmed(retmax=300)
        ingest_fda_sources()
        logger.info("Ingestion complete\n")
    else:
        logger.info("Skipping ingestion (using existing staging records)")
    
    # Step 2: Process to generate candidates
    logger.info("Step 2: Processing staging records...")
    total_candidates = process_sources_to_generate_candidates(min_candidates=args.min_candidates)
    
    if total_candidates < args.min_candidates:
        logger.warning(f"Only {total_candidates} candidates available (target: {args.min_candidates})")
    
    # Step 3: Review candidates
    if not args.skip_review and total_candidates > 0:
        logger.info(f"\nStep 3: Reviewing candidates...")
        logger.info(f"Run: python scripts/batch_review_candidates.py --limit {min(total_candidates, args.min_candidates)}")
        
        # Actually run the review
        import subprocess
        result = subprocess.run([
            sys.executable,
            str(project_root / 'scripts' / 'batch_review_candidates.py'),
            '--limit', str(min(total_candidates, args.min_candidates)),
            '--reviewer-name', 'automated_batch'
        ])
        
        if result.returncode == 0:
            logger.info("Review completed successfully!")
        else:
            logger.warning(f"Review exited with code {result.returncode}")
    else:
        logger.info("Skipping review")
    
    print("\n" + "=" * 80)
    print("WORKFLOW COMPLETE")
    print("=" * 80)
    print(f"Completed at: {datetime.now()}")


if __name__ == '__main__':
    main()

