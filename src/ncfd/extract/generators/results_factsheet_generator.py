"""
LLM Results Factsheet Generator

Directly generates ResultsFactsheet with evidence quotes for each field.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ..models.results_factsheet import ResultsFactsheet
from ..models.evidence_field import EvidenceField
from ...llm import BaseLLMGenerator
from ...llm.json_parser import parse_llm_json_response, validate_confidence_score

logger = logging.getLogger(__name__)


# Use common EvidenceField instead of ResultsField


class LLMResultsFactsheetGenerator(BaseLLMGenerator):
    """Generates ResultsFactsheet directly with evidence quotes."""
    
    def __init__(self, llm_config: Optional[Dict[str, Any]] = None):
        super().__init__("LLMResultsFactsheetGenerator", "1.0.0", llm_config)
    
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
            
            if not raw_doc_text:
                return {
                    "results_factsheet": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": "No document text provided"
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
    
    async def _extract_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Extract results factsheet data using LLM with the given prompt."""
        return await self._extract_results_factsheet_with_llm(doc_text, trial_context, prompt)
    
    def _build_standard_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build the standard prompt for the first attempt."""
        return self._build_standard_results_prompt(doc_text, trial_context)
    
    def _build_simplified_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build a simplified prompt for the second attempt."""
        return self._build_simplified_results_prompt(doc_text, trial_context)
    
    def _build_minimal_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build a minimal prompt for the third attempt."""
        return self._build_minimal_results_prompt(doc_text, trial_context)
    
    async def _generate_results_with_quotes(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> tuple:
        """Generate results factsheet data with evidence quotes for each field."""
        
        prompt = f"""
You are a clinical trial results expert. Extract results information from this clinical trial document and provide evidence quotes for each field you fill.

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

Extract the following results fields:

**Primary Results:**
- primary_endpoint_result: Primary endpoint result description
- primary_endpoint_value: Primary endpoint numerical value
- primary_endpoint_units: Units for primary endpoint
- primary_endpoint_p_value: P-value for primary endpoint
- primary_endpoint_ci_lower: Lower confidence interval
- primary_endpoint_ci_upper: Upper confidence interval
- primary_endpoint_effect_size: Effect size (e.g., hazard ratio, odds ratio)

**Secondary Results:**
- secondary_endpoints: List of secondary endpoint results
- secondary_endpoint_values: List of secondary endpoint values
- secondary_endpoint_p_values: List of secondary endpoint p-values

**Safety Results:**
- adverse_events: Summary of adverse events
- serious_adverse_events: Summary of serious adverse events
- deaths: Number of deaths
- discontinuations: Number of discontinuations due to adverse events

**Population Results:**
- n_enrolled: Number of patients enrolled
- n_analyzed: Number of patients analyzed
- n_primary_analysis: Number in primary analysis
- n_safety_analysis: Number in safety analysis
- analysis_set: Analysis set used (ITT, mITT, PP)

**Statistical Results:**
- statistical_power: Statistical power achieved
- effect_size: Overall effect size
- clinical_significance: Assessment of clinical significance
- statistical_significance: Assessment of statistical significance

**Subgroup Results:**
- subgroup_analyses: List of subgroup analyses performed
- subgroup_results: Results of subgroup analyses
- interaction_p_values: P-values for interactions

**Time-to-Event Results:**
- median_follow_up: Median follow-up time
- median_pfs: Median progression-free survival
- median_os: Median overall survival
- hazard_ratios: Hazard ratios for time-to-event endpoints

**Biomarker Results:**
- biomarker_analyses: List of biomarker analyses
- biomarker_results: Results of biomarker analyses
- predictive_biomarkers: Predictive biomarkers identified

**Quality of Life:**
- qol_endpoints: Quality of life endpoints
- qol_results: Quality of life results

Respond in JSON format:
{{
    "results_data": {{
        "field_name": "extracted_value",
        ...
    }},
    "field_quotes": [
        {{
            "field_name": "field_name",
            "value": "extracted_value", 
            "evidence_quote": "exact quote from document",
            "confidence": 0.9
        }},
        ...
    ]
}}

Only include fields where you found clear evidence in the document. If a field is not mentioned, omit it from both the results_data and field_quotes.
"""

        try:
            # Use the LLM extraction method instead of direct client call
            result = await self._extract_results_factsheet_with_llm(doc_text, trial_context)
            logger.info(f"DEBUG: LLM extraction result keys: {list(result.keys())}")
            logger.info(f"DEBUG: LLM extraction result field_quotes: {result.get('field_quotes', [])}")
            
            results_data = result.get("results_data", {})
            field_quotes = []
            
            for quote_data in result.get("field_quotes", []):
                logger.info(f"DEBUG: Processing quote_data: {quote_data}")
                
                # Validate that quote_data is a dictionary
                if not isinstance(quote_data, dict):
                    logger.error(f"Quote data is not a dictionary, got {type(quote_data)}: {quote_data}")
                    logger.error("This indicates the LLM returned malformed JSON with numbers instead of quote objects.")
                    continue
                
                # Ensure evidence_quote is a string
                evidence_quote = quote_data.get("evidence_quote", "")
                if not isinstance(evidence_quote, str):
                    evidence_quote = str(evidence_quote) if evidence_quote is not None else ""
                
                field_quotes.append(EvidenceField(
                    field_name=quote_data.get("field_name", ""),
                    value=quote_data.get("value"),
                    evidence_quote=evidence_quote,
                    confidence=quote_data.get("confidence", 0.8)
                ))
            
            logger.info(f"DEBUG: Generated {len(field_quotes)} field quotes")
            return results_data, field_quotes
            
        except Exception as e:
            self.logger.error(f"LLM results factsheet generation failed: {e}")
            return {}, []
    
    async def _extract_results_factsheet_with_llm(self, doc_text: str, trial_context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract results factsheet using LLM with evidence quotes and retry logic."""
        
        # Try multiple times with different approaches
        for attempt in range(3):
            try:
                if attempt == 0:
                    # First attempt: Standard prompt
                    prompt = self._build_standard_prompt(doc_text, trial_context)
                elif attempt == 1:
                    # Second attempt: Simplified prompt
                    prompt = self._build_simplified_prompt(doc_text, trial_context)
                else:
                    # Third attempt: Minimal prompt
                    prompt = self._build_minimal_prompt(doc_text, trial_context)
                
                logger.info(f"DEBUG: Attempt {attempt + 1} - Making LLM call")
                
                # Validate inputs before API call
                if not doc_text or not doc_text.strip():
                    raise ValueError("Empty doc_text provided to LLM")
                if not prompt or not prompt.strip():
                    raise ValueError("Empty prompt provided to LLM")
                
                # Log redacted payload preview
                logger.debug(f"LLM payload preview: doc_text_length={len(doc_text)}, prompt_length={len(prompt)}")
                
                # Make LLM call with proper message format
                response = await self.call_llm(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=2000,
                    json_output=True
                )
                
                # Parse the response
                result = response.content
                logger.info(f"DEBUG: LLM raw response type: {type(result)}")
                logger.info(f"DEBUG: LLM raw response content: {str(result)[:500]}...")
                
                if isinstance(result, str):
                    # Use robust JSON parsing
                    parsed_result = parse_llm_json_response(result, expected_fields=["results_data", "field_quotes"])
                    if parsed_result:
                        result = parsed_result
                        # Safe field_quotes count logging
                        field_quotes_for_logging = result.get('field_quotes', [])
                        if not isinstance(field_quotes_for_logging, list):
                            field_quotes_for_logging = []
                        field_quotes_count = len(field_quotes_for_logging)
                        logger.info(f"DEBUG: Parsed JSON successfully, field_quotes count: {field_quotes_count}")
                        
                        # If we got field quotes, return the result
                        if field_quotes_count > 0:
                            logger.info(f"DEBUG: Success on attempt {attempt + 1} with {field_quotes_count} field quotes")
                            return result
                        else:
                            logger.warning(f"DEBUG: Attempt {attempt + 1} returned 0 field quotes, retrying...")
                            continue
                    else:
                        logger.error(f"DEBUG: JSON parsing failed on attempt {attempt + 1}")
                        logger.error(f"DEBUG: Raw response: {result}")
                        continue
                elif isinstance(result, (int, float)):
                    # Handle case where LLM returns a number instead of JSON
                    logger.error(f"LLM returned a number instead of JSON on attempt {attempt + 1}: {result}")
                    continue
                elif not isinstance(result, dict):
                    # Handle other unexpected types
                    logger.error(f"LLM returned unexpected type {type(result)} on attempt {attempt + 1}: {result}")
                    continue
                
                # If we got here, we have a valid result but no field quotes
                logger.warning(f"DEBUG: Attempt {attempt + 1} returned valid JSON but 0 field quotes, retrying...")
                continue
                
            except Exception as e:
                logger.error(f"DEBUG: Attempt {attempt + 1} failed: {e}")
                if attempt == 2:  # Last attempt
                    raise e
                continue
        
        # If all attempts failed to get field quotes, return empty result
        logger.warning("DEBUG: All attempts failed to generate field quotes, returning empty result")
        return {"results_data": {}, "field_quotes": []}
    
    def _build_standard_prompt(self, doc_text: str, trial_context: Dict[str, Any]) -> str:
        """Build standard prompt for results extraction."""
        return f"""
You are a clinical trial results expert. Extract results information from this clinical trial document and provide evidence quotes for each field you fill.

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

Respond in JSON format:
{{
    "results_data": {{
        "results": [
            {{
                "metric": "metric_name",
                "value": "value",
                "units": "units",
                "timepoint": "timepoint",
                "analysis_set": "ITT",
                "population_slice": "population",
                "is_posthoc": false,
                "flags": ["flag1", "flag2"],
                "span_ids": ["span_id1", "span_id2"],
                "doc_id": "doc_id"
            }}
        ],
        "primary_endpoint_results": {{...}},
        "secondary_endpoint_results": [{...}],
        "safety_results": [{...}],
        "primary_analysis_set": "ITT",
        "secondary_analysis_sets": ["mITT", "PP"],
        "total_enrolled": 100,
        "completed_primary_endpoint": 95,
        "dropout_rate": 0.05,
        "follow_up_completion": 0.95
    }},
    "field_quotes": [
        {{
            "field_name": "field_name",
            "value": "extracted_value", 
            "evidence_quote": "exact quote from document",
            "confidence": 0.9
        }},
        ...
    ]
}}

Only include fields where you found clear evidence in the document. If a field is not mentioned, omit it from both the results_data and field_quotes.
"""
    
    def _build_simplified_prompt(self, doc_text: str, trial_context: Dict[str, Any]) -> str:
        """Build simplified prompt for results extraction."""
        return f"""
Extract key results from this clinical trial document. Focus on finding specific findings, outcomes, or measurements.

Document Text:
{doc_text[:3000]}

Trial Context:
- Disease: {trial_context.get('disease', 'Unknown')}
- Intervention: {trial_context.get('intervention', 'Unknown')}

Return JSON with this structure:
{{
    "results_data": {{
        "results": [
            {{
                "metric": "description of what was measured",
                "value": "the actual result or finding",
                "units": "units if applicable",
                "confidence": 0.9
            }}
        ]
    }},
    "field_quotes": [
        {{
            "field_name": "metric_name",
            "value": "the result value",
            "evidence_quote": "exact quote from document supporting this result",
            "confidence": 0.9
        }}
    ]
}}

IMPORTANT: You must provide at least 2-3 field_quotes with evidence_quote from the document.
"""
    
    def _build_minimal_prompt(self, doc_text: str, trial_context: Dict[str, Any]) -> str:
        """Build minimal prompt for results extraction."""
        return f"""
Find key findings in this text and provide quotes that support them.

Text: {doc_text[:2000]}

Return JSON:
{{
    "results_data": {{}},
    "field_quotes": [
        {{
            "field_name": "finding_1",
            "value": "what was found",
            "evidence_quote": "quote from text",
            "confidence": 0.8
        }},
        {{
            "field_name": "finding_2", 
            "value": "another finding",
            "evidence_quote": "another quote from text",
            "confidence": 0.8
        }}
    ]
}}

Provide at least 2 field_quotes with evidence_quote from the text.
"""
