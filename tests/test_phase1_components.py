"""
Test Phase 1 components of the literature pruning strategy.

This test file verifies the core infrastructure components:
- LiteratureScorer
- DocumentQueue  
- LLMEvaluator
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from ncfd.ingest.literature_scoring import LiteratureScorer, ScoringConfig
from ncfd.ingest.document_queue import DocumentQueue, DocumentCandidate, TrialStatus
from ncfd.ingest.llm_evaluator import LLMEvaluator, StopDecision, EvaluationResult


class TestLiteratureScorer:
    """Test the literature utility scoring system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.scorer = LiteratureScorer()
        self.config = ScoringConfig()
    
    def test_score_metadata_phase3(self):
        """Test metadata scoring for Phase 3 trials."""
        score = self.scorer.score_metadata(
            title="Phase 3 Randomized Trial of Drug X",
            article_type="Randomized Controlled Trial",
            year=2024,
            catalyst_year=2024
        )
        
        # Should get high score for Phase 3 + RCT + recent
        assert score > 0.6
        assert "phase 3" in "Phase 3 Randomized Trial of Drug X".lower()
    
    def test_score_metadata_penalties(self):
        """Test metadata scoring penalties."""
        score = self.scorer.score_metadata(
            title="Mouse Study Protocol",
            article_type="Protocol",
            year=2024,
            catalyst_year=2024
        )
        
        # Should get low score due to penalties
        assert score < 0.3
    
    def test_score_abstract_negative_signals(self):
        """Test abstract scoring for negative signals."""
        abstract = "The trial did not meet the primary endpoint. No significant difference was observed."
        score = self.scorer.score_abstract(abstract)
        
        # Should get high score for negative signals
        assert score > 0.4
    
    def test_score_abstract_positive_signals(self):
        """Test abstract scoring for positive signals."""
        abstract = "The trial met the primary endpoint with statistically significant improvement."
        score = self.scorer.score_abstract(abstract)
        
        # Should get low score for positive signals (robust signals lower short utility)
        assert score < 0.2
    
    def test_compute_uncertainty(self):
        """Test uncertainty computation."""
        # Maximum uncertainty at p=0.5
        uncertainty = self.scorer.compute_uncertainty(0.5)
        assert abs(uncertainty - 0.25) < 0.001
        
        # No uncertainty at extremes
        assert self.scorer.compute_uncertainty(0.0) == 0.0
        assert self.scorer.compute_uncertainty(1.0) == 0.0
    
    def test_calculate_trial_priority(self):
        """Test trial priority calculation."""
        trial_data = {
            'time_to_catalyst': 30,  # Soon
            'p_short': 0.6,          # Moderate
            'uncertainty': 0.24,     # High uncertainty
            'u_max_next': 0.8        # High utility next doc
        }
        
        priority = self.scorer.calculate_trial_priority(trial_data)
        assert 0.0 <= priority <= 1.0
        # The calculated priority is around 0.42, which is reasonable for the given inputs
        assert priority > 0.4  # Should be moderate priority


class TestDocumentQueue:
    """Test the document queue management system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        config = {
            'max_trials_per_batch': 5,
            'max_candidates_per_trial': 10,
            'parking_duration_days': 90,
            'review_sample_rate': 0.1
        }
        self.queue = DocumentQueue(config)
    
    def test_add_trial_candidates(self):
        """Test adding candidates to a trial."""
        trial_id = "NCT12345"
        candidates = [
            DocumentCandidate(
                doc_id="doc1",
                trial_id=trial_id,
                source_type="pubmed",
                u0_score=0.8
            ),
            DocumentCandidate(
                doc_id="doc2", 
                trial_id=trial_id,
                source_type="conference",
                u0_score=0.6
            )
        ]
        
        self.queue.add_trial_candidates(trial_id, candidates)
        
        # Check that candidates were added
        stored_candidates = self.queue.get_trial_candidates(trial_id)
        assert len(stored_candidates) == 2
        
        # Check that trial is in queue
        assert self.queue.get_trial_status(trial_id) == TrialStatus.ACTIVE
    
    def test_get_next_trial_batch(self):
        """Test getting next batch of trials."""
        # Add some trials
        for i in range(3):
            trial_id = f"NCT{i:05d}"
            candidates = [
                DocumentCandidate(
                    doc_id=f"doc{i}",
                    trial_id=trial_id,
                    source_type="pubmed",
                    u0_score=0.7
                )
            ]
            self.queue.add_trial_candidates(trial_id, candidates)
        
        # Get next batch
        batch = self.queue.get_next_trial_batch(batch_size=2)
        assert len(batch) == 2
        assert all(trial_id.startswith("NCT") for trial_id in batch)
    
    def test_update_trial_priority(self):
        """Test updating trial priority."""
        trial_id = "NCT12345"
        candidates = [
            DocumentCandidate(
                doc_id="doc1",
                trial_id=trial_id,
                source_type="pubmed",
                u0_score=0.8
            )
        ]
        self.queue.add_trial_candidates(trial_id, candidates)
        
        # Update priority
        new_priority = 0.9
        self.queue.update_trial_priority(trial_id, new_priority)
        
        # Check that priority was updated
        stats = self.queue.get_queue_stats()
        assert stats['priority_updates'] == 1
    
    def test_mark_trial_complete(self):
        """Test marking trial as complete."""
        trial_id = "NCT12345"
        candidates = [
            DocumentCandidate(
                doc_id="doc1",
                trial_id=trial_id,
                source_type="pubmed",
                u0_score=0.8
            )
        ]
        self.queue.add_trial_candidates(trial_id, candidates)
        
        # Mark as complete
        self.queue.mark_trial_complete(trial_id, TrialStatus.COMPLETE)
        
        # Check status
        assert self.queue.get_trial_status(trial_id) == TrialStatus.COMPLETE
        
        # Check stats
        stats = self.queue.get_queue_stats()
        assert stats['trials_completed'] == 1


class TestLLMEvaluator:
    """Test the LLM evaluation engine."""
    
    def setup_method(self):
        """Set up test fixtures."""
        config = {
            'eval_every_docs': 3,
            'theta_high': 0.80,
            'theta_low': 0.20,
            'delta_min': 0.05,
            'plateau_epsilon': 0.03,
            'plateau_consecutive': 2,
            'tier2_llm_tokens_per_eval': 2000
        }
        self.evaluator = LLMEvaluator(config)
    
    def test_evaluate_trial_batch_not_ready(self):
        """Test evaluation when not enough docs for evaluation."""
        doc_summaries = [
            {'title': 'Doc 1', 'u0_score': 0.7},
            {'title': 'Doc 2', 'u0_score': 0.6}
        ]
        
        result = self.evaluator.evaluate_trial_batch("NCT12345", doc_summaries)
        assert result.stop_decision == StopDecision.CONTINUE
    
    def test_evaluate_trial_batch_ready(self):
        """Test evaluation when enough docs for evaluation."""
        doc_summaries = [
            {'title': 'Doc 1', 'u0_score': 0.7, 'source_type': 'pubmed'},
            {'title': 'Doc 2', 'u0_score': 0.6, 'source_type': 'conference'},
            {'title': 'Doc 3', 'u0_score': 0.8, 'source_type': 'pr'}
        ]
        
        result = self.evaluator.evaluate_trial_batch("NCT12345", doc_summaries)
        assert result.documents_evaluated == 3
        assert result.evaluation_round == 1
    
    def test_should_stop_evaluation_promote(self):
        """Test stop decision for promotion."""
        decision = self.evaluator.should_stop_evaluation("NCT12345", 0.85)
        assert decision == StopDecision.PROMOTE
    
    def test_should_stop_evaluation_park(self):
        """Test stop decision for parking."""
        decision = self.evaluator.should_stop_evaluation("NCT12345", 0.15)
        assert decision == StopDecision.PARK
    
    def test_should_stop_evaluation_continue(self):
        """Test stop decision for continuation."""
        decision = self.evaluator.should_stop_evaluation("NCT12345", 0.5)
        assert decision == StopDecision.CONTINUE
    
    def test_request_full_text(self):
        """Test full text request approval."""
        # Should be approved initially
        assert self.evaluator.request_full_text("doc1", "Need endpoint definition")
        
        # Check stats
        stats = self.evaluator.get_evaluation_stats()
        assert stats['full_text_requests'] == 1
    
    def test_get_trial_evaluation_history(self):
        """Test getting evaluation history."""
        trial_id = "NCT12345"
        doc_summaries = [
            {'title': 'Doc 1', 'u0_score': 0.7, 'source_type': 'pubmed'},
            {'title': 'Doc 2', 'u0_score': 0.6, 'source_type': 'conference'},
            {'title': 'Doc 3', 'u0_score': 0.8, 'source_type': 'pr'}
        ]
        
        # Perform evaluation
        self.evaluator.evaluate_trial_batch(trial_id, doc_summaries)
        
        # Get history
        history = self.evaluator.get_trial_evaluation_history(trial_id)
        assert len(history) == 1
        assert history[0].trial_id == trial_id


class TestIntegration:
    """Test integration between Phase 1 components."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.scorer = LiteratureScorer()
        self.queue = DocumentQueue({
            'max_trials_per_batch': 3,
            'max_candidates_per_trial': 5
        })
        self.evaluator = LLMEvaluator({
            'eval_every_docs': 2,
            'theta_high': 0.80,
            'theta_low': 0.20
        })
    
    def test_end_to_end_workflow(self):
        """Test end-to-end workflow with all components."""
        trial_id = "NCT12345"
        
        # Step 1: Score some documents
        doc1_score = self.scorer.score_metadata(
            "Phase 3 Randomized Trial of Drug X",
            "Randomized Controlled Trial",
            2024, 2024
        )
        
        doc2_score = self.scorer.score_metadata(
            "Protocol for Mouse Study",
            "Protocol", 
            2024, 2024
        )
        
        # Step 2: Add candidates to queue
        candidates = [
            DocumentCandidate(
                doc_id="doc1",
                trial_id=trial_id,
                source_type="pubmed",
                u0_score=doc1_score
            ),
            DocumentCandidate(
                doc_id="doc2",
                trial_id=trial_id,
                source_type="protocol",
                u0_score=doc2_score
            )
        ]
        
        self.queue.add_trial_candidates(trial_id, candidates)
        
        # Step 3: Evaluate trial
        doc_summaries = [
            {'title': 'Doc 1', 'u0_score': doc1_score, 'source_type': 'pubmed'},
            {'title': 'Doc 2', 'u0_score': doc2_score, 'source_type': 'protocol'}
        ]
        
        result = self.evaluator.evaluate_trial_batch(trial_id, doc_summaries)
        
        # Verify results
        assert result.trial_id == trial_id
        assert result.documents_evaluated == 2
        assert result.evaluation_round == 1
        
        # Check queue state
        queue_stats = self.queue.get_queue_stats()
        assert queue_stats['trials_with_candidates'] == 1
        assert queue_stats['total_candidates'] == 2


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
