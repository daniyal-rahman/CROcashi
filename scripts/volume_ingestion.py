"""
Volume ingestion script to populate the database with real-world data.

This script:
1. Fetches data from multiple sources
2. Loads into staging
3. Processes through pipeline
4. Creates events via backfill
"""
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from src.processing.pipeline import ProcessingPipeline
from ingestion.clinicaltrials_gov import fetch_studies_sample
from ingestion.pubmed import fetch_sample as fetch_pubmed

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def ingest_clinicaltrials_gov(count=1000, days_back=365):
    """Ingest ClinicalTrials.gov data."""
    logger.info(f"Fetching up to {count} ClinicalTrials.gov studies from last {days_back} days...")
    try:
        # Use diverse queries to get different studies (API doesn't support simple pagination)
        # Cover multiple therapeutic areas to capture more companies
        queries = [
            "cancer OR oncology",
            "drug OR pharmaceutical OR biotech",
            "clinical trial AND (terminated OR withdrawn)",
            "(Phase II OR Phase III) AND cancer",
            "immunotherapy",
            "CAR-T OR CAR T-cell",
            "biomarker AND cancer",
            "precision medicine",
            "targeted therapy",
            "rare disease",
            # Add more therapeutic areas for better coverage
            "Alzheimer OR dementia OR neurodegenerative",
            "neurology OR CNS OR central nervous system",
            "diabetes OR metabolic",
            "cardiovascular OR heart",
            "autoimmune OR inflammation",
            "Phase III",  # Capture late-stage trials (more likely to have company sponsors)
            "INDUSTRY",  # Search by sponsor class to get industry-sponsored trials
        ]
        
        total_fetched = 0
        page_size = 100  # API max per request
        studies_per_query = count // len(queries) if len(queries) > 0 else count
        
        for i, query in enumerate(queries[:10]):  # Limit to 10 queries
            if total_fetched >= count:
                break
                
            current_count = min(studies_per_query, count - total_fetched, page_size)
            logger.info(f"  Query {i+1}/{len(queries)}: '{query}' ({current_count} studies)...")
            
            result = fetch_studies_sample(
                query_term=query,
                page_size=current_count,
                load_to_staging=True,
                days_back=days_back
            )
            
            if isinstance(result, dict):
                studies = result.get('studies', [])
                batch_count = len(studies)
                total_fetched += batch_count
                logger.info(f"    Fetched {batch_count} studies")
            else:
                logger.warning(f"    Unexpected result type: {type(result)}")
        
        logger.info(f"✓ ClinicalTrials.gov: Fetched {total_fetched} studies and loaded to staging")
        return True
    except Exception as e:
        logger.error(f"✗ ClinicalTrials.gov ingestion failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def ingest_fda_drugs(count=100):
    """Ingest FDA Drugs data."""
    logger.info(f"Fetching {count} FDA drug approvals...")
    try:
        # FDA drugs ingestion may need to be implemented or use a different approach
        # For now, skip if not available
        logger.warning("FDA Drugs ingestion not yet implemented, skipping...")
        return False
    except Exception as e:
        logger.error(f"✗ FDA Drugs ingestion failed: {e}")
        return False


def ingest_pubmed(count=500, days_back=365):
    """Ingest PubMed data."""
    logger.info(f"Fetching {count} PubMed articles from last {days_back} days...")
    try:
        result = fetch_pubmed(
            term="clinical trial AND (cancer OR oncology OR biotech OR pharmaceutical)",
            retmax=count,
            load_to_staging=True,
            days_back=days_back
        )
        
        # Check if result is a dict (expected) or string (error)
        if isinstance(result, dict):
            search_result = result.get('search', {})
            ids = search_result.get('esearchresult', {}).get('idlist', [])
            logger.info(f"✓ PubMed: Fetched {len(ids)} article IDs and loaded to staging")
        else:
            logger.warning(f"⚠ PubMed: Unexpected result format")
        
        return True
    except Exception as e:
        logger.error(f"✗ PubMed ingestion failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def process_staging_data():
    """Process all unprocessed staging data through the pipeline."""
    logger.info("=" * 60)
    logger.info("Processing Staging Data")
    logger.info("=" * 60)
    
    pipeline = ProcessingPipeline(batch_size=50)
    
    sources = ['clinicaltrials_gov', 'pubmed']  # fda_drugs can be added when ready
    
    total_stats = {
        'records_processed': 0,
        'entities_created': 0,
        'relationships_created': 0
    }
    
    for source in sources:
        logger.info(f"\nProcessing {source}...")
        try:
            stats = pipeline.process_source(source_name=source, limit=None)
            
            if 'error' in stats:
                logger.warning(f"  ⚠ {source}: {stats['error']}")
                continue
            
            logger.info(f"  ✓ {source}:")
            logger.info(f"    - Records processed: {stats.get('records_processed', 0)}")
            logger.info(f"    - Entities created: {stats.get('entities_created', 0)}")
            logger.info(f"    - Entities matched: {stats.get('entities_matched', 0)}")
            logger.info(f"    - Relationships created: {stats.get('relationships_created', 0)}")
            
            total_stats['records_processed'] += stats.get('records_processed', 0)
            total_stats['entities_created'] += stats.get('entities_created', 0)
            total_stats['relationships_created'] += stats.get('relationships_created', 0)
            
        except Exception as e:
            logger.error(f"  ✗ {source} processing failed: {e}", exc_info=True)
    
    logger.info("\n" + "=" * 60)
    logger.info("Processing Summary")
    logger.info("=" * 60)
    logger.info(f"Total records processed: {total_stats['records_processed']}")
    logger.info(f"Total entities created: {total_stats['entities_created']}")
    logger.info(f"Total relationships created: {total_stats['relationships_created']}")
    
    return total_stats


def verify_database_population():
    """Verify the database has been populated."""
    logger.info("\n" + "=" * 60)
    logger.info("Database Population Status")
    logger.info("=" * 60)
    
    with get_db_session() as session:
        from database.models.entities import Company
        from database.models.clinical import ClinicalTrial
        from database.models.relationships import TrialSponsor
        from database.models.events import Event
        from sqlalchemy import func
        
        company_count = session.query(Company).filter(Company.deleted_at.is_(None)).count()
        trial_count = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
        sponsor_count = session.query(TrialSponsor).filter(TrialSponsor.deleted_at.is_(None)).count()
        event_count = session.query(Event).filter(Event.deleted_at.is_(None)).count()
        
        # Companies with trials
        companies_with_trials = session.query(func.count(func.distinct(TrialSponsor.entity_id))).filter(
            TrialSponsor.entity_type == 'company',
            TrialSponsor.deleted_at.is_(None)
        ).scalar()
        
        logger.info(f"Companies: {company_count}")
        logger.info(f"Trials: {trial_count}")
        logger.info(f"Trial Sponsors: {sponsor_count}")
        logger.info(f"Events: {event_count}")
        logger.info(f"Companies with trials: {companies_with_trials}")
        
        return {
            'companies': company_count,
            'trials': trial_count,
            'sponsors': sponsor_count,
            'events': event_count,
            'companies_with_trials': companies_with_trials
        }


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Volume Ingestion & Processing")
    logger.info("=" * 60)
    
    try:
        # Step 1: Ingest data (past 1 year)
        logger.info("\n[Step 1] Ingesting data from sources (past 1 year)...")
        ingest_clinicaltrials_gov(count=1000, days_back=365)
        # ingest_fda_drugs(count=100)  # Skip for now
        ingest_pubmed(count=500, days_back=365)
        
        # Step 2: Process staging data
        logger.info("\n[Step 2] Processing staging data...")
        process_staging_data()
        
        # Step 3: Backfill events
        logger.info("\n[Step 3] Backfilling events...")
        from scripts.backfill_events import backfill_trial_events, backfill_regulatory_events
        backfill_trial_events()
        backfill_regulatory_events()
        
        # Step 4: Verify
        logger.info("\n[Step 4] Verifying database population...")
        stats = verify_database_population()
        
        logger.info("\n" + "=" * 60)
        logger.info("✓ Volume ingestion complete!")
        logger.info("=" * 60)
        logger.info(f"\nDashboard should now show:")
        logger.info(f"  - {stats['companies']} companies")
        logger.info(f"  - {stats['trials']} trials")
        logger.info(f"  - {stats['events']} events in timelines")
        logger.info(f"  - {stats['companies_with_trials']} companies with trial data")
        
    except Exception as e:
        logger.error(f"Volume ingestion failed: {e}", exc_info=True)
        sys.exit(1)

