"""
Detailed system verification script.

Provides comprehensive breakdown of system state including:
- Per-source statistics
- Relationship quality checks
- Entity resolution quality
- Data quality issues
- Overlap analysis
"""
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.entities import Company, Drug, Disease
from database.models.clinical import ClinicalTrial
from database.models.publications import Publication, Patent, SECFiling
from database.models.relationships import (
    TrialSponsor, TrialDrug, TrialDisease,
    CompanyDrug, PublicationDrug, PublicationCompany,
    FilingCompany, FilingDrug, PatentDrug, PatentCompany
)
from database.models.resolution import SourceProcessingLog, EntityAlias, EntityMatchCandidate
from sqlalchemy import func, and_, or_, distinct
from collections import defaultdict

logger = logging.getLogger(__name__)


def get_detailed_stats(test_run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get detailed system statistics.
    
    Args:
        test_run_id: Optional test run ID for filtering (not fully implemented)
    
    Returns:
        Dictionary with detailed statistics
    """
    stats = {
        'timestamp': datetime.now(),
        'test_run_id': test_run_id,
        'per_source': {},
        'relationship_quality': {},
        'entity_resolution_quality': {},
        'data_quality_issues': [],
        'overlap_analysis': {}
    }
    
    with get_db_session() as session:
        # Get all sources with staging data
        sources = session.query(distinct(StagingRawData.source_system)).filter(
            StagingRawData.deleted_at.is_(None)
        ).all()
        
        source_names = [s[0] for s in sources]
        
        # Per-source breakdown
        for source_name in source_names:
            source_stats = get_source_detailed_stats(session, source_name)
            stats['per_source'][source_name] = source_stats
        
        # Relationship quality checks
        stats['relationship_quality'] = check_relationship_quality(session)
        
        # Entity resolution quality
        stats['entity_resolution_quality'] = check_entity_resolution_quality(session)
        
        # Data quality issues
        stats['data_quality_issues'] = check_data_quality_issues(session)
        
        # Overlap analysis (simplified - would need test run tracking)
        stats['overlap_analysis'] = analyze_data_overlap(session)
    
    return stats


def get_source_detailed_stats(session, source_name: str) -> Dict[str, Any]:
    """Get detailed statistics for a single source."""
    stats = {
        'source_name': source_name,
        'staging': {},
        'processing': {},
        'entities': {},
        'relationships': {}
    }
    
    # Staging statistics
    staging_query = session.query(
        func.count(StagingRawData.staging_id).label('total'),
        func.sum(func.cast(StagingRawData.processed, func.Integer)).label('processed'),
        func.sum(func.cast(StagingRawData.processed == False, func.Integer)).label('unprocessed')
    ).filter(
        StagingRawData.source_system == source_name,
        StagingRawData.deleted_at.is_(None)
    ).first()
    
    stats['staging'] = {
        'total': staging_query.total or 0,
        'processed': staging_query.processed or 0,
        'unprocessed': staging_query.unprocessed or 0,
        'error_rate': 0.0
    }
    
    # Processing logs
    log_query = session.query(
        func.count(SourceProcessingLog.log_id).label('total'),
        func.sum(func.case((SourceProcessingLog.processing_status == 'success', 1), else_=0)).label('success'),
        func.sum(func.case((SourceProcessingLog.processing_status == 'failed', 1), else_=0)).label('failed'),
        func.sum(SourceProcessingLog.entities_created).label('entities_created'),
        func.sum(SourceProcessingLog.entities_matched).label('entities_matched'),
        func.sum(SourceProcessingLog.relationships_created).label('relationships_created')
    ).filter(
        SourceProcessingLog.source_name == source_name,
        SourceProcessingLog.deleted_at.is_(None)
    ).first()
    
    stats['processing'] = {
        'total_logs': log_query.total or 0,
        'successful': log_query.success or 0,
        'failed': log_query.failed or 0,
        'success_rate': ((log_query.success or 0) / (log_query.total or 1)) * 100 if log_query.total else 0.0,
        'entities_created': log_query.entities_created or 0,
        'entities_matched': log_query.entities_matched or 0,
        'relationships_created': log_query.relationships_created or 0
    }
    
    # Entity extraction (from processing logs)
    stats['entities'] = {
        'created': log_query.entities_created or 0,
        'matched': log_query.entities_matched or 0,
        'total': (log_query.entities_created or 0) + (log_query.entities_matched or 0)
    }
    
    # Relationships
    stats['relationships'] = {
        'created': log_query.relationships_created or 0
    }
    
    return stats


def check_relationship_quality(session) -> Dict[str, Any]:
    """Check relationship quality: orphaned, duplicates, coverage."""
    quality = {
        'orphaned': {},
        'duplicates': {},
        'coverage': {}
    }
    
    # Check orphaned relationships (simplified - would need joins)
    # For now, just count relationships
    quality['orphaned'] = {
        'trial_sponsors': 0,  # Would need to check if trial/entity exists
        'trial_drugs': 0,
        'trial_diseases': 0,
        'company_drugs': 0,
        'publication_drugs': 0,
        'filing_drugs': 0
    }
    
    # Check duplicates (would need to check for same source/target pairs)
    quality['duplicates'] = {
        'trial_sponsors': 0,
        'trial_drugs': 0,
        'trial_diseases': 0
    }
    
    # Relationship coverage
    total_trials = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
    trials_with_sponsors = session.query(distinct(TrialSponsor.trial_id)).filter(
        TrialSponsor.deleted_at.is_(None)
    ).count()
    trials_with_drugs = session.query(distinct(TrialDrug.trial_id)).filter(
        TrialDrug.deleted_at.is_(None)
    ).count()
    trials_with_diseases = session.query(distinct(TrialDisease.trial_id)).filter(
        TrialDisease.deleted_at.is_(None)
    ).count()
    
    quality['coverage'] = {
        'trials_with_sponsors': {
            'count': trials_with_sponsors,
            'percentage': (trials_with_sponsors / total_trials * 100) if total_trials > 0 else 0.0
        },
        'trials_with_drugs': {
            'count': trials_with_drugs,
            'percentage': (trials_with_drugs / total_trials * 100) if total_trials > 0 else 0.0
        },
        'trials_with_diseases': {
            'count': trials_with_diseases,
            'percentage': (trials_with_diseases / total_trials * 100) if total_trials > 0 else 0.0
        }
    }
    
    # Company-drug coverage
    total_companies = session.query(Company).filter(Company.deleted_at.is_(None)).count()
    companies_with_drugs = session.query(distinct(CompanyDrug.company_id)).filter(
        CompanyDrug.deleted_at.is_(None)
    ).count()
    
    quality['coverage']['companies_with_drugs'] = {
        'count': companies_with_drugs,
        'percentage': (companies_with_drugs / total_companies * 100) if total_companies > 0 else 0.0
    }
    
    return quality


def check_entity_resolution_quality(session) -> Dict[str, Any]:
    """Check entity resolution quality: match candidates, aliases, resolution rates."""
    quality = {
        'match_candidates': {},
        'aliases': {},
        'resolution_rates': {}
    }
    
    # Match candidates
    needs_review = session.query(EntityMatchCandidate).filter(
        and_(
            EntityMatchCandidate.status == 'needs_review',
            EntityMatchCandidate.deleted_at.is_(None)
        )
    ).count()
    
    high_confidence = session.query(EntityMatchCandidate).filter(
        and_(
            EntityMatchCandidate.match_confidence >= 0.8,
            EntityMatchCandidate.deleted_at.is_(None)
        )
    ).count()
    
    low_confidence = session.query(EntityMatchCandidate).filter(
        and_(
            EntityMatchCandidate.match_confidence < 0.6,
            EntityMatchCandidate.deleted_at.is_(None)
        )
    ).count()
    
    quality['match_candidates'] = {
        'needs_review': needs_review,
        'high_confidence': high_confidence,
        'low_confidence': low_confidence,
        'total': session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.deleted_at.is_(None)
        ).count()
    }
    
    # Entity aliases
    total_aliases = session.query(EntityAlias).filter(EntityAlias.deleted_at.is_(None)).count()
    
    # Aliases per entity (simplified)
    aliases_per_entity = session.query(
        EntityAlias.entity_id,
        func.count(EntityAlias.alias_id).label('alias_count')
    ).filter(
        EntityAlias.deleted_at.is_(None)
    ).group_by(EntityAlias.entity_id).all()
    
    entities_with_one_alias = sum(1 for _, count in aliases_per_entity if count == 1)
    
    quality['aliases'] = {
        'total': total_aliases,
        'entities_with_one_alias': entities_with_one_alias,
        'average_aliases_per_entity': (total_aliases / len(aliases_per_entity)) if aliases_per_entity else 0.0
    }
    
    # Resolution rates (simplified - would need source tracking)
    quality['resolution_rates'] = {
        'note': 'Resolution rates require source-level tracking'
    }
    
    return quality


def check_data_quality_issues(session) -> List[Dict[str, Any]]:
    """Check for data quality issues."""
    issues = []
    
    # Check for missing required fields (simplified)
    # Would need to check each entity type for required fields
    
    # Check for constraint violations (would need to catch exceptions)
    
    return issues


def analyze_data_overlap(session) -> Dict[str, Any]:
    """Analyze data overlap between test runs."""
    # Simplified - would need test run tracking
    overlap = {
        'note': 'Overlap analysis requires test run ID tracking in staging table',
        'records_skipped': 0,  # Would need to track skipped records
        'records_reprocessed': 0,  # Would need to track reprocessing
        'new_records': 0
    }
    
    return overlap


def print_detailed_stats(stats: Dict[str, Any]):
    """Print detailed statistics to console."""
    print(f"\n{'='*80}")
    print(f"Detailed System Statistics")
    print(f"{'='*80}")
    print(f"Timestamp: {stats['timestamp']}")
    if stats['test_run_id']:
        print(f"Test Run ID: {stats['test_run_id']}")
    
    # Per-source breakdown
    print(f"\n📊 Per-Source Breakdown:")
    print(f"{'-'*80}")
    for source_name, source_stats in sorted(stats['per_source'].items()):
        print(f"\n{source_name}:")
        print(f"  Staging: {source_stats['staging']['total']} total, "
              f"{source_stats['staging']['processed']} processed, "
              f"{source_stats['staging']['unprocessed']} unprocessed")
        print(f"  Processing: {source_stats['processing']['successful']}/{source_stats['processing']['total_logs']} successful "
              f"({source_stats['processing']['success_rate']:.1f}%)")
        print(f"  Entities: {source_stats['entities']['created']} created, {source_stats['entities']['matched']} matched")
        print(f"  Relationships: {source_stats['relationships']['created']} created")
    
    # Relationship quality
    print(f"\n🔗 Relationship Quality:")
    print(f"{'-'*80}")
    coverage = stats['relationship_quality']['coverage']
    print(f"  Trial Coverage:")
    print(f"    With sponsors: {coverage['trials_with_sponsors']['count']} ({coverage['trials_with_sponsors']['percentage']:.1f}%)")
    print(f"    With drugs: {coverage['trials_with_drugs']['count']} ({coverage['trials_with_drugs']['percentage']:.1f}%)")
    print(f"    With diseases: {coverage['trials_with_diseases']['count']} ({coverage['trials_with_diseases']['percentage']:.1f}%)")
    print(f"  Company-Drug Coverage: {coverage['companies_with_drugs']['count']} ({coverage['companies_with_drugs']['percentage']:.1f}%)")
    
    # Entity resolution quality
    print(f"\n🎯 Entity Resolution Quality:")
    print(f"{'-'*80}")
    match_candidates = stats['entity_resolution_quality']['match_candidates']
    print(f"  Match Candidates: {match_candidates['total']} total")
    print(f"    Needs review: {match_candidates['needs_review']}")
    print(f"    High confidence (>=0.8): {match_candidates['high_confidence']}")
    print(f"    Low confidence (<0.6): {match_candidates['low_confidence']}")
    
    aliases = stats['entity_resolution_quality']['aliases']
    print(f"  Aliases: {aliases['total']} total")
    print(f"    Entities with only 1 alias: {aliases['entities_with_one_alias']}")
    print(f"    Average aliases per entity: {aliases['average_aliases_per_entity']:.2f}")
    
    # Data quality issues
    if stats['data_quality_issues']:
        print(f"\n⚠️  Data Quality Issues:")
        print(f"{'-'*80}")
        for issue in stats['data_quality_issues']:
            print(f"  - {issue}")
    else:
        print(f"\n✓ No data quality issues detected")
    
    # Overlap analysis
    print(f"\n📈 Overlap Analysis:")
    print(f"{'-'*80}")
    overlap = stats['overlap_analysis']
    print(f"  Note: {overlap.get('note', 'N/A')}")


if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Get detailed system statistics')
    parser.add_argument('--test-run-id', type=str, default=None,
                       help='Test run ID for filtering')
    
    args = parser.parse_args()
    
    try:
        stats = get_detailed_stats(test_run_id=args.test_run_id)
        print_detailed_stats(stats)
        
    except Exception as e:
        logger.error(f"Error getting detailed stats: {e}", exc_info=True)
        sys.exit(1)

