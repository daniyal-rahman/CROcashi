#!/usr/bin/env python3
"""
Single Trial Test Verification Script

Provides SQL queries and checks to verify the progress of single-trial testing.
Run this script to check the state of your test at any point.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

# Add the src directory to the Python path
src_path = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(src_path))

from ncfd.db.session import session_scope
from sqlalchemy import text


def setup_logging():
    """Setup logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def run_query(session, query: str, description: str) -> List[Dict]:
    """Run a SQL query and return results."""
    try:
        result = session.execute(text(query))
        rows = [dict(row._mapping) for row in result]
        print(f"\n=== {description} ===")
        if rows:
            for row in rows:
                print(f"  {row}")
        else:
            print("  No results found")
        return rows
    except Exception as e:
        print(f"\n=== {description} (ERROR) ===")
        print(f"  Error: {e}")
        return []


def verify_trial_setup(session, nct_id: str = "NCT04994483"):
    """Verify the trial and company are properly set up."""
    queries = [
        (
            f"""
            SELECT t.trial_id, t.nct_id, t.sponsor_company_id, c.name as company_name, 
                   t.brief_title, t.indication, t.status, t.phase
            FROM trials t
            LEFT JOIN companies c ON c.company_id = t.sponsor_company_id
            WHERE t.nct_id = '{nct_id}'
            """,
            "1. Trial and Company Setup"
        ),
        (
            """
            SELECT status, task_type, COUNT(*) as count
            FROM tasks 
            GROUP BY status, task_type 
            ORDER BY task_type, status
            """,
            "2. Task Queue Status"
        )
    ]
    
    results = {}
    for query, description in queries:
        results[description] = run_query(session, query, description)
    
    return results


def verify_u1_processing(session, trial_id: Optional[int] = None):
    """Verify U1 processing results."""
    trial_filter = f"WHERE c.trial_id = {trial_id}" if trial_id else ""
    
    queries = [
        (
            f"""
            SELECT d.pmid, d.status, dt.abstract_text IS NOT NULL as has_abstract,
                   dt.fulltext_text IS NOT NULL as has_fulltext
            FROM documents d
            JOIN trial_doc_candidates c ON c.doc_id = d.doc_id
            LEFT JOIN document_text dt ON dt.doc_id = d.doc_id
            {trial_filter}
            ORDER BY d.doc_id
            LIMIT 10
            """,
            "3. Documents and Text Content (First 10)"
        ),
        (
            f"""
            SELECT COUNT(*) as total_documents
            FROM documents d
            JOIN trial_doc_candidates c ON c.doc_id = d.doc_id
            {trial_filter}
            """,
            "4. Total Documents Count"
        ),
        (
            f"""
            SELECT COUNT(*) as abstracts_with_text
            FROM document_text dt
            JOIN documents d ON d.doc_id = dt.doc_id
            JOIN trial_doc_candidates c ON c.doc_id = d.doc_id
            {trial_filter}
            AND dt.abstract_text IS NOT NULL
            """,
            "5. Documents with Abstract Text"
        ),
        (
            f"""
            SELECT rs."R_score", rs."S_score", COUNT(*) as count
            FROM doc_rs_scores rs
            {trial_filter.replace('c.trial_id', 'rs.trial_id') if trial_filter else ''}
            GROUP BY rs."R_score", rs."S_score"
            ORDER BY rs."R_score" DESC, rs."S_score" DESC
            LIMIT 10
            """,
            "6. R/S Score Distribution (Top 10)"
        )
    ]
    
    results = {}
    for query, description in queries:
        results[description] = run_query(session, query, description)
    
    return results


def verify_oa_processing(session, trial_id: Optional[int] = None):
    """Verify OA processing results."""
    trial_filter = f"WHERE c.trial_id = {trial_id}" if trial_id else ""
    
    queries = [
        (
            f"""
            SELECT COUNT(*) as fulltext_documents
            FROM document_text dt
            JOIN documents d ON d.doc_id = dt.doc_id
            JOIN trial_doc_candidates c ON c.doc_id = d.doc_id
            {trial_filter}
            AND dt.fulltext_text IS NOT NULL
            """,
            "7. Documents with Full Text"
        ),
        (
            f"""
            SELECT d.pmid, LENGTH(dt.fulltext_text) as fulltext_length
            FROM documents d
            JOIN trial_doc_candidates c ON c.doc_id = d.doc_id
            JOIN document_text dt ON dt.doc_id = d.doc_id
            {trial_filter}
            AND dt.fulltext_text IS NOT NULL
            ORDER BY LENGTH(dt.fulltext_text) DESC
            LIMIT 5
            """,
            "8. Full Text Documents (Top 5 by Length)"
        )
    ]
    
    results = {}
    for query, description in queries:
        results[description] = run_query(session, query, description)
    
    return results


def verify_study_card_processing(session, trial_id: Optional[int] = None):
    """Verify study card processing results."""
    trial_filter = f"WHERE trial_id = {trial_id}" if trial_id else ""
    
    queries = [
        (
            f"""
            SELECT * FROM trial_lit_state 
            {trial_filter}
            """,
            "9. Trial Literature State"
        ),
        (
            """
            SELECT task_type, status, COUNT(*) as count,
                   MIN(created_at) as earliest,
                   MAX(updated_at) as latest
            FROM tasks 
            GROUP BY task_type, status
            ORDER BY task_type, status
            """,
            "10. Task Progress Timeline"
        )
    ]
    
    results = {}
    for query, description in queries:
        results[description] = run_query(session, query, description)
    
    return results


def get_trial_summary(session, nct_id: str = "NCT04994483") -> Dict[str, Any]:
    """Get a comprehensive summary of the trial processing status."""
    summary = {}
    
    # Get trial info
    trial_query = f"""
    SELECT t.trial_id, t.nct_id, c.name as company_name
    FROM trials t
    LEFT JOIN companies c ON c.company_id = t.sponsor_company_id
    WHERE t.nct_id = '{nct_id}'
    """
    
    trial_result = session.execute(text(trial_query)).fetchone()
    if not trial_result:
        return {"error": f"Trial {nct_id} not found"}
    
    trial_id = trial_result.trial_id
    summary['trial_info'] = dict(trial_result._mapping)
    
    # Get processing stats
    stats_queries = {
        'total_tasks': f"SELECT COUNT(*) as count FROM tasks WHERE trial_id = {trial_id}",
        'completed_tasks': f"SELECT COUNT(*) as count FROM tasks WHERE trial_id = {trial_id} AND status = 'done'",
        'failed_tasks': f"SELECT COUNT(*) as count FROM tasks WHERE trial_id = {trial_id} AND status = 'failed'",
        'documents_found': f"SELECT COUNT(*) as count FROM trial_doc_candidates WHERE trial_id = {trial_id}",
        'abstracts_processed': f"""
            SELECT COUNT(*) as count 
            FROM document_text dt
            JOIN documents d ON d.doc_id = dt.doc_id
            JOIN trial_doc_candidates c ON c.doc_id = d.doc_id
            WHERE c.trial_id = {trial_id} AND dt.abstract_text IS NOT NULL
        """,
        'fulltext_processed': f"""
            SELECT COUNT(*) as count 
            FROM document_text dt
            JOIN documents d ON d.doc_id = dt.doc_id
            JOIN trial_doc_candidates c ON c.doc_id = d.doc_id
            WHERE c.trial_id = {trial_id} AND dt.fulltext_text IS NOT NULL
        """,
        'rs_scores_generated': f"SELECT COUNT(*) as count FROM doc_rs_scores WHERE trial_id = {trial_id}",
    }
    
    for key, query in stats_queries.items():
        try:
            result = session.execute(text(query)).fetchone()
            summary[key] = result.count if result else 0
        except Exception as e:
            summary[key] = f"Error: {e}"
    
    return summary


def main():
    """Main verification function."""
    parser = argparse.ArgumentParser(description='Verify Single Trial Test Progress')
    parser.add_argument('--nct-id', default='NCT04994483', 
                       help='NCT ID of the trial to verify')
    parser.add_argument('--summary-only', action='store_true',
                       help='Show only summary information')
    parser.add_argument('--check-all', action='store_true',
                       help='Run all verification checks')
    args = parser.parse_args()
    
    setup_logging()
    
    # Validate database connection
    if not os.getenv('DATABASE_URL'):
        print("Error: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    print(f"🔍 Verifying single trial test progress for {args.nct_id}")
    print("=" * 60)
    
    try:
        with session_scope() as session:
            # Get trial summary
            summary = get_trial_summary(session, args.nct_id)
            
            if 'error' in summary:
                print(f"❌ {summary['error']}")
                return
            
            # Print summary
            print(f"\n📊 TRIAL SUMMARY")
            print(f"Trial ID: {summary['trial_info']['trial_id']}")
            print(f"NCT ID: {summary['trial_info']['nct_id']}")
            print(f"Company: {summary['trial_info']['company_name']}")
            print(f"Total Tasks: {summary['total_tasks']}")
            print(f"Completed Tasks: {summary['completed_tasks']}")
            print(f"Failed Tasks: {summary['failed_tasks']}")
            print(f"Documents Found: {summary['documents_found']}")
            print(f"Abstracts Processed: {summary['abstracts_processed']}")
            print(f"Full Text Processed: {summary['fulltext_processed']}")
            print(f"R/S Scores Generated: {summary['rs_scores_generated']}")
            
            if args.summary_only:
                return
            
            trial_id = summary['trial_info']['trial_id']
            
            # Run detailed verification
            if args.check_all or True:  # Default to checking all
                verify_trial_setup(session, args.nct_id)
                verify_u1_processing(session, trial_id)
                verify_oa_processing(session, trial_id)
                verify_study_card_processing(session, trial_id)
            
            print(f"\n✅ Verification complete for trial {args.nct_id}")
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
