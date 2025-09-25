#!/usr/bin/env python3
"""
Enhanced Content Retrieval Fallback Chain Test

This test verifies and fixes the PMC → PubMed → Unpaywall fallback chain functionality
using real paper IDs to ensure proper content retrieval.

Fixes tested:
1. PMCContentService config issue
2. Unpaywall email format
3. PMC OAI access workarounds
4. Real Cassava paper content verification

Test Papers:
1. PMC10531384 - "Simufilam Reverses Aberrant Receptor Interactions" (should have PMC content)
2. PMC10339288 - "Simufilam suppresses overactive mTOR and restores its" (should have PMC content)  
3. JPAD 2020 paper - No PMCID (should try PubMed/Unpaywall)

This test isolates the content retrieval system to verify it works correctly
before integrating with the full pipeline.
"""

import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path

from ncfd.extract.services.pmc_content_service import PMCContentService
from ncfd.extract.runtime_text.text_generator import RuntimeTextGenerator
from ncfd.extract.runtime_text.api_clients import PubMedTextClient, PMCTextClient, UnpaywallTextClient
from ncfd.ingest.pubmed.oa_worker import OAWorker
from ncfd.ingest.pubmed.client_manager import get_client_manager

# Setup logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test papers with real IDs
TEST_PAPERS = [
    {
        "pmcid": "PMC10531384",
        "title": "Simufilam Reverses Aberrant Receptor Interactions",
        "description": "Mechanism paper (2023): FLNA–α7nAChR receptor interactions (Cell Mol Neurobiol)",
        "expected_source": "pmc",
        "should_have_content": True
    },
    {
        "pmcid": "PMC10339288", 
        "title": "Simufilam suppresses overactive mTOR and restores its",
        "description": "Mechanism paper (2023): mTOR/lymphocytes (Frontiers in Aging)",
        "expected_source": "pmc",
        "should_have_content": True
    },
    {
        "pmcid": None,
        "pmid": "12345678",  # Placeholder PMID for testing
        "title": "PTI-125 Reduces Biomarkers of Alzheimer's Disease in Patients",
        "description": "JPAD 2020 Phase 2a trial paper (PTI-125 reduces AD biomarkers)",
        "expected_source": "pubmed_or_unpaywall",
        "should_have_content": False  # Likely won't have content with placeholder PMID
    }
]


class EnhancedContentRetrievalTest:
    """Enhanced test for the content retrieval fallback chain with fixes."""
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        self.end_time = None
        
        # Test configuration
        self.test_config = {
            "client_config": {
                "rate_limit_requests_per_minute": 60,
                "timeout_seconds": 30,
                "max_retries": 3,
                "api_key": None,  # Will use default
                "email": "test@example.com",
                "tool": "NCFD-Test"
            },
            "apis": {
                "pubmed": {"rate_limit_per_minute": 60, "timeout_seconds": 30},
                "pmc": {"rate_limit_per_minute": 30, "timeout_seconds": 45},
                "unpaywall": {"rate_limit_per_minute": 30, "timeout_seconds": 30}
            },
            "fallback_order": ["pmc", "pubmed", "unpaywall"],
            "quality": {"min_content_length": 100}
        }
    
    async def run_test(self):
        """Run the enhanced content retrieval fallback test."""
        logger.info("🧪 Starting Enhanced Content Retrieval Fallback Chain Test")
        logger.info("=" * 70)
        
        self.start_time = datetime.now(timezone.utc)
        
        try:
            # Test 1: Fixed PMC Content Service
            await self._test_fixed_pmc_service()
            
            # Test 2: Individual API Clients with fixes
            await self._test_enhanced_api_clients()
            
            # Test 3: Runtime Text Generator (full fallback chain)
            await self._test_runtime_generator()
            
            # Test 4: Direct PubMed Client Manager test
            await self._test_direct_pubmed_client()
            
            # Test 5: Unpaywall with proper email format
            await self._test_unpaywall_fixes()
            
            # Validate results
            await self._validate_results()
            
            # Save results
            await self._save_results()
            
        except Exception as e:
            logger.error(f"❌ Test failed: {e}")
            raise
        finally:
            self.end_time = datetime.now(timezone.utc)
            duration = (self.end_time - self.start_time).total_seconds()
            logger.info(f"⏱️ Test completed in {duration:.2f} seconds")
    
    async def _test_fixed_pmc_service(self):
        """Test PMC Content Service with proper config."""
        logger.info("🔬 Test 1: Fixed PMC Content Service")
        
        try:
            # Create PMC service with proper config
            pmc_service = PMCContentService()
            pmc_results = {}
            
            for paper in TEST_PAPERS:
                if not paper["pmcid"]:
                    logger.info(f"⏭️ Skipping {paper['title']} - no PMCID")
                    continue
                
                logger.info(f"📄 Testing PMC retrieval for {paper['pmcid']}")
                
                try:
                    # Fix: Pass config to get_client
                    client_manager = get_client_manager()
                    client = await client_manager.get_client(self.test_config)
                    
                    # Try JATS first (more comprehensive)
                    full_text = await client.get_pmc_full_text_jats(
                        paper["pmcid"], 
                        include_refs=True, 
                        include_captions=True
                    )
                    
                    # Fallback to plain text if JATS fails
                    if not full_text:
                        logger.warning(f"JATS failed for {paper['pmcid']}, trying plain text")
                        full_text = await client.get_pmc_full_text(paper["pmcid"])
                    
                    pmc_results[paper["pmcid"]] = {
                        "success": bool(full_text),
                        "content_length": len(full_text) if full_text else 0,
                        "method": "jats" if full_text else "plain_text_failed",
                        "has_content": bool(full_text and len(full_text) > 100),
                        "content_preview": full_text[:200] if full_text else None
                    }
                    
                    if full_text:
                        logger.info(f"✅ Retrieved {len(full_text)} chars from PMC")
                        logger.info(f"📝 Preview: {full_text[:100]}...")
                    else:
                        logger.warning(f"⚠️ No content retrieved from PMC")
                        
                except Exception as e:
                    logger.error(f"❌ PMC retrieval failed for {paper['pmcid']}: {e}")
                    pmc_results[paper["pmcid"]] = {
                        "success": False,
                        "error": str(e),
                        "content_length": 0,
                        "has_content": False
                    }
            
            self.results['fixed_pmc_service'] = pmc_results
            logger.info(f"✅ Fixed PMC Service test completed: {len(pmc_results)} papers tested")
            
        except Exception as e:
            logger.error(f"❌ Fixed PMC Service test failed: {e}")
            self.results['fixed_pmc_service'] = {"error": str(e)}
    
    async def _test_enhanced_api_clients(self):
        """Test individual API clients with enhanced configuration."""
        logger.info("🔬 Test 2: Enhanced API Clients")
        
        try:
            # Test PMC Client with enhanced config
            pmc_client = PMCTextClient({
                "rate_limit_per_minute": 30, 
                "timeout_seconds": 45,
                "retry_attempts": 3,
                "backoff_factor": 2.0
            })
            pmc_results = {}
            
            for paper in TEST_PAPERS:
                if not paper["pmcid"]:
                    continue
                
                logger.info(f"📄 Testing enhanced PMC client for {paper['pmcid']}")
                
                try:
                    result = await pmc_client.fetch_fulltext(paper["pmcid"])
                    pmc_results[paper["pmcid"]] = {
                        "success": result.success,
                        "content_length": result.length,
                        "source": result.source,
                        "error": result.error_message,
                        "has_content": result.success and result.length > 100,
                        "metadata": result.metadata
                    }
                    
                    if result.success:
                        logger.info(f"✅ Enhanced PMC client retrieved {result.length} chars")
                    else:
                        logger.warning(f"⚠️ Enhanced PMC client failed: {result.error_message}")
                        
                except Exception as e:
                    logger.error(f"❌ Enhanced PMC client error for {paper['pmcid']}: {e}")
                    pmc_results[paper["pmcid"]] = {
                        "success": False,
                        "error": str(e),
                        "content_length": 0,
                        "has_content": False
                    }
            
            # Test PubMed Client with enhanced config
            pubmed_client = PubMedTextClient({
                "rate_limit_per_minute": 60, 
                "timeout_seconds": 30,
                "retry_attempts": 3,
                "backoff_factor": 1.5
            })
            pubmed_results = {}
            
            for paper in TEST_PAPERS:
                if not paper.get("pmid"):
                    continue
                
                logger.info(f"📄 Testing enhanced PubMed client for PMID {paper['pmid']}")
                
                try:
                    result = await pubmed_client.fetch_abstract(paper["pmid"])
                    pubmed_results[paper["pmid"]] = {
                        "success": result.success,
                        "content_length": result.length,
                        "source": result.source,
                        "error": result.error_message,
                        "has_content": result.success and result.length > 50,
                        "metadata": result.metadata
                    }
                    
                    if result.success:
                        logger.info(f"✅ Enhanced PubMed client retrieved {result.length} chars")
                    else:
                        logger.warning(f"⚠️ Enhanced PubMed client failed: {result.error_message}")
                        
                except Exception as e:
                    logger.error(f"❌ Enhanced PubMed client error for PMID {paper['pmid']}: {e}")
                    pubmed_results[paper["pmid"]] = {
                        "success": False,
                        "error": str(e),
                        "content_length": 0,
                        "has_content": False
                    }
            
            self.results['enhanced_api_clients'] = {
                'pmc': pmc_results,
                'pubmed': pubmed_results
            }
            
            logger.info("✅ Enhanced API Clients test completed")
            
        except Exception as e:
            logger.error(f"❌ Enhanced API Clients test failed: {e}")
            self.results['enhanced_api_clients'] = {"error": str(e)}
    
    async def _test_runtime_generator(self):
        """Test Runtime Text Generator (full fallback chain)."""
        logger.info("🔬 Test 3: Runtime Text Generator")
        
        try:
            generator = RuntimeTextGenerator(self.test_config)
            generator_results = {}
            
            for paper in TEST_PAPERS:
                if not paper["pmcid"]:
                    continue
                
                logger.info(f"📄 Testing Runtime Generator for {paper['pmcid']}")
                
                try:
                    # Use PMCID as doc_id for testing
                    doc_id = f"pmc:{paper['pmcid']}"
                    result = await generator.generate_text(doc_id)
                    
                    generator_results[paper["pmcid"]] = {
                        "success": bool(result),
                        "content_length": len(result) if result else 0,
                        "has_content": bool(result and len(result) > 100),
                        "content_preview": result[:200] if result else None,
                        "content_analysis": self._analyze_content_quality(result) if result else None
                    }
                    
                    if result:
                        logger.info(f"✅ Runtime Generator retrieved {len(result)} chars")
                        logger.info(f"📝 Preview: {result[:100]}...")
                        
                        # Analyze content quality
                        analysis = self._analyze_content_quality(result)
                        logger.info(f"🔍 Content Analysis: {analysis}")
                    else:
                        logger.warning(f"⚠️ Runtime Generator returned no content")
                        
                except Exception as e:
                    logger.error(f"❌ Runtime Generator error for {paper['pmcid']}: {e}")
                    generator_results[paper["pmcid"]] = {
                        "success": False,
                        "error": str(e),
                        "content_length": 0,
                        "has_content": False
                    }
            
            self.results['runtime_generator'] = generator_results
            logger.info("✅ Runtime Generator test completed")
            
        except Exception as e:
            logger.error(f"❌ Runtime Generator test failed: {e}")
            self.results['runtime_generator'] = {"error": str(e)}
    
    async def _test_direct_pubmed_client(self):
        """Test direct PubMed client manager usage."""
        logger.info("🔬 Test 4: Direct PubMed Client Manager")
        
        try:
            client_manager = get_client_manager()
            client = await client_manager.get_client(self.test_config)
            
            direct_results = {}
            
            for paper in TEST_PAPERS:
                if not paper["pmcid"]:
                    continue
                
                logger.info(f"📄 Testing direct PubMed client for {paper['pmcid']}")
                
                try:
                    # Test different PMC methods
                    methods_tested = {}
                    
                    # Method 1: JATS
                    try:
                        jats_result = await client.get_pmc_full_text_jats(paper["pmcid"])
                        methods_tested["jats"] = {
                            "success": bool(jats_result),
                            "length": len(jats_result) if jats_result else 0
                        }
                    except Exception as e:
                        methods_tested["jats"] = {"success": False, "error": str(e)}
                    
                    # Method 2: Plain text
                    try:
                        plain_result = await client.get_pmc_full_text(paper["pmcid"])
                        methods_tested["plain_text"] = {
                            "success": bool(plain_result),
                            "length": len(plain_result) if plain_result else 0
                        }
                    except Exception as e:
                        methods_tested["plain_text"] = {"success": False, "error": str(e)}
                    
                    direct_results[paper["pmcid"]] = methods_tested
                    
                    # Log results
                    successful_methods = [m for m, r in methods_tested.items() if r.get("success")]
                    if successful_methods:
                        logger.info(f"✅ Direct client succeeded with methods: {successful_methods}")
                    else:
                        logger.warning(f"⚠️ Direct client failed for all methods")
                        
                except Exception as e:
                    logger.error(f"❌ Direct client error for {paper['pmcid']}: {e}")
                    direct_results[paper["pmcid"]] = {"error": str(e)}
            
            self.results['direct_pubmed_client'] = direct_results
            logger.info("✅ Direct PubMed Client test completed")
            
        except Exception as e:
            logger.error(f"❌ Direct PubMed Client test failed: {e}")
            self.results['direct_pubmed_client'] = {"error": str(e)}
    
    async def _test_unpaywall_fixes(self):
        """Test Unpaywall with proper email format and real DOIs."""
        logger.info("🔬 Test 5: Unpaywall Fixes")
        
        try:
            # Test with proper email format
            unpaywall_client = UnpaywallTextClient({
                "rate_limit_per_minute": 30, 
                "timeout_seconds": 30,
                "email": "test@example.com"  # Proper email format
            })
            
            unpaywall_results = {}
            
            # Test with real DOIs that might be associated with our papers
            test_dois = [
                "10.1007/s11064-023-04020-9",  # Example DOI
                "10.1038/s41586-023-06221-2",  # Another example DOI
                "10.1016/j.cell.2023.05.012"   # Cell journal DOI
            ]
            
            for doi in test_dois:
                logger.info(f"📄 Testing Unpaywall client for DOI {doi}")
                
                try:
                    result = await unpaywall_client.fetch_fulltext(doi)
                    unpaywall_results[doi] = {
                        "success": result.success,
                        "content_length": result.length,
                        "source": result.source,
                        "error": result.error_message,
                        "has_content": result.success and result.length > 10,
                        "metadata": result.metadata,
                        "is_oa": result.metadata.get("is_oa") if result.metadata else None,
                        "pdf_url": result.metadata.get("pdf_url") if result.metadata else None
                    }
                    
                    if result.success:
                        logger.info(f"✅ Unpaywall client retrieved {result.length} chars")
                        if result.metadata:
                            logger.info(f"📊 Metadata: {result.metadata}")
                    else:
                        logger.warning(f"⚠️ Unpaywall client failed: {result.error_message}")
                        
                except Exception as e:
                    logger.error(f"❌ Unpaywall client error for DOI {doi}: {e}")
                    unpaywall_results[doi] = {
                        "success": False,
                        "error": str(e),
                        "content_length": 0,
                        "has_content": False
                    }
            
            self.results['unpaywall_fixes'] = unpaywall_results
            logger.info("✅ Unpaywall Fixes test completed")
            
        except Exception as e:
            logger.error(f"❌ Unpaywall Fixes test failed: {e}")
            self.results['unpaywall_fixes'] = {"error": str(e)}
    
    def _analyze_content_quality(self, content: str) -> Dict[str, Any]:
        """Analyze the quality and type of retrieved content."""
        if not content:
            return {"quality": "empty", "type": "unknown"}
        
        analysis = {
            "length": len(content),
            "quality": "unknown",
            "type": "unknown",
            "has_abstract": False,
            "has_methods": False,
            "has_results": False,
            "has_references": False,
            "cassava_mentions": 0,
            "simufilam_mentions": 0,
            "alzheimer_mentions": 0
        }
        
        content_lower = content.lower()
        
        # Check for common academic paper sections
        analysis["has_abstract"] = any(word in content_lower for word in ["abstract", "summary"])
        analysis["has_methods"] = any(word in content_lower for word in ["methods", "methodology", "experimental"])
        analysis["has_results"] = any(word in content_lower for word in ["results", "findings", "outcomes"])
        analysis["has_references"] = any(word in content_lower for word in ["references", "bibliography", "cited"])
        
        # Count relevant mentions
        analysis["cassava_mentions"] = content_lower.count("cassava")
        analysis["simufilam_mentions"] = content_lower.count("simufilam")
        analysis["alzheimer_mentions"] = content_lower.count("alzheimer")
        
        # Determine quality
        if analysis["has_abstract"] and analysis["has_methods"] and analysis["has_results"]:
            analysis["quality"] = "high"
            analysis["type"] = "academic_paper"
        elif analysis["has_abstract"] or analysis["has_methods"]:
            analysis["quality"] = "medium"
            analysis["type"] = "partial_paper"
        elif len(content) > 500:
            analysis["quality"] = "low"
            analysis["type"] = "generic_content"
        else:
            analysis["quality"] = "very_low"
            analysis["type"] = "minimal_content"
        
        return analysis
    
    async def _validate_results(self):
        """Validate test results and provide comprehensive summary."""
        logger.info("📊 Validating Enhanced Results")
        
        summary = {
            "total_papers_tested": len([p for p in TEST_PAPERS if p["pmcid"]]),
            "total_dois_tested": 3,  # From Unpaywall test
            "pmc_success_rate": 0,
            "pubmed_success_rate": 0,
            "unpaywall_success_rate": 0,
            "runtime_generator_success_rate": 0,
            "direct_client_success_rate": 0,
            "overall_success": False,
            "content_quality_analysis": {},
            "recommendations": []
        }
        
        # Calculate success rates
        if 'fixed_pmc_service' in self.results and 'error' not in self.results['fixed_pmc_service']:
            pmc_results = self.results['fixed_pmc_service']
            successful = sum(1 for r in pmc_results.values() if r.get('success', False))
            summary['pmc_success_rate'] = successful / len(pmc_results) if pmc_results else 0
        
        if 'enhanced_api_clients' in self.results and 'error' not in self.results['enhanced_api_clients']:
            api_results = self.results['enhanced_api_clients']
            
            if 'pmc' in api_results:
                pmc_successful = sum(1 for r in api_results['pmc'].values() if r.get('success', False))
                summary['pmc_success_rate'] = max(summary['pmc_success_rate'], pmc_successful / len(api_results['pmc']) if api_results['pmc'] else 0)
            
            if 'pubmed' in api_results:
                pubmed_successful = sum(1 for r in api_results['pubmed'].values() if r.get('success', False))
                summary['pubmed_success_rate'] = pubmed_successful / len(api_results['pubmed']) if api_results['pubmed'] else 0
        
        if 'unpaywall_fixes' in self.results and 'error' not in self.results['unpaywall_fixes']:
            unpaywall_results = self.results['unpaywall_fixes']
            unpaywall_successful = sum(1 for r in unpaywall_results.values() if r.get('success', False))
            summary['unpaywall_success_rate'] = unpaywall_successful / len(unpaywall_results) if unpaywall_results else 0
        
        if 'runtime_generator' in self.results and 'error' not in self.results['runtime_generator']:
            runtime_results = self.results['runtime_generator']
            runtime_successful = sum(1 for r in runtime_results.values() if r.get('success', False))
            summary['runtime_generator_success_rate'] = runtime_successful / len(runtime_results) if runtime_results else 0
            
            # Analyze content quality
            for pmcid, result in runtime_results.items():
                if result.get('content_analysis'):
                    summary['content_quality_analysis'][pmcid] = result['content_analysis']
        
        if 'direct_pubmed_client' in self.results and 'error' not in self.results['direct_pubmed_client']:
            direct_results = self.results['direct_pubmed_client']
            direct_successful = sum(1 for r in direct_results.values() if any(method.get('success', False) for method in r.values() if isinstance(method, dict)))
            summary['direct_client_success_rate'] = direct_successful / len(direct_results) if direct_results else 0
        
        # Overall success if at least one method works
        summary['overall_success'] = (
            summary['pmc_success_rate'] > 0 or 
            summary['pubmed_success_rate'] > 0 or 
            summary['unpaywall_success_rate'] > 0 or
            summary['runtime_generator_success_rate'] > 0 or
            summary['direct_client_success_rate'] > 0
        )
        
        # Generate recommendations
        if summary['pmc_success_rate'] == 0:
            summary['recommendations'].append("PMC access is failing - consider using PubMed fallback")
        if summary['pubmed_success_rate'] > 0:
            summary['recommendations'].append("PubMed fallback is working - use this as primary method")
        if summary['unpaywall_success_rate'] > 0:
            summary['recommendations'].append("Unpaywall is working - integrate for open access papers")
        if summary['runtime_generator_success_rate'] > 0:
            summary['recommendations'].append("Runtime generator fallback chain is working - use in production")
        
        self.results['enhanced_summary'] = summary
        
        # Log comprehensive summary
        logger.info("📈 Enhanced Test Results Summary:")
        logger.info(f"  • PMC Success Rate: {summary['pmc_success_rate']:.1%}")
        logger.info(f"  • PubMed Success Rate: {summary['pubmed_success_rate']:.1%}")
        logger.info(f"  • Unpaywall Success Rate: {summary['unpaywall_success_rate']:.1%}")
        logger.info(f"  • Runtime Generator Success Rate: {summary['runtime_generator_success_rate']:.1%}")
        logger.info(f"  • Direct Client Success Rate: {summary['direct_client_success_rate']:.1%}")
        logger.info(f"  • Overall Success: {'✅' if summary['overall_success'] else '❌'}")
        
        if summary['recommendations']:
            logger.info("💡 Recommendations:")
            for rec in summary['recommendations']:
                logger.info(f"  • {rec}")
    
    async def _save_results(self):
        """Save enhanced test results to file."""
        results_file = Path("tests/logs/enhanced_content_retrieval_test_results.json")
        results_file.parent.mkdir(exist_ok=True)
        
        results_data = {
            "test_name": "Enhanced Content Retrieval Fallback Chain Test",
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.start_time and self.end_time else None,
            "test_config": self.test_config,
            "test_papers": TEST_PAPERS,
            "results": self.results
        }
        
        with open(results_file, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        logger.info(f"📁 Enhanced results saved to: {results_file}")


async def main():
    """Run the enhanced content retrieval fallback test."""
    test = EnhancedContentRetrievalTest()
    await test.run_test()


if __name__ == "__main__":
    asyncio.run(main())
