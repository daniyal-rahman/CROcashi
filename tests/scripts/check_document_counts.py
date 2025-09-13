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
# Note: retrieval_models was removed in favor of simplified Document table approach
# from ncfd.db.retrieval_models import RetrievalSession, RetrievalDocument, ProcessedDocument


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
        
        # Simplified document counts by processing stage
        print("\n📚 Document Counts by Processing Stage:")
        raw_doc_count = session.query(Document).filter(Document.processing_stage == 'raw').count()
        processed_doc_count = session.query(Document).filter(Document.processing_stage == 'processed').count()
        
        print(f"   • Raw Documents: {raw_doc_count}")
        print(f"   • Processed Documents: {processed_doc_count}")
        
        # Detailed breakdown by trial using DocumentLink
        print("\n🔬 Breakdown by Trial:")
        from ncfd.db.models import DocumentLink
        trial_breakdown = session.query(
            Trial.nct_id,
            Trial.brief_title,
            func.count(Document.doc_id).label('total_docs'),
            func.count(Document.doc_id).filter(Document.processing_stage == 'raw').label('raw_docs'),
            func.count(Document.doc_id).filter(Document.processing_stage == 'processed').label('processed_docs')
        ).outerjoin(DocumentLink, Trial.trial_id == DocumentLink.trial_id)\
         .outerjoin(Document, DocumentLink.doc_id == Document.doc_id)\
         .group_by(Trial.trial_id, Trial.nct_id, Trial.brief_title)\
         .all()
        
        for trial in trial_breakdown:
            print(f"   • {trial.nct_id}: {trial.raw_docs or 0} raw, {trial.processed_docs or 0} processed")
            if trial.brief_title:
                print(f"     Title: {trial.brief_title[:80]}{'...' if len(trial.brief_title) > 80 else ''}")
        
        # Sample raw documents
        if raw_doc_count > 0:
            print("\n📄 Sample Raw Documents:")
            sample_docs = session.query(Document)\
                .filter(Document.processing_stage == 'raw')\
                .order_by(Document.discovered_at.desc())\
                .limit(3)\
                .all()
            
            for doc in sample_docs:
                print(f"   • PMID {doc.pmid}: {doc.title[:60] if doc.title else 'No title'}{'...' if doc.title and len(doc.title) > 60 else ''}")
                print(f"     Status: {doc.status}, Discovered: {doc.discovered_at}")
                print()
        
        # Sample processed documents
        if processed_doc_count > 0:
            print("\n⚙️ Sample Processed Documents:")
            sample_processed = session.query(Document)\
                .filter(Document.processing_stage == 'processed')\
                .order_by(Document.parsed_at.desc())\
                .limit(3)\
                .all()
            
            for doc in sample_processed:
                print(f"   • PMID {doc.pmid}: {doc.title[:60] if doc.title else 'No title'}{'...' if doc.title and len(doc.title) > 60 else ''}")
                r_score_str = f"{doc.r_score:.3f}" if doc.r_score is not None else "N/A"
                s_score_str = f"{doc.s_score:.3f}" if doc.s_score is not None else "N/A"
                print(f"     R-Score: {r_score_str}, S-Score: {s_score_str}, R-Tier: {doc.r_tier}, S-Tier: {doc.s_tier}")
                print()
        
        # Summary
        print("\n📈 Summary:")
        if raw_doc_count > 0 and processed_doc_count > 0:
            processing_rate = (processed_doc_count / raw_doc_count) * 100
            print(f"   • Processing rate: {processing_rate:.1f}% ({processed_doc_count}/{raw_doc_count})")
        
        if raw_doc_count == 0:
            print("   • No raw documents found - pipeline may not have run yet")
        elif processed_doc_count == 0:
            print("   • No processed documents found - processing stage may not have completed")
        else:
            print("   • Simplified pipeline appears to be working correctly")


if __name__ == "__main__":
    try:
        check_document_counts()
    except Exception as e:
        print(f"❌ Error checking document counts: {e}")
        import traceback
        traceback.print_exc()
