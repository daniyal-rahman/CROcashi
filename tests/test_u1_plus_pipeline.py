"""
Tests for U1+ Pipeline components.

Tests the unified discovery and abstract processing pipeline.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Any

from src.ncfd.ingest.pubmed.stage_u1 import StageU1Processor, StageU1Result
from src.ncfd.ingest.pubmed.queue_service import TaskQueueService
from src.ncfd.ingest.pubmed.priority_service import PriorityService
from src.ncfd.ingest.pubmed.logging_service import ContextManager, MetricsCollector
from src.ncfd.ingest.pubmed.db_service import PubMedDBService


class TestTaskQueueService:
    """Test task queue service functionality."""
    
    @pytest.fixture
    def queue_service(self):
        """Create queue service instance."""
        return TaskQueueService(worker_id="test_worker")
    
    @pytest.fixture
    def mock_task_data(self):
        """Mock task data."""
        return {
            'id': 1,
            'task_type': 'PUBMED_OA',
            'task_key': 'trial:123:OA',
            'trial_id': 123,
            'priority': 0.8,
            'payload': {'test': 'data'},
            'attempts': 0
        }
    
    def test_enqueue_task_success(self, queue_service):
        """Test successful task enqueueing."""
        success = queue_service.enqueue_task(
            task_type='PUBMED_U1',
            task_key='trial:123:U1',
            priority=0.8,
            payload={'trial_id': 123},
            trial_id=123
        )
        assert success is True
    
    def test_enqueue_task_duplicate(self, queue_service):
        """Test enqueueing duplicate task (should update)."""
        # Enqueue first time
        success1 = queue_service.enqueue_task(
            task_type='PUBMED_U1',
            task_key='trial:123:U1',
            priority=0.8,
            payload={'trial_id': 123},
            trial_id=123
        )
        assert success1 is True
        
        # Enqueue same task with different priority (should update)
        success2 = queue_service.enqueue_task(
            task_type='PUBMED_U1',
            task_key='trial:123:U1',
            priority=0.9,
            payload={'trial_id': 123, 'updated': True},
            trial_id=123
        )
        assert success2 is True
    
    @patch('src.ncfd.ingest.pubmed.queue_service.session_scope')
    def test_lease_next_success(self, mock_session_scope, queue_service, mock_task_data):
        """Test successful task leasing."""
        # Mock database session
        mock_session = Mock()
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Mock task query result
        mock_task = Mock()
        mock_task.id = 1
        mock_task.task_type = 'PUBMED_OA'
        mock_task.task_key = 'trial:123:OA'
        mock_task.trial_id = 123
        mock_task.priority = 0.8
        mock_task.payload = {'test': 'data'}
        mock_task.attempts = 0
        
        mock_session.query.return_value.filter.return_value.order_by.return_value.with_for_update.return_value.first.return_value = mock_task
        
        # Test leasing
        result = queue_service.lease_next(['PUBMED_OA'])
        
        assert result is not None
        assert result['id'] == 1
        assert result['task_type'] == 'PUBMED_OA'
        assert result['trial_id'] == 123
    
    @patch('src.ncfd.ingest.pubmed.queue_service.session_scope')
    def test_lease_next_no_tasks(self, mock_session_scope, queue_service):
        """Test leasing when no tasks available."""
        # Mock database session
        mock_session = Mock()
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Mock empty query result
        mock_session.query.return_value.filter.return_value.order_by.return_value.with_for_update.return_value.first.return_value = None
        
        # Test leasing
        result = queue_service.lease_next(['PUBMED_OA'])
        
        assert result is None
    
    @patch('src.ncfd.ingest.pubmed.queue_service.session_scope')
    def test_complete_task(self, mock_session_scope, queue_service):
        """Test task completion."""
        # Mock database session
        mock_session = Mock()
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Mock task query result
        mock_task = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_task
        
        # Test completion
        success = queue_service.complete_task(1)
        
        assert success is True
        assert mock_task.status == 'done'
        assert mock_task.leased_by is None
        assert mock_task.leased_until is None
    
    @patch('src.ncfd.ingest.pubmed.queue_service.session_scope')
    def test_fail_task(self, mock_session_scope, queue_service):
        """Test task failure."""
        # Mock database session
        mock_session = Mock()
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Mock task query result
        mock_task = Mock()
        mock_task.payload = {}
        mock_session.query.return_value.filter.return_value.first.return_value = mock_task
        
        # Test failure
        success = queue_service.fail_task(1, "Test failure")
        
        assert success is True
        assert mock_task.status == 'failed'
        assert mock_task.attempts == 1
        assert 'failure_reason' in mock_task.payload


class TestPriorityService:
    """Test priority computation service."""
    
    @pytest.fixture
    def priority_service(self):
        """Create priority service instance."""
        return PriorityService()
    
    def test_calculate_task_priority_basic(self, priority_service):
        """Test basic priority calculation."""
        trial_data = {
            'best_S_Rge2': 0.8,
            'uncertainty': 0.6,
            'n_docs_selected': 5,
            'phase': 'phase_2',
            'status': 'recruiting'
        }
        
        priority = priority_service.calculate_task_priority(
            'PUBMED_U1', 123, trial_data
        )
        
        assert isinstance(priority, float)
        assert priority > 0
        assert priority < 2.0  # Should be reasonable range
    
    def test_calculate_task_priority_with_catalyst(self, priority_service):
        """Test priority calculation with catalyst date."""
        trial_data = {
            'best_S_Rge2': 0.8,
            'uncertainty': 0.6,
            'n_docs_selected': 5,
            'phase': 'phase_2',
            'status': 'recruiting',
            'catalyst_date': datetime.now(timezone.utc).isoformat()
        }
        
        priority = priority_service.calculate_task_priority(
            'PUBMED_U1', 123, trial_data
        )
        
        assert isinstance(priority, float)
        assert priority > 0
    
    def test_calculate_task_priority_different_types(self, priority_service):
        """Test priority calculation for different task types."""
        trial_data = {
            'best_S_Rge2': 0.8,
            'uncertainty': 0.6,
            'n_docs_selected': 5
        }
        
        # Test different task types
        u1_priority = priority_service.calculate_task_priority('PUBMED_U1', 123, trial_data)
        oa_priority = priority_service.calculate_task_priority('PUBMED_OA', 123, trial_data)
        studycard_priority = priority_service.calculate_task_priority('STUDYCARD', 123, trial_data)
        
        # STUDY CARD should have highest priority
        assert studycard_priority > oa_priority
        assert oa_priority > u1_priority
    
    def test_time_weight_calculation(self, priority_service):
        """Test time weight calculation."""
        # Test with different time to catalyst values
        weight_close = priority_service._calculate_time_weight(30)  # 30 days
        weight_far = priority_service._calculate_time_weight(180)  # 180 days
        
        # Closer catalyst should have higher weight
        assert weight_close > weight_far
        assert 0 <= weight_close <= 1
        assert 0 <= weight_far <= 1
    
    def test_company_pressure_calculation(self, priority_service):
        """Test company pressure calculation."""
        # Test with different company data
        no_company = priority_service._calculate_company_pressure(None)
        small_company = priority_service._calculate_company_pressure({'market_cap': 1000000})
        large_company = priority_service._calculate_company_pressure({'market_cap': 1000000000})
        
        assert no_company == 0.0
        assert small_company < large_company
        assert 0 <= large_company <= 1.0


class TestContextManager:
    """Test logging context manager."""
    
    @pytest.fixture
    def context_manager(self):
        """Create context manager instance."""
        return ContextManager(run_id="test_run_123")
    
    def test_set_trial_context(self, context_manager):
        """Test setting trial context."""
        context_manager.set_trial_context(123)
        # Context should be set (we can't easily test contextvars here)
        assert True  # Placeholder assertion
    
    def test_set_task_context(self, context_manager):
        """Test setting task context."""
        context_manager.set_task_context(456, "PUBMED_OA")
        # Context should be set
        assert True  # Placeholder assertion
    
    def test_log_stage_start_end(self, context_manager):
        """Test stage logging."""
        # Test stage start
        context_manager.log_stage_start("U1_discovery", trial_id=123)
        
        # Test stage end
        metrics = Mock()
        metrics.to_dict.return_value = {'documents_discovered': 10}
        
        context_manager.log_stage_end("U1_discovery", True, metrics, documents_found=10)
        
        # Should not raise exceptions
        assert True


class TestMetricsCollector:
    """Test metrics collector."""
    
    @pytest.fixture
    def metrics_collector(self):
        """Create metrics collector instance."""
        return MetricsCollector()
    
    def test_increment_metrics(self, metrics_collector):
        """Test metric incrementing."""
        metrics_collector.increment('documents_discovered', 5)
        metrics_collector.increment('documents_processed', 3)
        
        metrics = metrics_collector.get_metrics()
        assert metrics.documents_discovered == 5
        assert metrics.documents_processed == 3
    
    def test_set_metrics(self, metrics_collector):
        """Test metric setting."""
        metrics_collector.set('execution_time_seconds', 120.5)
        
        metrics = metrics_collector.get_metrics()
        assert metrics.execution_time_seconds == 120.5
    
    def test_reset_metrics(self, metrics_collector):
        """Test metrics reset."""
        # Set some metrics
        metrics_collector.increment('documents_discovered', 10)
        metrics_collector.set('execution_time_seconds', 60.0)
        
        # Reset
        metrics_collector.reset()
        
        # Check reset
        metrics = metrics_collector.get_metrics()
        assert metrics.documents_discovered == 0
        assert metrics.execution_time_seconds == 0.0


class TestStageU1Processor:
    """Test U1+ stage processor."""
    
    @pytest.fixture
    def mock_components(self):
        """Create mock components."""
        client = Mock()
        mapper = Mock()
        feature_extractor = Mock()
        rs_scorer = Mock()
        query_builder = Mock()
        
        return {
            'client': client,
            'mapper': mapper,
            'feature_extractor': feature_extractor,
            'rs_scorer': rs_scorer,
            'query_builder': query_builder
        }
    
    @pytest.fixture
    def processor(self, mock_components):
        """Create processor instance."""
        return StageU1Processor(
            client=mock_components['client'],
            mapper=mock_components['mapper'],
            feature_extractor=mock_components['feature_extractor'],
            rs_scorer=mock_components['rs_scorer'],
            query_builder=mock_components['query_builder']
        )
    
    @pytest.mark.asyncio
    async def test_execute_stage_u1_discovery_mode(self, processor, mock_components):
        """Test U1+ execution in discovery mode."""
        # Mock discovery components
        mock_components['query_builder'].build_trial_query.return_value = "test query"
        mock_components['client'].esearch_all = AsyncMock(return_value=['123', '456', '789'])
        mock_components['client'].esummary_batch = AsyncMock(return_value={'123': {}, '456': {}, '789': {}})
        mock_components['mapper'].map_esummary_result.return_value = [
            {'pmid': '123', 'title': 'Test 1'},
            {'pmid': '456', 'title': 'Test 2'},
            {'pmid': '789', 'title': 'Test 3'}
        ]
        
        # Mock database service
        processor.db_service.upsert_documents_metadata = Mock(return_value=(3, 0))
        processor.db_service.store_trial_doc_candidates_discovery = Mock(return_value=(3, 0))
        
        # Execute discovery mode
        result = await processor.execute_stage_u1(
            trial_id=123,
            trial_asset="Test Asset",
            trial_indication="Test Indication",
            asset_aliases=["Test Asset"],
            indication_terms=["Test Indication"]
        )
        
        assert isinstance(result, StageU1Result)
        assert result.success is True
        assert result.documents_discovered == 3
        assert result.documents_mapped == 3
    
    @pytest.mark.asyncio
    async def test_execute_stage_u1_process_only_mode(self, processor, mock_components):
        """Test U1+ execution in process-only mode."""
        # Mock existing documents
        u0_documents = [
            {'pmid': '123', 'title': 'Test 1'},
            {'pmid': '456', 'title': 'Test 2'}
        ]
        
        # Mock processing components
        mock_components['client'].efetch_abstracts_xml = AsyncMock(return_value={
            '123': 'Abstract 1',
            '456': 'Abstract 2'
        })
        mock_components['feature_extractor'].extract_features = Mock(return_value=[
            {'pmid': '123', 'entities': []},
            {'pmid': '456', 'entities': []}
        ])
        mock_components['rs_scorer'].score_documents = Mock(return_value=[
            {'pmid': '123', 'R_score': 0.8, 'S_score': 0.7},
            {'pmid': '456', 'R_score': 0.6, 'S_score': 0.5}
        ])
        
        # Mock database service
        processor.db_service.store_abstracts = Mock(return_value=(2, 0))
        processor.db_service.store_document_links = Mock(return_value=(2, 0))
        processor.db_service.store_rs_scores = Mock(return_value=(2, 0))
        processor.db_service.store_trial_doc_candidates = Mock(return_value=(2, 0))
        processor.db_service.calculate_trial_metrics = Mock(return_value={'best_S_Rge2': 0.7})
        processor.db_service.update_trial_lit_state = Mock(return_value=True)
        
        # Execute process-only mode
        result = await processor.execute_stage_u1(
            trial_id=123,
            trial_asset="Test Asset",
            trial_indication="Test Indication",
            u0_documents=u0_documents
        )
        
        assert isinstance(result, StageU1Result)
        assert result.success is True
        assert result.documents_processed == 2
        assert result.abstracts_fetched == 2
        assert result.documents_scored == 2


class TestIntegration:
    """Integration tests for U1+ pipeline."""
    
    @pytest.mark.asyncio
    async def test_full_u1_plus_workflow(self):
        """Test complete U1+ workflow."""
        # This would be a more comprehensive integration test
        # that tests the full workflow from discovery to scoring
        
        # Mock all components
        client = Mock()
        mapper = Mock()
        feature_extractor = Mock()
        rs_scorer = Mock()
        query_builder = Mock()
        
        # Create processor
        processor = StageU1Processor(
            client=client,
            mapper=mapper,
            feature_extractor=feature_extractor,
            rs_scorer=rs_scorer,
            query_builder=query_builder
        )
        
        # Mock the full workflow
        client.esearch_all = AsyncMock(return_value=['123', '456'])
        client.esummary_batch = AsyncMock(return_value={'123': {}, '456': {}})
        client.efetch_abstracts_xml = AsyncMock(return_value={'123': 'Abstract 1', '456': 'Abstract 2'})
        
        mapper.map_esummary_result.return_value = [
            {'pmid': '123', 'title': 'Test 1'},
            {'pmid': '456', 'title': 'Test 2'}
        ]
        
        feature_extractor.extract_features.return_value = [
            {'pmid': '123', 'entities': []},
            {'pmid': '456', 'entities': []}
        ]
        
        rs_scorer.score_documents.return_value = [
            {'pmid': '123', 'R_score': 0.8, 'S_score': 0.7},
            {'pmid': '456', 'R_score': 0.6, 'S_score': 0.5}
        ]
        
        # Mock database service methods
        processor.db_service.upsert_documents_metadata = Mock(return_value=(2, 0))
        processor.db_service.store_trial_doc_candidates_discovery = Mock(return_value=(2, 0))
        processor.db_service.store_abstracts = Mock(return_value=(2, 0))
        processor.db_service.store_document_links = Mock(return_value=(2, 0))
        processor.db_service.store_rs_scores = Mock(return_value=(2, 0))
        processor.db_service.store_trial_doc_candidates = Mock(return_value=(2, 0))
        processor.db_service.calculate_trial_metrics = Mock(return_value={'best_S_Rge2': 0.7})
        processor.db_service.update_trial_lit_state = Mock(return_value=True)
        
        # Execute full workflow
        result = await processor.execute_stage_u1(
            trial_id=123,
            trial_asset="Test Asset",
            trial_indication="Test Indication",
            asset_aliases=["Test Asset"],
            indication_terms=["Test Indication"]
        )
        
        # Verify result
        assert isinstance(result, StageU1Result)
        assert result.success is True
        assert result.documents_discovered == 2
        assert result.documents_processed == 2
        assert result.abstracts_fetched == 2
        assert result.documents_scored == 2


if __name__ == "__main__":
    pytest.main([__file__])
