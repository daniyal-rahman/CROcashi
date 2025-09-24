"""
LLM Factsheet Extractor

Extracts Factsheet data with provenance-first extraction and JSONB sections.
Supports all study types with flexible schema.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json

from ..models.evidence_field import EvidenceField
from ...llm.base_worker import BaseLLMWorker
from ...llm.json_parser import parse_llm_json_response, validate_confidence_score
from ..classifiers.study_type_classifier import StudyTypeClassifier
from ..utils.json_repair import JSONRepairUtil
from ...db.models import Factsheet
from ..normalization.facts_normalizer import FactsNormalizer

logger = logging.getLogger(__name__)


class LLMFactsheetExtractor(BaseLLMWorker):
    """Extracts Factsheet data with provenance-first extraction and flexible schema."""
    
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        super().__init__("LLMFactsheetExtractor", "2.0.0", llm_config)
        self.study_classifier = StudyTypeClassifier()
        self.json_repair = JSONRepairUtil()
        self.facts_normalizer = FactsNormalizer()
    
    
    async def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract Factsheet data with provenance-first extraction.
        
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
            
            # Step 1: Classify study type
            study_type = self.study_classifier.classify(raw_doc_text)
            study_context = self.study_classifier.get_study_type_context(study_type)
            
            self.logger.info(f"Classified study type: {study_type}")
            
            # Step 2: Build extraction prompt based on study type
            prompt = self._build_flexible_prompt(raw_doc_text, doc_id, trial_context, study_type, study_context)
            
            # Step 3: Make LLM call with token limit
            response = await self.call_llm(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=8000,  # Token limit to prevent parsing issues
                json_output=True,
                json_schema=self._get_flexible_json_schema()
            )
            
            # Step 4: Parse and repair JSON response
            result = response.content
            if isinstance(result, str):
                # Try direct parsing first
                try:
                    parsed_result = json.loads(result)
                except json.JSONDecodeError:
                    # Attempt repair
                    self.logger.warning("JSON parsing failed, attempting repair")
                    parsed_result = self.json_repair.repair_json(result, self._get_flexible_json_schema())
                    
                    if not parsed_result:
                        return {
                            "factsheet": None,
                            "field_quotes": [],
                            "success": False,
                            "error_message": "Failed to parse LLM JSON response after repair attempts"
                        }
                
                result = parsed_result
            
            # Step 5: Extract data and provenance
            factsheet_sections = result.get("factsheet_sections", {})
            provenance = result.get("provenance", {})
            
            # Step 6: Normalize facts
            normalized_facts = self.facts_normalizer.normalize_facts(factsheet_sections)
            
            # Step 7: Validate content
            if not self._has_meaningful_content(factsheet_sections):
                error_msg = "No meaningful content generated"
                if result.get("reason"):
                    error_msg += f" - LLM reason: {result['reason']}"
                self.logger.warning(f"Factsheet extraction produced no meaningful content for doc_id: {doc_id}")
                return {
                    "factsheet": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": error_msg
                }
            
            # Step 8: Create Factsheet object with new schema
            factsheet = Factsheet(
                doc_id=doc_id,
                study_type=study_type,
                factsheet_sections=factsheet_sections,
                provenance=provenance,
                normalized_facts=normalized_facts,
                # Keep legacy fields for backward compatibility
                results=factsheet_sections.get("results", []),
                primary_endpoint_results=factsheet_sections.get("primary_endpoint_results"),
                secondary_endpoint_results=factsheet_sections.get("secondary_endpoint_results", []),
                safety_results=factsheet_sections.get("safety_results", []),
                total_enrolled=factsheet_sections.get("total_enrolled"),
                dropout_rate=factsheet_sections.get("dropout_rate")
            )
            
            # Step 9: Parse field quotes from provenance
            field_quotes = self._parse_provenance_quotes(provenance)
            
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
    
    def _has_meaningful_content(self, factsheet_sections: Dict[str, Any]) -> bool:
        """Check if factsheet sections contain meaningful content."""
        # Check if any field has non-empty content
        for field, value in factsheet_sections.items():
            if value and str(value).strip():
                return True
        
        return False
    
    def _parse_provenance_quotes(self, provenance: Dict[str, Any]) -> List[Any]:
        """Parse provenance into EvidenceField objects."""
        from ..models.evidence_field import EvidenceField
        
        field_quotes = []
        
        for field_name, field_data in provenance.items():
            if isinstance(field_data, dict) and 'quotes' in field_data:
                quotes = field_data['quotes']
                if isinstance(quotes, list):
                    for quote in quotes:
                        if isinstance(quote, dict) and 'text' in quote:
                            field_quotes.append(EvidenceField(
                                field_name=field_name,
                                value=field_data.get('value'),
                                evidence_quote=quote['text'],
                                confidence=quote.get('confidence', 0.8)
                            ))
        
        return field_quotes
    
    def _build_flexible_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any], 
                             study_type: str, study_context: Dict[str, Any]) -> str:
        """Build flexible prompt based on study type."""
        focus_areas = study_context.get('focus_areas', [])
        extraction_guidance = study_context.get('extraction_guidance', '')
        expected_fields = study_context.get('expected_fields', [])
        
        return f"""
You are a scientific literature expert. Extract important facts from this document.

STUDY TYPE: {study_type.upper()}
EXTRACTION GUIDANCE: {extraction_guidance}

Document Text:
{doc_text}

Extract the following information into structured sections:

1. KEY FINDINGS: Main results, conclusions, or important discoveries
2. EFFICACY DATA: Any effectiveness measures (clinical endpoints, preclinical efficacy, etc.)
3. SAFETY DATA: Safety information, adverse events, toxicity data
4. MECHANISM DATA: How the treatment works, biological mechanisms
5. DOSING DATA: Administration details, doses, schedules
6. POPULATION DATA: Who was studied (patients, animals, cells, demographics)
7. BIOMARKER DATA: Any biomarker information, surrogate endpoints
8. LIMITATIONS: Study limitations, caveats, or concerns

CRITICAL REQUIREMENTS:
- Extract facts from ANY type of study (clinical, preclinical, review, etc.)
- For each populated field, provide provenance with exact text quotes
- Include location information (section, approximate character positions)
- If a field is not applicable, omit it entirely
- Be flexible with data types and formats
- Focus on: {', '.join(focus_areas)}
- IMPORTANT: Extract ALL available information - don't omit fields just because they don't contain specific data types
- For preclinical studies, extract mechanism data, efficacy data, and any other relevant findings
- For clinical studies, extract all available endpoints, safety data, and population information

RESPONSE STRUCTURE:
You must return a JSON object with these top-level keys:
- "factsheet_sections": An object containing the extracted field values
- "provenance": An object with field-level provenance information
- "reason": (optional) A brief explanation if no meaningful information was found

Each field in "provenance" should have:
- "value": The extracted value
- "quotes": Array of quote objects with "text" and "loc" (location info)

The response will be automatically formatted according to the required schema.
"""
    
    def _get_flexible_json_schema(self) -> Dict[str, Any]:
        """Return the flexible JSON schema for factsheet extraction."""
        return {
            "type": "object",
            "properties": {
                "factsheet_sections": {
                    "type": "object",
                    "properties": {
                        "key_findings": {"type": "string"},
                        "efficacy_data": {"type": "string"},
                        "safety_data": {"type": "string"},
                        "mechanism_data": {"type": "string"},
                        "dosing_data": {"type": "string"},
                        "population_data": {"type": "string"},
                        "biomarker_data": {"type": "string"},
                        "limitations": {"type": "string"},
                        # Legacy fields for backward compatibility
                        "results": {"type": "string"},
                        "primary_endpoint_results": {"type": "string"},
                        "secondary_endpoint_results": {"type": "string"},
                        "safety_results": {"type": "string"},
                        "total_enrolled": {"type": "number"},
                        "dropout_rate": {"type": "number"}
                    }
                },
                "provenance": {
                    "type": "object",
                    "patternProperties": {
                        "^[a-z_]+$": {
                            "type": "object",
                            "properties": {
                                "value": {"type": ["string", "number", "boolean"]},
                                "quotes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "text": {"type": "string", "minLength": 10},
                                            "loc": {
                                                "type": "object",
                                                "properties": {
                                                    "doc_id": {"type": "string"},
                                                    "section": {"type": "string"},
                                                    "start": {"type": "number"},
                                                    "end": {"type": "number"}
                                                }
                                            },
                                            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                                        },
                                        "required": ["text", "loc"]
                                    }
                                }
                            },
                            "required": ["value", "quotes"]
                        }
                    }
                },
                "reason": {
                    "type": "string",
                    "description": "Optional explanation if no meaningful information was found"
                }
            },
            "required": ["factsheet_sections", "provenance"]
        }
    
    def _build_standard_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build the standard prompt for factsheet extraction (legacy method)."""
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
    
