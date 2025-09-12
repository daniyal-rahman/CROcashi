"""
Test script for dual persistence strategy.

Tests the dual persistence implementation:
1. Retrieval: Store ALL documents found (human verification)
2. Processing: Store only filtered documents (LLM processing)
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from ncfd.pipeline.pubmed_pipeline import PubMedPipeline
from ncfd.db.session import session_scope

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_dual_persistence():
    """Test dual persistence strategy with Cassava trial."""
    
    # Test configuration
    config = {
        'asset_names': ['simufilam', 'PTI-125', 'PTI 125'],
        'indications': ['Alzheimer Disease', 'Alzheimer\'s', 'AD', 'dementia'],
        'client_config': {
            'rate_limit_requests_per_minute': 60,
            'batch_size': 100,
            'max_retries': 3,
            'timeout_seconds': 30,
            'circuit_breaker_threshold': 5,
            'email': 'ncfd@example.com',
            'tool': 'NCFD'
        },
        'enable_entity_extraction': True,
        'enable_rs_scoring': True,
        'min_r_score': 0.35,
        'min_s_score': 0.20
    }
    
    trial_id = 1  # Cassava trial ID
    trial_nct = "NCT04388254"
    
    try:
        logger.info("Starting dual persistence test")
        
        # Initialize pipeline with dual persistence
        pipeline = PubMedPipeline(config)
        
        # Execute pipeline
        results = await pipeline.execute_pipeline(
            trial_id=trial_id,
            asset_names=config['asset_names'],
            indications=config['indications'],
            trial_phases=None,
            date_range=None,
            max_results=100,
            enable_stages=['retrieval', 'processing'],
            entity_id=trial_nct
        )
        
        # Print results
        logger.info("Pipeline execution results:")
        for result in results:
            logger.info(f"  {result.stage}: {'SUCCESS' if result.success else 'FAILED'}")
            logger.info(f"    Documents processed: {result.documents_processed}")
            logger.info(f"    Execution time: {result.execution_time:.2f}s")
            if result.metadata:
                logger.info(f"    Metadata: {result.metadata}")
            if result.error_message:
                logger.info(f"    Error: {result.error_message}")
        
        # Get retrieval metrics
        metrics = pipeline.get_retrieval_metrics(trial_id)
        if metrics:
            logger.info(f"\nRetrieval metrics for trial {trial_id}:")
            for key, value in metrics.items():
                logger.info(f"  {key}: {value}")
        
        # Get retrieval documents (human verification)
        retrieval_docs = pipeline.get_retrieval_documents(trial_id)
        logger.info(f"\nRetrieval documents (human verification): {len(retrieval_docs)}")
        
        # Get processed documents (LLM processing)
        processed_docs = pipeline.get_processed_documents(trial_id)
        logger.info(f"Processed documents (LLM processing): {len(processed_docs)}")
        
        # Show sample documents
        if retrieval_docs:
            logger.info(f"\nSample retrieval document:")
            sample = retrieval_docs[0]
            logger.info(f"  PMID: {sample.get('pmid')}")
            logger.info(f"  Title: {sample.get('title', 'N/A')[:100]}...")
            logger.info(f"  Retrieval tier: {sample.get('retrieval_tier')}")
            logger.info(f"  Policy engine passed: {sample.get('policy_engine_passed')}")
            logger.info(f"  Guardrails passed: {sample.get('guardrails_passed')}")
        
        if processed_docs:
            logger.info(f"\nSample processed document:")
            sample = processed_docs[0]
            logger.info(f"  PMID: {sample.get('pmid')}")
            logger.info(f"  Title: {sample.get('title', 'N/A')[:100]}...")
            logger.info(f"  R Score: {sample.get('r_score')}")
            logger.info(f"  S Score: {sample.get('s_score')}")
            logger.info(f"  RS Tier: {sample.get('rs_tier')}")
        
        logger.info("\nDual persistence test completed successfully!")
        
    except Exception as e:
        logger.error(f"Error in dual persistence test: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_dual_persistence())
