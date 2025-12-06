#!/usr/bin/env python3
"""
Ingest event sources (fda_clinical_hold, fda_breakthrough).
These are critical failure signal sources.
"""
import sys
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ingestion.fda_clinical_hold import fetch_clinical_holds
from ingestion.fda_breakthrough import scrape_designations
from src.processing.pipeline import ProcessingPipeline

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def ingest_and_process_event_sources():
    """Ingest and process event sources."""
    logger.info("=" * 80)
    logger.info("INGESTING EVENT SOURCES")
    logger.info("=" * 80)
    
    results = {}
    
    # 1. Ingest fda_clinical_hold
    logger.info("\n[1] Ingesting fda_clinical_hold...")
    try:
        result = fetch_clinical_holds(load_to_staging=True)
        results['fda_clinical_hold'] = result
        
        if 'error' in result:
            logger.error(f"fda_clinical_hold: Error - {result['error']}")
        else:
            inserted = result.get('staging_stats', {}).get('inserted', 0)
            logger.info(f"fda_clinical_hold: Inserted {inserted} records to staging")
    except Exception as e:
        logger.error(f"fda_clinical_hold: Failed - {e}", exc_info=True)
        results['fda_clinical_hold'] = {'error': str(e)}
    
    # 2. Ingest fda_breakthrough
    logger.info("\n[2] Ingesting fda_breakthrough...")
    try:
        result = scrape_designations(load_to_staging=True)
        results['fda_breakthrough'] = result
        
        if 'error' in result:
            logger.error(f"fda_breakthrough: Error - {result['error']}")
        else:
            inserted = result.get('staging_stats', {}).get('inserted', 0)
            logger.info(f"fda_breakthrough: Inserted {inserted} records to staging")
    except Exception as e:
        logger.error(f"fda_breakthrough: Failed - {e}", exc_info=True)
        results['fda_breakthrough'] = {'error': str(e)}
    
    # 3. Process ingested records
    logger.info("\n[3] Processing ingested records...")
    pipeline = ProcessingPipeline(batch_size=50)
    
    for source in ['fda_clinical_hold', 'fda_breakthrough']:
        if source not in pipeline.PROCESSOR_MAP:
            logger.warning(f"{source}: No processor found, skipping processing")
            continue
        
        logger.info(f"Processing {source}...")
        try:
            result = pipeline.process_source(source, limit=None)
            
            if 'error' in result:
                logger.error(f"{source}: Processing error - {result['error']}")
            else:
                records = result.get('records_processed', 0)
                entities = result.get('entities_created', 0) + result.get('entities_matched', 0)
                relationships = result.get('relationships_created', 0)
                logger.info(f"{source}: Processed {records} records, created {entities} entities, {relationships} relationships")
                results[f'{source}_processing'] = result
        except Exception as e:
            logger.error(f"{source}: Processing failed - {e}", exc_info=True)
            results[f'{source}_processing'] = {'error': str(e)}
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("INGESTION SUMMARY")
    logger.info("=" * 80)
    
    for source, result in results.items():
        if 'error' in result:
            logger.info(f"{source}: ✗ Error - {result['error']}")
        elif 'staging_stats' in result:
            stats = result['staging_stats']
            logger.info(f"{source}: ✓ Inserted {stats.get('inserted', 0)} records")
        elif 'records_processed' in result:
            logger.info(f"{source}: ✓ Processed {result.get('records_processed', 0)} records")
    
    return results


if __name__ == '__main__':
    ingest_and_process_event_sources()

