#!/usr/bin/env python3
"""
Test script for database-integrated smart PubMed search.

This tests the full pipeline: search → triage → store in database.
"""

import logging
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_database_connection():
    """Test basic database connection."""
    
    logger.info("Testing database connection...")
    
    try:
        from ncfd.db.session import get_session
        
        # Use the session context manager properly
        with get_session() as session:
            logger.info("✅ Database session established successfully")
            
            # Test a simple query
            from sqlalchemy import text
            result = session.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            logger.info(f"✅ Test query successful: {row}")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False


def test_models_import():
    """Test that the document models can be imported."""
    
    logger.info("Testing document models import...")
    
    try:
        from ncfd.db.models import Document, DocumentTextPage, DocumentCitation, DocumentNote
        logger.info("✅ Document models imported successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Document models import failed: {e}")
        return False


def test_smart_search_db_import():
    """Test that the database-integrated smart search can be imported."""
    
    logger.info("Testing smart search DB import...")
    
    try:
        from ncfd.ingest.smart_pubmed_db import SmartPubMedDBClient, quick_smart_search_db
        logger.info("✅ Smart search DB imported successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Smart search DB import failed: {e}")
        return False


def test_database_integrated_search():
    """Test the full database-integrated search pipeline."""
    
    logger.info("Testing database-integrated search pipeline...")
    
    try:
        from ncfd.db.session import get_session
        from ncfd.ingest.smart_pubmed_db import quick_smart_search_db
        
        # Get a database session
        with get_session() as session:
            logger.info("✅ Database session established")
            
            # Test the database-integrated search
            logger.info("🔍 Testing Ruxolitinib search with database storage...")
            result = quick_smart_search_db(
                db_session=session,
                drug_name="ruxolitinib",
                disease="myelofibrosis"
            )
            
            logger.info(f"✅ Search completed successfully!")
            logger.info(f"   Decision: {result.search_result.decision}")
            logger.info(f"   Reason: {result.search_result.reason}")
            logger.info(f"   Total hits: {result.search_result.total_hits}")
            logger.info(f"   Documents created: {result.documents_created}")
            logger.info(f"   Documents updated: {result.documents_updated}")
            logger.info(f"   Errors: {len(result.errors)}")
            
            if result.errors:
                logger.warning("⚠️  Some errors occurred:")
                for error in result.errors[:3]:  # Show first 3 errors
                    logger.warning(f"   - {error}")
            
            return result
            
    except Exception as e:
        logger.error(f"❌ Database-integrated search failed: {e}")
        return None


def test_document_retrieval():
    """Test retrieving stored documents from the database."""
    
    logger.info("Testing document retrieval...")
    
    try:
        from ncfd.db.session import get_session
        from ncfd.db.models import Document, DocumentNote
        
        with get_session() as session:
            logger.info("✅ Database session established")
            
            # Count total documents
            total_docs = session.query(Document).count()
            logger.info(f"✅ Total documents in database: {total_docs}")
            
            if total_docs > 0:
                # Show some document details
                docs = session.query(Document).limit(5).all()
                logger.info(f"✅ Sample documents:")
                for i, doc in enumerate(docs):
                    logger.info(f"   {i+1}. PMID: {doc.pmid}")
                    logger.info(f"      Title: {doc.title[:60]}...")
                    logger.info(f"      Status: {doc.status}")
                    logger.info(f"      Created: {doc.discovered_at}")
                
                # Show document notes
                notes = session.query(DocumentNote).limit(5).all()
                logger.info(f"✅ Sample notes:")
                for i, note in enumerate(notes):
                    logger.info(f"   {i+1}. Type: {note.note_type}")
                    logger.info(f"      Text: {note.note_text[:80]}...")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Document retrieval failed: {e}")
        return False


def test_search_statistics():
    """Test getting search statistics from the database."""
    
    logger.info("Testing search statistics...")
    
    try:
        from ncfd.db.session import get_session
        from ncfd.ingest.smart_pubmed_db import SmartPubMedDBClient
        
        with get_session() as session:
            logger.info("✅ Database session established")
            
            client = SmartPubMedDBClient(session)
            stats = client.get_search_statistics()
            
            logger.info(f"✅ Search statistics:")
            logger.info(f"   Total documents: {stats['total_documents']}")
            logger.info(f"   Discovered documents: {stats['discovered_documents']}")
            logger.info(f"   Updated documents: {stats['updated_documents']}")
            logger.info(f"   By source type: {stats['by_source_type']}")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Search statistics failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Starting Database Integration Tests")
    logger.info("This tests the full pipeline: search → triage → store in database")
    
    # Test 1: Database connection
    logger.info("\n" + "="*60)
    logger.info("TEST 1: Database Connection")
    logger.info("="*60)
    db_connected = test_database_connection()
    
    # Test 2: Models import
    logger.info("\n" + "="*60)
    logger.info("TEST 2: Document Models Import")
    logger.info("="*60)
    models_imported = test_models_import()
    
    # Test 3: Smart search DB import
    logger.info("\n" + "="*60)
    logger.info("TEST 3: Smart Search DB Import")
    logger.info("="*60)
    smart_search_imported = test_smart_search_db_import()
    
    # Test 4: Database-integrated search
    logger.info("\n" + "="*60)
    logger.info("TEST 4: Database-Integrated Search")
    logger.info("="*60)
    if all([db_connected, models_imported, smart_search_imported]):
        search_result = test_database_integrated_search()
        search_working = search_result is not None
    else:
        search_working = False
        logger.warning("Skipping search test due to previous failures")
    
    # Test 5: Document retrieval
    logger.info("\n" + "="*60)
    logger.info("TEST 5: Document Retrieval")
    logger.info("="*60)
    if db_connected and models_imported:
        retrieval_working = test_document_retrieval()
    else:
        retrieval_working = False
        logger.warning("Skipping retrieval test due to previous failures")
    
    # Test 6: Search statistics
    logger.info("\n" + "="*60)
    logger.info("TEST 6: Search Statistics")
    logger.info("="*60)
    if all([db_connected, models_imported, smart_search_imported]):
        stats_working = test_search_statistics()
    else:
        stats_working = False
        logger.warning("Skipping statistics test due to previous failures")
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("SUMMARY")
    logger.info("="*60)
    logger.info(f"✅ Database Connection: {'PASSED' if db_connected else 'FAILED'}")
    logger.info(f"✅ Models Import: {'PASSED' if models_imported else 'FAILED'}")
    logger.info(f"✅ Smart Search DB Import: {'PASSED' if smart_search_imported else 'FAILED'}")
    logger.info(f"✅ Database-Integrated Search: {'PASSED' if search_working else 'FAILED'}")
    logger.info(f"✅ Document Retrieval: {'PASSED' if retrieval_working else 'FAILED'}")
    logger.info(f"✅ Search Statistics: {'PASSED' if stats_working else 'FAILED'}")
    
    if all([db_connected, models_imported, smart_search_imported, search_working, retrieval_working, stats_working]):
        logger.info("\n🎉 All tests passed! Database integration is working!")
        
        if search_result:
            logger.info(f"\n📊 Search Results Summary:")
            logger.info(f"   Decision: {search_result.search_result.decision}")
            logger.info(f"   Documents created: {search_result.documents_created}")
            logger.info(f"   Documents updated: {search_result.documents_updated}")
            logger.info(f"   Total hits: {search_result.search_result.total_hits}")
        
        logger.info("\n🚀 Next Steps:")
        logger.info("1. Scale up to more drugs and conditions")
        logger.info("2. Implement deep fetch for promoted papers")
        logger.info("3. Build asset alias system from stored documents")
        logger.info("4. Test linking heuristics with real data")
        
    else:
        logger.error("\n❌ Some tests failed. Check the errors above.")
        sys.exit(1)
    
    logger.info("\n🎯 Your smart PubMed search pipeline is now database-integrated!")
    logger.info("Ready to build your 3k+ paper corpus! 🚀")
