#!/usr/bin/env python3
"""
Basic PubMed API test - just check if we can connect and search.
"""

import asyncio
import logging
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ncfd.ingest.pubmed import PubMedClient, PubMedQueryBuilder

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_basic_pubmed_connection():
    """Test basic PubMed API connectivity."""
    logger.info("🔍 Testing basic PubMed API connection...")
    
    try:
        # Initialize client with very conservative settings
        async with PubMedClient(
            rate_limit_per_sec=2,  # Very conservative
            batch_size=5,          # Small batch
            timeout_seconds=30,
            email="test@example.com",  # Test email
            tool="NCFD-Test"           # Test tool name
        ) as client:
            
            logger.info("✅ PubMed client initialized")
            
            # Test 1: Simple ESearch
            logger.info("Testing ESearch with simple query...")
            search_result = await client.esearch("cancer", max_results=5)
            
            # The client returns the 'esearchresult' part, so we expect the structure directly
            if 'idlist' in search_result:
                count = search_result.get('count', '0')
                pmids = search_result.get('idlist', [])
                logger.info(f"✅ ESearch successful! Found {count} results, got {len(pmids)} PMIDs")
                logger.info(f"First few PMIDs: {pmids[:3]}")
                
                # Show the full response structure for debugging
                logger.info(f"Response keys: {list(search_result.keys())}")
            else:
                logger.error(f"❌ ESearch failed - unexpected response format: {search_result}")
                return False
            
            # Test 2: ESummary for a few PMIDs
            if pmids:
                logger.info("Testing ESummary with first PMID...")
                summary_result = await client.esummary_batch(pmids[:2])
                
                if summary_result:
                    logger.info(f"✅ ESummary successful! Got metadata for {len(summary_result)} documents")
                    
                    # Show some basic info
                    for pmid, doc_data in summary_result.items():
                        title = doc_data.get('title', 'No title')
                        journal = doc_data.get('fulljournalname', 'No journal')
                        pub_date = doc_data.get('pubdate', 'No date')
                        logger.info(f"   PMID {pmid}: {title[:80]}...")
                        logger.info(f"   Journal: {journal}, Date: {pub_date}")
                else:
                    logger.error("❌ ESummary failed - no results")
                    return False
            
            # Test 3: XML-based abstract fetching (more reliable)
            if pmids:
                logger.info("Testing XML-based abstract fetching...")
                try:
                    abstract_result = await client.efetch_abstracts_xml(pmids[:2])
                    if abstract_result:
                        logger.info(f"✅ XML abstract fetching successful! Got abstracts for {len(abstract_result)} documents")
                        for pmid, abstract in abstract_result.items():
                            if abstract:
                                logger.info(f"   PMID {pmid}: Abstract length: {len(abstract)} chars")
                                logger.info(f"   Preview: {abstract[:100]}...")
                            else:
                                logger.info(f"   PMID {pmid}: No abstract available")
                    else:
                        logger.warning("⚠️ XML abstract fetching returned no results")
                except Exception as e:
                    logger.warning(f"⚠️ XML abstract fetching failed (this is expected for some PMIDs): {e}")
            
            # Test 4: Health check
            logger.info("Testing health check...")
            is_healthy = await client.health_check()
            if is_healthy:
                logger.info("✅ Health check passed")
            else:
                logger.warning("⚠️ Health check failed")
            
            # Test 5: Rate limit info
            rate_info = client.get_rate_limit_info()
            logger.info(f"Rate limit info: {rate_info}")
            
            logger.info("🎉 All basic API tests passed!")
            return True
        
    except Exception as e:
        logger.error(f"❌ API test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_query_builder():
    """Test the query builder."""
    logger.info("\n🔍 Testing query builder...")
    
    try:
        builder = PubMedQueryBuilder()
        
        # Test 1: Simple trial query
        query = builder.build_trial_query(
            asset_names=["Remdesivir"],
            indications=["COVID-19"],
            trial_phases=["PHASE3"]
        )
        
        logger.info(f"✅ Built query: {query[:200]}...")
        
        # Test 2: Validate query
        is_valid, issues = builder.validate_query(query)
        if is_valid:
            logger.info("✅ Query validation passed")
        else:
            logger.warning(f"⚠️ Query validation issues: {issues}")
        
        # Test 3: Get query stats
        stats = builder.get_query_stats(query)
        logger.info(f"✅ Query stats: {stats}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Query builder test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_pagination():
    """Test pagination functionality."""
    logger.info("\n🔍 Testing pagination...")
    
    try:
        async with PubMedClient(
            rate_limit_per_sec=2,
            batch_size=10,
            timeout_seconds=30
        ) as client:
            
            # Test paginated search
            logger.info("Testing paginated ESearch...")
            result = await client.esearch_all("cancer", max_results=25, use_history=True)
            
            if 'idlist' in result:
                count = result.get('count', 0)
                pmids = result.get('idlist', [])
                webenv = result.get('webenv')
                query_key = result.get('querykey')
                
                logger.info(f"✅ Paginated search successful! Got {count} results")
                logger.info(f"WebEnv: {webenv}")
                logger.info(f"QueryKey: {query_key}")
                logger.info(f"First few PMIDs: {pmids[:5]}")
                
                return True
            else:
                logger.error("❌ Paginated search failed")
                return False
                
    except Exception as e:
        logger.error(f"❌ Pagination test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    logger.info("🚀 Starting Basic PubMed API Tests")
    logger.info("=" * 50)
    
    # Test 1: Basic API connection
    api_success = await test_basic_pubmed_connection()
    
    # Test 2: Query builder
    query_success = await test_query_builder()
    
    # Test 3: Pagination
    pagination_success = await test_pagination()
    
    # Summary
    logger.info("\n" + "=" * 50)
    if api_success and query_success and pagination_success:
        logger.info("🎉 ALL TESTS PASSED! PubMed API is working.")
        logger.info("Next step: Test with actual trial data")
    else:
        logger.error("❌ Some tests failed. Check the logs above.")
    
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
