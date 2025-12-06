#!/usr/bin/env python3
"""
Daily pipeline script for automation.
Ingests critical sources, processes staging records, and runs relationship inference.
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
from src.processing.pipeline import ProcessingPipeline

# Set up logging
log_dir = project_root / 'logs'
log_dir.mkdir(exist_ok=True)

log_file = log_dir / f'pipeline_{datetime.now().strftime("%Y%m%d")}.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def ingest_source(source_name, limit=100):
    """Ingest a source with error handling."""
    logger.info(f"Ingesting {source_name} (limit: {limit})...")
    
    try:
        # Import the ingestion module
        ingestion_module = __import__(f'ingestion.{source_name}', fromlist=[''])
        
        # Try different function name patterns
        ingest_func = None
        func_names = [
            'ingest',
            f'ingest_{source_name}',
            f'fetch_{source_name}',
            'fetch_studies_sample',  # clinicaltrials_gov
            'fetch_sample',  # pubmed
            'fetch_8k_filings_for_biotech_companies',  # sec_edgar
            'ingest_termination_8ks',  # sec_edgar alternative
        ]
        
        for func_name in func_names:
            if hasattr(ingestion_module, func_name):
                ingest_func = getattr(ingestion_module, func_name)
                break
        
        if not ingest_func:
            logger.warning(f"{source_name}: No ingestion function found")
            return {'status': 'skipped', 'reason': 'no_ingest_function'}
        
        # Run ingestion
        try:
            result = ingest_func(limit=limit)
        except TypeError:
            # Function might not accept limit parameter
            result = ingest_func()
        
        if isinstance(result, dict):
            records_inserted = result.get('inserted', 0) or result.get('staging_stats', {}).get('inserted', 0)
            logger.info(f"{source_name}: Inserted {records_inserted} records")
            return {'status': 'success', 'records_inserted': records_inserted}
        else:
            logger.warning(f"{source_name}: Unexpected result type")
            return {'status': 'warning'}
            
    except ImportError as e:
        logger.error(f"{source_name}: Import error - {e}")
        return {'status': 'error', 'error': str(e)}
    except Exception as e:
        logger.error(f"{source_name}: Error - {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}


def process_staging_records():
    """Process new staging records."""
    logger.info("Processing staging records...")
    
    # Critical sources to process
    sources_to_process = [
        'clinicaltrials_gov',
        'sec_edgar',
        'pubmed',
        'fda_drugs',
        'fda_warning_letters',
        'fda_clinical_hold',  # Event source - failure signals
        'fda_breakthrough',   # Event source - positive signals
        'fda_eua',
        'fda_guidance',
        'fda_orphan',
        'nih_reporter'
    ]
    
    pipeline = ProcessingPipeline(batch_size=50)
    total_processed = 0
    total_entities = 0
    total_relationships = 0
    
    for source in sources_to_process:
        # Check if processor exists
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
            result = pipeline.process_source(source, limit=100)
            
            if 'error' in result:
                logger.error(f"{source}: Processing error - {result['error']}")
                continue
            
            records = result.get('records_processed', 0)
            entities = result.get('entities_created', 0) + result.get('entities_matched', 0)
            relationships = result.get('relationships_created', 0)
            
            total_processed += records
            total_entities += entities
            total_relationships += relationships
            
            logger.info(f"{source}: Processed {records} records, created {entities} entities, {relationships} relationships")
            
        except Exception as e:
            logger.error(f"{source}: Processing failed - {e}", exc_info=True)
    
    logger.info(f"Total: {total_processed} records processed, {total_entities} entities, {total_relationships} relationships")
    return {
        'records_processed': total_processed,
        'entities_created': total_entities,
        'relationships_created': total_relationships
    }


def run_relationship_inference():
    """Run relationship inference (if ready)."""
    logger.info("Running relationship inference...")
    
    try:
        # Check if inference script exists
        inference_script = project_root / 'scripts' / 'infer_relationships.py'
        if not inference_script.exists():
            logger.warning("Relationship inference script not found, skipping")
            return {'status': 'skipped', 'reason': 'script_not_found'}
        
        # Import and run
        import subprocess
        result = subprocess.run(
            [sys.executable, str(inference_script), '--incremental'],
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.returncode == 0:
            logger.info("Relationship inference completed successfully")
            return {'status': 'success'}
        else:
            logger.error(f"Relationship inference failed: {result.stderr}")
            return {'status': 'error', 'error': result.stderr}
            
    except Exception as e:
        logger.error(f"Relationship inference error: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}


def main():
    """Main pipeline execution."""
    logger.info("=" * 80)
    logger.info("DAILY PIPELINE EXECUTION")
    logger.info("=" * 80)
    logger.info(f"Started at: {datetime.now()}")
    
    summary = {
        'ingestion': {},
        'processing': {},
        'inference': {}
    }
    
    # Step 1: Ingest critical sources (small daily batches)
    logger.info("\n[1] INGESTION")
    logger.info("-" * 80)
    
    critical_sources = ['clinicaltrials_gov', 'sec_edgar', 'pubmed', 'fda_drugs']
    for source in critical_sources:
        result = ingest_source(source, limit=50)  # Small daily batch
        summary['ingestion'][source] = result
    
    # Step 2: Process staging records
    logger.info("\n[2] PROCESSING")
    logger.info("-" * 80)
    
    processing_result = process_staging_records()
    summary['processing'] = processing_result
    
    # Step 3: Run relationship inference (weekly, not daily)
    # Only run on specific days to avoid overload
    if datetime.now().weekday() == 0:  # Monday
        logger.info("\n[3] RELATIONSHIP INFERENCE")
        logger.info("-" * 80)
        
        inference_result = run_relationship_inference()
        summary['inference'] = inference_result
    else:
        logger.info("\n[3] RELATIONSHIP INFERENCE")
        logger.info("-" * 80)
        logger.info("Skipping (runs weekly on Mondays)")
        summary['inference'] = {'status': 'skipped', 'reason': 'not_monday'}
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("PIPELINE SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Completed at: {datetime.now()}")
    logger.info(f"Ingestion: {len([r for r in summary['ingestion'].values() if r.get('status') == 'success'])}/{len(critical_sources)} successful")
    logger.info(f"Processing: {summary['processing'].get('records_processed', 0)} records processed")
    logger.info(f"Inference: {summary['inference'].get('status', 'unknown')}")
    
    return summary


if __name__ == '__main__':
    try:
        summary = main()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)

