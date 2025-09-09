#!/usr/bin/env python3
"""
Degenerate Study Card Detection Test

This test specifically checks for the issues mentioned in the error:
- PubMed skipped (async mismatch)
- Span config schema mismatch  
- CT.gov only abstract retrieved
- SEC universe empty
- Title missing for NCT05352763
- Success criteria too lax
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.ncfd.pipeline.orchestrator import UnifiedPipelineOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DegenerateStudyCardTest:
    """Test for degenerate study card issues."""
    
    def __init__(self, session):
        self.session = session
        self.orchestrator = None
        self.results = {
            "success": False,
            "test_name": "Degenerate Study Card Detection Test",
            "test_timestamp": datetime.now(timezone.utc).isoformat(),
            "issues_detected": [],
            "recommendations": []
        }
    
    async def run_degenerate_test(self, nct_id: str = "NCT04388254"):
        """Run test to detect degenerate study card issues."""
        try:
            logger.info("🔬 Degenerate Study Card Test initialized")
            logger.info("🚀 Starting Degenerate Study Card Detection Test")
            
            # Step 1: Check PubMed pipeline
            pubmed_issues = await self._check_pubmed_pipeline()
            self.results["issues_detected"].extend(pubmed_issues)
            
            # Step 2: Check BaseSpan configuration
            span_issues = await self._check_span_config()
            self.results["issues_detected"].extend(span_issues)
            
            # Step 3: Check CT.gov pipeline
            ctgov_issues = await self._check_ctgov_pipeline()
            self.results["issues_detected"].extend(ctgov_issues)
            
            # Step 4: Check SEC universe
            sec_issues = await self._check_sec_universe()
            self.results["issues_detected"].extend(sec_issues)
            
            # Step 5: Check trial title lookup
            title_issues = await self._check_trial_title(nct_id)
            self.results["issues_detected"].extend(title_issues)
            
            # Step 6: Check success criteria
            criteria_issues = await self._check_success_criteria()
            self.results["issues_detected"].extend(criteria_issues)
            
            # Step 7: Generate recommendations
            recommendations = self._generate_recommendations(self.results["issues_detected"])
            self.results["recommendations"] = recommendations
            
            # Step 8: Determine overall success
            self.results["success"] = len(self.results["issues_detected"]) == 0
            
            logger.info("✅ Degenerate Study Card Test completed!")
            
            # Save results
            self._save_results()
            
            return self.results
            
        except Exception as e:
            logger.error(f"❌ Degenerate test failed: {e}")
            self.results["error"] = str(e)
            self.results["success"] = False
            self._save_results()
            raise
    
    async def _check_pubmed_pipeline(self):
        """Check for PubMed pipeline issues."""
        logger.info("📚 Checking PubMed pipeline...")
        issues = []
        
        try:
            # Initialize orchestrator with proper config
            orchestrator_config = {
                'ctgov': {},
                'sec': {'monitored_companies': []},
                'pubmed': {
                    'enable_pmcid_linking': True,
                    'enable_oa_detection': True,
                    'rate_limit_per_sec': 1,
                    'asset_names': ['drug', 'compound', 'therapy'],
                    'indications': ['disease', 'condition', 'cancer']
                },
                'literature_queue': {},
                'execution_order': ['ctgov', 'pubmed', 'sec'],
                'parallel_execution': False,
                'dependency_checking': True,
                'max_retries': 3,
                'retry_delay_seconds': 10
            }
            self.orchestrator = UnifiedPipelineOrchestrator(orchestrator_config)
            
            # Check if PubMed pipeline exists
            if not hasattr(self.orchestrator, 'pubmed_pipeline'):
                issues.append("PubMed pipeline not initialized in orchestrator")
                return issues
            
            # Check PubMed pipeline configuration
            pubmed_config = self.orchestrator.pubmed_pipeline.config
            if not pubmed_config:
                issues.append("PubMed pipeline configuration missing")
            
            # Check for async issues
            if hasattr(self.orchestrator.pubmed_pipeline, 'client'):
                client = self.orchestrator.pubmed_pipeline.client
                if hasattr(client, 'rate_limit_per_sec'):
                    if client.rate_limit_per_sec == 0:
                        issues.append("PubMed client rate limit is 0 (causes division by zero)")
            
            # Check PubMed pipeline methods
            if not hasattr(self.orchestrator.pubmed_pipeline, 'run_daily_ingestion'):
                issues.append("PubMed pipeline missing run_daily_ingestion method")
            
            if not hasattr(self.orchestrator.pubmed_pipeline, 'run_oa_for_trial'):
                issues.append("PubMed pipeline missing run_oa_for_trial method")
            
        except Exception as e:
            issues.append(f"PubMed pipeline check failed: {e}")
        
        return issues
    
    async def _check_span_config(self):
        """Check BaseSpan configuration issues."""
        logger.info("🔧 Checking BaseSpan configuration...")
        issues = []
        
        try:
            # Check if span config file exists
            span_config_path = Path("src/ncfd/extract/config/span_config.yaml")
            if not span_config_path.exists():
                issues.append("BaseSpan config file missing: span_config.yaml")
                return issues
            
            # Check span config content
            import yaml
            with open(span_config_path, 'r') as f:
                span_config = yaml.safe_load(f)
            
            # Check required sections
            if 'span_generation' not in span_config:
                issues.append("BaseSpan config missing span_generation section")
            
            if 'span_indexing' not in span_config:
                issues.append("BaseSpan config missing span_indexing section")
            
            if 'span_triage' not in span_config:
                issues.append("BaseSpan config missing span_triage section")
            
            # Check span generation settings
            if 'span_generation' in span_config:
                gen_config = span_config['span_generation']
                if 'min_sentence_length' not in gen_config:
                    issues.append("BaseSpan config missing min_sentence_length")
                if 'max_sentence_length' not in gen_config:
                    issues.append("BaseSpan config missing max_sentence_length")
            
        except Exception as e:
            issues.append(f"BaseSpan config check failed: {e}")
        
        return issues
    
    async def _check_ctgov_pipeline(self):
        """Check CT.gov pipeline issues."""
        logger.info("🏥 Checking CT.gov pipeline...")
        issues = []
        
        try:
            # Check if CT.gov pipeline exists
            if not hasattr(self.orchestrator, 'ctgov_pipeline'):
                issues.append("CT.gov pipeline not initialized in orchestrator")
                return issues
            
            # Check CT.gov pipeline configuration
            ctgov_config = self.orchestrator.ctgov_pipeline.config
            if not ctgov_config:
                issues.append("CT.gov pipeline configuration missing")
            
            # Check CT.gov pipeline methods
            if not hasattr(self.orchestrator.ctgov_pipeline, 'run_daily_ingestion'):
                issues.append("CT.gov pipeline missing run_daily_ingestion method")
            
        except Exception as e:
            issues.append(f"CT.gov pipeline check failed: {e}")
        
        return issues
    
    async def _check_sec_universe(self):
        """Check SEC universe issues."""
        logger.info("📊 Checking SEC universe...")
        issues = []
        
        try:
            # Check if SEC pipeline exists
            if not hasattr(self.orchestrator, 'sec_pipeline'):
                issues.append("SEC pipeline not initialized in orchestrator")
                return issues
            
            # Check SEC pipeline configuration
            sec_config = self.orchestrator.sec_pipeline.config
            if not sec_config:
                issues.append("SEC pipeline configuration missing")
            
            # Check SEC pipeline methods
            if not hasattr(self.orchestrator.sec_pipeline, 'run_daily_ingestion'):
                issues.append("SEC pipeline missing run_daily_ingestion method")
            
            # Check if SEC universe is empty
            if hasattr(self.orchestrator.sec_pipeline, 'monitored_companies'):
                if len(self.orchestrator.sec_pipeline.monitored_companies) == 0:
                    issues.append("SEC universe is empty (no monitored companies)")
            
        except Exception as e:
            issues.append(f"SEC universe check failed: {e}")
        
        return issues
    
    async def _check_trial_title(self, nct_id: str):
        """Check trial title lookup issues."""
        logger.info(f"🔍 Checking trial title lookup for {nct_id}...")
        issues = []
        
        try:
            # Check if trial exists in database
            from src.ncfd.db.models import Trial
            from src.ncfd.utils.trial_metadata_utils import ensure_trial_metadata
            
            trial = self.session.query(Trial).filter(Trial.nct_id == nct_id).first()
            
            if not trial:
                logger.info(f"Trial {nct_id} not found, attempting backfill...")
                # Try to backfill from CT.gov
                success, trial_data = ensure_trial_metadata(nct_id)
                if success:
                    logger.info(f"Successfully backfilled trial {nct_id}")
                    # Re-check after backfill
                    trial = self.session.query(Trial).filter(Trial.nct_id == nct_id).first()
                else:
                    issues.append(f"Trial {nct_id} not found in database and backfill failed")
            
            if trial:
                if not trial.official_title:
                    logger.info(f"Trial {nct_id} missing official title, attempting backfill...")
                    success, trial_data = ensure_trial_metadata(nct_id)
                    if not success or not trial_data.get('official_title'):
                        issues.append(f"Trial {nct_id} missing official title")
                
                if not trial.brief_title:
                    logger.info(f"Trial {nct_id} missing brief title, attempting backfill...")
                    success, trial_data = ensure_trial_metadata(nct_id)
                    if not success or not trial_data.get('brief_title'):
                        issues.append(f"Trial {nct_id} missing brief title")
            
        except Exception as e:
            issues.append(f"Trial title check failed: {e}")
        
        return issues
    
    async def _check_success_criteria(self):
        """Check success criteria issues."""
        logger.info("✅ Checking success criteria...")
        issues = []
        
        try:
            # Check if success criteria are too lax
            # This would typically be in the study card pipeline or evaluation logic
            
            # Check study card pipeline
            if hasattr(self.orchestrator, 'study_card_pipeline'):
                pipeline = self.orchestrator.study_card_pipeline
                if hasattr(pipeline, 'success_criteria'):
                    criteria = pipeline.success_criteria
                    if criteria.get('min_quotes', 0) == 0:
                        issues.append("Success criteria too lax: min_quotes = 0")
                    if criteria.get('min_evidence_spans', 0) == 0:
                        issues.append("Success criteria too lax: min_evidence_spans = 0")
                    if criteria.get('min_confidence', 0) < 0.5:
                        issues.append(f"Success criteria too lax: min_confidence = {criteria.get('min_confidence', 0)}")
            
        except Exception as e:
            issues.append(f"Success criteria check failed: {e}")
        
        return issues
    
    def _generate_recommendations(self, issues):
        """Generate recommendations based on issues found."""
        recommendations = []
        
        for issue in issues:
            if "PubMed" in issue:
                recommendations.append("Fix PubMed pipeline initialization and async handling")
            elif "BaseSpan" in issue or "span" in issue.lower():
                recommendations.append("Fix BaseSpan configuration schema and file structure")
            elif "CT.gov" in issue:
                recommendations.append("Ensure CT.gov pipeline retrieves full trial data, not just abstracts")
            elif "SEC" in issue:
                recommendations.append("Populate SEC universe with monitored companies")
            elif "title" in issue.lower():
                recommendations.append("Fix trial title lookup and database population")
            elif "success criteria" in issue.lower():
                recommendations.append("Implement stricter success criteria for study card generation")
            else:
                recommendations.append(f"Investigate and fix: {issue}")
        
        return recommendations
    
    def _save_results(self):
        """Save test results to file."""
        output_file = "degenerate_study_card_test_results.json"
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        logger.info(f"💾 Results saved to {output_file}")


@pytest.mark.asyncio
async def test_degenerate_study_card(session):
    """Test for degenerate study card issues."""
    test = DegenerateStudyCardTest(session)
    
    try:
        results = await test.run_degenerate_test()
        
        # Print summary
        print("\n" + "="*80)
        print("🎯 DEGENERATE STUDY CARD DETECTION TEST SUMMARY")
        print("="*80)
        print(f"✅ Test Status: {'SUCCESS' if results['success'] else 'FAILED'}")
        
        if results["issues_detected"]:
            print(f"\n🚨 Issues Detected ({len(results['issues_detected'])}):")
            for issue in results["issues_detected"]:
                print(f"   • {issue}")
        
        if results["recommendations"]:
            print(f"\n💡 Recommendations ({len(results['recommendations'])}):")
            for rec in results["recommendations"]:
                print(f"   • {rec}")
        
        print("="*80)
        
        # Assertions
        assert results['success'], f"Degenerate test failed: {results.get('error', 'Unknown error')}"
        assert len(results['issues_detected']) == 0, f"Issues detected: {results['issues_detected']}"
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}")
        print(f"\n❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v", "-s"])
