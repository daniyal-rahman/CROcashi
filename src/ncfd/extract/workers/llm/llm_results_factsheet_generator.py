"""
LLM Results Factsheet Generator

Directly generates ResultsFactsheet with evidence quotes for each field.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ...models.results_factsheet import ResultsFactsheet
from ...models.evidence_span import EvidenceSpan
from ..base_llm_worker import BaseLLMWorker

logger = logging.getLogger(__name__)


@dataclass
class ResultsField:
    """A field in the results factsheet with its evidence quote."""
    field_name: str
    value: Any
    evidence_quote: str
    confidence: float = 0.8


class LLMResultsFactsheetGenerator(BaseLLMWorker):
    """Generates ResultsFactsheet directly with evidence quotes."""
    
    def __init__(self, model_name: str = "gpt-4o-mini"):
        super().__init__(model_name)
        self.logger = logging.getLogger(__name__)
    
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
                "field_quotes": List[ResultsField],
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
            
            results_data = result.get("results_data", {})
            field_quotes = []
            
            for quote_data in result.get("field_quotes", []):
                field_quotes.append(ResultsField(
                    field_name=quote_data.get("field_name", ""),
                    value=quote_data.get("value"),
                    evidence_quote=quote_data.get("evidence_quote", ""),
                    confidence=quote_data.get("confidence", 0.8)
                ))
            
            return results_data, field_quotes
            
        except Exception as e:
            self.logger.error(f"LLM results factsheet generation failed: {e}")
            return {}, []
    
    async def _extract_results_factsheet_with_llm(self, doc_text: str, trial_context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract results factsheet using LLM with evidence quotes."""
        try:
            # Prepare the prompt
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

            # Make LLM call
            response = await self.call_llm(
                messages=[prompt],
                temperature=0.1,
                max_tokens=2000,
                json_output=True
            )
            
            # Parse the response
            result = response.content
            if isinstance(result, str):
                import json
                result = json.loads(result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM results factsheet extraction failed: {e}")
            return {}
