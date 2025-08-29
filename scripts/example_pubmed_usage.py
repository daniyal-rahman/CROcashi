#!/usr/bin/env python3
"""
Example usage of the improved PubMed client.

This script demonstrates the key improvements and fixes implemented.
"""

import asyncio
import logging
import sys
import os
import yaml

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ncfd.ingest.pubmed import PubMedClient, PubMedBatchProcessor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_config(config_path: str = "../config/pubmed_config.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        logger.warning(f"Config file {config_path} not found, using defaults")
        return {}
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


async def example_basic_usage():
    """Demonstrate basic PubMed client usage."""
    logger.info("🔍 Example: Basic PubMed Client Usage")
    
    # Load configuration
    config = load_config()
    api_config = config.get('api', {})
    
    # Initialize client with configuration
    async with PubMedClient(
        api_key=api_config.get('api_key'),
        email=api_config.get('email', 'test@example.com'),
        tool=api_config.get('tool', 'NCFD-Example'),
        rate_limit_per_sec=api_config.get('rate_limit_per_sec', 3),
        batch_size=api_config.get('batch_size', 50),
        max_retries=api_config.get('max_retries', 3)
    ) as client:
        
        # Example 1: Search for clinical trials
        logger.info("Searching for COVID-19 clinical trials...")
        search_result = await client.esearch(
            query="COVID-19 AND clinical trial",
            max_results=20,
            sort="pub_date"
        )
        
        pmids = search_result.get('idlist', [])
        logger.info(f"Found {len(pmids)} PMIDs")
        
        if pmids:
            # Example 2: Get metadata for first 5 results
            logger.info("Fetching metadata for first 5 results...")
            metadata = await client.esummary_batch(pmids[:5])
            
            for pmid, doc in metadata.items():
                title = doc.get('title', 'No title')
                journal = doc.get('fulljournalname', 'No journal')
                pub_date = doc.get('pubdate', 'No date')
                logger.info(f"PMID {pmid}: {title[:60]}...")
                logger.info(f"  Journal: {journal}, Date: {pub_date}")
            
            # Example 3: Get abstracts in XML format (most reliable)
            logger.info("Fetching abstracts in XML format...")
            abstracts = await client.efetch_abstracts_xml(pmids[:3])
            
            for pmid, abstract in abstracts.items():
                if abstract:
                    logger.info(f"PMID {pmid}: Abstract ({len(abstract)} chars)")
                    logger.info(f"  Preview: {abstract[:100]}...")
                else:
                    logger.info(f"PMID {pmid}: No abstract available")
            
            # Example 4: Convert PMIDs to PMCIDs
            logger.info("Converting PMIDs to PMCIDs...")
            pmcids = await client.elink_pmid_to_pmcid(pmids[:5])
            
            for pmid, pmcid in pmcids.items():
                if pmcid:
                    logger.info(f"PMID {pmid} → PMCID {pmcid}")
                else:
                    logger.info(f"PMID {pmid} → No PMCID available")


async def example_pagination():
    """Demonstrate pagination functionality."""
    logger.info("\n🔍 Example: Pagination with History")
    
    config = load_config()
    api_config = config.get('api', {})
    
    async with PubMedClient(
        email=api_config.get('email', 'test@example.com'),
        tool=api_config.get('tool', 'NCFD-Example'),
        rate_limit_per_sec=api_config.get('rate_limit_per_sec', 3)
    ) as client:
        
        # Use pagination to get more results efficiently
        logger.info("Using pagination to fetch 100 results...")
        result = await client.esearch_all(
            query="cancer AND immunotherapy",
            max_results=100,
            use_history=True
        )
        
        pmids = result.get('idlist', [])
        webenv = result.get('webenv')
        query_key = result.get('querykey')
        
        logger.info(f"Retrieved {len(pmids)} PMIDs using pagination")
        logger.info(f"WebEnv: {webenv}")
        logger.info(f"QueryKey: {query_key}")
        
        # Process in batches
        if pmids:
            logger.info("Processing results in batches...")
            batch_processor = PubMedBatchProcessor(client, max_concurrent=3)
            
            # Get metadata for all results
            metadata = await batch_processor.process_pmids_in_batches(
                pmids, 'esummary'
            )
            
            logger.info(f"Successfully processed {len(metadata)} documents")


async def example_error_handling():
    """Demonstrate error handling and circuit breaker."""
    logger.info("\n🔍 Example: Error Handling and Circuit Breaker")
    
    config = load_config()
    api_config = config.get('api', {})
    
    async with PubMedClient(
        email=api_config.get('email', 'test@example.com'),
        tool=api_config.get('tool', 'NCFD-Example'),
        rate_limit_per_sec=api_config.get('rate_limit_per_sec', 3),
        circuit_breaker_threshold=3
    ) as client:
        
        # Test health check
        is_healthy = await client.health_check()
        logger.info(f"Health check: {'✅ PASSED' if is_healthy else '❌ FAILED'}")
        
        # Get rate limit info
        rate_info = client.get_rate_limit_info()
        logger.info(f"Rate limit info: {rate_info}")
        
        # Test with invalid query (should handle gracefully)
        try:
            logger.info("Testing error handling with invalid query...")
            result = await client.esearch("", max_results=1)
            logger.info("Unexpected success with empty query")
        except Exception as e:
            logger.info(f"✅ Properly handled error: {type(e).__name__}")


async def main():
    """Main example function."""
    logger.info("🚀 PubMed Client Examples")
    logger.info("=" * 50)
    
    try:
        # Run examples
        await example_basic_usage()
        await example_pagination()
        await example_error_handling()
        
        logger.info("\n" + "=" * 50)
        logger.info("🎉 All examples completed successfully!")
        logger.info("Key improvements demonstrated:")
        logger.info("✅ Configurable email/tool parameters")
        logger.info("✅ XML-based abstract fetching")
        logger.info("✅ Proper pagination with history")
        logger.info("✅ Fixed health check")
        logger.info("✅ Configurable retry logic")
        logger.info("✅ Circuit breaker protection")
        logger.info("✅ Rate limiting with proper locking")
        
    except Exception as e:
        logger.error(f"❌ Example failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
