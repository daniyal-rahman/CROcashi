"""
Basic system verification script.

Provides quick overview of system state: entity counts, relationship counts, processing status.
"""
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional
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
from database.models.resolution import SourceProcessingLog
from sqlalchemy import func, and_, cast, Integer

logger = logging.getLogger(__name__)


def get_basic_stats(test_run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get basic system statistics.
    
    Args:
        test_run_id: Optional test run ID for filtering (not implemented yet)
    
    Returns:
        Dictionary with basic statistics
    """
    stats = {
        'timestamp': datetime.now(),
        'test_run_id': test_run_id,
        'staging': {},
        'entities': {},
        'relationships': {},
        'processing': {},
        'top_sources': {}
    }
    
    with get_db_session() as session:
        # Staging statistics
        staging_total = session.query(StagingRawData).filter(
            StagingRawData.deleted_at.is_(None)
        ).count()
        
        staging_processed = session.query(StagingRawData).filter(
            and_(
                StagingRawData.processed == True,
                StagingRawData.deleted_at.is_(None)
            )
        ).count()
        
        staging_unprocessed = staging_total - staging_processed
        
        # Staging by source
        staging_by_source = session.query(
            StagingRawData.source_system,
            func.count(StagingRawData.staging_id).label('total'),
            func.sum(cast(StagingRawData.processed, Integer)).label('processed')
        ).filter(
            StagingRawData.deleted_at.is_(None)
        ).group_by(StagingRawData.source_system).all()
        
        stats['staging'] = {
            'total': staging_total,
            'processed': staging_processed,
            'unprocessed': staging_unprocessed,
            'by_source': {
                source: {'total': total, 'processed': processed or 0}
                for source, total, processed in staging_by_source
            }
        }
        
        # Entity counts
        stats['entities'] = {
            'companies': session.query(Company).filter(Company.deleted_at.is_(None)).count(),
            'drugs': session.query(Drug).filter(Drug.deleted_at.is_(None)).count(),
            'diseases': session.query(Disease).filter(Disease.deleted_at.is_(None)).count(),
            'trials': session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count(),
            'publications': session.query(Publication).filter(Publication.deleted_at.is_(None)).count(),
            'patents': session.query(Patent).filter(Patent.deleted_at.is_(None)).count(),
            'filings': session.query(SECFiling).filter(SECFiling.deleted_at.is_(None)).count(),
        }
        
        # Relationship counts
        stats['relationships'] = {
            'trial_sponsors': session.query(TrialSponsor).filter(TrialSponsor.deleted_at.is_(None)).count(),
            'trial_drugs': session.query(TrialDrug).filter(TrialDrug.deleted_at.is_(None)).count(),
            'trial_diseases': session.query(TrialDisease).filter(TrialDisease.deleted_at.is_(None)).count(),
            'company_drugs': session.query(CompanyDrug).filter(CompanyDrug.deleted_at.is_(None)).count(),
            'publication_drugs': session.query(PublicationDrug).filter(PublicationDrug.deleted_at.is_(None)).count(),
            'publication_companies': session.query(PublicationCompany).filter(PublicationCompany.deleted_at.is_(None)).count(),
            'filing_companies': session.query(FilingCompany).filter(FilingCompany.deleted_at.is_(None)).count(),
            'filing_drugs': session.query(FilingDrug).filter(FilingDrug.deleted_at.is_(None)).count(),
            'patent_drugs': session.query(PatentDrug).filter(PatentDrug.deleted_at.is_(None)).count(),
            'patent_companies': session.query(PatentCompany).filter(PatentCompany.deleted_at.is_(None)).count(),
        }
        
        # Processing statistics
        processing_total = session.query(SourceProcessingLog).filter(
            SourceProcessingLog.deleted_at.is_(None)
        ).count()
        
        processing_success = session.query(SourceProcessingLog).filter(
            and_(
                SourceProcessingLog.processing_status == 'success',
                SourceProcessingLog.deleted_at.is_(None)
            )
        ).count()
        
        processing_failed = session.query(SourceProcessingLog).filter(
            and_(
                SourceProcessingLog.processing_status == 'failed',
                SourceProcessingLog.deleted_at.is_(None)
            )
        ).count()
        
        # Processing by source
        from sqlalchemy import case
        processing_by_source = session.query(
            SourceProcessingLog.source_name,
            func.count(SourceProcessingLog.log_id).label('total'),
            func.sum(case((SourceProcessingLog.processing_status == 'success', 1), else_=0)).label('success'),
            func.sum(SourceProcessingLog.entities_created).label('entities_created'),
            func.sum(SourceProcessingLog.relationships_created).label('relationships_created')
        ).filter(
            SourceProcessingLog.deleted_at.is_(None)
        ).group_by(SourceProcessingLog.source_name).all()
        
        stats['processing'] = {
            'total': processing_total,
            'success': processing_success,
            'failed': processing_failed,
            'success_rate': (processing_success / processing_total * 100) if processing_total > 0 else 0.0,
            'by_source': {
                source: {
                    'total': total,
                    'success': success or 0,
                    'entities_created': entities_created or 0,
                    'relationships_created': relationships_created or 0
                }
                for source, total, success, entities_created, relationships_created in processing_by_source
            }
        }
        
        # Top sources by entity count
        top_entities = sorted(
            processing_by_source,
            key=lambda x: x[3] or 0,  # entities_created
            reverse=True
        )[:10]
        
        stats['top_sources'] = {
            'by_entities': [
                {
                    'source': source,
                    'entities_created': entities_created or 0,
                    'relationships_created': relationships_created or 0
                }
                for source, _, _, entities_created, relationships_created in top_entities
            ],
            'by_relationships': sorted(
                [
                    {
                        'source': source,
                        'entities_created': entities_created or 0,
                        'relationships_created': relationships_created or 0
                    }
                    for source, _, _, entities_created, relationships_created in processing_by_source
                ],
                key=lambda x: x['relationships_created'],
                reverse=True
            )[:10]
        }
    
    return stats


def print_basic_stats(stats: Dict[str, Any]):
    """Print basic statistics to console."""
    print(f"\n{'='*60}")
    print(f"Basic System Statistics")
    print(f"{'='*60}")
    print(f"Timestamp: {stats['timestamp']}")
    if stats['test_run_id']:
        print(f"Test Run ID: {stats['test_run_id']}")
    
    print(f"\n📊 Staging Records:")
    print(f"  Total: {stats['staging']['total']:,}")
    print(f"  Processed: {stats['staging']['processed']:,}")
    print(f"  Unprocessed: {stats['staging']['unprocessed']:,}")
    
    print(f"\n📦 Entities:")
    for entity_type, count in stats['entities'].items():
        print(f"  {entity_type}: {count:,}")
    
    print(f"\n🔗 Relationships:")
    for rel_type, count in stats['relationships'].items():
        print(f"  {rel_type}: {count:,}")
    
    print(f"\n⚙️  Processing:")
    print(f"  Total logs: {stats['processing']['total']:,}")
    print(f"  Successful: {stats['processing']['success']:,}")
    print(f"  Failed: {stats['processing']['failed']:,}")
    print(f"  Success rate: {stats['processing']['success_rate']:.1f}%")
    
    print(f"\n🏆 Top 10 Sources by Entities:")
    for i, source in enumerate(stats['top_sources']['by_entities'], 1):
        print(f"  {i}. {source['source']}: {source['entities_created']:,} entities, {source['relationships_created']:,} relationships")
    
    print(f"\n🏆 Top 10 Sources by Relationships:")
    for i, source in enumerate(stats['top_sources']['by_relationships'], 1):
        print(f"  {i}. {source['source']}: {source['relationships_created']:,} relationships, {source['entities_created']:,} entities")


if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Get basic system statistics')
    parser.add_argument('--test-run-id', type=str, default=None,
                       help='Test run ID for filtering')
    
    args = parser.parse_args()
    
    try:
        stats = get_basic_stats(test_run_id=args.test_run_id)
        print_basic_stats(stats)
        
    except Exception as e:
        logger.error(f"Error getting basic stats: {e}", exc_info=True)
        sys.exit(1)

