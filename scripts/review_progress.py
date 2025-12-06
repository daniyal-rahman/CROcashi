#!/usr/bin/env python3
"""
Review progress tracking script.

Displays review statistics, tracks progress rate, and projects completion date.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.resolution import EntityMatchCandidate
from sqlalchemy import func

# Set up output directory
output_dir = project_root / 'data' / 'review_progress'
output_dir.mkdir(parents=True, exist_ok=True)


def get_review_stats():
    """Get comprehensive review statistics."""
    with get_db_session() as session:
        # Count by status
        status_counts = session.query(
            EntityMatchCandidate.status,
            func.count(EntityMatchCandidate.candidate_id)
        ).filter(
            EntityMatchCandidate.deleted_at.is_(None)
        ).group_by(EntityMatchCandidate.status).all()
        
        # Count pending by entity type
        pending_by_type = session.query(
            EntityMatchCandidate.entity_type,
            func.count(EntityMatchCandidate.candidate_id)
        ).filter(
            EntityMatchCandidate.status == 'needs_review',
            EntityMatchCandidate.deleted_at.is_(None)
        ).group_by(EntityMatchCandidate.entity_type).all()
        
        # Count pending by source
        pending_by_source = session.query(
            EntityMatchCandidate.source_name,
            func.count(EntityMatchCandidate.candidate_id)
        ).filter(
            EntityMatchCandidate.status == 'needs_review',
            EntityMatchCandidate.deleted_at.is_(None)
        ).group_by(EntityMatchCandidate.source_name).all()
        
        # Count reviewed by date
        reviewed_by_date = session.query(
            EntityMatchCandidate.reviewed_at,
            func.count(EntityMatchCandidate.candidate_id)
        ).filter(
            EntityMatchCandidate.status.in_(['reviewed', 'new_entity']),
            EntityMatchCandidate.reviewed_at.isnot(None),
            EntityMatchCandidate.deleted_at.is_(None)
        ).group_by(EntityMatchCandidate.reviewed_at).order_by(EntityMatchCandidate.reviewed_at.desc()).all()
        
        # Confidence score distribution for pending
        confidence_dist = session.query(
            func.floor(EntityMatchCandidate.match_confidence * 10) / 10,
            func.count(EntityMatchCandidate.candidate_id)
        ).filter(
            EntityMatchCandidate.status == 'needs_review',
            EntityMatchCandidate.match_confidence.isnot(None),
            EntityMatchCandidate.deleted_at.is_(None)
        ).group_by(func.floor(EntityMatchCandidate.match_confidence * 10) / 10).all()
        
        return {
            'status_counts': dict(status_counts),
            'pending_by_type': dict(pending_by_type),
            'pending_by_source': dict(pending_by_source),
            'reviewed_by_date': [(date, count) for date, count in reviewed_by_date],
            'confidence_dist': dict(confidence_dist)
        }


def calculate_review_rate(reviewed_by_date, days=7):
    """Calculate average review rate over last N days."""
    if not reviewed_by_date:
        return 0.0
    
    cutoff_date = datetime.now().date() - timedelta(days=days)
    recent_reviews = [
        count for date, count in reviewed_by_date
        if date and date >= cutoff_date
    ]
    
    if not recent_reviews:
        return 0.0
    
    total_reviews = sum(recent_reviews)
    return total_reviews / days


def project_completion_date(pending_count, review_rate):
    """Project completion date based on current review rate."""
    if review_rate <= 0:
        return None
    
    days_remaining = pending_count / review_rate
    completion_date = datetime.now().date() + timedelta(days=int(days_remaining))
    return completion_date


def display_progress_report():
    """Display comprehensive progress report."""
    print("=" * 80)
    print("REVIEW PROGRESS REPORT")
    print("=" * 80)
    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    stats = get_review_stats()
    
    # Status summary
    print("## STATUS SUMMARY")
    print("-" * 80)
    total = sum(stats['status_counts'].values())
    pending = stats['status_counts'].get('needs_review', 0)
    reviewed = stats['status_counts'].get('reviewed', 0)
    new_entity = stats['status_counts'].get('new_entity', 0)
    
    print(f"Total Candidates: {total}")
    print(f"  Pending Review: {pending}")
    print(f"  Reviewed (Approved): {reviewed}")
    print(f"  Reviewed (New Entity): {new_entity}")
    print(f"  Other: {total - pending - reviewed - new_entity}")
    print()
    
    if pending > 0:
        completion_pct = ((reviewed + new_entity) / total * 100) if total > 0 else 0
        print(f"Completion: {completion_pct:.1f}% ({reviewed + new_entity}/{total})")
        print()
    
    # Review rate
    print("## REVIEW RATE")
    print("-" * 80)
    review_rate_7d = calculate_review_rate(stats['reviewed_by_date'], days=7)
    review_rate_30d = calculate_review_rate(stats['reviewed_by_date'], days=30)
    
    print(f"Last 7 days: {review_rate_7d:.1f} candidates/day")
    print(f"Last 30 days: {review_rate_30d:.1f} candidates/day")
    print()
    
    if pending > 0 and review_rate_7d > 0:
        completion_date = project_completion_date(pending, review_rate_7d)
        if completion_date:
            print(f"Projected completion (at current rate): {completion_date.strftime('%Y-%m-%d')}")
            days_remaining = (completion_date - datetime.now().date()).days
            print(f"Days remaining: {days_remaining}")
        print()
    
    # Pending by entity type
    if stats['pending_by_type']:
        print("## PENDING BY ENTITY TYPE")
        print("-" * 80)
        for entity_type, count in sorted(stats['pending_by_type'].items(), key=lambda x: x[1], reverse=True):
            pct = (count / pending * 100) if pending > 0 else 0
            print(f"  {entity_type:20s}: {count:5d} ({pct:5.1f}%)")
        print()
    
    # Pending by source
    if stats['pending_by_source']:
        print("## PENDING BY SOURCE")
        print("-" * 80)
        for source, count in sorted(stats['pending_by_source'].items(), key=lambda x: x[1], reverse=True):
            pct = (count / pending * 100) if pending > 0 else 0
            print(f"  {source:30s}: {count:5d} ({pct:5.1f}%)")
        print()
    
    # Confidence distribution
    if stats['confidence_dist']:
        print("## CONFIDENCE SCORE DISTRIBUTION (Pending)")
        print("-" * 80)
        for conf_bucket in sorted(stats['confidence_dist'].keys()):
            count = stats['confidence_dist'][conf_bucket]
            pct = (count / pending * 100) if pending > 0 else 0
            bar = '█' * int(pct / 2)
            print(f"  {conf_bucket:.1f}-{conf_bucket+0.1:.1f}: {count:5d} {bar} ({pct:5.1f}%)")
        print()
    
    # Recent activity
    if stats['reviewed_by_date']:
        print("## RECENT ACTIVITY (Last 7 Days)")
        print("-" * 80)
        cutoff_date = datetime.now().date() - timedelta(days=7)
        recent = [
            (date, count) for date, count in stats['reviewed_by_date']
            if date and date >= cutoff_date
        ]
        if recent:
            for date, count in recent[:7]:
                print(f"  {date}: {count} candidates reviewed")
        else:
            print("  No reviews in last 7 days")
        print()
    
    return stats


def export_progress_report(stats):
    """Export progress report to file."""
    report_file = output_dir / f'progress_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    
    import json
    report_data = {
        'generated_at': datetime.now().isoformat(),
        'status_counts': stats['status_counts'],
        'pending_by_type': stats['pending_by_type'],
        'pending_by_source': stats['pending_by_source'],
        'review_rate_7d': calculate_review_rate(stats['reviewed_by_date'], days=7),
        'review_rate_30d': calculate_review_rate(stats['reviewed_by_date'], days=30),
        'confidence_distribution': stats['confidence_dist']
    }
    
    pending = stats['status_counts'].get('needs_review', 0)
    review_rate = report_data['review_rate_7d']
    if pending > 0 and review_rate > 0:
        completion_date = project_completion_date(pending, review_rate)
        if completion_date:
            report_data['projected_completion'] = completion_date.isoformat()
    
    with open(report_file, 'w') as f:
        json.dump(report_data, f, indent=2, default=str)
    
    print(f"✓ Progress report saved to {report_file}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Track review progress and statistics"
    )
    parser.add_argument(
        '--export',
        action='store_true',
        help='Export progress report to file'
    )
    
    args = parser.parse_args()
    
    stats = display_progress_report()
    
    if args.export:
        export_progress_report(stats)


if __name__ == '__main__':
    main()





