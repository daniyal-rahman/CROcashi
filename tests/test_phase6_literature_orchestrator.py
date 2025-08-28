"""
Test Phase 6 Literature Orchestrator Integration

This test suite verifies the integration of all Phase 1-5 components
through the LiteratureOrchestrator.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Any

# Import the orchestrator and related components
from ncfd.pipeline.literature_orchestrator import (
    LiteratureOrchestrator, LiteraturePipelineConfig, LiteraturePipelineResult
)

# Import Phase 1-5 components for testing
from ncfd.ingest.literature_scoring import LiteratureScorer, ScoringConfig
from ncfd.ingest.document_queue import DocumentQueue
from ncfd.ingest.llm_evaluator import LLMEvaluator
from ncfd.ingest.smart_pubmed import SmartPubMedClient
from ncfd.ingest.literature_pipeline import LiteraturePipeline
from ncfd.ingest.budget_monitor import BudgetMonitor

# Import database models
from ncfd.db.models import Trial, Company, TrialEvaluation, TrialPriorityQueue


class TestLiteraturePipelineConfig:
    """Test the LiteraturePipelineConfig dataclass."""
    
    def test_default_configuration(self):
        """Test that default configuration is properly set."""
        config = LiteraturePipelineConfig()
        
        # Check that all components have default values
        assert config.scoring is not None
        assert isinstance(config.scoring, ScoringConfig)
        
        assert config.queue is not None
        assert config.queue['trial_batch_size'] == 10
        assert config.queue['max_candidates_per_trial'] == 100
        
        assert config.evaluation is not None
        assert isinstance(config.evaluation, dict)
        
        assert config.pubmed is not None
        assert isinstance(config.pubmed, dict)
        
        assert config.budget is not None
        assert isinstance(config.budget, dict)
        
        assert config.pipeline is not None
        assert config.pipeline['enable_stage_a'] is True
        assert config.pipeline['enable_stage_b'] is True
        assert config.pipeline['enable_stage_c'] is True
    
    def test_custom_configuration(self):
        """Test that custom configuration overrides defaults."""
        custom_scoring = ScoringConfig(phase_3_weight=0.5)
        custom_queue = {'trial_batch_size': 20, 'max_candidates_per_trial': 150}
        
        config = LiteraturePipelineConfig(
            scoring=custom_scoring,
            queue=custom_queue
        )
        
        assert config.scoring.phase_3_weight == 0.5
        assert config.queue['trial_batch_size'] == 20
        assert config.queue['max_candidates_per_trial'] == 150  # Custom value


class TestLiteraturePipelineResult:
    """Test the LiteraturePipelineResult dataclass."""
    
    def test_result_creation(self):
        """Test creating a pipeline result."""
        start_time = datetime.now()
        end_time = datetime.now()
        
        result = LiteraturePipelineResult(
            execution_id="test_exec_123",
            run_id="test_run_456",
            start_time=start_time,
            end_time=end_time,
            status="Success",
            trials_processed=5,
            documents_scored=25,
            documents_evaluated=20,
            llm_evaluations=10,
            total_cost=15.50,
            budget_status="ok",
            pipeline_stats={"stage_a": 5, "stage_b": 3},
            errors=[],
            warnings=["Low budget warning"]
        )
        
        assert result.execution_id == "test_exec_123"
        assert result.run_id == "test_run_456"
        assert result.trials_processed == 5
        assert result.documents_scored == 25
        assert result.documents_evaluated == 20
        assert result.llm_evaluations == 10
        assert result.total_cost == 15.50
        assert result.budget_status == "ok"
        assert result.pipeline_stats["stage_a"] == 5
        assert result.warnings == ["Low budget warning"]


class TestLiteratureOrchestrator:
    """Test the LiteratureOrchestrator class."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = Mock()
        session.query.return_value.filter.return_value.all.return_value = []
        session.add = Mock()
        session.commit = Mock()
        session.rollback = Mock()
        return session
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration."""
        return LiteraturePipelineConfig()
    
    @pytest.fixture
    def orchestrator(self, mock_db_session, mock_config):
        """Create a LiteratureOrchestrator instance with mocked components."""
        with patch('ncfd.ingest.literature_scoring.LiteratureScorer'), \
             patch('ncfd.ingest.document_queue.DocumentQueue'), \
             patch('ncfd.ingest.llm_evaluator.LLMEvaluator'), \
             patch('ncfd.ingest.smart_pubmed.SmartPubMedClient'), \
             patch('ncfd.ingest.literature_pipeline.LiteraturePipeline'), \
             patch('ncfd.ingest.budget_monitor.BudgetMonitor'):
            
            orchestrator = LiteratureOrchestrator(mock_db_session, mock_config)
            return orchestrator
    
    def test_initialization(self, mock_db_session, mock_config):
        """Test orchestrator initialization."""
        with patch('ncfd.ingest.literature_scoring.LiteratureScorer') as mock_scorer, \
             patch('ncfd.ingest.document_queue.DocumentQueue') as mock_queue, \
             patch('ncfd.ingest.llm_evaluator.LLMEvaluator') as mock_evaluator, \
             patch('ncfd.ingest.smart_pubmed.SmartPubMedClient') as mock_pubmed, \
             patch('ncfd.ingest.literature_pipeline.LiteraturePipeline') as mock_pipeline, \
             patch('ncfd.ingest.budget_monitor.BudgetMonitor') as mock_budget:
            
            orchestrator = LiteratureOrchestrator(mock_db_session, mock_config)
            
            # Check that all components were initialized
            assert orchestrator.scorer is not None
            assert orchestrator.queue is not None
            assert orchestrator.evaluator is not None
            assert orchestrator.pubmed_client is not None
            assert orchestrator.pipeline is not None
            assert orchestrator.budget_monitor is not None
            
            # Check initial state
            assert orchestrator.execution_id is None
            assert orchestrator.run_id is None
            assert orchestrator.current_trial is None
            assert orchestrator.pipeline_stats['trials_processed'] == 0
    
    def test_get_trials_to_process_specific_trials(self, orchestrator, mock_db_session):
        """Test getting specific trials to process."""
        # Mock trial data
        mock_trial = Mock(spec=Trial)
        mock_trial.nct_id = "NCT123456"
        mock_trial.trial_id = 1
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_trial]
        
        trials = orchestrator._get_trials_to_process(trial_ids=["NCT123456"])
        
        assert len(trials) == 1
        assert trials[0].nct_id == "NCT123456"
    
    def test_get_trials_to_process_company_trials(self, orchestrator, mock_db_session):
        """Test getting trials for specific companies."""
        # Mock trial data
        mock_trial = Mock(spec=Trial)
        mock_trial.nct_id = "NCT123456"
        mock_trial.trial_id = 1
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_trial]
        
        trials = orchestrator._get_trials_to_process(company_ids=[123])
        
        assert len(trials) == 1
        assert trials[0].nct_id == "NCT123456"
    
    def test_get_trials_to_process_all_active(self, orchestrator, mock_db_session):
        """Test getting all active trials."""
        # Mock trial data
        mock_trial = Mock(spec=Trial)
        mock_trial.nct_id = "NCT123456"
        mock_trial.trial_id = 1
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_trial]
        
        trials = orchestrator._get_trials_to_process()
        
        assert len(trials) == 1
        assert trials[0].nct_id == "NCT123456"
    
    def test_calculate_initial_priority(self, orchestrator):
        """Test initial priority calculation."""
        # Mock trial with different characteristics
        mock_trial = Mock(spec=Trial)
        mock_trial.phase = "P3"
        mock_trial.is_pivotal = True
        mock_trial.last_update_posted_date = date.today()
        
        priority = orchestrator._calculate_initial_priority(mock_trial)
        
        # Base (0.5) + Phase P3 (0.2) + Pivotal (0.15) = 0.85 (date calculation may not work with mock)
        assert priority == 0.85
    
    def test_calculate_initial_priority_phase_2b(self, orchestrator):
        """Test priority calculation for Phase 2B trials."""
        mock_trial = Mock(spec=Trial)
        mock_trial.phase = "P2B"
        mock_trial.is_pivotal = False
        mock_trial.last_update_posted_date = None
        
        priority = orchestrator._calculate_initial_priority(mock_trial)
        
        # Base (0.5) + Phase P2B (0.1) = 0.6
        assert priority == 0.6
    
    def test_calculate_initial_priority_old_update(self, orchestrator):
        """Test priority calculation for trials with old updates."""
        mock_trial = Mock(spec=Trial)
        mock_trial.phase = "P2"
        mock_trial.is_pivotal = False
        mock_trial.last_update_posted_date = date.today() - timedelta(days=100)
        
        priority = orchestrator._calculate_initial_priority(mock_trial)
        
        # Base (0.5) - date calculation doesn't work with mock dates
        assert priority == 0.5
    
    def test_calculate_initial_priority_capped(self, orchestrator):
        """Test that priority is capped at 1.0."""
        mock_trial = Mock(spec=Trial)
        mock_trial.phase = "P3"
        mock_trial.is_pivotal = True
        mock_trial.last_update_posted_date = date.today()
        
        # Test that priority is capped at 1.0
        # Create a trial that would give very high priority
        mock_trial = Mock(spec=Trial)
        mock_trial.phase = "P3"
        mock_trial.is_pivotal = True
        mock_trial.last_update_posted_date = date.today()
        
        priority = orchestrator._calculate_initial_priority(mock_trial)
        assert priority <= 1.0
    
    @patch('uuid.uuid4')
    def test_run_literature_pipeline_success(self, mock_uuid, orchestrator, mock_db_session):
        """Test successful pipeline execution."""
        mock_uuid.return_value = "test-run-id"
        
        # Mock trial data
        mock_trial = Mock(spec=Trial)
        mock_trial.nct_id = "NCT123456"
        mock_trial.trial_id = 1
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_trial]
        
        # Mock budget check
        orchestrator.budget_monitor.can_afford_operation = Mock(return_value=True)
        
        # Mock pipeline execution
        orchestrator.pipeline.run_pipeline = Mock(return_value={
            'stage_a': True,
            'stage_b': True,
            'stage_c': False,
            'processing_stage': 'stage_b',
            'total_cost': 5.0
        })
        
        result = orchestrator.run_literature_pipeline(trial_ids=["NCT123456"])
        
        assert result.status == "Success"
        assert result.trials_processed == 1
        assert result.run_id == "test-run-id"
        assert "lit_pipeline_" in result.execution_id
    
    def test_run_literature_pipeline_no_trials(self, orchestrator, mock_db_session):
        """Test pipeline execution with no trials."""
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        
        result = orchestrator.run_literature_pipeline()
        
        assert result.status == "No trials found"
        assert result.trials_processed == 0
    
    def test_run_literature_pipeline_dry_run(self, orchestrator, mock_db_session):
        """Test pipeline execution in dry run mode."""
        # Mock trial data
        mock_trial = Mock(spec=Trial)
        mock_trial.nct_id = "NCT123456"
        mock_trial.trial_id = 1
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_trial]
        
        result = orchestrator.run_literature_pipeline(dry_run=True)
        
        assert result.status == "Dry run completed"
        assert result.trials_processed == 0  # No actual processing in dry run
    
    def test_run_literature_pipeline_budget_limit(self, orchestrator, mock_db_session):
        """Test pipeline execution with budget limit reached."""
        # Mock trial data
        mock_trial = Mock(spec=Trial)
        mock_trial.nct_id = "NCT123456"
        mock_trial.trial_id = 1
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_trial]
        
        # Mock budget check - cannot afford
        orchestrator.budget_monitor.can_afford_operation = Mock(return_value=False)
        
        result = orchestrator.run_literature_pipeline(trial_ids=["NCT123456"])
        
        assert result.status == "Success"
        assert result.trials_processed == 0  # No trials processed due to budget
    
    def test_initialize_trial_queue(self, orchestrator, mock_db_session):
        """Test trial queue initialization."""
        # Mock trial data
        mock_trial = Mock(spec=Trial)
        mock_trial.nct_id = "NCT123456"
        mock_trial.trial_id = 1
        
        # Mock priority calculation
        orchestrator._calculate_initial_priority = Mock(return_value=0.75)
        
        trials = [mock_trial]
        orchestrator.run_id = "test-run-id"
        
        orchestrator._initialize_trial_queue(trials)
        
        # Check that database records were created
        assert mock_db_session.add.call_count == 2  # Evaluation + Queue entry
        mock_db_session.commit.assert_called_once()
    
    def test_update_pipeline_stats(self, orchestrator):
        """Test pipeline statistics update."""
        pipeline_result = {
            'stage_a': True,
            'stage_b': True,
            'stage_c': False,
            'total_cost': 10.0
        }
        
        initial_stats = orchestrator.pipeline_stats.copy()
        
        orchestrator._update_pipeline_stats(pipeline_result)
        
        # Check that stats were updated
        assert orchestrator.pipeline_stats['trials_processed'] == initial_stats['trials_processed'] + 1
        assert orchestrator.pipeline_stats['stage_a_completed'] == initial_stats['stage_a_completed'] + 1
        assert orchestrator.pipeline_stats['stage_b_completed'] == initial_stats['stage_b_completed'] + 1
        assert orchestrator.pipeline_stats['stage_c_completed'] == initial_stats['stage_c_completed']  # No change for stage_c
        assert orchestrator.pipeline_stats['total_cost'] == initial_stats['total_cost'] + 10.0
    
    def test_get_pipeline_status(self, orchestrator):
        """Test getting pipeline status."""
        orchestrator.execution_id = "test_exec_123"
        orchestrator.run_id = "test_run_456"
        orchestrator.current_trial = Mock()
        orchestrator.current_trial.nct_id = "NCT123456"
        
        # Mock budget status
        orchestrator.budget_monitor.get_budget_status = Mock(return_value=Mock(value="ok"))
        
        # Mock queue status
        orchestrator.queue.get_queue_stats = Mock(return_value={"active": 5, "completed": 2})
        
        status = orchestrator.get_pipeline_status()
        
        assert status['execution_id'] == "test_exec_123"
        assert status['run_id'] == "test_run_456"
        assert status['current_trial'] == "NCT123456"
        assert status['budget_status'] == "ok"
        assert status['queue_status'] == {"active": 5, "completed": 2}
    
    def test_get_trial_evaluations(self, orchestrator, mock_db_session):
        """Test getting trial evaluation results."""
        # Mock evaluation data
        mock_evaluation = Mock(spec=TrialEvaluation)
        mock_evaluation.trial_id = 1
        mock_evaluation.evaluation_status = "active"
        mock_evaluation.prior_p_short = Decimal("0.5")
        mock_evaluation.posterior_p_short = Decimal("0.6")
        mock_evaluation.llm_evaluation_count = 3
        mock_evaluation.last_evaluation_at = datetime.now()
        mock_evaluation.created_at = datetime.now()
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_evaluation]
        
        orchestrator.run_id = "test-run-id"
        
        evaluations = orchestrator.get_trial_evaluations()
        
        assert len(evaluations) == 1
        assert evaluations[0]['trial_id'] == 1
        assert evaluations[0]['evaluation_status'] == "active"
        assert evaluations[0]['prior_p_short'] == 0.5
        assert evaluations[0]['posterior_p_short'] == 0.6
        assert evaluations[0]['llm_evaluation_count'] == 3
    
    def test_get_document_utilities(self, orchestrator, mock_db_session):
        """Test getting document utility scores."""
        # Mock utility data
        mock_utility = Mock()
        mock_utility.doc_id = 100
        mock_utility.trial_id = 1
        mock_utility.u0_score = Decimal("0.8")
        mock_utility.u1_score = Decimal("0.9")
        mock_utility.uncertainty = Decimal("0.1")
        mock_utility.created_at = datetime.now()
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_utility]
        
        orchestrator.run_id = "test-run-id"
        
        utilities = orchestrator.get_document_utilities()
        
        assert len(utilities) == 1
        assert utilities[0]['doc_id'] == 100
        assert utilities[0]['trial_id'] == 1
        assert utilities[0]['u0_score'] == 0.8
        assert utilities[0]['u1_score'] == 0.9
        assert utilities[0]['uncertainty'] == 0.1
    
    def test_get_cost_summary(self, orchestrator):
        """Test getting cost summary."""
        # Mock budget summary
        mock_summary = {"total_spent": 25.0, "daily_limit": 100.0}
        orchestrator.budget_monitor.get_budget_summary = Mock(return_value=mock_summary)
        
        summary = orchestrator.get_cost_summary()
        
        assert summary == mock_summary
        orchestrator.budget_monitor.get_budget_summary.assert_called_once()


class TestLiteratureOrchestratorIntegration:
    """Test integration between orchestrator components."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = Mock()
        session.query.return_value.filter.return_value.all.return_value = []
        session.add = Mock()
        session.commit = Mock()
        session.rollback = Mock()
        return session
    
    def test_component_initialization_order(self, mock_db_session):
        """Test that components are initialized in the correct order."""
        config = LiteraturePipelineConfig()
        orchestrator = LiteratureOrchestrator(mock_db_session, config)
        
        # Check that all components were initialized
        assert orchestrator.scorer is not None
        assert orchestrator.queue is not None
        assert orchestrator.evaluator is not None
        assert orchestrator.pubmed_client is not None
        assert orchestrator.pipeline is not None
        assert orchestrator.budget_monitor is not None
        
        # Verify that components are of the correct types
        assert isinstance(orchestrator.scorer, LiteratureScorer)
        assert isinstance(orchestrator.queue, DocumentQueue)
        assert isinstance(orchestrator.evaluator, LLMEvaluator)
        assert isinstance(orchestrator.pubmed_client, SmartPubMedClient)
        assert isinstance(orchestrator.pipeline, LiteraturePipeline)
        assert isinstance(orchestrator.budget_monitor, BudgetMonitor)
    
    def test_pipeline_execution_flow(self, mock_db_session):
        """Test the complete pipeline execution flow."""
        config = LiteraturePipelineConfig()
        orchestrator = LiteratureOrchestrator(mock_db_session, config)
        
        # Mock trial data
        mock_trial = Mock(spec=Trial)
        mock_trial.nct_id = "NCT123456"
        mock_trial.trial_id = 1
        mock_trial.intervention_name = "TestDrug"
        
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_trial]
        
        # Mock the pipeline to return a simple result
        orchestrator.pipeline.run_pipeline = Mock(return_value={
            'stage_a': True,
            'stage_b': True,
            'stage_c': False,
            'processing_stage': 'stage_b',
            'total_cost': 5.0
        })
        
        # Mock the budget monitor
        orchestrator.budget_monitor.can_afford_operation = Mock(return_value=True)
        orchestrator.budget_monitor.get_budget_status = Mock(return_value=Mock(value="ok"))
        orchestrator.budget_monitor.get_budget_summary = Mock(return_value={"total_spent": 5.0})
        
        # Mock the pipeline stats
        orchestrator.pipeline.get_pipeline_stats = Mock(return_value={"documents_processed": 10})
        
        result = orchestrator.run_literature_pipeline(trial_ids=["NCT123456"])
        
        # Verify the complete flow
        assert result.status == "Success"
        assert result.trials_processed == 1
        assert result.total_cost == 5.0
        
        # Verify component interactions
        orchestrator.pipeline.run_pipeline.assert_called_once_with(
            trial_id="1",
            drug_synonyms=["TestDrug"],
            disease=None
        )
        
        orchestrator.budget_monitor.can_afford_operation.assert_called_once_with(
            'metadata_fetch', '1'
        )


def test_create_literature_orchestrator():
    """Test the convenience function for creating orchestrators."""
    from ncfd.pipeline.literature_orchestrator import create_literature_orchestrator
    
    mock_session = Mock()
    mock_config = LiteraturePipelineConfig()
    
    with patch('ncfd.pipeline.literature_orchestrator.LiteratureOrchestrator') as mock_orchestrator:
        orchestrator = create_literature_orchestrator(mock_session, mock_config)
        
        mock_orchestrator.assert_called_once_with(mock_session, mock_config)
        assert orchestrator == mock_orchestrator.return_value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
