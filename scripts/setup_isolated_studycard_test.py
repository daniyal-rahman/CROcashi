#!/usr/bin/env python3
"""
Setup script for isolated study card testing.

This script creates a minimal test database with:
- One company (Cassava Sciences)
- One trial (Phase 2 simufilam trial)
- One selected document (Phase 2 trial paper)
- One study card task

This allows us to test study card generation in isolation without running
the full pipeline.
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def setup_isolated_test_data():
    """Create the minimal test data for study card testing."""
    
    # Database connection
    database_url = os.getenv('DATABASE_URL', 'postgresql://ncfd:ncfd@localhost:5433/lit_test')
    
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Setting up isolated study card test data...")
        
        # Clear any existing test data
        print("Clearing existing test data...")
        cur.execute("DELETE FROM tasks WHERE task_key = 'test_studycard_1_phase2'")
        cur.execute("DELETE FROM trial_doc_candidates WHERE trial_id = 1")
        cur.execute("DELETE FROM document_links WHERE trial_id = 1")
        cur.execute("DELETE FROM document_text WHERE doc_id = 1")
        cur.execute("DELETE FROM documents WHERE doc_id = 1")
        cur.execute("DELETE FROM trials WHERE trial_id = 1")
        cur.execute("DELETE FROM companies WHERE company_id = 1")
        
        # Insert company
        print("Inserting company...")
        cur.execute("""
            INSERT INTO companies (company_id, name, name_norm, created_at, updated_at)
            VALUES (1, 'Cassava Sciences, Inc.', 'cassava sciences inc', NOW(), NOW())
        """)
        
        # Insert trial (Phase 2 trial for simufilam)
        print("Inserting trial...")
        cur.execute("""
            INSERT INTO trials (trial_id, nct_id, brief_title, sponsor_text, sponsor_company_id, 
                              phase, indication, status, created_at, updated_at)
            VALUES (1, 'NCT05515666', 'A Phase 2 Study of Simufilam in Patients with Alzheimer''s Disease', 
                   'Cassava Sciences, Inc.', 1, 'PHASE2', 'Alzheimer''s Disease', 'RECRUITING', NOW(), NOW())
        """)
        
        # Insert one selected study (the Phase 2 trial paper)
        print("Inserting document...")
        cur.execute("""
            INSERT INTO documents (doc_id, source_type, title, pmid, pmcid, nct_id, status, discovered_at)
            VALUES (1, 'Paper', 'Simufilam Reverses Aberrant Receptor Interactions of Filamin A in Alzheimer''s Disease', 
                   '37762230', 'PMC9706102', 'NCT05515666', 'discovered', NOW())
        """)
        
        # Insert full text for the study
        print("Inserting document text...")
        cur.execute("""
            INSERT INTO document_text (doc_id, fulltext_text, abstract_text)
            VALUES (1, %s, %s)
        """, (
            'This is a comprehensive study of simufilam in Alzheimer''s disease patients. The study demonstrates that simufilam reverses aberrant receptor interactions of filamin A, which is a key pathological mechanism in Alzheimer''s disease. The Phase 2 clinical trial NCT05515666 enrolled 64 patients with mild to moderate Alzheimer''s disease. Patients were randomized to receive either simufilam 100mg twice daily or placebo for 12 months. Primary endpoints included changes in ADAS-Cog scores and safety assessments. Secondary endpoints included biomarker analysis and neuroimaging studies. Results showed significant improvement in cognitive function as measured by ADAS-Cog scores in the simufilam group compared to placebo (p<0.001). The drug was well-tolerated with no serious adverse events reported. These findings support the continued development of simufilam as a potential treatment for Alzheimer''s disease.',
            'Simufilam is a small molecule drug candidate for Alzheimer''s disease that targets filamin A. This Phase 2 study demonstrates its efficacy and safety profile.'
        ))
        
        # Link the document to the trial
        print("Creating document link...")
        cur.execute("""
            INSERT INTO document_links (doc_id, trial_id, nct_id, asset_id, company_id, link_type)
            VALUES (1, 1, 'NCT05515666', NULL, 1, 'NCT_MATCH')
        """)
        
        # Mark as selected for study card processing
        print("Marking document as selected...")
        cur.execute("""
            INSERT INTO trial_doc_candidates (trial_id, doc_id, stage, selected)
            VALUES (1, 1, 'U1_abstract', TRUE)
        """)
        
        # Create a study card task
        print("Creating study card task...")
        cur.execute("""
            INSERT INTO tasks (task_type, task_key, trial_id, company_id, priority, status, payload, created_at, updated_at)
            VALUES ('STUDYCARD', 'test_studycard_1_phase2', 1, 1, 0, 'queued', '{"source": "manual_test", "trial_id": 1}', NOW(), NOW())
        """)
        
        # Verify the setup
        print("\nVerifying setup...")
        cur.execute("""
            SELECT 'Companies' as table_name, count(*) as count FROM companies
            UNION ALL
            SELECT 'Trials', count(*) FROM trials
            UNION ALL
            SELECT 'Documents', count(*) FROM documents
            UNION ALL
            SELECT 'Document Text', count(*) FROM document_text
            UNION ALL
            SELECT 'Document Links', count(*) FROM document_links
            UNION ALL
            SELECT 'Trial Doc Candidates', count(*) FROM trial_doc_candidates
            UNION ALL
            SELECT 'Tasks', count(*) FROM tasks
        """)
        
        results = cur.fetchall()
        for row in results:
            print(f"  {row['table_name']}: {row['count']}")
        
        # Show the trial details
        print("\nTrial details:")
        cur.execute("SELECT trial_id, nct_id, brief_title, phase, indication, status FROM trials WHERE trial_id = 1")
        trial = cur.fetchone()
        if trial:
            print(f"  Trial {trial['trial_id']}: {trial['nct_id']} - {trial['brief_title']}")
            print(f"  Phase: {trial['phase']}, Indication: {trial['indication']}, Status: {trial['status']}")
        
        # Show the document details
        print("\nDocument details:")
        cur.execute("SELECT doc_id, title, pmid, pmcid, nct_id, status FROM documents WHERE doc_id = 1")
        doc = cur.fetchone()
        if doc:
            print(f"  Document {doc['doc_id']}: {doc['title']}")
            print(f"  PMID: {doc['pmid']}, PMCID: {doc['pmcid']}, NCT: {doc['nct_id']}")
        
        # Show the task details
        print("\nTask details:")
        cur.execute("SELECT id, task_type, task_key, trial_id, status FROM tasks WHERE task_key = 'test_studycard_1_phase2'")
        task = cur.fetchone()
        if task:
            print(f"  Task {task['id']}: {task['task_type']} - {task['task_key']}")
            print(f"  Trial ID: {task['trial_id']}, Status: {task['status']}")
        
        print("\n✅ Isolated study card test data setup complete!")
        print("You can now run the study card worker to test study card generation.")
        
    except Exception as e:
        print(f"❌ Error setting up test data: {e}")
        raise
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

def clear_test_data():
    """Clear the test data."""
    database_url = os.getenv('DATABASE_URL', 'postgresql://ncfd:ncfd@localhost:5433/lit_test')
    
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cur = conn.cursor()
        
        print("Clearing test data...")
        cur.execute("DELETE FROM tasks WHERE task_key = 'test_studycard_1_phase2'")
        cur.execute("DELETE FROM trial_doc_candidates WHERE trial_id = 1")
        cur.execute("DELETE FROM document_links WHERE trial_id = 1")
        cur.execute("DELETE FROM document_text WHERE doc_id = 1")
        cur.execute("DELETE FROM documents WHERE doc_id = 1")
        cur.execute("DELETE FROM trials WHERE trial_id = 1")
        cur.execute("DELETE FROM companies WHERE company_id = 1")
        
        print("✅ Test data cleared!")
        
    except Exception as e:
        print(f"❌ Error clearing test data: {e}")
        raise
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Setup isolated study card test data")
    parser.add_argument("--clear", action="store_true", help="Clear test data instead of setting up")
    args = parser.parse_args()
    
    if args.clear:
        clear_test_data()
    else:
        setup_isolated_test_data()
