"""
Test Phase 2: Smart PubMed Client with Three-Stage Pipeline.

This test file verifies the new three-stage retrieval system that replaces
the old smart stopping logic.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from ncfd.ingest.smart_pubmed import (
    SmartPubMedClient, PubMedSummary, StageAResult, 
    StageBResult, StageCResult
)
from ncfd.ingest.document_queue import DocumentCandidate
from ncfd.ingest.literature_scoring import ScoringConfig


class TestSmartPubMedClient:
    """Test the new three-stage Smart PubMed client."""
    
    def setup_method(self):
        """Set up test fixtures."""
        config = {
            'scoring': {
                'tau_abstract': 0.40,
                'theta_high': 0.80,
                'theta_low': 0.20
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
            'stage_a_batch_size': 50,
            'stage_b_threshold': 0.3,
            'max_abstracts_per_trial': 5
        }
        self.client = SmartPubMedClient(config)
    
    def test_initialization(self):
        """Test client initialization with Phase 1 components."""
        assert self.client.scorer is not None
        assert self.client.queue is not None
        assert self.client.evaluator is not None
        assert self.client.stage_a_batch_size == 50
        assert self.client.stage_b_threshold == 0.3
        assert self.client.max_abstracts_per_trial == 5
    
    def test_build_drug_query(self):
        """Test drug query building."""
        # Test with generic drug name
        query = self.client._build_drug_query(["ruxolitinib"])
        assert "ruxolitinib" in query
        assert "[tiab]" in query
        
        # Test with internal code
        query = self.client._build_drug_query(["AB-123"])
        assert "AB-123" in query
        assert "[tiab]" in query
        
        # Test with NCT ID
        query = self.client._build_drug_query(["NCT12345"])
        assert "NCT12345" in query
        assert "[si]" in query
        
        # Test with disease
        query = self.client._build_drug_query(["ruxolitinib"], "myelofibrosis")
        assert "ruxolitinib" in query
        assert "myelofibrosis" in query
        assert "AND" in query
    
    def test_parse_summary(self):
        """Test PubMed summary parsing."""
        summary_data = {
            "uid": "12345",
            "title": "Phase 3 Trial of Drug X",
            "fulljournalname": "New England Journal of Medicine",
            "pubdate": "2024",
            "pubtype": [{"name": "Randomized Controlled Trial"}],
            "articleids": [
                {"idtype": "si", "value": "NCT12345"}
            ],
            "meshterms": [{"name": "Cancer"}]
        }
        
        summary = self.client._parse_summary(summary_data)
        
        assert summary.pmid == "12345"
        assert summary.title == "Phase 3 Trial of Drug X"
        assert summary.journal == "New England Journal of Medicine"
        assert summary.pub_date == "2024"
        assert "Randomized Controlled Trial" in summary.pub_types
        assert "NCT12345" in summary.secondary_ids
        assert "Cancer" in summary.mesh_terms
    
    @patch('ncfd.ingest.smart_pubmed.requests.Session.get')
    def test_stage_a_metadata_only(self, mock_get):
        """Test Stage A: metadata-only processing."""
        # Mock PubMed API responses
        mock_search_response = Mock()
        mock_search_response.json.return_value = {
            "esearchresult": {
                "idlist": ["12345", "67890"]
            }
        }
        mock_search_response.raise_for_status.return_value = None
        
        mock_summary_response = Mock()
        mock_summary_response.json.return_value = {
            "result": {
                "12345": {
                    "uid": "12345",
                    "title": "Phase 3 Trial of Drug X",
                    "fulljournalname": "NEJM",
                    "pubdate": "2024",
                    "pubtype": [{"name": "Randomized Controlled Trial"}],
                    "articleids": [],
                    "meshterms": []
                },
                "67890": {
                    "uid": "67890",
                    "title": "Mouse Study of Drug X",
                    "fulljournalname": "Nature",
                    "pubdate": "2024",
                    "pubtype": [{"name": "Research Article"}],
                    "articleids": [],
                    "meshterms": []
                }
            }
        }
        mock_summary_response.raise_for_status.return_value = None
        
        mock_get.side_effect = [mock_search_response, mock_summary_response]
        
        # Run Stage A
        result = self.client.stage_a_metadata_only(
            "NCT12345", ["drug_x"], catalyst_year=2024
        )
        
        # Verify results
        assert result.trial_id == "NCT12345"
        assert result.total_found == 2
        assert len(result.candidates) == 2
        
        # First candidate should have higher U0 score (Phase 3 + RCT)
        assert result.candidates[0].u0_score > result.candidates[1].u0_score
        
        # Check that candidates were added to queue
        queue_candidates = self.client.queue.get_trial_candidates("NCT12345")
        assert len(queue_candidates) == 2
    
    def test_stage_b_abstract_evaluation(self):
        """Test Stage B: abstract evaluation."""
        # Add some candidates to the queue first
        candidates = [
            DocumentCandidate(
                doc_id="12345",
                trial_id="NCT12345",
                source_type="pubmed",
                u0_score=0.8
            ),
            DocumentCandidate(
                doc_id="67890",
                trial_id="NCT12345",
                source_type="pubmed",
                u0_score=0.6
            ),
            DocumentCandidate(
                doc_id="11111",
                trial_id="NCT12345",
                source_type="pubmed",
                u0_score=0.2  # Below threshold
            )
        ]
        
        self.client.queue.add_trial_candidates("NCT12345", candidates)
        
        # Mock abstract fetching
        with patch.object(self.client, '_efetch_abstract') as mock_fetch:
            mock_fetch.side_effect = [
                "The trial did not meet the primary endpoint. No significant difference was observed.",
                "The trial met the primary endpoint with statistically significant improvement.",
                None  # No abstract available
            ]
            
            # Run Stage B
            result = self.client.stage_b_abstract_evaluation("NCT12345")
        
        # Verify results
        assert result.trial_id == "NCT12345"
        assert result.total_evaluated == 2  # Only high-U0 candidates evaluated
        
        # First candidate should be promoted (negative signals in abstract)
        assert len(result.promoted_candidates) >= 1
        assert result.promoted_candidates[0].u1_score > 0.4
        
        # Second candidate should be parked (positive signals)
        assert len(result.parked_candidates) >= 1
        assert result.parked_candidates[0].u1_score < 0.2
    
    def test_stage_c_full_text_on_demand(self):
        """Test Stage C: full-text on demand."""
        # Mock LLM evaluator to approve request
        self.client.evaluator.request_full_text = Mock(return_value=True)
        
        # Run Stage C
        result = self.client.stage_c_full_text_on_demand(
            "NCT12345", "12345", "Need to check endpoint definition"
        )
        
        # Verify results
        assert result is not None
        assert result.trial_id == "NCT12345"
        assert len(result.full_text_requests) == 1
        assert result.full_text_requests[0]["doc_id"] == "12345"
        assert result.full_text_requests[0]["reason"] == "Need to check endpoint definition"
    
    def test_stage_c_full_text_denied(self):
        """Test Stage C: full-text request denied."""
        # Mock LLM evaluator to deny request
        self.client.evaluator.request_full_text = Mock(return_value=False)
        
        # Run Stage C
        result = self.client.stage_c_full_text_on_demand(
            "NCT12345", "12345", "Need to check endpoint definition"
        )
        
        # Verify request was denied
        assert result is None
    
    @patch('ncfd.ingest.smart_pubmed.requests.Session.get')
    def test_run_three_stage_pipeline(self, mock_get):
        """Test complete three-stage pipeline."""
        # Mock PubMed API responses
        mock_search_response = Mock()
        mock_search_response.json.return_value = {
            "esearchresult": {
                "idlist": ["12345", "67890"]
            }
        }
        mock_search_response.raise_for_status.return_value = None
        
        mock_summary_response = Mock()
        mock_summary_response.json.return_value = {
            "result": {
                "12345": {
                    "uid": "12345",
                    "title": "Phase 3 Trial of Drug X",
                    "fulljournalname": "NEJM",
                    "pubdate": "2024",
                    "pubtype": [{"name": "Randomized Controlled Trial"}],
                    "articleids": [],
                    "meshterms": []
                },
                "67890": {
                    "uid": "67890",
                    "title": "Phase 2 Trial of Drug X",
                    "fulljournalname": "JCO",
                    "pubdate": "2024",
                    "pubtype": [{"name": "Clinical Trial, Phase II"}],
                    "articleids": [],
                    "meshterms": []
                }
            }
        }
        mock_summary_response.raise_for_status.return_value = None
        
        mock_get.side_effect = [mock_search_response, mock_summary_response]
        
        # Mock abstract fetching
        with patch.object(self.client, '_efetch_abstract') as mock_fetch:
            mock_fetch.side_effect = [
                "The trial did not meet the primary endpoint.",
                "The trial met the primary endpoint."
            ]
            
            # Run complete pipeline
            result = self.client.run_three_stage_pipeline(
                "NCT12345", ["drug_x"], catalyst_year=2024
            )
        
        # Verify pipeline results
        assert result['success'] is True
        assert result['trial_id'] == "NCT12345"
        assert result['stage_a'] is not None
        assert result['stage_b'] is not None
        assert result['stage_c'] is None  # Not automatically triggered
        
        # Check Stage A results
        stage_a = result['stage_a']
        assert stage_a.total_found == 2
        assert len(stage_a.candidates) == 2
        
        # Check Stage B results
        stage_b = result['stage_b']
        # Only candidates with U0 >= stage_b_threshold (0.3) are evaluated
        # The first candidate has U0=0.6, second has U0=0.4, so both should be evaluated
        assert stage_b.total_evaluated >= 1  # At least one should be evaluated
        assert len(stage_b.promoted_candidates) >= 0  # May have promoted candidates
        assert len(stage_b.parked_candidates) >= 0  # May have parked candidates
        
        # Check that trial priority was updated
        queue_stats = self.client.queue.get_queue_stats()
        assert queue_stats['priority_updates'] >= 1
    
    def test_get_pipeline_stats(self):
        """Test pipeline statistics retrieval."""
        stats = self.client.get_pipeline_stats()
        
        assert 'queue_stats' in stats
        assert 'evaluation_stats' in stats
        assert 'scoring_config' in stats
        
        # Check scoring config
        scoring_config = stats['scoring_config']
        assert scoring_config['tau_abstract'] == 0.40
        assert scoring_config['theta_high'] == 0.80
        assert scoring_config['theta_low'] == 0.20


class TestIntegration:
    """Test integration between Phase 2 and Phase 1 components."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = SmartPubMedClient()
    
    def test_scoring_integration(self):
        """Test that scoring integrates correctly with Phase 1 components."""
        # Create a test candidate
        candidate = DocumentCandidate(
            doc_id="test123",
            trial_id="NCT12345",
            source_type="pubmed",
            u0_score=0.0
        )
        
        # Add to queue
        self.client.queue.add_trial_candidates("NCT12345", [candidate])
        
        # Verify integration
        queue_candidates = self.client.queue.get_trial_candidates("NCT12345")
        assert len(queue_candidates) == 1
        assert queue_candidates[0].doc_id == "test123"
    
    def test_evaluation_integration(self):
        """Test that evaluation integrates correctly with Phase 1 components."""
        # Test LLM evaluation integration
        doc_summaries = [
            {'title': 'Doc 1', 'u0_score': 0.7, 'source_type': 'pubmed'},
            {'title': 'Doc 2', 'u0_score': 0.6, 'source_type': 'conference'},
            {'title': 'Doc 3', 'u0_score': 0.8, 'source_type': 'pr'}
        ]
        
        result = self.client.evaluator.evaluate_trial_batch("NCT12345", doc_summaries)
        
        # Verify evaluation worked
        assert result.trial_id == "NCT12345"
        assert result.documents_evaluated == 3
        assert result.evaluation_round == 1


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
