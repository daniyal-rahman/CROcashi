#!/usr/bin/env python3
"""
Check Document Counts in Database

This script checks how many raw (retrieval) and processed documents are stored
in the database using the dual-persistence strategy.

Usage:
    python tests/scripts/check_document_counts.py
"""

import sys
from pathlib import Path

# Add the src directory to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "tests"))

# Setup test environment before importing modules
from utils.env_loader import setup_test_environment
setup_test_environment(project_root)

from sqlalchemy import text, func
from ncfd.db.session import session_scope, reset_engine
from ncfd.db.models import Trial, Company, Document
from ncfd.db.retrieval_models import RetrievalSession, RetrievalDocument, ProcessedDocument


def check_document_counts():
    """Check document counts in the database."""
    print("🔍 Checking Document Counts in Database")
    print("=" * 60)
    
    # Reset engine to ensure it uses the test environment
    reset_engine()
    
    with session_scope() as session:
        # Basic entity counts
        print("\n📊 Basic Entity Counts:")
        company_count = session.query(Company).count()
        trial_count = session.query(Trial).count()
        document_count = session.query(Document).count()
        
        print(f"   • Companies: {company_count}")
        print(f"   • Trials: {trial_count}")
        print(f"   • Documents (legacy): {document_count}")
        
        # Dual-persistence document counts
        print("\n📚 Dual-Persistence Document Counts:")
        retrieval_session_count = session.query(RetrievalSession).count()
        retrieval_doc_count = session.query(RetrievalDocument).count()
        processed_doc_count = session.query(ProcessedDocument).count()
        
        print(f"   • Retrieval Sessions: {retrieval_session_count}")
        print(f"   • Raw Retrieval Documents: {retrieval_doc_count}")
        print(f"   • Processed Documents: {processed_doc_count}")
        
        # Detailed breakdown by trial
        print("\n🔬 Breakdown by Trial:")
        trial_breakdown = session.query(
            Trial.nct_id,
            Trial.brief_title,
            func.count(RetrievalDocument.id).label('retrieval_docs'),
            func.count(ProcessedDocument.id).label('processed_docs')
        ).outerjoin(RetrievalDocument, Trial.trial_id == RetrievalDocument.trial_id)\
         .outerjoin(ProcessedDocument, Trial.trial_id == ProcessedDocument.trial_id)\
         .group_by(Trial.trial_id, Trial.nct_id, Trial.brief_title)\
         .all()
        
        for trial in trial_breakdown:
            print(f"   • {trial.nct_id}: {trial.retrieval_docs} raw, {trial.processed_docs} processed")
            if trial.brief_title:
                print(f"     Title: {trial.brief_title[:80]}{'...' if len(trial.brief_title) > 80 else ''}")
        
        # Retrieval session details
        if retrieval_session_count > 0:
            print("\n📋 Recent Retrieval Sessions:")
            recent_sessions = session.query(RetrievalSession)\
                .order_by(RetrievalSession.created_at.desc())\
                .limit(5)\
                .all()
            
            for session_obj in recent_sessions:
                print(f"   • Session {session_obj.session_id[:8]}... (Trial {session_obj.trial_id})")
                print(f"     Status: {session_obj.status}")
                print(f"     Documents found: {session_obj.total_documents_found}")
                print(f"     After policy engine: {session_obj.documents_after_policy_engine}")
                print(f"     After guardrails: {session_obj.documents_after_guardrails}")
                print(f"     After processing: {session_obj.documents_after_processing}")
                print(f"     Created: {session_obj.created_at}")
                print()
        
        # Sample retrieval documents
        if retrieval_doc_count > 0:
            print("\n📄 Sample Retrieval Documents:")
            sample_docs = session.query(RetrievalDocument)\
                .order_by(RetrievalDocument.created_at.desc())\
                .limit(3)\
                .all()
            
            for doc in sample_docs:
                print(f"   • PMID {doc.pmid}: {doc.title[:60]}{'...' if doc.title and len(doc.title) > 60 else ''}")
                score_str = f"{doc.retrieval_score:.3f}" if doc.retrieval_score is not None else "N/A"
                print(f"     Tier: {doc.retrieval_tier}, Score: {score_str}")
                print(f"     Policy passed: {doc.policy_engine_passed}, Guardrails passed: {doc.guardrails_passed}")
                print()
        
        # Sample processed documents
        if processed_doc_count > 0:
            print("\n⚙️ Sample Processed Documents:")
            sample_processed = session.query(ProcessedDocument)\
                .order_by(ProcessedDocument.created_at.desc())\
                .limit(3)\
                .all()
            
            for doc in sample_processed:
                print(f"   • PMID {doc.pmid}: {doc.title[:60]}{'...' if doc.title and len(doc.title) > 60 else ''}")
                print(f"     R-Score: {doc.r_score:.3f}, S-Score: {doc.s_score:.3f}, Tier: {doc.rs_tier}")
                print()
        
        # Summary
        print("\n📈 Summary:")
        if retrieval_doc_count > 0 and processed_doc_count > 0:
            processing_rate = (processed_doc_count / retrieval_doc_count) * 100
            print(f"   • Processing rate: {processing_rate:.1f}% ({processed_doc_count}/{retrieval_doc_count})")
        
        if retrieval_doc_count == 0:
            print("   • No retrieval documents found - pipeline may not have run yet")
        elif processed_doc_count == 0:
            print("   • No processed documents found - processing stage may not have completed")
        else:
            print("   • Dual-persistence pipeline appears to be working correctly")


if __name__ == "__main__":
    try:
        check_document_counts()
    except Exception as e:
        print(f"❌ Error checking document counts: {e}")
        import traceback
        traceback.print_exc()
