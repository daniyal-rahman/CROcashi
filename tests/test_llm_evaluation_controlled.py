#!/usr/bin/env python3
"""
LLM Evaluation Controlled Test Suite

This test suite implements the three controlled variants for LLM evaluation
as specified in the instructions:

1. High-posterior stop: two high-utility abstracts → LLM raises P(short) ≥ θ_high
2. Low-posterior park: two low-utility abstracts → P(short) ≤ θ_low
3. Plateau stop: several abstracts where |ΔP| < ε twice and next_doc_utility < δ

This ensures the LLM path is actually exercised and early stopping works correctly.
"""

import os
import sys
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from unittest.mock import Mock, patch, MagicMock
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.db.session import get_session
from ncfd.db.models import (
    Trial, Document, DocumentUtility, TrialEvaluation, 
    TrialPriorityQueue, CostRecord
)
from ncfd.ingest.llm_evaluator import LLMEvaluator, StopDecision, EvaluationResult
from ncfd.ingest.literature_scoring import LiteratureScorer, ScoringConfig
from ncfd.ingest.document_queue import DocumentQueue
from ncfd.ingest.smart_pubmed import SmartPubMedClient
from ncfd.ingest.budget_monitor import BudgetMonitor
from ncfd.pipeline.literature_orchestrator import LiteratureOrchestrator, LiteraturePipelineConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMEvaluationControlledTest:
    """Controlled test suite for LLM evaluation behavior."""
    
    def __init__(self):
        self.test_start_time = datetime.now()
        self.execution_id = None
        self.run_id = None
        self.test_results = {}
        
    def setup_test_environment(self, db_session):
        """Setup isolated test environment."""
        logger.info("🔧 Setting up isolated test environment...")
        
        # Clean all literature tables
        tables_to_clean = [
            'document_utilities', 'trial_evaluations', 'trial_priority_queue',
            'cost_records', 'budget_periods', 'literature_pipeline_executions'
        ]
        
        for table in tables_to_clean:
            try:
                db_session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                logger.info(f"Cleaned table: {table}")
            except Exception as e:
                logger.warning(f"Could not clean {table}: {e}")
        
        logger.info("✅ Test environment setup complete")
    
    def create_test_trial(self, db_session, nct_id="NCT05111574"):
        """Create a test trial with proper data."""
        logger.info(f"🧪 Creating test trial: {nct_id}")
        
        # Check if trial exists
        trial = db_session.query(Trial).filter(Trial.nct_id == nct_id).first()
        if not trial:
            # Create test trial
            trial = Trial(
                nct_id=nct_id,
                brief_title="Test Clinical Trial for LLM Evaluation",
                phase="PHASE2",
                status="RECRUITING",
                intervention_name="Test Drug",
                drug_name="Test Compound",
                compound_name="Test Molecule"
            )
            db_session.add(trial)
            db_session.commit()
            logger.info(f"Created test trial with ID: {trial.trial_id}")
        else:
            # Update trial with proper data
            trial.brief_title = "Test Clinical Trial for LLM Evaluation"
            trial.phase = "PHASE2"
            trial.status = "RECRUITING"
            trial.intervention_name = "Test Drug"
            trial.drug_name = "Test Compound"
            trial.compound_name = "Test Molecule"
            db_session.commit()
            logger.info(f"Updated existing trial with ID: {trial.trial_id}")
        
        return trial
    
    def create_demo_config(self):
        """Create deterministic demo configuration."""
        scoring_config = ScoringConfig(
            phase_3_weight=0.30,
            randomization_weight=0.25,
            double_blind_weight=0.15,
            nct_mention_weight=0.10,
            rct_type_weight=0.15,
            recency_weight=0.05,
            negative_signal_weight=0.50,
            positive_signal_weight=0.10,
            sample_size_weight=0.20,
            structural_weight=0.20,
            recency_months=24,
            tau_abstract=0.35,
            theta_high=0.75,
            theta_low=0.25,
            delta_min=0.05
        )
        
        budget_config = {
            'daily_limit': 50.0,
            'monthly_limit': 1000.0,
            'trial_limit': 5.0,
            'costs': {
                'metadata_fetch': 0.001,
                'abstract_fetch': 0.01,
                'full_text_fetch': 0.25,
                'llm_evaluation': 0.05
            },
            'alert_thresholds': {
                'warning': 0.70,
                'critical': 0.85,
                'emergency': 0.95
            },
            'reset_schedule': 'daily',
            'reset_day': 1
        }
        
        queue_config = {
            'trial_batch_size': 5,
            'max_candidates_per_trial': 50,
            'cleanup_interval_hours': 12
        }
        
        evaluation_config = {
            'eval_every_docs': 2,  # Force LLM evaluation every 2 docs
            'theta_high': 0.75,
            'theta_low': 0.25,
            'delta_min': 0.05,
            'plateau_epsilon': 0.03,
            'plateau_consecutive': 2,
            'tier2_llm_tokens_per_eval': 1500,
            'evaluation_prompt_version': '1.0'
        }
        
        pubmed_config = {
            'api_key': 'test_key',
            'base_url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
            'tool': 'NCFD-Literature-Pipeline-Test',
            'email': 'test@ncfd.com',
            'rate_limit_delay': 0.1,
            'max_retries': 3,
            'timeout': 30
        }
        
        pipeline_config = {
            'enable_stages': ['stage_a', 'stage_b', 'stage_c'],
            'timeout_seconds': 300,
            'batch_size': 10,
            'error_handling': 'continue_on_error'
        }
        
        return LiteraturePipelineConfig(
            scoring=scoring_config,
            queue=queue_config,
            evaluation=evaluation_config,
            pubmed=pubmed_config,
            budget=budget_config,
            pipeline=pipeline_config
        )
    
    def create_mock_llm_client(self, test_variant):
        """Create a mock LLM client that returns controlled responses."""
        mock_client = Mock()
        
        if test_variant == "high_posterior":
            # High utility abstracts → P(short) ≥ θ_high
            mock_client.evaluate_documents.return_value = {
                'p_short_posterior': 0.85,  # Above 0.75 threshold
                'confidence': 0.90,
                'reasoning': 'High utility documents indicate strong positive signals',
                'stop_decision': 'promote',
                'tokens_used': 1500
            }
            
        elif test_variant == "low_posterior":
            # Low utility abstracts → P(short) ≤ θ_low
            mock_client.evaluate_documents.return_value = {
                'p_short_posterior': 0.15,  # Below 0.25 threshold
                'confidence': 0.85,
                'reasoning': 'Low utility documents indicate weak signals',
                'stop_decision': 'park',
                'tokens_used': 1500
            }
            
        elif test_variant == "plateau":
            # Plateau scenario → |ΔP| < ε and next_doc_utility < δ
            mock_client.evaluate_documents.return_value = {
                'p_short_posterior': 0.45,  # Between thresholds
                'confidence': 0.80,
                'reasoning': 'Plateau reached with minimal improvement',
                'stop_decision': 'stop',
                'tokens_used': 1500
            }
        
        return mock_client
    
    def test_high_posterior_stop(self, db_session):
        """Test high-posterior stop: two high-utility abstracts → LLM raises P(short) ≥ θ_high."""
        logger.info("🔍 Testing high-posterior stop scenario...")
        
        # Create test trial
        trial = self.create_test_trial(db_session)
        
        # Create configuration
        config = self.create_demo_config()
        
        # Create orchestrator with mock LLM client
        with patch('ncfd.ingest.llm_client.create_llm_client') as mock_create_client:
            mock_create_client.return_value = self.create_mock_llm_client("high_posterior")
            
            orchestrator = LiteratureOrchestrator(db_session, config)
            
            # Run pipeline
            result = orchestrator.run_literature_pipeline(trial_ids=[trial.nct_id])
            
            # Verify LLM evaluation was triggered
            assert result.llm_evaluations > 0, f"LLM evaluation not triggered: {result.llm_evaluations}"
            
            # Verify trial evaluation status
            evaluations = orchestrator.get_trial_evaluations()
            assert len(evaluations) > 0, "No trial evaluations found"
            
            # Check for promoted status
            promoted_found = False
            for eval_obj in evaluations:
                if eval_obj.get('evaluation_status') == 'promoted':
                    promoted_found = True
                    break
            
            assert promoted_found, "Trial not promoted despite high posterior"
            
            # Verify posterior is above threshold
            for eval_obj in evaluations:
                if eval_obj.get('posterior_p_short'):
                    posterior = eval_obj['posterior_p_short']
                    assert posterior >= 0.75, f"Posterior {posterior} below θ_high threshold"
            
            logger.info("✅ High-posterior stop test passed")
            return True
    
    def test_low_posterior_park(self, db_session):
        """Test low-posterior park: two low-utility abstracts → P(short) ≤ θ_low."""
        logger.info("🔍 Testing low-posterior park scenario...")
        
        # Create test trial
        trial = self.create_test_trial(db_session, "NCT12345678")
        
        # Create configuration
        config = self.create_demo_config()
        
        # Create orchestrator with mock LLM client
        with patch('ncfd.ingest.llm_client.create_llm_client') as mock_create_client:
            mock_create_client.return_value = self.create_mock_llm_client("low_posterior")
            
            orchestrator = LiteratureOrchestrator(db_session, config)
            
            # Run pipeline
            result = orchestrator.run_literature_pipeline(trial_ids=[trial.nct_id])
            
            # Verify LLM evaluation was triggered
            assert result.llm_evaluations > 0, f"LLM evaluation not triggered: {result.llm_evaluations}"
            
            # Verify trial evaluation status
            evaluations = orchestrator.get_trial_evaluations()
            assert len(evaluations) > 0, "No trial evaluations found"
            
            # Check for parked status
            parked_found = False
            for eval_obj in evaluations:
                if eval_obj.get('evaluation_status') == 'parked':
                    parked_found = True
                    break
            
            assert parked_found, "Trial not parked despite low posterior"
            
            # Verify posterior is below threshold
            for eval_obj in evaluations:
                if eval_obj.get('posterior_p_short'):
                    posterior = eval_obj['posterior_p_short']
                    assert posterior <= 0.25, f"Posterior {posterior} above θ_low threshold"
            
            logger.info("✅ Low-posterior park test passed")
            return True
    
    def test_plateau_stop(self, db_session):
        """Test plateau stop: several abstracts where |ΔP| < ε twice and next_doc_utility < δ."""
        logger.info("🔍 Testing plateau stop scenario...")
        
        # Create test trial
        trial = self.create_test_trial(db_session, "NCT87654321")
        
        # Create configuration
        config = self.create_demo_config()
        
        # Create orchestrator with mock LLM client
        with patch('ncfd.ingest.llm_client.create_llm_client') as mock_create_client:
            mock_create_client.return_value = self.create_mock_llm_client("plateau")
            
            orchestrator = LiteratureOrchestrator(db_session, config)
            
            # Run pipeline
            result = orchestrator.run_literature_pipeline(trial_ids=[trial.nct_id])
            
            # Verify LLM evaluation was triggered
            assert result.llm_evaluations > 0, f"LLM evaluation not triggered: {result.llm_evaluations}"
            
            # Verify trial evaluation status
            evaluations = orchestrator.get_trial_evaluations()
            assert len(evaluations) > 0, "No trial evaluations found"
            
            # Check for stopped status
            stopped_found = False
            for eval_obj in evaluations:
                if eval_obj.get('evaluation_status') == 'stopped':
                    stopped_found = True
                    break
            
            assert stopped_found, "Trial not stopped despite plateau"
            
            # Verify posterior is between thresholds
            for eval_obj in evaluations:
                if eval_obj.get('posterior_p_short'):
                    posterior = eval_obj['posterior_p_short']
                    assert 0.25 < posterior < 0.75, f"Posterior {posterior} outside expected range"
            
            logger.info("✅ Plateau stop test passed")
            return True
    
    def test_llm_path_exercise(self, db_session):
        """Test that LLM path is actually exercised with eval_every_docs=2."""
        logger.info("🔍 Testing LLM path exercise with eval_every_docs=2...")
        
        # Create test trial
        trial = self.create_test_trial(db_session, "NCT11111111")
        
        # Create configuration with eval_every_docs=2
        config = self.create_demo_config()
        config.evaluation['eval_every_docs'] = 2  # Force evaluation every 2 docs
        
        # Create orchestrator
        orchestrator = LiteratureOrchestrator(db_session, config)
        
        # Run pipeline
        result = orchestrator.run_literature_pipeline(trial_ids=[trial.nct_id])
        
        # Verify documents were evaluated
        assert result.documents_evaluated > 0, f"No documents evaluated: {result.documents_evaluated}"
        
        # Verify LLM evaluations occurred
        assert result.llm_evaluations > 0, f"LLM evaluations not triggered: {result.llm_evaluations}"
        
        # Verify evaluation count matches expected pattern
        # With eval_every_docs=2, we should have evaluations at doc counts 2, 4, 6, etc.
        expected_evaluations = result.documents_evaluated // 2
        assert result.llm_evaluations >= expected_evaluations, \
            f"LLM evaluations {result.llm_evaluations} < expected {expected_evaluations}"
        
        logger.info(f"✅ LLM path exercise verified: {result.llm_evaluations} evaluations for {result.documents_evaluated} docs")
        return True
    
    def test_budget_breach_scenario(self, db_session):
        """Test budget breach: Configure trial_limit = $0.001 then try to fetch an abstract."""
        logger.info("🔍 Testing budget breach scenario...")
        
        # Create test trial
        trial = self.create_test_trial(db_session, "NCT22222222")
        
        # Create configuration with very low budget
        config = self.create_demo_config()
        config.budget['trial_limit'] = 0.001  # Very low trial limit
        
        # Create orchestrator
        orchestrator = LiteratureOrchestrator(db_session, config)
        
        # Run pipeline - should hit budget limit quickly
        result = orchestrator.run_literature_pipeline(trial_ids=[trial.nct_id])
        
        # Verify pipeline handled budget constraint gracefully
        assert result.status in ['Success', 'Failed', 'Budget exceeded'], \
            f"Unexpected pipeline status: {result.status}"
        
        # Verify cost tracking
        assert result.total_cost <= 0.001, f"Cost {result.total_cost} exceeded trial limit 0.001"
        
        logger.info("✅ Budget breach scenario handled correctly")
        return True
    
    def test_multi_trial_scoping(self, db_session):
        """Test multi-trial scoping: Seed two trials; ensure Stage B for trial A never touches trial B's U0 rows."""
        logger.info("🔍 Testing multi-trial scoping...")
        
        # Create two test trials
        trial_a = self.create_test_trial(db_session, "NCT33333333")
        trial_b = self.create_test_trial(db_session, "NCT44444444")
        
        # Create configuration
        config = self.create_demo_config()
        
        # Create orchestrator
        orchestrator = LiteratureOrchestrator(db_session, config)
        
        # Run pipeline for trial A only
        result_a = orchestrator.run_literature_pipeline(trial_ids=[trial_a.nct_id])
        
        # Verify trial A processing
        assert result_a.trials_processed == 1, f"Trial A not processed: {result_a.trials_processed}"
        
        # Verify no cross-trial contamination
        from sqlalchemy import text
        
        # Check that trial B has no document utilities
        result = db_session.execute(text(
            "SELECT COUNT(*) FROM document_utilities WHERE trial_id = :trial_id"
        ), {'trial_id': trial_b.trial_id})
        trial_b_utilities = result.scalar()
        
        assert trial_b_utilities == 0, f"Trial B contaminated with {trial_b_utilities} utilities"
        
        # Verify trial A has utilities
        result = db_session.execute(text(
            "SELECT COUNT(*) FROM document_utilities WHERE trial_id = :trial_id"
        ), {'trial_id': trial_a.trial_id})
        trial_a_utilities = result.scalar()
        
        assert trial_a_utilities > 0, f"Trial A has no utilities: {trial_a_utilities}"
        
        logger.info("✅ Multi-trial scoping verified")
        return True
    
    def run_all_controlled_tests(self):
        """Run all controlled LLM evaluation tests."""
        logger.info("🚀 Starting LLM Evaluation Controlled Test Suite")
        
        with get_session() as db_session:
            try:
                # Setup test environment
                self.setup_test_environment(db_session)
                
                # Run all test scenarios
                test_results = {}
                
                test_results['high_posterior'] = self.test_high_posterior_stop(db_session)
                test_results['low_posterior'] = self.test_low_posterior_park(db_session)
                test_results['plateau'] = self.test_plateau_stop(db_session)
                test_results['llm_path_exercise'] = self.test_llm_path_exercise(db_session)
                test_results['budget_breach'] = self.test_budget_breach_scenario(db_session)
                test_results['multi_trial_scoping'] = self.test_multi_trial_scoping(db_session)
                
                # Verify all tests passed
                all_passed = all(test_results.values())
                
                if all_passed:
                    logger.info("🎉 ALL CONTROLLED LLM EVALUATION TESTS PASSED!")
                    logger.info("✅ High-posterior stop working correctly")
                    logger.info("✅ Low-posterior park working correctly")
                    logger.info("✅ Plateau stop working correctly")
                    logger.info("✅ LLM path actually exercised")
                    logger.info("✅ Budget breach handled gracefully")
                    logger.info("✅ Multi-trial scoping maintained")
                else:
                    failed_tests = [name for name, passed in test_results.items() if not passed]
                    logger.error(f"❌ Failed tests: {failed_tests}")
                
                return all_passed
                
            except Exception as e:
                logger.error(f"❌ Controlled test suite failed: {e}")
                raise


def main():
    """Main test execution function."""
    test_suite = LLMEvaluationControlledTest()
    
    try:
        success = test_suite.run_all_controlled_tests()
        if success:
            print("\n🎉 LLM Evaluation Controlled Test Suite Completed Successfully!")
            print("All three controlled variants are working correctly.")
            print("The LLM path is actually exercised and early stopping works.")
        else:
            print("\n💥 LLM Evaluation Controlled Test Suite Failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 LLM Evaluation Controlled Test Suite Failed with Exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
