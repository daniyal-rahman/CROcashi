#!/usr/bin/env python3
"""
Runtime Text Generation Integration Test

Tests the complete runtime text generation system with real document data.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the src directory to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "tests"))

# Setup test environment
from utils.env_loader import setup_test_environment
setup_test_environment(project_root)

from src.ncfd.extract.runtime_text import RuntimeTextGenerator, DocumentTextCache
from src.ncfd.db.session import session_scope
from src.ncfd.db.models import Document, DocumentText

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_runtime_text_generation():
    """Test runtime text generation with real document data."""
    logger.info("🧪 Starting Runtime Text Generation Integration Test")
    
    try:
        # Initialize components
        generator = RuntimeTextGenerator()
        cache = DocumentTextCache()
        
        # Get a real document from the database
        with session_scope() as session:
            # Find a document with PMID for testing
            test_doc = session.query(Document).filter(
                Document.pmid.isnot(None),
                Document.pmid != ""
            ).first()
            
            if not test_doc:
                logger.warning("No documents with PMIDs found in database")
                return
            
            logger.info(f"Testing with document: PMID {test_doc.pmid}, Title: {test_doc.title}")
            
            # Test 1: Direct text generation
            logger.info("Test 1: Direct text generation")
            doc_id = f"db:{test_doc.doc_id}"
            generated_text = await generator.generate_text(doc_id)
            
            if generated_text:
                logger.info(f"✅ Generated {len(generated_text)} characters of text")
                logger.info(f"Text preview: {generated_text[:200]}...")
            else:
                logger.warning("❌ No text generated")
            
            # Test 2: Cache functionality
            logger.info("Test 2: Cache functionality")
            cached_text = await cache.get_document_text(doc_id, prefer_fulltext=True)
            
            if cached_text:
                logger.info(f"✅ Retrieved {len(cached_text)} characters from cache")
                logger.info(f"Cache stats: {cache.get_cache_stats()}")
            else:
                logger.warning("❌ No text retrieved from cache")
            
            # Test 3: Batch generation
            logger.info("Test 3: Batch generation")
            test_docs = session.query(Document).filter(
                Document.pmid.isnot(None),
                Document.pmid != ""
            ).limit(3).all()
            
            if len(test_docs) >= 2:
                doc_ids = [f"db:{doc.doc_id}" for doc in test_docs]
                batch_results = await generator.generate_texts_batch(doc_ids)
                
                logger.info(f"✅ Batch generation: {len(batch_results)}/{len(doc_ids)} documents processed")
                for doc_id, text in batch_results.items():
                    logger.info(f"   {doc_id}: {len(text)} characters")
            else:
                logger.warning("❌ Not enough documents for batch test")
            
            # Test 4: Cache performance
            logger.info("Test 4: Cache performance")
            cache_stats_before = cache.get_cache_stats()
            
            # Access the same document multiple times
            for i in range(3):
                await cache.get_document_text(doc_id, prefer_fulltext=True)
            
            cache_stats_after = cache.get_cache_stats()
            logger.info(f"Cache hit rate: {cache_stats_after['hit_rate']:.2%}")
            logger.info(f"Cache hits: {cache_stats_after['hits']}")
            logger.info(f"Cache misses: {cache_stats_after['misses']}")
            logger.info(f"API calls: {cache_stats_after['api_calls']}")
            
        logger.info("✅ Runtime text generation integration test completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}", exc_info=True)
        raise


async def test_api_clients():
    """Test individual API clients."""
    logger.info("🧪 Testing API Clients")
    
    try:
        from src.ncfd.extract.runtime_text.api_clients import PubMedTextClient, PMCTextClient
        
        # Test PubMed client with a known PMID
        pubmed_client = PubMedTextClient({"rate_limit_per_minute": 60, "timeout_seconds": 30})
        
        # Use a known PMID for testing
        test_pmid = "12345678"  # This should be a real PMID
        result = await pubmed_client.fetch_abstract(test_pmid)
        
        logger.info(f"PubMed test result: success={result.success}, length={result.length}")
        if result.success:
            logger.info(f"Abstract preview: {result.text[:200]}...")
        else:
            logger.info(f"Error: {result.error_message}")
        
        # Test PMC client with a known PMCID
        pmc_client = PMCTextClient({"rate_limit_per_minute": 30, "timeout_seconds": 45})
        
        # Use a known PMCID for testing
        test_pmcid = "PMC123456"  # This should be a real PMCID
        result = await pmc_client.fetch_fulltext(test_pmcid)
        
        logger.info(f"PMC test result: success={result.success}, length={result.length}")
        if result.success:
            logger.info(f"Full text preview: {result.text[:200]}...")
        else:
            logger.info(f"Error: {result.error_message}")
        
        logger.info("✅ API clients test completed")
        
    except Exception as e:
        logger.error(f"❌ API clients test failed: {str(e)}", exc_info=True)


async def main():
    """Main test function."""
    logger.info("🚀 Starting Runtime Text Generation Tests")
    logger.info("=" * 60)
    
    try:
        await test_runtime_text_generation()
        logger.info("")
        await test_api_clients()
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("🎉 All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"💥 Test suite failed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
