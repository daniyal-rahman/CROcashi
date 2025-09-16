#!/usr/bin/env python3
"""
Clean up old resolver tables after migration to simplified schema.

This script removes the old resolver tables that are no longer needed.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def cleanup_old_resolver_tables():
    """Remove old resolver tables."""
    
    # Get database URL
    database_url = os.environ.get('DATABASE_URL', 'postgresql://ncfd:ncfd@localhost:5433/ncfd')
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    
    # Tables to remove (in dependency order)
    tables_to_remove = [
        'resolver_features',
        'resolver_decisions', 
        'review_queue',
        'resolver_inputs',
        'resolver_runs',
        'resolver_det_rules',
        'resolver_ignore_sponsor'
    ]
    
    with Session() as session:
        try:
            print("🧹 Cleaning up old resolver tables...")
            
            for table in tables_to_remove:
                # Check if table exists
                result = session.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = :table_name
                    )
                """), {"table_name": table})
                
                table_exists = result.fetchone()[0]
                
                if table_exists:
                    # Get row count before dropping
                    result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    row_count = result.fetchone()[0]
                    
                    # Drop table
                    session.execute(text(f"DROP TABLE {table} CASCADE"))
                    print(f"  ✅ Dropped {table} ({row_count} rows)")
                else:
                    print(f"  ⚠️  Table {table} does not exist, skipping")
            
            session.commit()
            print("\n✅ Cleanup completed successfully!")
            
        except Exception as e:
            session.rollback()
            print(f"❌ Error during cleanup: {e}")
            raise


if __name__ == "__main__":
    cleanup_old_resolver_tables()
