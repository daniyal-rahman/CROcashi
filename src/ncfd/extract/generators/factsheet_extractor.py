"""
LLM Factsheet Extractor

Extracts Factsheet data with evidence quotes for each field.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ..models.factsheet import Factsheet
from ..models.evidence_field import EvidenceField
from ...llm.base_worker import BaseLLMWorker
from ...llm.json_parser import parse_llm_json_response, validate_confidence_score

logger = logging.getLogger(__name__)


class LLMFactsheetExtractor(BaseLLMWorker):
    """Extracts Factsheet data directly with evidence quotes."""
    
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        super().__init__("LLMFactsheetExtractor", "1.0.0", llm_config)
    
    
    async def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract Factsheet data with evidence quotes.
        
        Args:
            inputs: {
                "raw_doc_text": str,
                "doc_id": str,
                "trial_context": Dict[str, Any]
            }
            
        Returns:
            {
                "factsheet": Factsheet,
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
                    "factsheet": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": "Missing required inputs"
                }
            
            self.logger.info(f"Extracting factsheet for doc_id: {doc_id}")
            
            # Build extraction prompt
            prompt = self._build_standard_prompt(raw_doc_text, doc_id, trial_context)
            
            # Make LLM call using BaseLLMWorker interface
            response = await self.call_llm(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
                json_output=True,
                json_schema=self._get_json_schema()
            )
            
            # Parse response
            result = response.content
            if isinstance(result, str):
                parsed_result = parse_llm_json_response(result, expected_fields=["factsheet_data", "field_quotes"])
                if parsed_result:
                    result = parsed_result
                else:
                    return {
                        "factsheet": None,
                        "field_quotes": [],
                        "success": False,
                        "error_message": "Failed to parse LLM JSON response"
                    }
            
            # Extract data and field quotes
            factsheet_data = result.get("factsheet_data", {})
            field_quotes = self._parse_field_quotes(result)
            reason = result.get("reason", "")
            
            # Debug logging for extracted data
            self.logger.info(f"🔍 EXTRACTED DATA DEBUG:")
            self.logger.info(f"   factsheet_data keys: {list(factsheet_data.keys()) if isinstance(factsheet_data, dict) else 'Not a dict'}")
            self.logger.info(f"   field_quotes count: {len(field_quotes)}")
            if reason:
                self.logger.info(f"   reason: {reason}")
            
            # Check success criteria - must have meaningful content
            has_meaningful_content = (
                factsheet_data.get("primary_endpoint_results") or
                factsheet_data.get("results") or
                factsheet_data.get("safety_results") or
                len(field_quotes) > 0
            )
            
            if not has_meaningful_content:
                error_msg = "No meaningful content generated"
                if reason:
                    error_msg += f" - LLM reason: {reason}"
                self.logger.warning(f"Factsheet extraction produced no meaningful content for doc_id: {doc_id}")
                if reason:
                    self.logger.warning(f"LLM provided reason: {reason}")
                return {
                    "factsheet": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": error_msg
                }
            
            # Create Factsheet object with proper field mapping
            factsheet = Factsheet(
                doc_id=doc_id,
                results=factsheet_data.get("results", []),
                primary_endpoint_results=factsheet_data.get("primary_endpoint_results"),
                secondary_endpoint_results=factsheet_data.get("secondary_endpoint_results", []),
                safety_results=factsheet_data.get("safety_results", []),
                primary_analysis_set=factsheet_data.get("primary_analysis_set"),
                secondary_analysis_sets=factsheet_data.get("secondary_analysis_sets", []),
                total_enrolled=factsheet_data.get("total_enrolled"),
                completed_primary_endpoint=factsheet_data.get("completed_primary_endpoint"),
                dropout_rate=factsheet_data.get("dropout_rate"),
                follow_up_completion=factsheet_data.get("follow_up_completion")
            )
            
            return {
                "factsheet": factsheet,
                "field_quotes": field_quotes,
                "success": True,
                "error_message": None
            }
            
        except Exception as e:
            self.logger.error(f"Factsheet extraction failed: {e}")
            return {
                "factsheet": None,
                "field_quotes": [],
                "success": False,
                "error_message": str(e)
            }
    
    def _parse_field_quotes(self, result: Dict[str, Any]) -> List[Any]:
        """Parse field_quotes from LLM result into EvidenceField objects."""
        from ..models.evidence_field import EvidenceField
        
        field_quotes = []
        raw_field_quotes = result.get("field_quotes", [])
        
        self.logger.info(f"🔍 FIELD QUOTES PROCESSING:")
        self.logger.info(f"   Raw field_quotes count: {len(raw_field_quotes) if isinstance(raw_field_quotes, list) else 'Not a list'}")
        
        if not isinstance(raw_field_quotes, list):
            self.logger.warning(f"LLM returned field_quotes as {type(raw_field_quotes)} instead of list: {raw_field_quotes}")
            raw_field_quotes = []
        
        processed_quotes = 0
        skipped_quotes = 0
        
        for quote_data in raw_field_quotes:
            # Validate that quote_data is a dictionary
            if not isinstance(quote_data, dict):
                self.logger.error(f"Quote data is not a dictionary, got {type(quote_data)}: {quote_data}")
                skipped_quotes += 1
                continue
            
            # Validate field_name is a string
            field_name = quote_data.get("field_name", "")
            if not isinstance(field_name, str):
                self.logger.warning(f"Malformed field_name with non-string value '{field_name}' (type: {type(field_name)}) - skipping quote")
                skipped_quotes += 1
                continue
            
            # Validate and clean evidence_quote
            evidence_quote = quote_data.get("evidence_quote", "")
            if not isinstance(evidence_quote, str):
                if evidence_quote is None:
                    evidence_quote = ""
                elif isinstance(evidence_quote, (int, float)):
                    self.logger.warning(f"Malformed evidence_quote with numeric value '{evidence_quote}' for field '{quote_data.get('field_name', 'unknown')}' - skipping quote")
                    skipped_quotes += 1
                    continue
                else:
                    evidence_quote = str(evidence_quote)
            
            # Additional validation: ensure evidence_quote is not empty or just whitespace
            if not evidence_quote or not evidence_quote.strip():
                self.logger.warning(f"Empty or whitespace-only evidence_quote - skipping quote")
                skipped_quotes += 1
                continue
            
            field_quotes.append(EvidenceField(
                field_name=quote_data.get("field_name", ""),
                value=quote_data.get("value"),
                evidence_quote=evidence_quote,
                confidence=quote_data.get("confidence", 0.8)
            ))
            processed_quotes += 1
        
        self.logger.info(f"🔍 FIELD QUOTES PROCESSING SUMMARY:")
        self.logger.info(f"   Total raw quotes: {len(raw_field_quotes)}")
        self.logger.info(f"   Successfully processed: {processed_quotes}")
        self.logger.info(f"   Skipped: {skipped_quotes}")
        self.logger.info(f"   Final field_quotes count: {len(field_quotes)}")
        
        return field_quotes
    
    def _get_json_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for this extractor's LLM calls."""
        return {
            "type": "object",
            "properties": {
                "factsheet_data": {
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
            "required": ["factsheet_data", "field_quotes"],
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Optional explanation if no results information was found"
                }
            }
        }
    
    
    
    def _build_standard_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build the standard prompt for factsheet extraction."""
        return f"""
You are a clinical trial results expert. Extract results information from this document.

IMPORTANT: Only extract information if this document contains clinical trial results data.

Document Text:
{doc_text}

Extract the following results information:
1. Primary endpoint results
2. Secondary endpoint results  
3. Safety results
4. Total enrolled participants
5. Dropout rate

CRITICAL REQUIREMENTS:
1. Only include fields where you found clear evidence in the document
2. For each field you extract, provide the exact text quote from the document that supports it
3. field_name must ALWAYS be a text string (never a number like 2017.0)
4. evidence_quote must ALWAYS be a text string containing actual words from the document (never a number like 5.0)
5. value can be a string, number, or boolean depending on the field type
6. If no results information is found, include a "reason" field explaining why (e.g., "Document appears to be a methodology section without results", "Document is too short or lacks clinical trial results", "Document contains only background information without trial outcomes")
7. If a field is not mentioned, omit it entirely
8. IMPORTANT: Never use numeric values as field names or evidence quotes

RESPONSE STRUCTURE:
You must return a JSON object with these top-level keys:
- "factsheet_data": An object containing the extracted field values (just the values, not objects)
- "field_quotes": An array of objects, each with field_name, value, evidence_quote, and confidence
- "reason": (optional) A brief explanation if no results information was found

The response will be automatically formatted according to the required schema.
"""
    
