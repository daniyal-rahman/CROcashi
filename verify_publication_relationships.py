"""
Comprehensive verification script for Publication-Trial and Publication-Drug relationships.

This script verifies:
1. Current relationship counts in database
2. Relationship creation flow
3. Cross-run resolution functionality
4. RelationshipBuilder integration
5. Identifies blocking issues
"""
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from database.models import (
    ClinicalTrial, Publication, Drug, SourceProcessingLog
)
from database.models.relationships import PublicationTrial, PublicationDrug
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.relationship_builder import RelationshipBuilder
from src.entity_resolution.types import EntityType, ExtractedEntity, RelationshipExtraction

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_current_counts() -> Dict[str, int]:
    """
    Check current relationship counts and entity availability.
    
    Returns:
        Dictionary with counts and statistics
    """
    logger.info("=" * 80)
    logger.info("STEP 1: Checking Current Database State")
    logger.info("=" * 80)
    
    with get_db_session() as session:
        stats = {}
        
        # Relationship counts
        stats['publication_trial_count'] = session.query(PublicationTrial).filter(
            PublicationTrial.deleted_at.is_(None)
        ).count()
        
        stats['publication_drug_count'] = session.query(PublicationDrug).filter(
            PublicationDrug.deleted_at.is_(None)
        ).count()
        
        # Entity counts
        stats['publication_count'] = session.query(Publication).filter(
            Publication.deleted_at.is_(None),
            Publication.pmid.isnot(None)
        ).count()
        
        stats['trial_count'] = session.query(ClinicalTrial).filter(
            ClinicalTrial.deleted_at.is_(None),
            ClinicalTrial.nct_id.isnot(None)
        ).count()
        
        stats['drug_count'] = session.query(Drug).filter(
            Drug.deleted_at.is_(None)
        ).count()
        
        # Publications with NCT IDs in text
        publications_with_nct = session.query(Publication).filter(
            Publication.deleted_at.is_(None)
        ).all()
        
        nct_pattern = re.compile(r'NCT\d{8}', re.IGNORECASE)
        pubs_with_nct_ids = 0
        for pub in publications_with_nct:
            text = (pub.title or '') + ' ' + (pub.abstract or '')
            if nct_pattern.search(text):
                pubs_with_nct_ids += 1
        
        stats['publications_with_nct_ids'] = pubs_with_nct_ids
        
        # Orphaned relationships check
        orphaned_trial_rels = session.query(PublicationTrial).filter(
            PublicationTrial.deleted_at.is_(None)
        ).outerjoin(
            Publication, PublicationTrial.pub_id == Publication.pub_id
        ).outerjoin(
            ClinicalTrial, PublicationTrial.trial_id == ClinicalTrial.trial_id
        ).filter(
            (Publication.pub_id.is_(None)) | (ClinicalTrial.trial_id.is_(None))
        ).count()
        
        orphaned_drug_rels = session.query(PublicationDrug).filter(
            PublicationDrug.deleted_at.is_(None)
        ).outerjoin(
            Publication, PublicationDrug.pub_id == Publication.pub_id
        ).outerjoin(
            Drug, PublicationDrug.drug_id == Drug.drug_id
        ).filter(
            (Publication.pub_id.is_(None)) | (Drug.drug_id.is_(None))
        ).count()
        
        stats['orphaned_trial_relationships'] = orphaned_trial_rels
        stats['orphaned_drug_relationships'] = orphaned_drug_rels
        
        # Print results
        logger.info("\nRelationship Counts:")
        logger.info(f"  Publication-Trial: {stats['publication_trial_count']}")
        logger.info(f"  Publication-Drug: {stats['publication_drug_count']}")
        
        logger.info("\nEntity Counts:")
        logger.info(f"  Publications (with PMID): {stats['publication_count']}")
        logger.info(f"  Trials (with NCT ID): {stats['trial_count']}")
        logger.info(f"  Drugs: {stats['drug_count']}")
        
        logger.info("\nPublications with NCT IDs in text:")
        logger.info(f"  {stats['publications_with_nct_ids']}")
        
        logger.info("\nOrphaned Relationships:")
        logger.info(f"  Publication-Trial: {stats['orphaned_trial_relationships']}")
        logger.info(f"  Publication-Drug: {stats['orphaned_drug_relationships']}")
        
        # Analysis
        logger.info("\nAnalysis:")
        if stats['publication_trial_count'] == 0 and stats['publications_with_nct_ids'] > 0:
            logger.warning("  ⚠️  Publications with NCT IDs exist but no relationships created")
        elif stats['publication_trial_count'] > 0:
            logger.info("  ✅ Publication-Trial relationships exist")
        
        if stats['publication_drug_count'] == 0 and stats['publication_count'] > 0:
            logger.warning("  ⚠️  Publications exist but no drug relationships created")
        elif stats['publication_drug_count'] > 0:
            logger.info("  ✅ Publication-Drug relationships exist")
        
        return stats


def test_publication_trial_flow() -> bool:
    """
    Test Publication-Trial relationship creation flow.
    
    Returns:
        True if test passes, False otherwise
    """
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Testing Publication-Trial Relationship Creation Flow")
    logger.info("=" * 80)
    
    with get_db_session() as session:
        # Find a publication with NCT ID in text
        publications = session.query(Publication).filter(
            Publication.deleted_at.is_(None)
        ).all()
        
        nct_pattern = re.compile(r'NCT\d{8}', re.IGNORECASE)
        test_pub = None
        nct_ids = []
        
        for pub in publications:
            text = (pub.title or '') + ' ' + (pub.abstract or '')
            matches = nct_pattern.findall(text)
            if matches:
                test_pub = pub
                nct_ids = [m.upper() for m in matches]
                break
        
        if not test_pub:
            logger.warning("  ⚠️  No publication with NCT ID found in text")
            logger.info("  Creating test scenario...")
            
            # Find any publication and trial
            test_pub = session.query(Publication).filter(
                Publication.deleted_at.is_(None)
            ).first()
            
            test_trial = session.query(ClinicalTrial).filter(
                ClinicalTrial.deleted_at.is_(None),
                ClinicalTrial.nct_id.isnot(None)
            ).first()
            
            if not test_pub or not test_trial:
                logger.error("  ❌ Cannot create test scenario - missing publications or trials")
                return False
            
            logger.info(f"  Using publication: {test_pub.pmid} ({test_pub.title[:50]}...)")
            logger.info(f"  Using trial: {test_trial.nct_id}")
            logger.info("  Note: This test verifies the flow, not actual relationship creation")
        
        # Test entity stub creation
        from src.processors.pubmed_processor import PubMedProcessor
        processor = PubMedProcessor(session)
        
        # Simulate relationship extraction
        resolved_entities = {'publication': test_pub.pub_id}
        id_to_entity = {}
        
        # Check if processor can extract NCT IDs
        raw_data = {
            'title': test_pub.title or '',
            'abstract': test_pub.abstract or '',
            'pmid': test_pub.pmid
        }
        
        extracted_nct_ids = processor._extract_nct_ids(raw_data)
        logger.info(f"\n  Extracted NCT IDs: {extracted_nct_ids}")
        
        if extracted_nct_ids:
            # Check if trials exist for these NCT IDs
            trials = session.query(ClinicalTrial).filter(
                ClinicalTrial.nct_id.in_([nct.upper() for nct in extracted_nct_ids])
            ).all()
            
            logger.info(f"  Found {len(trials)} matching trials")
            
            if trials:
                # Test entity stub creation
                trial = trials[0]
                trial_stub = processor._make_trial_entity_stub(trial)
                logger.info(f"  Trial stub created: {trial_stub.entity_type.value} - {trial_stub.name[:50]}")
                logger.info(f"  Trial stub identifiers: {trial_stub.identifiers}")
                
                # Test relationship extraction
                relationships = processor.extract_relationships(
                    raw_data,
                    resolved_entities,
                    id_to_entity
                )
                
                pub_trial_rels = [r for r in relationships if r.relationship_type == 'publication_trial']
                logger.info(f"  Extracted {len(pub_trial_rels)} publication-trial relationships")
                
                if pub_trial_rels:
                    logger.info("  ✅ Publication-Trial relationship extraction working")
                    return True
                else:
                    logger.warning("  ⚠️  No relationships extracted despite matching trials")
                    return False
            else:
                logger.warning("  ⚠️  No trials found for extracted NCT IDs")
                return False
        else:
            logger.warning("  ⚠️  No NCT IDs extracted from publication")
            return False


def test_publication_drug_flow() -> bool:
    """
    Test Publication-Drug relationship creation flow.
    
    Returns:
        True if test passes, False otherwise
    """
    logger.info("\n" + "=" * 80)
    logger.info("STEP 3: Testing Publication-Drug Relationship Creation Flow")
    logger.info("=" * 80)
    
    with get_db_session() as session:
        # Find a publication
        test_pub = session.query(Publication).filter(
            Publication.deleted_at.is_(None)
        ).first()
        
        if not test_pub:
            logger.error("  ❌ No publications found in database")
            return False
        
        logger.info(f"  Testing with publication: {test_pub.pmid} ({test_pub.title[:50]}...)")
        
        # Test drug extraction
        from src.processors.pubmed_processor import PubMedProcessor
        processor = PubMedProcessor(session)
        
        raw_data = {
            'title': test_pub.title or '',
            'abstract': test_pub.abstract or '',
            'pmid': test_pub.pmid
        }
        
        # Extract drugs from text
        extracted_drugs = processor._extract_drugs(raw_data)
        logger.info(f"  Extracted {len(extracted_drugs)} drugs from text")
        
        if extracted_drugs:
            logger.info(f"  Sample drugs: {[d.name for d in extracted_drugs[:3]]}")
            
            # Test entity resolution
            resolver = EntityResolver(session)
            resolved_drug_ids = []
            
            for drug_entity in extracted_drugs[:3]:  # Test first 3
                resolution = resolver.resolve(drug_entity)
                if resolution.entity_id:
                    resolved_drug_ids.append(resolution.entity_id)
                    logger.info(f"  ✅ Resolved drug: {drug_entity.name} -> {resolution.entity_id}")
                else:
                    logger.info(f"  ⚠️  Could not resolve drug: {drug_entity.name} (status: {resolution.status.value})")
            
            if resolved_drug_ids:
                # Test relationship extraction
                resolved_entities = {
                    'publication': test_pub.pub_id,
                    'drugs': resolved_drug_ids
                }
                id_to_entity = {test_pub.pub_id: processor._make_publication_entity(raw_data)}
                for drug_id, drug_entity in zip(resolved_drug_ids, extracted_drugs[:len(resolved_drug_ids)]):
                    id_to_entity[drug_id] = drug_entity
                
                relationships = processor.extract_relationships(
                    raw_data,
                    resolved_entities,
                    id_to_entity
                )
                
                pub_drug_rels = [r for r in relationships if r.relationship_type == 'publication_drug']
                logger.info(f"  Extracted {len(pub_drug_rels)} publication-drug relationships")
                
                if pub_drug_rels:
                    logger.info("  ✅ Publication-Drug relationship extraction working")
                    return True
                else:
                    logger.warning("  ⚠️  No relationships extracted despite resolved drugs")
                    return False
            else:
                logger.warning("  ⚠️  No drugs could be resolved")
                return False
        else:
            logger.warning("  ⚠️  No drugs extracted from publication text")
            logger.info("  This may be normal if publication doesn't mention specific drug names")
            return None  # Not a failure, just no data


def test_cross_run_resolution() -> Tuple[bool, bool]:
    """
    Test cross-run resolution for both trials and drugs.
    
    Returns:
        Tuple of (trial_test_passed, drug_test_passed)
    """
    logger.info("\n" + "=" * 80)
    logger.info("STEP 4: Testing Cross-Run Resolution")
    logger.info("=" * 80)
    
    with get_db_session() as session:
        resolver = EntityResolver(session)
        
        # Test 1: Trial cross-run resolution
        logger.info("\n  Test 4a: Publication-Trial Cross-Run Resolution")
        trial_test_passed = False
        
        # Find an existing trial
        existing_trial = session.query(ClinicalTrial).filter(
            ClinicalTrial.deleted_at.is_(None),
            ClinicalTrial.nct_id.isnot(None)
        ).first()
        
        if existing_trial:
            logger.info(f"  Using existing trial: {existing_trial.nct_id}")
            
            # Create entity stub as if from publication processing
            trial_entity = ExtractedEntity(
                entity_type=EntityType.TRIAL,
                name=existing_trial.trial_title or f"Trial {existing_trial.nct_id}",
                identifiers={'nct_id': existing_trial.nct_id},
                context={},
                source_name='pubmed',
                source_identifier='test-cross-run'
            )
            
            # Test resolution (should find in database)
            resolution = resolver.resolve(trial_entity)
            
            if resolution.entity_id == existing_trial.trial_id:
                logger.info(f"  ✅ Trial resolved via database fallback: {resolution.entity_id}")
                logger.info(f"     Status: {resolution.status.value}")
                logger.info(f"     Method: {resolution.match_method.value if resolution.match_method else 'N/A'}")
                trial_test_passed = True
            else:
                logger.error(f"  ❌ Trial resolution failed. Expected {existing_trial.trial_id}, got {resolution.entity_id}")
        else:
            logger.warning("  ⚠️  No trials found for cross-run test")
        
        # Test 2: Drug cross-run resolution
        logger.info("\n  Test 4b: Publication-Drug Cross-Run Resolution")
        drug_test_passed = False
        
        # Find an existing drug
        existing_drug = session.query(Drug).filter(
            Drug.deleted_at.is_(None)
        ).first()
        
        if existing_drug:
            logger.info(f"  Using existing drug: {existing_drug.primary_name}")
            
            # Create entity stub as if from publication processing
            drug_entity = ExtractedEntity(
                entity_type=EntityType.DRUG,
                name=existing_drug.primary_name,
                identifiers={},
                context={},
                source_name='pubmed',
                source_identifier='test-cross-run'
            )
            
            # Test resolution (should find in database)
            resolution = resolver.resolve(drug_entity)
            
            if resolution.entity_id == existing_drug.drug_id:
                logger.info(f"  ✅ Drug resolved via database fallback: {resolution.entity_id}")
                logger.info(f"     Status: {resolution.status.value}")
                logger.info(f"     Method: {resolution.match_method.value if resolution.match_method else 'N/A'}")
                drug_test_passed = True
            else:
                logger.warning(f"  ⚠️  Drug resolution: Expected {existing_drug.drug_id}, got {resolution.entity_id if resolution.entity_id else 'None'}")
                logger.info(f"     Status: {resolution.status.value}")
        else:
            logger.warning("  ⚠️  No drugs found for cross-run test")
        
        return trial_test_passed, drug_test_passed


def verify_relationship_builder() -> bool:
    """
    Verify RelationshipBuilder correctly handles publication_trial and publication_drug.
    
    Returns:
        True if verification passes
    """
    logger.info("\n" + "=" * 80)
    logger.info("STEP 5: Verifying RelationshipBuilder Integration")
    logger.info("=" * 80)
    
    with get_db_session() as session:
        builder = RelationshipBuilder(session)
        
        # Check relationship model mappings
        logger.info("\n  Checking relationship model mappings:")
        if 'publication_trial' in builder.RELATIONSHIP_MODELS:
            model = builder.RELATIONSHIP_MODELS['publication_trial']
            logger.info(f"  ✅ publication_trial -> {model.__name__}")
        else:
            logger.error("  ❌ publication_trial not in RELATIONSHIP_MODELS")
            return False
        
        if 'publication_drug' in builder.RELATIONSHIP_MODELS:
            model = builder.RELATIONSHIP_MODELS['publication_drug']
            logger.info(f"  ✅ publication_drug -> {model.__name__}")
        else:
            logger.error("  ❌ publication_drug not in RELATIONSHIP_MODELS")
            return False
        
        # Check ID field mappings
        logger.info("\n  Checking ID field mappings:")
        pub_trial_model = builder.RELATIONSHIP_MODELS['publication_trial']
        source_field, target_field = builder._get_id_fields(pub_trial_model)
        logger.info(f"  PublicationTrial: source={source_field}, target={target_field}")
        
        if source_field == 'pub_id' and target_field == 'trial_id':
            logger.info("  ✅ PublicationTrial ID fields correct")
        else:
            logger.error(f"  ❌ PublicationTrial ID fields incorrect: expected ('pub_id', 'trial_id'), got ('{source_field}', '{target_field}')")
            return False
        
        pub_drug_model = builder.RELATIONSHIP_MODELS['publication_drug']
        source_field, target_field = builder._get_id_fields(pub_drug_model)
        logger.info(f"  PublicationDrug: source={source_field}, target={target_field}")
        
        if source_field == 'pub_id' and target_field == 'drug_id':
            logger.info("  ✅ PublicationDrug ID fields correct")
        else:
            logger.error(f"  ❌ PublicationDrug ID fields incorrect: expected ('pub_id', 'drug_id'), got ('{source_field}', '{target_field}')")
            return False
        
        return True


def check_processing_logs() -> Dict[str, any]:
    """
    Check processing logs for relationship creation counts and errors.
    
    Returns:
        Dictionary with log statistics
    """
    logger.info("\n" + "=" * 80)
    logger.info("STEP 6: Checking Processing Logs")
    logger.info("=" * 80)
    
    with get_db_session() as session:
        # Get recent publication processing logs
        pub_logs = session.query(SourceProcessingLog).filter(
            SourceProcessingLog.source_name == 'pubmed'
        ).order_by(
            SourceProcessingLog.processing_completed_at.desc()
        ).limit(10).all()
        
        logger.info(f"\n  Found {len(pub_logs)} recent PubMed processing logs")
        
        stats = {
            'total_logs': len(pub_logs),
            'successful': 0,
            'failed': 0,
            'with_relationships': 0,
            'total_relationships': 0,
            'errors': []
        }
        
        for log in pub_logs:
            if log.processing_status == 'success':
                stats['successful'] += 1
                if log.relationships_created and log.relationships_created > 0:
                    stats['with_relationships'] += 1
                    stats['total_relationships'] += (log.relationships_created or 0)
            elif log.processing_status == 'failed':
                stats['failed'] += 1
                if log.errors:
                    stats['errors'].extend(log.errors)
        
        logger.info(f"\n  Successful: {stats['successful']}")
        logger.info(f"  Failed: {stats['failed']}")
        logger.info(f"  With relationships created: {stats['with_relationships']}")
        logger.info(f"  Total relationships created: {stats['total_relationships']}")
        
        if stats['errors']:
            logger.warning(f"\n  Errors found: {len(stats['errors'])}")
            for error in stats['errors'][:5]:  # Show first 5
                logger.warning(f"    - {error}")
        
        return stats


def diagnose_issues(stats: Dict) -> List[str]:
    """
    Identify blocking issues based on verification results.
    
    Args:
        stats: Statistics from previous checks
        
    Returns:
        List of identified issues
    """
    logger.info("\n" + "=" * 80)
    logger.info("STEP 7: Diagnosing Issues")
    logger.info("=" * 80)
    
    issues = []
    recommendations = []
    
    # Check relationship counts
    if stats.get('publication_trial_count', 0) == 0:
        if stats.get('publications_with_nct_ids', 0) > 0:
            issues.append("Publications with NCT IDs exist but no Publication-Trial relationships created")
            recommendations.append("Check if NCT ID extraction is working in pubmed_processor")
            recommendations.append("Verify trials exist in database for extracted NCT IDs")
            recommendations.append("Check if hybrid resolver is being invoked for trial entity stubs")
        elif stats.get('trial_count', 0) == 0:
            issues.append("No trials in database - cannot create Publication-Trial relationships")
            recommendations.append("Process some clinical trials first: python -m src.cli ingest --source clinicaltrials --limit 10")
        elif stats.get('publication_count', 0) == 0:
            issues.append("No publications in database - cannot create Publication-Trial relationships")
            recommendations.append("Process some publications first: python -m src.cli ingest --source pubmed --limit 10")
    
    if stats.get('publication_drug_count', 0) == 0:
        if stats.get('publication_count', 0) > 0:
            issues.append("Publications exist but no Publication-Drug relationships created")
            recommendations.append("Check if drug name extraction is working in pubmed_processor")
            recommendations.append("Verify drugs are being resolved from database (cross-run resolution)")
            recommendations.append("Check if drugs are mentioned in publication text")
        elif stats.get('drug_count', 0) == 0:
            issues.append("No drugs in database - cannot create Publication-Drug relationships")
            recommendations.append("Process some drug sources first (clinicaltrials, fda_drugs, etc.)")
        elif stats.get('publication_count', 0) == 0:
            issues.append("No publications in database - cannot create Publication-Drug relationships")
            recommendations.append("Process some publications first: python -m src.cli ingest --source pubmed --limit 10")
    
    # Check orphaned relationships
    if stats.get('orphaned_trial_relationships', 0) > 0:
        issues.append(f"{stats['orphaned_trial_relationships']} orphaned Publication-Trial relationships found")
        recommendations.append("Clean up orphaned relationships - entities may have been deleted")
    
    if stats.get('orphaned_drug_relationships', 0) > 0:
        issues.append(f"{stats['orphaned_drug_relationships']} orphaned Publication-Drug relationships found")
        recommendations.append("Clean up orphaned relationships - entities may have been deleted")
    
    # Check processing logs
    log_stats = stats.get('log_stats', {})
    if log_stats.get('with_relationships', 0) == 0 and log_stats.get('successful', 0) > 0:
        issues.append("Processing logs show successful runs but no relationships created")
        recommendations.append("Check relationship extraction logic in pubmed_processor.extract_relationships()")
        recommendations.append("Verify entities are being resolved before relationship extraction")
    
    if log_stats.get('failed', 0) > 0:
        issues.append(f"{log_stats['failed']} failed processing runs found")
        recommendations.append("Review error logs to identify processing failures")
        if log_stats.get('errors'):
            logger.warning("  Recent errors:")
            for error in log_stats['errors'][:3]:
                logger.warning(f"    - {error}")
    
    if issues:
        logger.warning("\n  Identified Issues:")
        for i, issue in enumerate(issues, 1):
            logger.warning(f"    {i}. {issue}")
        
        if recommendations:
            logger.info("\n  Recommendations:")
            for i, rec in enumerate(recommendations, 1):
                logger.info(f"    {i}. {rec}")
    else:
        logger.info("\n  ✅ No blocking issues identified")
    
    return issues


def generate_report(stats: Dict, issues: List[str]) -> None:
    """
    Generate final verification report.
    
    Args:
        stats: All collected statistics
        issues: List of identified issues
    """
    logger.info("\n" + "=" * 80)
    logger.info("VERIFICATION REPORT")
    logger.info("=" * 80)
    
    logger.info("\nSummary:")
    logger.info(f"  Publication-Trial relationships: {stats.get('publication_trial_count', 0)}")
    logger.info(f"  Publication-Drug relationships: {stats.get('publication_drug_count', 0)}")
    
    logger.info("\nStatus:")
    if stats.get('publication_trial_count', 0) > 0:
        logger.info("  ✅ Publication-Trial relationships are populating")
    else:
        logger.warning("  ⚠️  Publication-Trial relationships are NOT populating")
    
    if stats.get('publication_drug_count', 0) > 0:
        logger.info("  ✅ Publication-Drug relationships are populating")
    else:
        logger.warning("  ⚠️  Publication-Drug relationships are NOT populating")
    
    if issues:
        logger.warning(f"\n⚠️  {len(issues)} issue(s) identified - see diagnosis above")
    else:
        logger.info("\n✅ No blocking issues found")


def main():
    """Run all verification steps."""
    logger.info("\n" + "=" * 80)
    logger.info("PUBLICATION RELATIONSHIP VERIFICATION")
    logger.info("=" * 80 + "\n")
    
    # Step 1: Check current counts
    stats = check_current_counts()
    
    # Step 2: Test relationship creation flows
    trial_flow_ok = test_publication_trial_flow()
    drug_flow_ok = test_publication_drug_flow()
    
    # Step 3: Test cross-run resolution
    trial_cross_run, drug_cross_run = test_cross_run_resolution()
    
    # Step 4: Verify RelationshipBuilder
    builder_ok = verify_relationship_builder()
    
    # Step 5: Check processing logs
    log_stats = check_processing_logs()
    stats['log_stats'] = log_stats
    
    # Step 6: Diagnose issues
    issues = diagnose_issues(stats)
    
    # Step 7: Generate report
    generate_report(stats, issues)
    
    # Return exit code
    if stats.get('publication_trial_count', 0) > 0 and stats.get('publication_drug_count', 0) > 0:
        return 0
    elif not issues:
        return 0  # No issues, just no data yet
    else:
        return 1  # Issues found


if __name__ == '__main__':
    sys.exit(main())


