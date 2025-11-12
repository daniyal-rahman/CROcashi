"""
Source health check script.

Reports on the health of each source including:
- Last ingestion date
- Staging record count
- Processing success rate
- Entity creation rate
- Relationship creation rate
"""
import sys
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.sources import Source
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from sqlalchemy import func


def get_source_health(source_name: str, session) -> Dict[str, Any]:
    """Get health metrics for a source."""
    health = {
        'source_name': source_name,
        'last_ingestion': None,
        'staging_records': 0,
        'processed_records': 0,
        'unprocessed_records': 0,
        'processing_logs': 0,
        'successful_runs': 0,
        'failed_runs': 0,
        'total_entities_created': 0,
        'total_entities_matched': 0,
        'total_relationships_created': 0,
        'success_rate': 0.0,
        'entity_creation_rate': 0.0,
        'relationship_creation_rate': 0.0
    }
    
    # Get staging records
    staging_stats = session.query(
        func.count(StagingRawData.staging_id).label('total'),
        func.sum(func.cast(StagingRawData.processed, func.Integer)).label('processed'),
        func.max(StagingRawData.ingested_at).label('last_ingested')
    ).filter(
        StagingRawData.source_system == source_name,
        StagingRawData.deleted_at.is_(None)
    ).first()
    
    if staging_stats:
        health['staging_records'] = staging_stats.total or 0
        health['processed_records'] = staging_stats.processed or 0
        health['unprocessed_records'] = health['staging_records'] - health['processed_records']
        health['last_ingestion'] = staging_stats.last_ingested
    
    # Get processing logs
    log_stats = session.query(
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
    
    if log_stats:
        health['processing_logs'] = log_stats.total or 0
        health['successful_runs'] = log_stats.success or 0
        health['failed_runs'] = log_stats.failed or 0
        health['total_entities_created'] = log_stats.entities_created or 0
        health['total_entities_matched'] = log_stats.entities_matched or 0
        health['total_relationships_created'] = log_stats.relationships_created or 0
        
        if health['processing_logs'] > 0:
            health['success_rate'] = (health['successful_runs'] / health['processing_logs']) * 100
        
        if health['processed_records'] > 0:
            health['entity_creation_rate'] = (health['total_entities_created'] / health['processed_records']) * 100
            health['relationship_creation_rate'] = (health['total_relationships_created'] / health['processed_records']) * 100
    
    return health


def generate_health_report(active_only: bool = False) -> List[Dict[str, Any]]:
    """Generate health report for all sources."""
    with get_db_session() as session:
        # Get sources
        query = session.query(Source).filter(Source.deleted_at.is_(None))
        if active_only:
            query = query.filter(Source.is_active == True)
        
        sources = query.order_by(Source.source_name).all()
        
        health_reports = []
        for source in sources:
            health = get_source_health(source.source_name, session)
            health['is_active'] = source.is_active
            health['source_type'] = source.source_type
            health_reports.append(health)
        
        return health_reports


def print_health_report(reports: List[Dict[str, Any]]):
    """Print formatted health report."""
    print("="*100)
    print("Source Health Report")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100)
    print()
    
    # Summary statistics
    total_sources = len(reports)
    active_sources = sum(1 for r in reports if r['is_active'])
    sources_with_data = sum(1 for r in reports if r['staging_records'] > 0)
    sources_processed = sum(1 for r in reports if r['processed_records'] > 0)
    
    print("Summary:")
    print(f"  Total sources: {total_sources}")
    print(f"  Active sources: {active_sources}")
    print(f"  Sources with staging data: {sources_with_data}")
    print(f"  Sources with processed data: {sources_processed}")
    print()
    
    # Detailed report
    print("Detailed Report:")
    print("-" * 100)
    print(f"{'Source Name':<30} {'Status':<8} {'Staging':<10} {'Processed':<10} {'Success%':<10} {'Entities':<10} {'Relations':<10}")
    print("-" * 100)
    
    for report in sorted(reports, key=lambda x: x['source_name']):
        status = "ACTIVE" if report['is_active'] else "INACTIVE"
        staging = f"{report['staging_records']:,}"
        processed = f"{report['processed_records']:,}"
        success = f"{report['success_rate']:.1f}%" if report['processing_logs'] > 0 else "N/A"
        entities = f"{report['total_entities_created']:,}"
        relations = f"{report['total_relationships_created']:,}"
        
        print(f"{report['source_name']:<30} {status:<8} {staging:<10} {processed:<10} {success:<10} {entities:<10} {relations:<10}")
    
    print()
    
    # Sources needing attention
    print("Sources Needing Attention:")
    print("-" * 100)
    
    issues = []
    for report in reports:
        if report['is_active'] and report['staging_records'] == 0:
            issues.append(f"  ⚠️  {report['source_name']}: Active but no staging data")
        elif report['is_active'] and report['unprocessed_records'] > 100:
            issues.append(f"  ⚠️  {report['source_name']}: {report['unprocessed_records']:,} unprocessed records")
        elif report['processing_logs'] > 0 and report['success_rate'] < 50:
            issues.append(f"  ⚠️  {report['source_name']}: Low success rate ({report['success_rate']:.1f}%)")
    
    if issues:
        for issue in issues:
            print(issue)
    else:
        print("  ✓ No issues detected")
    
    print()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate source health report')
    parser.add_argument('--active-only', action='store_true',
                       help='Only show active sources')
    args = parser.parse_args()
    
    try:
        reports = generate_health_report(active_only=args.active_only)
        print_health_report(reports)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

