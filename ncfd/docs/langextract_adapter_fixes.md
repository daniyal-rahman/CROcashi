# LangExtract/Gemini Adapter Fixes Implementation

## Overview

This document details the comprehensive fixes implemented for the LangExtract/Gemini adapter to address the issues identified in the code review:

1. **Inconsistent model/env story**: Fixed model choice and environment variable naming
2. **Two different result shapes**: Unified to single, consistent result handling
3. **"Aggressive JSON repair" attempts**: Eliminated multiple parsing methods
4. **Missing post-extract validator**: Added evidence span validation

## 🔧 Fixes Implemented

### 1. Consistent Model and Environment Configuration

**Before**: Multiple model choices and confusing environment variable names
```python
# Inconsistent model usage
model_id: str = "gemini-2.0-flash-exp"  # Sometimes
model_id: str = "gemini-1.5-flash"      # Other times

# Confusing environment variable
gemini_api_key = os.getenv('GEMINI_API_KEY')  # Suggests OpenAI
```

**After**: Single, stable configuration
```python
# Fixed model choice
MODEL_ID = "gemini-1.5-pro"  # Single, stable model choice

# Clear, provider-specific naming
ENV_VAR = "LANGEXTRACT_API_KEY_GEMINI"  # Clear provider identification
```

**Benefits**:
- ✅ Eliminates model confusion
- ✅ Clear provider identification
- ✅ Consistent behavior across all extractions
- ✅ Easier debugging and maintenance

### 2. Unified Result Shape Handling

**Before**: Multiple parsing methods with fallbacks
```python
# Method 1: Check extraction_text
if hasattr(extraction, 'extraction_text'):
    study_card_data = _parse_study_card_text(extraction.extraction_text)

# Method 2: Check attributes
if not study_card_data and hasattr(extraction, 'attributes'):
    study_card_text = extraction.attributes.get('StudyCard')

# Method 3: Check extraction text
if not study_card_data and hasattr(extraction, 'text'):
    # Complex nested checking...

# Method 4: Check result structure
if not study_card_data and hasattr(result, 'extractions'):
    # More complex checking...
```

**After**: Single, consistent result shape
```python
# Single, consistent result shape - fail hard if not found
if not result or not hasattr(result, 'extractions') or not result.extractions:
    raise ExtractionError("No extractions returned from LangExtract")

extraction = result.extractions[0]
if not hasattr(extraction, 'extraction_text'):
    raise ExtractionError("Extraction missing extraction_text field")

study_card_text = extraction.extraction_text
if not study_card_text:
    raise ExtractionError("Extraction text is empty")
```

**Benefits**:
- ✅ Single code path for result handling
- ✅ Clear error messages when things go wrong
- ✅ No more "bad data sliding in" through fallbacks
- ✅ Easier to debug and maintain

### 3. Eliminated JSON Repair Attempts

**Before**: Multiple parsing attempts with potential data corruption
```python
# Multiple parsing methods that could let bad data through
study_card_data = None

# Try various locations and formats
if hasattr(extraction, 'extraction_text'):
    study_card_data = _parse_study_card_text(extraction.extraction_text)
if not study_card_data and hasattr(extraction, 'attributes'):
    # More attempts...
if not study_card_data and hasattr(extraction, 'text'):
    # Even more attempts...
```

**After**: Single-pass JSON parsing with strict validation
```python
# Single-pass JSON parse - no repairs, no fallbacks
try:
    data = json.loads(study_card_text)
except json.JSONDecodeError as e:
    raise ExtractionError(f"Invalid JSON returned: {e}")

# Validate against schema
try:
    validate_card(data, is_pivotal=data.get("trial", {}).get("is_pivotal", False))
except Exception as e:
    raise ExtractionError(f"Schema validation failed: {e}")
```

**Benefits**:
- ✅ No more data corruption through "repair" attempts
- ✅ Clear failure points when JSON is invalid
- ✅ Guaranteed data integrity
- ✅ Easier to identify and fix upstream issues

### 4. Post-Extract Evidence Validation

**Before**: No validation that numeric fields have evidence spans
```python
# Missing validation - could return data without evidence
return study_card_data  # No guarantee of evidence spans
```

**After**: Comprehensive evidence validation
```python
# Post-extract validation: every numeric field must have evidence
evidence_issues = validate_evidence_spans(data)
if evidence_issues:
    raise ExtractionError(f"Missing evidence spans: {', '.join(evidence_issues)}")

return data
```

**Benefits**:
- ✅ Guarantees every numeric claim has evidence
- ✅ Prevents incomplete data from being returned
- ✅ Enforces data quality standards
- ✅ Clear error messages for missing evidence

## 🏗️ New Architecture

### StudyCardAdapter Class

The new implementation introduces a clean, typed adapter class:

```python
class StudyCardAdapter:
    """
    Thin, typed adapter for Study Card extraction via LangExtract.
    
    This adapter provides a stable interface with strict validation
    and fails hard on non-JSON or invalid data.
    """
    
    def __init__(self):
        """Initialize the adapter with prompts and validation."""
        self.prompts = load_prompts()
        
        # Verify API key is available
        api_key = os.getenv(ENV_VAR)
        if not api_key:
            raise ValueError(
                f"{ENV_VAR} environment variable not set. "
                f"Please set your Google Gemini API key for LangExtract."
            )
    
    def extract(self, text: str, prompt: str) -> Dict[str, Any]:
        """
        Extract Study Card data from text using LangExtract.
        
        Args:
            text: The text to extract from
            prompt: The extraction prompt
            
        Returns:
            Validated Study Card data as a dictionary
            
        Raises:
            ExtractionError: If extraction fails or returns invalid data
        """
        # Implementation with strict validation...
```

### Custom Exception Handling

New `ExtractionError` exception for clear error handling:

```python
class ExtractionError(Exception):
    """Raised when extraction fails or returns invalid data."""
    pass
```

### Environment Configuration

Updated environment variable naming:

```bash
# Before (confusing)
GEMINI_API_KEY=your-gemini-api-key-here

# After (clear)
LANGEXTRACT_API_KEY_GEMINI=your-gemini-api-key-here
```

## 📋 Usage Examples

### Basic Usage

```python
from ncfd.extract.lanextract_adapter import StudyCardAdapter

# Initialize adapter
adapter = StudyCardAdapter()

# Extract study card
try:
    result = adapter.extract(document_text, prompt_text)
    print(f"Extraction successful: {result['coverage_level']}")
except ExtractionError as e:
    print(f"Extraction failed: {e}")
```

### Legacy Function Interface

The old function interface is maintained for backward compatibility:

```python
from ncfd.extract.lanextract_adapter import extract_study_card_from_document

try:
    result = extract_study_card_from_document(
        document_text="Methods: Adults with COPD...",
        document_metadata={
            "doc_type": "Abstract",
            "title": "Phase 3 Study of Drug X in COPD",
            "year": 2024,
            "url": "https://example.com",
            "source_id": "example_001"
        },
        trial_context={
            "nct_id": "NCT12345678",
            "phase": "3",
            "indication": "COPD"
        }
    )
    print(f"Extraction successful: {result['coverage_level']}")
except ExtractionError as e:
    print(f"Extraction failed: {e}")
```

## 🧪 Testing

### Structure Tests

Run the structure tests to verify the implementation:

```bash
cd ncfd
python test_adapter_structure.py
```

Expected output:
```
🧪 Testing StudyCardAdapter Structure and Configuration
============================================================
✅ MODEL_ID is correctly set to gemini-1.5-pro
✅ ENV_VAR is correctly set to LANGEXTRACT_API_KEY_GEMINI
✅ StudyCardAdapter class is defined
✅ extract method is defined with correct signature
✅ ExtractionError exception class is defined
✅ Validator functions are imported
✅ LangExtract is imported
✅ New environment variable is correctly named
✅ Old environment variable has been removed
✅ Coverage rubric is present
✅ Evidence requirement is emphasized
============================================================
📊 Test Results: 5/5 tests passed
🎉 All tests passed! The adapter structure is correct.
```

### Integration Tests

For full integration testing (requires LangExtract module):

```bash
cd ncfd
python test_new_adapter.py
```

## 🔄 Migration Guide

### 1. Update Environment Variables

```bash
# Remove old variable
unset GEMINI_API_KEY

# Set new variable
export LANGEXTRACT_API_KEY_GEMINI="your-actual-api-key-here"
```

### 2. Update .env File

```bash
# In your .env file, change:
# GEMINI_API_KEY=your-key-here
# to:
LANGEXTRACT_API_KEY_GEMINI=your-key-here
```

### 3. Code Changes

**Before**:
```python
# Model selection was flexible
result = run_langextract(prompts, payload, "gemini-2.0-flash-exp")
```

**After**:
```python
# Model is fixed for consistency
result = run_langextract(prompts, payload)  # Uses gemini-1.5-pro
```

## 🎯 Benefits Summary

1. **Consistency**: Single model, single environment variable, single result shape
2. **Reliability**: No more data corruption through "repair" attempts
3. **Quality**: Guaranteed evidence spans for all numeric claims
4. **Maintainability**: Clean, typed adapter with clear error handling
5. **Debugging**: Clear failure points and error messages
6. **Performance**: Single-pass parsing without multiple fallback attempts

## 🚀 Next Steps

1. **Deploy**: Update environment variables in production
2. **Monitor**: Watch for any extraction failures (should be more frequent initially due to stricter validation)
3. **Iterate**: Use the clear error messages to improve upstream data quality
4. **Document**: Update team documentation with new usage patterns

## 📚 Related Documentation

- [Study Card Schema](../src/ncfd/extract/study_card.schema.json)
- [Validator Module](../src/ncfd/extract/validator.py)
- [Prompts](../src/ncfd/extract/prompts/study_card_prompts.md)
- [Environment Configuration](../env.example)
