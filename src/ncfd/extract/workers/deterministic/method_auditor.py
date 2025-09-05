"""
Deterministic Method Auditor Worker

Extracts study methodology using rule-based patterns, regex matching, and deterministic logic.
Provides an alternative to LLM-based extraction with high precision but potentially lower recall.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict

from ..base_worker import BaseWorker, WorkerResult
from ...models import EvidenceSpan, MethodCard, PocketContextCard


class DeterministicMethodAuditor(BaseWorker):
    """
    Deterministic worker for extracting study methodology from evidence spans.
    
    Uses rule-based patterns, regex matching, and deterministic logic to extract:
    - Survival method (KM, inferred_KM, not_reported)
    - Interim looks (Gehan, group sequential, none)
    - Ascertainment (RECIST, cadence)
    - Analysis denominators (response_n, ttp_os_n)
    - Site geography (with section constraints)
    """
    
    def __init__(self):
        super().__init__("DeterministicMethodAuditor", "1.0.0")
        
        # Pattern definitions for deterministic extraction
        self.survival_patterns = {
            'km_explicit': [
                r'kaplan.?meier',
                r'km\s+method',
                r'estimated\s+by\s+kaplan',
                r'kaplan.?meier\s+method'
            ],
            'logrank_cox': [
                r'log.?rank',
                r'cox\s+regression',
                r'cox\s+proportional'
            ]
        }
        
        self.interim_patterns = {
            'gehan': [
                r'gehan\s+design',
                r'gehan\s+stopping',
                r'part\s+1.*part\s+2',
                r'stage\s+1.*stage\s+2'
            ],
            'group_sequential': [
                r'group\s+sequential',
                r'sequential\s+design',
                r'interim\s+analysis'
            ]
        }
        
        self.ascertainment_patterns = {
            'recist': [
                r'recist',
                r'response\s+evaluation\s+criteria',
                r'response\s+criteria'
            ],
            'cadence': [
                r'every\s+\d+\s+cycles',
                r'every\s+\d+\s+weeks',
                r'assessment\s+every'
            ]
        }
        
        self.denominator_patterns = {
            'response_n': [
                r'evaluable\s+for\s+response\s*\(n\s*=\s*(\d+)\)',
                r'response\s+evaluable\s*\(n\s*=\s*(\d+)\)',
                r'response\s+population\s*\(n\s*=\s*(\d+)\)'
            ],
            'ttp_os_n': [
                r'survival\s+evaluable\s*\(n\s*=\s*(\d+)\)',
                r'ttp\s+evaluable\s*\(n\s*=\s*(\d+)\)',
                r'os\s+evaluable\s*\(n\s*=\s*(\d+)\)'
            ]
        }
        
        # Study phase patterns for deterministic extraction
        self.study_phase_patterns = {
            'phase_1_2': r'phase\s*1/2|phase\s*I/II|phase\s*1\s*and\s*2|phase\s*I\s*and\s*II',
            'phase_1': r'phase\s*1|phase\s*I',
            'phase_2': r'phase\s*2|phase\s*II',
            'phase_3': r'phase\s*3|phase\s*III'
        }
    
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process evidence spans to extract methodology using deterministic rules.
        
        Args:
            inputs: Dict containing:
                - evidence_spans: List[EvidenceSpan] - Methods/Protocol/SAP spans
                - design_json: Dict - Basic design information
                - pocket_context: PocketContextCard - Disease and intervention context
                
        Returns:
            WorkerResult containing MethodCard
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required evidence_spans, design_json, or pocket_context",
                    output={}
                )
            
            evidence_spans = inputs['evidence_spans']
            design_json = inputs.get('design_json', {})
            pocket_context = inputs.get('pocket_context')
            
            # Filter spans to focus on Methods sections
            methods_spans = self._filter_methods_spans(evidence_spans)
            
            # Extract methodological information using deterministic rules
            method_info = self._extract_methodology_deterministic(methods_spans, design_json, pocket_context)
            
            # Create MethodCard
            method_card = self._create_method_card(method_info, methods_spans)
            
            return WorkerResult(
                success=True,
                output=method_card,
                metadata={
                    'worker': 'DeterministicMethodAuditor',
                    'version': '1.0',
                    'processed_spans': len(methods_spans),
                    'extracted_fields': len([f for f in method_info.values() if f is not None])
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                error_message=f"Deterministic method auditing failed: {str(e)}",
                output={}
            )
    
    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required evidence spans and context."""
        required_keys = ['evidence_spans', 'design_json', 'pocket_context']
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs['evidence_spans'], list):
            return False
            
        if not inputs['evidence_spans']:
            return False
            
        # Validate that all spans are EvidenceSpan objects
        for span in inputs['evidence_spans']:
            if not isinstance(span, EvidenceSpan):
                return False
                
        return True
    
    def _filter_methods_spans(self, spans: List[EvidenceSpan]) -> List[EvidenceSpan]:
        """Filter spans to focus on Methods/Protocol/SAP sections."""
        methods_sections = ['methods', 'protocol', 'sap', 'statistical analysis']
        return [span for span in spans if span.section.lower() in methods_sections]
    
    def _extract_methodology_deterministic(self, spans: List[EvidenceSpan], 
                                         design_json: Dict[str, Any], 
                                         pocket_context: Any) -> Dict[str, Any]:
        """Extract methodology using deterministic rules and patterns."""
        method_info = {
            'survival_method': 'not_reported',
            'interim_looks': 'none',
            'ascertainment': 'not_reported',
            'assessment_interval': None,
            'response_n': None,
            'ttp_os_n': None,
            'site_geography': 'not_reported',
            'design_archetype': None,
            'gehan_two_stage': None,
            'interim_looks_count': None,
            'primary_endpoint': None,
            'secondary_endpoints': [],
            'span_ids': []
        }
        
        # Extract survival method
        method_info['survival_method'] = self._extract_survival_method(spans)
        
        # Extract interim looks and Gehan design
        method_info['interim_looks'] = self._extract_interim_looks(spans)
        method_info['gehan_two_stage'] = self._extract_gehan_two_stage(spans)
        method_info['interim_looks_count'] = self._extract_interim_looks_count(spans)
        
        # Extract ascertainment and assessment interval
        method_info['ascertainment'] = self._extract_ascertainment(spans)
        method_info['assessment_interval'] = self._extract_assessment_interval(spans)
        
        # Extract design archetype
        method_info['design_archetype'] = self._extract_design_archetype(spans)
        
        # Extract endpoints
        method_info['primary_endpoint'] = self._extract_primary_endpoint(spans)
        method_info['secondary_endpoints'] = self._extract_secondary_endpoints(spans)
        
        # Extract analysis denominators
        response_n, ttp_os_n = self._extract_denominators(spans)
        method_info['response_n'] = response_n
        method_info['ttp_os_n'] = ttp_os_n
        
        # Extract site geography (Methods-only constraint)
        method_info['site_geography'] = self._extract_site_geography(spans)
        
        # Extract study phase using deterministic patterns
        method_info['study_phase'] = self._extract_study_phase(spans)
        
        # Collect span IDs
        method_info['span_ids'] = [span.span_id for span in spans]
        
        return method_info
    
    def _extract_survival_method(self, spans: List[EvidenceSpan]) -> str:
        """Extract survival method using deterministic patterns."""
        text = ' '.join([span.quote.lower() for span in spans])
        
        # Check for explicit KM mentions (since we have a direct KM span)
        for pattern in self.survival_patterns['km_explicit']:
            if re.search(pattern, text, re.IGNORECASE):
                return 'km'
        
        # Check for log-rank/Cox (inferred KM when only log-rank is present)
        for pattern in self.survival_patterns['logrank_cox']:
            if re.search(pattern, text, re.IGNORECASE):
                return 'inferred_km'
        
        return 'not_reported'
    
    def _extract_interim_looks(self, spans: List[EvidenceSpan]) -> str:
        """Extract interim looks using deterministic patterns."""
        text = ' '.join([span.quote.lower() for span in spans])
        
        # Check for Gehan design
        for pattern in self.interim_patterns['gehan']:
            if re.search(pattern, text, re.IGNORECASE):
                return 'gehan'
        
        # Check for group sequential
        for pattern in self.interim_patterns['group_sequential']:
            if re.search(pattern, text, re.IGNORECASE):
                return 'group_sequential'
        
        return 'none'
    
    def _extract_ascertainment(self, spans: List[EvidenceSpan]) -> str:
        """Extract ascertainment using deterministic patterns."""
        text = ' '.join([span.quote.lower() for span in spans])
        
        # Check for RECIST
        for pattern in self.ascertainment_patterns['recist']:
            if re.search(pattern, text, re.IGNORECASE):
                return 'recist'
        
        # Check for cadence
        for pattern in self.ascertainment_patterns['cadence']:
            if re.search(pattern, text, re.IGNORECASE):
                return 'cadence'
        
        return 'not_reported'
    
    def _extract_denominators(self, spans: List[EvidenceSpan]) -> Tuple[Optional[int], Optional[int]]:
        """Extract analysis denominators using deterministic patterns."""
        text = ' '.join([span.quote.lower() for span in spans])
        
        response_n = None
        ttp_os_n = None
        
        # Extract response_n
        for pattern in self.denominator_patterns['response_n']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                response_n = int(match.group(1))
                break
        
        # Extract ttp_os_n
        for pattern in self.denominator_patterns['ttp_os_n']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                ttp_os_n = int(match.group(1))
                break
        
        return response_n, ttp_os_n
    
    def _extract_site_geography(self, spans: List[EvidenceSpan]) -> str:
        """Extract site geography with Methods-only constraint."""
        # Only look at Methods section spans
        methods_spans = [span for span in spans if span.section.lower() == 'methods']
        
        if not methods_spans:
            return 'not_reported'
        
        text = ' '.join([span.quote.lower() for span in methods_spans])
        
        # Simple patterns for site geography
        if re.search(r'multicenter|multi.?center|multiple\s+sites', text, re.IGNORECASE):
            return 'multicenter'
        elif re.search(r'single\s+center|single.?center|single\s+site', text, re.IGNORECASE):
            return 'single_center'
        
        return 'not_reported'
    
    def _extract_study_phase(self, spans: List[EvidenceSpan]) -> str:
        """Extract study phase using deterministic patterns with Roman numeral handling."""
        # Only look at Methods section spans
        methods_spans = [span for span in spans if span.section.lower() == 'methods']
        
        if not methods_spans:
            return 'not_reported'
        
        text = ' '.join([span.quote.lower() for span in methods_spans])
        
        # First normalize Roman numerals to Arabic numerals
        normalized_text = self._normalize_phase_text(text)
        
        # Then extract using the normalized text
        for phase, pattern in self.study_phase_patterns.items():
            if re.search(pattern, normalized_text, re.IGNORECASE):
                return phase
        
        return 'not_reported'
    
    def _normalize_phase_text(self, text: str) -> str:
        """Normalize phase text using shared TextNormalizer."""
        from ...utils.text_normalization import TextNormalizer
        return TextNormalizer.normalize_phase_text(text)
    
    def _extract_gehan_two_stage(self, spans: List[EvidenceSpan]) -> Optional[bool]:
        """Extract Gehan two-stage design using explicit Gehan span."""
        text = ' '.join([span.quote.lower() for span in spans])
        
        # Check for explicit Gehan two-stage design
        if re.search(r'gehan\s+two.?stage\s+design', text, re.IGNORECASE):
            return True
        
        return None
    
    def _extract_interim_looks_count(self, spans: List[EvidenceSpan]) -> Optional[int]:
        """Extract number of interim looks based on Gehan design."""
        text = ' '.join([span.quote.lower() for span in spans])
        
        # Gehan two-stage design typically has 1 interim look
        if re.search(r'gehan\s+two.?stage\s+design', text, re.IGNORECASE):
            return 1
        
        return None
    
    def _extract_assessment_interval(self, spans: List[EvidenceSpan]) -> Optional[str]:
        """Extract assessment interval from cadence span."""
        text = ' '.join([span.quote.lower() for span in spans])
        
        # Extract "every two cycles" pattern
        match = re.search(r'every\s+(two|2)\s+cycles?', text, re.IGNORECASE)
        if match:
            return "every two cycles"
        
        return None
    
    def _extract_design_archetype(self, spans: List[EvidenceSpan]) -> Optional[str]:
        """Extract design archetype based on study characteristics."""
        text = ' '.join([span.quote.lower() for span in spans])
        
        # Check for single-arm phase 2 with Gehan design
        if (re.search(r'single.?arm', text, re.IGNORECASE) and 
            re.search(r'phase\s*2|phase\s*ii', text, re.IGNORECASE) and
            re.search(r'gehan\s+two.?stage\s+design', text, re.IGNORECASE)):
            return "single_arm_phase2_gehan"
        
        return None
    
    def _extract_primary_endpoint(self, spans: List[EvidenceSpan]) -> Optional[str]:
        """Extract primary endpoint from explicit endpoint spans."""
        text = ' '.join([span.quote.lower() for span in spans])
        
        # Check for overall response rate as primary endpoint
        if re.search(r'primary\s+endpoint.*overall\s+response\s+rate', text, re.IGNORECASE):
            return "overall response rate"
        
        return None
    
    def _extract_secondary_endpoints(self, spans: List[EvidenceSpan]) -> List[str]:
        """Extract secondary endpoints from explicit endpoint spans."""
        text = ' '.join([span.quote.lower() for span in spans])
        secondary_endpoints = []
        
        # Check for progression-free survival
        if re.search(r'progression.?free\s+survival', text, re.IGNORECASE):
            secondary_endpoints.append("progression-free survival")
        
        # Check for overall survival
        if re.search(r'overall\s+survival', text, re.IGNORECASE):
            secondary_endpoints.append("overall survival")
        
        return secondary_endpoints
    
    def _create_method_card(self, method_info: Dict[str, Any], spans: List[EvidenceSpan]) -> MethodCard:
        """Create MethodCard from extracted information."""
        # Get doc_id from spans
        doc_id = None
        if spans:
            doc_id = spans[0].doc_id
        
        if not doc_id:
            raise ValueError("Cannot create MethodCard without a valid doc_id from spans")
        
        return MethodCard(
            doc_id=doc_id,
            primary_endpoint=method_info['primary_endpoint'] or "not_specified",  # Required field
            secondary_endpoints=method_info['secondary_endpoints'],
            design_archetype=method_info['design_archetype'],
            gehan_two_stage=method_info['gehan_two_stage'],
            interim_looks=[{"timing": "interim", "alpha_spent": 0.05, "stop_rules": []}] if method_info['interim_looks_count'] else [],
            endpoint_ascertainment=method_info['ascertainment'],
            assessment_interval=method_info['assessment_interval'],
            study_phase=method_info['study_phase'],
            span_ids=method_info['span_ids'],
            # Add extracted fields as metadata
            protocol_features=[
                f"survival_method:{method_info['survival_method']}",
                f"interim_looks:{method_info['interim_looks']}",
                f"ascertainment:{method_info['ascertainment']}",
                f"site_geography:{method_info['site_geography']}",
                f"study_phase:{method_info['study_phase']}"
            ],
            # Store numeric values in metadata
            site_geography={
                'response_n': method_info['response_n'],
                'ttp_os_n': method_info['ttp_os_n']
            }
        )
