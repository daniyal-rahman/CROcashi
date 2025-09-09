#!/usr/bin/env python3
"""
Load resolver ignore sponsor patterns into the database.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.db.session import get_db_session
from ncfd.config import get_config
from sqlalchemy import text


def load_patterns_file(file_path: str) -> Dict[str, Any]:
    """Load patterns from JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def load_patterns_to_database(patterns_data: Dict[str, Any]) -> Dict[str, Any]:
    """Load resolver ignore sponsor patterns to database."""
    
    stats = {
        "total_patterns": 0,
        "patterns_loaded": 0,
        "patterns_skipped": 0,
        "errors": []
    }
    
    with get_db_session() as session:
        for pattern_data in patterns_data.get("resolver_ignore_sponsor_patterns", []):
            pattern = pattern_data["pattern"]
            note = pattern_data["note"]
            
            stats["total_patterns"] += 1
            
            try:
                # Check if pattern already exists
                existing = session.execute(
                    text("SELECT pattern FROM resolver_ignore_sponsor WHERE pattern = :pattern"),
                    {"pattern": pattern}
                ).fetchone()
                
                if existing:
                    print(f"Pattern already exists: {pattern}")
                    stats["patterns_skipped"] += 1
                    continue
                
                # Insert new pattern
                session.execute(
                    text("""
                        INSERT INTO resolver_ignore_sponsor (pattern, note)
                        VALUES (:pattern, :note)
                    """),
                    {
                        "pattern": pattern,
                        "note": note
                    }
                )
                
                stats["patterns_loaded"] += 1
                print(f"Loaded pattern: {pattern} - {note}")
                
            except Exception as e:
                error_msg = f"Error loading pattern '{pattern}': {e}"
                print(f"❌ {error_msg}")
                stats["errors"].append(error_msg)
        
        # Commit all changes
        session.commit()
    
    return stats


def main():
    """Main entry point."""
    # File path
    patterns_file = Path("data/resolver_ignore_sponsor_seed.json")
    
    if not patterns_file.exists():
        print(f"❌ Patterns file not found: {patterns_file}")
        return 1
    
    try:
        # Load patterns from file
        print(f"📁 Loading patterns from: {patterns_file}")
        patterns_data = load_patterns_file(str(patterns_file))
        
        # Load to database
        stats = load_patterns_to_database(patterns_data)
        
        # Print results
        print(f"\n📊 Resolver Ignore Sponsor Patterns Loading Results:")
        print(f"  Total patterns in file: {stats['total_patterns']}")
        print(f"  Patterns loaded: {stats['patterns_loaded']}")
        print(f"  Patterns skipped (existing): {stats['patterns_skipped']}")
        
        if stats["errors"]:
            print(f"\n❌ Errors ({len(stats['errors'])}):")
            for error in stats["errors"][:5]:  # Show first 5 errors
                print(f"  - {error}")
            if len(stats["errors"]) > 5:
                print(f"  ... and {len(stats['errors']) - 5} more errors")
        
        if stats["patterns_loaded"] > 0:
            print(f"\n✅ Successfully loaded {stats['patterns_loaded']} patterns")
        else:
            print(f"\n⚠️  No new patterns loaded (all may already exist)")
        
    except Exception as e:
        print(f"❌ Failed to load patterns: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
