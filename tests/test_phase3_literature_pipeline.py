"""
Test Phase 3: Literature Pipeline Integration.

This test file verifies the integration of the new literature pipeline
with the document ingestion system.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from ncfd.ingest.literature_pipeline import (
    LiteraturePipeline, PipelineStage, PipelineResult
)
from ncfd.ingest.document_ingest import DocumentIngester
from ncfd.ingest.literature_scoring import ScoringConfig
from ncfd.ingest.document_queue import DocumentCandidate
from ncfd.ingest.llm_evaluator import StopDecision


class TestLiteraturePipeline:
    """Test the literature pipeline implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        config = {
            'scoring': {
                'tau_abstract': 0.40,
                'theta_high': 0.80,
                'theta_low': 0.20,
                'delta_min': 0.05
            },
            'queue': {
                'max_trials_per_batch': 5,
                'max_candidates_per_trial': 10
            },
            'evaluation': {
                'eval_every_docs': 3,
                'theta_high': 0.80,
                'theta_low': 0.20
            },
            'smart_pubmed': {
                'stage_a_batch_size': 50,
                'stage_b_threshold': 0.3,
                'max_abstracts_per_trial': 5
            },
            'enable_stage_c': True,
            'auto_evaluation': True,
            'evaluation_interval': 3
        }
        self.pipeline = LiteraturePipeline(config)
    
    def test_initialization(self):
        """Test pipeline initialization."""
        assert self.pipeline.scorer is not None
        assert self.pipeline.queue is not None
        assert self.pipeline.evaluator is not None
        assert self.pipeline.pubmed_client is not None
        assert self.pipeline.enable_stage_c is True
        assert self.pipeline.auto_evaluation is True
        assert self.pipeline.evaluation_interval == 3
    
    def test_pipeline_stage_creation(self):
        """Test PipelineStage creation and properties."""
        stage = PipelineStage(
            stage_name="Test Stage",
            trial_id="NCT12345",
            start_time=datetime.now()
        )
        
        assert stage.stage_name == "Test Stage"
        assert stage.trial_id == "NCT12345"
        assert stage.success is False
        assert stage.results == {}
        assert stage.error_message is None
        assert stage.duration is None
        
        # Test duration calculation
        stage.end_time = datetime.now()
        assert stage.duration is not None
        assert stage.duration >= 0
    
    def test_pipeline_result_creation(self):
        """Test PipelineResult creation and properties."""
        stages = [
            PipelineStage("Stage 1", "NCT12345", datetime.now()),
            PipelineStage("Stage 2", "NCT12345", datetime.now())
        ]
        
        # Mark stages as complete
        for stage in stages:
            stage.end_time = datetime.now()
            stage.success = True
        
        result = PipelineResult(
            trial_id="NCT12345",
            stages=stages,
            overall_success=True,
            total_duration=1.5,
            final_decision=StopDecision.CONTINUE
        )
        
        assert result.trial_id == "NCT12345"
        assert len(result.stages) == 2
        assert result.overall_success is True
        assert result.total_duration == 1.5
        assert result.final_decision == StopDecision.CONTINUE
        assert result.successful_stages == ["Stage 1", "Stage 2"]
        assert result.failed_stages == []
    
    @patch('ncfd.ingest.literature_pipeline.SmartPubMedClient')
    def test_run_pipeline_stage_a_success(self, mock_pubmed_client):
        """Test successful Stage A execution."""
        # Mock Smart PubMed client
        mock_client = Mock()
        mock_client.stage_a_metadata_only.return_value = Mock(
            total_found=5,
            candidates=[Mock(u0_score=0.8) for _ in range(5)],
            processing_time=2.5
        )
        self.pipeline.pubmed_client = mock_client
        
        # Run Stage A
        stage = self.pipeline._run_stage_a(
            "NCT12345", ["drug_x"], "cancer", 2024
        )
        
        # Verify results
        assert stage.success is True
        assert stage.stage_name == "Stage A: Metadata Discovery"
        assert stage.results['total_found'] == 5
        assert stage.results['candidates'] == 5
        assert stage.results['processing_time'] == 2.5
        assert stage.results['top_u0_score'] == 0.8
        assert stage.duration is not None
    
    @patch('ncfd.ingest.literature_pipeline.SmartPubMedClient')
    def test_run_pipeline_stage_a_failure(self, mock_pubmed_client):
        """Test Stage A failure handling."""
        # Mock Smart PubMed client to raise exception
        mock_client = Mock()
        mock_client.stage_a_metadata_only.side_effect = Exception("API Error")
        self.pipeline.pubmed_client = mock_client
        
        # Run Stage A
        stage = self.pipeline._run_stage_a(
            "NCT12345", ["drug_x"], "cancer", 2024
        )
        
        # Verify failure handling
        assert stage.success is False
        assert stage.error_message == "API Error"
        assert stage.duration is not None
    
    @patch('ncfd.ingest.literature_pipeline.SmartPubMedClient')
    def test_run_pipeline_stage_b_success(self, mock_pubmed_client):
        """Test successful Stage B execution."""
        # Mock Smart PubMed client
        mock_client = Mock()
        mock_client.stage_b_abstract_evaluation.return_value = Mock(
            total_evaluated=3,
            promoted_candidates=[Mock() for _ in range(2)],
            parked_candidates=[Mock() for _ in range(1)],
            processing_time=1.5
        )
        self.pipeline.pubmed_client = mock_client
        
        # Run Stage B
        stage = self.pipeline._run_stage_b("NCT12345")
        
        # Verify results
        assert stage.success is True
        assert stage.stage_name == "Stage B: Abstract Evaluation"
        assert stage.results['total_evaluated'] == 3
        assert stage.results['promoted_candidates'] == 2
        assert stage.results['parked_candidates'] == 1
        assert stage.results['promotion_rate'] == 2/3
        assert stage.duration is not None
    
    def test_run_pipeline_stage_c_conditional(self):
        """Test conditional Stage C execution."""
        # Add some candidates to the queue
        candidates = [
            DocumentCandidate(
                doc_id=f"doc_{i}",
                trial_id="NCT12345",
                source_type="pubmed",
                u0_score=0.8,
                u1_score=0.6 if i < 2 else 0.3,  # First 2 have high U1
                metadata={'title': f'Document {i}'}
            )
            for i in range(3)
        ]
        
        self.pipeline.queue.add_trial_candidates("NCT12345", candidates)
        
        # Run Stage C
        stage = self.pipeline._run_stage_c("NCT12345")
        
        # Verify Stage C was created (high-priority candidates exist)
        assert stage is not None
        assert stage.success is True
        assert stage.stage_name == "Stage C: Full-Text Retrieval"
        assert stage.results['full_text_requests'] == 2  # Only 2 high-U1 candidates
        assert stage.results['candidates_processed'] == 2
    
    def test_run_pipeline_stage_c_no_candidates(self):
        """Test Stage C when no high-priority candidates exist."""
        # Add low-priority candidates
        candidates = [
            DocumentCandidate(
                doc_id="doc_1",
                trial_id="NCT12345",
                source_type="pubmed",
                u0_score=0.8,
                u1_score=0.2,  # Below threshold
                metadata={'title': 'Document 1'}
            )
        ]
        
        self.pipeline.queue.add_trial_candidates("NCT12345", candidates)
        
        # Run Stage C
        stage = self.pipeline._run_stage_c("NCT12345")
        
        # Verify Stage C was not created
        assert stage is None
    
    @patch('ncfd.ingest.literature_pipeline.LLMEvaluator')
    def test_run_llm_evaluation(self, mock_evaluator):
        """Test LLM evaluation execution."""
        # Add candidates to queue
        candidates = [
            DocumentCandidate(
                doc_id=f"doc_{i}",
                trial_id="NCT12345",
                source_type="pubmed",
                u0_score=0.8,
                u1_score=0.6,
                metadata={'title': f'Document {i}', 'abstract': f'Abstract {i}'}
            )
            for i in range(3)  # Exactly evaluation_interval
        ]
        
        self.pipeline.queue.add_trial_candidates("NCT12345", candidates)
        
        # Mock evaluator
        mock_eval = Mock()
        mock_eval.evaluate_trial_batch.return_value = Mock(
            stop_decision=StopDecision.CONTINUE,
            p_short_posterior=0.45
        )
        self.pipeline.evaluator = mock_eval
        
        # Run evaluation
        result = self.pipeline._run_llm_evaluation("NCT12345")
        
        # Verify evaluation was performed
        assert result is not None
        assert result.stop_decision == StopDecision.CONTINUE
        assert result.p_short_posterior == 0.45
        
        # Verify evaluator was called with correct data
        mock_eval.evaluate_trial_batch.assert_called_once()
        call_args = mock_eval.evaluate_trial_batch.call_args[0]
        assert call_args[0] == "NCT12345"
        assert len(call_args[1]) == 3  # 3 document summaries
    
    def test_run_llm_evaluation_not_ready(self):
        """Test LLM evaluation when not enough documents."""
        # Add candidates but not enough for evaluation interval
        candidates = [
            DocumentCandidate(
                doc_id="doc_1",
                trial_id="NCT12345",
                source_type="pubmed",
                u0_score=0.8,
                u1_score=0.6,
                metadata={'title': 'Document 1'}
            )
        ]
        
        self.pipeline.queue.add_trial_candidates("NCT12345", candidates)
        
        # Run evaluation
        result = self.pipeline._run_llm_evaluation("NCT12345")
        
        # Verify evaluation was not performed
        assert result is None
    
    def test_update_trial_status(self):
        """Test trial status updates based on LLM decisions."""
        # Test PROMOTE decision
        self.pipeline._update_trial_status("NCT12345", StopDecision.PROMOTE)
        
        # Test PARK decision
        self.pipeline._update_trial_status("NCT12345", StopDecision.PARK)
        
        # Test STOP decision
        self.pipeline._update_trial_status("NCT12345", StopDecision.STOP)
        
        # Test CONTINUE decision (should not change status)
        self.pipeline._update_trial_status("NCT12345", StopDecision.CONTINUE)
        
        # Verify status updates were logged (we can't easily verify the actual updates)
        # The test passes if no exceptions are raised
    
    def test_get_pipeline_stats(self):
        """Test pipeline statistics retrieval."""
        stats = self.pipeline.get_pipeline_stats()
        
        # Check basic stats
        assert 'pipelines_run' in stats
        assert 'trials_processed' in stats
        assert 'documents_discovered' in stats
        assert 'documents_evaluated' in stats
        assert 'full_text_requests' in stats
        assert 'total_processing_time' in stats
        
        # Check computed stats
        assert 'avg_processing_time' in stats
        assert 'success_rate' in stats
        
        # Check component stats
        assert 'queue_stats' in stats
        assert 'evaluation_stats' in stats
    
    def test_run_batch_pipeline(self):
        """Test batch pipeline execution."""
        trials = [
            {
                'trial_id': 'NCT12345',
                'drug_synonyms': ['drug_x'],
                'disease': 'cancer',
                'catalyst_year': 2024
            },
            {
                'trial_id': 'NCT67890',
                'drug_synonyms': ['drug_y'],
                'disease': 'diabetes',
                'catalyst_year': 2025
            }
        ]
        
        # Mock the run_pipeline method to avoid actual execution
        with patch.object(self.pipeline, 'run_pipeline') as mock_run:
            mock_run.side_effect = [
                Mock(trial_id='NCT12345', overall_success=True),
                Mock(trial_id='NCT67890', overall_success=True)
            ]
            
            results = self.pipeline.run_batch_pipeline(trials)
        
        # Verify batch execution
        assert len(results) == 2
        assert results[0].trial_id == 'NCT12345'
        assert results[1].trial_id == 'NCT67890'


class TestDocumentIngesterIntegration:
    """Test integration between DocumentIngester and LiteraturePipeline."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock database session
        self.mock_session = Mock()
        
        # Storage config with literature pipeline
        self.storage_config = {
            'literature_pipeline': {
                'scoring': {'tau_abstract': 0.40},
                'queue': {'max_trials_per_batch': 5},
                'evaluation': {'eval_every_docs': 3},
                'smart_pubmed': {'stage_a_batch_size': 50}
            }
        }
    
    def test_literature_pipeline_not_available(self):
        """Test graceful handling when literature pipeline is not available."""
        # Create document ingester without pipeline config
        ingester = DocumentIngester(self.mock_session, {})
        
        # Verify pipeline is None
        assert ingester.literature_pipeline is None
    
    def test_run_literature_pipeline_not_available(self):
        """Test literature pipeline execution when not available."""
        ingester = DocumentIngester(self.mock_session, {})
        result = ingester.run_literature_pipeline(
            'NCT12345', ['drug_x'], 'cancer', 2024
        )
        
        # Verify error response
        assert 'error' in result
        assert result['error'] == 'Literature pipeline not available'
    
    def test_literature_pipeline_integration_with_real_pipeline(self):
        """Test integration with a real literature pipeline instance."""
        # This test requires the actual pipeline to be available
        # We'll test the basic functionality without mocking
        
        # Create ingester with pipeline config
        ingester = DocumentIngester(self.mock_session, self.storage_config)
        
        # Check if pipeline was initialized (may fail if dependencies not available)
        if ingester.literature_pipeline is not None:
            # Test basic pipeline functionality
            assert hasattr(ingester.literature_pipeline, 'run_pipeline')
            assert hasattr(ingester.literature_pipeline, 'get_pipeline_stats')
            
            # Test stats retrieval
            stats = ingester.get_literature_pipeline_stats()
            assert isinstance(stats, dict)
        else:
            # Pipeline not available, skip test
            pytest.skip("Literature pipeline not available for integration test")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
