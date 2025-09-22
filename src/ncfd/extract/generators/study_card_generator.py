"""
LLM Study Card Extractor

Extracts StudyCard data with evidence quotes for each field.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ..models.study_card import StudyCard
from ..models.evidence_field import EvidenceField
from ...llm.base_worker import BaseLLMExtractor
from ...llm.json_parser import parse_llm_json_response, validate_confidence_score
from ...utils.config_manager import get_config_manager
from ...utils.error_handler import get_error_handler, safe_execute

logger = logging.getLogger(__name__)


class LLMStudyCardExtractor(BaseLLMExtractor):
    """Extracts StudyCard data directly with evidence quotes."""
    
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        super().__init__("LLMStudyCardExtractor", llm_config)
    
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
            
            # Extract study card data with evidence quotes using base class
            study_card_data, field_quotes = await self.extract_document(
                raw_doc_text, doc_id, trial_context
            )
            
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
                self.logger.warning(f"Study card generation produced completely empty response for doc_id: {doc_id} "
                                   f"(doc_length={len(raw_doc_text)})")
                return {
                    "study_card": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": "LLM returned empty response - may indicate insufficient content or prompt issue"
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
    
    def _get_data_key(self) -> str:
        """Return the key for the main data in the LLM response."""
        return "study_card_data"
    
    def _get_meaningful_fields(self) -> List[str]:
        """Return the list of fields that indicate meaningful data for this extractor."""
        return [
            "design_archetype", "primary_endpoint", "analysis_set", 
            "population_description", "is_blinded", "alpha_level"
        ]
    
    def _build_extraction_prompt(self, doc_text: str, doc_id: str, context: Dict[str, Any]) -> str:
        """Build the extraction prompt for this specific extractor."""
        return self._build_standard_study_prompt(doc_text, doc_id, context)
    
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
            "required": ["study_card_data", "field_quotes"]
        }
    
    
    def _build_standard_study_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build enhanced prompt for study card extraction with better guidance."""
        return f"""
You are a clinical trial methodology expert. Extract methodology information from this document.

IMPORTANT: Only extract information if this document contains clinical trial methodology details.
If this is just an abstract, press release, or non-methodology content, return empty results.

Document Text:
{doc_text[:4000]}

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
- The extracted value
- A direct quote from the document that supports this value
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
4. evidence_quote must ALWAYS be a text string containing actual words from the document (never a number like 37.0 or 2.0)
5. value can be a string, number, or boolean depending on the field type
6. If no methodology information is found, return empty objects
7. If a field is not mentioned, omit it entirely
8. IMPORTANT: Never use numeric values as field names or evidence quotes

RESPONSE STRUCTURE:
You must return a JSON object with exactly two top-level keys:
- "study_card_data": An object containing the extracted field values (just the values, not objects)
- "field_quotes": An array of objects, each with field_name, value, evidence_quote, and confidence

The response will be automatically formatted according to the required schema.
"""
    async def _extract_study_card_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str = None) -> Dict[str, Any]:
        """Extract study card using LLM with evidence quotes."""
        try:
            # Use provided prompt or build default one
            if prompt is None:
                prompt = f"""
You are a clinical trial methodology expert. Extract methodology information from this clinical trial document and provide evidence quotes for each field you fill.

Document Text:
{doc_text[:4000]}  # Truncate for token limits

Trial Context:
- Trial ID: {trial_context.get('trial_id', 'Unknown')}
- Disease: {trial_context.get('disease', 'Unknown')}
- Intervention: {trial_context.get('intervention', 'Unknown')}

For each field you fill, provide:
1. The extracted value
2. A direct quote from the document that supports this value
3. Your confidence in the extraction (0.0-1.0)

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
4. evidence_quote must ALWAYS be a text string containing actual words from the document (never a number like 37.0 or 2.0)
5. value can be a string, number, or boolean depending on the field type
6. If no methodology information is found, return empty objects
7. If a field is not mentioned, omit it entirely
8. IMPORTANT: Never use numeric values as field names or evidence quotes

RESPONSE STRUCTURE:
You must return a JSON object with exactly two top-level keys:
- "study_card_data": An object containing the extracted field values (just the values, not objects)
- "field_quotes": An array of objects, each with field_name, value, evidence_quote, and confidence

The response will be automatically formatted according to the required schema.
"""
            
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
                    "study_card_data": {
                        "type": "object",
                        "properties": {
                            "design_archetype": {"type": "string"},
                            "is_blinded": {"type": "boolean"},
                            "analysis_set": {"type": "string"},
                            "population_description": {"type": "string"},
                            "stratification_factors": {"type": "array", "items": {"type": "string"}},
                            "covariate_adjustment": {"type": "array", "items": {"type": "string"}},
                            "primary_endpoint": {"type": "string"},
                            "secondary_endpoints": {"type": "array", "items": {"type": "string"}},
                            "summary_measure": {"type": "string"},
                            "alpha_level": {"type": "number"},
                            "is_one_sided": {"type": "boolean"},
                            "multiplicity_adjustment": {"type": "string"},
                            "sample_size_reassessment": {"type": "boolean"},
                            "interim_looks": {"type": "array"},
                            "interim_timing": {"type": "string"},
                            "spending_function": {"type": "string"},
                            "stop_rules": {"type": "array", "items": {"type": "string"}},
                            "missingness_assumption": {"type": "string"},
                            "missingness_pattern": {"type": "string"},
                            "imputation_method": {"type": "string"},
                            "estimand": {"type": "string"},
                            "intercurrent_events_policy": {"type": "string"},
                            "endpoint_ascertainment": {"type": "string"},
                            "assessment_interval": {"type": "string"},
                            "adjudication_committee": {"type": "boolean"}
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
                "required": ["study_card_data", "field_quotes"]
            }
            
            response = await self.call_llm(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
                json_schema=json_schema
            )
            
            # Parse the response
            result = response.content
            self.logger.info(f"🔍 LLM RAW RESPONSE DEBUG:")
            self.logger.info(f"   Type: {type(result)}")
            self.logger.info(f"   Content length: {len(str(result))}")
            self.logger.info(f"   Content preview: {str(result)[:500]}...")
            
            if isinstance(result, str):
                # Use robust JSON parsing
                self.logger.info(f"🔍 PARSING STRING RESPONSE:")
                parsed_result = parse_llm_json_response(result, expected_fields=["study_card_data", "field_quotes"])
                if parsed_result:
                    result = parsed_result
                    self.logger.info(f"✅ JSON PARSING SUCCESSFUL:")
                    self.logger.info(f"   Parsed keys: {list(result.keys())}")
                    self.logger.info(f"   study_card_data type: {type(result.get('study_card_data'))}")
                    self.logger.info(f"   study_card_data content: {result.get('study_card_data')}")
                    self.logger.info(f"   field_quotes type: {type(result.get('field_quotes'))}")
                    self.logger.info(f"   field_quotes count: {len(result.get('field_quotes', []))}")
                    if result.get('field_quotes'):
                        self.logger.info(f"   field_quotes preview: {result.get('field_quotes')[:2]}")
                else:
                    self.logger.error(f"❌ JSON PARSING FAILED:")
                    self.logger.error(f"   Raw response: {result}")
                    return {}
            elif isinstance(result, (int, float)):
                # Handle case where LLM returns a number instead of JSON
                self.logger.error(f"❌ LLM RETURNED NUMBER: {result}")
                return {}
            elif not isinstance(result, dict):
                # Handle other unexpected types
                self.logger.error(f"❌ LLM RETURNED UNEXPECTED TYPE {type(result)}: {result}")
                return {}
            
            self.logger.info(f"🔍 FINAL RESULT BEFORE RETURN:")
            self.logger.info(f"   Keys: {list(result.keys())}")
            self.logger.info(f"   study_card_data: {result.get('study_card_data')}")
            self.logger.info(f"   field_quotes count: {len(result.get('field_quotes', []))}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM study card extraction failed: {e}")
            return {}
    
    def _build_simplified_study_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build simplified prompt for study card extraction."""
        return f"""
Extract methodology information from this clinical trial document. Focus on the most important methodology elements.

IMPORTANT: Only extract if this document contains clinical trial methodology details.

Document Text:
{doc_text[:3000]}

Trial Context:
- Disease: {trial_context.get('disease', 'Unknown')}
- Intervention: {trial_context.get('intervention', 'Unknown')}

Look for: study design, population description, primary endpoint, statistical methods.

CRITICAL REQUIREMENTS:
1. Only include fields where you found clear evidence in the document
2. For each field you extract, provide the exact text quote from the document that supports it
3. field_name must ALWAYS be a text string (never a number like 2017.0)
4. evidence_quote must ALWAYS be a text string containing actual words from the document (never a number like 37.0 or 2.0)
5. value can be a string, number, or boolean depending on the field type
6. If no methodology information is found, return empty objects
7. If a field is not mentioned, omit it entirely
8. IMPORTANT: Never use numeric values as field names or evidence quotes

RESPONSE STRUCTURE:
You must return a JSON object with exactly two top-level keys:
- "study_card_data": An object containing the extracted field values (just the values, not objects)
- "field_quotes": An array of objects, each with field_name, value, evidence_quote, and confidence

The response will be automatically formatted according to the required schema.
"""
    
    def _build_minimal_study_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build minimal prompt for study card extraction."""
        return f"""
Find any methodology information in this text and provide quotes.

IMPORTANT: Only extract if methodology information is present.

Text: {doc_text[:2000]}

Look for: study design, endpoints, statistical methods, population.

CRITICAL REQUIREMENTS:
1. Only include fields where you found clear evidence in the document
2. For each field you extract, provide the exact text quote from the document that supports it
3. field_name must ALWAYS be a text string (never a number like 2017.0)
4. evidence_quote must ALWAYS be a text string containing actual words from the document (never a number like 37.0 or 2.0)
5. value can be a string, number, or boolean depending on the field type
6. If no methodology information is found, return empty objects
7. If a field is not mentioned, omit it entirely
8. IMPORTANT: Never use numeric values as field names or evidence quotes

RESPONSE STRUCTURE:
You must return a JSON object with exactly two top-level keys:
- "study_card_data": An object containing the extracted field values (just the values, not objects)
- "field_quotes": An array of objects, each with field_name, value, evidence_quote, and confidence

The response will be automatically formatted according to the required schema.
"""
