#!/usr/bin/env python3
"""
Interactive batch review of match candidates.

Allows efficient review of candidates in batches with keyboard shortcuts.
Processes candidates and tracks progress.
"""
import sys
from pathlib import Path
import logging
from datetime import datetime
from uuid import UUID
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.resolution import EntityMatchCandidate
from database.models.entities import Company, Drug, Disease, Institution
from database.models.clinical import ClinicalTrial
from src.entity_resolution.review_interface import ReviewInterface

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def get_entity_name(session, entity_type: str, entity_id: UUID) -> str:
    """Get the name of an entity."""
    try:
        if entity_type == 'company':
            entity = session.query(Company).filter(Company.company_id == entity_id).first()
            if entity:
                return entity.name or 'Unknown'
        elif entity_type == 'drug':
            entity = session.query(Drug).filter(Drug.drug_id == entity_id).first()
            if entity:
                return entity.primary_name or entity.generic_name or 'Unknown'
        elif entity_type == 'disease':
            entity = session.query(Disease).filter(Disease.disease_id == entity_id).first()
            if entity:
                return entity.disease_name or 'Unknown'
        elif entity_type == 'institution':
            entity = session.query(Institution).filter(Institution.institution_id == entity_id).first()
            if entity:
                return entity.name or 'Unknown'
        elif entity_type == 'trial':
            entity = session.query(ClinicalTrial).filter(ClinicalTrial.trial_id == entity_id).first()
            if entity:
                return entity.trial_title or 'Unknown'
    except Exception as e:
        logger.error(f"Error getting entity name: {e}")
    
    return 'Unknown'


def display_candidate(candidate: EntityMatchCandidate, index: int, total: int, session):
    """Display candidate information."""
    print("\n" + "=" * 80)
    print(f"CANDIDATE {index}/{total}")
    print("=" * 80)
    print(f"ID: {candidate.candidate_id}")
    print(f"Entity Type: {candidate.entity_type}")
    print(f"Source: {candidate.source_name} ({candidate.source_identifier})")
    print(f"Extracted Text: {candidate.extracted_text}")
    
    confidence = float(candidate.match_confidence) if candidate.match_confidence else 0.0
    print(f"Confidence: {confidence:.2f}")
    
    if candidate.match_reasoning:
        print(f"Reasoning: {candidate.match_reasoning[:200]}...")
    
    potential_matches = candidate.potential_matches or []
    
    if potential_matches:
        print(f"\nPotential Matches ({len(potential_matches)}):")
        for i, match in enumerate(potential_matches[:5], 1):  # Show top 5
            entity_id = UUID(match.get('entity_id', ''))
            score = match.get('score', 0.0)
            reason = match.get('reason', '')
            entity_name = get_entity_name(session, candidate.entity_type, entity_id)
            
            print(f"  {i}. {entity_name[:60]}")
            print(f"     ID: {entity_id}")
            print(f"     Score: {score:.2f}")
            print(f"     Reason: {reason[:100]}")
    else:
        print("\nNo potential matches found - will create new entity")
    
    print("=" * 80)


def review_batch(
    session,
    candidates: list,
    batch_start: int,
    reviewer_name: str = "batch_reviewer"
) -> dict:
    """Review a batch of candidates."""
    results = {
        'approved': 0,
        'rejected': 0,
        'skipped': 0,
        'errors': 0
    }
    
    review_interface = ReviewInterface(session)
    
    for i, candidate in enumerate(candidates, start=batch_start):
        display_candidate(candidate, i, len(candidates) + batch_start - 1, session)
        
        potential_matches = candidate.potential_matches or []
        confidence = float(candidate.match_confidence) if candidate.match_confidence else 0.0
        
        # Auto-suggest decision based on confidence and matches
        if not potential_matches:
            suggested = 'r'  # reject - no matches
            suggestion_text = "No matches - suggest REJECT"
        elif len(potential_matches) == 1 and confidence >= 0.85:
            suggested = '1'  # approve top match
            suggestion_text = f"High confidence ({confidence:.2f}) - suggest APPROVE match 1"
        elif len(potential_matches) == 1 and confidence >= 0.70:
            suggested = '?'  # unclear
            suggestion_text = f"Medium confidence ({confidence:.2f}) - review carefully"
        else:
            suggested = '?'
            suggestion_text = "Multiple matches or low confidence - review carefully"
        
        print(f"\nSuggested: {suggestion_text}")
        
        while True:
            if potential_matches:
                action = input(
                    f"\nAction: (1-{min(len(potential_matches), 5)}) approve match, (r) reject, (s) skip, (q) quit: "
                ).strip().lower()
            else:
                action = input(
                    "\nAction: (r) reject (create new), (s) skip, (q) quit: "
                ).strip().lower()
            
            if action == 'q':
                print("\nQuitting review session...")
                return results
            elif action == 's':
                results['skipped'] += 1
                print("⏭ Skipped")
                break
            elif action == 'r':
                # Reject match
                try:
                    success = review_interface.reject_match(
                        candidate.candidate_id,
                        reviewer_name=reviewer_name,
                        notes=f"Batch review - rejected (confidence: {confidence:.2f})"
                    )
                    if success:
                        results['rejected'] += 1
                        print("✓ Rejected - will create new entity")
                        session.commit()
                    else:
                        results['errors'] += 1
                        print("✗ Error rejecting match")
                except Exception as e:
                    results['errors'] += 1
                    print(f"✗ Error: {e}")
                    session.rollback()
                break
            elif action.isdigit():
                match_index = int(action) - 1
                if 0 <= match_index < len(potential_matches):
                    match = potential_matches[match_index]
                    entity_id = UUID(match['entity_id'])
                    
                    try:
                        success = review_interface.confirm_match(
                            candidate.candidate_id,
                            entity_id,
                            reviewer_name=reviewer_name,
                            notes=f"Batch review - approved match {match_index + 1} (score: {match.get('score', 0):.2f})"
                        )
                        if success:
                            results['approved'] += 1
                            entity_name = get_entity_name(session, candidate.entity_type, entity_id)
                            print(f"✓ Approved - matched to: {entity_name}")
                            session.commit()
                        else:
                            results['errors'] += 1
                            print("✗ Error confirming match")
                    except Exception as e:
                        results['errors'] += 1
                        print(f"✗ Error: {e}")
                        session.rollback()
                    break
                else:
                    print(f"Invalid match number (1-{len(potential_matches)})")
            else:
                print("Invalid action. Use: 1-N (approve), r (reject), s (skip), q (quit)")
        
        # Show progress
        total_processed = results['approved'] + results['rejected'] + results['skipped']
        print(f"\nProgress: {total_processed} processed ({results['approved']} approved, {results['rejected']} rejected, {results['skipped']} skipped)")
    
    return results


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Interactive batch review of match candidates"
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Number of candidates to review in this batch (default: 50)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Maximum total candidates to review (default: 100)'
    )
    parser.add_argument(
        '--entity-type',
        type=str,
        help='Filter by entity type (company, drug, disease, etc.)'
    )
    parser.add_argument(
        '--reviewer-name',
        type=str,
        default='batch_reviewer',
        help='Name of reviewer (default: batch_reviewer)'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("BATCH REVIEW OF MATCH CANDIDATES")
    print("=" * 80)
    print(f"Started at: {datetime.now()}")
    print(f"Batch size: {args.batch_size}")
    print(f"Max limit: {args.limit}")
    if args.entity_type:
        print(f"Entity type filter: {args.entity_type}")
    print()
    
    with get_db_session() as session:
        # Get candidates
        query = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.status == 'needs_review',
            EntityMatchCandidate.deleted_at.is_(None)
        )
        
        if args.entity_type:
            query = query.filter(EntityMatchCandidate.entity_type == args.entity_type)
        
        total_available = query.count()
        print(f"Total candidates available: {total_available}")
        
        candidates = query.order_by(EntityMatchCandidate.created_at).limit(args.limit).all()
        
        if not candidates:
            print("No candidates found for review!")
            return
        
        print(f"Reviewing {len(candidates)} candidates\n")
        
        # Review in batches
        all_results = {
            'approved': 0,
            'rejected': 0,
            'skipped': 0,
            'errors': 0
        }
        
        batch_num = 1
        for i in range(0, len(candidates), args.batch_size):
            batch = candidates[i:i + args.batch_size]
            batch_start = i + 1
            
            print(f"\n{'=' * 80}")
            print(f"BATCH {batch_num} ({len(batch)} candidates)")
            print(f"{'=' * 80}")
            
            batch_results = review_batch(
                session,
                batch,
                batch_start,
                reviewer_name=args.reviewer_name
            )
            
            # Accumulate results
            for key in all_results:
                all_results[key] += batch_results[key]
            
            batch_num += 1
            
            # Check if user quit
            if batch_results.get('quit', False):
                break
        
        # Final summary
        print("\n" + "=" * 80)
        print("REVIEW SUMMARY")
        print("=" * 80)
        print(f"Total candidates reviewed: {len(candidates)}")
        print(f"Approved: {all_results['approved']}")
        print(f"Rejected: {all_results['rejected']}")
        print(f"Skipped: {all_results['skipped']}")
        print(f"Errors: {all_results['errors']}")
        print(f"Completed at: {datetime.now()}")
        print("=" * 80)


if __name__ == '__main__':
    main()





