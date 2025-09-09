"""
LLM Method Card Generator

Directly generates MethodCard with evidence quotes for each field.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ...models.method_card import MethodCard
from ...models.evidence_span import EvidenceSpan
from ..base_llm_worker import BaseLLMWorker

logger = logging.getLogger(__name__)


@dataclass
class MethodCardField:
    """A field in the method card with its evidence quote."""
    field_name: str
    value: Any
    evidence_quote: str
    confidence: float = 0.8


class LLMMethodCardGenerator(BaseLLMWorker):
    """Generates MethodCard directly with evidence quotes."""
    
    def __init__(self, model_name: str = "gpt-4o-mini"):
        super().__init__("LLMMethodCardGenerator", "1.0.0")
        self.model_name = model_name
    
    async def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate MethodCard with evidence quotes.
        
        Args:
            inputs: {
                "raw_doc_text": str,
                "doc_id": str,
                "trial_context": Dict[str, Any]
            }
            
        Returns:
            {
                "method_card": MethodCard,
                "field_quotes": List[MethodCardField],
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
                    "method_card": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": "No document text provided"
                }
            
            self.logger.info(f"Generating method card for doc_id: {doc_id}")
            
            # Generate method card with evidence quotes
            method_card_data, field_quotes = await self._generate_method_card_with_quotes(
                raw_doc_text, doc_id, trial_context
            )
            
            # Create MethodCard object
            method_card = MethodCard(
                doc_id=doc_id,
                **method_card_data
            )
            
            return {
                "method_card": method_card,
                "field_quotes": field_quotes,
                "success": True,
                "error_message": None
            }
            
        except Exception as e:
            self.logger.error(f"Method card generation failed: {e}")
            return {
                "method_card": None,
                "field_quotes": [],
                "success": False,
                "error_message": str(e)
            }
    
    async def _generate_method_card_with_quotes(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> tuple:
        """Generate method card data with evidence quotes for each field."""
        
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

Respond in JSON format:
{{
    "method_card_data": {{
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

Only include fields where you found clear evidence in the document. If a field is not mentioned, omit it from both the method_card_data and field_quotes.
"""

        try:
            # Use LLM to extract method card with evidence quotes
            result = await self._extract_method_card_with_llm(doc_text, trial_context)
            
            method_card_data = result.get("method_card_data", {})
            field_quotes = []
            
            for quote_data in result.get("field_quotes", []):
                field_quotes.append(MethodCardField(
                    field_name=quote_data.get("field_name", ""),
                    value=quote_data.get("value"),
                    evidence_quote=quote_data.get("evidence_quote", ""),
                    confidence=quote_data.get("confidence", 0.8)
                ))
            
            return method_card_data, field_quotes
            
        except Exception as e:
            self.logger.error(f"LLM method card generation failed: {e}")
            return {}, []
    
    
    async def _extract_method_card_with_llm(self, doc_text: str, trial_context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract method card using LLM with evidence quotes."""
        try:
            # Prepare the prompt
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

Respond in JSON format:
{{
    "method_card_data": {{
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

Only include fields where you found clear evidence in the document. If a field is not mentioned, omit it from both the method_card_data and field_quotes.
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
            self.logger.error(f"LLM method card extraction failed: {e}")
            return {}
