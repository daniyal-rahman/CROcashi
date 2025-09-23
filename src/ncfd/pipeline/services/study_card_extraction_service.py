"""
Study Card Extraction Service for Study Card Pipeline.

Handles LLM-based study card extraction from prioritized documents.
This service extracts the study card generation logic from the main pipeline.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ncfd.extract.generators import LLMStudyCardExtractor
from ncfd.llm.base_worker import BaseLLMWorker

logger = logging.getLogger(__name__)


@dataclass
class StudyCardExtractionResult:
    """Result of study card extraction."""
    study_cards: List[Dict[str, Any]]
    total_documents_processed: int
    successful_extractions: int
    failed_extractions: int
    extraction_errors: List[str]


class StudyCardExtractionService:
    """
    Service for extracting study cards from documents using LLM.
    
    This service handles:
    - LLM-based study card extraction
    - Batch processing of documents
    - Error handling and retry logic
    - Result validation and formatting
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the study card extraction service.
        
        Args:
            config: Configuration dictionary with extraction settings
        """
        self.config = config
        self.extraction_config = config.get('study_card_extraction', {})
        
        # Initialize LLM extractor
        self.llm_extractor = LLMStudyCardExtractor()
        
        # Configuration values
        self.batch_size = self.extraction_config.get('batch_size', 5)
        self.max_retries = self.extraction_config.get('max_retries', 3)
        self.timeout_seconds = self.extraction_config.get('timeout_seconds', 300)
    
    async def extract_study_cards(
        self, 
        documents: List[Dict[str, Any]], 
        trial_id: str,
        entity_pack: Optional[Dict[str, Any]] = None
    ) -> StudyCardExtractionResult:
        """
        Extract study cards from documents using LLM.
        
        Args:
            documents: List of prioritized documents to process
            trial_id: Trial ID for context
            entity_pack: Entity pack for context
            
        Returns:
            StudyCardExtractionResult with extracted study cards
        """
        logger.info(f"Extracting study cards from {len(documents)} documents for trial {trial_id}")
        
        if not documents:
            return StudyCardExtractionResult(
                study_cards=[],
                total_documents_processed=0,
                successful_extractions=0,
                failed_extractions=0,
                extraction_errors=[]
            )
        
        study_cards = []
        extraction_errors = []
        successful_extractions = 0
        failed_extractions = 0
        
        # Process documents in batches
        for i in range(0, len(documents), self.batch_size):
            batch = documents[i:i + self.batch_size]
            logger.info(f"Processing batch {i//self.batch_size + 1} with {len(batch)} documents")
            
            # Process batch
            batch_result = await self._process_batch(batch, trial_id, entity_pack)
            
            # Collect results
            study_cards.extend(batch_result['study_cards'])
            extraction_errors.extend(batch_result['errors'])
            successful_extractions += batch_result['successful']
            failed_extractions += batch_result['failed']
        
        logger.info(f"Study card extraction completed: {successful_extractions} successful, {failed_extractions} failed")
        
        return StudyCardExtractionResult(
            study_cards=study_cards,
            total_documents_processed=len(documents),
            successful_extractions=successful_extractions,
            failed_extractions=failed_extractions,
            extraction_errors=extraction_errors
        )
    
    async def _process_batch(
        self, 
        documents: List[Dict[str, Any]], 
        trial_id: str,
        entity_pack: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a batch of documents for study card extraction."""
        study_cards = []
        errors = []
        successful = 0
        failed = 0
        
        for doc in documents:
            try:
                # Extract study card from document
                study_card = await self._extract_single_study_card(doc, trial_id, entity_pack)
                
                if study_card:
                    study_cards.append(study_card)
                    successful += 1
                else:
                    failed += 1
                    errors.append(f"Failed to extract study card from document {doc.doc_id if hasattr(doc, 'doc_id') else doc.get('doc_id', 'unknown')}")
                    
            except Exception as e:
                failed += 1
                error_msg = f"Error extracting study card from document {doc.doc_id if hasattr(doc, 'doc_id') else doc.get('doc_id', 'unknown')}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            'study_cards': study_cards,
            'errors': errors,
            'successful': successful,
            'failed': failed
        }
    
    async def _extract_single_study_card(
        self, 
        document: Dict[str, Any], 
        trial_id: str,
        entity_pack: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Extract a single study card from a document."""
        try:
            # Prepare document text for extraction
            document_text = self._prepare_document_text(document)
            
            if not document_text:
                logger.warning(f"No text available for document {document.doc_id if hasattr(document, 'doc_id') else document.get('doc_id', 'unknown')}")
                return None
            
            # Extract study card using LLM
            inputs = {
                "raw_doc_text": document_text,
                "doc_id": document.doc_id if hasattr(document, 'doc_id') else document.get('doc_id', 'unknown'),
                "trial_context": {
                    "trial_id": trial_id,
                    "entity_pack": entity_pack
                }
            }
            
            result = await self.llm_extractor.process(inputs)
            
            if result.get("success", False):
                study_card = result.get("study_card")
            else:
                logger.error(f"Study card extraction failed: {result.get('error_message', 'Unknown error')}")
                study_card = None
            
            if study_card:
                # Convert StudyCard object to dictionary for metadata addition
                if hasattr(study_card, '__dict__'):
                    # It's a SQLAlchemy model or dataclass
                    study_card_dict = {
                        'doc_id': getattr(study_card, 'doc_id', None),
                        'design_archetype': getattr(study_card, 'design_archetype', None),
                        'is_blinded': getattr(study_card, 'is_blinded', None),
                        'analysis_set': getattr(study_card, 'analysis_set', None),
                        'population_description': getattr(study_card, 'population_description', None),
                        'stratification_factors': getattr(study_card, 'stratification_factors', []),
                        'covariate_adjustment': getattr(study_card, 'covariate_adjustment', []),
                        'primary_endpoint': getattr(study_card, 'primary_endpoint', None),
                        'secondary_endpoints': getattr(study_card, 'secondary_endpoints', []),
                        'summary_measure': getattr(study_card, 'summary_measure', None),
                        'alpha_level': getattr(study_card, 'alpha_level', None),
                        'is_one_sided': getattr(study_card, 'is_one_sided', None),
                        'multiplicity_adjustment': getattr(study_card, 'multiplicity_adjustment', None),
                        'sample_size_reassessment': getattr(study_card, 'sample_size_reassessment', None),
                        'interim_looks': getattr(study_card, 'interim_looks', []),
                        'interim_timing': getattr(study_card, 'interim_timing', None),
                        'spending_function': getattr(study_card, 'spending_function', None),
                        'stop_rules': getattr(study_card, 'stop_rules', []),
                        'missingness_assumption': getattr(study_card, 'missingness_assumption', None),
                        'missingness_pattern': getattr(study_card, 'missingness_pattern', None),
                        'imputation_method': getattr(study_card, 'imputation_method', None),
                        'estimand': getattr(study_card, 'estimand', None),
                        'intercurrent_events_policy': getattr(study_card, 'intercurrent_events_policy', None),
                        'endpoint_ascertainment': getattr(study_card, 'endpoint_ascertainment', None),
                        'assessment_interval': getattr(study_card, 'assessment_interval', None),
                        'adjudication_committee': getattr(study_card, 'adjudication_committee', None),
                        'summary_text': getattr(study_card, 'summary_text', None),
                        'risks_text': getattr(study_card, 'risks_text', None),
                        'methods_text': getattr(study_card, 'methods_text', None),
                        'gates_json': getattr(study_card, 'gates_json', {}),
                        'p_fail': getattr(study_card, 'p_fail', None),
                        'model_name': getattr(study_card, 'model_name', None),
                        'authored_by': getattr(study_card, 'authored_by', None)
                    }
                else:
                    # It's already a dictionary
                    study_card_dict = study_card.copy()
                
                # Add metadata
                study_card_dict['trial_id'] = trial_id
                study_card_dict['document_id'] = document.doc_id if hasattr(document, 'doc_id') else document.get('doc_id', 'unknown')
                study_card_dict['extraction_timestamp'] = self._get_current_timestamp()
                
                return study_card_dict
            
            return None
            
        except Exception as e:
            logger.error(f"Error in study card extraction for document {document.doc_id if hasattr(document, 'doc_id') else document.get('doc_id', 'unknown')}: {e}")
            return None
    
    def _prepare_document_text(self, document: Dict[str, Any]) -> str:
        """Prepare document text for LLM processing."""
        # Get document ID
        if isinstance(document, dict):
            doc_id = document.get('doc_id', 'unknown')
        else:
            # DocumentCard object
            doc_id = getattr(document, 'doc_id', 'unknown')
        
        # Retrieve text from database using the proper method
        try:
            from ncfd.db.session import session_scope
            from ncfd.extract.utils.document_utils import get_document_text
            
            with session_scope() as session:
                text = get_document_text(session, str(doc_id), prefer_fulltext=True)
                
                if not text:
                    logger.warning(f"No text found in database for document {doc_id}")
                    return ""
                
                # Truncate if too long (LLM context limits)
                max_length = self.extraction_config.get('max_text_length', 8000)
                if len(text) > max_length:
                    text = text[:max_length]
                    logger.info(f"Truncated document {doc_id} text to {max_length} characters")
                
                return text
                
        except Exception as e:
            logger.error(f"Error retrieving text for document {doc_id}: {e}")
            return ""
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp as string."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
