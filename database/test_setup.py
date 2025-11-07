#!/usr/bin/env python3
"""Test database setup."""
from database.config import get_db_session, engine
from database.models import Company, Drug, ClinicalTrial
from sqlalchemy import text

print("=" * 60)
print("Database Setup Verification")
print("=" * 60)

# Test connection
try:
    with get_db_session() as session:
        print("✓ Database connection successful!")
        
        # Count rows in key tables
        companies = session.query(Company).count()
        drugs = session.query(Drug).count()
        trials = session.query(ClinicalTrial).count()
        
        print(f"\nTable row counts:")
        print(f"  - Companies: {companies}")
        print(f"  - Drugs: {drugs}")
        print(f"  - Clinical Trials: {trials}")
        
        # Check total tables
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            table_count = result.fetchone()[0]
            print(f"\n✓ Total tables in database: {table_count}")
            
            # Check extensions
            result = conn.execute(text("""
                SELECT extname FROM pg_extension 
                WHERE extname IN ('uuid-ossp', 'pg_trgm')
            """))
            extensions = [row[0] for row in result]
            print(f"✓ Extensions installed: {', '.join(extensions)}")
        
        print("\n" + "=" * 60)
        print("✓ Database is ready for use!")
        print("=" * 60)
        
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

