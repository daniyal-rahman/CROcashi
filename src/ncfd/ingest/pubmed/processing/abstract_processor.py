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

from ..client import PubMedClient
from ..mapper import PubMedMapper
from ..db_service import PubMedDBService, get_db_service
from ....db.session import session_scope
# Dual persistence service removed - using simplified approach
from ....extract.abstract_features import AbstractFeatureExtractor

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
        client_config = config.get('client_config', {})
        
        # Map configuration parameters to PubMedClient constructor parameters
        mapped_config = {}
        if 'rate_limit_requests_per_minute' in client_config:
            # Convert requests per minute to requests per second
            mapped_config['rate_limit_per_sec'] = client_config['rate_limit_requests_per_minute'] / 60
        if 'batch_size' in client_config:
            mapped_config['batch_size'] = client_config['batch_size']
        if 'timeout_seconds' in client_config:
            mapped_config['timeout_seconds'] = client_config['timeout_seconds']
        if 'max_retries' in client_config:
            mapped_config['max_retries'] = client_config['max_retries']
        if 'api_key' in client_config:
            mapped_config['api_key'] = client_config['api_key']
        if 'email' in client_config:
            mapped_config['email'] = client_config['email']
        if 'tool' in client_config:
            mapped_config['tool'] = client_config['tool']
        
        self.client = PubMedClient(**mapped_config)
        self.mapper = PubMedMapper(config.get('mapper_config', {}))
        self.db_service = get_db_service()
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
            
            # Store only processed documents (filtered for LLM processing)
            if selected_docs:
                # Mark documents as processed using simplified approach
                doc_ids = []
                for doc in selected_docs:
                    pmid = doc.get('pmid')
                    if pmid:
                        # Get document ID from database
                        with session_scope() as session:
                            from ....db.models import Document
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
            logger.info(f"EFetch coverage diagnostics:")
            logger.info(f"  EFetch batch size: {len(pmids)}, retry attempts: {self.client.max_retries}")
            
            async with self.client:
                # Fetch abstracts using EFetch XML for more reliable parsing
                abstract_result = await self.client.efetch_abstracts_xml(pmids)
                
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
                        abstract_text = abstract_result[pmid]  # efetch_abstracts_xml returns Dict[str, str]
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
            # This would integrate with the R/S scoring system
            # For now, return documents as-is with placeholder scores
            documents_scored = []
            
            for doc in documents:
                # Placeholder R/S scoring logic
                r_score = 0.5  # Would be computed based on relevance
                s_score = 0.3  # Would be computed based on shortability
                
                # Determine R/S tiers
                r_tier = self._determine_r_tier(r_score)
                s_tier = self._determine_s_tier(s_score)
                
                # Add R/S scores directly to document
                doc['r_score'] = r_score
                doc['r_tier'] = r_tier
                doc['s_score'] = s_score
                doc['s_tier'] = s_tier
                doc['r_components_jsonb'] = {'placeholder': 'R components would go here'}
                doc['s_components_jsonb'] = {'placeholder': 'S components would go here'}
                doc['rs_decided_at'] = datetime.now(timezone.utc)
                
                documents_scored.append(doc)
            
            # Store R/S scores directly in documents using the updated DB service
            if documents_scored:
                successful, failed = self.db_service.update_document_rs_scores(documents_scored)
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