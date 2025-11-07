#!/usr/bin/env python3
"""
Database setup script - creates database and initializes schema.
"""
import sys
import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from database.config import DATABASE_URL, engine
from database.models import Base


def create_database_if_not_exists():
    """Create database if it doesn't exist."""
    # Parse DATABASE_URL to get connection details
    db_url = DATABASE_URL
    # Extract database name
    db_name = db_url.split('/')[-1]
    # Get base URL without database name
    base_url = '/'.join(db_url.split('/')[:-1])
    
    print(f"Checking if database '{db_name}' exists...")
    
    try:
        # Try to connect to the database
        test_engine = create_engine(db_url)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"✓ Database '{db_name}' already exists")
        return True
    except OperationalError as e:
        if "does not exist" in str(e) or "database" in str(e).lower():
            print(f"Database '{db_name}' does not exist")
            print(f"\n⚠️  Please create the database manually:")
            print(f"   psql -U ncfd -d postgres")
            print(f"   CREATE DATABASE {db_name};")
            print(f"   \\q")
            print(f"\nOr if you have superuser access:")
            print(f"   createdb -U postgres {db_name}")
            return False
        else:
            print(f"✗ Connection error: {e}")
            return False


def create_extensions():
    """Create PostgreSQL extensions."""
    print("\nCreating PostgreSQL extensions...")
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"pg_trgm\";"))
            conn.commit()
        print("✓ Extensions created successfully")
        return True
    except Exception as e:
        print(f"✗ Error creating extensions: {e}")
        return False


def create_tables():
    """Create all database tables."""
    print("\nCreating database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print(f"✓ Created {len(Base.metadata.tables)} tables successfully")
        return True
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return False


def verify_setup():
    """Verify database setup."""
    print("\nVerifying setup...")
    try:
        with engine.connect() as conn:
            # Check extensions
            result = conn.execute(text("""
                SELECT extname FROM pg_extension 
                WHERE extname IN ('uuid-ossp', 'pg_trgm')
            """))
            extensions = [row[0] for row in result]
            print(f"✓ Extensions: {', '.join(extensions)}")
            
            # Check tables
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            table_count = result.fetchone()[0]
            print(f"✓ Tables created: {table_count}")
            
            if table_count >= 40:
                print("\n✓ Database setup complete!")
                return True
            else:
                print(f"\n⚠️  Expected ~45 tables, found {table_count}")
                return False
    except Exception as e:
        print(f"✗ Verification error: {e}")
        return False


def main():
    """Main setup function."""
    print("=" * 60)
    print("Biotech Knowledge Graph Database Setup")
    print("=" * 60)
    print(f"\nDatabase URL: {DATABASE_URL.split('@')[0]}@...")
    
    # Check if database exists
    if not create_database_if_not_exists():
        print("\n❌ Please create the database first, then run this script again.")
        sys.exit(1)
    
    # Create extensions
    if not create_extensions():
        print("\n⚠️  Extensions creation failed, but continuing...")
    
    # Create tables
    if not create_tables():
        print("\n❌ Table creation failed")
        sys.exit(1)
    
    # Verify
    if verify_setup():
        print("\n" + "=" * 60)
        print("✓ Database initialization complete!")
        print("\nNext steps:")
        print("1. Create Alembic migration: alembic revision --autogenerate -m 'Initial schema'")
        print("2. Review migration file in database/migrations/versions/")
        print("3. Apply migration: alembic upgrade head")
        print("=" * 60)
    else:
        print("\n⚠️  Setup completed with warnings")
        sys.exit(1)


if __name__ == '__main__':
    main()

