#!/usr/bin/env python3
"""
Study Card Quality Integration Test

This test ensures that study cards are generated with proper quality metrics:
- Non-zero quotes and evidence spans
- Proper method/results/gates extraction
- LLM artifacts present
- Confidence scores above threshold
- Real PubMed pipeline execution
- Proper BaseSpan configuration
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
from src.ncfd.extract.pipeline import StudyCardPipeline
from src.ncfd.db.models import Trial, Document, DocumentText, DocumentLink, DocRSScore, TrialDocCandidate, TrialLitState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StudyCardQualityTest:
    """Test study card generation quality and completeness."""
    
    def __init__(self, session):
        self.session = session
        self.orchestrator = None
        self.results = {
            "success": False,
            "test_name": "Study Card Quality Integration Test",
            "test_timestamp": datetime.now(timezone.utc).isoformat(),
            "quality_metrics": None,
            "issues_found": [],
            "recommendations": []
        }
    
    async def run_quality_test(self, nct_id: str = "NCT04388254"):
        """Run comprehensive study card quality test."""
        try:
            logger.info("🔬 Study Card Quality Test initialized")
            logger.info("🚀 Starting Study Card Quality Test")
            
            # Step 1: Add trial to database
            trial_info = await self._add_trial_to_db(nct_id)
            
            # Step 2: Initialize orchestrator
            self.orchestrator = UnifiedPipelineOrchestrator()
            
            # Step 3: Run PubMed pipeline
            pubmed_result = await self._run_pubmed_pipeline()
            
            # Step 4: Run study card pipeline
            study_card_result = await self._run_study_card_pipeline(trial_info)
            
            # Step 5: Analyze quality metrics
            quality_metrics = self._analyze_quality_metrics(study_card_result)
            self.results["quality_metrics"] = quality_metrics
            
            # Step 6: Check for issues
            issues = self._check_for_issues(quality_metrics, pubmed_result, study_card_result)
            self.results["issues_found"] = issues
            
            # Step 7: Generate recommendations
            recommendations = self._generate_recommendations(issues)
            self.results["recommendations"] = recommendations
            
            # Step 8: Determine overall success
            self.results["success"] = len(issues) == 0
            
            logger.info("✅ Study Card Quality Test completed!")
            
            # Save results
            self._save_results()
            
            return self.results
            
        except Exception as e:
            logger.error(f"❌ Quality test failed: {e}")
            self.results["error"] = str(e)
            self.results["success"] = False
            self._save_results()
            raise
    
    async def _add_trial_to_db(self, nct_id: str):
        """Add trial to database for testing."""
        logger.info(f"🔍 Adding trial {nct_id} to database...")
        
        # Check if trial already exists
        existing = self.session.query(Trial).filter(Trial.nct_id == nct_id).first()
        if existing:
            logger.info(f"Trial {nct_id} already exists (ID: {existing.trial_id})")
            return {"trial_id": existing.trial_id, "nct_id": nct_id}
        
        # Create new trial
        trial = Trial(
            nct_id=nct_id,
            official_title="Test Trial for Quality Assessment",
            brief_title="Quality Test Trial",
            status="Recruiting",
            phase="Phase 2",
            indication="Test Indication",
            sponsor_text="Test Sponsor",
            current_sha256="test_sha256_hash"
        )
        
        self.session.add(trial)
        self.session.flush()
        trial_id = trial.trial_id
        
        logger.info(f"Created trial {nct_id} (ID: {trial_id})")
        return {"trial_id": trial_id, "nct_id": nct_id}
    
    async def _run_pubmed_pipeline(self):
        """Run PubMed pipeline and check for issues."""
        logger.info("📚 Running PubMed pipeline...")
        
        try:
            result = await self.orchestrator._execute_pubmed_pipeline()
            
            # Check for common issues
            issues = []
            if result.get("documents_processed", 0) == 0:
                issues.append("PubMed pipeline processed 0 documents")
            if result.get("documents_failed", 0) > 0:
                issues.append(f"PubMed pipeline failed on {result['documents_failed']} documents")
            if "async mismatch" in str(result.get("errors", [])):
                issues.append("PubMed async mismatch detected")
            
            return {
                "success": len(issues) == 0,
                "result": result,
                "issues": issues
            }
            
        except Exception as e:
            logger.error(f"❌ PubMed pipeline failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "issues": [f"PubMed pipeline exception: {e}"]
            }
    
    async def _run_study_card_pipeline(self, trial_info):
        """Run study card pipeline and check for issues."""
        logger.info("📄 Running study card pipeline...")
        
        try:
            # Initialize study card pipeline
            pipeline = StudyCardPipeline()
            
            # Run pipeline
            result = await pipeline.run_pipeline(trial_info["trial_id"])
            
            # Check for common issues
            issues = []
            if not result.get("study_card"):
                issues.append("No study card generated")
            else:
                study_card = result["study_card"]
                if study_card.get("documents_analyzed", 0) == 0:
                    issues.append("Study card has 0 documents analyzed")
                if study_card.get("quotes", 0) == 0:
                    issues.append("Study card has 0 quotes")
                if study_card.get("evidence_spans", 0) == 0:
                    issues.append("Study card has 0 evidence spans")
                if not study_card.get("method"):
                    issues.append("Study card missing method section")
                if not study_card.get("results"):
                    issues.append("Study card missing results section")
                if not study_card.get("gates"):
                    issues.append("Study card missing gates section")
                if study_card.get("llm_artifacts", 0) == 0:
                    issues.append("Study card has 0 LLM artifacts")
                if study_card.get("avg_confidence", 0) < 0.5:
                    issues.append(f"Study card low confidence: {study_card.get('avg_confidence', 0)}")
            
            return {
                "success": len(issues) == 0,
                "result": result,
                "issues": issues
            }
            
        except Exception as e:
            logger.error(f"❌ Study card pipeline failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "issues": [f"Study card pipeline exception: {e}"]
            }
    
    def _analyze_quality_metrics(self, study_card_result):
        """Analyze study card quality metrics."""
        if not study_card_result.get("result", {}).get("study_card"):
            return {
                "documents_analyzed": 0,
                "quotes": 0,
                "evidence_spans": 0,
                "method_present": False,
                "results_present": False,
                "gates_present": False,
                "llm_artifacts": 0,
                "avg_confidence": 0.0,
                "quality_score": 0.0
            }
        
        study_card = study_card_result["result"]["study_card"]
        
        metrics = {
            "documents_analyzed": study_card.get("documents_analyzed", 0),
            "quotes": study_card.get("quotes", 0),
            "evidence_spans": study_card.get("evidence_spans", 0),
            "method_present": bool(study_card.get("method")),
            "results_present": bool(study_card.get("results")),
            "gates_present": bool(study_card.get("gates")),
            "llm_artifacts": study_card.get("llm_artifacts", 0),
            "avg_confidence": study_card.get("avg_confidence", 0.0)
        }
        
        # Calculate quality score
        quality_score = 0.0
        if metrics["documents_analyzed"] > 0:
            quality_score += 0.2
        if metrics["quotes"] > 0:
            quality_score += 0.2
        if metrics["evidence_spans"] > 0:
            quality_score += 0.2
        if metrics["method_present"]:
            quality_score += 0.1
        if metrics["results_present"]:
            quality_score += 0.1
        if metrics["gates_present"]:
            quality_score += 0.1
        if metrics["llm_artifacts"] > 0:
            quality_score += 0.1
        
        metrics["quality_score"] = quality_score
        
        return metrics
    
    def _check_for_issues(self, quality_metrics, pubmed_result, study_card_result):
        """Check for specific issues that cause degenerate study cards."""
        issues = []
        
        # Check quality metrics
        if quality_metrics["documents_analyzed"] == 0:
            issues.append("No documents analyzed")
        if quality_metrics["quotes"] == 0:
            issues.append("No quotes extracted")
        if quality_metrics["evidence_spans"] == 0:
            issues.append("No evidence spans found")
        if not quality_metrics["method_present"]:
            issues.append("Method section missing")
        if not quality_metrics["results_present"]:
            issues.append("Results section missing")
        if not quality_metrics["gates_present"]:
            issues.append("Gates section missing")
        if quality_metrics["llm_artifacts"] == 0:
            issues.append("No LLM artifacts generated")
        if quality_metrics["avg_confidence"] < 0.5:
            issues.append(f"Low confidence score: {quality_metrics['avg_confidence']}")
        
        # Check PubMed issues
        if pubmed_result.get("issues"):
            issues.extend(pubmed_result["issues"])
        
        # Check study card issues
        if study_card_result.get("issues"):
            issues.extend(study_card_result["issues"])
        
        return issues
    
    def _generate_recommendations(self, issues):
        """Generate recommendations based on issues found."""
        recommendations = []
        
        for issue in issues:
            if "PubMed" in issue:
                recommendations.append("Fix PubMed pipeline async handling and document processing")
            elif "span" in issue.lower():
                recommendations.append("Fix BaseSpan configuration and schema")
            elif "CT.gov" in issue:
                recommendations.append("Ensure CT.gov pipeline retrieves full trial data")
            elif "SEC" in issue:
                recommendations.append("Populate SEC universe with company data")
            elif "title missing" in issue.lower():
                recommendations.append("Fix trial title lookup in database")
            elif "confidence" in issue.lower():
                recommendations.append("Improve LLM confidence scoring and validation")
            elif "quotes" in issue.lower():
                recommendations.append("Fix quote extraction and evidence span generation")
            elif "method" in issue.lower() or "results" in issue.lower() or "gates" in issue.lower():
                recommendations.append("Fix study card section generation")
            else:
                recommendations.append(f"Investigate and fix: {issue}")
        
        return recommendations
    
    def _save_results(self):
        """Save test results to file."""
        output_file = "study_card_quality_test_results.json"
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        logger.info(f"💾 Results saved to {output_file}")


@pytest.mark.asyncio
async def test_study_card_quality(session):
    """Test study card generation quality and completeness."""
    test = StudyCardQualityTest(session)
    
    try:
        results = await test.run_quality_test()
        
        # Print summary
        print("\n" + "="*80)
        print("🎯 STUDY CARD QUALITY TEST SUMMARY")
        print("="*80)
        print(f"✅ Test Status: {'SUCCESS' if results['success'] else 'FAILED'}")
        
        if results["quality_metrics"]:
            metrics = results["quality_metrics"]
            print(f"📊 Quality Metrics:")
            print(f"   • Documents Analyzed: {metrics['documents_analyzed']}")
            print(f"   • Quotes: {metrics['quotes']}")
            print(f"   • Evidence Spans: {metrics['evidence_spans']}")
            print(f"   • Method Present: {'✅' if metrics['method_present'] else '❌'}")
            print(f"   • Results Present: {'✅' if metrics['results_present'] else '❌'}")
            print(f"   • Gates Present: {'✅' if metrics['gates_present'] else '❌'}")
            print(f"   • LLM Artifacts: {metrics['llm_artifacts']}")
            print(f"   • Avg Confidence: {metrics['avg_confidence']:.3f}")
            print(f"   • Quality Score: {metrics['quality_score']:.3f}")
        
        if results["issues_found"]:
            print(f"\n🚨 Issues Found ({len(results['issues_found'])}):")
            for issue in results["issues_found"]:
                print(f"   • {issue}")
        
        if results["recommendations"]:
            print(f"\n💡 Recommendations ({len(results['recommendations'])}):")
            for rec in results["recommendations"]:
                print(f"   • {rec}")
        
        print("="*80)
        
        # Assertions
        assert results['success'], f"Quality test failed: {results.get('error', 'Unknown error')}"
        assert results['quality_metrics']['quality_score'] >= 0.7, "Quality score too low"
        assert len(results['issues_found']) == 0, f"Issues found: {results['issues_found']}"
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}")
        print(f"\n❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v", "-s"])
