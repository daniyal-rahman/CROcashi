"""
JSON Repair Utility

Deterministic JSON repair for LLM responses that fail to parse.
This handles common JSON parsing errors without making new LLM calls.
"""

import json
import re
import logging
from typing import Dict, Any, Optional, Union

logger = logging.getLogger(__name__)


class JSONRepairUtil:
    """Utility for repairing malformed JSON responses."""
    
    def __init__(self):
        self.max_repair_attempts = 3
    
    def repair_json(self, malformed_json: str, expected_schema: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Attempt to repair malformed JSON.
        
        Args:
            malformed_json: The malformed JSON string
            expected_schema: Optional schema to guide repair
            
        Returns:
            Repaired JSON as dictionary, or None if repair fails
        """
        if not malformed_json or not isinstance(malformed_json, str):
            return None
        
        # Try direct parsing first
        try:
            return json.loads(malformed_json)
        except json.JSONDecodeError:
            pass
        
        # Attempt repairs
        for attempt in range(self.max_repair_attempts):
            logger.debug(f"JSON repair attempt {attempt + 1}")
            
            repaired_json = self._attempt_repair(malformed_json, attempt)
            if repaired_json:
                try:
                    result = json.loads(repaired_json)
                    logger.info(f"JSON repair successful on attempt {attempt + 1}")
                    return result
                except json.JSONDecodeError as e:
                    logger.debug(f"Repair attempt {attempt + 1} still invalid: {e}")
                    continue
        
        logger.warning("All JSON repair attempts failed")
        return None
    
    def _attempt_repair(self, json_str: str, attempt: int) -> Optional[str]:
        """Attempt a specific repair strategy."""
        if attempt == 0:
            return self._repair_basic_syntax(json_str)
        elif attempt == 1:
            return self._repair_structure(json_str)
        elif attempt == 2:
            return self._repair_extract_valid(json_str)
        else:
            return None
    
    def _repair_basic_syntax(self, json_str: str) -> Optional[str]:
        """Repair basic JSON syntax errors."""
        repaired = json_str.strip()
        
        # Remove any leading/trailing non-JSON content
        repaired = re.sub(r'^[^{[]*', '', repaired)  # Remove leading non-JSON
        repaired = re.sub(r'[^}\]]*$', '', repaired)  # Remove trailing non-JSON
        
        # Fix common quote issues
        repaired = re.sub(r"'([^']*)':", r'"\1":', repaired)  # Single quotes to double quotes for keys
        repaired = re.sub(r":\s*'([^']*)'", r': "\1"', repaired)  # Single quotes to double quotes for string values
        
        # Fix trailing commas
        repaired = re.sub(r',(\s*[}\]])', r'\1', repaired)
        
        # Fix missing commas between objects
        repaired = re.sub(r'}\s*{', '}, {', repaired)
        repaired = re.sub(r']\s*\[', '], [', repaired)
        
        # Fix unescaped quotes in strings
        repaired = re.sub(r'"([^"]*)"([^"]*)"([^"]*)"', r'"\1\\"\2\\"\3"', repaired)
        
        return repaired
    
    def _repair_structure(self, json_str: str) -> Optional[str]:
        """Repair JSON structure issues."""
        repaired = json_str.strip()
        
        # Ensure it starts and ends with proper brackets
        if not repaired.startswith(('{', '[')):
            repaired = '{' + repaired
        if not repaired.endswith(('}', ']')):
            repaired = repaired + '}'
        
        # Fix mismatched brackets
        open_braces = repaired.count('{')
        close_braces = repaired.count('}')
        if open_braces > close_braces:
            repaired += '}' * (open_braces - close_braces)
        elif close_braces > open_braces:
            repaired = '{' * (close_braces - open_braces) + repaired
        
        # Fix array brackets
        open_brackets = repaired.count('[')
        close_brackets = repaired.count(']')
        if open_brackets > close_brackets:
            repaired += ']' * (open_brackets - close_brackets)
        elif close_brackets > open_brackets:
            repaired = '[' * (close_brackets - open_brackets) + repaired
        
        return repaired
    
    def _repair_extract_valid(self, json_str: str) -> Optional[str]:
        """Extract valid JSON from malformed string."""
        # Try to find valid JSON objects
        json_objects = []
        
        # Find all potential JSON objects
        brace_count = 0
        start_idx = -1
        
        for i, char in enumerate(json_str):
            if char == '{':
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and start_idx != -1:
                    potential_json = json_str[start_idx:i+1]
                    try:
                        json.loads(potential_json)
                        json_objects.append(potential_json)
                    except json.JSONDecodeError:
                        pass
        
        if json_objects:
            # Return the largest valid JSON object
            return max(json_objects, key=len)
        
        return None
    
    def validate_against_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """
        Validate data against expected schema.
        
        Args:
            data: The parsed JSON data
            schema: The expected schema
            
        Returns:
            True if data matches schema, False otherwise
        """
        if not isinstance(data, dict):
            return False
        
        # Check required fields
        required_fields = schema.get('required', [])
        for field in required_fields:
            if field not in data:
                logger.debug(f"Missing required field: {field}")
                return False
        
        # Check field types
        properties = schema.get('properties', {})
        for field, value in data.items():
            if field in properties:
                expected_type = properties[field].get('type')
                if expected_type and not self._check_type(value, expected_type):
                    logger.debug(f"Field {field} has wrong type. Expected {expected_type}, got {type(value)}")
                    return False
        
        return True
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        type_mapping = {
            'string': str,
            'number': (int, float),
            'integer': int,
            'boolean': bool,
            'array': list,
            'object': dict
        }
        
        if expected_type in type_mapping:
            expected_python_type = type_mapping[expected_type]
            return isinstance(value, expected_python_type)
        
        return True  # Unknown type, assume valid
