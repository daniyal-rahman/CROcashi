#!/usr/bin/env python3
"""
Backtest PubMed Cassava trial processing.
"""

import json
import sys
from pathlib import Path

from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.ingest.pubmed.pipeline import PubMedPipeline
from ncfd.config import get_config


class PubMedBacktest:
    """Backtest the PubMed literature review pipeline."""
    
    def __init__(self):
        self.pipeline_config = {
            "asset_names": [
                "simufilam",
                "PTI-125",
                "filamin A inhibitor",
                "Cassava Sciences"
            ],
            "indications": [
                "Alzheimer's disease",
                "AD",
                "dementia",
                "cognitive decline"
            ],
            "max_results": 1000,
            "enable_stages": ['U0', 'U1', 'OA'],
            "client_config": {
                "rate_limit_requests_per_minute": 300,
                "timeout_seconds": 30,
                "max_retries": 3
            },
            "query_config": {
                "max_terms": 50,
                "enable_boolean_operators": True
            },
            "mapper_config": {
                "enable_entity_extraction": True,
                "enable_citation_parsing": True
            },
            "max_concurrent_requests": 3,
            "batch_size": 50
        }
        
        self.cassava_trial = {
            "nct_id": "NCT04388254",
            "asset_names": [
                "simufilam",
                "PTI-125",
                "filamin A inhibitor",
                "Cassava Sciences"
            ],
            "indications": [
                "Alzheimer's disease",
                "AD",
                "dementia",
                "cognitive decline"
            ],
            "trial_phase": "phase_2",
            "primary_endpoint": "ADAS-Cog11",
            "mechanism": "small molecule filamin A inhibitor",
            "completion_date": "2023-12-01"
        }
        
        self.results = {
            "test_info": {
                "date": datetime.now(UTC).isoformat(),
                "trial_id": self.cassava_trial["nct_id"],
                "test_type": "PubMed Literature Review Backtest"
            },
            "pipeline_results": {},
            "llm_verification": {},
            "summary": {}
        }
    
    async def run_pubmed_pipeline(self) -> Dict[str, Any]:
        """Run the PubMed pipeline for the Cassava trial."""
        logger.info(f"Starting PubMed pipeline for {self.cassava_trial['nct_id']}")
        
        # Create pipeline with Cassava trial configuration
        pipeline_config = {
            **self.pipeline_config,
            "asset_names": self.cassava_trial["asset_names"],
            "indications": self.cassava_trial["indications"],
            "trial_phases": [self.cassava_trial["trial_phase"]],
            "date_range": ("2020/01/01", "2024/12/31"),  # 5-year window
            "max_results": 1000
        }
        
        async with PubMedPipeline(pipeline_config) as pipeline:
            # Execute all stages
            results = await pipeline.execute_pipeline(
                asset_names=self.cassava_trial["asset_names"],
                indications=self.cassava_trial["indications"],
                trial_phases=[self.cassava_trial["trial_phase"]],
                date_range=("2020/01/01", "2024/12/31"),  # 5-year window
                max_results=1000,
                enable_stages=['U0', 'U1', 'OA']
            )
            
            # Process results
            pipeline_summary = {
                "total_documents": 0,
                "documents_by_stage": {},
                "documents_by_relevance": {},
                "documents_by_shortability": {},
                "top_documents": []
            }
            
            for result in results:
                if result.success:
                    stage_name = result.stage
                    pipeline_summary["documents_by_stage"][stage_name] = result.documents_processed
                    pipeline_summary["total_documents"] += result.documents_processed
                    
                    # For now, just track the stage results
                    # Document analysis would require accessing the actual documents from the pipeline
                    # which are not directly exposed in the PipelineResult
            
            # Sort top documents by combined score
            pipeline_summary["top_documents"].sort(
                key=lambda x: x["relevance_score"] * x["shortability_score"], 
                reverse=True
            )
            pipeline_summary["top_documents"] = pipeline_summary["top_documents"][:10]
            
            return pipeline_summary
    
    async def verify_with_llm(self, pipeline_documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Use LLM to verify if we missed any important papers."""
        logger.info("Starting LLM verification of PubMed results")
        
        # Initialize GPT-5 thinking hook
        hook = GPT5ThinkingHook()
        
        # Prepare document summary for LLM
        doc_summary = []
        for i, doc in enumerate(pipeline_documents[:20]):  # Top 20 documents
            doc_summary.append(f"{i+1}. {doc['title']} ({doc['year']}) - PMID: {doc['pmid']}")
            doc_summary.append(f"   Authors: {doc['authors']}")
            doc_summary.append(f"   Relevance: {doc['relevance_score']:.2f}, Shortability: {doc['shortability_score']:.2f}")
            doc_summary.append(f"   Abstract: {doc['abstract']}")
            doc_summary.append("")
        
        # LLM verification prompt
        verification_prompt = f"""
You are an expert clinical researcher reviewing literature search results for the Cassava Sciences simufilam trial (NCT04388254).

TRIAL CONTEXT:
- NCT ID: {self.cassava_trial['nct_id']}
- Drug: simufilam (PTI-125)
- Mechanism: filamin A inhibitor
- Indication: Alzheimer's disease
- Phase: {self.cassava_trial['trial_phase']}
- Primary Endpoint: {self.cassava_trial['primary_endpoint']}
- Completion: {self.cassava_trial['completion_date']}

DOCUMENTS FOUND BY PIPELINE:
{chr(10).join(doc_summary)}

TASK:
1. Evaluate if the pipeline found the most important papers for this trial
2. Identify any critical papers that might be missing
3. Assess the quality and relevance of the search results
4. Suggest additional search terms or strategies if needed

REQUIRED OUTPUT FORMAT (JSON):
{{
    "pipeline_assessment": {{
        "coverage_score": 0.0-1.0,
        "quality_score": 0.0-1.0,
        "missing_critical_papers": true/false,
        "assessment_notes": "Brief assessment"
    }},
    "missing_papers": [
        {{
            "title": "Paper title",
            "authors": "Authors",
            "journal": "Journal",
            "year": "Year",
            "reason_missing": "Why this paper is important",
            "search_terms": ["term1", "term2"]
        }}
    ],
    "suggested_improvements": [
        "Specific improvement suggestion"
    ],
    "overall_verdict": "Brief summary of pipeline performance"
}}

IMPORTANT:
- Focus on papers directly related to simufilam, filamin A inhibition, or Cassava Sciences
- Consider papers about similar Alzheimer's mechanisms or endpoints
- Look for papers that might contain safety signals or efficacy concerns
- Be specific about what's missing and why it matters
"""
        
        try:
            # Use the literature review agent for verification
            literature_result = await hook.literature_agent.review_literature(
                trial_id="cassava_001",
                nct_id=self.cassava_trial["nct_id"],
                indication=self.cassava_trial["indications"][0],
                phase=self.cassava_trial["trial_phase"],
                primary_endpoint=self.cassava_trial["primary_endpoint"],
                mechanism=self.cassava_trial["mechanism"]
            )
            
            # Process LLM results
            llm_verification = {
                "llm_found_trials": len(literature_result.relevant_trials),
                "llm_found_papers": len(literature_result.relevant_papers),
                "llm_confidence": literature_result.confidence_score,
                "llm_trials": literature_result.relevant_trials[:5],
                "llm_papers": literature_result.relevant_papers[:5],
                "verification_notes": literature_result.search_notes
            }
            
            return llm_verification
            
        except Exception as e:
            logger.error(f"LLM verification failed: {e}")
            return {
                "error": str(e),
                "llm_found_trials": 0,
                "llm_found_papers": 0,
                "llm_confidence": 0.0
            }
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate comprehensive summary of the backtest."""
        pipeline_results = self.results["pipeline_results"]
        llm_verification = self.results["llm_verification"]
        
        # Calculate coverage metrics
        total_docs = pipeline_results.get("total_documents", 0)
        high_relevance = pipeline_results.get("documents_by_relevance", {}).get("high", 0)
        high_shortability = pipeline_results.get("documents_by_shortability", {}).get("high", 0)
        
        # LLM comparison
        llm_papers = llm_verification.get("llm_found_papers", 0)
        llm_confidence = llm_verification.get("llm_confidence", 0.0)
        
        summary = {
            "pipeline_performance": {
                "total_documents_found": total_docs,
                "high_relevance_documents": high_relevance,
                "high_shortability_documents": high_shortability,
                "relevance_coverage": high_relevance / max(total_docs, 1),
                "shortability_coverage": high_shortability / max(total_docs, 1)
            },
            "llm_verification": {
                "llm_found_papers": llm_papers,
                "llm_confidence": llm_confidence,
                "pipeline_vs_llm": f"{total_docs} vs {llm_papers} papers"
            },
            "quality_assessment": {
                "pipeline_quality": "good" if total_docs >= 20 else "needs_improvement",
                "llm_agreement": "high" if llm_confidence >= 0.7 else "low",
                "overall_verdict": "pass" if total_docs >= 20 and llm_confidence >= 0.6 else "fail"
            }
        }
        
        return summary
    
    async def run_full_backtest(self) -> Dict[str, Any]:
        """Run the complete PubMed backtest."""
        logger.info("Starting PubMed Literature Review Backtest")
        
        # Step 1: Run PubMed pipeline
        logger.info("Step 1: Running PubMed pipeline")
        pipeline_results = await self.run_pubmed_pipeline()
        self.results["pipeline_results"] = pipeline_results
        
        # Step 2: LLM verification
        logger.info("Step 2: Running LLM verification")
        llm_verification = await self.verify_with_llm(pipeline_results.get("top_documents", []))
        self.results["llm_verification"] = llm_verification
        
        # Step 3: Generate summary
        logger.info("Step 3: Generating summary")
        summary = self.generate_summary()
        self.results["summary"] = summary
        
        return self.results


async def main():
    """Main function to run the PubMed backtest."""
    parser = argparse.ArgumentParser(description="PubMed Literature Review Backtest")
    parser.add_argument("--output", default="backtest/pubmed_cassava_backtest.json", 
                       help="Output file for results")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)
    
    # Run backtest
    backtest = PubMedBacktest()
    results = await backtest.run_full_backtest()
    
    # Save results
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    # Print summary
    summary = results["summary"]
    print("\n" + "="*60)
    print("🎯 PubMed Literature Review Backtest Summary")
    print("="*60)
    print(f"📊 Pipeline Performance:")
    print(f"   Total Documents Found: {summary['pipeline_performance']['total_documents_found']}")
    print(f"   High Relevance Documents: {summary['pipeline_performance']['high_relevance_documents']}")
    print(f"   High Shortability Documents: {summary['pipeline_performance']['high_shortability_documents']}")
    print(f"   Relevance Coverage: {summary['pipeline_performance']['relevance_coverage']:.2%}")
    print(f"   Shortability Coverage: {summary['pipeline_performance']['shortability_coverage']:.2%}")
    
    print(f"\n🤖 LLM Verification:")
    print(f"   LLM Found Papers: {summary['llm_verification']['llm_found_papers']}")
    print(f"   LLM Confidence: {summary['llm_verification']['llm_confidence']:.2f}")
    print(f"   Pipeline vs LLM: {summary['llm_verification']['pipeline_vs_llm']}")
    
    print(f"\n📈 Quality Assessment:")
    print(f"   Pipeline Quality: {summary['quality_assessment']['pipeline_quality']}")
    print(f"   LLM Agreement: {summary['quality_assessment']['llm_agreement']}")
    print(f"   Overall Verdict: {summary['quality_assessment']['overall_verdict'].upper()}")
    
    print(f"\n💾 Results saved to: {output_path}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
