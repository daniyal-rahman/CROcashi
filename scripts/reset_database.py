#!/usr/bin/env python3
"""
Reset database by dropping all tables and recreating schema.
WARNING: This will delete all data!
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from database.config import get_db_session, engine
from database.models.base import Base

def reset_database():
    """Drop all tables and recreate schema."""
    print("=" * 80)
    print("RESETTING DATABASE")
    print("=" * 80)
    print("WARNING: This will delete ALL data!")
    print()
    
    try:
        # Drop all tables
        print("Dropping all tables...")
        with get_db_session() as session:
            # Get all table names
            result = session.execute(text("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public'
            """))
            tables = [row[0] for row in result]
            
            if tables:
                # Drop all tables with CASCADE
                for table in tables:
                    print(f"  Dropping {table}...")
                    session.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                session.commit()
                print(f"✓ Dropped {len(tables)} tables")
            else:
                print("  No tables to drop")
        
        # Recreate schema
        print("\nRecreating schema...")
        Base.metadata.create_all(engine)
        print("✓ Schema recreated")
        
        print("\n" + "=" * 80)
        print("DATABASE RESET COMPLETE")
        print("=" * 80)
        return True
        
    except Exception as e:
        print(f"\n❌ Error resetting database: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Reset database (WARNING: Deletes all data!)')
    parser.add_argument('--confirm', action='store_true', help='Confirm reset (required)')
    
    args = parser.parse_args()
    
    if not args.confirm:
        print("ERROR: This will delete ALL data!")
        print("Use --confirm flag to proceed")
        sys.exit(1)
    
    success = reset_database()
    sys.exit(0 if success else 1)

