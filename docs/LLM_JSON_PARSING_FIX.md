# LLM JSON Parsing Fix Implementation

## Problem Description

The LLM JSON parsing system was failing when models occasionally emitted non-strict JSON with words inside numbers. For example:
- `"ninetyFive"` instead of `0.95`
- `"95%"` instead of `0.95`
- `"ninety-five"` instead of `0.95`

This caused JSON parsing errors that broke the pipeline, particularly affecting confidence scores and numeric fields.

## Solution Overview

Implemented a comprehensive multi-layered approach to fix LLM JSON parsing issues:

### 1. Robust JSON Parser (`src/ncfd/llm/json_parser.py`)

**Key Features:**
- **Text-to-number conversion**: Handles word-based numbers, percentages, fractions
- **Multiple extraction strategies**: JSON blocks, markdown code blocks, brace matching
- **Confidence score validation**: Ensures values are in 0.0-1.0 range
- **Comprehensive word mapping**: Supports common number words and confidence terms

**Supported Formats:**
```python
# Direct numbers
"0.95" -> 0.95

# Word-based numbers
"ninetyFive" -> 0.95
"ninety five" -> 95.0
"ninety-five" -> 95.0

# Percentages
"95%" -> 0.95
"95 percent" -> 0.95

# Fractions
"95/100" -> 0.95
"95 out of 100" -> 0.95

# Confidence terms
"confident" -> 0.8
"very confident" -> 0.9
"uncertain" -> 0.5
```

### 2. Schema Validation (`src/ncfd/llm/schema_validator.py`)

**Key Features:**
- **Type validation**: Ensures fields have correct data types
- **Range validation**: Enforces min/max constraints for numeric fields
- **Default value handling**: Provides fallbacks for missing fields
- **Strict mode**: Optionally rejects unknown fields

**Predefined Schemas:**
- Literature review responses
- Independent analysis responses
- Study card responses
- Results factsheet responses
- LLM decider responses

### 3. Comprehensive Monitoring (`src/ncfd/llm/json_monitoring.py`)

**Key Features:**
- **Performance tracking**: Parse times, success rates
- **Error categorization**: Different error types with detailed logging
- **Conversion tracking**: Success/failure rates for value conversions
- **Historical error tracking**: Recent errors with context

**Error Types Tracked:**
- JSON decode errors
- Missing fields
- Invalid value types
- Schema validation errors
- Number conversion errors
- Unknown fields

### 4. Improved Prompting

**Enhanced prompts with:**
- **Explicit examples**: Show correct numeric format (e.g., `0.85` not `"eighty-five"`)
- **Critical instructions**: Emphasize strict JSON number requirements
- **Format specifications**: Clear decimal format requirements (0.0-1.0 range)

## Implementation Details

### Updated Files

1. **`src/ncfd/llm/json_parser.py`** - Core parsing utility
2. **`src/ncfd/llm/schema_validator.py`** - Schema validation system
3. **`src/ncfd/llm/json_monitoring.py`** - Monitoring and error tracking
4. **`src/ncfd/synthesis/independent_llm_analysis.py`** - Updated to use new parsing
5. **`src/ncfd/extract/generators/study_card_generator.py`** - Updated parsing
6. **`src/ncfd/extract/generators/results_factsheet_generator.py`** - Updated parsing
7. **`src/ncfd/mapping/llm_decider.py`** - Updated parsing

### Usage Examples

#### Basic JSON Parsing
```python
from ncfd.llm.json_parser import parse_llm_json_response

# Parse with robust error handling
data = parse_llm_json_response(response, expected_fields=["confidence", "gpt5_p_fail"])
```

#### Schema Validation
```python
from ncfd.llm.schema_validator import validate_independent_analysis

# Validate against predefined schema
validated_data = validate_independent_analysis(raw_data)
```

#### Monitoring
```python
from ncfd.llm.json_monitoring import get_parsing_stats, log_performance_summary

# Get performance statistics
stats = get_parsing_stats()
print(f"Success rate: {stats['success_rate']:.2%}")

# Log performance summary
log_performance_summary()
```

## Benefits

### 1. **Robustness**
- Handles various number formats automatically
- Graceful fallbacks for parsing failures
- Comprehensive error recovery

### 2. **Monitoring**
- Real-time performance tracking
- Detailed error categorization
- Historical error analysis

### 3. **Maintainability**
- Centralized parsing logic
- Consistent error handling
- Easy to extend for new formats

### 4. **Data Quality**
- Schema validation ensures data consistency
- Confidence score normalization
- Type safety enforcement

## Testing

The solution includes comprehensive test cases covering:
- Word-to-number conversions
- Percentage parsing
- Fraction handling
- JSON extraction from various formats
- Schema validation
- Error handling

## Future Enhancements

1. **Machine Learning**: Train models to better understand numeric formatting requirements
2. **Dynamic Schemas**: Generate schemas automatically from API responses
3. **Advanced Monitoring**: Real-time dashboards for parsing performance
4. **Custom Validators**: Allow domain-specific validation rules

## Migration Guide

### For Existing Code

1. **Replace direct JSON parsing**:
   ```python
   # Old
   data = json.loads(response)
   
   # New
   data = parse_llm_json_response(response)
   ```

2. **Add schema validation**:
   ```python
   # Optional but recommended
   data = validate_independent_analysis(data)
   ```

3. **Monitor performance**:
   ```python
   # Add to your logging
   from ncfd.llm.json_monitoring import log_performance_summary
   log_performance_summary()
   ```

### Configuration

No configuration changes required. The system works out of the box with sensible defaults.

## Conclusion

This comprehensive solution addresses the root cause of LLM JSON parsing failures while providing robust error handling, monitoring, and data validation. The multi-layered approach ensures that even if one layer fails, the system continues to function with graceful degradation.

The implementation is backward-compatible and requires minimal changes to existing code while providing significant improvements in reliability and data quality.
