#!/usr/bin/env python3
"""
Minimal test script for PubMed literature system.

Demonstrates:
1. Basic search with NCT ID + drug name
2. R-score ranking of results
"""

import asyncio
import logging
import sys
import os
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ncfd.ingest.pubmed import PubMedClient, PubMedQueryBuilder, PubMedMapper
from ncfd.score.simple_rs_scorer import SimpleRSScorer
from ncfd.extract.abstract_features import AbstractFeatureExtractor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MinimalPubMedTest:
    """Minimal test implementation for PubMed literature system."""
    
    def __init__(self):
        """Initialize test components."""
        # PubMed client (no API key for testing)
        self.client = PubMedClient(
            rate_limit_per_sec=3,  # Conservative rate limit
            batch_size=10,  # Small batch size for testing
            timeout_seconds=30
        )
        
        # Query builder
        self.query_builder = PubMedQueryBuilder()
        
        # Response mapper
        self.mapper = PubMedMapper()
        
        # R/S scorer
        self.scorer = SimpleRSScorer()
        
        # Feature extractor
        self.extractor = AbstractFeatureExtractor()
    
    async def test_basic_search(self, nct_id: str, drug_name: str, indication: str) -> List[Dict[str, Any]]:
        """
        Test 1: Basic search and results.
        
        Args:
            nct_id: NCT ID to search for
            drug_name: Drug name to search for
            indication: Disease/indication to search for
            
        Returns:
            List of PubMed results with basic metadata
        """
        logger.info(f"=== Test 1: Basic Search ===")
        logger.info(f"NCT: {nct_id}")
        logger.info(f"Drug: {drug_name}")
        logger.info(f"Indication: {indication}")
        
        try:
            # 1. Build search query
            query = self.query_builder.build_trial_query(
                asset_names=[drug_name],
                indications=[indication],
                trial_phases=['PHASE2', 'PHASE3'],  # Focus on later phases
                publication_types=['Clinical Trial', 'Randomized Controlled Trial']
            )
            
            logger.info(f"Built query: {query[:200]}...")
            
            # 2. Execute PubMed search
            search_result = await self.client.esearch(query, max_results=20)
            pmids = search_result.get('idlist', [])
            
            if not pmids:
                logger.warning("No PMIDs found in search")
                return []
            
            logger.info(f"Found {len(pmids)} PMIDs")
            
            # 3. Fetch metadata for PMIDs
            metadata_results = await self.client.esummary_batch(pmids[:10])  # Limit to 10 for testing
            
            # 4. Map to our format
            mapped_documents = self.mapper.map_esummary_result(metadata_results)
            
            logger.info(f"Mapped {len(mapped_documents)} documents")
            
            # 5. Extract features from each document
            for doc in mapped_documents:
                doc_text = self._extract_document_text(doc)
                if doc_text:
                    entities = self.extractor.extract_all_features(doc_text)
                    doc['extracted_entities'] = entities
                    
                    # Log some extracted features
                    nct_ids = self.extractor.extract_nct_ids(doc_text)
                    phases = self.extractor.extract_phases(doc_text)
                    sample_sizes = self.extractor.extract_sample_sizes(doc_text)
                    
                    if nct_ids or phases or sample_sizes:
                        logger.info(f"PMID {doc.get('pmid', 'unknown')}: "
                                  f"NCTs={nct_ids}, Phases={phases}, N={sample_sizes}")
            
            return mapped_documents
            
        except Exception as e:
            logger.error(f"Basic search failed: {e}")
            return []
    
    async def test_r_score_ranking(self, documents: List[Dict[str, Any]], 
                                  drug_name: str, indication: str) -> List[Dict[str, Any]]:
        """
        Test 2: R-score ranking of results.
        
        Args:
            documents: List of documents from basic search
            drug_name: Drug name for scoring
            indication: Indication for scoring
            
        Returns:
            Documents ranked by R score
        """
        logger.info(f"\n=== Test 2: R-Score Ranking ===")
        
        if not documents:
            logger.warning("No documents to score")
            return []
        
        try:
            # Score all documents
            scored_docs = self.scorer.score_batch(documents, drug_name, indication)
            
            logger.info(f"Scored {len(scored_docs)} documents")
            
            # Rank by R score
            ranked_docs = self.scorer.rank_by_r_score(scored_docs)
            
            # Display top results
            logger.info("\nTop 5 results by R score:")
            for i, (doc, score) in enumerate(ranked_docs[:5]):
                logger.info(f"{i+1}. PMID {doc.get('pmid', 'unknown')} - "
                          f"R: {score.R_tier} ({score.R_score:.3f}), "
                          f"S: {score.S_tier} ({score.S_score:.3f})")
                
                # Show title
                title = doc.get('title', 'No title')
                logger.info(f"   Title: {title[:100]}...")
                
                # Show R components
                r_comp = score.R_components
                logger.info(f"   R Components: Asset={r_comp.get('asset_match', 0):.3f}, "
                          f"Indication={r_comp.get('indication_match', 0):.3f}, "
                          f"NCT={r_comp.get('nct_match', 0):.3f}")
            
            return [doc for doc, _ in ranked_docs]
            
        except Exception as e:
            logger.error(f"R-score ranking failed: {e}")
            return documents
    
    def _extract_document_text(self, doc: Dict[str, Any]) -> str:
        """Extract text content from document."""
        text_parts = []
        
        if doc.get('title'):
            text_parts.append(doc['title'])
        
        if 'text' in doc and doc['text'].get('abstract_text'):
            text_parts.append(doc['text']['abstract_text'])
        
        return ' '.join(text_parts)
    
    async def run_demo(self):
        """Run a complete demo of the system."""
        logger.info("🚀 Starting Minimal PubMed Literature System Demo")
        
        # Demo parameters
        demo_trials = [
            {
                'nct_id': 'NCT04368728',
                'drug_name': 'Remdesivir',
                'indication': 'COVID-19'
            },
            {
                'nct_id': 'NCT04269498',
                'drug_name': 'Pembrolizumab',
                'indication': 'Non-small cell lung cancer'
            }
        ]
        
        for trial in demo_trials:
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing Trial: {trial['nct_id']}")
            logger.info(f"{'='*60}")
            
            # Test 1: Basic search
            documents = await self.test_basic_search(
                trial['nct_id'],
                trial['drug_name'],
                trial['indication']
            )
            
            if documents:
                # Test 2: R-score ranking
                ranked_docs = await self.test_r_score_ranking(
                    documents,
                    trial['drug_name'],
                    trial['indication']
                )
                
                # Summary
                logger.info(f"\n📊 Summary for {trial['nct_id']}:")
                logger.info(f"   Documents found: {len(documents)}")
                logger.info(f"   Documents scored: {len(ranked_docs)}")
                
                # Count by R tier
                r_tier_counts = {}
                for doc in ranked_docs:
                    if 'extracted_entities' in doc:
                        # Re-score to get current R tier
                        doc_text = self._extract_document_text(doc)
                        if doc_text:
                            score = self.scorer.score_document(
                                doc_text, trial['drug_name'], trial['indication']
                            )
                            r_tier = score.R_tier
                            r_tier_counts[r_tier] = r_tier_counts.get(r_tier, 0) + 1
                
                for tier in ['R3', 'R2', 'R1', 'R0']:
                    count = r_tier_counts.get(tier, 0)
                    logger.info(f"   {tier}: {count} documents")
            else:
                logger.warning(f"No documents found for {trial['nct_id']}")
        
        logger.info(f"\n{'='*60}")
        logger.info("✅ Demo completed!")
        logger.info(f"{'='*60}")


async def main():
    """Main function."""
    try:
        test = MinimalPubMedTest()
        await test.run_demo()
        
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
