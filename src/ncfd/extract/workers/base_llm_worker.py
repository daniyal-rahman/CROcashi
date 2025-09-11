"""
Base LLM Worker Class

Extends BaseWorker to provide LLM functionality with modular provider support.
"""

from typing import Dict, Any, Optional
import asyncio
import logging

from .base_worker import BaseWorker, WorkerResult
from ...llm import LLMProviderFactory, LLMRequest, LLMResponse, LLMError
from ...llm.models import LLMMessage, LLMGenerationConfig


class BaseLLMWorker(BaseWorker):
    """Base class for workers that use LLM services."""
    
    def __init__(self, name: str, version: str = "1.0.0", llm_config: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM worker.
        
        Args:
            name: Worker name (used for LLM provider selection)
            version: Worker version
            llm_config: Optional LLM configuration override
        """
        super().__init__(name, version)
        self.logger = logging.getLogger(f"{__name__}.{name}")
        
        # Initialize LLM provider
        self.llm_factory = LLMProviderFactory(llm_config) if llm_config else LLMProviderFactory()
        self.llm_provider = self.llm_factory.create_for_worker(name)
        self.model = self.llm_factory.get_model_for_worker(name)
        
        self.logger.info(f"LLM Worker '{name}' initialized with provider={self.llm_provider.provider_name}, model={self.model}")
    
    async def call_llm(
        self,
        messages: list,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        json_output: bool = False,
        json_schema: Optional[Dict[str, Any]] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[str] = None
    ) -> LLMResponse:
        """
        Make an LLM call with standardized parameters.
        
        Args:
            messages: List of messages (can be strings or message objects)
            system_prompt: Optional system prompt
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            json_output: Whether to request JSON output
            json_schema: Optional JSON schema for structured output
            tools: Optional list of tools/functions
            tool_choice: Tool choice strategy
            
        Returns:
            LLM response
            
        Raises:
            LLMError: If the LLM call fails
        """
        try:
            # Convert messages to LLMMessage format
            llm_messages = []
            for msg in messages:
                if isinstance(msg, str):
                    llm_messages.append(LLMMessage(role="user", content=msg))
                elif isinstance(msg, dict):
                    llm_messages.append(LLMMessage(
                        role=msg.get("role", "user"),
                        content=msg.get("content", "")
                    ))
                else:
                    llm_messages.append(msg)
            
            # Create request
            request = LLMRequest(
                model=self.model,
                messages=llm_messages,
                system=system_prompt,
                generation_config=LLMGenerationConfig(
                    max_tokens=max_tokens,
                    temperature=temperature
                )
            )
            
            # Add structured output if requested
            if json_output or json_schema:
                from ...llm.models import LLMSchema
                request.schema = LLMSchema(
                    json_schema=json_schema,
                    force=True
                )
            
            # Add tools if provided
            if tools:
                from ...llm.models import LLMTool
                llm_tools = []
                for tool in tools:
                    if isinstance(tool, dict):
                        llm_tools.append(LLMTool(
                            name=tool["name"],
                            description=tool.get("description", ""),
                            parameters=tool.get("parameters", {})
                        ))
                    else:
                        llm_tools.append(tool)
                request.tools = llm_tools
                request.tool_choice = tool_choice
            
            # Make the call
            model_name = getattr(self.llm_provider, 'model_name', 'unknown')
            self.logger.info(f"🚀 Starting LLM call - Worker: {self.__class__.__name__}, Provider: {self.llm_provider.provider_name}, Model: {model_name}")
            self.logger.debug(f"LLM request details - Messages: {len(request.messages)}, Tools: {len(request.tools) if request.tools else 0}")
            
            self.logger.debug(f"🔄 Calling llm_provider.complete()...")
            response = await self.llm_provider.complete(request)
            self.logger.debug(f"✅ llm_provider.complete() returned")
            
            self.logger.info(f"✅ LLM call completed - Worker: {self.__class__.__name__}, Tokens: {response.usage.total_tokens}, Time: {response.response_time:.2f}s")
            return response
            
        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            raise LLMError(f"LLM call failed: {e}", provider=self.llm_provider.provider_name, original_error=e)
    
    def call_llm_sync(self, *args, **kwargs) -> LLMResponse:
        """Synchronous wrapper for LLM calls."""
        return asyncio.run(self.call_llm(*args, **kwargs))
    
    def get_llm_stats(self) -> Dict[str, Any]:
        """Get LLM provider statistics."""
        return self.llm_provider.get_stats()
    
    def reset_llm_stats(self) -> None:
        """Reset LLM provider statistics."""
        self.llm_provider.reset_stats()
