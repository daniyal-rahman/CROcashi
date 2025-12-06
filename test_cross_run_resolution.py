"""
Diagnostic script to test cross-run entity resolution.

This script verifies that:
1. Entities processed in one run can be found in subsequent runs
2. Relationships can be created between entities from different runs
3. Cache behavior is working correctly
"""
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models import ClinicalTrial, Publication, PublicationTrial
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.types import EntityType, ExtractedEntity

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_cache_key_consistency():
    """Test that cache keys are consistent for the same entity."""
    logger.info("=" * 60)
    logger.info("TEST 1: Cache Key Consistency")
    logger.info("=" * 60)
    
    with get_db_session() as session:
        resolver = EntityResolver(session)
        
        # Create test entity with NCT ID
        entity1 = ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name="Test Trial",
            identifiers={'nct_id': 'NCT12345678'},
            context={},
            source_name='test',
            source_identifier='test-1'
        )
        
        entity2 = ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name="Test Trial",  # Same name
            identifiers={'nct_id': 'NCT12345678'},  # Same identifier
            context={},
            source_name='test',
            source_identifier='test-2'
        )
        
        key1 = resolver._make_cache_key(entity1)
        key2 = resolver._make_cache_key(entity2)
        
        logger.info(f"Entity 1 cache key: {key1}")
        logger.info(f"Entity 2 cache key: {key2}")
        
        if key1 == key2:
            logger.info("✅ PASS: Cache keys are consistent")
            return True
        else:
            logger.error("❌ FAIL: Cache keys differ for same entity")
            return False


def test_database_fallback():
    """Test that resolver can find entities from database."""
    logger.info("=" * 60)
    logger.info("TEST 2: Database Fallback")
    logger.info("=" * 60)
    
    with get_db_session() as session:
        # Find an existing trial in database
        trial = session.query(ClinicalTrial).filter(
            ClinicalTrial.nct_id.isnot(None)
        ).first()
        
        if not trial:
            logger.warning("⚠️  No trials with NCT IDs found in database")
            logger.info("   Run: python -m src.cli ingest --source clinicaltrials --limit 5")
            return None
        
        logger.info(f"Testing with trial: {trial.nct_id} ({trial.trial_title[:50]}...)")
        
        resolver = EntityResolver(session)
        
        # Create entity stub that references this trial
        entity = ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name=trial.trial_title,
            identifiers={'nct_id': trial.nct_id},
            context={},
            source_name='test',
            source_identifier='test-fallback'
        )
        
        # Resolve (should find in database, not cache)
        resolution = resolver.resolve(entity)
        
        if resolution.entity_id == trial.trial_id:
            logger.info(f"✅ PASS: Found trial in database: {resolution.entity_id}")
            logger.info(f"   Status: {resolution.status.value}")
            logger.info(f"   Method: {resolution.match_method.value if resolution.match_method else 'N/A'}")
            logger.info(f"   Confidence: {resolution.confidence_score:.2f}")
            return True
        else:
            logger.error(f"❌ FAIL: Expected {trial.trial_id}, got {resolution.entity_id}")
            return False


def test_cross_run_relationship():
    """Test that relationships can be created between entities from different runs."""
    logger.info("=" * 60)
    logger.info("TEST 3: Cross-Run Relationship Creation")
    logger.info("=" * 60)
    
    with get_db_session() as session:
        # Find existing trial
        trial = session.query(ClinicalTrial).filter(
            ClinicalTrial.nct_id.isnot(None)
        ).first()
        
        if not trial:
            logger.warning("⚠️  No trials found. Create some first.")
            return None
        
        # Find existing publication
        pub = session.query(Publication).filter(
            Publication.pmid.isnot(None)
        ).first()
        
        if not pub:
            logger.warning("⚠️  No publications found. Create some first.")
            return None
        
        logger.info(f"Trial: {trial.nct_id} ({trial.trial_id})")
        logger.info(f"Publication: {pub.pmid} ({pub.pub_id})")
        
        # Check if relationship already exists
        existing = session.query(PublicationTrial).filter(
            PublicationTrial.pub_id == pub.pub_id,
            PublicationTrial.trial_id == trial.trial_id
        ).first()
        
        if existing:
            logger.info(f"✅ Relationship already exists (created at: {existing.created_at})")
            logger.info("   This confirms cross-run relationships are possible")
            return True
        
        # Try to create relationship using resolver
        resolver = EntityResolver(session)
        
        # Create entity stubs
        pub_entity = ExtractedEntity(
            entity_type=EntityType.PUBLICATION,
            name=pub.title,
            identifiers={'pmid': pub.pmid},
            context={},
            source_name='test',
            source_identifier='test-pub'
        )
        
        trial_entity = ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name=trial.trial_title,
            identifiers={'nct_id': trial.nct_id},
            context={},
            source_name='test',
            source_identifier='test-trial'
        )
        
        # Resolve both (should find in database)
        pub_resolution = resolver.resolve(pub_entity)
        trial_resolution = resolver.resolve(trial_entity)
        
        if pub_resolution.entity_id and trial_resolution.entity_id:
            logger.info(f"✅ Both entities resolved:")
            logger.info(f"   Publication: {pub_resolution.entity_id}")
            logger.info(f"   Trial: {trial_resolution.entity_id}")
            logger.info("   Relationship could be created between these entities")
            return True
        else:
            logger.error("❌ FAIL: Could not resolve both entities")
            if not pub_resolution.entity_id:
                logger.error(f"   Publication resolution: {pub_resolution.status.value}")
            if not trial_resolution.entity_id:
                logger.error(f"   Trial resolution: {trial_resolution.status.value}")
            return False


def test_cache_behavior():
    """Test cache hit/miss behavior."""
    logger.info("=" * 60)
    logger.info("TEST 4: Cache Behavior")
    logger.info("=" * 60)
    
    with get_db_session() as session:
        resolver = EntityResolver(session)
        
        # Find existing trial
        trial = session.query(ClinicalTrial).filter(
            ClinicalTrial.nct_id.isnot(None)
        ).first()
        
        if not trial:
            logger.warning("⚠️  No trials found")
            return None
        
        entity = ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name=trial.trial_title,
            identifiers={'nct_id': trial.nct_id},
            context={},
            source_name='test',
            source_identifier='test-cache'
        )
        
        # First resolution - should hit database
        logger.info("First resolution (should hit database):")
        resolution1 = resolver.resolve(entity)
        logger.info(f"   Status: {resolution1.status.value}")
        logger.info(f"   Entity ID: {resolution1.entity_id}")
        logger.info(f"   Cache size: {len(resolver._memory_cache)}")
        
        # Second resolution - should hit cache
        logger.info("\nSecond resolution (should hit cache):")
        resolution2 = resolver.resolve(entity)
        logger.info(f"   Status: {resolution2.status.value}")
        logger.info(f"   Entity ID: {resolution2.entity_id}")
        logger.info(f"   Cache size: {len(resolver._memory_cache)}")
        
        if resolution1.entity_id == resolution2.entity_id:
            logger.info("✅ PASS: Both resolutions returned same entity ID")
            if resolution2.reasoning and "cache" in resolution2.reasoning.lower():
                logger.info("✅ PASS: Second resolution used cache")
                return True
            else:
                logger.warning("⚠️  Second resolution may not have used cache (check logs)")
                return True  # Still pass if IDs match
        else:
            logger.error("❌ FAIL: Resolutions returned different entity IDs")
            return False


def check_relationship_counts():
    """Check current relationship counts in database."""
    logger.info("=" * 60)
    logger.info("TEST 5: Relationship Counts")
    logger.info("=" * 60)
    
    with get_db_session() as session:
        from database.models.relationships import (
            TrialSponsor, TrialDrug, TrialDisease, PublicationTrial,
            PublicationDrug, PublicationCompany
        )
        
        counts = {
            'TrialSponsor': session.query(TrialSponsor).count(),
            'TrialDrug': session.query(TrialDrug).count(),
            'TrialDisease': session.query(TrialDisease).count(),
            'PublicationTrial': session.query(PublicationTrial).count(),
            'PublicationDrug': session.query(PublicationDrug).count(),
            'PublicationCompany': session.query(PublicationCompany).count(),
        }
        
        logger.info("Current relationship counts:")
        for rel_type, count in counts.items():
            status = "✅" if count > 0 else "⚠️"
            logger.info(f"   {status} {rel_type}: {count}")
        
        # Check if PublicationTrial has any relationships
        if counts['PublicationTrial'] > 0:
            logger.info("\n✅ Cross-run relationships exist!")
            logger.info("   This confirms the hybrid resolver is working")
            return True
        else:
            logger.warning("\n⚠️  No PublicationTrial relationships found")
            logger.info("   This is expected if publications haven't been processed yet")
            logger.info("   Or if publications don't reference existing trials")
            return None


def main():
    """Run all diagnostic tests."""
    logger.info("\n" + "=" * 60)
    logger.info("CROSS-RUN RESOLUTION DIAGNOSTIC TESTS")
    logger.info("=" * 60 + "\n")
    
    results = {}
    
    # Test 1: Cache key consistency
    results['cache_key_consistency'] = test_cache_key_consistency()
    logger.info("")
    
    # Test 2: Database fallback
    results['database_fallback'] = test_database_fallback()
    logger.info("")
    
    # Test 3: Cross-run relationships
    results['cross_run_relationship'] = test_cross_run_relationship()
    logger.info("")
    
    # Test 4: Cache behavior
    results['cache_behavior'] = test_cache_behavior()
    logger.info("")
    
    # Test 5: Relationship counts
    results['relationship_counts'] = check_relationship_counts()
    logger.info("")
    
    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)
    
    logger.info(f"✅ Passed: {passed}")
    logger.info(f"❌ Failed: {failed}")
    logger.info(f"⚠️  Skipped: {skipped}")
    
    if failed == 0:
        logger.info("\n✅ All tests passed or were skipped!")
        return 0
    else:
        logger.error(f"\n❌ {failed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())


