"""
Enhanced Retriever Worker - LLM-First Architecture

Document retrieval worker that fetches DocumentCards and raw text for LLM processing.
No longer generates or triages spans - spans are created by LLM quote backtracing.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from ..base_extract_worker import BaseWorker, WorkerOutput
from ..models import DocumentCard
from ..utils import resolve_external_doc_id, get_document_metadata, get_document_text, get_standardized_doc_id
from ...db.models import Document, DocumentText
from ...db.session import get_session

logger = logging.getLogger(__name__)


class EnhancedRetriever(BaseWorker):
    """Enhanced Retriever for LLM-first architecture - fetches documents and raw text only."""
    
    def __init__(self, max_span_length: int = 400, min_confidence: float = 0.7):
        super().__init__("EnhancedRetriever", "3.0.0")  # Version bump for LLM-first
        # Note: max_span_length and min_confidence are kept for API compatibility
        # but are not used in LLM-first architecture
        
        
    def _validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate required inputs."""
        return 'trial_context' in inputs
    
    def process(self, inputs: Dict[str, Any]) -> WorkerOutput:
        """Process inputs to retrieve documents and raw text for LLM processing."""
        try:
            trial_context = inputs["trial_context"]
            date_window = inputs.get("date_window", "2020-2024")
            use_real_retrieval = inputs.get("use_real_retrieval", True)
            
            # Retrieve documents based on trial context
            document_cards = self._retrieve_documents(trial_context, date_window, use_real_retrieval)
            
            # Get abstracts for prioritization (runtime only, not persisted)
            # Full text will be lazy-loaded during LLM processing
            raw_doc_texts = {}
            for doc_card in document_cards:
                # Ensure doc_id is consistently a string for key consistency
                doc_id_key = str(doc_card.doc_id)
                abstract_text = self._get_abstract_for_prioritization(doc_id_key)
                if abstract_text:
                    raw_doc_texts[doc_id_key] = abstract_text
                    logger.debug(f"Loaded abstract for prioritization: doc {doc_card.doc_id} ({len(abstract_text)} chars)")
            
            # Add provenance to document cards
            for i, doc_card in enumerate(document_cards):
                document_cards[i] = self._add_provenance(doc_card, inputs)
            
            return WorkerOutput(
                success=True,
                output={
                    "document_cards": document_cards,
                    "raw_doc_texts": raw_doc_texts
                },
                metadata={
                    "documents_retrieved": len(document_cards),
                    "raw_texts_retrieved": len(raw_doc_texts),
                    "date_window": date_window,
                    "llm_first_mode": True
                }
            )
            
        except Exception as e:
            return WorkerOutput(
                success=False,
                output=None,
                error_message=f"Enhanced Retriever failed: {str(e)}"
            )
    
    def _retrieve_documents(self, trial_context: Dict[str, Any], 
                           date_window: str, use_real_retrieval: bool = True) -> List[DocumentCard]:
        """Retrieve relevant documents based on trial context."""
        documents = []
        
        if use_real_retrieval:
            try:
                with get_session() as session:
                    trial_id = trial_context.get('trial_id')
                    nct_id = trial_context.get('nct_id')
                    logger.info(f"DEBUG: trial_context = {trial_context}")
                    logger.info(f"DEBUG: trial_id = {trial_id}, nct_id = {nct_id}")
                    
                    # Query documents linked to this trial
                    linked_docs = []
                    if trial_id:
                        # Convert trial_id to integer if needed for database lookup
                        trial_id_int = None
                        try:
                            trial_id_int = int(trial_id) if isinstance(trial_id, str) else trial_id
                        except (ValueError, TypeError):
                            logger.warning(f"Could not convert trial_id '{trial_id}' to integer, skipping trial_id lookup")
                        
                        if trial_id_int is not None:
                            # Use simplified system - documents are directly linked to trials
                            linked_docs = session.query(Document).filter(
                                Document.trial_id == trial_id_int
                            ).all()
                            logger.info(f"DEBUG: Found {len(linked_docs)} documents linked to trial_id {trial_id_int}")
                    
                    # Also try NCT ID lookup (fallback strategy)
                    if not linked_docs and nct_id:
                        linked_docs = session.query(Document).filter(
                            Document.nct_id == nct_id
                        ).all()
                        logger.debug(f"Found {len(linked_docs)} documents with nct_id {nct_id}")
                    
                    # NCT ID lookup is already handled above
                    
                    # Convert to DocumentCards using database doc_id for prioritization matching
                    # Only create DocumentCard objects for documents that have abstracts
                    for doc in linked_docs:
                        # Check if document has abstract text
                        doc_text = session.query(DocumentText).filter(DocumentText.doc_id == doc.doc_id).first()
                        if not doc_text or not doc_text.abstract_text or len(doc_text.abstract_text.strip()) == 0:
                            logger.debug(f"Skipping document {doc.doc_id} - no abstract text available")
                            continue
                            
                        # Simple document type classification
                        title = doc.title or f"Document for {nct_id}"
                        abstract = doc_text.abstract_text or ""
                        
                        # Skip non-trial papers (reviews, mechanistic studies, etc.)
                        non_trial_keywords = [
                            "review", "mechanism", "preclinical", "in vitro", "in vivo", 
                            "animal model", "cell line", "molecular", "pathway", "signaling"
                        ]
                        
                        is_non_trial = any(keyword in title.lower() or keyword in abstract.lower() 
                                          for keyword in non_trial_keywords)
                        
                        if is_non_trial:
                            logger.debug(f"Skipping non-trial document {doc.doc_id}: {title[:50]}...")
                            continue
                        
                        # Use database doc_id (integer) for prioritization matching
                        # The standardized format is used elsewhere, but here we need the integer for matching
                        doc_card = DocumentCard(
                            doc_id=doc.doc_id,  # Use integer doc_id for prioritization matching
                            doc_type="paper",
                            title=title,
                            year=doc.published_at.year if doc.published_at else 2023
                        )
                        
                        doc_card.disease = trial_context.get('disease', '')
                        doc_card.intervention = trial_context.get('intervention', '')
                        doc_card.study_type = trial_context.get('study_type', 'RCT')
                        doc_card.venue = "Literature"
                        
                        documents.append(doc_card)
                        
                    if documents:
                        print(f"Found {len(documents)} real documents for trial {nct_id}")
                        return documents
                    
            except Exception as e:
                print(f"Error retrieving real documents: {e}")
        
        # Fallback to mock document for testing
        disease = trial_context.get("disease", "")
        intervention = trial_context.get("intervention", "")
        
        if disease and intervention:
            doc_card = DocumentCard(
                doc_id=f"ctgov:{trial_context.get('trial_id', 'NCT12345')}",
                doc_type="paper", 
                title=f"Study of {intervention} in {disease}",
                year=2023
            )
            
            doc_card.disease = disease
            doc_card.intervention = intervention
            doc_card.study_type = trial_context.get('study_type', 'RCT')
            doc_card.venue = "Clinical Trial"
            
            documents.append(doc_card)
        
        return documents
    
    def _get_standardized_doc_id(self, doc: Document) -> str:
        """Get standardized doc_id format per docs/ids.md"""
        return get_standardized_doc_id(doc)
    
    def _get_raw_document_text(self, doc_id: str) -> str:
        """Get raw text content from document using runtime generation."""
        try:
            # Import here to avoid circular imports
            from ..runtime_text.text_cache import DocumentTextCache
            
            # Initialize cache (will be reused across calls)
            if not hasattr(self, '_text_cache'):
                self._text_cache = DocumentTextCache()
            
            # Use async method in sync context
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're already in an async context, we need to handle this differently
                    # Fall back to synchronous method
                    return self._get_raw_document_text_fallback(doc_id)
                else:
                    return loop.run_until_complete(self._text_cache.get_document_text(doc_id, prefer_fulltext=True))
            except RuntimeError:
                # No event loop, create one
                return asyncio.run(self._text_cache.get_document_text(doc_id, prefer_fulltext=True))
                    
        except Exception as e:
            logger.error(f"Error getting raw text for {doc_id}: {e}")
            # Fall back to synchronous method
            return self._get_raw_document_text_fallback(doc_id)
    
    def _get_abstract_for_prioritization(self, doc_id: str) -> str:
        """Get abstract text for prioritization purposes (runtime only, not persisted)."""
        try:
            with get_session() as session:
                # Use shared utility to get document text
                text = get_document_text(session, doc_id, prefer_fulltext=False)
                if text:
                    logger.debug(f"Retrieved {len(text)} characters of abstract for prioritization")
                return text
                    
        except Exception as e:
            logger.error(f"Error getting abstract for prioritization for {doc_id}: {e}")
            return ""
    
    def _get_raw_document_text_fallback(self, doc_id: str) -> str:
        """Fallback method for getting document text (original implementation)."""
        try:
            with get_session() as session:
                # Use shared utility to get document text
                text = get_document_text(session, doc_id, prefer_fulltext=True)
                if text:
                    logger.info(f"Retrieved {len(text)} characters of text for LLM processing")
                return text
                    
        except Exception as e:
            logger.error(f"Error getting raw text for {doc_id}: {e}")
            return ""
    
    def validate_fulltext_availability(self, trial_context: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate that adequate full text is available for study card generation.
        
        Args:
            trial_context: Trial context with trial_id and nct_id
            
        Returns:
            Tuple of (has_adequate_fulltext, issues)
        """
        issues = []
        
        try:
            with get_session() as session:
                # Get trial information
                trial_id = trial_context.get('trial_id')
                nct_id = trial_context.get('nct_id')
                
                # Find documents linked to this trial
                linked_docs = []
                
                if trial_id:
                    # Convert to int if needed
                    trial_id_int = None
                    try:
                        trial_id_int = int(trial_id) if isinstance(trial_id, str) else trial_id
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert trial_id '{trial_id}' to integer")
                    
                    if trial_id_int is not None:
                        linked_docs = session.query(Document).filter(
                            Document.trial_id == trial_id_int
                        ).all()
                
                # Fallback to NCT ID lookup
                if not linked_docs and nct_id:
                    linked_docs = session.query(Document).filter(Document.nct_id == nct_id).all()
                    
                    # NCT ID lookup is already handled above
                
                if not linked_docs:
                    issues.append("No documents found linked to trial")
                    return False, issues
                
                # Check for adequate full text
                adequate_fulltext_count = 0
                total_docs = len(linked_docs)
                
                for doc in linked_docs:
                    doc_text = session.query(DocumentText).filter(
                        DocumentText.doc_id == doc.doc_id
                    ).first()
                    
                    if doc_text:
                        # Check for substantial fulltext
                        if hasattr(doc_text, 'fulltext_text') and doc_text.fulltext_text:
                            if len(doc_text.fulltext_text) >= 1500:
                                adequate_fulltext_count += 1
                        
                        # Note: Using document_text table for text content
                
                # Validation criteria
                if adequate_fulltext_count == 0:
                    issues.append("No documents with adequate full text (>1500 chars) found")
                elif adequate_fulltext_count < max(1, total_docs // 2):
                    issues.append(f"Insufficient full text coverage: {adequate_fulltext_count}/{total_docs} documents have adequate full text")
                
                logger.info(f"Full text validation: {adequate_fulltext_count}/{total_docs} documents have adequate full text")
                return len(issues) == 0, issues
                
        except Exception as e:
            issues.append(f"Full text validation failed: {e}")
            logger.error(f"Error validating full text availability: {e}")
            return False, issues
    
    
    def _add_provenance(self, item, inputs):
        """Add provenance information."""
        return item
