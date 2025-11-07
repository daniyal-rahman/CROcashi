#!/usr/bin/env python3
"""
Monitoring dashboard for processing pipeline.

Displays:
- Processing stats by source
- Entity resolution stats
- Relationship stats
- Data quality metrics
"""
import argparse
from datetime import datetime, timedelta

from sqlalchemy import func

from database.config import get_db_session
from database.models import (
    SourceProcessingLog, EntityMatchCandidate, Company, Drug,
    Disease, ClinicalTrial, CompanyDrug, TrialDrug, TrialDisease
)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Monitor processing pipeline"
    )
    parser.add_argument(
        '--source',
        type=str,
        help='Filter by source name'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Show stats for last N days'
    )
    
    args = parser.parse_args()
    
    with get_db_session() as session:
        show_dashboard(session, args.source, args.days)


def show_dashboard(session, source_filter=None, days=7):
    """Display monitoring dashboard."""
    cutoff_date = (datetime.now() - timedelta(days=days)).date()
    
    print("\n" + "=" * 80)
    print(f"PROCESSING PIPELINE DASHBOARD (Last {days} days)")
    print("=" * 80)
    
    # Processing stats by source
    show_processing_stats(session, cutoff_date, source_filter)
    
    # Entity resolution stats
    show_resolution_stats(session, cutoff_date)
    
    # Relationship stats
    show_relationship_stats(session)
    
    # Data quality metrics
    show_data_quality(session)
    
    # Review queue status
    show_review_queue(session)
    
    print("=" * 80 + "\n")


def show_processing_stats(session, cutoff_date, source_filter=None):
    """Show processing statistics by source."""
    print("\n## PROCESSING STATS BY SOURCE")
    print("-" * 80)
    
    query = session.query(
        SourceProcessingLog.source_name,
        SourceProcessingLog.processing_status,
        func.count(SourceProcessingLog.log_id).label('count'),
        func.avg(SourceProcessingLog.entities_extracted).label('avg_entities'),
        func.avg(SourceProcessingLog.entities_matched).label('avg_matched'),
        func.avg(SourceProcessingLog.relationships_created).label('avg_relationships')
    ).filter(
        SourceProcessingLog.processing_started_at >= cutoff_date
    )
    
    if source_filter:
        query = query.filter(SourceProcessingLog.source_name == source_filter)
    
    query = query.group_by(
        SourceProcessingLog.source_name,
        SourceProcessingLog.processing_status
    )
    
    results = query.all()
    
    if not results:
        print("No processing records found.")
        return
    
    current_source = None
    for row in results:
        if current_source != row.source_name:
            if current_source:
                print()
            current_source = row.source_name
            print(f"\n{row.source_name}:")
        
        print(f"  {row.processing_status:15s}: {row.count:5d} records")
        if row.avg_entities:
            print(f"    Avg entities: {row.avg_entities:.1f}, " +
                  f"matched: {row.avg_matched or 0:.1f}, " +
                  f"relationships: {row.avg_relationships or 0:.1f}")


def show_resolution_stats(session, cutoff_date):
    """Show entity resolution statistics."""
    print("\n## ENTITY RESOLUTION STATS")
    print("-" * 80)
    
    # Count by status
    query = session.query(
        EntityMatchCandidate.status,
        func.count(EntityMatchCandidate.candidate_id)
    ).filter(
        EntityMatchCandidate.created_at >= cutoff_date
    ).group_by(EntityMatchCandidate.status)
    
    results = query.all()
    
    total = sum(count for _, count in results)
    
    print(f"\nTotal candidates: {total}")
    for status, count in results:
        pct = (count / total * 100) if total > 0 else 0
        print(f"  {status:20s}: {count:5d} ({pct:5.1f}%)")
    
    # Auto-match rate
    auto_matched = sum(count for status, count in results if status == 'auto_matched')
    if total > 0:
        auto_match_rate = (auto_matched / total * 100)
        print(f"\nAuto-match rate: {auto_match_rate:.1f}%")


def show_relationship_stats(session):
    """Show relationship statistics."""
    print("\n## RELATIONSHIP STATS")
    print("-" * 80)
    
    # Count relationships by type
    relationships = [
        ('Company-Drug', CompanyDrug),
        ('Trial-Drug', TrialDrug),
        ('Trial-Disease', TrialDisease),
    ]
    
    for name, model in relationships:
        count = session.query(func.count()).select_from(model).scalar()
        print(f"{name:25s}: {count:8d}")


def show_data_quality(session):
    """Show data quality metrics."""
    print("\n## DATA QUALITY")
    print("-" * 80)
    
    # Entity counts
    entity_counts = [
        ('Companies', Company),
        ('Drugs', Drug),
        ('Diseases', Disease),
        ('Clinical Trials', ClinicalTrial),
    ]
    
    print("\nEntity Counts:")
    for name, model in entity_counts:
        count = session.query(func.count()).select_from(model).scalar()
        print(f"  {name:20s}: {count:8d}")
    
    # Entities with multiple sources
    print("\nMulti-Source Coverage:")
    for name, model in entity_counts:
        if not hasattr(model, 'data_sources'):
            continue
        
        total = session.query(func.count()).select_from(model).scalar()
        
        # Count entities where data_sources JSONB has > 1 key
        multi_source = session.query(func.count()).select_from(model).filter(
            func.jsonb_array_length(func.jsonb_object_keys(model.data_sources)) > 1
        ).scalar()
        
        if total > 0:
            pct = (multi_source / total * 100)
            print(f"  {name:20s}: {multi_source:5d} / {total:5d} ({pct:5.1f}%)")


def show_review_queue(session):
    """Show review queue status."""
    print("\n## REVIEW QUEUE")
    print("-" * 80)
    
    # Count by entity type
    query = session.query(
        EntityMatchCandidate.entity_type,
        func.count(EntityMatchCandidate.candidate_id)
    ).filter(
        EntityMatchCandidate.status == 'needs_review'
    ).group_by(EntityMatchCandidate.entity_type)
    
    results = query.all()
    
    if not results:
        print("\n✓ No items in review queue")
    else:
        total_pending = sum(count for _, count in results)
        print(f"\n⚠ {total_pending} items pending review:")
        for entity_type, count in results:
            print(f"  {entity_type:20s}: {count:5d}")


if __name__ == '__main__':
    main()

