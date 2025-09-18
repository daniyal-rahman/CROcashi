"""
Robust JSON Parser for LLM Responses

Handles common LLM JSON parsing issues including:
- Non-strict JSON with words inside numbers (e.g., "ninetyFive" -> 0.95)
- Malformed JSON with extra text
- Mixed content types
- Confidence scores in various formats
"""

import json
import re
import logging
import time
from typing import Dict, Any, Optional, Union, List
from decimal import Decimal, InvalidOperation

from .json_monitoring import ParsingTimer, log_parsing_error, log_conversion_attempt, ParsingErrorType

logger = logging.getLogger(__name__)

# Common word-to-number mappings
WORD_TO_NUMBER = {
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
    'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70,
    'eighty': 80, 'ninety': 90, 'hundred': 100, 'thousand': 1000,
    'million': 1000000, 'billion': 1000000000,
    # Common decimal representations
    'point': '.', 'dot': '.',
    # Confidence-related terms
    'confident': 0.8, 'very_confident': 0.9, 'highly_confident': 0.95,
    'moderate': 0.6, 'low': 0.3, 'minimal': 0.1,
    'uncertain': 0.5, 'doubtful': 0.2, 'skeptical': 0.1
}

# Common percentage patterns
PERCENTAGE_PATTERNS = [
    r'(\d+(?:\.\d+)?)\s*%',  # "95%" or "95.5%"
    r'(\d+(?:\.\d+)?)\s*percent',  # "95 percent"
    r'(\d+(?:\.\d+)?)\s*per\s*cent',  # "95 per cent"
]

# Common decimal patterns
DECIMAL_PATTERNS = [
    r'(\d+(?:\.\d+)?)',  # Standard decimal
    r'(\d+)\s*point\s*(\d+)',  # "95 point 5"
    r'(\d+)\s*dot\s*(\d+)',  # "95 dot 5"
]

# Common fraction patterns
FRACTION_PATTERNS = [
    r'(\d+)/(\d+)',  # "95/100"
    r'(\d+)\s*out\s*of\s*(\d+)',  # "95 out of 100"
]


def parse_number_from_text(text: str) -> Optional[float]:
    """
    Parse a number from text that may contain words or mixed formats.
    
    Args:
        text: Text that may contain a number in various formats
        
    Returns:
        Parsed number as float, or None if parsing fails
    """
    if not text or not isinstance(text, str):
        return None
    
    text = text.strip().lower()
    
    # Handle direct numeric values
    try:
        result = float(text)
        log_conversion_attempt(True, text, result)
        return result
    except (ValueError, TypeError):
        pass
    
    # Handle percentages
    for pattern in PERCENTAGE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            try:
                value = float(match.group(1))
                return value / 100.0  # Convert percentage to decimal
            except (ValueError, TypeError):
                continue
    
    # Handle fractions
    for pattern in FRACTION_PATTERNS:
        match = re.search(pattern, text)
        if match:
            try:
                numerator = float(match.group(1))
                denominator = float(match.group(2))
                if denominator != 0:
                    return numerator / denominator
            except (ValueError, TypeError, ZeroDivisionError):
                continue
    
    # Handle word-based numbers
    if text in WORD_TO_NUMBER:
        result = float(WORD_TO_NUMBER[text])
        log_conversion_attempt(True, text, result)
        return result
    
    # Handle compound word numbers (e.g., "ninety five", "ninety-five")
    compound_pattern = r'(\w+)\s*-?\s*(\w+)'
    match = re.search(compound_pattern, text)
    if match:
        word1, word2 = match.groups()
        if word1 in WORD_TO_NUMBER and word2 in WORD_TO_NUMBER:
            return float(WORD_TO_NUMBER[word1] + WORD_TO_NUMBER[word2])
    
    # Handle "point" or "dot" decimal notation
    point_pattern = r'(\w+)\s*(?:point|dot)\s*(\w+)'
    match = re.search(point_pattern, text)
    if match:
        word1, word2 = match.groups()
        if word1 in WORD_TO_NUMBER and word2 in WORD_TO_NUMBER:
            try:
                return float(f"{WORD_TO_NUMBER[word1]}.{WORD_TO_NUMBER[word2]}")
            except (ValueError, TypeError):
                pass
    
    # Try to extract any numeric value from the text
    numeric_match = re.search(r'(\d+(?:\.\d+)?)', text)
    if numeric_match:
        try:
            return float(numeric_match.group(1))
        except (ValueError, TypeError):
            pass
    
    return None


def clean_json_value(value: Any) -> Any:
    """
    Clean a JSON value, converting text numbers to proper numeric values.
    
    Args:
        value: Value to clean
        
    Returns:
        Cleaned value
    """
    if isinstance(value, str):
        # Try to parse as number first
        parsed_number = parse_number_from_text(value)
        if parsed_number is not None:
            return parsed_number
        
        # Handle boolean-like strings
        if value.lower() in ['true', 'yes', 'y', '1']:
            return True
        elif value.lower() in ['false', 'no', 'n', '0']:
            return False
        
        # Return original string if no conversion possible
        return value
    
    elif isinstance(value, dict):
        return {k: clean_json_value(v) for k, v in value.items()}
    
    elif isinstance(value, list):
        return [clean_json_value(item) for item in value]
    
    else:
        return value


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON from text that may contain extra content.
    
    Args:
        text: Text that may contain JSON
        
    Returns:
        Parsed JSON dict or None if extraction fails
    """
    if not text or not isinstance(text, str):
        return None
    
    text = text.strip()
    
    # Try direct JSON parsing first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Look for JSON blocks in markdown code blocks
    json_patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'`([^`]+)`',
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue
    
    # Look for JSON-like content between curly braces
    brace_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(brace_pattern, text, re.DOTALL)
    
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    
    # Try to find the largest JSON-like structure
    start_idx = text.find('{')
    if start_idx != -1:
        # Find matching closing brace
        brace_count = 0
        end_idx = start_idx
        for i, char in enumerate(text[start_idx:], start_idx):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break
        
        if end_idx > start_idx:
            try:
                return json.loads(text[start_idx:end_idx])
            except json.JSONDecodeError:
                pass
    
    return None


def parse_llm_json_response(response: str, expected_fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Parse LLM JSON response with robust error handling and value cleaning.
    
    Args:
        response: Raw LLM response text
        expected_fields: Optional list of expected field names for validation
        
    Returns:
        Parsed and cleaned JSON dict
    """
    with ParsingTimer("llm_json_parsing"):
        logger.debug(f"Parsing LLM response: {response[:200]}...")
        
        # Extract JSON from response
        json_data = extract_json_from_text(response)
        if json_data is None:
            logger.error(f"Failed to extract JSON from response: {response[:500]}...")
            log_parsing_error(
                ParsingErrorType.JSON_DECODE_ERROR,
                "Failed to extract JSON from response",
                original_value=response[:500]
            )
            return {}
        
        # Clean all values in the JSON
        cleaned_data = clean_json_value(json_data)
        
        # Validate expected fields if provided
        if expected_fields:
            missing_fields = [field for field in expected_fields if field not in cleaned_data]
            if missing_fields:
                logger.warning(f"Missing expected fields: {missing_fields}")
                log_parsing_error(
                    ParsingErrorType.MISSING_FIELDS,
                    f"Missing expected fields: {missing_fields}",
                    original_value=missing_fields
                )
        
        # Log any confidence-related fields that were converted
        confidence_fields = ['confidence', 'confidence_score', 'gpt5_p_fail', 'agreement_with_deterministic']
        for field in confidence_fields:
            if field in cleaned_data:
                original_value = json_data.get(field)
                cleaned_value = cleaned_data.get(field)
                if original_value != cleaned_value:
                    logger.info(f"Converted {field}: '{original_value}' -> {cleaned_value}")
                    log_conversion_attempt(True, original_value, cleaned_value)
        
        logger.debug(f"Successfully parsed JSON with {len(cleaned_data)} fields")
        return cleaned_data


def validate_confidence_score(value: Any, field_name: str = "confidence") -> float:
    """
    Validate and normalize a confidence score to 0.0-1.0 range.
    
    Args:
        value: Confidence value to validate
        field_name: Name of the field for logging
        
    Returns:
        Normalized confidence score (0.0-1.0)
    """
    if isinstance(value, (int, float)):
        # Clamp to 0.0-1.0 range
        return max(0.0, min(1.0, float(value)))
    
    if isinstance(value, str):
        parsed = parse_number_from_text(value)
        if parsed is not None:
            # If it looks like a percentage (>1), convert to decimal
            if parsed > 1.0:
                parsed = parsed / 100.0
            return max(0.0, min(1.0, parsed))
    
    logger.warning(f"Invalid confidence score '{value}' for field '{field_name}', using default 0.5")
    return 0.5


# Example usage and testing
if __name__ == "__main__":
    # Test cases
    test_cases = [
        "ninetyFive",
        "0.95",
        "95%",
        "ninety five",
        "ninety-five",
        "95 percent",
        "95 out of 100",
        "95/100",
        "ninety point five",
        "confident",
        "very confident",
        "0.95",
        "1.0",
        "0.0"
    ]
    
    print("Testing number parsing:")
    for test in test_cases:
        result = parse_number_from_text(test)
        print(f"'{test}' -> {result}")
    
    # Test JSON parsing
    test_json = '''
    {
        "confidence": "ninetyFive",
        "gpt5_p_fail": "0.95",
        "agreement": "95%",
        "status": "confident"
    }
    '''
    
    print("\nTesting JSON parsing:")
    result = parse_llm_json_response(test_json)
    print(f"Parsed: {result}")
