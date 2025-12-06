"""
CLI tool for reviewing entity match candidates.

Usage:
    python review_tool.py list                    # List pending reviews
    python review_tool.py show <candidate_id>      # Show candidate details
    python review_tool.py confirm <candidate_id> <entity_id>  # Confirm match
    python review_tool.py reject <candidate_id>    # Reject match
    python review_tool.py stats                    # Show review statistics
"""
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session
from src.entity_resolution.review_interface import ReviewInterface


def list_reviews(limit=20):
    """List pending reviews."""
    with get_db_session() as session:
        review = ReviewInterface(session)
        candidates = review.get_pending_reviews(limit=limit)
        
        print(f"\nPending Reviews ({len(candidates)}):")
        print("="*70)
        
        for i, candidate in enumerate(candidates, 1):
            print(f"\n{i}. {candidate.entity_type.upper()}: \"{candidate.extracted_text}\"")
            print(f"   ID: {candidate.candidate_id}")
            print(f"   Source: {candidate.source_name} ({candidate.source_identifier})")
            print(f"   Confidence: {candidate.match_confidence:.2f}")
            if candidate.potential_matches:
                print(f"   Potential matches: {len(candidate.potential_matches)}")
                for match in candidate.potential_matches[:2]:
                    print(f"     - {match.get('entity_id', 'N/A')[:8]}... (score: {match.get('score', 0):.2f})")


def show_candidate(candidate_id_str):
    """Show detailed candidate information."""
    try:
        candidate_id = UUID(candidate_id_str)
    except ValueError:
        print(f"Error: Invalid candidate ID: {candidate_id_str}")
        return
    
    with get_db_session() as session:
        review = ReviewInterface(session)
        details = review.get_candidate_details(candidate_id)
        
        if 'error' in details:
            print(f"Error: {details['error']}")
            return
        
        print("\n" + "="*70)
        print("CANDIDATE DETAILS")
        print("="*70)
        print(f"\nEntity Type: {details['entity_type']}")
        print(f"Extracted Text: \"{details['extracted_text']}\"")
        print(f"Source: {details['source_name']} ({details['source_identifier']})")
        print(f"Confidence: {details['match_confidence']:.2f}")
        print(f"Reasoning: {details['match_reasoning']}")
        
        if details['potential_matches']:
            print(f"\nPotential Matches ({len(details['potential_matches'])}):")
            for i, match in enumerate(details['potential_matches'], 1):
                print(f"\n  {i}. Entity ID: {match['entity_id']}")
                print(f"     Score: {match['score']:.2f}")
                print(f"     Reason: {match['reason']}")
                if 'entity_details' in match and 'name' in match['entity_details']:
                    print(f"     Name: {match['entity_details']['name']}")
                    if 'generic_name' in match['entity_details']:
                        print(f"     Generic: {match['entity_details']['generic_name']}")


def confirm_match(candidate_id_str, entity_id_str, reviewer="cli_user"):
    """Confirm a match."""
    try:
        candidate_id = UUID(candidate_id_str)
        entity_id = UUID(entity_id_str)
    except ValueError as e:
        print(f"Error: Invalid UUID: {e}")
        return
    
    with get_db_session() as session:
        review = ReviewInterface(session)
        success = review.confirm_match(candidate_id, entity_id, reviewer)
        
        if success:
            print(f"✅ Match confirmed: {candidate_id} -> {entity_id}")
        else:
            print(f"❌ Failed to confirm match")


def reject_match(candidate_id_str, reviewer="cli_user"):
    """Reject all matches."""
    try:
        candidate_id = UUID(candidate_id_str)
    except ValueError:
        print(f"Error: Invalid candidate ID: {candidate_id_str}")
        return
    
    with get_db_session() as session:
        review = ReviewInterface(session)
        success = review.reject_match(candidate_id, reviewer)
        
        if success:
            print(f"✅ Match rejected: {candidate_id}")
        else:
            print(f"❌ Failed to reject match")


def show_stats():
    """Show review statistics."""
    with get_db_session() as session:
        review = ReviewInterface(session)
        stats = review.get_review_stats()
        
        print("\n" + "="*70)
        print("REVIEW STATISTICS")
        print("="*70)
        
        print(f"\nStatus Counts:")
        for status, count in stats['status_counts'].items():
            print(f"  {status}: {count}")
        
        print(f"\nPending Reviews by Type:")
        for etype, count in stats['needs_review_by_type'].items():
            print(f"  {etype}: {count}")
        
        print(f"\nTotal Pending: {stats['total_pending']}")


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1].lower()
    
    if command == 'list':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        list_reviews(limit)
    
    elif command == 'show':
        if len(sys.argv) < 3:
            print("Error: candidate_id required")
            print("Usage: python review_tool.py show <candidate_id>")
            return
        show_candidate(sys.argv[2])
    
    elif command == 'confirm':
        if len(sys.argv) < 4:
            print("Error: candidate_id and entity_id required")
            print("Usage: python review_tool.py confirm <candidate_id> <entity_id>")
            return
        confirm_match(sys.argv[2], sys.argv[3])
    
    elif command == 'reject':
        if len(sys.argv) < 3:
            print("Error: candidate_id required")
            print("Usage: python review_tool.py reject <candidate_id>")
            return
        reject_match(sys.argv[2])
    
    elif command == 'stats':
        show_stats()
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()

