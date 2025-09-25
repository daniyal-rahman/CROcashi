"""
LLM Study Card Extractor

Extracts StudyCard data with evidence quotes for each field.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ...db.models import StudyCard
from ..models.evidence_field import EvidenceField
from ...llm.base_worker import BaseLLMWorker
from ...llm.json_parser import parse_llm_json_response, validate_confidence_score
from ...utils.config_manager import get_config_manager
from ...utils.error_handler import get_error_handler, safe_execute

logger = logging.getLogger(__name__)


class LLMStudyCardExtractor(BaseLLMWorker):
    """Extracts StudyCard data directly with evidence quotes."""
    
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        super().__init__("LLMStudyCardExtractor", "1.0.0", llm_config)
    
    
    async def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate StudyCard with evidence quotes.
        
        Args:
            inputs: {
                "raw_doc_text": str,
                "doc_id": str,
                "trial_context": Dict[str, Any]
            }
            
        Returns:
            {
                "study_card": StudyCard,
                "field_quotes": List[EvidenceField],
                "success": bool,
                "error_message": Optional[str]
            }
        """
        try:
            raw_doc_text = inputs.get("raw_doc_text", "")
            doc_id = inputs.get("doc_id", "")
            trial_context = inputs.get("trial_context", {})
            
            if not raw_doc_text:
                return {
                    "study_card": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": "No document text provided"
                }
            
            self.logger.info(f"Generating study card for doc_id: {doc_id}")
            
            # Build extraction prompt
            prompt = self._build_standard_study_prompt(raw_doc_text, doc_id, trial_context)
            
            # Make LLM call using BaseLLMWorker interface
            response = await self.call_llm(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000,
                json_output=True,
                json_schema=self._get_json_schema()
            )
            
            # Parse response
            result = response.content
            
            # Debug logging to see what the LLM actually returned
            self.logger.info(f"🔍 LLM RAW RESPONSE DEBUG:")
            self.logger.info(f"   Type: {type(result)}")
            self.logger.info(f"   Content length: {len(str(result))}")
            self.logger.info(f"   FULL CONTENT:")
            self.logger.info(f"   {str(result)}")
            
            if isinstance(result, str):
                parsed_result = parse_llm_json_response(result, expected_fields=["study_card_data", "field_quotes"])
                if parsed_result:
                    result = parsed_result
                    self.logger.info(f"✅ JSON PARSING SUCCESSFUL:")
                    self.logger.info(f"   Parsed keys: {list(result.keys())}")
                else:
                    self.logger.error(f"❌ JSON PARSING FAILED:")
                    self.logger.error(f"   Raw response: {result[:1000]}...")
                    return {
                        "study_card": None,
                        "field_quotes": [],
                        "success": False,
                        "error_message": "Failed to parse LLM JSON response"
                    }
            elif isinstance(result, (int, float)):
                self.logger.error(f"❌ LLM RETURNED NUMBER: {result}")
                return {
                    "study_card": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": "LLM returned numeric value instead of JSON"
                }
            elif not isinstance(result, dict):
                self.logger.error(f"❌ LLM RETURNED UNEXPECTED TYPE {type(result)}: {result}")
                return {
                    "study_card": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": f"LLM returned unexpected type {type(result)}"
                }
            
            # Extract data and field quotes
            study_card_data = result.get("study_card_data", {})
            field_quotes = self._parse_field_quotes(result)
            reason = result.get("reason", "")
            
            # Debug logging for extracted data
            self.logger.info(f"🔍 EXTRACTED DATA DEBUG:")
            self.logger.info(f"   study_card_data keys: {list(study_card_data.keys()) if isinstance(study_card_data, dict) else 'Not a dict'}")
            # self.logger.info(f"   study_card_data content: {str(study_card_data)}")
            self.logger.info(f"   field_quotes count: {len(field_quotes)}")
            if reason:
                self.logger.info(f"   reason: {reason}")
            
            # Check success criteria - must have meaningful content
            # Ensure field_quotes is a list before checking length
            if not isinstance(field_quotes, list):
                field_quotes = []
            
            # Enhanced logging for debugging
            meaningful_fields = sum(1 for field in [
                'design_archetype', 'primary_endpoint', 'population_description'
            ] if study_card_data.get(field))
            
            self.logger.info(f"Extraction result for {doc_id}: "
                           f"meaningful_fields={meaningful_fields}, "
                           f"field_quotes_count={len(field_quotes)}, "
                           f"doc_length={len(raw_doc_text)}")
            
            # Check if study_card_data is empty or has no meaningful content
            study_card_data_empty = not study_card_data or len(study_card_data) == 0
            has_meaningful_content = (
                study_card_data.get('design_archetype') or
                study_card_data.get('primary_endpoint') or
                study_card_data.get('population_description') or
                len(field_quotes) > 0
            )
            
            if study_card_data_empty and len(field_quotes) == 0:
                error_msg = "LLM returned empty response - may indicate insufficient content or prompt issue"
                if reason:
                    error_msg += f" - LLM reason: {reason}"
                self.logger.warning(f"Study card generation produced completely empty response for doc_id: {doc_id} "
                                   f"(doc_length={len(raw_doc_text)})")
                if reason:
                    self.logger.warning(f"LLM provided reason: {reason}")
                return {
                    "study_card": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": error_msg
                }
            
            if not has_meaningful_content:
                self.logger.warning(f"Study card generation produced no meaningful content for doc_id: {doc_id} "
                                   f"(meaningful_fields={meaningful_fields}, "
                                   f"field_quotes={len(field_quotes)}, "
                                   f"doc_length={len(raw_doc_text)})")
                return {
                    "study_card": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": "No meaningful content generated"
                }
            
            # Create StudyCard object
            study_card = StudyCard(
                doc_id=doc_id,
                design_archetype=study_card_data.get('design_archetype'),
                is_blinded=study_card_data.get('is_blinded'),
                analysis_set=study_card_data.get('analysis_set'),
                population_description=study_card_data.get('population_description'),
                stratification_factors=study_card_data.get('stratification_factors', []),
                covariate_adjustment=study_card_data.get('covariate_adjustment', []),
                primary_endpoint=study_card_data.get('primary_endpoint'),
                secondary_endpoints=study_card_data.get('secondary_endpoints', []),
                summary_measure=study_card_data.get('summary_measure'),
                alpha_level=study_card_data.get('alpha_level'),
                is_one_sided=study_card_data.get('is_one_sided'),
                multiplicity_adjustment=study_card_data.get('multiplicity_adjustment'),
                sample_size_reassessment=study_card_data.get('sample_size_reassessment'),
                interim_looks=study_card_data.get('interim_looks', []),
                interim_timing=study_card_data.get('interim_timing'),
                spending_function=study_card_data.get('spending_function'),
                stop_rules=study_card_data.get('stop_rules', []),
                missingness_assumption=study_card_data.get('missingness_assumption'),
                missingness_pattern=study_card_data.get('missingness_pattern'),
                imputation_method=study_card_data.get('imputation_method'),
                estimand=study_card_data.get('estimand'),
                intercurrent_events_policy=study_card_data.get('intercurrent_events_policy'),
                endpoint_ascertainment=study_card_data.get('endpoint_ascertainment'),
                assessment_interval=study_card_data.get('assessment_interval'),
                adjudication_committee=study_card_data.get('adjudication_committee')
            )
            
            return {
                "study_card": study_card,
                "field_quotes": field_quotes,
                "success": True,
                "error_message": None
            }
            
        except Exception as e:
            self.logger.error(f"Study card generation failed: {e}")
            return {
                "study_card": None,
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
            self.logger.warning(f"LLM returned field_quotes as {type(raw_field_quotes)} instead of list: {str(raw_field_quotes)}")
            raw_field_quotes = []
        
        processed_quotes = 0
        skipped_quotes = 0
        
        for i, quote_data in enumerate(raw_field_quotes):
            
            # Validate that quote_data is a dictionary
            if not isinstance(quote_data, dict):
                self.logger.error(f"Quote data is not a dictionary, got {type(quote_data)}: {str(quote_data)}")
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
                "study_card_data": {
                    "type": "object",
                    "properties": {
                        "design_archetype": {"type": "string"},
                        "is_blinded": {"type": "boolean"},
                        "analysis_set": {"type": "string"},
                        "population_description": {"type": "string"},
                        "primary_endpoint": {"type": "string"},
                        "statistical_test": {"type": "string"},
                        "alpha_level": {"type": "number"},
                        "is_one_sided": {"type": "boolean"}
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
            "required": ["study_card_data", "field_quotes"],
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Optional explanation if no methodology information was found"
                }
            }
        }
    
    
    def _build_standard_study_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build enhanced prompt for study card extraction with better guidance."""
        return f"""
You are a clinical trial methodology expert. Extract methodology information from this document.

IMPORTANT: This document likely contains clinical trial information. Look carefully for ANY methodology details, even if they are brief or incomplete. Extract whatever information you can find.

NOTE: This is the first 20,000 characters of a longer document. If you don't find methodology information in this excerpt, the full document may contain more details.

Document Text:
{doc_text[:10000]}

Trial Context:
- Trial ID: {trial_context.get('trial_id', 'Unknown')}
- Disease: {trial_context.get('disease', 'Unknown')}
- Intervention: {trial_context.get('intervention', 'Unknown')}

Look for these methodology elements:
1. Study design (randomized, blinded, controlled, single-arm, crossover, etc.)
2. Population description (patient characteristics, inclusion/exclusion criteria)
3. Primary/secondary endpoints (outcome measures, assessment scales)
4. Statistical methods (sample size, alpha level, analysis population, statistical tests)
5. Interim analysis plans (timing, stopping rules, spending functions)
6. Missing data handling (imputation methods, assumptions)

For each field you find, provide:
- The extracted value (can be string, number, or boolean)
- A direct TEXT QUOTE from the document that supports this value (MUST be text, never a number)
- Your confidence in the extraction (0.0-1.0)

Extract the following methodology fields:

**Study Design:**
- design_archetype: Type of study design (e.g., "Randomized Controlled Trial", "Single Arm", "Crossover")
- is_blinded: Whether the study is blinded (true/false)
- analysis_set: Primary analysis population (e.g., "Intent-to-Treat", "Per-Protocol")

**Population:**
- population_description: Description of study population
- stratification_factors: List of stratification factors used
- covariate_adjustment: List of covariates adjusted for

**Endpoints:**
- primary_endpoint: Primary endpoint description
- secondary_endpoints: List of secondary endpoints
- summary_measure: Type of summary measure (e.g., "Hazard Ratio", "Odds Ratio", "Mean Difference")

**Statistical Design:**
- alpha_level: Significance level (e.g., 0.05)
- is_one_sided: Whether test is one-sided (true/false)
- multiplicity_adjustment: Method for multiple comparisons (e.g., "Bonferroni", "Holm")
- sample_size_reassessment: Whether sample size can be reassessed (true/false)

**Interim Analysis:**
- interim_looks: List of interim analysis details
- interim_timing: Timing of interim analyses
- spending_function: Alpha spending function used
- stop_rules: List of stopping rules

**Missing Data:**
- missingness_assumption: Assumption about missing data (e.g., "Missing at Random")
- missingness_pattern: Pattern of missingness
- imputation_method: Method for handling missing data

**Other:**
- estimand: Primary estimand definition
- intercurrent_events_policy: Policy for handling intercurrent events
- endpoint_ascertainment: How endpoints are ascertained
- assessment_interval: Interval between assessments
- adjudication_committee: Whether there's an adjudication committee

CRITICAL REQUIREMENTS:
1. Only include fields where you found clear evidence in the document
2. For each field you extract, provide the exact text quote from the document that supports it
3. field_name must ALWAYS be a text string (never a number like 2017.0)
4. evidence_quote must ALWAYS be a text string containing actual words from the document (never a number like 37.0 or 2.0). It should be a complete sentence or phrase from the document that supports the extracted value.
5. value can be a string, number, or boolean depending on the field type
6. Try to extract at least some basic information (population, endpoints, design) even if details are limited. If you truly cannot find any methodology information, include a "reason" field explaining why (e.g., "Document appears to be an abstract without methodology details", "Document is too short or lacks clinical trial information", "Document contains only results without methodology section")
7. If a field is not mentioned, omit it entirely
8. Do not use evidence quotes or come to conclusions that are natrative driven. The naritive message is likely unreliable, so it is better to come to your own evidenced based reasonable conclusion then be persuaded by the naritive delivered. 
9. Keep quotes below 1000 characters.

RESPONSE STRUCTURE:
You must return a JSON object with these top-level keys:
- "study_card_data": An object containing the extracted field values (just the values, not objects)
- "field_quotes": An array of objects, each with field_name, value, evidence_quote, and confidence
- "reason": (optional) A brief explanation if no methodology information was found

The response will be automatically formatted according to the required schema.
"""
