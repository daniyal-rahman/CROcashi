#!/usr/bin/env python3
"""
Test script for literature ingestion functionality.

This demonstrates how to use the pubs.py module to ingest literature for a clinical trial.
"""

import logging
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from ncfd.db.session import get_session
from ncfd.ingest.pubs import LiteratureIngester

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_literature_ingestion():
    """Test the literature ingestion for a sample clinical trial."""
    
    # Sample NCT ID (you can replace this with a real one)
    nct_id = "NCT04331665"  # Example: COVID-19 trial
    
    logger.info(f"Testing literature ingestion for trial: {nct_id}")
    
    try:
        # Get database session
        db_session = get_session()
        
        # Initialize literature ingester
        ingester = LiteratureIngester(db_session)
        
        # Ingest literature for the trial
        results = ingester.ingest_trial_literature(nct_id, max_pubs=10)
        
        # Print results
        logger.info("=== Literature Ingestion Results ===")
        logger.info(f"NCT ID: {results['nct_id']}")
        logger.info(f"Publications found: {results['publications_found']}")
        logger.info(f"Publications processed: {results['publications_processed']}")
        logger.info(f"Documents created: {results['documents_created']}")
        
        if results['errors']:
            logger.warning(f"Errors encountered: {len(results['errors'])}")
            for error in results['errors'][:3]:  # Show first 3 errors
                logger.warning(f"  - {error}")
        
        # Query the database to see what was created
        from ncfd.db.models import Document, DocumentTextPage, DocumentCitation
        
        # Count documents
        doc_count = db_session.query(Document).filter(
            Document.nct_id == nct_id
        ).count()
        
        # Count text pages
        text_page_count = db_session.query(DocumentTextPage).join(Document).filter(
            Document.nct_id == nct_id
        ).count()
        
        # Count citations
        citation_count = db_session.query(DocumentCitation).join(Document).filter(
            Document.nct_id == nct_id
        ).count()
        
        logger.info("=== Database Results ===")
        logger.info(f"Documents in database: {doc_count}")
        logger.info(f"Text pages in database: {text_page_count}")
        logger.info(f"Citations in database: {citation_count}")
        
        # Show sample documents
        if doc_count > 0:
            logger.info("=== Sample Documents ===")
            docs = db_session.query(Document).filter(
                Document.nct_id == nct_id
            ).limit(3).all()
            
            for doc in docs:
                logger.info(f"  - PMID: {doc.pmid}, Title: {doc.title[:50]}...")
                logger.info(f"    Status: {doc.status}, Type: {doc.source_type}")
        
        logger.info("Literature ingestion test completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    finally:
        if 'db_session' in locals():
            db_session.close()


def test_pubmed_search():
    """Test just the PubMed search functionality."""
    
    nct_id = "NCT04331665"
    logger.info(f"Testing PubMed search for: {nct_id}")
    
    try:
        from ncfd.ingest.pubs import PubMedClient
        
        client = PubMedClient()
        publications = client.search_by_nct(nct_id, max_results=5)
        
        logger.info(f"Found {len(publications)} publications")
        
        for i, pub in enumerate(publications[:3]):
            logger.info(f"  {i+1}. PMID: {pub.pmid}")
            logger.info(f"     Title: {pub.title[:60]}...")
            logger.info(f"     Journal: {pub.journal}")
            logger.info(f"     Authors: {', '.join(pub.authors[:2])}...")
            logger.info(f"     Abstract: {pub.abstract[:100]}...")
            logger.info("")
        
    except Exception as e:
        logger.error(f"PubMed search test failed: {e}")
        raise


if __name__ == "__main__":
    logger.info("Starting literature ingestion tests...")
    
    # Test 1: PubMed search only
    try:
        test_pubmed_search()
        logger.info("PubMed search test passed!")
    except Exception as e:
        logger.error(f"PubMed search test failed: {e}")
    
    # Test 2: Full literature ingestion (requires database)
    try:
        test_literature_ingestion()
        logger.info("Full literature ingestion test passed!")
    except Exception as e:
        logger.error(f"Full literature ingestion test failed: {e}")
        logger.info("This is expected if database is not configured")
    
    logger.info("All tests completed!")
