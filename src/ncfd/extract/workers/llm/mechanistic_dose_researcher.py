"""
Mechanistic Dose Researcher Worker

Performs self-research to analyze disease pathways, mechanism of action, PK/PD requirements,
and dosing rationale with evidence-based citations.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ..base_llm_worker import BaseLLMWorker, WorkerResult
from ...models import EvidenceSpan, PocketContextCard


@dataclass
class Citation:
    """Citation for evidence-based claims."""
    type: str  # "PMID", "DOI", "NCT", "URL"
    value: str
    note: Optional[str] = None


@dataclass
class PKPDRequirement:
    """PK/PD requirement specification."""
    exposure_metric: str
    target_value: str
    rationale: str
    citations: List[Citation] = field(default_factory=list)


@dataclass
class DoseRange:
    """Recommended dose range specification."""
    unit: str
    loading: Optional[str] = None
    maintenance: Optional[str] = None
    mg_per_kg: Optional[str] = None


@dataclass
class MechanisticDoseCard:
    """Structured output for mechanistic and dosing analysis."""
    mechanism_summary: str
    dose_time_course_sanity: str
    therapeutic_window: str
    class_priors: str
    confidence: str  # "High", "Medium", "Low"
    canonical_pathways: List[str] = field(default_factory=list)
    key_nodes: List[str] = field(default_factory=list)
    biomarkers: List[str] = field(default_factory=list)
    pkpd_requirements: List[PKPDRequirement] = field(default_factory=list)
    recommended_dose_ranges: List[DoseRange] = field(default_factory=list)
    contraindications: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)


class MechanisticDoseResearcher(BaseLLMWorker):
    """
    LLM worker for mechanistic pathway analysis and dosing requirements research.
    
    Performs self-research to analyze:
    - Disease pathways and mechanism of action
    - PK/PD requirements and exposure targets
    - Dose-response relationships and time-course sanity
    - Therapeutic windows and contraindications
    - Class priors and red flags
    
    All claims must be evidence-based with citations.
    """
    
    def __init__(self):
        super().__init__("mechanistic_dose_researcher", "1.0.0")
        self.logger = logging.getLogger(f"{__name__}.MechanisticDoseResearcher")
    
    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required data for mechanistic analysis."""
        required_fields = ['trial_context', 'evidence_spans']
        
        for field in required_fields:
            if field not in inputs:
                self.logger.error(f"Missing required field: {field}")
                return False
        
        trial_context = inputs['trial_context']
        if not isinstance(trial_context, dict):
            self.logger.error("trial_context must be a dictionary")
            return False
        
        # Check for minimum required trial context
        if not trial_context.get('disease') and not trial_context.get('indication'):
            self.logger.error("trial_context must contain 'disease' or 'indication'")
            return False
        
        evidence_spans = inputs['evidence_spans']
        if not isinstance(evidence_spans, list):
            self.logger.error("evidence_spans must be a list")
            return False
        
        return True
    
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process trial context and evidence spans to perform mechanistic analysis.
        
        Args:
            inputs: Dict containing:
                - trial_context: Dict with disease, intervention, phase, etc.
                - evidence_spans: List[EvidenceSpan] - MOA/PK/biomarker spans
                - pocket_context: Optional[PocketContextCard] - Disease context
                - design_json: Optional[Dict] - Trial design information
                
        Returns:
            WorkerResult containing MechanisticDoseCard
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs for mechanistic dose research",
                    output={}
                )
            
            trial_context = inputs['trial_context']
            evidence_spans = inputs['evidence_spans']
            pocket_context = inputs.get('pocket_context')
            design_json = inputs.get('design_json', {})
            
            # Filter spans for MOA/PK/biomarker content
            relevant_spans = self._filter_relevant_spans(evidence_spans)
            
            # Build research prompt
            prompt = self._build_research_prompt(trial_context, relevant_spans, pocket_context, design_json)
            
            # Define JSON schema for structured output
            json_schema = self._get_output_schema()
            
            # Make LLM call
            response = self.call_llm_sync(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self._get_system_prompt(),
                json_output=True,
                json_schema=json_schema,
                max_tokens=4000,
                temperature=0.1
            )
            
            # Parse response
            try:
                result_data = json.loads(response.content)
                mechanistic_card = self._parse_mechanistic_card(result_data)
                
                return WorkerResult(
                    success=True,
                    output={
                        'mechanistic_dose_card': mechanistic_card,
                        'processed_spans': len(relevant_spans),
                        'total_citations': len(mechanistic_card.citations)
                    },
                    metadata={
                        'worker': 'MechanisticDoseResearcher',
                        'version': '1.0.0',
                        'confidence': mechanistic_card.confidence,
                        'red_flags_count': len(mechanistic_card.red_flags)
                    }
                )
                
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse LLM response as JSON: {e}")
                return WorkerResult(
                    success=False,
                    error_message=f"Failed to parse LLM response: {e}",
                    output={}
                )
                
        except Exception as e:
            self.logger.error(f"Mechanistic dose research failed: {e}")
            return WorkerResult(
                success=False,
                error_message=f"Mechanistic dose research failed: {str(e)}",
                output={}
            )
    
    def _filter_relevant_spans(self, evidence_spans: List[EvidenceSpan]) -> List[EvidenceSpan]:
        """Filter spans for MOA/PK/biomarker content."""
        relevant_keywords = [
            'mechanism', 'pathway', 'target', 'receptor', 'enzyme', 'inhibitor', 'agonist',
            'pharmacokinetics', 'pharmacodynamics', 'pk', 'pd', 'clearance', 'half-life',
            'bioavailability', 'metabolism', 'exposure', 'concentration', 'dose',
            'biomarker', 'surrogate', 'endpoint', 'response', 'efficacy', 'safety'
        ]
        
        relevant_spans = []
        for span in evidence_spans:
            span_text_lower = span.text.lower()
            if any(keyword in span_text_lower for keyword in relevant_keywords):
                relevant_spans.append(span)
        
        # Limit to top 20 most relevant spans to manage token budget
        return relevant_spans[:20]
    
    def _build_research_prompt(self, trial_context: Dict[str, Any], 
                              evidence_spans: List[EvidenceSpan],
                              pocket_context: Optional[PocketContextCard],
                              design_json: Dict[str, Any]) -> str:
        """Build the research prompt for mechanistic analysis."""
        
        # Extract key trial information
        disease = trial_context.get('disease', trial_context.get('indication', 'Unknown'))
        intervention = trial_context.get('intervention', 'Unknown')
        phase = trial_context.get('phase', 'Unknown')
        primary_endpoint = trial_context.get('primary_endpoint', 'Not specified')
        
        # Build evidence summary
        evidence_summary = ""
        if evidence_spans:
            evidence_summary = "EVIDENCE SPANS:\n"
            for i, span in enumerate(evidence_spans[:10]):  # Limit to top 10
                evidence_summary += f"{i+1}. [{span.section}] {span.text[:200]}...\n"
        
        # Add pocket context if available
        pocket_summary = ""
        if pocket_context:
            pocket_summary = f"""
DISEASE CONTEXT:
- Disease: {pocket_context.disease}
- Stage: {pocket_context.disease_stage or 'Not specified'}
- Severity: {pocket_context.disease_severity or 'Not specified'}
- Mechanism of Action: {pocket_context.mechanism_of_action or 'Not specified'}
- Intervention Class: {pocket_context.intervention_class}
- Route: {pocket_context.route or 'Not specified'}
- Dose Form: {pocket_context.dose_form or 'Not specified'}
"""
        
        prompt = f"""
You are a senior mechanistic PK/PD analyst conducting deep research on {disease} and {intervention}.

TRIAL CONTEXT:
- Disease/Indication: {disease}
- Intervention: {intervention}
- Phase: {phase}
- Primary Endpoint: {primary_endpoint}

{pocket_summary}

{evidence_summary}

TASK:
Perform comprehensive mechanistic and dosing analysis with the following requirements:

1. **Disease Pathway Analysis**: Identify canonical pathways involved in {disease}
2. **MOA Mapping**: Map {intervention} to relevant pathways and key nodes
3. **PK/PD Requirements**: Determine exposure targets and rationale
4. **Dose-Response Sanity**: Assess dose-response relationships and time-course plausibility
5. **Therapeutic Window**: Define safe and effective dose ranges
6. **Class Priors**: Analyze historical context and class precedents
7. **Red Flags**: Identify mechanistic or dosing concerns

CRITICAL REQUIREMENTS:
- **Cite or Skip**: Every claim must be supported by a citation (PMID, DOI, NCT, URL)
- **Evidence-Based**: Base all recommendations on published literature
- **Conservative**: If evidence is unclear, mark as "unknown" with rationale
- **Structured Output**: Use the exact JSON schema provided

SEARCH QUERIES TO COMPOSE AND EXECUTE:
- "{disease} signaling pathway"
- "{disease} biomarkers"
- "{intervention} mechanism of action"
- "{intervention} pharmacokinetics"
- "{intervention} dose response"
- "{intervention} therapeutic window"
- "{intervention} class" AND "{disease}"
- "{intervention} contraindications"

Focus on:
- Human clinical data (P2/P3 studies)
- Systematic reviews and meta-analyses
- FDA guidance documents
- Recent publications (last 10 years)
- Classmate data for similar mechanisms

Provide a comprehensive analysis that would inform clinical development decisions.
"""
        
        return prompt
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for mechanistic analysis."""
        return """You are a senior mechanistic PK/PD analyst with expertise in clinical pharmacology and drug development.

Your role is to:
1. Analyze disease pathways and mechanism of action
2. Determine PK/PD requirements and exposure targets
3. Assess dose-response relationships and time-course plausibility
4. Identify therapeutic windows and contraindications
5. Provide evidence-based recommendations

IMPORTANT CONSTRAINTS:
- Every claim must be supported by a citation (PMID, DOI, NCT, URL)
- If evidence is insufficient, mark as "unknown" with rationale
- Be conservative - prefer "unknown" over speculation
- Focus on human clinical data and regulatory guidance
- Consider class priors and historical context

Output must be structured according to the provided JSON schema with all required fields."""
    
    def _get_output_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for structured output."""
        return {
            "type": "object",
            "properties": {
                "mechanism_summary": {
                    "type": "string",
                    "description": "Concise summary of mechanism of action and pathway involvement"
                },
                "canonical_pathways": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of canonical pathways involved in the disease"
                },
                "key_nodes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key molecular nodes/targets in the pathway"
                },
                "biomarkers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relevant biomarkers for the disease/mechanism"
                },
                "pkpd_requirements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "exposure_metric": {"type": "string"},
                            "target_value": {"type": "string"},
                            "rationale": {"type": "string"},
                            "citations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["PMID", "DOI", "NCT", "URL"]},
                                        "value": {"type": "string"},
                                        "note": {"type": "string"}
                                    },
                                    "required": ["type", "value"]
                                }
                            }
                        },
                        "required": ["exposure_metric", "target_value", "rationale"]
                    }
                },
                "dose_time_course_sanity": {
                    "type": "string",
                    "description": "Assessment of dose-response and time-course plausibility"
                },
                "recommended_dose_ranges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "unit": {"type": "string"},
                            "loading": {"type": "string"},
                            "maintenance": {"type": "string"},
                            "mg_per_kg": {"type": "string"}
                        },
                        "required": ["unit"]
                    }
                },
                "therapeutic_window": {
                    "type": "string",
                    "description": "Definition of safe and effective dose range"
                },
                "class_priors": {
                    "type": "string",
                    "description": "Historical context and class precedents"
                },
                "contraindications": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "red_flags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Mechanistic or dosing concerns"
                },
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["PMID", "DOI", "NCT", "URL"]},
                            "value": {"type": "string"},
                            "note": {"type": "string"}
                        },
                        "required": ["type", "value"]
                    }
                },
                "confidence": {
                    "type": "string",
                    "enum": ["High", "Medium", "Low"],
                    "description": "Overall confidence in the analysis"
                }
            },
            "required": [
                "mechanism_summary", "canonical_pathways", "key_nodes", "biomarkers",
                "pkpd_requirements", "dose_time_course_sanity", "recommended_dose_ranges",
                "therapeutic_window", "class_priors", "contraindications", "red_flags",
                "citations", "confidence"
            ]
        }
    
    def _parse_mechanistic_card(self, data: Dict[str, Any]) -> MechanisticDoseCard:
        """Parse LLM response into MechanisticDoseCard."""
        
        # Parse PKPD requirements
        pkpd_requirements = []
        for req_data in data.get('pkpd_requirements', []):
            citations = [Citation(**cit) for cit in req_data.get('citations', [])]
            pkpd_requirements.append(PKPDRequirement(
                exposure_metric=req_data['exposure_metric'],
                target_value=req_data['target_value'],
                rationale=req_data['rationale'],
                citations=citations
            ))
        
        # Parse dose ranges
        dose_ranges = []
        for range_data in data.get('recommended_dose_ranges', []):
            dose_ranges.append(DoseRange(
                unit=range_data['unit'],
                loading=range_data.get('loading'),
                maintenance=range_data.get('maintenance'),
                mg_per_kg=range_data.get('mg_per_kg')
            ))
        
        # Parse citations
        citations = [Citation(**cit) for cit in data.get('citations', [])]
        
        return MechanisticDoseCard(
            mechanism_summary=data['mechanism_summary'],
            canonical_pathways=data.get('canonical_pathways', []),
            key_nodes=data.get('key_nodes', []),
            biomarkers=data.get('biomarkers', []),
            pkpd_requirements=pkpd_requirements,
            dose_time_course_sanity=data['dose_time_course_sanity'],
            recommended_dose_ranges=dose_ranges,
            therapeutic_window=data['therapeutic_window'],
            class_priors=data['class_priors'],
            contraindications=data.get('contraindications', []),
            red_flags=data.get('red_flags', []),
            citations=citations,
            confidence=data['confidence']
        )
