"""
Batch ingestion script for testing all sources.

Ingests data from all 30 sources with processors, tracking test run metadata.
"""
import sys
import logging
import importlib
import signal
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.staging import StagingRawData
from sqlalchemy import func

logger = logging.getLogger(__name__)

# Source to ingestion function mapping
# Format: (module_path, function_name, kwargs_for_small_sample, kwargs_for_scale_test)
INGESTION_MAP = {
    'clinicaltrials_gov': (
        'ingestion.clinicaltrials_gov',
        'fetch_studies_sample',
        {'page_size': 50, 'days_back': 30, 'load_to_staging': True},
        {'page_size': 2000, 'days_back': 365, 'load_to_staging': True}
    ),
    'fda_drugs': (
        'ingestion.fda_drugs',
        'ingest_fda_drugs',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'fda_clinical_hold': (
        'ingestion.fda_clinical_hold',
        'fetch_clinical_holds',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'fda_breakthrough': (
        'ingestion.fda_breakthrough',
        'scrape_designations',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'fda_orphan': (
        'ingestion.fda_orphan',
        'fetch_orphan_designations',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'fda_orange_book': (
        'ingestion.fda_orange_book',
        'ingest_orange_book',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'fda_purple_book': (
        'ingestion.fda_purple_book',
        'search_biosimilars',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'fda_warning_letters': (
        'ingestion.fda_warning_letters',
        'fetch_recent_warnings',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'fda_guidance': (
        'ingestion.fda_guidance',
        'search_guidance',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'fda_eua': (
        'ingestion.fda_eua',
        'fetch_recent_euas',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'fda_expanded_access': (
        'ingestion.fda_expanded_access',
        'fetch_expanded_access',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'fda_faers': (
        'ingestion.fda_faers',
        'ingest_faers',
        {'load_to_staging': True, 'limit': 50},  # Small sample: 50 records
        {'load_to_staging': True, 'limit': 2000}  # Scale test: 2000 records
    ),
    'california_warn': (
        'ingestion.california_warn',
        'fetch_recent_warn_notices',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'federal_warn': (
        'ingestion.federal_warn',
        'fetch_recent_warn_notices',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'biospace_layoff_tracker': (
        'ingestion.biospace_layoff_tracker',
        'fetch_layoff_tracker',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'fierce_layoff_tracker': (
        'ingestion.fierce_layoff_tracker',
        'fetch_layoff_tracker',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'ema_epar': (
        'ingestion.ema_epar',
        'search_medicines',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'ema_prime': (
        'ingestion.ema_prime',
        'fetch_prime_designations',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'ema_trials': (
        'ingestion.ema_trials',
        'scrape_search_first_page',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'ema_guidelines': (
        'ingestion.ema_guidelines',
        'fetch_guidelines',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'who_ictrp': (
        'ingestion.who_ictrp',
        'ingest_ictrp',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'who_outbreak_news': (
        'ingestion.who_outbreak_news',
        'fetch_outbreak_news',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'uspto_public_pair': (
        'ingestion.uspto_public_pair',
        'search_application',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'health_canada': (
        'ingestion.health_canada',
        'search_products',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'mhra_uk': (
        'ingestion.mhra_uk',
        'search_products',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'tga_australia': (
        'ingestion.tga_australia',
        'search_medicines',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'nih_reporter': (
        'ingestion.nih_reporter',
        'search_projects',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'nsf_awards': (
        'ingestion.nsf_awards',
        'search_awards',
        {'limit': 50, 'load_to_staging': True},
        {'limit': 2000, 'load_to_staging': True}
    ),
    'vaers': (
        'ingestion.vaers',
        'download_recent_years',  # VAERS downloads files first, then needs ingest_vaers
        {'save_dir': None, 'years': None},
        {'save_dir': None, 'years': None}
    ),
    'ich_guidelines': (
        'ingestion.ich_guidelines',
        'fetch_guidelines',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'anvisa_brazil': (
        'ingestion.anvisa_brazil',
        'search_products',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'cdsco_india': (
        'ingestion.cdsco_india',
        'search_products',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'mfds_korea': (
        'ingestion.mfds_korea',
        'search_products',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
    'hsa_singapore': (
        'ingestion.hsa_singapore',
        'search_products',
        {'load_to_staging': True},
        {'load_to_staging': True}
    ),
}


def ingest_source(
    source_name: str,
    sample_size: str = 'small',
    test_run_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ingest data from a single source.
    
    Args:
        source_name: Name of the source
        sample_size: 'small' (10-50 records) or 'scale' (~2000 records)
        test_run_id: Optional test run ID for tracking
    
    Returns:
        Dictionary with ingestion results
    """
    if source_name not in INGESTION_MAP:
        return {
            'source_name': source_name,
            'status': 'error',
            'error': f'Source {source_name} not in ingestion map'
        }
    
    module_path, func_name, small_kwargs, scale_kwargs = INGESTION_MAP[source_name]
    
    # Select kwargs based on sample size
    kwargs = small_kwargs if sample_size == 'small' else scale_kwargs
    
    result = {
        'source_name': source_name,
        'test_run_id': test_run_id,
        'sample_size': sample_size,
        'ingestion_start': datetime.now(),
        'status': 'unknown',
        'records_fetched': 0,
        'records_inserted': 0,
        'records_skipped': 0,
        'errors': 0,
        'error_message': None
    }
    
    try:
        # Dynamically import and call the ingestion function
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        
        logger.info(f"Ingesting {source_name} (sample_size={sample_size})...")
        
        # Special handling for sources that need different approaches
        if source_name == 'vaers':
            # VAERS only downloads files - no direct staging load
            # Skip for now or implement ingest_vaers separately
            logger.warning(f"VAERS requires file download + separate parsing - skipping direct ingestion")
            result['status'] = 'skipped'
            result['error_message'] = 'VAERS requires two-step process (download + parse)'
            return result
        elif source_name == 'uspto_public_pair':
            # USPTO requires app_number - skip for batch ingestion
            logger.warning(f"USPTO Public PAIR requires application number - skipping batch ingestion")
            result['status'] = 'skipped'
            result['error_message'] = 'USPTO Public PAIR requires specific application numbers'
            return result
        else:
            # Call the ingestion function
            ingestion_result = func(**kwargs)
        
        # Extract statistics from result
        if isinstance(ingestion_result, dict):
            result['records_fetched'] = ingestion_result.get('parsed', 0) or ingestion_result.get('count', 0) or len(ingestion_result.get('studies', [])) or len(ingestion_result.get('notices', [])) or len(ingestion_result.get('designations', [])) or len(ingestion_result.get('euas', [])) or len(ingestion_result.get('entries', [])) or 0
            # Check staging_stats first (from StagingLoader)
            if 'staging_stats' in ingestion_result:
                result['records_inserted'] = ingestion_result['staging_stats'].get('inserted', 0)
                result['records_skipped'] = ingestion_result['staging_stats'].get('skipped', 0)
                result['errors'] = ingestion_result['staging_stats'].get('errors', 0)
            else:
                result['records_inserted'] = ingestion_result.get('inserted', 0)
                result['records_skipped'] = ingestion_result.get('skipped', 0)
                result['errors'] = ingestion_result.get('errors', 0)
            
            if 'error' in ingestion_result:
                result['status'] = 'error'
                result['error_message'] = ingestion_result['error']
            elif result['errors'] > 0:
                result['status'] = 'partial'
            else:
                result['status'] = 'success'
        else:
            result['status'] = 'success'
            result['records_fetched'] = len(ingestion_result) if isinstance(ingestion_result, list) else 1
        
        # Get actual staging counts
        with get_db_session() as session:
            staging_count = session.query(StagingRawData).filter(
                StagingRawData.source_system == source_name,
                StagingRawData.deleted_at.is_(None)
            ).count()
            
            # Count records ingested in this test run (approximate - records ingested after start)
            result['staging_total'] = staging_count
        
        result['ingestion_end'] = datetime.now()
        result['duration_seconds'] = (result['ingestion_end'] - result['ingestion_start']).total_seconds()
        
        logger.info(f"✓ {source_name}: {result['records_inserted']} inserted, {result['records_skipped']} skipped")
        
    except Exception as e:
        logger.error(f"✗ {source_name} ingestion failed: {e}", exc_info=True)
        result['status'] = 'error'
        result['error_message'] = str(e)
        result['ingestion_end'] = datetime.now()
        result['duration_seconds'] = (result['ingestion_end'] - result['ingestion_start']).total_seconds()
    
    return result


def ingest_all_sources(
    sample_size: str = 'small',
    test_run_id: Optional[str] = None,
    sources: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Ingest data from all test sources.
    
    Args:
        sample_size: 'small' (10-50 records) or 'scale' (~2000 records)
        test_run_id: Optional test run ID for tracking
        sources: Optional list of specific sources to ingest (default: all)
    
    Returns:
        Dictionary with overall statistics and per-source results
    """
    if test_run_id is None:
        test_run_id = str(uuid4())
    
    if sources is None:
        sources = list(INGESTION_MAP.keys())
    
    logger.info(f"Starting batch ingestion (test_run_id={test_run_id}, sample_size={sample_size}, sources={len(sources)})")
    
    start_time = datetime.now()
    results = []
    
    print(f"\n{'='*60}")
    print(f"Batch Ingestion Progress")
    print(f"{'='*60}")
    print(f"Total sources: {len(sources)}")
    print(f"Sample size: {sample_size}")
    print(f"Test Run ID: {test_run_id}")
    print(f"{'='*60}\n")
    
    # Skip problematic sources for small sample
    skip_sources = []
    if sample_size == 'small':
        # Skip FAERS and VAERS for small sample (can be very slow even with limit)
        skip_sources = ['vaers']  # FAERS now has limit, so keep it
        sources = [s for s in sources if s not in skip_sources]
        if skip_sources:
            logger.info(f"Skipping sources for small sample: {skip_sources}")
    
    # Timeout implementation (Unix/macOS only - signal.SIGALRM)
    use_timeout = hasattr(signal, 'SIGALRM')
    timeout_seconds = 120  # 2 minutes per source
    
    if use_timeout:
        def timeout_handler(signum, frame):
            raise TimeoutError(f"Source ingestion timed out after {timeout_seconds} seconds")
    
    for idx, source_name in enumerate(sources, 1):
        print(f"[{idx}/{len(sources)}] Processing {source_name}...", end=' ', flush=True)
        start_time = datetime.now()
        
        # Set timeout for slow sources (Unix/macOS only)
        if use_timeout:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)
        
        try:
            result = ingest_source(source_name, sample_size, test_run_id)
            if use_timeout:
                signal.alarm(0)  # Cancel timeout
        except TimeoutError as e:
            if use_timeout:
                signal.alarm(0)
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.warning(f"{source_name} timed out after {elapsed:.1f} seconds")
            result = {
                'source_name': source_name,
                'status': 'timeout',
                'error_message': f'Ingestion timed out after {timeout_seconds} seconds',
                'records_inserted': 0,
                'records_skipped': 0,
                'duration_seconds': elapsed
            }
        except Exception as e:
            if use_timeout:
                signal.alarm(0)
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"{source_name} failed: {e}")
            result = {
                'source_name': source_name,
                'status': 'error',
                'error_message': str(e),
                'records_inserted': 0,
                'records_skipped': 0,
                'duration_seconds': elapsed
            }
        
        results.append(result)
        
        # Print immediate result
        status = result.get('status', 'unknown')
        elapsed = result.get('duration_seconds', (datetime.now() - start_time).total_seconds())
        if status == 'timeout':
            status_icon = "⏱"
        elif status == 'success':
            status_icon = "✓"
        elif status == 'error':
            status_icon = "✗"
        else:
            status_icon = "⚠"
        inserted = result.get('records_inserted', 0)
        skipped = result.get('records_skipped', 0)
        if status == 'timeout':
            print(f"{status_icon} TIMEOUT ({elapsed:.1f}s)")
        else:
            print(f"{status_icon} {inserted} inserted, {skipped} skipped ({elapsed:.1f}s)")
        
        # Show running totals every 5 sources
        if idx % 5 == 0:
            total_inserted = sum(r.get('records_inserted', 0) for r in results)
            total_skipped = sum(r.get('records_skipped', 0) for r in results)
            successful = sum(1 for r in results if r.get('status') == 'success')
            timeouts = sum(1 for r in results if r.get('status') == 'timeout')
            print(f"  → Progress: {successful}/{idx} successful, {timeouts} timeouts, {total_inserted} total inserted, {total_skipped} total skipped\n")
    
    end_time = datetime.now()
    
    # Calculate summary statistics
    total_inserted = sum(r.get('records_inserted', 0) for r in results)
    total_skipped = sum(r.get('records_skipped', 0) for r in results)
    total_errors = sum(r.get('errors', 0) for r in results)
    successful = sum(1 for r in results if r.get('status') == 'success')
    failed = sum(1 for r in results if r.get('status') == 'error')
    partial = sum(1 for r in results if r.get('status') == 'partial')
    
    summary = {
        'test_run_id': test_run_id,
        'sample_size': sample_size,
        'start_time': start_time,
        'end_time': end_time,
        'duration_seconds': (end_time - start_time).total_seconds(),
        'sources_attempted': len(sources),
        'sources_successful': successful,
        'sources_partial': partial,
        'sources_failed': failed,
        'total_records_inserted': total_inserted,
        'total_records_skipped': total_skipped,
        'total_errors': total_errors,
        'results': results
    }
    
    logger.info(f"Batch ingestion complete: {successful} successful, {partial} partial, {failed} failed")
    logger.info(f"Total records: {total_inserted} inserted, {total_skipped} skipped")
    
    return summary


if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Ingest data from all test sources')
    parser.add_argument('--sample-size', choices=['small', 'scale'], default='small',
                       help='Sample size: small (10-50) or scale (~2000)')
    parser.add_argument('--test-run-id', type=str, default=None,
                       help='Test run ID for tracking')
    parser.add_argument('--sources', nargs='+', default=None,
                       help='Specific sources to ingest (default: all)')
    
    args = parser.parse_args()
    
    try:
        summary = ingest_all_sources(
            sample_size=args.sample_size,
            test_run_id=args.test_run_id,
            sources=args.sources
        )
        
        print(f"\n{'='*60}")
        print(f"Batch Ingestion Summary")
        print(f"{'='*60}")
        print(f"Test Run ID: {summary['test_run_id']}")
        print(f"Sample Size: {summary['sample_size']}")
        print(f"Duration: {summary['duration_seconds']:.1f} seconds")
        print(f"\nSources: {summary['sources_successful']} successful, {summary['sources_partial']} partial, {summary['sources_failed']} failed")
        print(f"Records: {summary['total_records_inserted']} inserted, {summary['total_records_skipped']} skipped")
        
        if summary['sources_failed'] > 0:
            print(f"\nFailed sources:")
            for r in summary['results']:
                if r.get('status') == 'error':
                    print(f"  - {r['source_name']}: {r.get('error_message', 'Unknown error')}")
        
    except Exception as e:
        logger.error(f"Error in batch ingestion: {e}", exc_info=True)
        sys.exit(1)

