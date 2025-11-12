#!/usr/bin/env python3
"""
Prioritize entity match candidates for review.
Focuses on high-priority sources and exports top candidates.
"""
import sys
from pathlib import Path
import csv
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from database.config import get_db_session
from database.models.resolution import EntityMatchCandidate


# Priority order by source importance
SOURCE_PRIORITY = {
    'fda_warning_letters': 1,  # Highest - critical failure signals
    'fda_clinical_hold': 2,     # High - failure signals
    'fda_eua': 3,               # High - regulatory events
    'fda_breakthrough': 4,      # Medium - positive signals
    'fda_guidance': 5,          # Medium - general guidance
    'fda_orphan': 6,            # Medium - regulatory events
    'california_warn': 7,       # Lower - layoff signals
    'federal_warn': 8,          # Lower - layoff signals
    'sec_edgar': 9,             # Lower - financial (but important for dashboard)
    'pubmed': 10,               # Lower - publications
    'clinicaltrials_gov': 11,   # Lower - trials (usually well-matched)
}


def prioritize_candidates(session, limit=30):
    """Prioritize match candidates by source importance and confidence."""
    print(f"Prioritizing top {limit} candidates for review...")
    
    # Get all candidates
    candidates = session.query(EntityMatchCandidate).filter(
        EntityMatchCandidate.status == 'needs_review',
        EntityMatchCandidate.deleted_at.is_(None)
    ).all()
    
    print(f"Total candidates: {len(candidates)}")
    
    # Score and sort candidates
    scored_candidates = []
    for candidate in candidates:
        # Priority score (lower = higher priority)
        source_priority = SOURCE_PRIORITY.get(candidate.source_name, 99)
        
        # Confidence score (lower confidence = higher priority for review)
        confidence_score = candidate.match_confidence or 0.5
        
        # Combined score (lower = higher priority)
        priority_score = source_priority * 1000 + (1 - confidence_score) * 100
        
        scored_candidates.append({
            'candidate': candidate,
            'priority_score': priority_score,
            'source_priority': source_priority,
            'confidence': confidence_score
        })
    
    # Sort by priority score
    scored_candidates.sort(key=lambda x: x['priority_score'])
    
    # Get top N
    top_candidates = scored_candidates[:limit]
    
    return top_candidates


def export_candidates(candidates, output_file):
    """Export candidates to CSV for review."""
    print(f"Exporting {len(candidates)} candidates to {output_file}...")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            'Candidate ID',
            'Entity Type',
            'Source Name',
            'Source Identifier',
            'Extracted Text',
            'Match Confidence',
            'Potential Matches',
            'Match Reasoning',
            'Priority',
            'Review Status'
        ])
        
        # Data rows
        for item in candidates:
            candidate = item['candidate']
            
            # Format potential matches
            potential_matches = []
            if candidate.potential_matches:
                for match in candidate.potential_matches[:3]:  # Top 3
                    potential_matches.append(
                        f"{match.get('entity_id', 'N/A')[:8]}... "
                        f"(score: {match.get('score', 0):.2f})"
                    )
            matches_str = '; '.join(potential_matches) if potential_matches else 'None'
            
            # Truncate long text
            extracted_text = candidate.extracted_text[:100] if candidate.extracted_text else ''
            reasoning = candidate.match_reasoning[:200] if candidate.match_reasoning else ''
            
            writer.writerow([
                str(candidate.candidate_id),
                candidate.entity_type,
                candidate.source_name,
                candidate.source_identifier,
                extracted_text,
                f"{item['confidence']:.2f}",
                matches_str,
                reasoning,
                item['source_priority'],
                candidate.status
            ])
    
    print(f"✓ Exported to {output_file}")


def create_review_summary(candidates, session):
    """Create summary statistics for review."""
    print("\n" + "=" * 80)
    print("REVIEW SUMMARY")
    print("=" * 80)
    
    # Group by source
    by_source = {}
    for item in candidates:
        source = item['candidate'].source_name
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(item)
    
    print(f"\nTop {len(candidates)} candidates by source:")
    for source in sorted(by_source.keys(), key=lambda x: SOURCE_PRIORITY.get(x, 99)):
        count = len(by_source[source])
        avg_confidence = sum(item['confidence'] for item in by_source[source]) / count
        print(f"  {source}: {count} candidates (avg confidence: {avg_confidence:.2f})")
    
    # Group by entity type
    by_type = {}
    for item in candidates:
        entity_type = item['candidate'].entity_type
        if entity_type not in by_type:
            by_type[entity_type] = []
        by_type[entity_type].append(item)
    
    print(f"\nBy entity type:")
    for entity_type in sorted(by_type.keys()):
        count = len(by_type[entity_type])
        print(f"  {entity_type}: {count} candidates")
    
    # Confidence distribution
    low_confidence = [item for item in candidates if item['confidence'] < 0.5]
    medium_confidence = [item for item in candidates if 0.5 <= item['confidence'] < 0.7]
    high_confidence = [item for item in candidates if item['confidence'] >= 0.7]
    
    print(f"\nConfidence distribution:")
    print(f"  Low (<0.5): {len(low_confidence)} candidates")
    print(f"  Medium (0.5-0.7): {len(medium_confidence)} candidates")
    print(f"  High (>=0.7): {len(high_confidence)} candidates")


def main():
    print("=" * 80)
    print("ENTITY MATCH CANDIDATE PRIORITIZATION")
    print("=" * 80)
    
    with get_db_session() as session:
        # Prioritize candidates
        top_candidates = prioritize_candidates(session, limit=30)
        
        if not top_candidates:
            print("\nNo candidates found for review.")
            return
        
        # Create summary
        create_review_summary(top_candidates, session)
        
        # Export to CSV
        output_dir = project_root / 'data' / 'entity_review'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = output_dir / f'entity_matches_review_{timestamp}.csv'
        
        export_candidates(top_candidates, output_file)
        
        print(f"\n✓ Review file created: {output_file}")
        print(f"\nNext steps:")
        print(f"  1. Open {output_file} in Excel/Google Sheets")
        print(f"  2. Review each candidate")
        print(f"  3. Update status in database using candidate IDs")
        print(f"  4. Document patterns for auto-resolution")


if __name__ == '__main__':
    main()

