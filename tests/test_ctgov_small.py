#!/usr/bin/env python3
"""
Test script for CT.gov ingestion with small dataset.
Ingests trials from this year only, limited to 2-3 trials for testing.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.ingest.ctgov import CtgovClient
from ncfd.pipeline.ctgov_pipeline import CtgovPipeline
from ncfd.db.session import get_session
from ncfd.config import get_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_small_ctgov_ingestion():
    """Test CT.gov ingestion with a very small dataset."""
    
    logger.info("🚀 Starting small CT.gov ingestion test")
    
    # Get configuration
    config = get_config()
    ctgov_config = config.get('ctgov', {})
    
    # Override config for testing - limit to this year only
    test_config = {
        **ctgov_config,
        'ingestion': {
            **ctgov_config.get('ingestion', {}),
            'max_studies_per_run': 3,  # Only 3 studies max
            'batch_size': 3,
            'default_since_days': 365,  # Last year
        }
    }
    
    try:
        # Initialize pipeline
        pipeline = CtgovPipeline(config=test_config)
        
        logger.info("📊 Running limited CT.gov ingestion...")
        
        # For testing, let's use a much more recent date to get fewer trials
        # Use last 30 days instead of last year to get a manageable dataset
        recent_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        logger.info(f"🔍 Using recent date: {recent_date} to limit dataset size")
        
        # Run ingestion with limited scope - be more flexible to get some data
        result = pipeline.run_limited_ingestion(
            max_studies=10,  # Allow up to 10 studies to ensure we get some data
            since_date=recent_date,
            phases=None,  # Don't restrict by phase - let's see what we get
            statuses=['recruiting', 'active, not recruiting', 'completed', 'not yet recruiting']
        )
        
        logger.info(f"✅ Ingestion completed: {result}")
        
        # Check what was ingested  
        with get_session() as session:
            from ncfd.db.models import Trial, Company
            
            trial_count = session.query(Trial).count()
            company_count = session.query(Company).count()
            
            logger.info(f"📈 Database state after ingestion:")
            logger.info(f"   - Trials: {trial_count}")
            logger.info(f"   - Companies: {company_count}")
            
            if trial_count > 0:
                # Show sample trials
                trials = session.query(Trial).limit(3).all()
                logger.info("🔍 Sample trials ingested:")
                for trial in trials:
                    title = trial.brief_title or "No title"
                    logger.info(f"   - {trial.nct_id}: {title[:60]}...")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ CT.gov ingestion test failed: {e}")
        raise

if __name__ == "__main__":
    test_small_ctgov_ingestion()
