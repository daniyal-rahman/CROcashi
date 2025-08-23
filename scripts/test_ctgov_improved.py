#!/usr/bin/env python3
"""
Test script for improved CT.gov pipeline.
Tests the fixed pipeline with comprehensive field extraction for August 2025 trials.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.pipeline.ctgov_pipeline import CtgovPipeline
from ncfd.db.session import get_session
from ncfd.db.models import Trial, TrialVersion

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_august_2025_ingestion():
    """Test the CT.gov pipeline with all trials from August 2025 onwards."""
    
    logger.info("🧪 Testing CT.gov pipeline for August 2025 trials...")
    
    # Configuration for comprehensive ingestion
    config = {
        'max_studies_per_run': 1000,  # High limit to get all August trials
        'batch_size': 50,  # Larger batch size for efficiency
        'default_since_days': 30,
        'focus_phases': ['PHASE1', 'PHASE2', 'PHASE3', 'PHASE4'],  # All phases
        'focus_intervention_types': ['DRUG', 'BIOLOGICAL', 'DEVICE', 'PROCEDURE'],
        'focus_study_types': ['INTERVENTIONAL', 'OBSERVATIONAL']
    }
    
    try:
        # Initialize pipeline
        pipeline = CtgovPipeline(config=config)
        
        logger.info("✅ Pipeline initialized successfully")
        
        # Set start date to August 1, 2025
        start_date = "2025-08-01"
        logger.info(f"🔍 Starting comprehensive ingestion from {start_date}...")
        
        # Run comprehensive ingestion for August 2025
        result = pipeline.run_limited_ingestion(
            max_studies=1000,  # High limit to get all trials
            since_date=start_date,
            phases=['PHASE1', 'PHASE2', 'PHASE3', 'PHASE4'],  # All phases
            statuses=['RECRUITING', 'ACTIVE_NOT_RECRUITING', 'NOT_YET_RECRUITING', 'ENROLLING_BY_INVITATION']
        )
        
        if result.success:
            logger.info(f"✅ August 2025 ingestion successful!")
            logger.info(f"   - Trials processed: {result.trials_processed}")
            logger.info(f"   - New trials: {result.trials_new}")
            logger.info(f"   - Updated trials: {result.trials_updated}")
            logger.info(f"   - Changes detected: {result.changes_detected}")
            logger.info(f"   - Processing time: {result.processing_time_seconds:.2f}s")
            
            # Verify the database state
            with get_session() as session:
                total_trials = session.query(Trial).count()
                total_versions = session.query(TrialVersion).count()
                
                logger.info(f"📊 Database state after ingestion:")
                logger.info(f"   - Total trials: {total_trials}")
                logger.info(f"   - Total versions: {total_versions}")
                
                # Show sample of ingested trials
                recent_trials = session.query(Trial).order_by(Trial.last_seen_at.desc()).limit(5).all()
                logger.info("🔍 Recent trials ingested:")
                for trial in recent_trials:
                    title = trial.brief_title or "No title"
                    logger.info(f"   - {trial.nct_id}: {title[:60]}...")
                    logger.info(f"     Phase: {trial.phase}, Status: {trial.status}")
                    logger.info(f"     Sponsor: {trial.sponsor_text}")
                    
                    # Check versions
                    versions = session.query(TrialVersion).filter(
                        TrialVersion.trial_id == trial.trial_id
                    ).all()
                    logger.info(f"     Versions: {len(versions)}")
                
                # Show phase distribution
                phase_counts = session.query(Trial.phase, session.query(Trial).filter(Trial.phase == Trial.phase).count()).group_by(Trial.phase).all()
                logger.info("📊 Phase distribution:")
                for phase, count in phase_counts:
                    logger.info(f"   - {phase}: {count} trials")
                
                # Show status distribution
                status_counts = session.query(Trial.status, session.query(Trial).filter(Trial.status == Trial.status).count()).group_by(Trial.status).all()
                logger.info("📊 Status distribution:")
                for status, count in status_counts:
                    logger.info(f"   - {status}: {count} trials")
                    
        else:
            logger.error(f"❌ August 2025 ingestion failed:")
            for error in result.errors:
                logger.error(f"   - {error}")
            
        return result.success
        
    except Exception as e:
        logger.error(f"❌ Pipeline test failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = test_august_2025_ingestion()
    if success:
        logger.info("🎉 August 2025 ingestion completed successfully!")
    else:
        logger.error("💥 August 2025 ingestion failed!")
        sys.exit(1)
