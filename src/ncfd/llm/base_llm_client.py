"""
Clean, domain-agnostic LLM client base class.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable, Union
from dataclasses import dataclass

from ..models import LLMRequest, LLMResponse, LLMMessage, LLMSchema, LLMGenerationConfig


@dataclass
class RetryPolicy:
    """Configurable retry policy."""
    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    should_retry: Callable[[Exception], bool] = lambda e: True


class BaseLLMClient(ABC):
    """
    Domain-agnostic LLM client with provider wiring, retries, timeouts, and generic logging.
    """
    
    def __init__(self, name: str, llm_config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.llm_config = llm_config or {}
        self.logger = logging.getLogger(f"ncfd.llm.client.{name}")
        
        # Provider wiring
        self.llm_provider = self._get_provider()
        self.model = self._get_model()
        
        # Configurable policies
        self.retry_policy = self._get_retry_policy()
        self.timeout_sec = self.llm_config.get("timeout_sec", 60)
        self.normalize_messages = self.llm_config.get("normalize_messages", True)
    
    @abstractmethod
    def _get_provider(self):
        """Get the LLM provider instance."""
        pass
    
    @abstractmethod
    def _get_model(self) -> str:
        """Get the model name."""
        pass
    
    def _get_retry_policy(self) -> RetryPolicy:
        """Get retry policy from config."""
        return RetryPolicy(
            max_retries=self.llm_config.get("max_retries", 3),
            base_delay=self.llm_config.get("retry_base_delay", 0.5),
            max_delay=self.llm_config.get("retry_max_delay", 8.0),
            should_retry=self.llm_config.get("should_retry", lambda e: True)
        )
    
    def _normalize_messages(self, messages: List[Union[Dict[str, Any], LLMMessage]]) -> List[LLMMessage]:
        """Normalize messages to LLMMessage format."""
        if not self.normalize_messages:
            return messages
        
        message_list = []
        for msg in messages:
            if isinstance(msg, LLMMessage):
                message_list.append(msg)
            elif isinstance(msg, dict):
                message_list.append(LLMMessage(
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    name=msg.get("name"),
                    tool_call_id=msg.get("tool_call_id"),
                    function_call=msg.get("function_call")
                ))
            else:
                message_list.append(LLMMessage(role="user", content=str(msg)))
        
        return message_list
    
    async def call_llm(
        self,
        messages: List[Union[Dict[str, Any], LLMMessage]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_output: Optional[bool] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Any]] = None,
        tool_choice: Optional[str] = None,
        timeout_sec: Optional[int] = None
    ) -> LLMResponse:
        """
        Make LLM call with retries, timeout, and generic logging.
        """
        # Use provided values or defaults
        temperature = temperature if temperature is not None else self.llm_config.get("temperature", 0.1)
        max_tokens = max_tokens if max_tokens is not None else self.llm_config.get("max_tokens", 2000)
        json_output = json_output if json_output is not None else self.llm_config.get("json_output", None)
        timeout_sec = timeout_sec or self.timeout_sec
        
        # Normalize messages
        message_list = self._normalize_messages(messages)
        
        # Create generation config
        generation_config = LLMGenerationConfig(
            temperature=temperature,
            max_tokens=max_tokens,
            json_output=json_output
        )
        
        # Create schema if provided and not empty
        schema = None
        if json_schema and json_schema != {}:
            force_schema = self.llm_config.get("force_schema", False)
            schema = LLMSchema(json_schema=json_schema, force=force_schema)
        
        # Create request
        request = LLMRequest(
            model=self.model,
            messages=message_list,
            generation_config=generation_config,
            schema=schema,
            tools=tools,
            tool_choice=tool_choice
        )
        
        # Generic logging
        self.logger.info(f"🚀 LLM Request - Client: {self.name}, Provider: {self.llm_provider.provider_name}, Model: {self.model}")
        
        # Make call with retries and timeout
        policy = self.retry_policy
        for attempt in range(policy.max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self.llm_provider.complete(request),
                    timeout=timeout_sec
                )
                
                # Generic success logging
                tokens = response.usage.total_tokens if response.usage else 'unknown'
                self.logger.info(f"✅ LLM Response - Tokens: {tokens}, Latency: {getattr(response, 'latency_ms', 'unknown')}ms")
                return response
                
            except asyncio.TimeoutError:
                error_msg = f"LLM call timed out after {timeout_sec}s"
                if attempt == policy.max_retries:
                    self.logger.error(f"❌ {error_msg} (final attempt)")
                    raise
                self.logger.warning(f"⚠️ {error_msg} (attempt {attempt + 1}/{policy.max_retries + 1})")
                
            except Exception as e:
                if not policy.should_retry(e):
                    self.logger.error(f"❌ LLM call failed (non-retryable): {e}")
                    raise
                
                if attempt == policy.max_retries:
                    self.logger.error(f"❌ LLM call failed after {policy.max_retries} retries: {e}")
                    raise
                
                delay = min(policy.max_delay, policy.base_delay * (2 ** attempt))
                self.logger.warning(f"⚠️ LLM call failed (attempt {attempt + 1}/{policy.max_retries + 1}): {e}")
                self.logger.info(f"🔄 Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)
