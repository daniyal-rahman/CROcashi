"""
LLM Gate Assessment Generator

Directly generates GateAssessment with evidence quotes for each field.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ...models.gate_assessment import GateAssessment
from ...models.evidence_span import EvidenceSpan
from ..base_llm_worker import BaseLLMWorker

logger = logging.getLogger(__name__)


@dataclass
class GateField:
    """A field in the gate assessment with its evidence quote."""
    field_name: str
    value: Any
    evidence_quote: str
    confidence: float = 0.8


class LLMGateAssessmentGenerator(BaseLLMWorker):
    """Generates GateAssessment directly with evidence quotes."""
    
    def __init__(self, model_name: str = "gpt-4o-mini"):
        super().__init__(model_name)
        self.logger = logging.getLogger(__name__)
    
    async def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate GateAssessment with evidence quotes.
        
        Args:
            inputs: {
                "raw_doc_text": str,
                "doc_id": str,
                "trial_context": Dict[str, Any]
            }
            
        Returns:
            {
                "gate_assessments": List[GateAssessment],
                "field_quotes": List[GateField],
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
                    "gate_assessments": [],
                    "field_quotes": [],
                    "success": False,
                    "error_message": "No document text provided"
                }
            
            self.logger.info(f"Generating gate assessments for doc_id: {doc_id}")
            
            # Generate gate assessments with evidence quotes
            gate_assessments, field_quotes = await self._generate_gates_with_quotes(
                raw_doc_text, doc_id, trial_context
            )
            
            return {
                "gate_assessments": gate_assessments,
                "field_quotes": field_quotes,
                "success": True,
                "error_message": None
            }
            
        except Exception as e:
            self.logger.error(f"Gate assessment generation failed: {e}")
            return {
                "gate_assessments": [],
                "field_quotes": [],
                "success": False,
                "error_message": str(e)
            }
    
    async def _generate_gates_with_quotes(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> tuple:
        """Generate gate assessment data with evidence quotes for each field."""
        
        prompt = f"""
You are a clinical trial gate assessment expert. Evaluate this clinical trial document against key decision gates and provide evidence quotes for each assessment.

Document Text:
{doc_text[:4000]}  # Truncate for token limits

Trial Context:
- Trial ID: {trial_context.get('trial_id', 'Unknown')}
- Disease: {trial_context.get('disease', 'Unknown')}
- Intervention: {trial_context.get('intervention', 'Unknown')}

For each gate assessment, provide:
1. The gate evaluation
2. A direct quote from the document that supports this assessment
3. Your confidence in the assessment (0.0-1.0)

Evaluate the following key gates:

**Efficacy Gates:**
- primary_endpoint_success: Did the trial meet its primary endpoint? (PASS/FAIL/UNCLEAR)
- statistical_significance: Is the result statistically significant? (PASS/FAIL/UNCLEAR)
- clinical_significance: Is the result clinically meaningful? (PASS/FAIL/UNCLEAR)
- effect_size_adequate: Is the effect size adequate? (PASS/FAIL/UNCLEAR)

**Safety Gates:**
- safety_acceptable: Is the safety profile acceptable? (PASS/FAIL/UNCLEAR)
- adverse_events_manageable: Are adverse events manageable? (PASS/FAIL/UNCLEAR)
- no_unexpected_safety_signals: No unexpected safety signals? (PASS/FAIL/UNCLEAR)

**Quality Gates:**
- study_quality_adequate: Is the study quality adequate? (PASS/FAIL/UNCLEAR)
- methodology_sound: Is the methodology sound? (PASS/FAIL/UNCLEAR)
- data_quality_acceptable: Is the data quality acceptable? (PASS/FAIL/UNCLEAR)

**Regulatory Gates:**
- regulatory_requirements_met: Are regulatory requirements met? (PASS/FAIL/UNCLEAR)
- endpoints_appropriate: Are the endpoints appropriate for regulatory approval? (PASS/FAIL/UNCLEAR)
- population_appropriate: Is the study population appropriate? (PASS/FAIL/UNCLEAR)

**Commercial Gates:**
- commercial_viability: Is the commercial viability demonstrated? (PASS/FAIL/UNCLEAR)
- competitive_advantage: Does it show competitive advantage? (PASS/FAIL/UNCLEAR)
- market_opportunity: Is there a clear market opportunity? (PASS/FAIL/UNCLEAR)

For each gate, also provide:
- rationale: Brief explanation of the assessment
- key_findings: Key findings that support the assessment
- concerns: Any concerns or limitations
- recommendations: Recommendations for next steps

Respond in JSON format:
{{
    "gate_assessments": [
        {{
            "gate_name": "primary_endpoint_success",
            "gate_type": "efficacy",
            "assessment": "PASS",
            "rationale": "Brief explanation",
            "key_findings": "Key findings",
            "concerns": "Any concerns",
            "recommendations": "Next steps"
        }},
        ...
    ],
    "field_quotes": [
        {{
            "gate_name": "primary_endpoint_success",
            "field_name": "assessment",
            "value": "PASS",
            "evidence_quote": "exact quote from document",
            "confidence": 0.9
        }},
        ...
    ]
}}

Only include gates where you found clear evidence in the document. If a gate cannot be assessed, omit it.
"""

        try:
            # Use the LLM extraction method instead of direct client call
            result = await self._extract_gate_assessments_with_llm(doc_text, trial_context)
            
            gate_assessments = []
            field_quotes = []
            
            for gate_data in result.get("gate_assessments", []):
                gate_assessment = GateAssessment(
                    gate_id=gate_data.get("gate_name", ""),
                    status=gate_data.get("assessment", "UNCERTAIN"),
                    rationale=[gate_data.get("rationale", "")],
                    assessment_notes=[gate_data.get("key_findings", ""), gate_data.get("concerns", "")],
                    next_steps=[gate_data.get("recommendations", "")],
                    confidence_in_assessment=gate_data.get("confidence", 0.8)
                )
                gate_assessments.append(gate_assessment)
            
            for quote_data in result.get("field_quotes", []):
                field_quotes.append(GateField(
                    field_name=f"{quote_data.get('gate_name', '')}_{quote_data.get('field_name', '')}",
                    value=quote_data.get("value"),
                    evidence_quote=quote_data.get("evidence_quote", ""),
                    confidence=quote_data.get("confidence", 0.8)
                ))
            
            return gate_assessments, field_quotes
            
        except Exception as e:
            self.logger.error(f"LLM gate assessment generation failed: {e}")
            return [], []
    
    async def _extract_gate_assessments_with_llm(self, doc_text: str, trial_context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract gate assessments using LLM with evidence quotes."""
        try:
            # Prepare the prompt
            prompt = f"""
You are a clinical trial gate assessment expert. Evaluate this clinical trial document against key decision gates and provide evidence quotes for each assessment.

IMPORTANT: Look for red flags and concerning issues such as:
- Expression of Concern from journals
- FDA warnings or regulatory concerns
- Data integrity issues
- Methodological problems
- Statistical concerns
- Safety warnings
- Regulatory warnings

Document Text:
{doc_text[:4000]}  # Truncate for token limits

Trial Context:
- Trial ID: {trial_context.get('trial_id', 'Unknown')}
- Disease: {trial_context.get('disease', 'Unknown')}
- Intervention: {trial_context.get('intervention', 'Unknown')}

For each gate assessment, provide:
1. The assessment result (PASS/FAIL/UNCLEAR)
2. A direct quote from the document that supports this assessment
3. Your confidence in the assessment (0.0-1.0)

CRITICAL: If you find any red flags, warnings, expressions of concern, or regulatory issues, you MUST mark the relevant gates as FAIL and provide detailed rationale.

Evaluate the following decision gates:

**Efficacy Gate:**
- gate_name: "Efficacy"
- gate_type: "EFFICACY"
- assessment: PASS/FAIL/UNCLEAR
- rationale: Why this assessment was made
- key_findings: Key findings that support the assessment
- concerns: Any concerns or limitations
- recommendations: Recommendations for next steps

**Safety Gate:**
- gate_name: "Safety"
- gate_type: "SAFETY"
- assessment: PASS/FAIL/UNCLEAR
- rationale: Why this assessment was made
- key_findings: Key findings that support the assessment
- concerns: Any concerns or limitations
- recommendations: Recommendations for next steps

**Quality Gate:**
- gate_name: "Quality"
- gate_type: "QUALITY"
- assessment: PASS/FAIL/UNCLEAR
- rationale: Why this assessment was made
- key_findings: Key findings that support the assessment
- concerns: Any concerns or limitations
- recommendations: Recommendations for next steps

**Regulatory Gate:**
- gate_name: "Regulatory"
- gate_type: "REGULATORY"
- assessment: PASS/FAIL/UNCLEAR
- rationale: Why this assessment was made
- key_findings: Key findings that support the assessment
- concerns: Any concerns or limitations
- recommendations: Recommendations for next steps

Respond in JSON format:
{{
    "gate_assessments": [
        {{
            "gate_name": "Efficacy",
            "gate_type": "EFFICACY",
            "assessment": "PASS",
            "rationale": "Clear evidence of efficacy",
            "key_findings": "Primary endpoint met",
            "concerns": "None",
            "recommendations": "Proceed to next phase"
        }},
        ...
    ],
    "field_quotes": [
        {{
            "gate_name": "Efficacy",
            "field_name": "assessment",
            "value": "PASS",
            "evidence_quote": "exact quote from document",
            "confidence": 0.9
        }},
        ...
    ]
}}

Only include gates where you found clear evidence in the document. If a gate cannot be assessed, omit it from both the gate_assessments and field_quotes.
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
            self.logger.error(f"LLM gate assessment extraction failed: {e}")
            return {}
