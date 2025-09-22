"""
Base LLM Worker Class

Provides LLM functionality with modular provider support and content generation patterns.
Consolidates BaseLLMWorker and BaseLLMExtractor into a single, comprehensive class.
"""

from typing import Dict, Any, Optional, List, Tuple
import asyncio
import logging
from abc import ABC, abstractmethod

from .base_llm_client import BaseLLMClient
from .factory import LLMProviderFactory
from .models import LLMRequest, LLMResponse, LLMError, LLMMessage, LLMGenerationConfig, LLMSchema
from ..utils.config_manager import get_config_manager
from ..utils.error_handler import get_error_handler, safe_execute


class BaseLLMWorker:
    """Base class for workers that use LLM services with optional content generation patterns."""
    
    def __init__(self, name: str, version: str = "1.0.0", llm_config: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM worker.
        
        Args:
            name: Worker name (used for LLM provider selection)
            version: Worker version
            llm_config: Optional LLM configuration override
        """
        self.name = name
        self.version = version
        self.logger = logging.getLogger(f"{__name__}.{name}")
        
        # Initialize LLM provider
        if llm_config:
            # If custom config provided, create a custom LLMConfig
            from .config import LLMConfig, ProviderConfig, ModelConfig
            from . import load_llm_config
            
            # Load default config and override with custom settings
            default_config = load_llm_config()
            if isinstance(llm_config, dict) and 'workers' in llm_config:
                # Override worker configs
                default_config.workers.update(llm_config['workers'])
            self.llm_factory = LLMProviderFactory(default_config)
        else:
            self.llm_factory = LLMProviderFactory()
        
        self.llm_provider = self.llm_factory.create_for_worker(name)
        self.model = self.llm_factory.get_model_for_worker(name)
        
        # Content generation settings (from config)
        worker_config = self.llm_factory.config.get_worker_config(name)
        self.max_retries = worker_config.get('max_retries', 3)
        self.temperature = worker_config.get('temperature', 0.1)
        self.max_tokens = worker_config.get('max_tokens', 4000)
        self.json_output = worker_config.get('json_output', True)
        
        self.logger.info(f"LLM Worker '{name}' initialized with provider={self.llm_provider.provider_name}, model={self.model}")
    
    async def call_llm(
        self,
        messages: list,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_output: Optional[bool] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[str] = None
    ) -> LLMResponse:
        """
        Call LLM with standardized interface.
        
        Args:
            messages: List of message dictionaries
            system_prompt: Optional system prompt
            temperature: Override default temperature
            max_tokens: Override default max tokens
            json_output: Override default json output setting
            json_schema: Optional JSON schema for structured output
            tools: Optional tools for function calling
            tool_choice: Optional tool choice strategy
            
        Returns:
            LLMResponse object
        """
        # Use provided values or defaults from config
        temperature = temperature if temperature is not None else self.temperature
        max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        json_output = json_output if json_output is not None else self.json_output
        
        # Build message list
        message_list = []
        if system_prompt:
            message_list.append(LLMMessage(role="system", content=system_prompt))
        
        for msg in messages:
            if isinstance(msg, dict):
                message_list.append(LLMMessage(role=msg.get("role", "user"), content=msg.get("content", "")))
            else:
                message_list.append(LLMMessage(role="user", content=str(msg)))
        
        # Create generation config
        generation_config = LLMGenerationConfig(
            temperature=temperature,
            max_tokens=max_tokens,
            json_output=json_output
        )
        
        # Create schema if json_schema is provided and not empty
        schema = None
        if json_schema and json_schema != {}:
            force_schema = getattr(self, 'force_schema', False)
            schema = LLMSchema(json_schema=json_schema, force=force_schema)
        
        # Create request
        request = LLMRequest(
            model=self.model,  # Use the resolved model, not provider.model_name
            messages=message_list,
            generation_config=generation_config,
            schema=schema,
            tools=tools,
            tool_choice=tool_choice
        )
        
        # Log the request  
        self.logger.info(f"🚀 Starting LLM call - Worker: {self.__class__.__name__}, Provider: {self.llm_provider.provider_name}, Model: {self.model}")
        
        # Make the call with retries
        max_retries = getattr(self, 'max_retries', 3)
        base_delay = 0.5
        max_delay = 8.0
        
        for attempt in range(max_retries + 1):
            try:
                timeout_sec = getattr(self, 'timeout_sec', 60)
                response = await asyncio.wait_for(
                    self.llm_provider.complete(request), 
                    timeout=timeout_sec
                )
                self.logger.info(f"✅ LLM call completed - Tokens: {response.usage.total_tokens if response.usage else 'unknown'}")
                return response
            except Exception as e:
                if attempt == max_retries:
                    self.logger.error(f"❌ LLM call failed after {max_retries} retries: {e}")
                    raise
                
                delay = min(max_delay, base_delay * (2 ** attempt))
                self.logger.warning(f"⚠️ LLM call failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
                self.logger.info(f"🔄 Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)


class BaseLLMExtractor(BaseLLMClient, ABC):
    """Base class for document extraction extractors."""
    
    def __init__(self, name: str, llm_config: Optional[Dict[str, Any]] = None):
        super().__init__(name, llm_config)
        self.logger = logging.getLogger(f"ncfd.llm.extractor.{name}")
    
    @abstractmethod
    def _get_data_key(self) -> str:
        """Return the key for the main data in the LLM response."""
        pass
    
    @abstractmethod
    def _get_meaningful_fields(self) -> List[str]:
        """Return the list of fields that indicate meaningful data for this extractor."""
        pass
    
    @abstractmethod
    def _build_extraction_prompt(self, doc_text: str, doc_id: str, context: Dict[str, Any]) -> str:
        """Build the extraction prompt for this specific extractor."""
        pass
    
    @abstractmethod
    def _get_json_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for this extractor's LLM calls."""
        pass
    
    def _parse_field_quotes(self, result: Dict[str, Any]) -> List[Any]:
        """Parse field_quotes from LLM result into EvidenceField objects."""
        from ..extract.models.evidence_field import EvidenceField
        
        field_quotes = []
        raw_field_quotes = result.get("field_quotes", [])
        
        self.logger.info(f"🔍 FIELD QUOTES PROCESSING:")
        self.logger.info(f"   Raw field_quotes count: {len(raw_field_quotes) if isinstance(raw_field_quotes, list) else 'Not a list'}")
        
        if not isinstance(raw_field_quotes, list):
            self.logger.warning(f"LLM returned field_quotes as {type(raw_field_quotes)} instead of list: {raw_field_quotes}")
            raw_field_quotes = []
        
        processed_quotes = 0
        skipped_quotes = 0
        
        for quote_data in raw_field_quotes:
            # Validate that quote_data is a dictionary
            if not isinstance(quote_data, dict):
                self.logger.error(f"Quote data is not a dictionary, got {type(quote_data)}: {quote_data}")
                skipped_quotes += 1
                continue
            
            # Validate field_name is a string
            field_name = quote_data.get("field_name", "")
            if not isinstance(field_name, str):
                self.logger.warning(f"Malformed field_name with non-string value '{field_name}' (type: {type(field_name)}) - skipping quote")
                skipped_quotes += 1
                continue
            
            # Validate and clean evidence_quote
            evidence_quote = quote_data.get("evidence_quote", "")
            if not isinstance(evidence_quote, str):
                if evidence_quote is None:
                    evidence_quote = ""
                elif isinstance(evidence_quote, (int, float)):
                    self.logger.warning(f"Malformed evidence_quote with numeric value '{evidence_quote}' for field '{quote_data.get('field_name', 'unknown')}' - skipping quote")
                    skipped_quotes += 1
                    continue
                else:
                    evidence_quote = str(evidence_quote)
            
            # Additional validation: ensure evidence_quote is not empty or just whitespace
            if not evidence_quote or not evidence_quote.strip():
                self.logger.warning(f"Empty or whitespace-only evidence_quote - skipping quote")
                skipped_quotes += 1
                continue
            
            field_quotes.append(EvidenceField(
                field_name=quote_data.get("field_name", ""),
                value=quote_data.get("value"),
                evidence_quote=evidence_quote,
                confidence=quote_data.get("confidence", 0.8)
            ))
            processed_quotes += 1
        
        self.logger.info(f"🔍 FIELD QUOTES PROCESSING SUMMARY:")
        self.logger.info(f"   Total raw quotes: {len(raw_field_quotes)}")
        self.logger.info(f"   Successfully processed: {processed_quotes}")
        self.logger.info(f"   Skipped: {skipped_quotes}")
        self.logger.info(f"   Final field_quotes count: {len(field_quotes)}")
        
        return field_quotes
    
    def _has_meaningful_data(self, data_dict: Dict[str, Any]) -> bool:
        """Check if data_dict contains meaningful data for this extractor."""
        meaningful_fields = self._get_meaningful_fields()
        
        def _has_value(v):
            return v is not None and not (isinstance(v, str) and v.strip() == "")
        
        has_meaningful = any(_has_value(data_dict.get(field)) for field in meaningful_fields)
        
        self.logger.info(f"🔍 MEANINGFUL DATA CHECK:")
        self.logger.info(f"   Checking fields: {meaningful_fields}")
        self.logger.info(f"   Found meaningful data: {has_meaningful}")
        
        return has_meaningful
    
    def _handle_no_meaningful_data(self, data_dict: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle case where no meaningful data was found."""
        self.logger.warning(f"❌ NO MEANINGFUL DATA FOUND - zeroing out data_dict")
        self.logger.warning(f"LLM returned no meaningful {self.name} data - this may indicate document has no relevant information")
        return {}
    
    async def extract_document(
        self, 
        doc_text: str, 
        doc_id: str, 
        context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Any]]:
        """Extract data from document using LLM with field_quotes parsing."""
        # Build extraction-specific prompt
        prompt = self._build_extraction_prompt(doc_text, doc_id, context)
        
        self.logger.info(f"Making LLM call for {self.name} extraction")
        
        # Make LLM call
        response = await self.call_llm(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
            json_output=True,
            json_schema=self._get_json_schema()
        )
        
        # Parse response
        result = response.content
        self.logger.info(f"🔍 LLM RAW RESPONSE DEBUG:")
        self.logger.info(f"   Type: {type(result)}")
        self.logger.info(f"   Content length: {len(str(result))}")
        
        if isinstance(result, str):
            from ..llm.json_parser import parse_llm_json_response
            parsed_result = parse_llm_json_response(result, expected_fields=[self._get_data_key(), "field_quotes"])
            if parsed_result:
                result = parsed_result
                self.logger.info(f"✅ JSON PARSING SUCCESSFUL:")
                self.logger.info(f"   Parsed keys: {list(result.keys())}")
            else:
                self.logger.error(f"❌ JSON PARSING FAILED:")
                return {}, []
        elif isinstance(result, (int, float)):
            self.logger.error(f"❌ LLM RETURNED NUMBER: {result}")
            return {}, []
        elif not isinstance(result, dict):
            self.logger.error(f"❌ LLM RETURNED UNEXPECTED TYPE {type(result)}: {result}")
            return {}, []
        
        # Extract data and field quotes
        data_dict = result.get(self._get_data_key(), {})
        field_quotes = self._parse_field_quotes(result)
        
        # Check for meaningful data
        if not self._has_meaningful_data(data_dict):
            data_dict = self._handle_no_meaningful_data(data_dict, context)
        
        if len(field_quotes) == 0:
            self.logger.warning("❌ NO FIELD QUOTES FOUND - evidence extraction may be incomplete")
        
        return data_dict, field_quotes