# GPT-5 Thinking Hook Implementation

## Overview

The GPT-5 Thinking Hook is a two-agent system that provides independent analysis of clinical trials using advanced language models. It consists of:

1. **Literature Review Agent**: Finds relevant trials and literature
2. **Independent Analysis Agent**: Analyzes evidence and makes predictions

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Trial Input    │───▶│ Literature Agent │───▶│ Analysis Agent   │
│                 │    │                  │    │                 │
│ - NCT ID        │    │ - PubMed search  │    │ - Mechanistic   │
│ - Indication    │    │ - Trial search   │    │   analysis      │
│ - Phase         │    │ - Paper search   │    │ - Class priors  │
│ - Endpoint      │    │ - Relevance      │    │ - Risk factors  │
│ - Mechanism     │    │   scoring        │    │ - Red flags     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                                                         ▼
                                               ┌─────────────────┐
                                               │   Results       │
                                               │                 │
                                               │ - GPT-5 P_fail  │
                                               │ - Confidence    │
                                               │ - Red flags     │
                                               │ - Recommendation │
                                               └─────────────────┘
```

## Key Features

### 🎯 **Conservative Analysis**
- Only recommends with **very strong red flags**
- Requires clear mechanistic issues or class priors
- Conservative approach to avoid false positives

### 🔍 **Comprehensive Literature Review**
- Searches for relevant trials in same indication/phase
- Finds key papers establishing class priors
- Identifies trials with similar endpoints/mechanisms
- Focuses on recent evidence (last 10 years)

### 🤖 **Independent Assessment**
- Generates independent P_fail prediction
- Analyzes biological plausibility
- Reviews historical context and class priors
- Compares against deterministic synthesis

### 📊 **Quality Metrics**
- Literature review confidence score
- Analysis confidence level (High/Medium/Low)
- Agreement with deterministic synthesis
- Disagreement level tracking

## Usage

### Python API

```python
from ncfd.synthesis import GPT5ThinkingHook, trigger_gpt5_analysis_sync

# Async usage
hook = GPT5ThinkingHook(api_key="your-openai-api-key")
result = await hook.trigger_thinking_analysis(
    trial_id="trial_001",
    nct_id="NCT01234567",
    indication="Advanced Non-Small Cell Lung Cancer",
    phase="3",
    primary_endpoint="Overall Survival",
    mechanism="PD-1 inhibitor",
    p_fail=0.85
)

# Sync usage
result = trigger_gpt5_analysis_sync(
    api_key="your-openai-api-key",
    trial_id="trial_001",
    nct_id="NCT01234567",
    indication="Advanced Non-Small Cell Lung Cancer",
    phase="3",
    primary_endpoint="Overall Survival",
    mechanism="PD-1 inhibitor",
    p_fail=0.85
)
```

### CLI Usage

```bash
# Basic analysis
python scripts/gpt5_analysis.py \
  --trial-id trial_001 \
  --nct-id NCT01234567 \
  --indication "Advanced Non-Small Cell Lung Cancer" \
  --phase 3 \
  --primary-endpoint "Overall Survival" \
  --mechanism "PD-1 inhibitor" \
  --p-fail 0.85 \
  --verbose

# Save results to file
python scripts/gpt5_analysis.py \
  --trial-id trial_001 \
  --nct-id NCT01234567 \
  --indication "NSCLC" \
  --phase 3 \
  --out results.json \
  --verbose
```

### Environment Variables

```bash
export OPENAI_API_KEY="your-openai-api-key"
```

## Output Format

### Literature Review Results

```json
{
  "literature_confidence": 0.85,
  "relevant_trials_count": 5,
  "relevant_papers_count": 3,
  "search_queries": [
    "\"Advanced Non-Small Cell Lung Cancer\" AND \"Phase 3\" AND \"clinical trial\"",
    "\"Advanced Non-Small Cell Lung Cancer\" AND \"Overall Survival\" AND \"clinical trial\"",
    "\"Advanced Non-Small Cell Lung Cancer\" AND \"PD-1 inhibitor\" AND \"clinical trial\""
  ]
}
```

### Independent Analysis Results

```json
{
  "gpt5_p_fail": 0.75,
  "mechanistic_analysis": "Biological plausibility is moderate based on target expression patterns...",
  "class_prior_analysis": "Historical success rate in this indication is 35%...",
  "independent_risk_factors": ["sample_size_concern", "endpoint_choice"],
  "agreement_with_deterministic": 0.80,
  "additional_insights": ["Consider biomarker stratification"],
  "research_sources": ["NCT01234567", "Smith et al. 2023"],
  "confidence_level": "Medium",
  "strong_red_flags": ["Sample size may be insufficient for primary endpoint"],
  "recommendation": "Proceed with caution due to sample size concerns"
}
```

### Summary Metrics

```json
{
  "analysis_quality": "Medium",
  "disagreement_level": 0.10,
  "recommendation_strength": 1,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Configuration

### Literature Review Agent

The literature review agent builds search queries based on:

- **Basic Query**: `"{indication}" AND "Phase {phase}" AND "clinical trial"`
- **Endpoint Query**: `"{indication}" AND "{primary_endpoint}" AND "clinical trial"`
- **Mechanism Query**: `"{indication}" AND "{mechanism}" AND "clinical trial"`
- **Class Prior Query**: `"{indication}" AND "systematic review" AND "meta-analysis"`
- **Historical Query**: `"{indication}" AND "pivotal trial" AND "FDA approval"`

### Independent Analysis Agent

The analysis agent uses conservative criteria:

#### Confidence Levels
- **High**: Clear mechanistic issues + strong class priors + multiple red flags
- **Medium**: Some concerns but unclear evidence
- **Low**: Limited evidence or unclear signals

#### Strong Red Flags (Only Very Strong)
- Clear mechanistic implausibility
- Multiple failed trials in same class
- Endpoint issues (surrogate vs clinical)
- Sample size concerns with clear evidence
- Regulatory precedents against approval

## Integration with Synthesis

The GPT-5 thinking hook integrates with the evidence-constrained synthesis:

```python
from ncfd.synthesis import EvidenceConstrainedSynthesizer

synthesizer = EvidenceConstrainedSynthesizer()
doc = synthesizer.generate(trial, study_cards, gates, score)

if doc.gpt5_hook_triggered:
    # Trigger GPT-5 analysis
    gpt5_result = trigger_gpt5_analysis_sync(
        api_key=api_key,
        trial_id=trial.trial_id,
        nct_id=trial.nct_id,
        indication=trial.indication,
        phase=trial.phase,
        primary_endpoint=primary_endpoint,
        mechanism=mechanism,
        p_fail=score.p_fail
    )
    
    # Add GPT-5 results to synthesis
    doc.gpt5_analysis = gpt5_result
```

## Error Handling

The system gracefully handles API failures:

```python
# API failure returns fallback values
result = {
    "trial_id": "trial_001",
    "nct_id": "NCT01234567",
    "error": "API call failed: 401 - Invalid API key",
    "gpt5_p_fail": None,
    "confidence_level": "Low",
    "recommendation": "Analysis failed"
}
```

## Testing

Run the test suite:

```bash
# Run all GPT-5 thinking hook tests
python -m pytest tests/test_gpt5_thinking_hook.py -v

# Run specific test
python -m pytest tests/test_gpt5_thinking_hook.py::TestGPT5ThinkingHook::test_trigger_thinking_analysis_success -v
```

## Examples

### Basic Example

```python
from ncfd.synthesis import trigger_gpt5_analysis_sync

result = trigger_gpt5_analysis_sync(
    api_key="your-key",
    trial_id="trial_001",
    nct_id="NCT01234567",
    indication="Advanced NSCLC",
    phase="3",
    primary_endpoint="Overall Survival",
    p_fail=0.85
)

print(f"GPT-5 P_fail: {result['gpt5_p_fail']}")
print(f"Confidence: {result['confidence_level']}")
print(f"Red Flags: {result['strong_red_flags']}")
```

### Advanced Example

```python
from ncfd.synthesis import GPT5ThinkingHook
import asyncio

async def analyze_trial():
    hook = GPT5ThinkingHook(api_key="your-key")
    
    # Step 1: Literature Review
    literature = await hook.literature_agent.review_literature(
        trial_id="trial_001",
        nct_id="NCT01234567",
        indication="Advanced NSCLC",
        phase="3",
        primary_endpoint="Overall Survival",
        mechanism="PD-1 inhibitor"
    )
    
    print(f"Found {len(literature.relevant_trials)} relevant trials")
    
    # Step 2: Independent Analysis
    analysis = await hook.analysis_agent.analyze_independently(
        trial_id="trial_001",
        nct_id="NCT01234567",
        indication="Advanced NSCLC",
        phase="3",
        primary_endpoint="Overall Survival",
        p_fail=0.85,
        literature_result=literature
    )
    
    print(f"GPT-5 P_fail: {analysis.gpt5_p_fail}")
    print(f"Recommendation: {analysis.recommendation}")

# Run
asyncio.run(analyze_trial())
```

## Best Practices

### 1. **API Key Management**
- Use environment variables for API keys
- Never commit API keys to version control
- Use different keys for development/production

### 2. **Error Handling**
- Always check for API failures
- Provide fallback values for failed analyses
- Log errors for debugging

### 3. **Rate Limiting**
- Implement rate limiting for API calls
- Use async/await for better performance
- Consider caching results for repeated analyses

### 4. **Quality Control**
- Monitor confidence levels
- Track disagreement with deterministic synthesis
- Review strong red flags manually

### 5. **Integration**
- Trigger only when P_fail ≥ threshold (default: 0.85)
- Include GPT-5 results in synthesis documents
- Use as complementary analysis, not replacement

## Troubleshooting

### Common Issues

1. **API Key Invalid**
   ```
   Error: API call failed: 401 - Invalid API key
   ```
   - Check API key is correct
   - Ensure key has sufficient credits
   - Verify key permissions

2. **Rate Limiting**
   ```
   Error: API call failed: 429 - Rate limit exceeded
   ```
   - Implement exponential backoff
   - Reduce request frequency
   - Use async processing

3. **JSON Parsing Errors**
   ```
   Error: Could not parse JSON response
   ```
   - Check API response format
   - Implement fallback parsing
   - Log raw responses for debugging

### Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Run analysis with debug output
result = trigger_gpt5_analysis_sync(...)
```

## Future Enhancements

1. **Multi-Model Support**
   - Support for different LLM providers
   - Model comparison and ensemble methods
   - Cost optimization strategies

2. **Enhanced Literature Review**
   - Patent analysis integration
   - Real-time PubMed updates
   - Automated relevance scoring

3. **Advanced Analysis**
   - Biomarker analysis
   - Regulatory pathway analysis
   - Competitive landscape assessment

4. **Performance Optimization**
   - Caching and memoization
   - Parallel processing
   - Batch analysis capabilities

## Contributing

1. Follow the existing code style
2. Add comprehensive tests
3. Update documentation
4. Include error handling
5. Add type hints

## License

This implementation is part of the CROcashi project and follows the same licensing terms.
