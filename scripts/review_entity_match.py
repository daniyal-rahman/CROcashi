#!/usr/bin/env python3
"""
Helper script to review and update entity match candidates.
"""
import sys
from pathlib import Path
import uuid

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.resolution import EntityMatchCandidate


def approve_match(candidate_id, entity_id=None):
    """Approve a match candidate."""
    with get_db_session() as session:
        candidate = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.candidate_id == uuid.UUID(candidate_id),
            EntityMatchCandidate.deleted_at.is_(None)
        ).first()
        
        if not candidate:
            print(f"Candidate {candidate_id} not found")
            return False
        
        # Update status
        candidate.status = 'approved'
        
        # If entity_id provided, store it
        if entity_id:
            # Update potential matches to mark this as selected
            if candidate.potential_matches:
                for match in candidate.potential_matches:
                    if str(match.get('entity_id', '')) == entity_id:
                        match['selected'] = True
        
        session.commit()
        print(f"✓ Approved candidate {candidate_id}")
        return True


def reject_match(candidate_id):
    """Reject a match candidate."""
    with get_db_session() as session:
        candidate = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.candidate_id == uuid.UUID(candidate_id),
            EntityMatchCandidate.deleted_at.is_(None)
        ).first()
        
        if not candidate:
            print(f"Candidate {candidate_id} not found")
            return False
        
        candidate.status = 'rejected'
        session.commit()
        print(f"✓ Rejected candidate {candidate_id}")
        return True


def create_new_entity(candidate_id):
    """Mark candidate for new entity creation."""
    with get_db_session() as session:
        candidate = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.candidate_id == uuid.UUID(candidate_id),
            EntityMatchCandidate.deleted_at.is_(None)
        ).first()
        
        if not candidate:
            print(f"Candidate {candidate_id} not found")
            return False
        
        candidate.status = 'create_new'
        session.commit()
        print(f"✓ Marked candidate {candidate_id} for new entity creation")
        return True


def show_candidate(candidate_id):
    """Show candidate details."""
    with get_db_session() as session:
        candidate = session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.candidate_id == uuid.UUID(candidate_id),
            EntityMatchCandidate.deleted_at.is_(None)
        ).first()
        
        if not candidate:
            print(f"Candidate {candidate_id} not found")
            return
        
        print(f"\nCandidate: {candidate.candidate_id}")
        print(f"Entity Type: {candidate.entity_type}")
        print(f"Source: {candidate.source_name}")
        print(f"Source ID: {candidate.source_identifier}")
        print(f"Extracted Text: {candidate.extracted_text}")
        print(f"Confidence: {candidate.match_confidence}")
        print(f"Status: {candidate.status}")
        
        if candidate.potential_matches:
            print(f"\nPotential Matches:")
            for i, match in enumerate(candidate.potential_matches[:5], 1):
                print(f"  {i}. Entity ID: {match.get('entity_id')}")
                print(f"     Score: {match.get('score', 0):.2f}")
                print(f"     Reason: {match.get('reason', 'N/A')}")
        
        if candidate.match_reasoning:
            print(f"\nReasoning: {candidate.match_reasoning}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python review_entity_match.py show <candidate_id>")
        print("  python review_entity_match.py approve <candidate_id> [entity_id]")
        print("  python review_entity_match.py reject <candidate_id>")
        print("  python review_entity_match.py create_new <candidate_id>")
        return
    
    command = sys.argv[1]
    candidate_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    if command == 'show':
        if candidate_id:
            show_candidate(candidate_id)
        else:
            print("Error: candidate_id required")
    elif command == 'approve':
        entity_id = sys.argv[3] if len(sys.argv) > 3 else None
        if candidate_id:
            approve_match(candidate_id, entity_id)
        else:
            print("Error: candidate_id required")
    elif command == 'reject':
        if candidate_id:
            reject_match(candidate_id)
        else:
            print("Error: candidate_id required")
    elif command == 'create_new':
        if candidate_id:
            create_new_entity(candidate_id)
        else:
            print("Error: candidate_id required")
    else:
        print(f"Unknown command: {command}")


if __name__ == '__main__':
    main()

