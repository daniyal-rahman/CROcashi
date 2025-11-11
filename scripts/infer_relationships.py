#!/usr/bin/env python3
"""
CLI script for running relationship inference.

This script infers relationships between entities that weren't created during
entity extraction, such as publication-trial relationships from NCT IDs,
publication-drug relationships from text search, etc.
"""
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from src.services.relationship_inference import RelationshipInferenceService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for relationship inference CLI."""
    parser = argparse.ArgumentParser(
        description='Infer relationships between entities',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Rebuild all relationships from scratch
  python scripts/infer_relationships.py --rebuild

  # Only infer specific relationship types
  python scripts/infer_relationships.py --types publication_trial publication_drug

  # Dry run (show what would be created)
  python scripts/infer_relationships.py --dry-run

  # Verbose logging
  python scripts/infer_relationships.py --rebuild --verbose
        """
    )
    
    parser.add_argument(
        '--rebuild',
        action='store_true',
        help='Clear existing relationships and rebuild from scratch'
    )
    
    parser.add_argument(
        '--types',
        nargs='+',
        metavar='TYPE',
        help='Only infer specific relationship types (e.g., publication_trial publication_drug)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be created without actually creating relationships'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--atomic',
        action='store_true',
        default=True,
        help='Wrap all inference in a single transaction (all-or-nothing). Default: True'
    )
    
    parser.add_argument(
        '--no-atomic',
        dest='atomic',
        action='store_false',
        help='Allow partial success (each method commits separately)'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Number of entities to process in memory at once (default: 1000)'
    )
    
    parser.add_argument(
        '--commit-batch-size',
        type=int,
        default=500,
        help='Number of relationships to create before committing (default: 500)'
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    
    # Validate relationship types if specified
    valid_types = {
        'company_drug',
        'publication_trial',
        'publication_drug',
        'publication_company',
        'filing_drug'
    }
    
    if args.types:
        invalid_types = set(args.types) - valid_types
        if invalid_types:
            logger.error(f"Invalid relationship types: {invalid_types}")
            logger.info(f"Valid types: {', '.join(sorted(valid_types))}")
            sys.exit(1)
    
    try:
        with get_db_session() as session:
            service = RelationshipInferenceService(
                session,
                batch_size=args.batch_size,
                commit_batch_size=args.commit_batch_size
            )
            
            if args.dry_run:
                logger.info("DRY RUN MODE - No relationships will be created")
                # In dry run, we could add logic to count what would be created
                # For now, just log that we're in dry run mode
                logger.info("Dry run mode not fully implemented - use without --dry-run to create relationships")
                return
            
            if args.rebuild:
                logger.info("Rebuilding all relationships from scratch...")
                results = service.rebuild_all(clear_existing=True)
            elif args.types:
                logger.info(f"Inferring specific relationship types: {', '.join(args.types)}")
                results = {}
                for rel_type in args.types:
                    method_name = f"infer_{rel_type}_relationships"
                    if hasattr(service, method_name):
                        method = getattr(service, method_name)
                        # For individual types, always commit (atomic only applies to all_relationships)
                        results[rel_type] = method(commit=True)
                    else:
                        logger.warning(f"Unknown relationship type method: {method_name}")
                        results[rel_type] = {'status': 'error', 'error': 'Method not found'}
            else:
                logger.info("Running all inference methods...")
                results = service.infer_all_relationships(atomic=args.atomic)
            
            # Print summary
            print("\n" + "=" * 80)
            print("RELATIONSHIP INFERENCE SUMMARY")
            print("=" * 80)
            
            total_created = 0
            for rel_type, result in results.items():
                if result.get('status') == 'success':
                    created = result.get('relationships_created', 0)
                    total_created += created
                    print(f"\n{rel_type.replace('_', ' ').title()}:")
                    print(f"  Status: {result.get('status')}")
                    print(f"  Relationships Created: {created:,}")
                    
                    # Print additional stats if available
                    if 'publications_processed' in result:
                        print(f"  Publications Processed: {result['publications_processed']:,}")
                    if 'filings_processed' in result:
                        print(f"  Filings Processed: {result['filings_processed']:,}")
                    if 'nct_ids_found' in result:
                        print(f"  NCT IDs Found: {result['nct_ids_found']:,}")
                    if 'trials_matched' in result:
                        print(f"  Trials Matched: {result['trials_matched']:,}")
                    if 'drugs_found' in result:
                        print(f"  Drug Mentions Found: {result['drugs_found']:,}")
                    if 'method' in result:
                        print(f"  Method: {result['method']}")
                    if 'note' in result:
                        print(f"  Note: {result['note']}")
                else:
                    print(f"\n{rel_type.replace('_', ' ').title()}:")
                    print(f"  Status: {result.get('status', 'unknown')}")
                    if 'error' in result:
                        print(f"  Error: {result['error']}")
            
            print("\n" + "=" * 80)
            print(f"TOTAL RELATIONSHIPS CREATED: {total_created:,}")
            print("=" * 80 + "\n")
            
    except Exception as e:
        logger.error(f"Error running relationship inference: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

