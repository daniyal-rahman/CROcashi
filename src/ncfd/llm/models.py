"""
Core data models for LLM abstraction layer.

Provides standardized request/response models that work across all providers.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union, Literal
from datetime import datetime
import json


@dataclass
class LLMMessage:
    """Standardized message format."""
    role: Literal["system", "user", "assistant"]
    content: Union[str, List[Dict[str, Any]]]  # String or content blocks
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content
        }


@dataclass
class LLMGenerationConfig:
    """Generation parameters."""
    max_tokens: int = 4000
    temperature: float = 0.1
    top_p: float = 0.95
    top_k: Optional[int] = None
    stop_sequences: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        config = {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p
        }
        if self.top_k is not None:
            config["top_k"] = self.top_k
        if self.stop_sequences:
            config["stop_sequences"] = self.stop_sequences
        return config


@dataclass
class LLMTool:
    """Tool/function definition."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }


@dataclass
class LLMSchema:
    """Schema definition for structured output."""
    kind: Literal["json"] = "json"
    json_schema: Optional[Dict[str, Any]] = None
    force: bool = True  # Force adherence to schema
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "json_schema": self.json_schema,
            "force": self.force
        }


@dataclass
class LLMRequest:
    """Standardized LLM request across all providers."""
    model: str
    messages: List[LLMMessage]
    system: Optional[str] = None
    generation_config: LLMGenerationConfig = field(default_factory=LLMGenerationConfig)
    schema: Optional[LLMSchema] = None
    tools: Optional[List[LLMTool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None  # "none", "auto", tool name, or complex choice
    stream: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        request_dict = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in self.messages],
            "generation_config": self.generation_config.to_dict(),
            "stream": self.stream,
            "metadata": self.metadata
        }
        
        if self.system:
            request_dict["system"] = self.system
        if self.schema:
            request_dict["schema"] = self.schema.to_dict()
        if self.tools:
            request_dict["tools"] = [tool.to_dict() for tool in self.tools]
        if self.tool_choice:
            request_dict["tool_choice"] = self.tool_choice
            
        return request_dict


@dataclass
class LLMUsage:
    """Token usage information."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens
        }


@dataclass
class LLMToolCall:
    """Represents a tool call made by the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments
        }


@dataclass 
class LLMResponse:
    """Standardized LLM response across all providers."""
    content: str
    model: str
    provider: str
    usage: LLMUsage
    tool_calls: Optional[List[LLMToolCall]] = None
    finish_reason: Optional[str] = None
    response_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_response: Optional[Dict[str, Any]] = None  # Original provider response
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        response_dict = {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage.to_dict(),
            "finish_reason": self.finish_reason,
            "response_time": self.response_time,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }
        
        if self.tool_calls:
            response_dict["tool_calls"] = [call.to_dict() for call in self.tool_calls]
        if self.raw_response:
            response_dict["raw_response"] = self.raw_response
            
        return response_dict

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMResponse':
        """Create LLMResponse from dictionary."""
        usage = LLMUsage(**data["usage"])
        
        tool_calls = None
        if data.get("tool_calls"):
            tool_calls = [LLMToolCall(**call) for call in data["tool_calls"]]
        
        timestamp = datetime.fromisoformat(data["timestamp"]) if isinstance(data["timestamp"], str) else data["timestamp"]
        
        return cls(
            content=data["content"],
            model=data["model"],
            provider=data["provider"],
            usage=usage,
            tool_calls=tool_calls,
            finish_reason=data.get("finish_reason"),
            response_time=data.get("response_time", 0.0),
            timestamp=timestamp,
            metadata=data.get("metadata", {}),
            raw_response=data.get("raw_response")
        )


class LLMError(Exception):
    """Base exception for LLM-related errors."""
    
    def __init__(self, message: str, provider: str = "unknown", error_code: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.provider = provider
        self.error_code = error_code
        self.original_error = original_error
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": str(self),
            "provider": self.provider,
            "error_code": self.error_code,
            "timestamp": self.timestamp.isoformat(),
            "original_error": str(self.original_error) if self.original_error else None
        }


class LLMProviderError(LLMError):
    """Error from LLM provider (API issues, rate limits, etc.)."""
    pass


class LLMConfigurationError(LLMError):
    """Error in LLM configuration."""
    pass


class LLMValidationError(LLMError):
    """Error in request validation."""
    pass
