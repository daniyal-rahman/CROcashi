# LLM Model Switching Guide

This guide explains how to configure and switch between different LLM providers (OpenAI, Anthropic, Gemini) in the CROcashi system.

## Overview

The CROcashi system uses a modular LLM abstraction layer that allows you to:

- Switch between OpenAI, Anthropic, and Gemini providers
- Configure different models for different workers
- Set up fallback providers
- Monitor usage and costs across providers
- Use provider-specific features (like web search for GPT-5)

## Quick Start

### 1. Set Up Environment Variables

```bash
# OpenAI (required for current setup)
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"  # Optional override
export OPENAI_ORG_ID="org-..."  # Optional organization ID

# Anthropic (future implementation)
export ANTHROPIC_API_KEY="sk-ant-..."

# Gemini (future implementation)  
export GEMINI_API_KEY="..."
```

### 2. Configure Models

Edit `config/llm_models.yaml` to configure providers and models:

```yaml
# Default provider selection
default_provider: openai

# Provider configurations
providers:
  openai:
    api_key_env: OPENAI_API_KEY
    default_model: gpt-4o
    models:
      gpt-4o:
        capabilities: [json_output, function_calling]
        max_tokens: 4000
        temperature: 0.1

# Worker-specific overrides
workers:
  llm_decider:
    provider: openai
    model: gpt-5-mini
  literature_review:
    provider: openai
    model: gpt-4o
```

### 3. Use in Code

For new workers, extend `BaseLLMWorker`:

```python
from src.ncfd.extract.workers.base_llm_worker import BaseLLMWorker

class MyLLMWorker(BaseLLMWorker):
    def __init__(self):
        super().__init__("my_worker", "1.0.0")
    
    async def process_with_llm(self, text: str) -> str:
        response = await self.call_llm(
            messages=[{"role": "user", "content": text}],
            system_prompt="You are a helpful assistant",
            json_output=True
        )
        return response.content
```

## Configuration Details

### Provider Configuration

Each provider in `config/llm_models.yaml` supports these settings:

```yaml
providers:
  openai:
    api_key_env: OPENAI_API_KEY           # Environment variable for API key
    base_url_env: OPENAI_BASE_URL         # Optional: Custom API endpoint
    organization_env: OPENAI_ORG_ID       # Optional: Organization ID
    default_model: gpt-4o                 # Default model for this provider
    rate_limit_requests_per_minute: 60    # Rate limiting
    timeout_seconds: 30                   # Request timeout
    max_retries: 3                        # Retry attempts
    retry_delay_seconds: 1.0              # Delay between retries
```

### Model Configuration

Each model supports these settings:

```yaml
models:
  gpt-4o:
    capabilities: [json_output, function_calling, structured_output]
    max_tokens: 4000                      # Maximum tokens to generate
    temperature: 0.1                      # Default temperature
    cost_per_input_token: 0.0000025       # Cost tracking (optional)
    cost_per_output_token: 0.00001        # Cost tracking (optional)
    supports_system_message: true         # Model capabilities
    supports_function_calling: true
    supports_json_output: true
    supports_streaming: true
```

### Worker-Specific Configuration

Configure specific models for each worker:

```yaml
workers:
  # Clinical trial resolution
  llm_decider:
    provider: openai
    model: gpt-5-mini       # Uses web search capabilities
  
  # Literature analysis
  literature_review:
    provider: anthropic     # When implemented
    model: claude-3-5-sonnet-20241022
  
  # SEC document extraction  
  sec_extractor:
    provider: gemini        # When implemented
    model: gemini-1.5-pro
  
  # Study card processing
  method_auditor:
    provider: openai
    model: gpt-4o
  
  results_distiller:
    provider: openai
    model: gpt-4o
```

### Fallback Configuration

Configure automatic fallback when primary provider fails:

```yaml
# Global fallback settings
enable_fallback: true
fallback_order: [openai, anthropic, gemini]

# Pipeline-level fallback settings
llm:
  enable_fallback: true
  fallback_order: [openai, anthropic, gemini]
```

## Worker Migration

### Migrating Existing Workers

To migrate an existing worker to use the new LLM system:

1. **Extend BaseLLMWorker instead of BaseWorker:**

```python
# Before
from ..base_worker import BaseWorker

class MyWorker(BaseWorker):
    def __init__(self):
        super().__init__("MyWorker", "1.0.0")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# After  
from ..base_llm_worker import BaseLLMWorker

class MyWorker(BaseLLMWorker):
    def __init__(self):
        super().__init__("my_worker", "1.0.0")
        # LLM provider automatically configured based on worker name
```

2. **Replace direct API calls with abstracted calls:**

```python
# Before
response = self.client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": text}],
    temperature=0.1,
    response_format={"type": "json_object"}
)
content = response.choices[0].message.content

# After
response = await self.call_llm(
    messages=[text],
    temperature=0.1,
    json_output=True
)
content = response.content
```

3. **Update configuration to specify provider/model:**

Add your worker to `config/llm_models.yaml`:

```yaml
workers:
  my_worker:
    provider: openai
    model: gpt-4o
```

### Example Migration

Here's a complete example of migrating the LLM decider:

```python
# Before (llm_decider.py)
def decide_with_llm_research(nct_id: str, session, context: Dict[str, Any]):
    model = os.getenv("OPENAI_MODEL_RESOLVER", "gpt-5-mini")
    cli = _client()
    
    resp = cli.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content

# After (llm_resolver.py) 
class LLMTrialResolver:
    def __init__(self):
        self.llm_factory = LLMProviderFactory()
        self.llm_provider = self.llm_factory.create_for_worker("llm_decider")
        self.model = self.llm_factory.get_model_for_worker("llm_decider")
    
    async def decide_with_llm_research(self, nct_id: str, session, context: Dict[str, Any]):
        request = LLMRequest(
            model=self.model,
            messages=[LLMMessage(role="user", content=user_prompt)],
            system=system_prompt,
            schema=LLMSchema(json_schema=json_schema, force=True)
        )
        
        response = await self.llm_provider.complete(request)
        content = response.content
```

## Provider-Specific Features

### OpenAI Features

- **GPT-5 Web Search**: Automatically enabled for `gpt-5*` models
- **Structured Output**: Full JSON schema validation with `strict=True`
- **Function Calling**: Advanced tool use capabilities
- **Responses API**: Automatic selection for GPT-5 models

```yaml
workers:
  research_worker:
    provider: openai
    model: gpt-5-mini  # Automatically gets web search tools
```

### Anthropic Features (Future)

- **Extended Thinking**: Use `thinking` capability for complex reasoning
- **Tool Use**: Anthropic-specific tool calling format
- **System Messages**: Proper system message handling

### Gemini Features (Future)

- **Safety Filtering**: Configurable safety settings
- **Code Execution**: Native code execution capabilities
- **Multimodal**: Image and text processing

## Monitoring and Debugging

### Usage Statistics

Get provider statistics programmatically:

```python
from src.ncfd.llm import get_default_factory

factory = get_default_factory()
stats = factory.get_provider_stats()
print(stats)
# {
#   "openai": {
#     "total_requests": 150,
#     "total_errors": 2,
#     "error_rate": 0.013,
#     "total_tokens": 45000,
#     "total_cost": 0.45
#   }
# }
```

### Debugging Failed Requests

Enable debug logging to see detailed request/response information:

```python
import logging
logging.getLogger("src.ncfd.llm").setLevel(logging.DEBUG)
```

### Testing Different Providers

Test different providers without changing configuration:

```python
from src.ncfd.llm import LLMProviderFactory

# Test with different provider
factory = LLMProviderFactory()
anthropic_provider = factory.create_provider("anthropic")  # When implemented
response = await anthropic_provider.complete(request)
```

## Cost Management

### Cost Tracking

Enable cost tracking in configuration:

```yaml
cost_tracking:
  enabled: true
  alert_threshold_dollars: 100.0
  daily_budget_dollars: 500.0
```

### Model Costs

Configure per-token costs for accurate tracking:

```yaml
models:
  gpt-4o:
    cost_per_input_token: 0.0000025   # $2.50 per 1M tokens
    cost_per_output_token: 0.00001    # $10.00 per 1M tokens
```

## Troubleshooting

### Common Issues

1. **Provider Not Available**
   ```
   LLMConfigurationError: Provider 'anthropic' not available
   ```
   - Check that the provider is implemented in `src/ncfd/llm/providers/`
   - Verify the provider is registered in `factory.py`

2. **Missing API Key**
   ```
   LLMProviderError: OpenAI API key not found
   ```
   - Set the required environment variable
   - Check the `api_key_env` setting in configuration

3. **Model Not Supported**
   ```
   LLMValidationError: Model gpt-5 does not support function calling
   ```
   - Check model capabilities in configuration
   - Use a different model or remove unsupported features

4. **Rate Limit Errors**
   ```
   LLMProviderError: Rate limit exceeded
   ```
   - Adjust `rate_limit_requests_per_minute` in configuration
   - Enable fallback providers
   - Implement exponential backoff

### Fallback Debugging

Test fallback behavior:

```python
# Force provider failure to test fallback
factory = LLMProviderFactory()
provider = factory.create_with_fallback(preferred_provider="nonexistent")
```

### Configuration Validation

Validate your configuration:

```python
from src.ncfd.llm.config import load_llm_config, validate_environment

config = load_llm_config()
missing_vars = validate_environment(config)
if missing_vars:
    print(f"Missing environment variables: {missing_vars}")
```

## Best Practices

1. **Use Worker-Specific Models**: Configure different models for different use cases
2. **Enable Fallback**: Always configure fallback providers for reliability
3. **Monitor Costs**: Track usage and set budgets to avoid surprise bills
4. **Test Thoroughly**: Test with different providers before deploying
5. **Use Structured Output**: Prefer JSON schema over prompt engineering for reliability
6. **Handle Errors Gracefully**: Implement proper error handling and logging

## Future Enhancements

The LLM system is designed for extensibility. Planned enhancements include:

- **Anthropic Provider**: Full Claude integration with thinking capabilities
- **Gemini Provider**: Google's models with safety filtering and multimodal support
- **Model Performance Monitoring**: Automatic A/B testing and performance comparison
- **Cost Optimization**: Automatic model selection based on cost/performance trade-offs
- **Caching Layer**: Response caching to reduce API calls and costs
