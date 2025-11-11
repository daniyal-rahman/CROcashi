"""
Activate priority sources for failure detection.

Activates the most critical sources for Week 1 based on the plan.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.sources import Source


# Priority sources for Week 1 (in order)
PRIORITY_SOURCES = [
    'fda_clinical_hold',      # Direct failure signal
    'fda_warning_letters',    # Regulatory risk (processor exists)
    'california_warn',        # Layoff signals (processor exists)
    'federal_warn',          # Layoff signals (processor exists)
    'fda_breakthrough',       # Success signals for comparison
    'fda_orphan',             # Success signals for comparison
    'asco_abstracts',         # Early trial results (processor exists)
]


def activate_priority_sources(dry_run: bool = False) -> Dict[str, int]:
    """
    Activate priority sources.
    
    Args:
        dry_run: If True, only report what would be activated without making changes
    
    Returns:
        Dictionary with activation statistics
    """
    stats = {
        'total_priority': len(PRIORITY_SOURCES),
        'activated': 0,
        'not_found': [],
        'already_active': 0,
        'errors': 0
    }
    
    print(f"Priority sources to activate: {len(PRIORITY_SOURCES)}")
    if dry_run:
        print("\n=== DRY RUN MODE - No changes will be made ===\n")
    
    with get_db_session() as session:
        for source_name in PRIORITY_SOURCES:
            try:
                source = session.query(Source).filter(
                    Source.source_name == source_name,
                    Source.deleted_at.is_(None)
                ).first()
                
                if not source:
                    print(f"⚠ {source_name}: Not found in database")
                    stats['not_found'].append(source_name)
                    continue
                
                if source.is_active:
                    print(f"✓ {source_name}: Already active")
                    stats['already_active'] += 1
                    continue
                
                if not dry_run:
                    source.is_active = True
                    session.flush()
                
                print(f"{'[DRY RUN] ' if dry_run else ''}✓ {source_name}: Activated")
                stats['activated'] += 1
                
            except Exception as e:
                print(f"✗ {source_name}: Error - {e}")
                stats['errors'] += 1
        
        if not dry_run:
            session.commit()
            print(f"\n✓ Successfully activated {stats['activated']} sources")
        else:
            print(f"\n[DRY RUN] Would activate {stats['activated']} sources")
    
    return stats


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Activate priority sources')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be activated without making changes')
    args = parser.parse_args()
    
    try:
        stats = activate_priority_sources(dry_run=args.dry_run)
        
        print("\n" + "="*60)
        print("Activation Summary")
        print("="*60)
        print(f"Total priority sources: {stats['total_priority']}")
        print(f"Activated: {stats['activated']}")
        print(f"Already active: {stats['already_active']}")
        print(f"Not found: {len(stats['not_found'])}")
        print(f"Errors: {stats['errors']}")
        
        if stats['not_found']:
            print("\n⚠️  Sources not found in database:")
            for source in stats['not_found']:
                print(f"  - {source}")
            print("\nRun bulk_register_sources.py first to register all sources")
        
        if args.dry_run:
            print("\nRun without --dry-run to actually activate sources")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

