"""
Factsheet Extraction Service for Study Card Pipeline.

Handles LLM-based factsheet extraction from prioritized documents.
This service extracts the factsheet generation logic from the main pipeline.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ncfd.extract.generators import LLMFactsheetExtractor

logger = logging.getLogger(__name__)


@dataclass
class FactsheetExtractionResult:
    """Result of factsheet extraction."""
    factsheets: List[Dict[str, Any]]
    total_documents_processed: int
    successful_extractions: int
    failed_extractions: int
    extraction_errors: List[str]


class FactsheetExtractionService:
    """
    Service for extracting factsheets from documents using LLM.
    
    This service handles:
    - LLM-based factsheet extraction
    - Batch processing of documents
    - Error handling and retry logic
    - Result validation and formatting
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the factsheet extraction service.
        
        Args:
            config: Configuration dictionary with extraction settings
        """
        self.config = config
        self.extraction_config = config.get('factsheet_extraction', {})
        
        # Initialize LLM extractor
        self.llm_extractor = LLMFactsheetExtractor()
        
        # Configuration values
        self.batch_size = self.extraction_config.get('batch_size', 5)
        self.max_retries = self.extraction_config.get('max_retries', 3)
        self.timeout_seconds = self.extraction_config.get('timeout_seconds', 300)
    
    async def extract_factsheets(
        self, 
        documents: List[Dict[str, Any]], 
        trial_id: str,
        entity_pack: Optional[Dict[str, Any]] = None
    ) -> FactsheetExtractionResult:
        """
        Extract factsheets from documents using LLM.
        
        Args:
            documents: List of prioritized documents to process
            trial_id: Trial ID for context
            entity_pack: Entity pack for context
            
        Returns:
            FactsheetExtractionResult with extracted factsheets
        """
        logger.info(f"Extracting factsheets from {len(documents)} documents for trial {trial_id}")
        
        if not documents:
            return FactsheetExtractionResult(
                factsheets=[],
                total_documents_processed=0,
                successful_extractions=0,
                failed_extractions=0,
                extraction_errors=[]
            )
        
        factsheets = []
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
            factsheets.extend(batch_result['factsheets'])
            extraction_errors.extend(batch_result['errors'])
            successful_extractions += batch_result['successful']
            failed_extractions += batch_result['failed']
        
        logger.info(f"Factsheet extraction completed: {successful_extractions} successful, {failed_extractions} failed")
        
        return FactsheetExtractionResult(
            factsheets=factsheets,
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
        """Process a batch of documents for factsheet extraction."""
        factsheets = []
        errors = []
        successful = 0
        failed = 0
        
        for doc in documents:
            try:
                # Extract factsheet from document
                factsheet = await self._extract_single_factsheet(doc, trial_id, entity_pack)
                
                if factsheet:
                    factsheets.append(factsheet)
                    successful += 1
                else:
                    failed += 1
                    doc_id = doc.get('doc_id', 'unknown') if isinstance(doc, dict) else (doc.doc_id if hasattr(doc, 'doc_id') else 'unknown')
                    errors.append(f"Failed to extract factsheet from document {doc_id}")
                    
            except Exception as e:
                failed += 1
                doc_id = doc.get('doc_id', 'unknown') if isinstance(doc, dict) else (doc.doc_id if hasattr(doc, 'doc_id') else 'unknown')
                error_msg = f"Error extracting factsheet from document {doc_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            'factsheets': factsheets,
            'errors': errors,
            'successful': successful,
            'failed': failed
        }
    
    async def _extract_single_factsheet(
        self, 
        document: Dict[str, Any], 
        trial_id: str,
        entity_pack: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Extract a single factsheet from a document."""
        try:
            # Prepare document text for extraction
            document_text = self._prepare_document_text(document)
            
            if not document_text:
                doc_id = document.get('doc_id', 'unknown') if isinstance(document, dict) else (document.doc_id if hasattr(document, 'doc_id') else 'unknown')
                logger.warning(f"No text available for document {doc_id}")
                return None
            
            # Extract factsheet using LLM
            doc_id = document.get('doc_id', 'unknown') if isinstance(document, dict) else (document.doc_id if hasattr(document, 'doc_id') else 'unknown')
            inputs = {
                "raw_doc_text": document_text,
                "doc_id": doc_id,
                "trial_context": {
                    "trial_id": trial_id,
                    "entity_pack": entity_pack
                }
            }
            
            result = await self.llm_extractor.process(inputs)
            
            if result.get("success", False):
                factsheet = result.get("factsheet")
            else:
                logger.error(f"Factsheet extraction failed: {result.get('error_message', 'Unknown error')}")
                factsheet = None
            
            if factsheet:
                # Convert Factsheet object to dictionary for metadata addition
                if hasattr(factsheet, '__dict__'):
                    # It's a SQLAlchemy model or dataclass
                    factsheet_dict = {
                        'doc_id': getattr(factsheet, 'doc_id', None),
                        # New JSONB-based fields
                        'study_type': getattr(factsheet, 'study_type', None),
                        'factsheet_sections': getattr(factsheet, 'factsheet_sections', {}),
                        'provenance': getattr(factsheet, 'provenance', {}),
                        'normalized_facts': getattr(factsheet, 'normalized_facts', {}),
                        # Legacy fields for backward compatibility
                        'results': getattr(factsheet, 'results', []),
                        'primary_endpoint_results': getattr(factsheet, 'primary_endpoint_results', None),
                        'secondary_endpoint_results': getattr(factsheet, 'secondary_endpoint_results', []),
                        'safety_results': getattr(factsheet, 'safety_results', []),
                        'primary_analysis_set': getattr(factsheet, 'primary_analysis_set', None),
                        'secondary_analysis_sets': getattr(factsheet, 'secondary_analysis_sets', []),
                        'total_enrolled': getattr(factsheet, 'total_enrolled', None),
                        'completed_primary_endpoint': getattr(factsheet, 'completed_primary_endpoint', None),
                        'dropout_rate': getattr(factsheet, 'dropout_rate', None),
                        'follow_up_completion': getattr(factsheet, 'follow_up_completion', None)
                    }
                else:
                    # It's already a dictionary
                    factsheet_dict = factsheet.copy()
                
                # Add metadata
                factsheet_dict['trial_id'] = trial_id
                factsheet_dict['document_id'] = document.get('doc_id', 'unknown')
                factsheet_dict['extraction_timestamp'] = self._get_current_timestamp()
                
                # Debug logging to see what we're returning
                logger.info(f"🔍 DEBUG: Factsheet extraction result for doc {document.get('doc_id', 'unknown')}:")
                logger.info(f"  study_type: {factsheet_dict.get('study_type')}")
                logger.info(f"  factsheet_sections keys: {list(factsheet_dict.get('factsheet_sections', {}).keys())}")
                logger.info(f"  factsheet_sections content: {factsheet_dict.get('factsheet_sections', {})}")
                logger.info(f"  provenance keys: {list(factsheet_dict.get('provenance', {}).keys())}")
                
                return factsheet_dict
            
            return None
            
        except Exception as e:
            logger.error(f"Error in factsheet extraction for document {document.doc_id if hasattr(document, 'doc_id') else document.get('doc_id', 'unknown')}: {e}")
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
