"""
Verification script to check source registration completeness.

Validates that all ingestion scripts have corresponding registered sources
and reports any mismatches or missing metadata.
"""
import sys
from pathlib import Path
from typing import Dict, List, Set

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.sources import Source


def get_ingestion_scripts() -> Set[str]:
    """Get all ingestion script names from the ingestion directory."""
    ingestion_dir = project_root / 'ingestion'
    scripts = set()
    
    for file in ingestion_dir.glob('*.py'):
        if file.name not in ['__init__.py', 'test_helper.py']:
            script_name = file.stem
            scripts.add(script_name)
    
    return scripts


def verify_source_registration() -> Dict[str, any]:
    """
    Verify source registration completeness.
    
    Returns:
        Dictionary with verification results
    """
    results = {
        'total_scripts': 0,
        'registered': 0,
        'unregistered': [],
        'missing_metadata': [],
        'inactive_sources': [],
        'active_sources': []
    }
    
    # Get all ingestion scripts
    ingestion_scripts = get_ingestion_scripts()
    results['total_scripts'] = len(ingestion_scripts)
    
    with get_db_session() as session:
        # Get all registered sources
        registered_sources = session.query(Source).filter(
            Source.deleted_at.is_(None)
        ).all()
        
        registered_names = {s.source_name for s in registered_sources}
        results['registered'] = len(registered_names)
        
        # Find unregistered scripts
        results['unregistered'] = sorted(ingestion_scripts - registered_names)
        
        # Check metadata completeness for registered sources
        for source in registered_sources:
            issues = []
            
            if not source.base_url:
                issues.append('missing_base_url')
            
            if not source.update_frequency:
                issues.append('missing_update_frequency')
            
            if not source.source_type:
                issues.append('missing_source_type')
            
            if issues:
                results['missing_metadata'].append({
                    'source_name': source.source_name,
                    'issues': issues
                })
            
            if source.is_active:
                results['active_sources'].append(source.source_name)
            else:
                results['inactive_sources'].append(source.source_name)
    
    return results


def print_verification_report(results: Dict):
    """Print a formatted verification report."""
    print("="*60)
    print("Source Registration Verification Report")
    print("="*60)
    print()
    
    print(f"Total Ingestion Scripts: {results['total_scripts']}")
    print(f"Registered Sources: {results['registered']}")
    print(f"Unregistered Scripts: {len(results['unregistered'])}")
    print(f"Active Sources: {len(results['active_sources'])}")
    print(f"Inactive Sources: {len(results['inactive_sources'])}")
    print(f"Sources with Missing Metadata: {len(results['missing_metadata'])}")
    print()
    
    if results['unregistered']:
        print("⚠️  UNREGISTERED SCRIPTS:")
        print("-" * 60)
        for script in results['unregistered']:
            print(f"  - {script}")
        print()
    
    if results['missing_metadata']:
        print("⚠️  SOURCES WITH MISSING METADATA:")
        print("-" * 60)
        for item in results['missing_metadata']:
            print(f"  - {item['source_name']}: {', '.join(item['issues'])}")
        print()
    
    if results['active_sources']:
        print("✅ ACTIVE SOURCES:")
        print("-" * 60)
        for source in sorted(results['active_sources']):
            print(f"  - {source}")
        print()
    
    # Summary
    print("="*60)
    print("Summary")
    print("="*60)
    coverage = (results['registered'] / results['total_scripts'] * 100) if results['total_scripts'] > 0 else 0
    print(f"Registration Coverage: {coverage:.1f}%")
    
    if results['unregistered']:
        print(f"⚠️  {len(results['unregistered'])} scripts need registration")
    
    if results['missing_metadata']:
        print(f"⚠️  {len(results['missing_metadata'])} sources need metadata updates")
    
    if not results['unregistered'] and not results['missing_metadata']:
        print("✅ All scripts are registered with complete metadata!")


if __name__ == '__main__':
    try:
        results = verify_source_registration()
        print_verification_report(results)
        
        # Exit with error code if there are issues
        if results['unregistered'] or results['missing_metadata']:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

