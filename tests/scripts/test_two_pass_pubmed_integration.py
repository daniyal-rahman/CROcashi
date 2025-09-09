#!/usr/bin/env python3
"""
Two-Pass PubMed Integration Test

This test verifies the complete two-pass PubMed workflow:
1. Pass 1: PubMed ingestion (U0, U1) + heuristic evaluation + literature queue
2. Pass 2: Pop trial from queue + OA full text + study card generation

The test uses mocked external services but real database operations.
"""

import asyncio
import pytest
import logging
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any, List
from datetime import datetime, timezone

from src.ncfd.pipeline.orchestrator import UnifiedPipelineOrchestrator
from src.ncfd.ingest.pubmed.pipeline import PubMedPipeline
from src.ncfd.ingest.pubmed.db_service import PubMedDBService
from src.ncfd.pipeline.lit_queue import LiteratureQueue
from src.ncfd.db.session import session_scope
from src.ncfd.db.models import Document, DocumentText, DocumentLink, TrialLitState, Trial

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_pubmed_client():
    """Mock PubMed client with realistic responses."""
    client = Mock()
    
    # Mock esearch - return sample PMIDs
    client.esearch = AsyncMock(return_value={
        'idlist': ['12345678', '87654321', '11111111'],
        'count': 3
    })
    
    # Mock esummary batch processing
    async def mock_process_pmids_in_batches(pmids, operation):
        return {
            '12345678': {
                'uid': '12345678',
                'title': 'Test Drug A for Cancer Treatment',
                'fulljournalname': 'Journal of Oncology',
                'pubdate': '2023',
                'pubtype': ['Clinical Trial'],
                'authors': [{'name': 'Smith J'}, {'name': 'Doe A'}]
            },
            '87654321': {
                'uid': '87654321', 
                'title': 'Phase II Study of Test Drug A',
                'fulljournalname': 'Cancer Research',
                'pubdate': '2023',
                'pubtype': ['Randomized Controlled Trial'],
                'authors': [{'name': 'Johnson B'}, {'name': 'Lee C'}]
            },
            '11111111': {
                'uid': '11111111',
                'title': 'Safety Profile of Test Drug A',
                'fulljournalname': 'Drug Safety',
                'pubdate': '2022',
                'pubtype': ['Clinical Study'],
                'authors': [{'name': 'Wilson D'}]
            }
        }
    
    client.batch_processor = Mock()
    client.batch_processor.process_pmids_in_batches = mock_process_pmids_in_batches
    
    # Mock abstract fetching
    client.efetch_abstracts_xml = AsyncMock(return_value={
        '12345678': 'This study evaluates Test Drug A for cancer treatment. NCT01234567.',
        '87654321': 'Phase II randomized controlled trial of Test Drug A in cancer patients.',
        '11111111': 'Safety analysis of Test Drug A showing good tolerability.'
    })
    
    # Mock PMC full text fetching
    client.elink_pmid_to_pmcid = AsyncMock(return_value={
        '12345678': 'PMC7654321',
        '87654321': 'PMC1234567',
        '11111111': None
    })
    
    client.check_pmc_oa_status = AsyncMock(return_value={
        'PMC7654321': {'full_text_available': True, 'is_oa': True},
        'PMC1234567': {'full_text_available': True, 'is_oa': True}
    })
    
    client.get_pmc_full_text = AsyncMock(return_value='Full text content for PMC article...')
    
    # Mock context manager methods
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    
    return client


@pytest.fixture
def test_trial_data():
    """Create test trial data."""
    return {
        'trial_id': 1,
        'nct_id': 'NCT01234567',
        'official_title': 'Test Drug A Phase II Study',
        'status': 'Recruiting',
        'phase': 'P2',
        'intervention_name': 'Test Drug A',
        'condition': 'Cancer'
    }


@pytest.fixture
def orchestrator_config():
    """Configuration for orchestrator."""
    return {
        'pubmed': {
            'asset_names': ['Test Drug A'],
            'indications': ['Cancer'],
            'max_results': 10,
            'enable_stages': ['U0', 'U1'],
            'client_config': {
                'rate_limit_requests_per_minute': 60,
                'timeout_seconds': 30
            }
        },
        'literature_queue': {
            'max_queue_size': 100,
            'priority_weights': {
                'best_s_weight': 0.4,
                'time_weight': 0.3,
                'uncertainty_weight': 0.2,
                'utility_weight': 0.1
            }
        },
        'study_card': {
            'max_documents': 10,
            'llm_config': {
                'model': 'gpt-4',
                'temperature': 0.3
            }
        }
    }


class TestTwoPassPubMedIntegration:
    """Test the complete two-pass PubMed workflow."""
    
    @pytest.mark.asyncio
    async def test_complete_two_pass_workflow(self, mock_pubmed_client, test_trial_data, orchestrator_config):
        """Test the complete two-pass workflow from ingestion to study cards."""
        
        # Setup: Create test trial in database
        with session_scope() as session:
            trial = Trial(
                trial_id=test_trial_data['trial_id'],
                nct_id=test_trial_data['nct_id'],
                official_title=test_trial_data['official_title'],
                status=test_trial_data['status'],
                phase=test_trial_data['phase'],
                intervention_name=test_trial_data['intervention_name'],
                condition=test_trial_data['condition']
            )
            session.add(trial)
            session.commit()
        
        # Initialize orchestrator
        orchestrator = UnifiedPipelineOrchestrator(orchestrator_config)
        
        # Mock the PubMed client in the pipeline
        with patch.object(orchestrator.pubmed_pipeline, 'client', mock_pubmed_client), \
             patch.object(orchestrator.pubmed_pipeline.batch_processor, 'client', mock_pubmed_client):
            
            # PASS 1: Run PubMed ingestion (U0, U1) + feed literature queue
            logger.info("=== PASS 1: PubMed Ingestion + Queue Feeding ===")
            
            # Execute PubMed pipeline
            pubmed_result = orchestrator._execute_pubmed_pipeline(force_full_scan=False)
            
            # Verify Pass 1 results
            assert pubmed_result is not None
            assert pubmed_result.success
            assert pubmed_result.documents_processed > 0
            logger.info(f"Pass 1 completed: {pubmed_result.documents_processed} documents processed")
            
            # Verify documents were persisted to database
            with session_scope() as session:
                documents = session.query(Document).filter(Document.source_type == 'Paper').all()
                assert len(documents) > 0
                logger.info(f"Found {len(documents)} documents in database")
                
                # Verify abstracts were stored
                doc_texts = session.query(DocumentText).filter(
                    DocumentText.abstract_text.isnot(None)
                ).all()
                assert len(doc_texts) > 0
                logger.info(f"Found {len(doc_texts)} documents with abstracts")
                
                # Verify document links were created
                doc_links = session.query(DocumentLink).filter(
                    DocumentLink.trial_id == test_trial_data['trial_id']
                ).all()
                assert len(doc_links) > 0
                logger.info(f"Found {len(doc_links)} document links")
                
                # Verify trial literature state was updated
                lit_state = session.query(TrialLitState).filter(
                    TrialLitState.trial_id == test_trial_data['trial_id']
                ).first()
                assert lit_state is not None
                assert lit_state.best_S_Rge2 is not None
                logger.info(f"Trial literature state: S={lit_state.best_S_Rge2}, docs_seen={lit_state.n_docs_seen}")
            
            # Verify literature queue was populated
            queue_size = orchestrator.literature_queue.get_queue_size()
            assert queue_size > 0
            logger.info(f"Literature queue size: {queue_size}")
            
            # PASS 2: Pop trial from queue + OA full text + study card generation
            logger.info("=== PASS 2: Queue Pop + Full Text + Study Cards ===")
            
            # Mock study card pipeline for testing
            with patch('src.ncfd.pipeline.study_card_pipeline.StudyCardPipeline') as mock_study_card:
                mock_pipeline_instance = Mock()
                mock_pipeline_instance.execute.return_value = {
                    'success': True,
                    'study_card': {
                        'trial_id': test_trial_data['trial_id'],
                        'title': 'Test Drug A Study Card',
                        'summary': 'Study card generated successfully'
                    },
                    'factsheet': {
                        'key_findings': ['Safety profile acceptable', 'Efficacy signals observed'],
                        'risk_factors': ['None identified']
                    }
                }
                mock_study_card.return_value = mock_pipeline_instance
                
                # Execute second pass
                second_pass_result = orchestrator.run_literature_second_pass()
                
                # Verify Pass 2 results
                assert second_pass_result['success']
                assert second_pass_result['trials_processed'] == 1
                assert second_pass_result['study_card_generated']
                logger.info(f"Pass 2 completed: trial {second_pass_result['trial_id']} processed")
                
                # Verify OA full text was fetched and stored
                if second_pass_result['oa_documents_processed'] > 0:
                    with session_scope() as session:
                        full_text_docs = session.query(DocumentText).filter(
                            DocumentText.fulltext_text.isnot(None)
                        ).all()
                        assert len(full_text_docs) > 0
                        logger.info(f"Found {len(full_text_docs)} documents with full text")
                
                # Verify study card pipeline was called
                mock_pipeline_instance.execute.assert_called_once()
                
                # Verify trial status was updated in queue
                # (This would be implementation-specific based on LiteratureQueue internals)
        
        logger.info("=== Two-Pass Workflow Test Completed Successfully ===")
    
    @pytest.mark.asyncio
    async def test_pass_1_document_persistence(self, mock_pubmed_client, test_trial_data, orchestrator_config):
        """Test that Pass 1 correctly persists all document metadata and relationships."""
        
        # Setup test trial
        with session_scope() as session:
            trial = Trial(
                trial_id=test_trial_data['trial_id'],
                nct_id=test_trial_data['nct_id'],
                official_title=test_trial_data['official_title'],
                status=test_trial_data['status']
            )
            session.add(trial)
            session.commit()
        
        # Initialize PubMed pipeline directly
        pubmed_pipeline = PubMedPipeline(orchestrator_config['pubmed'])
        
        with patch.object(pubmed_pipeline, 'client', mock_pubmed_client), \
             patch.object(pubmed_pipeline.batch_processor, 'client', mock_pubmed_client):
            
            # Execute U0 and U1 stages
            asset_names = orchestrator_config['pubmed']['asset_names']
            indications = orchestrator_config['pubmed']['indications']
            
            results = await pubmed_pipeline.execute_pipeline(
                asset_names=asset_names,
                indications=indications,
                enable_stages=['U0', 'U1']
            )
            
            # Verify U0 result
            u0_result = next((r for r in results if r.stage == 'U0'), None)
            assert u0_result is not None
            assert u0_result.success
            
            # Verify U1 result
            u1_result = next((r for r in results if r.stage == 'U1'), None)
            assert u1_result is not None
            assert u1_result.success
            
            # Verify database state after Pass 1
            with session_scope() as session:
                # Check documents table
                documents = session.query(Document).filter(
                    Document.source_type == 'Paper'
                ).all()
                assert len(documents) == 3  # Should match mock PMIDs
                
                # Check document_text table
                doc_texts = session.query(DocumentText).join(
                    Document, DocumentText.doc_id == Document.doc_id
                ).filter(Document.source_type == 'Paper').all()
                assert len(doc_texts) == 3
                
                # Verify abstracts are stored
                abstracts_count = sum(1 for dt in doc_texts if dt.abstract_text)
                assert abstracts_count > 0
                
                # Check document_links table
                doc_links = session.query(DocumentLink).filter(
                    DocumentLink.trial_id == test_trial_data['trial_id']
                ).all()
                assert len(doc_links) > 0
                
                # Check trial literature state
                lit_state = session.query(TrialLitState).filter(
                    TrialLitState.trial_id == test_trial_data['trial_id']
                ).first()
                assert lit_state is not None
                assert lit_state.n_docs_seen > 0
        
        logger.info("Pass 1 document persistence test completed successfully")
    
    @pytest.mark.asyncio
    async def test_pass_2_oa_execution(self, mock_pubmed_client, test_trial_data, orchestrator_config):
        """Test that Pass 2 correctly executes OA stage for queued trials."""
        
        # Setup: Pre-populate database with U1 results
        db_service = PubMedDBService()
        
        # Create test documents
        test_docs = [
            {
                'pmid': '12345678',
                'title': 'Test Drug A for Cancer Treatment',
                'fulljournalname': 'Journal of Oncology',
                'published_at': datetime(2023, 1, 1, tzinfo=timezone.utc)
            }
        ]
        
        # Store documents
        db_service.store_documents_metadata(test_docs)
        
        # Create trial doc candidates (selected for OA)
        candidates = [
            {
                'pmid': '12345678',
                'stage': 'U1_abstract',
                'selected': True
            }
        ]
        
        db_service.store_trial_doc_candidates(test_trial_data['trial_id'], candidates)
        
        # Initialize PubMed pipeline
        pubmed_pipeline = PubMedPipeline(orchestrator_config['pubmed'])
        
        with patch.object(pubmed_pipeline, 'client', mock_pubmed_client):
            
            # Execute OA stage for specific trial
            oa_result = await pubmed_pipeline.run_oa_for_trial(test_trial_data['trial_id'])
            
            # Verify OA execution
            assert oa_result is not None
            assert oa_result.success
            
            # Verify full text was stored in database
            with session_scope() as session:
                full_text_docs = session.query(DocumentText).filter(
                    DocumentText.fulltext_text.isnot(None)
                ).all()
                
                if oa_result.documents_processed > 0:
                    assert len(full_text_docs) > 0
                    
                    # Verify document content_type was updated
                    documents_with_fulltext = session.query(Document).filter(
                        Document.content_type == 'fulltext'
                    ).all()
                    assert len(documents_with_fulltext) > 0
        
        logger.info("Pass 2 OA execution test completed successfully")
    
    def test_literature_queue_integration(self, test_trial_data, orchestrator_config):
        """Test literature queue feeding and trial prioritization."""
        
        # Initialize orchestrator
        orchestrator = UnifiedPipelineOrchestrator(orchestrator_config)
        
        # Setup: Create trial with literature state
        with session_scope() as session:
            trial = Trial(
                trial_id=test_trial_data['trial_id'],
                nct_id=test_trial_data['nct_id'],
                official_title=test_trial_data['official_title'],
                status='Recruiting'
            )
            session.add(trial)
            
            lit_state = TrialLitState(
                trial_id=test_trial_data['trial_id'],
                best_S_Rge2=0.75,
                n_docs_seen=5,
                n_docs_selected=2,
                p_short=0.4,
                uncertainty=0.6,
                status='active'
            )
            session.add(lit_state)
            session.commit()
        
        # Mock PubMed result
        mock_pubmed_result = {
            'success': True,
            'documents_processed': 5,
            'documents_failed': 0
        }
        
        # Feed the literature queue
        orchestrator._feed_literature_queue_from_pubmed_results(mock_pubmed_result)
        
        # Verify queue was populated
        queue_size = orchestrator.literature_queue.get_queue_size()
        assert queue_size > 0
        
        # Verify we can pop a trial
        next_trial = orchestrator.literature_queue.get_next_trial()
        assert next_trial is not None
        assert next_trial['trial_id'] == test_trial_data['trial_id']
        assert next_trial['nct_id'] == test_trial_data['nct_id']
        
        logger.info("Literature queue integration test completed successfully")


if __name__ == "__main__":
    # Run the tests directly
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
