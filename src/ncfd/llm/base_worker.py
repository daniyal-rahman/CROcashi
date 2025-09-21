"""
Base LLM Worker Class

Provides LLM functionality with modular provider support and content generation patterns.
Consolidates BaseLLMWorker and BaseLLMGenerator into a single, comprehensive class.
"""

from typing import Dict, Any, Optional, List, Tuple
import asyncio
import logging
from abc import ABC, abstractmethod

from .factory import LLMProviderFactory
from .models import LLMRequest, LLMResponse, LLMError, LLMMessage, LLMGenerationConfig, LLMSchema


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
        
        # Create schema if json_schema is provided
        schema = None
        if json_schema:
            schema = LLMSchema(json_schema=json_schema, force=True)
        
        # Create request
        request = LLMRequest(
            model=getattr(self.llm_provider, 'model_name', 'unknown'),
            messages=message_list,
            generation_config=generation_config,
            schema=schema,
            tools=tools,
            tool_choice=tool_choice
        )
        
        # Log the request
        model_name = getattr(self.llm_provider, 'model_name', 'unknown')
        self.logger.info(f"🚀 Starting LLM call - Worker: {self.__class__.__name__}, Provider: {self.llm_provider.provider_name}, Model: {model_name}")
        
        # Make the call
        try:
            response = await self.llm_provider.complete(request)
            self.logger.info(f"✅ LLM call completed - Tokens: {response.usage.total_tokens if response.usage else 'unknown'}")
            return response
        except Exception as e:
            self.logger.error(f"❌ LLM call failed: {e}")
            raise


class BaseLLMGenerator(BaseLLMWorker, ABC):
    """Base class for LLM generators with content generation patterns and retry logic."""
    
    def __init__(self, name: str, version: str = "1.0.0", llm_config: Optional[Dict[str, Any]] = None):
        super().__init__(name, version, llm_config)
    
    async def _execute_with_retry(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Any]]:
        """
        Execute LLM generation with single robust attempt.
        
        Returns:
            Tuple of (data_dict, field_quotes_list)
        """
        try:
            # Use the standard prompt (now with complete JSON examples and structured output)
            prompt = self._build_standard_prompt(doc_text, doc_id, trial_context)
            
            self.logger.info(f"Making LLM call for {self.name} extraction")
            
            result = await self._extract_with_llm(doc_text, trial_context, prompt)
            self.logger.info(f"LLM extraction result keys: {list(result.keys())}")
            
            data_dict = result.get(self._get_data_key(), {})
            field_quotes = []
            
            # Handle case where LLM returns field_quotes as a single number instead of a list
            raw_field_quotes = result.get("field_quotes", [])
            if not isinstance(raw_field_quotes, list):
                self.logger.warning(f"LLM returned field_quotes as {type(raw_field_quotes)} instead of list: {raw_field_quotes}")
                raw_field_quotes = []
            
            for quote_data in raw_field_quotes:
                self.logger.debug(f"Processing quote_data: {quote_data}")
                from ..extract.models.evidence_field import EvidenceField
                
                # Validate that quote_data is a dictionary
                if not isinstance(quote_data, dict):
                    self.logger.error(f"Quote data is not a dictionary, got {type(quote_data)}: {quote_data}")
                    self.logger.error("This indicates the LLM returned malformed JSON with numbers instead of quote objects.")
                    continue
                
                # Ensure evidence_quote is a string
                evidence_quote = quote_data.get("evidence_quote", "")
                if not isinstance(evidence_quote, str):
                    evidence_quote = str(evidence_quote) if evidence_quote is not None else ""
                
                field_quotes.append(EvidenceField(
                    field_name=quote_data.get("field_name", ""),
                    value=quote_data.get("value"),
                    evidence_quote=evidence_quote,
                    confidence=quote_data.get("confidence", 0.8)
                ))
            
            self.logger.info(f"Generated {len(field_quotes)} field quotes")
            
            # Check if we have meaningful data
            has_meaningful_data = any([
                data_dict.get("design_archetype"),
                data_dict.get("primary_endpoint"),
                data_dict.get("analysis_set"),
                data_dict.get("population_description"),
                data_dict.get("results"),
                data_dict.get("primary_endpoint_results")
            ])
            
            if not has_meaningful_data:
                self.logger.warning(f"LLM returned no meaningful {self.name} data - this may indicate document has no relevant information")
                data_dict = {}
            
            if len(field_quotes) == 0:
                self.logger.warning("LLM returned no field_quotes - evidence extraction may be incomplete")
            
            return data_dict, field_quotes
                
        except Exception as e:
            self.logger.error(f"{self.name} generation failed: {e}")
            raise ValueError(f"LLM {self.name} extraction failed: {str(e)}")
    
    @abstractmethod
    def _get_data_key(self) -> str:
        """Return the key for the main data in the LLM response."""
        pass
    
    @abstractmethod
    def _build_standard_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build the standard prompt for extraction."""
        pass
    
    @abstractmethod
    async def _extract_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Extract data using LLM with the given prompt."""
        pass