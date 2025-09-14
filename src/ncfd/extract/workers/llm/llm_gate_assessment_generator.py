"""
LLM Gate Assessment Generator

Directly generates GateAssessment with evidence quotes for each field.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ...models.gate_assessment import GateAssessment
from ...models.evidence_field import EvidenceField
from .base_llm_generator import BaseLLMGenerator

logger = logging.getLogger(__name__)


# Use common EvidenceField instead of GateField


class LLMGateAssessmentGenerator(BaseLLMGenerator):
    """Generates GateAssessment directly with evidence quotes."""
    
    def __init__(self, model_name: str = "gpt-4o-mini"):
        super().__init__("LLMGateAssessmentGenerator", "1.0.0")
        self.model_name = model_name
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
                    "gate_assessments": [],
                    "field_quotes": [],
                    "success": False,
                    "error_message": "No document text provided"
                }
            
            self.logger.info(f"Generating gate assessments for doc_id: {doc_id}")
            
            # Generate gate assessments with evidence quotes using retry logic
            gate_assessments_data, field_quotes = await self._execute_with_retry(
                raw_doc_text, doc_id, trial_context
            )
            
            # Convert raw data to GateAssessment objects
            gate_assessments = []
            
            # Map gate names to database format (G1, G2, G3, G4)
            gate_name_mapping = {
                "alpha_meltdown": "G1",  # S1 & S2: endpoint change + underpowered
                "analysis_gaming": "G2",  # S3 & S4: subgroup-only win + ITT/PP dropout asymmetry
                "plausibility": "G3",     # S5 & (S7 | S6): implausible effect + single-arm/multiple interims
                "p_hacking": "G4",        # S8 & (S1 | S3): p-value cusp + endpoint/subgroup changes
                # Legacy mappings for backward compatibility
                "primary_endpoint_success": "G1",
                "statistical_significance": "G2", 
                "clinical_significance": "G3",
                "effect_size_adequate": "G4"
            }
            
            # Track which gate IDs we've used to ensure uniqueness
            used_gate_ids = set()
            
            for gate_data in gate_assessments_data:
                gate_name = gate_data.get("gate_name", "")
                db_gate_id = gate_name_mapping.get(gate_name, "G1")  # Default to G1 if not mapped
                
                # Ensure unique gate IDs - if we've already used this ID, try the next one
                original_gate_id = db_gate_id
                counter = 1
                while db_gate_id in used_gate_ids:
                    # Try G1, G2, G3, G4 in order
                    db_gate_id = f"G{counter}"
                    counter += 1
                    if counter > 4:  # Only G1-G4 are allowed
                        db_gate_id = "G1"  # Fallback to G1
                        break
                
                used_gate_ids.add(db_gate_id)
                
                gate_assessment = GateAssessment(
                    gate_id=db_gate_id,
                    status=gate_data.get("assessment", "UNCERTAIN"),
                    rationale=[gate_data.get("rationale", "")],
                    assessment_notes=[gate_data.get("key_findings", ""), gate_data.get("concerns", "")],
                    next_steps=[gate_data.get("recommendations", "")],
                    confidence_in_assessment=gate_data.get("confidence", 0.8)
                )
                gate_assessments.append(gate_assessment)
            
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
            self.logger.error(f"LLM gate assessment extraction failed: {e}")
            return {}
    
    # Implement abstract methods from BaseLLMGenerator
    def _get_data_key(self) -> str:
        """Return the key for the main data in the LLM response."""
        return "gate_assessments"
    
    async def _extract_with_llm(self, doc_text: str, trial_context: Dict[str, Any], prompt: str) -> Dict[str, Any]:
        """Call the LLM for gate assessment extraction with a given prompt."""
        try:
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
                    logger.info(f"DEBUG: Parsed JSON successfully, gate_assessments count: {len(result.get('gate_assessments', []))}")
                except json.JSONDecodeError as e:
                    logger.error(f"DEBUG: JSON parsing failed: {e}")
                    logger.error(f"DEBUG: Raw response: {result}")
                    return {}
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM gate assessment extraction failed: {e}")
            return {}
    
    def _build_standard_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build the standard prompt for the first attempt."""
        return f"""
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

Evaluate the following key gates (based on actual gate definitions):

**G1: Alpha-Meltdown (S1 & S2)**
- alpha_meltdown: Did the trial have endpoint changes post-registration AND is underpowered? (PASS/FAIL/UNCLEAR)
- Look for: endpoint modifications, protocol amendments, underpowered sample sizes

**G2: Analysis-Gaming (S3 & S4)**  
- analysis_gaming: Did the trial show subgroup-only wins without multiplicity adjustment AND ITT/PP dropout asymmetry? (PASS/FAIL/UNCLEAR)
- Look for: subgroup analyses, missing multiplicity corrections, dropout patterns

**G3: Plausibility (S5 & (S7 | S6))**
- plausibility: Does the trial claim implausible effect sizes AND use single-arm design or multiple interims without alpha spending? (PASS/FAIL/UNCLEAR)
- Look for: unrealistic effect sizes, single-arm studies, multiple looks without correction

**G4: p-Hacking (S8 & (S1 | S3))**
- p_hacking: Does the trial have p-values near 0.05 AND endpoint changes or subgroup-only wins? (PASS/FAIL/UNCLEAR)
- Look for: p-values around 0.05, endpoint modifications, subgroup fishing

For each gate, also provide:
- rationale: Brief explanation of the assessment
- key_findings: Key findings that support the assessment
- concerns: Any concerns or limitations
- recommendations: Recommendations for next steps

Respond in JSON format:
{{
    "gate_assessments": [
        {{
            "gate_name": "alpha_meltdown",
            "assessment": "PASS/FAIL/UNCLEAR",
            "rationale": "Brief explanation",
            "key_findings": "Key findings",
            "concerns": "Any concerns",
            "recommendations": "Next steps",
            "confidence": 0.8
        }},
        ...
    ],
    "field_quotes": [
        {{
            "gate_name": "alpha_meltdown",
            "field_name": "assessment",
            "value": "PASS/FAIL/UNCLEAR",
            "evidence_quote": "exact quote from document",
            "confidence": 0.9
        }},
        ...
    ]
}}

Only include gates where you found clear evidence in the document. If a gate cannot be assessed, omit it from both the gate_assessments and field_quotes.
"""
    
    def _build_simplified_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build a simplified prompt for the second attempt."""
        return f"""
Evaluate this clinical trial document for key gate assessments.

Document: {doc_text[:2000]}
Trial: {trial_context.get('disease', 'Unknown')} - {trial_context.get('intervention', 'Unknown')}

Assess these gates:
1. alpha_meltdown: Endpoint changes + underpowered?
2. analysis_gaming: Subgroup wins + dropout issues?
3. plausibility: Unrealistic effects + design issues?
4. p_hacking: p-values near 0.05 + endpoint changes?

For each gate, provide: assessment (PASS/FAIL/UNCLEAR), rationale, and evidence quote.

JSON format:
{{
    "gate_assessments": [{{"gate_name": "alpha_meltdown", "assessment": "FAIL", "rationale": "...", "key_findings": "...", "concerns": "...", "recommendations": "...", "confidence": 0.8}}],
    "field_quotes": [{{"gate_name": "alpha_meltdown", "field_name": "assessment", "value": "FAIL", "evidence_quote": "...", "confidence": 0.9}}]
}}
"""
    
    def _build_minimal_prompt(self, doc_text: str, doc_id: str, trial_context: Dict[str, Any]) -> str:
        """Build a minimal prompt for the third attempt."""
        return f"""
Assess this trial document for gate violations:

{doc_text[:1000]}

Check for:
- Endpoint changes (G1)
- Subgroup issues (G2) 
- Unrealistic effects (G3)
- p-value problems (G4)

Return JSON with gate_assessments and field_quotes arrays.
"""
