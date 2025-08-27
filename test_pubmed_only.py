#!/usr/bin/env python3
"""
Simple test script for PubMed search functionality only.

This tests just the PubMed client without requiring database models.
"""

import logging
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_pubmed_search():
    """Test just the PubMed search functionality."""
    
    nct_id = "NCT04331665"  # Example: COVID-19 trial
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
        
        logger.info("PubMed search test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"PubMed search test failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting PubMed search test...")
    
    success = test_pubmed_search()
    
    if success:
        logger.info("✅ PubMed search test PASSED!")
        sys.exit(0)
    else:
        logger.error("❌ PubMed search test FAILED!")
        sys.exit(1)
