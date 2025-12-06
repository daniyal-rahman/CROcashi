#!/usr/bin/env python3
"""
Focused Ingestion Script for Phase 2/3 Clinical Trials (2018-2024)

This script orchestrates a complete data ingestion pipeline:
1. Reset database (optional, requires --confirm)
2. Bulk fetch Phase 2/3 clinical trials from 2018-2024
3. Process staging data through the pipeline
4. Run relationship inference
5. Backfill events
6. Verify database population

Usage:
    python scripts/focused_ingestion.py --confirm              # Full run with DB reset
    python scripts/focused_ingestion.py --skip-reset --confirm # Skip DB reset
    python scripts/focused_ingestion.py --limit 1000 --confirm # Limit to 1000 studies
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, func

from database.config import get_db_session, engine
from database.models.base import Base
from database.models.staging import StagingRawData
from database.models.entities import Company, Drug
from database.models.clinical import ClinicalTrial, RegulatoryEvent
from database.models.relationships import TrialSponsor, TrialDrug, TrialDisease
from database.models.events import Event

# Set up logging
log_dir = project_root / 'logs'
log_dir.mkdir(exist_ok=True)

log_file = log_dir / f'focused_ingestion_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def reset_database() -> bool:
    """
    Reset database by dropping all tables and recreating schema.
    
    Returns:
        True if successful, False otherwise
    """
    logger.info("=" * 80)
    logger.info("RESETTING DATABASE")
    logger.info("=" * 80)
    logger.warning("This will delete ALL existing data!")
    
    try:
        # Drop all tables
        logger.info("Dropping all tables...")
        with get_db_session() as session:
            # Get all table names
            result = session.execute(text("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public'
            """))
            tables = [row[0] for row in result]
            
            if tables:
                for table in tables:
                    logger.info(f"  Dropping {table}...")
                    session.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                session.commit()
                logger.info(f"Dropped {len(tables)} tables")
            else:
                logger.info("No tables to drop")
        
        # Recreate schema
        logger.info("Recreating schema...")
        Base.metadata.create_all(engine)
        logger.info("Schema recreated successfully")
        
        return True
        
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_clinicaltrials_ingestion(
    start_year: int = 2018,
    end_year: int = 2024,
    max_studies: int = None
) -> dict:
    """
    Run bulk ingestion of Phase 2/3 clinical trials.
    
    Args:
        start_year: Start year for date range
        end_year: End year for date range
        max_studies: Optional limit on number of studies
        
    Returns:
        Dict with ingestion statistics
    """
    logger.info("=" * 80)
    logger.info("CLINICAL TRIALS BULK INGESTION")
    logger.info("=" * 80)
    logger.info(f"Parameters:")
    logger.info(f"  Phases: Phase 2, Phase 3")
    logger.info(f"  Date range: {start_year}-01-01 to {end_year}-12-31")
    logger.info(f"  Statuses: All (no filter)")
    logger.info(f"  Max studies: {max_studies or 'No limit'}")
    
    try:
        from ingestion.clinicaltrials_gov import fetch_phase_2_3_studies
        
        def progress_callback(fetched: int, total: int):
            pct = (fetched / total * 100) if total > 0 else 0
            logger.info(f"Progress: {fetched:,} / {total:,} ({pct:.1f}%)")
        
        result = fetch_phase_2_3_studies(
            start_year=start_year,
            end_year=end_year,
            max_studies=max_studies,
            load_to_staging=True,
            progress_callback=progress_callback,
        )
        
        logger.info("Ingestion complete:")
        logger.info(f"  Total fetched: {result['total_fetched']:,}")
        logger.info(f"  Total available: {result['total_available']:,}")
        logger.info(f"  Pages fetched: {result['pages_fetched']}")
        logger.info(f"  Staging: {result['staging_stats']}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error during ingestion: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


def process_staging_data(batch_size: int = 100) -> dict:
    """
    Process all staging data through the pipeline.
    
    Args:
        batch_size: Number of records to process per batch
        
    Returns:
        Dict with processing statistics
    """
    logger.info("=" * 80)
    logger.info("PROCESSING STAGING DATA")
    logger.info("=" * 80)
    
    try:
        from src.processing.pipeline import ProcessingPipeline
        
        # Check unprocessed count
        with get_db_session() as session:
            unprocessed = session.query(StagingRawData).filter(
                StagingRawData.source_system == 'clinicaltrials_gov',
                StagingRawData.processed == False,
                StagingRawData.deleted_at.is_(None)
            ).count()
            logger.info(f"Unprocessed staging records: {unprocessed:,}")
        
        if unprocessed == 0:
            logger.warning("No unprocessed records to process")
            return {'records_processed': 0}
        
        # Process through pipeline
        pipeline = ProcessingPipeline(batch_size=batch_size)
        
        logger.info(f"Processing clinicaltrials_gov source...")
        result = pipeline.process_source('clinicaltrials_gov', limit=None)
        
        if 'error' in result:
            logger.error(f"Processing error: {result['error']}")
            return result
        
        logger.info("Processing complete:")
        logger.info(f"  Records processed: {result.get('records_processed', 0):,}")
        logger.info(f"  Entities created: {result.get('entities_created', 0):,}")
        logger.info(f"  Entities matched: {result.get('entities_matched', 0):,}")
        logger.info(f"  Relationships created: {result.get('relationships_created', 0):,}")
        logger.info(f"  Needs review: {result.get('needs_review', 0):,}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing staging data: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


def run_relationship_inference() -> dict:
    """
    Run relationship inference to create additional relationships.
    
    Returns:
        Dict with inference statistics
    """
    logger.info("=" * 80)
    logger.info("RELATIONSHIP INFERENCE")
    logger.info("=" * 80)
    
    try:
        from src.services.relationship_inference import RelationshipInferenceService
        
        with get_db_session() as session:
            service = RelationshipInferenceService(session)
            
            logger.info("Running all inference methods...")
            results = service.infer_all_relationships(atomic=True)
            
            total_created = 0
            for rel_type, result in results.items():
                if result.get('status') == 'success':
                    created = result.get('relationships_created', 0)
                    total_created += created
                    logger.info(f"  {rel_type}: {created:,} relationships created")
                else:
                    logger.warning(f"  {rel_type}: {result.get('status', 'unknown')} - {result.get('error', '')}")
            
            logger.info(f"Total relationships inferred: {total_created:,}")
            
            return {
                'status': 'success',
                'total_created': total_created,
                'details': results
            }
            
    except Exception as e:
        logger.error(f"Error during relationship inference: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def backfill_events() -> dict:
    """
    Backfill events from trial status history and regulatory events.
    
    Returns:
        Dict with backfill statistics
    """
    logger.info("=" * 80)
    logger.info("EVENT BACKFILL")
    logger.info("=" * 80)
    
    try:
        from scripts.backfill_events import backfill_trial_events, backfill_regulatory_events
        
        logger.info("Backfilling trial events...")
        backfill_trial_events()
        
        logger.info("Backfilling regulatory events...")
        backfill_regulatory_events()
        
        # Count total events
        with get_db_session() as session:
            total_events = session.query(Event).filter(
                Event.deleted_at.is_(None)
            ).count()
            logger.info(f"Total events in database: {total_events:,}")
        
        return {'status': 'success', 'total_events': total_events}
        
    except Exception as e:
        logger.error(f"Error during event backfill: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def verify_database_population() -> dict:
    """
    Verify the database has been populated correctly.
    
    Returns:
        Dict with database statistics
    """
    logger.info("=" * 80)
    logger.info("DATABASE VERIFICATION")
    logger.info("=" * 80)
    
    with get_db_session() as session:
        # Entity counts
        company_count = session.query(Company).filter(Company.deleted_at.is_(None)).count()
        drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
        trial_count = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
        
        # Relationship counts
        sponsor_count = session.query(TrialSponsor).filter(TrialSponsor.deleted_at.is_(None)).count()
        trial_drug_count = session.query(TrialDrug).filter(TrialDrug.deleted_at.is_(None)).count()
        trial_disease_count = session.query(TrialDisease).filter(TrialDisease.deleted_at.is_(None)).count()
        
        # Event count
        event_count = session.query(Event).filter(Event.deleted_at.is_(None)).count()
        
        # Staging stats
        staging_total = session.query(StagingRawData).filter(
            StagingRawData.deleted_at.is_(None)
        ).count()
        staging_processed = session.query(StagingRawData).filter(
            StagingRawData.processed == True,
            StagingRawData.deleted_at.is_(None)
        ).count()
        
        # Companies with trials
        companies_with_trials = session.query(
            func.count(func.distinct(TrialSponsor.entity_id))
        ).filter(
            TrialSponsor.entity_type == 'company',
            TrialSponsor.deleted_at.is_(None)
        ).scalar()
        
        # Trial phase distribution
        phase_distribution = {}
        phase_query = session.execute(text("""
            SELECT phase, COUNT(*) as count
            FROM clinical_trials
            WHERE deleted_at IS NULL AND phase IS NOT NULL
            GROUP BY phase
            ORDER BY count DESC
        """))
        for phase, count in phase_query:
            phase_distribution[phase] = count
        
        # Trial status distribution
        status_distribution = {}
        status_query = session.execute(text("""
            SELECT status, COUNT(*) as count
            FROM clinical_trials
            WHERE deleted_at IS NULL AND status IS NOT NULL
            GROUP BY status
            ORDER BY count DESC
        """))
        for status, count in status_query:
            status_distribution[status] = count
    
    stats = {
        'entities': {
            'companies': company_count,
            'drugs': drug_count,
            'trials': trial_count,
        },
        'relationships': {
            'trial_sponsors': sponsor_count,
            'trial_drugs': trial_drug_count,
            'trial_diseases': trial_disease_count,
        },
        'events': event_count,
        'staging': {
            'total': staging_total,
            'processed': staging_processed,
            'processing_rate': f"{staging_processed/staging_total*100:.1f}%" if staging_total > 0 else "N/A"
        },
        'companies_with_trials': companies_with_trials,
        'phase_distribution': phase_distribution,
        'status_distribution': status_distribution,
    }
    
    # Log results
    logger.info("ENTITIES:")
    logger.info(f"  Companies: {company_count:,}")
    logger.info(f"  Drugs: {drug_count:,}")
    logger.info(f"  Trials: {trial_count:,}")
    
    logger.info("\nRELATIONSHIPS:")
    logger.info(f"  Trial-Sponsors: {sponsor_count:,}")
    logger.info(f"  Trial-Drugs: {trial_drug_count:,}")
    logger.info(f"  Trial-Diseases: {trial_disease_count:,}")
    
    logger.info(f"\nEVENTS: {event_count:,}")
    
    logger.info(f"\nCOMPANIES WITH TRIALS: {companies_with_trials:,}")
    
    logger.info(f"\nSTAGING: {staging_processed:,}/{staging_total:,} processed ({stats['staging']['processing_rate']})")
    
    logger.info("\nPHASE DISTRIBUTION:")
    for phase, count in sorted(phase_distribution.items(), key=lambda x: -x[1]):
        logger.info(f"  {phase}: {count:,}")
    
    logger.info("\nSTATUS DISTRIBUTION:")
    for status, count in sorted(status_distribution.items(), key=lambda x: -x[1]):
        logger.info(f"  {status}: {count:,}")
    
    return stats


def main():
    """Main entry point for focused ingestion."""
    parser = argparse.ArgumentParser(
        description='Focused ingestion for Phase 2/3 clinical trials (2018-2024)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run with database reset
  python scripts/focused_ingestion.py --confirm

  # Skip database reset (add to existing data)
  python scripts/focused_ingestion.py --skip-reset --confirm

  # Test with limited studies
  python scripts/focused_ingestion.py --limit 1000 --confirm

  # Custom date range
  python scripts/focused_ingestion.py --start-year 2020 --end-year 2024 --confirm
        """
    )
    
    parser.add_argument(
        '--confirm',
        action='store_true',
        required=True,
        help='Confirm you want to run the ingestion (required)'
    )
    parser.add_argument(
        '--skip-reset',
        action='store_true',
        help='Skip database reset (preserve existing data)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of studies to fetch (for testing)'
    )
    parser.add_argument(
        '--start-year',
        type=int,
        default=2018,
        help='Start year for date range (default: 2018)'
    )
    parser.add_argument(
        '--end-year',
        type=int,
        default=2024,
        help='End year for date range (default: 2024)'
    )
    parser.add_argument(
        '--skip-processing',
        action='store_true',
        help='Skip processing step (only ingest to staging)'
    )
    parser.add_argument(
        '--skip-inference',
        action='store_true',
        help='Skip relationship inference step'
    )
    parser.add_argument(
        '--skip-backfill',
        action='store_true',
        help='Skip event backfill step'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Batch size for processing (default: 100)'
    )
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    
    logger.info("=" * 80)
    logger.info("FOCUSED INGESTION PIPELINE")
    logger.info("=" * 80)
    logger.info(f"Started at: {start_time}")
    logger.info(f"Log file: {log_file}")
    logger.info("")
    logger.info("Configuration:")
    logger.info(f"  Date range: {args.start_year} - {args.end_year}")
    logger.info(f"  Phases: Phase 2, Phase 3")
    logger.info(f"  Statuses: All")
    logger.info(f"  Max studies: {args.limit or 'No limit'}")
    logger.info(f"  Skip reset: {args.skip_reset}")
    logger.info(f"  Skip processing: {args.skip_processing}")
    logger.info(f"  Skip inference: {args.skip_inference}")
    logger.info(f"  Skip backfill: {args.skip_backfill}")
    logger.info("")
    
    summary = {}
    
    # Step 1: Database Reset
    if not args.skip_reset:
        logger.info("\n" + "=" * 80)
        logger.info("[STEP 1/5] DATABASE RESET")
        logger.info("=" * 80)
        
        success = reset_database()
        summary['reset'] = {'status': 'success' if success else 'failed'}
        
        if not success:
            logger.error("Database reset failed. Aborting.")
            sys.exit(1)
    else:
        logger.info("\n[STEP 1/5] SKIPPED: Database Reset")
        summary['reset'] = {'status': 'skipped'}
    
    # Step 2: ClinicalTrials.gov Bulk Ingestion
    logger.info("\n" + "=" * 80)
    logger.info("[STEP 2/5] CLINICAL TRIALS INGESTION")
    logger.info("=" * 80)
    
    ingestion_result = run_clinicaltrials_ingestion(
        start_year=args.start_year,
        end_year=args.end_year,
        max_studies=args.limit
    )
    summary['ingestion'] = ingestion_result
    
    if 'error' in ingestion_result:
        logger.error("Ingestion failed. Continuing with existing data...")
    
    # Step 3: Process Staging Data
    if not args.skip_processing:
        logger.info("\n" + "=" * 80)
        logger.info("[STEP 3/5] PROCESSING")
        logger.info("=" * 80)
        
        processing_result = process_staging_data(batch_size=args.batch_size)
        summary['processing'] = processing_result
    else:
        logger.info("\n[STEP 3/5] SKIPPED: Processing")
        summary['processing'] = {'status': 'skipped'}
    
    # Step 4: Relationship Inference
    if not args.skip_inference:
        logger.info("\n" + "=" * 80)
        logger.info("[STEP 4/5] RELATIONSHIP INFERENCE")
        logger.info("=" * 80)
        
        inference_result = run_relationship_inference()
        summary['inference'] = inference_result
    else:
        logger.info("\n[STEP 4/5] SKIPPED: Relationship Inference")
        summary['inference'] = {'status': 'skipped'}
    
    # Step 5: Event Backfill
    if not args.skip_backfill:
        logger.info("\n" + "=" * 80)
        logger.info("[STEP 5/5] EVENT BACKFILL")
        logger.info("=" * 80)
        
        backfill_result = backfill_events()
        summary['backfill'] = backfill_result
    else:
        logger.info("\n[STEP 5/5] SKIPPED: Event Backfill")
        summary['backfill'] = {'status': 'skipped'}
    
    # Final Verification
    logger.info("\n" + "=" * 80)
    logger.info("FINAL VERIFICATION")
    logger.info("=" * 80)
    
    verification = verify_database_population()
    summary['verification'] = verification
    
    # Summary
    end_time = datetime.now()
    duration = end_time - start_time
    
    logger.info("\n" + "=" * 80)
    logger.info("PIPELINE SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Completed at: {end_time}")
    logger.info(f"Duration: {duration}")
    logger.info("")
    
    logger.info("Step Results:")
    logger.info(f"  1. Database Reset: {summary.get('reset', {}).get('status', 'unknown')}")
    logger.info(f"  2. Ingestion: {summary.get('ingestion', {}).get('total_fetched', 0):,} studies fetched")
    logger.info(f"  3. Processing: {summary.get('processing', {}).get('records_processed', 0):,} records processed")
    logger.info(f"  4. Inference: {summary.get('inference', {}).get('total_created', 0):,} relationships created")
    logger.info(f"  5. Backfill: {summary.get('backfill', {}).get('status', 'unknown')}")
    
    logger.info("")
    logger.info("Final Database State:")
    logger.info(f"  Trials: {verification['entities']['trials']:,}")
    logger.info(f"  Companies: {verification['entities']['companies']:,}")
    logger.info(f"  Drugs: {verification['entities']['drugs']:,}")
    logger.info(f"  Companies with trials: {verification['companies_with_trials']:,}")
    logger.info(f"  Events: {verification['events']:,}")
    
    logger.info("\n" + "=" * 80)
    logger.info("FOCUSED INGESTION COMPLETE")
    logger.info("=" * 80)
    
    return summary


if __name__ == '__main__':
    try:
        summary = main()
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("\nIngestion interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)




