#!/usr/bin/env python3
"""
PubMed Search Validation Test.

Shows exact search queries, results, and ranking for a drug with an associated NCT ID.
Uses Remdesivir + NCT04368728 to demonstrate the full pipeline.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PubMedSearchValidator:
    """Validates PubMed search queries and results."""
    
    def __init__(self):
        """Initialize validator components."""
        # PubMed client
        self.client = PubMedClient(
            rate_limit_per_sec=3,
            batch_size=20,
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
            {'max_results_per_trial': 50, 'batch_size': 20}
        )
        
        self.stage_u1 = StageU1Processor(
            self.client, self.mapper, self.feature_extractor, self.rs_scorer,
            {'batch_size': 10, 'min_r_score': 0.35, 'min_s_score': 0.20}
        )
    
    async def validate_remdesivir_search(self):
        """Validate Remdesivir + COVID-19 + NCT04368728 search."""
        logger.info("🔍 VALIDATING REMDESIVIR + COVID-19 + NCT04368728 SEARCH")
        logger.info("=" * 80)
        
        # Test case: Remdesivir for COVID-19 with specific NCT
        trial_id = "REM_COVID_001"
        asset_aliases = ["Remdesivir", "GS-5734"]
        indication_terms = ["COVID-19", "SARS-CoV-2"]
        trial_nct = "NCT04368728"
        trial_phase = "PHASE3"
        trial_design = "RANDOMIZED"
        catalyst_date = datetime(2023, 6, 15)  # Mid-2023 catalyst
        
        # 1. Build and show the exact query
        logger.info("📝 BUILDING SEARCH QUERY:")
        query_result = self.query_builder.build_trial_query(
            trial_id=trial_id,
            asset_aliases=asset_aliases,
            indication_terms=indication_terms,
            trial_nct=trial_nct,
            trial_phase=trial_phase,
            trial_design=trial_design,
            catalyst_date=catalyst_date,
            max_results=50
        )
        
        query_string = query_result['query_string']
        query_metadata = query_result['metadata']
        
        logger.info(f"🔍 EXACT SEARCH QUERY:")
        logger.info(f"   Query: {query_string}")
        logger.info(f"   Length: {len(query_string)} characters")
        logger.info(f"   Components: {query_metadata['query_components']}")
        logger.info(f"   Catalyst window: {query_metadata['catalyst_window_months']} months")
        logger.info("")
        
        # 2. Execute Stage U0 (Metadata Discovery)
        logger.info("🚀 EXECUTING STAGE U0 (Metadata Discovery):")
        u0_result = await self.stage_u0.execute_stage_u0(
            trial_id=trial_id,
            asset_aliases=asset_aliases,
            indication_terms=indication_terms,
            trial_nct=trial_nct,
            trial_phase=trial_phase,
            trial_design=trial_design,
            catalyst_date=catalyst_date,
            max_results=50
        )
        
        if not u0_result.success:
            logger.error(f"❌ Stage U0 failed: {u0_result.error_message}")
            return
        
        logger.info(f"✅ Stage U0 Results:")
        logger.info(f"   Total results found: {u0_result.documents_discovered}")
        logger.info(f"   Documents mapped: {u0_result.documents_mapped}")
        logger.info(f"   Execution time: {u0_result.execution_time:.2f}s")
        logger.info("")
        
        # 3. Show top 10 results with ranking
        if u0_result.mapped_documents:
            logger.info("📊 TOP 10 SEARCH RESULTS (by relevance):")
            logger.info("-" * 80)
            
            # Sort by title relevance (simple heuristic)
            sorted_docs = sorted(
                u0_result.mapped_documents, 
                key=lambda x: self._calculate_title_relevance(x, asset_aliases, indication_terms),
                reverse=True
            )
            
            for i, doc in enumerate(sorted_docs[:10], 1):
                title = doc.get('title', 'No title')
                pmid = doc.get('pmid', 'No PMID')
                journal = doc.get('journal', 'No journal')
                pub_date = doc.get('pubdate', 'No date')
                
                # Calculate relevance score
                relevance_score = self._calculate_title_relevance(doc, asset_aliases, indication_terms)
                
                logger.info(f"{i:2d}. PMID {pmid} (Score: {relevance_score:.3f})")
                logger.info(f"    Title: {title}")
                logger.info(f"    Journal: {journal}")
                logger.info(f"    Date: {pub_date}")
                logger.info("")
        
        # 4. Execute Stage U1 (Abstract Processing) on top 10
        logger.info("🔬 EXECUTING STAGE U1 (Abstract Processing) on top 10:")
        top_10_docs = u0_result.mapped_documents[:10]
        
        u1_result = await self.stage_u1.execute_stage_u1(
            trial_id=trial_id,
            u0_documents=top_10_docs,
            trial_asset="Remdesivir",
            trial_indication="COVID-19",
            trial_nct=trial_nct
        )
        
        if not u1_result.success:
            logger.error(f"❌ Stage U1 failed: {u1_result.error_message}")
            return
        
        logger.info(f"✅ Stage U1 Results:")
        logger.info(f"   Documents processed: {u1_result.documents_processed}")
        logger.info(f"   Abstracts fetched: {u1_result.abstracts_fetched}")
        logger.info(f"   Entities extracted: {u1_result.entities_extracted}")
        logger.info(f"   Documents scored: {u1_result.documents_scored}")
        logger.info(f"   Documents selected: {u1_result.documents_selected}")
        logger.info(f"   Documents dropped: {u1_result.documents_dropped}")
        logger.info("")
        
        # 5. Show R/S scoring results
        if u1_result.processed_documents:
            logger.info("🎯 R/S SCORING RESULTS (Top 10):")
            logger.info("-" * 80)
            
            # Sort by R score (descending)
            scored_docs = [doc for doc in u1_result.processed_documents if 'rs_score' in doc]
            sorted_scored = sorted(scored_docs, key=lambda x: x['rs_score'].R_score, reverse=True)
            
            for i, doc in enumerate(sorted_scored, 1):
                pmid = doc.get('pmid', 'No PMID')
                title = doc.get('title', 'No title')[:80]
                score = doc['rs_score']
                
                logger.info(f"{i:2d}. PMID {pmid}: R{score.R_tier}({score.R_score:.3f}) S{score.S_tier}({score.S_score:.3f})")
                logger.info(f"    Title: {title}...")
                logger.info(f"    R Components: {score.R_components}")
                logger.info(f"    S Components: {score.S_components}")
                logger.info("")
        
        # 6. Summary
        logger.info("📋 SEARCH VALIDATION SUMMARY:")
        logger.info("=" * 80)
        logger.info(f"✅ Search Query: {len(query_string)} characters")
        logger.info(f"✅ Total Results: {u0_result.documents_discovered}")
        logger.info(f"✅ Top 10 Processed: {len(top_10_docs)}")
        logger.info(f"✅ Abstracts Fetched: {u1_result.abstracts_fetched}")
        logger.info(f"✅ R/S Scoring: {u1_result.documents_scored} documents")
        logger.info(f"✅ Selection Rate: {u1_result.documents_selected}/{u1_result.documents_scored}")
        logger.info("")
        logger.info("🎉 Search validation complete! Check the results above for accuracy.")
    
    def _calculate_title_relevance(self, doc: Dict[str, Any], assets: List[str], indications: List[str]) -> float:
        """Calculate simple title relevance score."""
        title = doc.get('title', '').lower()
        score = 0.0
        
        # Asset matches
        for asset in assets:
            asset_lower = asset.lower()
            if asset_lower in title:
                score += 0.4
            elif any(word in title for word in asset_lower.split()):
                score += 0.2
        
        # Indication matches
        for indication in indications:
            indication_lower = indication.lower()
            if indication_lower in title:
                score += 0.3
            elif any(word in title for word in indication_lower.split()):
                score += 0.15
        
        # NCT ID match (bonus)
        if 'nct04368728' in title.lower():
            score += 0.2
        
        return min(score, 1.0)


async def main():
    """Main validation function."""
    try:
        validator = PubMedSearchValidator()
        await validator.validate_remdesivir_search()
        
    except KeyboardInterrupt:
        logger.info("Validation interrupted by user")
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
