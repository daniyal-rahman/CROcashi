"""
Abstract Processor - Dual Persistence Strategy.

Handles abstract fetching, entity extraction, R/S scoring, and document selection.
Stores only filtered, processed documents for LLM processing.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

from .client_manager import get_client_manager
from .mapper import PubMedMapper
from .db_service import PubMedDBService, get_db_service
from .document_manager import DocumentManager
from ...db.session import session_scope
from ...db.models import Document
# Dual persistence service removed - using simplified approach
from ...extract.abstract_features import AbstractFeatureExtractor
from ...utils.config_manager import get_config_manager
from ...utils.error_handler import get_error_handler, safe_execute

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result from abstract processing."""
    success: bool
    documents_processed: int
    abstracts_fetched: int
    entities_extracted: int
    documents_scored: int
    documents_selected: int
    documents_dropped: int
    execution_time: float
    abstracts_stored: int = 0
    error_message: Optional[str] = None
    processed_documents: Optional[List[Dict[str, Any]]] = None
    rs_scores: Optional[List[Dict[str, Any]]] = None


class AbstractProcessor:
    """Processes abstracts and extracts entities with dual persistence (Steps 7-8)."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, session_factory=None):
        """Initialize abstract processor."""
        self.config = config or {}
        self.session_factory = session_factory
        
        # Initialize components
        self.client_config = config.get('client_config', {})
        
        # Initialize PubMed client manager (singleton)
        self.client_manager = get_client_manager()
        self.mapper = PubMedMapper(config.get('mapper_config', {}))
        self.db_service = get_db_service()
        self.document_manager = DocumentManager()
        self.feature_extractor = AbstractFeatureExtractor()
        
        # Using simplified approach - no separate persistence service needed
        
        # Processing settings
        self.batch_size = self.config.get('batch_size', 10)
        self.enable_entity_extraction = self.config.get('enable_entity_extraction', True)
        self.enable_rs_scoring = self.config.get('enable_rs_scoring', True)
        self.min_r_score = self.config.get('min_r_score', 0.35)
        self.min_s_score = self.config.get('min_s_score', 0.20)
        self.enable_database_persistence = self.config.get('enable_database_persistence', True)
        
        logger.info("Abstract processor initialized with dual persistence")
    
    async def process_documents(
        self,
        documents: List[Dict[str, Any]],
        trial_id: int,
        trial_asset: str,
        trial_indication: str,
        trial_nct: Optional[str] = None
    ) -> ProcessingResult:
        """
        Process documents through abstract fetching and entity extraction.
        
        Args:
            documents: List of documents to process (from retrieval)
            trial_id: Trial ID for persistence
            trial_asset: Asset name for scoring
            trial_indication: Indication for scoring
            trial_nct: Optional NCT ID for scoring
            
        Returns:
            ProcessingResult with processing details
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            logger.info(f"Starting abstract processing for {len(documents)} documents with dual persistence")
            
            if not documents:
                return ProcessingResult(
                    success=True,
                    documents_processed=0,
                    abstracts_fetched=0,
                    abstracts_stored=0,
                    entities_extracted=0,
                    documents_scored=0,
                    documents_selected=0,
                    documents_dropped=0,
                    execution_time=(datetime.now(timezone.utc) - start_time).total_seconds()
                )
            
            # Step 7: Fetch abstracts for documents
            abstracts_fetched = await self._fetch_abstracts(documents)
            logger.info(f"Fetched abstracts for {abstracts_fetched} documents")
            
            # Step 7: Extract entities from abstracts
            documents_with_entities = []
            total_entities = 0
            
            if self.enable_entity_extraction:
                documents_with_entities, total_entities = await self._extract_entities(documents)
                logger.info(f"Extracted {total_entities} entities from {len(documents_with_entities)} documents")
            else:
                documents_with_entities = documents
            
            # Step 8: Compute R/S scores
            documents_scored = []
            rs_scores = []
            
            if self.enable_rs_scoring:
                documents_scored, rs_scores = await self._compute_rs_scores(
                    documents_with_entities, trial_id, trial_asset, trial_indication, trial_nct
                )
                logger.info(f"Computed R/S scores for {len(documents_scored)} documents")
            else:
                documents_scored = documents_with_entities
            
            # Step 8: Select/drop documents based on R/S tiers
            selected_docs, dropped_docs = await self._select_documents(documents_scored)
            
            # Store abstracts in database for all documents that have abstracts
            abstracts_stored = 0
            abstracts_failed = 0
            if documents_with_entities:  # Use documents that have abstracts
                try:
                    # Extract abstracts from documents for database storage
                    abstracts_dict = {}
                    for doc in documents_with_entities:
                        pmid = doc.get('pmid')
                        abstract = doc.get('abstract')
                        if pmid and abstract:
                            abstracts_dict[pmid] = abstract
                    
                    successful, failed = self.db_service.store_abstracts(documents_with_entities, abstracts_dict)
                    abstracts_stored = successful
                    abstracts_failed = failed
                    logger.info(f"Stored {successful} abstracts to database, {failed} failed")
                except Exception as e:
                    logger.error(f"Failed to store abstracts to database: {e}")
                    abstracts_failed = len(abstracts_dict) if 'abstracts_dict' in locals() else 0
            
            # Document status updates are now handled by DocumentManager
            candidates_updated = 0
            candidates_failed = 0
            if documents_with_entities:  # Use documents that have abstracts
                try:
                    # Prepare candidate data for stage progression
                    candidates_data = []
                    for doc in documents_with_entities:
                        pmid = doc.get('pmid')
                        if pmid:
                            candidates_data.append({
                                'pmid': pmid,
                                'stage': 'U1_abstract',  # Update stage from U1_discovery
                                'selected': True,  # Mark as selected after abstract processing
                                'dropped_reason': None,
                                'notes': 'Selected after abstract processing and R/S scoring'
                            })
                    
                    # Document status updates are now handled by DocumentManager in the scoring process
                    candidates_updated = len(documents_with_entities)
                    candidates_failed = 0
                    logger.info(f"Processed {candidates_updated} documents with abstracts")
                except Exception as e:
                    logger.error(f"Failed to process documents: {e}")
                    candidates_failed = len(documents_with_entities) if documents_with_entities else 0
            
            # Store only processed documents (filtered for LLM processing)
            if selected_docs:
                # Mark documents as processed using simplified approach
                doc_ids = []
                for doc in selected_docs:
                    pmid = doc.get('pmid')
                    if pmid:
                        # Get document ID from database
                        with session_scope() as session:
                            db_doc = session.query(Document).filter(Document.pmid == pmid).first()
                            if db_doc:
                                doc_ids.append(db_doc.doc_id)
                
                if doc_ids:
                    processed_count = self.db_service.mark_documents_as_processed(doc_ids)
                    logger.info(f"mark_documents_as_processed: marked={processed_count} documents as processed")
                    
                    if processed_count == 0:
                        logger.error(f"Failed to mark documents as processed: no documents updated")
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            return ProcessingResult(
                success=True,
                documents_processed=len(documents),
                abstracts_fetched=abstracts_fetched,
                abstracts_stored=abstracts_stored,
                entities_extracted=total_entities,
                documents_scored=len(documents_scored),
                documents_selected=len(selected_docs),
                documents_dropped=len(dropped_docs),
                execution_time=execution_time,
                processed_documents=selected_docs,
                rs_scores=rs_scores
            )
            
        except Exception as e:
            logger.error(f"Error in abstract processing: {e}")
            return ProcessingResult(
                success=False,
                documents_processed=0,
                abstracts_fetched=0,
                abstracts_stored=0,
                entities_extracted=0,
                documents_scored=0,
                documents_selected=0,
                documents_dropped=0,
                execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                error_message=str(e)
            )
    
    async def _fetch_abstracts(self, documents: List[Dict[str, Any]]) -> int:
        """Fetch abstracts for documents using EFetch."""
        try:
            pmids = [doc.get('pmid') for doc in documents if doc.get('pmid')]
            if not pmids:
                return 0
            
            # Log EFetch diagnostics
            client = await self.client_manager.get_client(self.config)
            logger.info(f"EFetch coverage diagnostics:")
            logger.info(f"  EFetch batch size: {len(pmids)}, retry attempts: {client.max_retries}")
            
            async with client:
                # Fetch abstracts using EFetch XML for more reliable parsing
                abstract_result = await client.efetch_abstracts_xml(pmids)
                
                # Parse abstracts and add to documents with detailed diagnostics
                abstracts_fetched = 0
                no_abstract = 0
                pmid_missing = 0
                xml_parse_error = 0
                
                # Log EFetch URL and payload for debugging
                logger.info(f"EFetch requested PMIDs: {pmids}")
                logger.info(f"EFetch returned PMIDs: {list(abstract_result.keys())}")
                missing_pmids = set(pmids) - set(abstract_result.keys())
                if missing_pmids:
                    logger.warning(f"EFetch missing PMIDs: {sorted(missing_pmids)[:10]}")
                
                for doc in documents:
                    pmid = doc.get('pmid')
                    if pmid and pmid in abstract_result:
                        # efetch_abstracts_xml now returns Dict[str, Dict[str, Any]]
                        abstract_data = abstract_result[pmid]
                        abstract_text = abstract_data.get('abstract', '') if isinstance(abstract_data, dict) else str(abstract_data)
                        if abstract_text and abstract_text.strip():
                            doc['abstract'] = abstract_text
                            abstracts_fetched += 1
                        else:
                            no_abstract += 1
                    else:
                        pmid_missing += 1
                
                # Log EFetch coverage results
                logger.info(f"  EFetch results: parsed={abstracts_fetched}, no_abstract={no_abstract}, pmid_missing={pmid_missing}, xml_parse_error={xml_parse_error}")
                
                return abstracts_fetched
                
        except Exception as e:
            logger.error(f"Error fetching abstracts: {e}")
            return 0
    
    async def _extract_entities(self, documents: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """Extract entities from document abstracts."""
        try:
            documents_with_entities = []
            total_entities = 0
            
            for doc in documents:
                pmid = doc.get('pmid')
                if pmid and doc.get('abstract'):
                    abstract_text = doc.get('abstract')
                    
                    # Extract entities using feature extractor
                    entities = self.feature_extractor.extract_all_features(abstract_text)
                    doc['extracted_entities'] = entities
                    doc['abstract_text'] = abstract_text
                    
                    total_entities += len(entities)
                    documents_with_entities.append(doc)
            
            return documents_with_entities, total_entities
            
        except Exception as e:
            logger.error(f"Error extracting entities: {e}")
            return documents, 0
    
    async def _compute_rs_scores(
        self, 
        documents: List[Dict[str, Any]], 
        trial_id: int, 
        trial_asset: str, 
        trial_indication: str, 
        trial_nct: Optional[str]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Compute R/S scores for documents and store them directly in document records."""
        try:
            # Import R/S scorer
            from .rs_scorer import RSScorer
            
            # Initialize R/S scorer
            rs_scorer = RSScorer()
            
            # Get trial phase for scoring context
            trial_phase = None
            try:
                from ncfd.db.session import session_scope
                from ncfd.db.models import Trial
                with session_scope() as session:
                    trial = session.query(Trial).filter(Trial.trial_id == trial_id).first()
                    if trial:
                        trial_phase = trial.phase
            except Exception as e:
                logger.warning(f"Could not get trial phase for R/S scoring: {e}")
            
            documents_scored = []
            
            for doc in documents:
                try:
                    # Calculate real R/S scores
                    rs_result = rs_scorer.score_document(
                        doc=doc,
                        trial_asset=trial_asset,
                        trial_indication=trial_indication,
                        trial_nct=trial_nct,
                        trial_phase=trial_phase
                    )
                    
                    # Add R/S scores to document
                    doc['r_score'] = rs_result.r_score
                    doc['r_tier'] = rs_result.r_tier
                    doc['s_score'] = rs_result.s_score
                    doc['s_tier'] = rs_result.s_tier
                    doc['r_components'] = rs_result.r_components
                    doc['s_components'] = rs_result.s_components
                    doc['rs_decided_at'] = datetime.now(timezone.utc)
                    
                    logger.debug(f"Document {doc.get('pmid', 'unknown')}: R={rs_result.r_score:.3f} ({rs_result.r_tier}), S={rs_result.s_score:.3f} ({rs_result.s_tier})")
                    
                except Exception as e:
                    logger.error(f"Error scoring document {doc.get('pmid', 'unknown')}: {e}")
                    # Use default scores for error cases
                    doc['r_score'] = 0.0
                    doc['r_tier'] = "R0"
                    doc['s_score'] = 0.0
                    doc['s_tier'] = "S0"
                    doc['r_components'] = {'error': str(e)}
                    doc['s_components'] = {'error': str(e)}
                    doc['rs_decided_at'] = datetime.now(timezone.utc)
                
                documents_scored.append(doc)
            
            # Store R/S scores using DocumentManager
            if documents_scored:
                successful = 0
                failed = 0
                
                for doc in documents_scored:
                    try:
                        doc_id = doc.get('doc_id')
                        if not doc_id:
                            # Look up doc_id from database using pmid
                            pmid = doc.get('pmid')
                            if pmid:
                                with session_scope() as session:
                                    from ncfd.db.models import Document
                                    db_doc = session.query(Document).filter(Document.pmid == pmid).first()
                                    if db_doc:
                                        doc_id = db_doc.doc_id
                                        doc['doc_id'] = doc_id
                                    else:
                                        logger.warning(f"Document with PMID {pmid} not found in database")
                                        failed += 1
                                        continue
                            else:
                                logger.warning(f"No doc_id or pmid found for document")
                                failed += 1
                                continue
                        
                        # Use DocumentManager to score the document
                        success = self.document_manager.score_document(
                            doc_id=doc_id,
                            r_score=doc.get('r_score', 0.0),
                            s_score=doc.get('s_score', 0.0),
                            r_components=doc.get('r_components'),
                            s_components=doc.get('s_components')
                        )
                        
                        # Document status is automatically updated to 'scored' by DocumentManager.score_document()
                        
                        if success:
                            successful += 1
                        else:
                            failed += 1
                            
                    except Exception as e:
                        logger.error(f"Failed to score document {doc.get('pmid', 'unknown')}: {e}")
                        failed += 1
                
                logger.info(f"Stored R/S scores for {successful} documents, {failed} failed")
            
            return documents_scored, []  # Return empty rs_scores list since scores are now in documents
            
        except Exception as e:
            logger.error(f"Error computing R/S scores: {e}")
            return documents, []
    
    def _determine_r_tier(self, r_score: float) -> str:
        """Determine R tier based on score."""
        if r_score >= 0.8:
            return "R3"
        elif r_score >= 0.6:
            return "R2"
        elif r_score >= 0.4:
            return "R1"
        else:
            return "R0"
    
    def _determine_s_tier(self, s_score: float) -> str:
        """Determine S tier based on score."""
        if s_score >= 0.8:
            return "S3"
        elif s_score >= 0.6:
            return "S2"
        elif s_score >= 0.4:
            return "S1"
        else:
            return "S0"
    
    def _determine_rs_tier(self, r_score: float, s_score: float) -> str:
        """Determine combined R/S tier based on scores (legacy method)."""
        r_tier = self._determine_r_tier(r_score)
        s_tier = self._determine_s_tier(s_score)
        return f"{r_tier}{s_tier}"
    
    async def _select_documents(self, documents: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Select/drop documents based on R/S tiers."""
        try:
            selected_docs = []
            dropped_docs = []
            
            for doc in documents:
                r_tier = doc.get('r_tier', 'R0')
                s_tier = doc.get('s_tier', 'S0')
                
                # Select documents with R>=1 or S>=1 (any meaningful relevance or shortability)
                if r_tier in ['R1', 'R2', 'R3'] or s_tier in ['S1', 'S2', 'S3']:
                    selected_docs.append(doc)
                else:
                    dropped_docs.append(doc)
            
            return selected_docs, dropped_docs
            
        except Exception as e:
            logger.error(f"Error selecting documents: {e}")
            return documents, []