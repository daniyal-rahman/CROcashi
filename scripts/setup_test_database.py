#!/usr/bin/env python3
"""
Database Setup Script for Test Environment

This script sets up the required PostgreSQL extensions and creates the database
schema needed for the Cassava pipeline test.

Usage:
    python scripts/setup_test_database.py
"""

import os
import sys
from pathlib import Path

# Add the src directory to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import text
from ncfd.db.session import get_engine, session_scope
from ncfd.db.models import Base


def setup_database():
    """Setup the test database with required extensions and schema."""
    print("🔧 Setting up test database...")
    
    try:
        # Create required PostgreSQL extensions
        print("📦 Creating PostgreSQL extensions...")
        
        with session_scope() as session:
            extensions = [
                "CREATE EXTENSION IF NOT EXISTS pg_trgm;",  # For trigram indexes
                "CREATE EXTENSION IF NOT EXISTS btree_gin;",  # For GIN indexes on btree types
                "CREATE EXTENSION IF NOT EXISTS btree_gist;",  # For GiST indexes on btree types
                "CREATE EXTENSION IF NOT EXISTS unaccent;",  # For text search
            ]
            
            for extension_sql in extensions:
                try:
                    session.execute(text(extension_sql))
                    session.commit()
                    extension_name = extension_sql.split()[5].rstrip(';')
                    print(f"✅ Created extension: {extension_name}")
                except Exception as e:
                    print(f"⚠️  Could not create extension {extension_sql}: {e}")
                    session.rollback()
        
        # Create database schema
        print("🏗️  Creating database schema...")
        
        engine = get_engine()
        Base.metadata.create_all(engine)
        
        print("✅ Database setup completed successfully!")
        print("\n📋 Next steps:")
        print("1. Run the Cassava test: python tests/scripts/run_cassava_test_v2.py")
        print("2. Check results in: tests/logs/comprehensive_cassava_test_v2_results.json")
        
        return True
        
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        print("\n🔍 Troubleshooting:")
        print("1. Ensure PostgreSQL is running")
        print("2. Check database connection settings in .env")
        print("3. Verify database user has CREATE EXTENSION privileges")
        print("4. Install PostgreSQL contrib modules: sudo apt-get install postgresql-contrib")
        return False


if __name__ == "__main__":
    success = setup_database()
    sys.exit(0 if success else 1)
