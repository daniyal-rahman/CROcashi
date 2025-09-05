"""
OpenAI Provider Implementation

Handles OpenAI API calls with proper request/response transformation.
Supports chat completions, function calling, and structured output.
"""

import os
import json
import time
from typing import Dict, Any, Optional, AsyncIterator, List
import asyncio
import aiohttp
from openai import OpenAI, AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessage

from ..base_provider import BaseLLMProvider
from ..models import (
    LLMRequest, LLMResponse, LLMMessage, LLMTool, LLMToolCall,
    LLMUsage, LLMProviderError, LLMValidationError
)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__("openai", config)
        
        # Get API credentials
        self.api_key = os.getenv(config.get("api_key_env", "OPENAI_API_KEY"))
        if not self.api_key:
            raise LLMProviderError(
                f"OpenAI API key not found in environment variable {config.get('api_key_env', 'OPENAI_API_KEY')}",
                provider="openai"
            )
        
        # Optional base URL override
        base_url = None
        if config.get("base_url_env"):
            base_url = os.getenv(config["base_url_env"])
        
        # Optional organization ID
        organization = None
        if config.get("organization_env"):
            organization = os.getenv(config["organization_env"])
        
        # Initialize clients
        client_kwargs = {"api_key": self.api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        if organization:
            client_kwargs["organization"] = organization
            
        self.client = OpenAI(**client_kwargs)
        self.async_client = AsyncOpenAI(**client_kwargs)
        
        # Model capabilities
        self.model_capabilities = {
            "gpt-4o": {
                "json_output": True,
                "function_calling": True,
                "web_search": False,
                "structured_output": True
            },
            "gpt-4": {
                "json_output": True,
                "function_calling": True,
                "web_search": False,
                "structured_output": True
            },
            "gpt-3.5-turbo": {
                "json_output": True,
                "function_calling": True,
                "web_search": False,
                "structured_output": False
            },
            "gpt-5-mini": {
                "json_output": True,
                "function_calling": False,
                "web_search": True,
                "structured_output": True
            }
        }
        
        self.logger.info(f"OpenAI provider initialized with base_url={base_url}")
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Complete an LLM request using OpenAI."""
        self._check_rate_limit()
        
        # Validate request
        self.validate_request(request)
        
        start_time = time.time()
        
        try:
            # Transform request to OpenAI format
            openai_request = self._transform_request(request)
            
            # Make API call
            if self._should_use_responses_api(request.model):
                response = await self._call_responses_api(openai_request, request)
            else:
                response = await self.async_client.chat.completions.create(**openai_request)
            
            # Transform response
            llm_response = self._transform_response(response, request, time.time() - start_time)
            
            # Track metrics
            self._track_request(request, llm_response)
            
            return llm_response
            
        except Exception as e:
            self._track_request(request, error=e)
            raise LLMProviderError(f"OpenAI API call failed: {e}", provider="openai", original_error=e)
    
    async def stream_complete(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream completion using OpenAI."""
        self._check_rate_limit()
        self.validate_request(request)
        
        try:
            openai_request = self._transform_request(request)
            openai_request["stream"] = True
            
            async with self.async_client.chat.completions.create(**openai_request) as stream:
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                        
        except Exception as e:
            self._track_request(request, error=e)
            raise LLMProviderError(f"OpenAI streaming failed: {e}", provider="openai", original_error=e)
    
    def validate_request(self, request: LLMRequest) -> bool:
        """Validate request for OpenAI."""
        if not request.model:
            raise LLMValidationError("Model is required", provider="openai")
        
        if not request.messages:
            raise LLMValidationError("Messages are required", provider="openai")
        
        # Check if model supports requested features
        capabilities = self.get_model_capabilities(request.model)
        
        if request.schema and not capabilities.get("json_output", False):
            raise LLMValidationError(
                f"Model {request.model} does not support structured JSON output",
                provider="openai"
            )
        
        if request.tools and not capabilities.get("function_calling", False):
            raise LLMValidationError(
                f"Model {request.model} does not support function calling",
                provider="openai"
            )
        
        return True
    
    def get_model_capabilities(self, model: str) -> Dict[str, bool]:
        """Get capabilities for OpenAI model."""
        return self.model_capabilities.get(model, {
            "json_output": False,
            "function_calling": False,
            "web_search": False,
            "structured_output": False
        })
    
    def _transform_request(self, request: LLMRequest) -> Dict[str, Any]:
        """Transform LLMRequest to OpenAI format."""
        openai_request = {
            "model": request.model,
            "messages": self._transform_messages(request),
            "max_tokens": request.generation_config.max_tokens,
            "temperature": request.generation_config.temperature,
            "top_p": request.generation_config.top_p,
            "stream": request.stream
        }
        
        # Add stop sequences
        if request.generation_config.stop_sequences:
            openai_request["stop"] = request.generation_config.stop_sequences
        
        # Handle structured output
        if request.schema and request.schema.json_schema:
            if request.schema.force:
                # Use structured output
                openai_request["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "schema": request.schema.json_schema,
                        "strict": True
                    }
                }
            else:
                # Use basic JSON mode
                openai_request["response_format"] = {"type": "json_object"}
        
        # Handle tools/functions
        if request.tools:
            openai_request["tools"] = self._transform_tools(request.tools)
            
            if request.tool_choice:
                if isinstance(request.tool_choice, str):
                    if request.tool_choice == "none":
                        openai_request["tool_choice"] = "none"
                    elif request.tool_choice == "auto":
                        openai_request["tool_choice"] = "auto"
                    else:
                        # Specific tool name
                        openai_request["tool_choice"] = {
                            "type": "function",
                            "function": {"name": request.tool_choice}
                        }
                else:
                    openai_request["tool_choice"] = request.tool_choice
        
        return openai_request
    
    def _transform_messages(self, request: LLMRequest) -> List[Dict[str, Any]]:
        """Transform messages to OpenAI format."""
        messages = []
        
        # Add system message if present
        if request.system:
            messages.append({
                "role": "system",
                "content": request.system
            })
        
        # Add conversation messages
        for msg in request.messages:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        return messages
    
    def _transform_tools(self, tools: List[LLMTool]) -> List[Dict[str, Any]]:
        """Transform tools to OpenAI format."""
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            })
        return openai_tools
    
    def _transform_response(self, response: ChatCompletion, request: LLMRequest, response_time: float) -> LLMResponse:
        """Transform OpenAI response to LLMResponse."""
        choice = response.choices[0]
        message = choice.message
        
        # Extract content
        content = message.content or ""
        
        # Extract tool calls
        tool_calls = None
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                tool_calls.append(LLMToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments)
                ))
        
        # Create usage info
        usage = LLMUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens
        ) if response.usage else LLMUsage(0, 0, 0)
        
        return LLMResponse(
            content=content,
            model=response.model,
            provider="openai",
            usage=usage,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            response_time=response_time,
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else None
        )
    
    def _should_use_responses_api(self, model: str) -> bool:
        """Check if we should use the newer Responses API for this model."""
        return "gpt-5" in model.lower()
    
    async def _call_responses_api(self, openai_request: Dict[str, Any], request: LLMRequest) -> ChatCompletion:
        """Call the newer OpenAI Responses API for GPT-5 models."""
        # Transform to responses API format
        responses_request = {
            "model": openai_request["model"],
            "input": openai_request["messages"]
        }
        
        # Add web search tools for GPT-5
        if "gpt-5" in request.model.lower():
            responses_request["tools"] = [{"type": "web_search_preview"}]
        
        try:
            response = self.client.responses.create(**responses_request)
            
            # Transform responses API response to chat completion format
            # This is a simplified transformation - may need adjustment based on actual API
            return ChatCompletion(
                id=getattr(response, 'id', 'resp_unknown'),
                object="chat.completion",
                created=int(time.time()),
                model=request.model,
                choices=[{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response.output_text if hasattr(response, 'output_text') else str(response)
                    },
                    "finish_reason": "stop"
                }],
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            )
            
        except AttributeError:
            # Fallback to regular chat completions if responses API not available
            self.logger.warning(f"Responses API not available for {request.model}, falling back to chat completions")
            return await self.async_client.chat.completions.create(**openai_request)
