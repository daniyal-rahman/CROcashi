"""
LLM Results Factsheet Extractor

Extracts ResultsFactsheet data with evidence quotes for each field.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ..models.results_factsheet import ResultsFactsheet
from ..models.evidence_field import EvidenceField
from ...llm.base_worker import BaseLLMExtractor
from ...llm.json_parser import parse_llm_json_response, validate_confidence_score

logger = logging.getLogger(__name__)


class LLMResultsFactsheetExtractor(BaseLLMExtractor):
    """Extracts ResultsFactsheet data directly with evidence quotes."""
    
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        super().__init__("LLMResultsFactsheetExtractor", llm_config)
    
    async def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate ResultsFactsheet with evidence quotes.
        
        Args:
            inputs: {
                "raw_doc_text": str,
                "doc_id": str,
                "trial_context": Dict[str, Any]
            }
            
        Returns:
            {
                "results_factsheet": ResultsFactsheet,
                "field_quotes": List[EvidenceField],
                "success": bool,
                "error_message": Optional[str]
            }
        """
        try:
            raw_doc_text = inputs.get("raw_doc_text", "")
            doc_id = inputs.get("doc_id", "")
            trial_context = inputs.get("trial_context", {})
            
            if not raw_doc_text or not doc_id:
                self.logger.error("Missing required inputs: raw_doc_text and doc_id")
                return {
                    "results_factsheet": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": "Missing required inputs"
                }
            
            self.logger.info(f"Generating results factsheet for doc_id: {doc_id}")
            
            # Generate results factsheet with evidence quotes
            results_data, field_quotes = await self._generate_results_with_quotes(
                raw_doc_text, doc_id, trial_context
            )
            
            # Check success criteria - must have meaningful content
            has_meaningful_content = (
                results_data.get("primary_endpoint_results") or
                results_data.get("results") or
                results_data.get("safety_results") or
                len(field_quotes) > 0
            )
            
            if not has_meaningful_content:
                self.logger.warning(f"Results factsheet generation produced no meaningful content for doc_id: {doc_id}")
                return {
                    "results_factsheet": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": "No meaningful content generated"
                }
            
            # Create ResultsFactsheet object with proper field mapping
            results_factsheet = ResultsFactsheet(
                doc_id=doc_id,
                results=results_data.get("results", []),
                primary_endpoint_results=results_data.get("primary_endpoint_results"),
                secondary_endpoint_results=results_data.get("secondary_endpoint_results", []),
                safety_results=results_data.get("safety_results", []),
                primary_analysis_set=results_data.get("primary_analysis_set"),
                secondary_analysis_sets=results_data.get("secondary_analysis_sets", []),
                total_enrolled=results_data.get("total_enrolled"),
                completed_primary_endpoint=results_data.get("completed_primary_endpoint"),
                dropout_rate=results_data.get("dropout_rate"),
                follow_up_completion=results_data.get("follow_up_completion")
            )
            
            return {
                "results_factsheet": results_factsheet,
                "field_quotes": field_quotes,
                "success": True,
                "error_message": None
            }
            
        except Exception as e:
            self.logger.error(f"Results factsheet generation failed: {e}")
            return {
                "results_factsheet": None,
                "field_quotes": [],
                "success": False,
                "error_message": str(e)
            }
    
    def _get_data_key(self) -> str:
        """Return the key for the main data in the LLM response."""
        return "results_data"
    
    def _get_meaningful_fields(self) -> List[str]:
        """Return the list of fields that indicate meaningful data for this extractor."""
        return [
            "results", "primary_endpoint_results", "secondary_endpoint_results",
            "safety_results", "total_enrolled", "dropout_rate"
        ]
    
    def _build_extraction_prompt(self, doc_text: str, doc_id: str, context: Dict[str, Any]) -> str:
        """Build the extraction prompt for this specific extractor."""
        return self._build_standard_prompt(doc_text, doc_id, context)
    
    def _get_json_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for this extractor's LLM calls."""
        return {
            "type": "object",
            "properties": {
                "results_data": {
                    "type": "object",
                    "properties": {
                        "results": {"type": "string"},
                        "primary_endpoint_results": {"type": "string"},
                        "secondary_endpoint_results": {"type": "string"},
                        "safety_results": {"type": "string"},
                        "total_enrolled": {"type": "number"},
                        "dropout_rate": {"type": "number"}
                    }
                },
                "field_quotes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field_name": {
                                "type": "string",
                                "pattern": "^[a-z][a-z0-9_]*$"
                            },
                            "value": {"type": ["string", "number", "boolean"]},
                            "evidence_quote": {
                                "type": "string",
                                "minLength": 10,
                                "pattern": "^[A-Za-z].*[A-Za-z]$"
                            },
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                        },
                        "required": ["field_name", "value", "evidence_quote", "confidence"]
                    }
                }
            },
            "required": ["results_data", "field_quotes"]
        }
    
    
    async def _extract_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Extract results factsheet data using LLM with the given prompt."""
        return await self._extract_results_factsheet_with_llm(doc_text, trial_context, prompt)
    
    async def _generate_results_with_quotes(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> tuple:
        """Generate results factsheet data with evidence quotes for each field."""
        
        try:
            # Use the standard prompt
            prompt = self._build_standard_prompt(doc_text, trial_context)
            
            self.logger.info(f"Making LLM call for {self.name} extraction")
            
            result = await self._extract_results_factsheet_with_llm(doc_text, trial_context, prompt)
            self.logger.info(f"DEBUG: LLM extraction result keys: {list(result.keys())}")
            self.logger.info(f"DEBUG: LLM extraction result field_quotes: {result.get('field_quotes', [])}")
            
            results_data = result.get("results_data", {})
            field_quotes = []
            
            for evidence_field_data in result.get("field_quotes", []):
                self.logger.info(f"DEBUG: Processing evidence_field_data: {evidence_field_data}")
                
                # Validate that evidence_field_data is a dictionary
                if not isinstance(evidence_field_data, dict):
                    self.logger.error(f"Evidence field data is not a dictionary, got {type(evidence_field_data)}: {evidence_field_data}")
                    self.logger.error("This indicates the LLM returned malformed JSON with numbers instead of evidence field objects.")
                    continue
                
                # Validate field_name is a string
                field_name = evidence_field_data.get("field_name", "")
                if not isinstance(field_name, str):
                    self.logger.warning(f"Malformed field_name with non-string value '{field_name}' (type: {type(field_name)}) - skipping evidence field")
                    self.logger.warning(f"Full LLM response for debugging: {result}")
                    continue
                
                # Validate and clean evidence_quote
                evidence_quote = evidence_field_data.get("evidence_quote", "")
                if not isinstance(evidence_quote, str):
                    if evidence_quote is None:
                        evidence_quote = ""
                    elif isinstance(evidence_quote, (int, float)):
                        # If it's a number, it's likely malformed - log and skip this evidence field
                        self.logger.warning(f"Malformed evidence_quote with numeric value '{evidence_quote}' for field '{evidence_field_data.get('field_name', 'unknown')}' - skipping evidence field. LLM should return text quotes, not numbers.")
                        self.logger.warning(f"Full LLM response for debugging: {result}")
                        continue
                    else:
                        # Try to convert other types to string
                        evidence_quote = str(evidence_quote)
                
                # Additional validation: ensure evidence_quote is not empty or just whitespace
                if not evidence_quote or not evidence_quote.strip():
                    self.logger.warning(f"Empty or whitespace-only evidence_quote - skipping evidence field")
                    continue
                
                # Validate confidence score
                confidence = evidence_field_data.get("confidence", 0.8)
                try:
                    confidence = validate_confidence_score(confidence)
                except ValueError as e:
                    self.logger.warning(f"Invalid confidence score '{confidence}': {e} - using default 0.8")
                    confidence = 0.8
                
                field_quotes.append(EvidenceField(
                    field_name=evidence_field_data.get("field_name", ""),
                    value=evidence_field_data.get("value"),
                    evidence_quote=evidence_quote,
                    confidence=confidence
                ))
            
            self.logger.info(f"DEBUG: Generated {len(field_quotes)} field quotes")
            return results_data, field_quotes
            
        except Exception as e:
            self.logger.error(f"LLM results factsheet generation failed: {e}")
            return {}, []
    
    async def _extract_results_factsheet_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Extract results factsheet using LLM with structured output."""
        
        try:
            self.logger.info("Making LLM call for results factsheet extraction")
            
            # Validate inputs before API call
            if not doc_text or not doc_text.strip():
                raise ValueError("Empty doc_text provided to LLM")
            if not prompt or not prompt.strip():
                raise ValueError("Empty prompt provided to LLM")
            
            # Log redacted payload preview
            self.logger.debug(f"LLM payload preview: doc_text_length={len(doc_text)}, prompt_length={len(prompt)}")
            
            # Make LLM call with structured JSON schema
            json_schema = {
                "type": "object",
                "properties": {
                    "results_data": {
                        "type": "object",
                        "properties": {
                            "results": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "metric": {"type": "string"},
                                        "value": {"type": ["string", "number", "boolean"]},
                                        "units": {"type": ["string", "null"]},
                                        "timepoint": {"type": ["string", "number", "null"]},
                                        "analysis_set": {"type": ["string", "null"]},
                                        "population_slice": {"type": ["string", "null"]},
                                        "is_posthoc": {"type": "boolean"},
                                        "flags": {"type": "array", "items": {"type": "string"}},
                                        "span_ids": {"type": "array", "items": {"type": ["string", "integer"]}},
                                        "doc_id": {"type": ["string", "integer"]}
                                    }
                                }
                            },
                            "primary_endpoint_results": {"type": "object"},
                            "secondary_endpoint_results": {"type": "array"},
                            "safety_results": {"type": "array"},
                            "primary_analysis_set": {"type": "string"},
                            "secondary_analysis_sets": {"type": "array", "items": {"type": "string"}},
                            "total_enrolled": {"type": ["integer", "null"]},
                            "completed_primary_endpoint": {"type": ["integer", "null"]},
                            "dropout_rate": {"type": ["number", "null"]},
                            "follow_up_completion": {"type": ["number", "null"]}
                        }
                    },
                    "field_quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field_name": {
                                    "type": "string",
                                    "pattern": "^[a-z][a-z0-9_]*$"
                                },
                                "value": {"type": ["string", "number", "boolean"]},
                                "evidence_quote": {
                                    "type": "string",
                                    "minLength": 10,
                                    "pattern": "^[A-Za-z].*[A-Za-z]$"
                                },
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                            },
                            "required": ["field_name", "value", "evidence_quote", "confidence"]
                        }
                    }
                },
                "required": ["results_data", "field_quotes"]
            }
            
            response = await self.call_llm(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
                json_schema=json_schema
            )
            
            # Parse the response
            result = response.content
            self.logger.info(f"LLM response type: {type(result)}")
            self.logger.info(f"LLM response content preview: {str(result)[:500]}...")
            
            if isinstance(result, str):
                # Use robust JSON parsing
                parsed_result = parse_llm_json_response(result, expected_fields=["results_data", "field_quotes"])
                if parsed_result:
                    result = parsed_result
                    self.logger.info(f"DEBUG: Parsed JSON successfully")
                else:
                    self.logger.error(f"DEBUG: JSON parsing failed")
                    self.logger.error(f"DEBUG: Raw response: {result}")
                    return {}
            elif isinstance(result, (int, float)):
                # Handle case where LLM returns a number instead of JSON
                self.logger.error(f"LLM returned a number instead of JSON: {result}")
                return {}
            elif not isinstance(result, dict):
                # Handle other unexpected types
                self.logger.error(f"LLM returned unexpected type {type(result)}: {result}")
                return {}
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM results factsheet extraction failed: {e}")
            return {}
    
    def _build_standard_prompt(self, doc_text: str, trial_context: Dict[str, Any]) -> str:
        """Build standard prompt for results extraction."""
        # Truncate doc_text to avoid token limits
        truncated_doc_text = doc_text[:4000]
        
        return f"""
You are a clinical trial results expert. Extract results information from this clinical trial document and provide evidence quotes for each field you fill.

Document Text:
{truncated_doc_text}

Trial Context:
- Trial ID: {trial_context.get('trial_id', 'Unknown')}
- Disease: {trial_context.get('disease', 'Unknown')}
- Intervention: {trial_context.get('intervention', 'Unknown')}

For each field you fill, provide:
1. The extracted value
2. A direct quote from the document that supports this value
3. Your confidence in the extraction (0.0-1.0)

Extract the following results fields:

**Results Array:**
- results: List of individual result items with metric, value, units, etc.

**Primary Endpoint:**
- primary_endpoint_results: Single result object for primary endpoint

**Secondary Endpoints:**
- secondary_endpoint_results: List of result objects for secondary endpoints

**Safety:**
- safety_results: List of result objects for safety metrics

**Analysis Sets:**
- primary_analysis_set: Primary analysis population (e.g., "ITT", "mITT", "PP")
- secondary_analysis_sets: List of secondary analysis populations

**Study Completion:**
- total_enrolled: Total number of enrolled patients
- completed_primary_endpoint: Number who completed primary endpoint
- dropout_rate: Dropout rate as decimal
- follow_up_completion: Follow-up completion rate as decimal

CRITICAL REQUIREMENTS:
1. Only include fields where you found clear evidence in the document
2. For each field you extract, provide the exact text quote from the document that supports it
3. field_name must ALWAYS be a text string (never a number like 2017.0)
4. evidence_quote must ALWAYS be a text string containing actual words from the document (never a number like 5.0)
5. value can be a string, number, or boolean depending on the field type
6. If a field is not mentioned, omit it entirely
7. IMPORTANT: Never use numeric values as field names or evidence quotes

The response will be automatically formatted according to the required schema.
"""
