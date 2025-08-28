#!/usr/bin/env python3
"""Quick investigation of current state for Checkpoint 1 fixes."""

from dotenv import load_dotenv
load_dotenv()

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.db.session import get_session
from ncfd.db.models import Document, DocumentUtility
from ncfd.ingest.smart_pubmed import SmartPubMedClient
from sqlalchemy import text

def investigate_u0_scores():
    """Check U0 score status."""
    print("🔍 Investigating U0 Score Status...")
    
    with get_session() as session:
        # Check U0 score nulls
        result = session.execute(text('''
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN u0_score IS NULL THEN 1 END) as null_scores,
                COUNT(CASE WHEN u0_score = 0 THEN 1 END) as zero_scores,
                AVG(u0_score) as avg_score,
                MIN(u0_score) as min_score,
                MAX(u0_score) as max_score
            FROM document_utilities
        '''))
        row = result.fetchone()
        stats = {
            'total': row[0],
            'null_scores': row[1], 
            'zero_scores': row[2],
            'avg_score': row[3],
            'min_score': row[4],
            'max_score': row[5]
        }
        
        print(f"📊 U0 Score Statistics:")
        print(f"   Total utilities: {stats['total']}")
        print(f"   NULL scores: {stats['null_scores']}")
        print(f"   Zero scores: {stats['zero_scores']}")
        print(f"   Average score: {stats['avg_score']:.3f}")
        print(f"   Score range: {stats['min_score']:.3f} - {stats['max_score']:.3f}")
        
        # Check top U0 scores
        top_scores = session.query(DocumentUtility).order_by(
            DocumentUtility.u0_score.desc()
        ).limit(5).all()
        
        print(f"\n🏆 Top 5 U0 Scores:")
        for i, util in enumerate(top_scores, 1):
            print(f"   {i}. U0: {util.u0_score:.3f} (doc_id: {util.doc_id})")

def investigate_document_schema():
    """Check document schema and content."""
    print("\n🗄️ Investigating Document Schema...")
    
    with get_session() as session:
        # Check document fields
        sample_doc = session.query(Document).first()
        if sample_doc:
            print(f"📋 Available Document Fields:")
            fields = [attr for attr in dir(sample_doc) if not attr.startswith('_')]
            for field in sorted(fields):
                print(f"   - {field}")
            
            # Check for key fields
            has_pub_types = hasattr(sample_doc, 'pub_types')
            has_article_type = hasattr(sample_doc, 'article_type')
            has_abstract = hasattr(sample_doc, 'abstract_text')
            has_fulltext = hasattr(sample_doc, 'fulltext_text')
            
            print(f"\n🔑 Key Field Status:")
            print(f"   pub_types: {'✅' if has_pub_types else '❌'}")
            print(f"   article_type: {'✅' if has_article_type else '❌'}")
            print(f"   abstract_text: {'✅' if has_abstract else '❌'}")
            print(f"   fulltext_text: {'✅' if has_fulltext else '❌'}")
            
            # Show sample titles
            docs = session.query(Document).limit(5).all()
            print(f"\n📚 Sample Document Titles:")
            for i, doc in enumerate(docs, 1):
                print(f"   {i}. {doc.title[:80]}...")

def investigate_pubmed_queries():
    """Test PubMed queries manually."""
    print("\n🔍 Testing PubMed Queries...")
    
    # Test NCT queries
    test_nct = "NCT05111574"
    
    pubmed_config = {
        'api_key': None,
        'base_url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
        'tool': 'NCFD-Investigation',
        'email': 'test@ncfd.com',
        'rate_limit_delay': 0.2,
        'max_retries': 3,
        'timeout': 30
    }
    
    client = SmartPubMedClient(pubmed_config)
    
    # Test different field tags
    queries = [
        (f'"{test_nct}"[si]', 'Secondary Source ID'),
        (f'"{test_nct}"[tiab]', 'Title/Abstract'),
        (f'"{test_nct}"[All Fields]', 'All Fields'),
        (f'"{test_nct}"[tiab] AND "Clinical Trial"[ptyp]', 'Title/Abstract + Clinical Trial filter'),
        (f'"{test_nct}"[tiab] AND ("Clinical Trial"[ptyp] OR "Randomized Controlled Trial"[ptyp])', 'Title/Abstract + RCT filter')
    ]
    
    for query, description in queries:
        try:
            results = client._esearch(query, retmax=5)
            count = results.get('esearchresult', {}).get('count', '0')
            print(f"   {description}: {count} results")
            if count != '0':
                print(f"     Query: {query}")
        except Exception as e:
            print(f"   {description}: ERROR - {e}")

def investigate_high_value_docs():
    """Check if we have any high-value documents."""
    print("\n🎯 Investigating High-Value Documents...")
    
    with get_session() as session:
        # Get top 10 utilities
        top_utilities = session.query(DocumentUtility).order_by(
            DocumentUtility.u0_score.desc()
        ).limit(10).all()
        
        # Get corresponding documents
        doc_ids = [util.doc_id for util in top_utilities]
        documents = session.query(Document).filter(Document.doc_id.in_(doc_ids)).all()
        doc_lookup = {doc.doc_id: doc for doc in documents}
        
        # Check for high-value terms
        high_value_terms = [
            'phase 3', 'phase iii', 'randomized', 'randomised', 
            'double-blind', 'double blind', 'NCT', 'clinical trial', 'rct'
        ]
        
        print(f"🔍 Checking top 10 documents for high-value terms:")
        high_value_found = 0
        
        for i, util in enumerate(top_utilities, 1):
            doc = doc_lookup.get(util.doc_id)
            if doc and doc.title:
                title_lower = doc.title.lower()
                matches = [term for term in high_value_terms if term in title_lower]
                
                if matches:
                    high_value_found += 1
                    print(f"   {i}. ✅ U0: {util.u0_score:.3f} - {doc.title[:80]}...")
                    print(f"      Matches: {', '.join(matches)}")
                else:
                    print(f"   {i}. ❌ U0: {util.u0_score:.3f} - {doc.title[:80]}...")
        
        print(f"\n📊 High-value documents found: {high_value_found}/10")

if __name__ == "__main__":
    print("🚀 Checkpoint 1 Investigation - Current State Analysis")
    print("=" * 60)
    
    try:
        investigate_u0_scores()
        investigate_document_schema()
        investigate_pubmed_queries()
        investigate_high_value_docs()
        
        print("\n" + "=" * 60)
        print("✅ Investigation complete!")
        
    except Exception as e:
        print(f"\n💥 Investigation failed: {e}")
        import traceback
        traceback.print_exc()
