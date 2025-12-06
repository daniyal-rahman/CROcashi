#!/usr/bin/env python3
"""
CLI tool for reviewing ambiguous entity matches.

Usage:
    python -m src.tools.review_matches [--entity-type TYPE] [--limit N]
"""
import argparse
import sys
from uuid import UUID

from database.config import get_db_session
from src.entity_resolution.review_interface import ReviewInterface
from src.entity_resolution.types import EntityType


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Review ambiguous entity matches"
    )
    parser.add_argument(
        '--entity-type',
        type=str,
        choices=[e.value for e in EntityType],
        help='Filter by entity type'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Maximum number of matches to show'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show review queue statistics'
    )
    
    args = parser.parse_args()
    
    with get_db_session() as session:
        interface = ReviewInterface(session)
        
        if args.stats:
            show_stats(interface)
            return
        
        # Get pending reviews
        entity_type = EntityType(args.entity_type) if args.entity_type else None
        candidates = interface.get_pending_reviews(entity_type, args.limit)
        
        if not candidates:
            print("No matches pending review!")
            return
        
        print(f"\nFound {len(candidates)} matches needing review\n")
        print("=" * 80)
        
        # Review each candidate
        for i, candidate in enumerate(candidates, 1):
            review_candidate(interface, candidate, i, len(candidates))


def show_stats(interface: ReviewInterface):
    """Show review queue statistics."""
    stats = interface.get_review_stats()
    
    print("\n" + "=" * 60)
    print("REVIEW QUEUE STATISTICS")
    print("=" * 60)
    
    print("\nBy Status:")
    for status, count in stats['status_counts'].items():
        print(f"  {status:20s}: {count:5d}")
    
    print("\nNeeds Review By Entity Type:")
    for entity_type, count in stats['needs_review_by_type'].items():
        print(f"  {entity_type:20s}: {count:5d}")
    
    print(f"\nTotal Pending: {stats['total_pending']}")
    print("=" * 60 + "\n")


def review_candidate(
    interface: ReviewInterface,
    candidate,
    index: int,
    total: int
):
    """Review a single candidate."""
    details = interface.get_candidate_details(candidate.candidate_id)
    
    print(f"\nCandidate {index}/{total}")
    print("-" * 80)
    print(f"Entity Type: {details['entity_type']}")
    print(f"Source: {details['source_name']} ({details['source_identifier']})")
    print(f"Extracted Text: {details['extracted_text']}")
    print(f"Confidence: {details['match_confidence']:.2f}" if details['match_confidence'] else "Confidence: N/A")
    print(f"\nReasoning:\n{details['match_reasoning']}")
    
    print("\nPotential Matches:")
    for j, match in enumerate(details['potential_matches'], 1):
        entity_details = match.get('entity_details', {})
        print(f"\n  {j}. Entity ID: {match['entity_id']}")
        print(f"     Name: {entity_details.get('name', 'Unknown')}")
        print(f"     Score: {match['score']:.2f}")
        print(f"     Reason: {match['reason']}")
    
    print("\n" + "-" * 80)
    
    # Get user input
    while True:
        choice = input(
            "\nAction: (1-N) confirm match, (r) reject all, (s) skip, (q) quit: "
        ).strip().lower()
        
        if choice == 'q':
            sys.exit(0)
        elif choice == 's':
            break
        elif choice == 'r':
            # Reject all matches
            reviewer_name = input("Your name: ").strip()
            notes = input("Notes (optional): ").strip()
            
            success = interface.reject_match(
                candidate.candidate_id,
                reviewer_name,
                notes or None
            )
            
            if success:
                print("✓ Match rejected - will create new entity")
            else:
                print("✗ Error rejecting match")
            break
        elif choice.isdigit():
            match_index = int(choice) - 1
            if 0 <= match_index < len(details['potential_matches']):
                # Confirm this match
                match = details['potential_matches'][match_index]
                entity_id = UUID(match['entity_id'])
                
                reviewer_name = input("Your name: ").strip()
                notes = input("Notes (optional): ").strip()
                
                success = interface.confirm_match(
                    candidate.candidate_id,
                    entity_id,
                    reviewer_name,
                    notes or None
                )
                
                if success:
                    print(f"✓ Match confirmed to entity {entity_id}")
                else:
                    print("✗ Error confirming match")
                break
            else:
                print("Invalid match number")
        else:
            print("Invalid choice")
    
    print("=" * 80)


if __name__ == '__main__':
    main()

