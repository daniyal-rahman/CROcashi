"""
LLM Method Card Generator

Directly generates MethodCard with evidence quotes for each field.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ...models.method_card import MethodCard
from ...models.evidence_field import EvidenceField
from .base_llm_generator import BaseLLMGenerator

logger = logging.getLogger(__name__)


# Use common EvidenceField instead of MethodCardField


class LLMMethodCardGenerator(BaseLLMGenerator):
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
                    "method_card": None,
                    "field_quotes": [],
                    "success": False,
                    "error_message": "No document text provided"
                }
            
            self.logger.info(f"Generating method card for doc_id: {doc_id}")
            
            # Generate method card with evidence quotes using base class retry logic
            method_card_data, field_quotes = await self._execute_with_retry(
                raw_doc_text, doc_id, trial_context
            )
            
            # Create MethodCard object
            method_card = MethodCard(
                doc_id=doc_id,
                design_archetype=method_card_data.get('design_archetype'),
                is_blinded=method_card_data.get('is_blinded'),
                analysis_set=method_card_data.get('analysis_set'),
                population_description=method_card_data.get('population_description'),
                stratification_factors=method_card_data.get('stratification_factors', []),
                covariate_adjustment=method_card_data.get('covariate_adjustment', []),
                primary_endpoint=method_card_data.get('primary_endpoint'),
                secondary_endpoints=method_card_data.get('secondary_endpoints', []),
                summary_measure=method_card_data.get('summary_measure'),
                alpha_level=method_card_data.get('alpha_level'),
                is_one_sided=method_card_data.get('is_one_sided'),
                multiplicity_adjustment=method_card_data.get('multiplicity_adjustment'),
                sample_size_reassessment=method_card_data.get('sample_size_reassessment'),
                interim_looks=method_card_data.get('interim_looks', []),
                interim_timing=method_card_data.get('interim_timing'),
                spending_function=method_card_data.get('spending_function'),
                stop_rules=method_card_data.get('stop_rules', []),
                missingness_assumption=method_card_data.get('missingness_assumption'),
                missingness_pattern=method_card_data.get('missingness_pattern'),
                imputation_method=method_card_data.get('imputation_method'),
                estimand=method_card_data.get('estimand'),
                intercurrent_events_policy=method_card_data.get('intercurrent_events_policy'),
                endpoint_ascertainment=method_card_data.get('endpoint_ascertainment'),
                assessment_interval=method_card_data.get('assessment_interval'),
                adjudication_committee=method_card_data.get('adjudication_committee')
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
    
    def _get_data_key(self) -> str:
        """Return the key for the main data in the LLM response."""
        return "method_card_data"
    
    async def _extract_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Extract method card data using LLM with the given prompt."""
        return await self._extract_method_card_with_llm(doc_text, trial_context, prompt)
    
    def _build_standard_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build the standard prompt for the first attempt."""
        return self._build_standard_method_prompt(doc_text, doc_id, trial_context)
    
    def _build_simplified_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build a simplified prompt for the second attempt."""
        return self._build_simplified_method_prompt(doc_text, doc_id, trial_context)
    
    def _build_minimal_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build a minimal prompt for the third attempt."""
        return self._build_minimal_method_prompt(doc_text, doc_id, trial_context)
    
    async def _generate_method_card_with_quotes(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> tuple:
        """Generate method card data with evidence quotes for each field."""
        
        # Try multiple times with different approaches
        for attempt in range(3):
            try:
                if attempt == 0:
                    # First attempt: Standard prompt
                    prompt = self._build_standard_method_prompt(doc_text, doc_id, trial_context)
                elif attempt == 1:
                    # Second attempt: Simplified prompt
                    prompt = self._build_simplified_method_prompt(doc_text, doc_id, trial_context)
                else:
                    # Third attempt: Minimal prompt
                    prompt = self._build_minimal_method_prompt(doc_text, doc_id, trial_context)
                
                logger.info(f"DEBUG: Method card attempt {attempt + 1} - Making LLM call")
                
                result = await self._extract_method_card_with_llm(doc_text, trial_context, prompt)
                logger.info(f"DEBUG: LLM extraction result keys: {list(result.keys())}")
                logger.info(f"DEBUG: LLM extraction result field_quotes: {result.get('field_quotes', [])}")
                
                method_card_data = result.get("method_card_data", {})
                field_quotes = []
                
                for quote_data in result.get("field_quotes", []):
                    logger.info(f"DEBUG: Processing quote_data: {quote_data}")
                    field_quotes.append(EvidenceField(
                        field_name=quote_data.get("field_name", ""),
                        value=quote_data.get("value"),
                        evidence_quote=quote_data.get("evidence_quote", ""),
                        confidence=quote_data.get("confidence", 0.8)
                    ))
                
                logger.info(f"DEBUG: Generated {len(field_quotes)} field quotes")
                
                # If we got field quotes, return the result
                if len(field_quotes) > 0:
                    logger.info(f"DEBUG: Method card success on attempt {attempt + 1} with {len(field_quotes)} field quotes")
                    return method_card_data, field_quotes
                else:
                    logger.warning(f"DEBUG: Method card attempt {attempt + 1} returned 0 field quotes, retrying...")
                    continue
                    
            except Exception as e:
                logger.error(f"DEBUG: Method card attempt {attempt + 1} failed: {e}")
                if attempt == 2:  # Last attempt
                    raise e
                continue
        
        # If all attempts failed to get field quotes, return empty result
        logger.warning("DEBUG: All method card attempts failed to generate field quotes, returning empty result")
        return {}, []
    
    def _build_standard_method_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build standard prompt for method card extraction."""
        return f"""
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
    async def _extract_method_card_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str = None) -> Dict[str, Any]:
        """Extract method card using LLM with evidence quotes."""
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
            logger.info(f"DEBUG: LLM raw response type: {type(result)}")
            logger.info(f"DEBUG: LLM raw response content: {str(result)[:500]}...")
            
            if isinstance(result, str):
                try:
                    import json
                    result = json.loads(result)
                    logger.info(f"DEBUG: Parsed JSON successfully, field_quotes count: {len(result.get('field_quotes', []))}")
                except json.JSONDecodeError as e:
                    logger.error(f"DEBUG: JSON parsing failed: {e}")
                    logger.error(f"DEBUG: Raw response: {result}")
                    return {}
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM method card extraction failed: {e}")
            return {}
    
    def _build_simplified_method_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build simplified prompt for method card extraction."""
        return f"""
Extract methodology information from this clinical trial document. Focus on study design, population, and key methods.

Document Text:
{doc_text[:3000]}

Trial Context:
- Disease: {trial_context.get('disease', 'Unknown')}
- Intervention: {trial_context.get('intervention', 'Unknown')}

Return JSON:
{{
    "method_card_data": {{
        "population_description": "description of study population",
        "design_archetype": "study design type",
        "primary_endpoint": "main outcome measure"
    }},
    "field_quotes": [
        {{
            "field_name": "population_description",
            "value": "extracted population description",
            "evidence_quote": "quote from document",
            "confidence": 0.9
        }}
    ]
}}

IMPORTANT: You must provide at least 1-2 field_quotes with evidence_quote from the document.
"""
    
    def _build_minimal_method_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build minimal prompt for method card extraction."""
        return f"""
Find methodology information in this text and provide quotes.

Text: {doc_text[:2000]}

Return JSON:
{{
    "method_card_data": {{}},
    "field_quotes": [
        {{
            "field_name": "methodology_finding",
            "value": "what was found about methods",
            "evidence_quote": "quote from text",
            "confidence": 0.8
        }}
    ]
}}

Provide at least 1 field_quote with evidence_quote from the text.
"""
