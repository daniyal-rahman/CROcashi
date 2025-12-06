"""
Prepare test environment for system testing.

Handles test isolation by clearing or archiving test data before running tests.
"""
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from sqlalchemy import and_

logger = logging.getLogger(__name__)

# List of all test sources (30 sources with processors)
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


def prepare_test_environment(
    strategy: str = 'clear',
    test_sources: Optional[List[str]] = None
) -> dict:
    """
    Prepare test environment by isolating test data.
    
    Args:
        strategy: One of 'clear', 'archive', 'date_filter'
            - 'clear': Reset processed=False for test sources, clear processing logs
            - 'archive': Move existing test data to archive (not implemented yet)
            - 'date_filter': Mark records with test run timestamp (no clearing)
        test_sources: List of source names to prepare. If None, uses TEST_SOURCES.
    
    Returns:
        Dictionary with test run ID, start timestamp, and statistics
    """
    if test_sources is None:
        test_sources = TEST_SOURCES
    
    test_run_id = str(uuid4())
    start_timestamp = datetime.now()
    
    logger.info(f"Preparing test environment (strategy: {strategy}, test_run_id: {test_run_id})")
    
    stats = {
        'test_run_id': test_run_id,
        'start_timestamp': start_timestamp,
        'strategy': strategy,
        'sources_prepared': len(test_sources),
        'staging_records_reset': 0,
        'processing_logs_cleared': 0,
    }
    
    with get_db_session() as session:
        if strategy == 'clear':
            # Reset processed flag for test sources
            staging_reset = session.query(StagingRawData).filter(
                and_(
                    StagingRawData.source_system.in_(test_sources),
                    StagingRawData.processed == True,
                    StagingRawData.deleted_at.is_(None)
                )
            ).update({
                'processed': False,
                'processed_at': None
            }, synchronize_session=False)
            
            stats['staging_records_reset'] = staging_reset
            
            # Clear processing logs for test sources
            logs_cleared = session.query(SourceProcessingLog).filter(
                and_(
                    SourceProcessingLog.source_name.in_(test_sources),
                    SourceProcessingLog.deleted_at.is_(None)
                )
            ).delete(synchronize_session=False)
            
            stats['processing_logs_cleared'] = logs_cleared
            
            session.commit()
            
            logger.info(f"Cleared test environment: {staging_reset} staging records reset, {logs_cleared} processing logs cleared")
            
        elif strategy == 'archive':
            # TODO: Implement archive strategy (move to archive table)
            logger.warning("Archive strategy not yet implemented, using 'clear' instead")
            return prepare_test_environment('clear', test_sources)
            
        elif strategy == 'date_filter':
            # No clearing, just record timestamp for filtering later
            logger.info("Using date filter strategy - no data cleared, records will be filtered by timestamp")
            
        else:
            raise ValueError(f"Unknown strategy: {strategy}. Must be one of: 'clear', 'archive', 'date_filter'")
    
    logger.info(f"Test environment prepared: {stats}")
    return stats


if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Prepare test environment')
    parser.add_argument('--strategy', choices=['clear', 'archive', 'date_filter'],
                       default='clear', help='Test isolation strategy')
    parser.add_argument('--sources', nargs='+', default=None,
                       help='Specific sources to prepare (default: all test sources)')
    
    args = parser.parse_args()
    
    try:
        result = prepare_test_environment(
            strategy=args.strategy,
            test_sources=args.sources
        )
        
        print(f"\n✓ Test environment prepared")
        print(f"  Test Run ID: {result['test_run_id']}")
        print(f"  Strategy: {result['strategy']}")
        print(f"  Sources prepared: {result['sources_prepared']}")
        print(f"  Staging records reset: {result['staging_records_reset']}")
        print(f"  Processing logs cleared: {result['processing_logs_cleared']}")
        
    except Exception as e:
        logger.error(f"Error preparing test environment: {e}", exc_info=True)
        sys.exit(1)

