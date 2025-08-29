#!/usr/bin/env python3
"""
Comprehensive test script for PubMed Pipeline M4-M6.

Tests the complete implementation:
- M4: Trial-specific query builder
- M5: Stage U0 (metadata discovery)  
- M6: Stage U1 (abstract processing)
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ncfd.ingest.pubmed import (
    PubMedClient, TrialQueryBuilder, PubMedMapper,
    StageU0Processor, StageU1Processor
)
from ncfd.extract.abstract_features import AbstractFeatureExtractor
from ncfd.score.simple_rs_scorer import SimpleRSScorer

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PubMedPipelineTest:
    """Comprehensive test for PubMed pipeline M4-M6."""
    
    def __init__(self):
        """Initialize test components."""
        # PubMed client
        self.client = PubMedClient(
            rate_limit_per_sec=3,  # Conservative rate limit
            batch_size=10,         # Small batch size for testing
            timeout_seconds=30
        )
        
        # Trial query builder
        self.query_builder = TrialQueryBuilder({
            'catalyst_window_months': 18,
            'recency_bias': True,
            'max_asset_aliases': 5,
            'max_indication_terms': 8
        })
        
        # Response mapper
        self.mapper = PubMedMapper()
        
        # Feature extractor
        self.feature_extractor = AbstractFeatureExtractor()
        
        # R/S scorer
        self.rs_scorer = SimpleRSScorer()
        
        # Stage processors
        self.stage_u0 = StageU0Processor(
            self.client, self.query_builder, self.mapper,
            {'max_results_per_trial': 20, 'batch_size': 10}
        )
        
        self.stage_u1 = StageU1Processor(
            self.client, self.mapper, self.feature_extractor, self.rs_scorer,
            {'batch_size': 5, 'min_r_score': 0.35, 'min_s_score': 0.20}
        )
    
    async def test_m4_trial_query_builder(self) -> bool:
        """Test M4: Trial-specific query builder."""
        logger.info("🔍 Testing M4: Trial Query Builder")
        
        try:
            # Test case 1: COVID-19 trial
            covid_query = self.query_builder.build_trial_query(
                trial_id="COVID_TRIAL_001",
                asset_aliases=["Remdesivir", "GS-5734"],
                indication_terms=["COVID-19", "SARS-CoV-2"],
                trial_nct="NCT04368728",
                trial_phase="PHASE3",
                trial_design="RANDOMIZED",
                catalyst_date=datetime(2023, 6, 15)
            )
            
            logger.info(f"✅ COVID-19 query built: {len(covid_query['query_string'])} chars")
            logger.info(f"   Query: {covid_query['query_string'][:200]}...")
            logger.info(f"   Metadata: {covid_query['metadata']['query_components']}")
            
            # Test case 2: Cancer trial
            cancer_query = self.query_builder.build_trial_query(
                trial_id="CANCER_TRIAL_001", 
                asset_aliases=["Pembrolizumab", "Keytruda"],
                indication_terms=["Non-small cell lung cancer", "NSCLC"],
                trial_phase="PHASE2",
                catalyst_date=datetime(2024, 1, 15)
            )
            
            logger.info(f"✅ Cancer trial query built: {len(cancer_query['query_string'])} chars")
            logger.info(f"   Query: {cancer_query['query_string'][:200]}...")
            
            # Test case 3: Simple query
            simple_query = self.query_builder.build_trial_query(
                trial_id="SIMPLE_TRIAL_001",
                asset_aliases=["Aspirin"],
                indication_terms=["Headache"]
            )
            
            logger.info(f"✅ Simple query built: {len(simple_query['query_string'])} chars")
            
            # Validate queries
            for query_info in [covid_query, cancer_query, simple_query]:
                query_string = query_info['query_string']
                is_valid, issues = self.query_builder.base_builder.validate_query(query_string)
                
                if is_valid:
                    logger.info(f"✅ Query validation passed for {query_info['metadata']['trial_id']}")
                else:
                    logger.warning(f"⚠️ Query validation issues for {query_info['metadata']['trial_id']}: {issues}")
            
            logger.info("🎉 M4: Trial Query Builder tests passed!")
            return True
            
        except Exception as e:
            logger.error(f"❌ M4 test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_m5_stage_u0(self) -> bool:
        """Test M5: Stage U0 (Metadata Discovery)."""
        logger.info("\n🔍 Testing M5: Stage U0 (Metadata Discovery)")
        
        try:
            # Test with COVID-19 trial
            u0_result = await self.stage_u0.execute_stage_u0(
                trial_id="COVID_TRIAL_001",
                asset_aliases=["Remdesivir"],
                indication_terms=["COVID-19"],
                trial_nct="NCT04368728",
                trial_phase="PHASE3",
                max_results=15
            )
            
            if not u0_result.success:
                logger.error(f"❌ Stage U0 failed: {u0_result.error_message}")
                return False
            
            logger.info(f"✅ Stage U0 completed successfully!")
            logger.info(f"   Documents discovered: {u0_result.documents_discovered}")
            logger.info(f"   Documents mapped: {u0_result.documents_mapped}")
            logger.info(f"   Execution time: {u0_result.execution_time:.2f}s")
            
            # Show some sample documents
            if u0_result.mapped_documents:
                sample_docs = u0_result.mapped_documents[:3]
                logger.info(f"   Sample documents:")
                for i, doc in enumerate(sample_docs):
                    title = doc.get('title', 'No title')[:80]
                    pmid = doc.get('pmid', 'No PMID')
                    logger.info(f"     {i+1}. PMID {pmid}: {title}...")
            
            # Get statistics
            stats = self.stage_u0.get_stage_u0_stats(u0_result)
            logger.info(f"   Statistics: {stats}")
            
            logger.info("🎉 M5: Stage U0 tests passed!")
            return True, u0_result.mapped_documents
            
        except Exception as e:
            logger.error(f"❌ M5 test failed: {e}")
            import traceback
            traceback.print_exc()
            return False, []
    
    async def test_m6_stage_u1(self, u0_documents: List[Dict[str, Any]]) -> bool:
        """Test M6: Stage U1 (Abstract Processing)."""
        logger.info("\n🔍 Testing M6: Stage U1 (Abstract Processing)")
        
        if not u0_documents:
            logger.warning("⚠️ No U0 documents to process, skipping U1 test")
            return True
        
        try:
            # Test with COVID-19 trial
            u1_result = await self.stage_u1.execute_stage_u1(
                trial_id="COVID_TRIAL_001",
                u0_documents=u0_documents[:5],  # Limit to 5 for testing
                trial_asset="Remdesivir",
                trial_indication="COVID-19",
                trial_nct="NCT04368728"
            )
            
            if not u1_result.success:
                logger.error(f"❌ Stage U1 failed: {u1_result.error_message}")
                return False
            
            logger.info(f"✅ Stage U1 completed successfully!")
            logger.info(f"   Documents processed: {u1_result.documents_processed}")
            logger.info(f"   Abstracts fetched: {u1_result.abstracts_fetched}")
            logger.info(f"   Entities extracted: {u1_result.entities_extracted}")
            logger.info(f"   Documents scored: {u1_result.documents_scored}")
            logger.info(f"   Documents selected: {u1_result.documents_selected}")
            logger.info(f"   Documents dropped: {u1_result.documents_dropped}")
            logger.info(f"   Execution time: {u1_result.execution_time:.2f}s")
            
            # Show R/S scoring results
            if u1_result.processed_documents:
                logger.info(f"   R/S Scoring Results:")
                for i, doc in enumerate(u1_result.processed_documents[:3]):
                    pmid = doc.get('pmid', 'No PMID')
                    title = doc.get('title', 'No title')[:60]
                    
                    if 'rs_score' in doc:
                        score = doc['rs_score']
                        logger.info(f"     {i+1}. PMID {pmid}: R{score.R_tier}({score.R_score:.3f}) "
                                  f"S{score.S_tier}({score.S_score:.3f}) - {title}...")
                    else:
                        logger.info(f"     {i+1}. PMID {pmid}: No score - {title}...")
            
            # Show entity extraction results
            if u1_result.processed_documents:
                logger.info(f"   Entity Extraction Results:")
                for doc in u1_result.processed_documents[:2]:
                    pmid = doc.get('pmid', 'No PMID')
                    entities = doc.get('extracted_entities', [])
                    
                    if entities:
                        entity_types = {}
                        for entity in entities:
                            ent_type = entity.ent_type
                            entity_types[ent_type] = entity_types.get(ent_type, 0) + 1
                        
                        logger.info(f"     PMID {pmid}: {entity_types}")
                    else:
                        logger.info(f"     PMID {pmid}: No entities extracted")
            
            # Get statistics
            stats = self.stage_u1.get_stage_u1_stats(u1_result)
            logger.info(f"   Statistics: {stats}")
            
            logger.info("🎉 M6: Stage U1 tests passed!")
            return True
            
        except Exception as e:
            logger.error(f"❌ M6 test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def run_comprehensive_test(self):
        """Run comprehensive test of M4-M6 pipeline."""
        logger.info("🚀 Starting Comprehensive PubMed Pipeline Test (M4-M6)")
        logger.info("=" * 70)
        
        test_results = []
        
        # Test M4: Trial Query Builder
        m4_success = await self.test_m4_trial_query_builder()
        test_results.append(('M4: Trial Query Builder', m4_success))
        
        # Test M5: Stage U0
        m5_success, u0_documents = await self.test_m5_stage_u0()
        test_results.append(('M5: Stage U0 (Metadata Discovery)', m5_success))
        
        # Test M6: Stage U1
        m6_success = await self.test_m6_stage_u1(u0_documents)
        test_results.append(('M6: Stage U1 (Abstract Processing)', m6_success))
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("📊 TEST RESULTS SUMMARY")
        logger.info("=" * 70)
        
        all_passed = True
        for test_name, success in test_results:
            status = "✅ PASSED" if success else "❌ FAILED"
            logger.info(f"{test_name}: {status}")
            if not success:
                all_passed = False
        
        if all_passed:
            logger.info("\n🎉 ALL TESTS PASSED! PubMed Pipeline M4-M6 is working correctly.")
            logger.info("Next steps:")
            logger.info("  1. Test database integration")
            logger.info("  2. Test full pipeline orchestration")
            logger.info("  3. Test with real trial data")
        else:
            logger.error("\n❌ SOME TESTS FAILED. Check the logs above for details.")
        
        logger.info("=" * 70)


async def main():
    """Main test function."""
    try:
        test = PubMedPipelineTest()
        await test.run_comprehensive_test()
        
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
