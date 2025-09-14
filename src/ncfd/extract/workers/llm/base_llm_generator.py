"""
Base LLM Generator Class

Provides common functionality for LLM-based generators including:
- Retry logic with progressive prompt simplification
- Common prompt building patterns
- Error handling and logging
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from abc import ABC, abstractmethod

from ..base_llm_worker import BaseLLMWorker

logger = logging.getLogger(__name__)


class BaseLLMGenerator(BaseLLMWorker, ABC):
    """Base class for LLM generators with common retry and prompt logic."""
    
    def __init__(self, name: str, version: str = "1.0.0", llm_config: Optional[Dict[str, Any]] = None):
        super().__init__(name, version, llm_config)
        self.max_retries = 3
    
    async def _execute_with_retry(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Any]]:
        """
        Execute LLM generation with retry logic and progressive prompt simplification.
        
        Returns:
            Tuple of (data_dict, field_quotes_list)
        """
        for attempt in range(self.max_retries):
            try:
                if attempt == 0:
                    # First attempt: Standard prompt
                    prompt = self._build_standard_prompt(doc_text, doc_id, trial_context)
                elif attempt == 1:
                    # Second attempt: Simplified prompt
                    prompt = self._build_simplified_prompt(doc_text, doc_id, trial_context)
                else:
                    # Third attempt: Minimal prompt
                    prompt = self._build_minimal_prompt(doc_text, doc_id, trial_context)
                
                logger.info(f"DEBUG: {self.name} attempt {attempt + 1} - Making LLM call")
                
                result = await self._extract_with_llm(doc_text, trial_context, prompt)
                logger.info(f"DEBUG: LLM extraction result keys: {list(result.keys())}")
                logger.info(f"DEBUG: LLM extraction result field_quotes: {result.get('field_quotes', [])}")
                
                data_dict = result.get(self._get_data_key(), {})
                field_quotes = []
                
                for quote_data in result.get("field_quotes", []):
                    logger.info(f"DEBUG: Processing quote_data: {quote_data}")
                    from ...models.evidence_field import EvidenceField
                    field_quotes.append(EvidenceField(
                        field_name=quote_data.get("field_name", ""),
                        value=quote_data.get("value"),
                        evidence_quote=quote_data.get("evidence_quote", ""),
                        confidence=quote_data.get("confidence", 0.8)
                    ))
                
                return data_dict, field_quotes
                
            except Exception as e:
                logger.warning(f"DEBUG: {self.name} attempt {attempt + 1} failed: {e}")
                if attempt == self.max_retries - 1:
                    logger.error(f"All {self.max_retries} attempts failed for {self.name}")
                    raise
        
        return {}, []
    
    @abstractmethod
    def _get_data_key(self) -> str:
        """Return the key for the main data in the LLM response."""
        pass
    
    @abstractmethod
    def _build_standard_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build the standard prompt for the first attempt."""
        pass
    
    @abstractmethod
    def _build_simplified_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build a simplified prompt for the second attempt."""
        pass
    
    @abstractmethod
    def _build_minimal_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build a minimal prompt for the third attempt."""
        pass
    
    @abstractmethod
    async def _extract_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Extract data using LLM with the given prompt."""
        pass
