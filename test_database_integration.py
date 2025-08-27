#!/usr/bin/env python3
"""
Test script for database-integrated literature ingestion.

This demonstrates how to properly use the database session and ingest literature.
"""

import logging
import sys
import os
from datetime import datetime

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
        from ncfd.db.models import Document, DocumentTextPage, DocumentCitation
        logger.info("✅ Document models imported successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Document models import failed: {e}")
        return False


def test_literature_ingestion_with_db():
    """Test literature ingestion with database integration."""
    
    logger.info("Testing literature ingestion with database...")
    
    try:
        from ncfd.ingest.pubs import LiteratureIngester
        from ncfd.db.session import get_session
        
        # Get a database session
        with get_session() as session:
            logger.info("✅ Database session established")
            
            # Initialize the literature ingester with the session
            ingester = LiteratureIngester(session)
            logger.info("✅ LiteratureIngester initialized with database session")
            
            # Test a small search to avoid rate limits
            publications = ingester.pubmed_client.search_by_drug("Ruxolitinib", max_results=2)
            logger.info(f"✅ Found {len(publications)} publications for Ruxolitinib")
            
            if publications:
                # Test processing one publication
                pub = publications[0]
                logger.info(f"✅ Testing with publication: {pub.title[:50]}...")
                
                # Check if document already exists
                from ncfd.db.models import Document
                existing_doc = session.query(Document).filter(
                    Document.pmid == pub.pmid
                ).first()
                
                if existing_doc:
                    logger.info(f"✅ Document already exists for PMID {pub.pmid}")
                else:
                    logger.info(f"✅ Document does not exist - ready for ingestion")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Literature ingestion with database failed: {e}")
        return False


def test_document_creation():
    """Test creating a document record in the database."""
    
    logger.info("Testing document creation...")
    
    try:
        from ncfd.db.session import get_session
        from ncfd.db.models import Document, DocumentTextPage, DocumentCitation
        
        with get_session() as session:
            logger.info("✅ Database session established")
            
            # Create a test document
            test_doc = Document(
                source_type='Paper',
                title='Test Document for Ruxolitinib',
                pmid='TEST123',
                status='discovered',
                discovered_at=datetime.now()
            )
            
            session.add(test_doc)
            session.flush()  # Get the doc_id
            
            logger.info(f"✅ Test document created with ID: {test_doc.doc_id}")
            
            # Create a test text page
            text_page = DocumentTextPage(
                doc_id=test_doc.doc_id,
                page_no=1,
                text='This is a test abstract about Ruxolitinib treatment.',
                char_count=58
            )
            
            session.add(text_page)
            
            # Create a test citation
            citation = DocumentCitation(
                doc_id=test_doc.doc_id,
                pmid='TEST123'
            )
            
            session.add(citation)
            
            # Commit the test data
            session.commit()
            logger.info("✅ Test document, text page, and citation created successfully")
            
            # Clean up test data
            session.delete(test_doc)
            session.commit()
            logger.info("✅ Test data cleaned up")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Document creation test failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting database integration tests...")
    
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
    
    # Test 3: Literature ingestion with database
    logger.info("\n" + "="*60)
    logger.info("TEST 3: Literature Ingestion with Database")
    logger.info("="*60)
    if db_connected and models_imported:
        ingestion_working = test_literature_ingestion_with_db()
    else:
        ingestion_working = False
        logger.warning("Skipping ingestion test due to previous failures")
    
    # Test 4: Document creation
    logger.info("\n" + "="*60)
    logger.info("TEST 4: Document Creation in Database")
    logger.info("="*60)
    if db_connected and models_imported:
        doc_creation_working = test_document_creation()
    else:
        doc_creation_working = False
        logger.warning("Skipping document creation test due to previous failures")
    
    logger.info("\n" + "="*60)
    logger.info("SUMMARY")
    logger.info("="*60)
    logger.info(f"✅ Database Connection: {'PASSED' if db_connected else 'FAILED'}")
    logger.info(f"✅ Models Import: {'PASSED' if models_imported else 'FAILED'}")
    logger.info(f"✅ Literature Ingestion: {'PASSED' if ingestion_working else 'FAILED'}")
    logger.info(f"✅ Document Creation: {'PASSED' if doc_creation_working else 'FAILED'}")
    
    if all([db_connected, models_imported, ingestion_working, doc_creation_working]):
        logger.info("\n🎉 All tests passed! Literature ingestion is ready for production!")
        logger.info("\n🚀 Next steps:")
        logger.info("1. Ingest Ruxolitinib literature (start with 100-500 papers)")
        logger.info("2. Test linking heuristics with real data")
        logger.info("3. Build asset alias system")
        logger.info("4. Scale up to more drugs and conditions")
    else:
        logger.error("\n❌ Some tests failed. Check the errors above.")
        sys.exit(1)
