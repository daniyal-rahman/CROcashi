"""
Schema Validation for LLM JSON Responses

Provides validation and normalization for LLM-generated JSON responses
to ensure data quality and consistency.
"""

import logging
from typing import Dict, Any, List, Optional, Union, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FieldType(Enum):
    """Supported field types for validation."""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    CONFIDENCE_SCORE = "confidence_score"  # Special type for 0.0-1.0 scores


@dataclass
class FieldSchema:
    """Schema definition for a single field."""
    name: str
    field_type: FieldType
    required: bool = True
    default_value: Any = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    validator_func: Optional[Callable[[Any], Any]] = None


@dataclass
class SchemaDefinition:
    """Complete schema definition for validation."""
    fields: List[FieldSchema]
    strict_mode: bool = True  # Whether to reject unknown fields


class SchemaValidator:
    """Validates and normalizes LLM JSON responses against schemas."""
    
    def __init__(self, schema: SchemaDefinition):
        self.schema = schema
        self.field_map = {field.name: field for field in schema.fields}
    
    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize data against the schema.
        
        Args:
            data: Raw data to validate
            
        Returns:
            Validated and normalized data
            
        Raises:
            ValidationError: If validation fails
        """
        validated_data = {}
        errors = []
        
        # Check for unknown fields in strict mode
        if self.schema.strict_mode:
            unknown_fields = set(data.keys()) - set(self.field_map.keys())
            if unknown_fields:
                logger.warning(f"Unknown fields found: {unknown_fields}")
        
        # Validate each field
        for field_schema in self.schema.fields:
            field_name = field_schema.name
            field_value = data.get(field_name)
            
            try:
                validated_value = self._validate_field(field_schema, field_value)
                validated_data[field_name] = validated_value
            except Exception as e:
                error_msg = f"Field '{field_name}' validation failed: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
                
                # Use default value if available
                if field_schema.default_value is not None:
                    validated_data[field_name] = field_schema.default_value
                    logger.info(f"Using default value for field '{field_name}': {field_schema.default_value}")
                elif field_schema.required:
                    raise ValidationError(f"Required field '{field_name}' validation failed: {e}")
        
        # Add any missing optional fields with defaults
        for field_schema in self.schema.fields:
            if not field_schema.required and field_schema.name not in validated_data:
                if field_schema.default_value is not None:
                    validated_data[field_schema.name] = field_schema.default_value
        
        if errors:
            logger.warning(f"Validation completed with {len(errors)} errors")
        
        return validated_data
    
    def _validate_field(self, field_schema: FieldSchema, value: Any) -> Any:
        """Validate a single field."""
        field_name = field_schema.name
        field_type = field_schema.field_type
        
        # Handle None values
        if value is None:
            if field_schema.required:
                raise ValidationError(f"Required field '{field_name}' is None")
            return field_schema.default_value
        
        # Apply custom validator if provided
        if field_schema.validator_func:
            return field_schema.validator_func(value)
        
        # Type-specific validation
        if field_type == FieldType.STRING:
            return self._validate_string(value, field_schema)
        elif field_type == FieldType.NUMBER:
            return self._validate_number(value, field_schema)
        elif field_type == FieldType.INTEGER:
            return self._validate_integer(value, field_schema)
        elif field_type == FieldType.BOOLEAN:
            return self._validate_boolean(value, field_schema)
        elif field_type == FieldType.ARRAY:
            return self._validate_array(value, field_schema)
        elif field_type == FieldType.OBJECT:
            return self._validate_object(value, field_schema)
        elif field_type == FieldType.CONFIDENCE_SCORE:
            return self._validate_confidence_score(value, field_schema)
        else:
            raise ValidationError(f"Unknown field type: {field_type}")
    
    def _validate_string(self, value: Any, field_schema: FieldSchema) -> str:
        """Validate string field."""
        if not isinstance(value, str):
            # Try to convert to string
            try:
                return str(value)
            except Exception:
                raise ValidationError(f"Value '{value}' cannot be converted to string")
        
        return value.strip()
    
    def _validate_number(self, value: Any, field_schema: FieldSchema) -> float:
        """Validate number field."""
        if isinstance(value, (int, float)):
            num_value = float(value)
        elif isinstance(value, str):
            try:
                num_value = float(value)
            except ValueError:
                raise ValidationError(f"Value '{value}' cannot be converted to number")
        else:
            raise ValidationError(f"Value '{value}' is not a valid number")
        
        # Check min/max constraints
        if field_schema.min_value is not None and num_value < field_schema.min_value:
            raise ValidationError(f"Value {num_value} is below minimum {field_schema.min_value}")
        if field_schema.max_value is not None and num_value > field_schema.max_value:
            raise ValidationError(f"Value {num_value} is above maximum {field_schema.max_value}")
        
        return num_value
    
    def _validate_integer(self, value: Any, field_schema: FieldSchema) -> int:
        """Validate integer field."""
        if isinstance(value, int):
            int_value = value
        elif isinstance(value, float):
            if value.is_integer():
                int_value = int(value)
            else:
                raise ValidationError(f"Value '{value}' is not an integer")
        elif isinstance(value, str):
            try:
                int_value = int(float(value))
            except ValueError:
                raise ValidationError(f"Value '{value}' cannot be converted to integer")
        else:
            raise ValidationError(f"Value '{value}' is not a valid integer")
        
        # Check min/max constraints
        if field_schema.min_value is not None and int_value < field_schema.min_value:
            raise ValidationError(f"Value {int_value} is below minimum {field_schema.min_value}")
        if field_schema.max_value is not None and int_value > field_schema.max_value:
            raise ValidationError(f"Value {int_value} is above maximum {field_schema.max_value}")
        
        return int_value
    
    def _validate_boolean(self, value: Any, field_schema: FieldSchema) -> bool:
        """Validate boolean field."""
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            lower_value = value.lower().strip()
            if lower_value in ['true', 'yes', 'y', '1', 'on']:
                return True
            elif lower_value in ['false', 'no', 'n', '0', 'off']:
                return False
            else:
                raise ValidationError(f"String value '{value}' cannot be converted to boolean")
        elif isinstance(value, (int, float)):
            return bool(value)
        else:
            raise ValidationError(f"Value '{value}' cannot be converted to boolean")
    
    def _validate_array(self, value: Any, field_schema: FieldSchema) -> List[Any]:
        """Validate array field."""
        if isinstance(value, list):
            return value
        elif isinstance(value, str):
            # Try to parse as JSON array
            try:
                import json
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
                else:
                    raise ValidationError(f"String '{value}' does not represent an array")
            except json.JSONDecodeError:
                # Treat as single-item list
                return [value]
        else:
            # Convert single value to list
            return [value]
    
    def _validate_object(self, value: Any, field_schema: FieldSchema) -> Dict[str, Any]:
        """Validate object field."""
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            try:
                import json
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
                else:
                    raise ValidationError(f"String '{value}' does not represent an object")
            except json.JSONDecodeError:
                raise ValidationError(f"String '{value}' is not valid JSON")
        else:
            raise ValidationError(f"Value '{value}' is not a valid object")
    
    def _validate_confidence_score(self, value: Any, field_schema: FieldSchema) -> float:
        """Validate confidence score field (0.0-1.0 range)."""
        from .json_parser import validate_confidence_score
        return validate_confidence_score(value, field_schema.name)


class ValidationError(Exception):
    """Exception raised when validation fails."""
    pass


# Predefined schemas for common LLM responses
def create_literature_review_schema() -> SchemaDefinition:
    """Create schema for literature review responses."""
    return SchemaDefinition(
        fields=[
            FieldSchema("relevant_trials", FieldType.ARRAY, required=True, default_value=[]),
            FieldSchema("relevant_papers", FieldType.ARRAY, required=True, default_value=[]),
            FieldSchema("confidence_score", FieldType.CONFIDENCE_SCORE, required=True, default_value=0.5),
            FieldSchema("search_notes", FieldType.STRING, required=False, default_value=""),
        ],
        strict_mode=False
    )


def create_independent_analysis_schema() -> SchemaDefinition:
    """Create schema for independent analysis responses."""
    return SchemaDefinition(
        fields=[
            FieldSchema("gpt5_p_fail", FieldType.CONFIDENCE_SCORE, required=True, default_value=0.5),
            FieldSchema("mechanistic_analysis", FieldType.STRING, required=True, default_value=""),
            FieldSchema("class_prior_analysis", FieldType.STRING, required=True, default_value=""),
            FieldSchema("independent_risk_factors", FieldType.ARRAY, required=True, default_value=[]),
            FieldSchema("agreement_with_deterministic", FieldType.CONFIDENCE_SCORE, required=True, default_value=0.5),
            FieldSchema("additional_insights", FieldType.ARRAY, required=True, default_value=[]),
            FieldSchema("research_sources", FieldType.ARRAY, required=True, default_value=[]),
            FieldSchema("confidence_level", FieldType.STRING, required=True, default_value="Low", 
                      allowed_values=["High", "Medium", "Low"]),
            FieldSchema("strong_red_flags", FieldType.ARRAY, required=True, default_value=[]),
            FieldSchema("recommendation", FieldType.STRING, required=True, default_value=""),
            FieldSchema("reasoning", FieldType.STRING, required=False, default_value=""),
        ],
        strict_mode=False
    )


def create_study_card_schema() -> SchemaDefinition:
    """Create schema for study card responses."""
    return SchemaDefinition(
        fields=[
            FieldSchema("study_card_data", FieldType.OBJECT, required=True, default_value={}),
            FieldSchema("field_quotes", FieldType.ARRAY, required=True, default_value=[]),
        ],
        strict_mode=False
    )


def create_factsheet_schema() -> SchemaDefinition:
    """Create schema for results factsheet responses."""
    return SchemaDefinition(
        fields=[
            FieldSchema("results_data", FieldType.OBJECT, required=True, default_value={}),
            FieldSchema("field_quotes", FieldType.ARRAY, required=True, default_value=[]),
        ],
        strict_mode=False
    )


def create_llm_decider_schema() -> SchemaDefinition:
    """Create schema for LLM decider responses."""
    return SchemaDefinition(
        fields=[
            FieldSchema("company_name", FieldType.STRING, required=True, default_value=""),
            FieldSchema("confidence", FieldType.CONFIDENCE_SCORE, required=True, default_value=0.0),
            FieldSchema("match_type", FieldType.STRING, required=True, default_value="uncertain",
                      allowed_values=["exact", "fuzzy", "uncertain"]),
            FieldSchema("evidence", FieldType.ARRAY, required=True, default_value=[]),
            FieldSchema("reasoning", FieldType.STRING, required=True, default_value=""),
            FieldSchema("flags", FieldType.ARRAY, required=True, default_value=[]),
            FieldSchema("ticker", FieldType.STRING, required=False, default_value=""),
        ],
        strict_mode=False
    )


# Convenience functions
def validate_literature_review(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate literature review response."""
    validator = SchemaValidator(create_literature_review_schema())
    return validator.validate(data)


def validate_independent_analysis(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate independent analysis response."""
    validator = SchemaValidator(create_independent_analysis_schema())
    return validator.validate(data)


def validate_study_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate study card response."""
    validator = SchemaValidator(create_study_card_schema())
    return validator.validate(data)


def validate_factsheet(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate factsheet response."""
    validator = SchemaValidator(create_factsheet_schema())
    return validator.validate(data)


def validate_llm_decider(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate LLM decider response."""
    validator = SchemaValidator(create_llm_decider_schema())
    return validator.validate(data)
