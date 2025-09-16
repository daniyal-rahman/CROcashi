#!/usr/bin/env python3
"""
Migrate existing resolver data to simplified schema.

This script migrates data from the old resolver tables to the new simplified schema.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def migrate_resolver_data():
    """Migrate existing resolver data to new schema."""
    
    # Get database URL
    database_url = os.environ.get('DATABASE_URL', 'postgresql://ncfd:ncfd@localhost:5433/ncfd')
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    
    with Session() as session:
        try:
            # 1. Migrate resolver_decisions to sponsor_resolutions
            print("🔄 Migrating resolver_decisions to sponsor_resolutions...")
            
            result = session.execute(text("""
                INSERT INTO sponsor_resolutions (
                    nct_id, sponsor_text, sponsor_text_norm, company_id, 
                    match_method, confidence, evidence, created_at
                )
                SELECT 
                    nct_id,
                    sponsor_text,
                    sponsor_text_norm,
                    company_id,
                    CASE 
                        WHEN decided_by LIKE 'det_%' THEN 'exact'
                        WHEN decided_by LIKE 'prob_%' THEN 'fuzzy'
                        WHEN decided_by LIKE 'llm_%' THEN 'llm'
                        ELSE 'manual'
                    END as match_method,
                    COALESCE(p_match, 0.5) as confidence,
                    jsonb_build_object(
                        'features', features_jsonb,
                        'evidence', evidence_jsonb,
                        'decided_by', decided_by,
                        'notes', notes_md
                    ) as evidence,
                    NOW() as created_at
                FROM resolver_decisions
                WHERE company_id IS NOT NULL
                ON CONFLICT (nct_id, sponsor_text_norm) DO NOTHING
            """))
            
            print(f"✅ Migrated {result.rowcount} decisions to sponsor_resolutions")
            
            # 2. Migrate review_queue to manual_review_queue
            print("🔄 Migrating review_queue to manual_review_queue...")
            
            result = session.execute(text("""
                INSERT INTO manual_review_queue (
                    nct_id, sponsor_text, status, assigned_company_id, 
                    notes, created_at, updated_at
                )
                SELECT 
                    nct_id,
                    sponsor_text,
                    CASE 
                        WHEN status = 'pending' THEN 'pending'
                        WHEN status = 'completed' THEN 'completed'
                        ELSE 'skipped'
                    END as status,
                    suggested_company as assigned_company_id,
                    notes_md as notes,
                    created_at,
                    updated_at
                FROM review_queue
                WHERE status IN ('pending', 'completed', 'skipped')
                ON CONFLICT DO NOTHING
            """))
            
            print(f"✅ Migrated {result.rowcount} items to manual_review_queue")
            
            # 3. Migrate LLM discoveries from resolver_decisions
            print("🔄 Migrating LLM discoveries...")
            
            result = session.execute(text("""
                INSERT INTO llm_discoveries (
                    nct_id, sponsor_text, discovered_company_id, 
                    llm_response, confidence, created_at
                )
                SELECT 
                    nct_id,
                    sponsor_text,
                    company_id as discovered_company_id,
                    jsonb_build_object(
                        'features', features_jsonb,
                        'evidence', evidence_jsonb,
                        'decided_by', decided_by,
                        'notes', notes_md
                    ) as llm_response,
                    COALESCE(p_match, 0.5) as confidence,
                    NOW() as created_at
                FROM resolver_decisions
                WHERE decided_by LIKE 'llm_%' 
                AND company_id IS NOT NULL
                ON CONFLICT DO NOTHING
            """))
            
            print(f"✅ Migrated {result.rowcount} LLM discoveries")
            
            # 4. Show migration summary
            print("\n📊 Migration Summary:")
            
            # Count records in new tables
            result = session.execute(text("SELECT COUNT(*) FROM sponsor_resolutions"))
            count = result.fetchone()[0]
            print(f"  sponsor_resolutions: {count} records")
            
            result = session.execute(text("SELECT COUNT(*) FROM manual_review_queue"))
            count = result.fetchone()[0]
            print(f"  manual_review_queue: {count} records")
            
            result = session.execute(text("SELECT COUNT(*) FROM llm_discoveries"))
            count = result.fetchone()[0]
            print(f"  llm_discoveries: {count} records")
            
            result = session.execute(text("SELECT COUNT(*) FROM academic_blacklist"))
            count = result.fetchone()[0]
            print(f"  academic_blacklist: {count} patterns")
            
            session.commit()
            print("\n✅ Migration completed successfully!")
            
        except Exception as e:
            session.rollback()
            print(f"❌ Error during migration: {e}")
            raise


if __name__ == "__main__":
    migrate_resolver_data()
