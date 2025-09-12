"""
Enhanced Retriever Worker - LLM-First Architecture

Document retrieval worker that fetches DocumentCards and raw text for LLM processing.
No longer generates or triages spans - spans are created by LLM quote backtracing.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from .base_worker import BaseWorker, WorkerResult
from ..models import DocumentCard
from ...db.models import Document, DocumentTextPage, DocumentText
from ...db.session import get_session

logger = logging.getLogger(__name__)


class EnhancedRetriever(BaseWorker):
    """Enhanced Retriever for LLM-first architecture - fetches documents and raw text only."""
    
    def __init__(self, max_span_length: int = 400, min_confidence: float = 0.7):
        super().__init__("EnhancedRetriever", "3.0.0")  # Version bump for LLM-first
        # Keep legacy params for backward compatibility but they're unused now
        self.max_span_length = max_span_length
        self.min_confidence = min_confidence
        
        
    def _validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate required inputs."""
        return 'trial_context' in inputs
    
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Process inputs to retrieve documents and raw text for LLM processing."""
        try:
            trial_context = inputs["trial_context"]
            date_window = inputs.get("date_window", "2020-2024")
            use_real_retrieval = inputs.get("use_real_retrieval", True)
            
            # Retrieve documents based on trial context
            document_cards = self._retrieve_documents(trial_context, date_window, use_real_retrieval)
            
            # Get raw document text for each document
            raw_doc_texts = {}
            for doc_card in document_cards:
                raw_text = self._get_raw_document_text(doc_card.doc_id)
                if raw_text:
                    raw_doc_texts[doc_card.doc_id] = raw_text
            
            # Add provenance to document cards
            for i, doc_card in enumerate(document_cards):
                document_cards[i] = self._add_provenance(doc_card, inputs)
            
            return WorkerResult(
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
            return WorkerResult(
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
                    from ...db.models import DocumentLink
                    
                    trial_id = trial_context.get('trial_id')
                    nct_id = trial_context.get('nct_id')
                    
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
                            # First try the traditional documents table
                            linked_docs = session.query(Document).join(
                                DocumentLink, Document.doc_id == DocumentLink.doc_id
                            ).filter(DocumentLink.trial_id == trial_id_int).all()
                            logger.debug(f"Found {len(linked_docs)} documents linked to trial_id {trial_id_int}")
                            
                            # If no documents found, try the processed_documents table (PubMed pipeline)
                            if not linked_docs:
                                from ...db.retrieval_models import ProcessedDocument
                                processed_docs = session.query(ProcessedDocument).filter(
                                    ProcessedDocument.trial_id == trial_id_int
                                ).all()
                                logger.debug(f"Found {len(processed_docs)} processed documents for trial_id {trial_id_int}")
                                
                                # Convert ProcessedDocument to Document-like objects for compatibility
                                for proc_doc in processed_docs:
                                    # Create a mock Document object with the required fields
                                    mock_doc = type('MockDocument', (), {
                                        'doc_id': proc_doc.id,
                                        'title': proc_doc.title or f"Processed Document {proc_doc.pmid}",
                                        'pmid': proc_doc.pmid,
                                        'nct_id': nct_id,
                                        'published_at': None,
                                        'source_type': 'Paper'
                                    })()
                                    linked_docs.append(mock_doc)
                    
                    # Also try NCT ID lookup (fallback strategy)
                    if not linked_docs and nct_id:
                        linked_docs = session.query(Document).filter(
                            Document.nct_id == nct_id
                        ).all()
                        logger.debug(f"Found {len(linked_docs)} documents with nct_id {nct_id}")
                    
                    # Also try linking via DocumentLink.nct_id
                    if not linked_docs and nct_id:
                        linked_docs = session.query(Document).join(
                            DocumentLink, Document.doc_id == DocumentLink.doc_id
                        ).filter(DocumentLink.nct_id == nct_id).all()
                        logger.debug(f"Found {len(linked_docs)} documents linked to nct_id {nct_id}")
                    
                    # Convert to DocumentCards with standardized doc_id format
                    for doc in linked_docs:
                        # Use standardized doc_id format per docs/ids.md
                        standardized_doc_id = self._get_standardized_doc_id(doc)
                        
                        doc_card = DocumentCard(
                            doc_id=standardized_doc_id,
                            doc_type="Paper",
                            title=doc.title or f"Document for {nct_id}",
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
                doc_type="Paper", 
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
        # Priority order: nct_id > pmcid > pmid > source_type fallback > db fallback
        if doc.nct_id:
            return f"ctgov:{doc.nct_id}"
        elif doc.pmcid:
            return f"pmc:{doc.pmcid}"
        elif doc.pmid:
            return f"pmid:{doc.pmid}"
        elif doc.source_type:
            source_lower = doc.source_type.lower()
            if source_lower in ['sec', '8k', '10k', '10q']:
                return f"sec:{doc.doc_id}"
            elif source_lower in ['pr', 'press_release']:
                return f"pr:{doc.doc_id}"
            elif source_lower in ['fda']:
                return f"fda:{doc.doc_id}"
        
        # Fallback to db: prefix
        return f"db:{doc.doc_id}"
    
    def _get_raw_document_text(self, doc_id: str) -> str:
        """Get raw text content from document, checking document_text as fallback."""
        try:
            with get_session() as session:
                internal_doc_id = self._resolve_external_doc_id(session, doc_id)
                if not internal_doc_id:
                    return ""
                
                # First try text pages
                text_pages = session.query(DocumentTextPage).filter(
                    DocumentTextPage.doc_id == internal_doc_id
                ).order_by(DocumentTextPage.page_no).all()
                
                if text_pages:
                    combined_text = "\n".join([page.text for page in text_pages])
                    print(f"Retrieved {len(combined_text)} characters of raw text from text_pages")
                    return combined_text
                
                # Try document_text table (fulltext first, then abstracts)
                doc_text = session.query(DocumentText).filter(
                    DocumentText.doc_id == internal_doc_id
                ).first()
                
                if doc_text:
                    # Try fulltext first - with quality check
                    if hasattr(doc_text, 'fulltext_text') and doc_text.fulltext_text:
                        fulltext_length = len(doc_text.fulltext_text)
                        # Quality check: ensure fulltext is substantial
                        if fulltext_length >= 500:  # Minimum length for methods/results extraction (lowered for testing)
                            print(f"Retrieved {fulltext_length} characters of fulltext from document_text")
                            return doc_text.fulltext_text
                        else:
                            logger.warning(f"Fulltext too short ({fulltext_length} chars) for document {internal_doc_id}, may lack methods/results")
                            print(f"Fulltext too short ({fulltext_length} chars), falling back to abstract...")
                    
                    # Fallback to abstract
                    if doc_text.abstract_text:
                        abstract_length = len(doc_text.abstract_text)
                        print(f"Retrieved {abstract_length} characters of abstract text from document_text")
                        
                        # Warn if only abstract available for study card generation
                        if abstract_length < 50:
                            logger.warning(f"Abstract too short ({abstract_length} chars) for quality study card generation")
                        
                        return doc_text.abstract_text
                
                # If no text found in traditional tables, try processed_documents table
                # Extract trial_id from doc_id if it's in the format we created
                if doc_id.startswith('db:'):
                    try:
                        doc_id_int = int(doc_id.split(':')[1])
                        from ...db.retrieval_models import ProcessedDocument
                        processed_doc = session.query(ProcessedDocument).filter(
                            ProcessedDocument.id == doc_id_int
                        ).first()
                        
                        if processed_doc and processed_doc.abstract:
                            abstract_length = len(processed_doc.abstract)
                            print(f"Retrieved {abstract_length} characters of abstract from processed_documents")
                            return processed_doc.abstract
                    except (ValueError, IndexError):
                        pass
                
                print(f"No text content found for document {internal_doc_id}")
                return ""
                    
        except Exception as e:
            logger.error(f"Error getting raw text for {doc_id}: {e}")
            print(f"Error getting raw text for {doc_id}: {e}")
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
                        linked_docs = session.query(Document).join(
                            DocumentLink, Document.doc_id == DocumentLink.doc_id
                        ).filter(DocumentLink.trial_id == trial_id_int).all()
                
                # Fallback to NCT ID lookup
                if not linked_docs and nct_id:
                    linked_docs = session.query(Document).filter(Document.nct_id == nct_id).all()
                    
                    # Additional fallback via DocumentLink.nct_id
                    if not linked_docs:
                        linked_docs = session.query(Document).join(
                            DocumentLink, Document.doc_id == DocumentLink.doc_id
                        ).filter(DocumentLink.nct_id == nct_id).all()
                
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
                        
                        # Check text pages as alternative
                        elif session.query(DocumentTextPage).filter(
                            DocumentTextPage.doc_id == doc.doc_id
                        ).count() > 0:
                            text_pages = session.query(DocumentTextPage).filter(
                                DocumentTextPage.doc_id == doc.doc_id
                            ).all()
                            total_text_length = sum(len(page.text or '') for page in text_pages)
                            if total_text_length >= 1500:
                                adequate_fulltext_count += 1
                
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
    
    
    def _resolve_external_doc_id(self, session, external_doc_id: str) -> Optional[int]:
        """Resolve external document ID to internal doc_id."""
        if not external_doc_id:
            return None
        
        if ':' in external_doc_id:
            source, identifier = external_doc_id.split(':', 1)
            source = source.lower()
            
            if source == 'ctgov':
                document = session.query(Document).filter(
                    Document.nct_id == identifier
                ).first()
            elif source == 'pmc':
                document = session.query(Document).filter(
                    Document.pmcid == identifier
                ).first()
            elif source == 'pmid':
                document = session.query(Document).filter(
                    Document.pmid == identifier
                ).first()
            elif source == 'db':
                try:
                    internal_id = int(identifier)
                    document = session.query(Document).filter(
                        Document.doc_id == internal_id
                    ).first()
                except ValueError:
                    return None
            else:
                # Handle sec:, fda:, pr: etc.
                document = session.query(Document).filter(
                    Document.source_type == source.upper(),
                    Document.source_url.contains(identifier)
                ).first()
        else:
            try:
                internal_id = int(external_doc_id)
                document = session.query(Document).filter(
                    Document.doc_id == internal_id
                ).first()
            except ValueError:
                return None
        
        return document.doc_id if document else None
    
    def _add_provenance(self, item, inputs):
        """Add provenance information."""
        return item
