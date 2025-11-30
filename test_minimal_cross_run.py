"""
Minimal cross-run resolution test.

Tests the happy path:
1. Process one trial (creates trial entity in DB)
2. Process one publication that references that trial by NCT ID
3. Check if Publication-Trial relationship was created

This tests the basic cross-run resolution flow, not edge cases.
"""
import logging
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models import StagingRawData, ClinicalTrial, Publication
from database.models.relationships import PublicationTrial
from src.processing.pipeline import ProcessingPipeline
from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
from src.processors.pubmed_processor import PubMedProcessor

# Configure logging to see diagnostic messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def create_test_trial_staging_record(session):
    """Create a test trial in staging."""
    nct_id = "NCT12345678"
    trial_data = {
        "nct_id": nct_id,
        "brief_title": "Test Trial for Cross-Run Resolution",
        "official_title": "A Test Clinical Trial to Verify Cross-Run Entity Resolution",
        "status": "RECRUITING",
        "phase": "Phase 2",
        "study_type": "INTERVENTIONAL",
        "lead_sponsor": {
            "name": "Test Pharma Inc",
            "class": "INDUSTRY"
        },
        "conditions": ["Test Disease"],
        "interventions": [
            {
                "intervention_type": "DRUG",
                "name": "Test Drug"
            }
        ]
    }
    
    staging = StagingRawData(
        staging_id=uuid4(),
        source_system='clinicaltrials_gov',
        source_record_id=nct_id,
        raw_data=trial_data,
        ingested_at=None,
        processed=False
    )
    session.add(staging)
    session.commit()
    
    logger.info(f"Created test trial staging record: {nct_id}")
    return staging, nct_id


def create_test_publication_staging_record(session, nct_id: str):
    """Create a test publication that references the trial by NCT ID."""
    pmid = "99999999"
    pub_data = {
        "pmid": pmid,
        "title": "Results from Clinical Trial NCT12345678",
        "abstract": f"This publication reports results from clinical trial {nct_id}. "
                   f"The trial {nct_id} showed promising results.",
        "authors": ["Test Author"],
        "publication_date": "2024-01-01"
    }
    
    staging = StagingRawData(
        staging_id=uuid4(),
        source_system='pubmed',
        source_record_id=pmid,
        raw_data=pub_data,
        ingested_at=None,
        processed=False
    )
    session.add(staging)
    session.commit()
    
    logger.info(f"Created test publication staging record: {pmid} (references {nct_id})")
    return staging, pmid


def check_relationship_created(session, nct_id: str, pmid: str):
    """Check if Publication-Trial relationship was created."""
    # Find the trial
    trial = session.query(ClinicalTrial).filter(
        ClinicalTrial.nct_id == nct_id,
        ClinicalTrial.deleted_at.is_(None)
    ).first()
    
    if not trial:
        logger.error(f"❌ Trial with NCT ID {nct_id} not found in database")
        return False
    
    # Find the publication
    pub = session.query(Publication).filter(
        Publication.pmid == pmid,
        Publication.deleted_at.is_(None)
    ).first()
    
    if not pub:
        logger.error(f"❌ Publication with PMID {pmid} not found in database")
        return False
    
    # Check for relationship
    rel = session.query(PublicationTrial).filter(
        PublicationTrial.pub_id == pub.pub_id,
        PublicationTrial.trial_id == trial.trial_id,
        PublicationTrial.deleted_at.is_(None)
    ).first()
    
    if rel:
        logger.info(
            f"✅ SUCCESS: Publication-Trial relationship found! "
            f"pub_id={pub.pub_id}, trial_id={trial.trial_id}"
        )
        return True
    else:
        logger.error(
            f"❌ FAILED: Publication-Trial relationship NOT found. "
            f"pub_id={pub.pub_id}, trial_id={trial.trial_id}"
        )
        return False


def main():
    """Run minimal cross-run test."""
    logger.info("=" * 80)
    logger.info("MINIMAL CROSS-RUN RESOLUTION TEST")
    logger.info("=" * 80)
    logger.info("")
    logger.info("This test verifies the happy path:")
    logger.info("1. Process one trial (creates trial entity)")
    logger.info("2. Process one publication referencing that trial by NCT ID")
    logger.info("3. Check if Publication-Trial relationship was created")
    logger.info("")
    
    with get_db_session() as session:
        # Step 1: Create and process trial
        logger.info("=" * 80)
        logger.info("STEP 1: Process Trial")
        logger.info("=" * 80)
        
        trial_staging, nct_id = create_test_trial_staging_record(session)
        
        pipeline = ProcessingPipeline(batch_size=10, use_hybrid_resolver=True)
        
        logger.info(f"Processing trial staging record: {trial_staging.source_record_id}")
        result = pipeline._process_single_record(
            session,
            trial_staging,
            ClinicalTrialsProcessor
        )
        
        if result.get('status') != 'success':
            logger.error(f"❌ Trial processing failed: {result}")
            return False
        
        logger.info(f"✅ Trial processed successfully")
        session.commit()
        
        # Verify trial was created
        trial = session.query(ClinicalTrial).filter(
            ClinicalTrial.nct_id == nct_id,
            ClinicalTrial.deleted_at.is_(None)
        ).first()
        
        if not trial:
            logger.error(f"❌ Trial not found in database after processing")
            return False
        
        logger.info(f"✅ Trial found in database: {trial.trial_id}")
        logger.info("")
        
        # Step 2: Create and process publication
        logger.info("=" * 80)
        logger.info("STEP 2: Process Publication (Cross-Run)")
        logger.info("=" * 80)
        logger.info("This publication references the trial from Step 1.")
        logger.info("The trial was processed in a different 'run', so this tests cross-run resolution.")
        logger.info("")
        
        pub_staging, pmid = create_test_publication_staging_record(session, nct_id)
        
        logger.info(f"Processing publication staging record: {pub_staging.source_record_id}")
        result = pipeline._process_single_record(
            session,
            pub_staging,
            PubMedProcessor
        )
        
        if result.get('status') != 'success':
            logger.error(f"❌ Publication processing failed: {result}")
            return False
        
        logger.info(f"✅ Publication processed successfully")
        session.commit()
        
        # Verify publication was created
        pub = session.query(Publication).filter(
            Publication.pmid == pmid,
            Publication.deleted_at.is_(None)
        ).first()
        
        if not pub:
            logger.error(f"❌ Publication not found in database after processing")
            return False
        
        logger.info(f"✅ Publication found in database: {pub.pub_id}")
        logger.info("")
        
        # Step 3: Check relationship
        logger.info("=" * 80)
        logger.info("STEP 3: Verify Relationship Creation")
        logger.info("=" * 80)
        
        relationship_exists = check_relationship_created(session, nct_id, pmid)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("TEST RESULT")
        logger.info("=" * 80)
        
        if relationship_exists:
            logger.info("✅ TEST PASSED: Cross-run resolution working!")
            logger.info("   Publication-Trial relationship was created successfully.")
            logger.info("   The publication was able to link to a trial from a previous processing run.")
            return True
        else:
            logger.error("❌ TEST FAILED: Cross-run resolution not working")
            logger.error("   Publication-Trial relationship was NOT created.")
            logger.error("   Check the logs above to see where resolution failed.")
            return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)


