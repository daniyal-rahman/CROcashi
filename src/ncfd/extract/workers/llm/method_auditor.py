# src/ncfd/extract/workers/llm/method_auditor.py
"""
Method Auditor Worker

Reconstructs study methodology from Methods/Protocol/SAP spans, extracting the "non-obvious" bits
like estimand, alpha structure, interim plans, and missingness policies.
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict

from ..base_worker import BaseWorker, WorkerResult
from ...models import EvidenceSpan, MethodCard, PocketContextCard
from ....utils.study_card_utils import (
    extract_numeric_value,
    normalize_units,
    normalize_endpoint_name
)


class MethodAuditor(BaseWorker):
    """
    Worker for reconstructing study methodology from evidence spans.
    
    Extracts estimand, alpha structure, interim plans, missingness policies,
    and other methodological details that aren't explicitly stated in tables.
    """
    
    def __init__(self, max_spans_per_pass: int = 8):
        super().__init__("MethodAuditor", "1.0.0")
        self.max_spans_per_pass = max_spans_per_pass
        
        # Patterns for extracting methodological information
        self.estimand_patterns = {
            'population': [
                r'(inclusion|eligible|enrolled|randomized)\s+patients?\s+with\s+([^.]*)',
                r'patients?\s+with\s+([^.]*)',
                r'population\s+consisted\s+of\s+([^.]*)'
            ],
            'endpoint': [
                r'(primary|secondary|co-primary|key)\s+(endpoint|outcome|objective)\s+([^.]*)',
                r'(endpoint|outcome|objective)\s+([^.]*)',
                r'measured\s+([^.]*)'
            ],
            'intercurrent': [
                r'(intercurrent|intercurrent\s+event|intercurrent\s+events?)\s+([^.]*)',
                r'(discontinuation|withdrawal|rescue|crossover)\s+([^.]*)',
                r'(missing|missingness|missing\s+data)\s+([^.]*)'
            ]
        }
        
        # Study phase patterns - order matters! More specific patterns first
        self.study_phase_patterns = {
            'phase_1_2': r'phase\s*1/2|phase\s*I/II|phase\s*1\s*and\s*2|phase\s*I\s*and\s*II',
            'phase_1': r'phase\s*1|phase\s*I',
            'phase_2': r'phase\s*2|phase\s*II',
            'phase_3': r'phase\s*3|phase\s*III'
        }
        
        # Blinding patterns
        self.blinding_patterns = {
            'none_open_label': [
                r'blinding\s+(was\s+)?not\s+performed',
                r'open.?label|open\s+label',
                r'unblinded|unblinding',
                r'no\s+blinding'
            ],
            'single_blind': [
                r'single.?blind|single\s+blind',
                r'investigator.?blind|investigator\s+blind'
            ],
            'double_blind': [
                r'double.?blind|double\s+blind',
                r'patient\s+and\s+investigator\s+blind'
            ]
        }
        
        # Endpoint ascertainment patterns
        self.endpoint_ascertainment_patterns = {
            'RECIST': [
                r'RECIST|Response\s+Evaluation\s+Criteria\s+in\s+Solid\s+Tumors',
                r'response\s+evaluation\s+criteria'
            ],
            'assessment_interval': [
                r'every\s+(two|2)\s+cycles?',
                r'every\s+cycle',
                r'(\d+)\s+weeks?\s+intervals?'
            ]
        }
        
        # Assessment interval patterns (to prevent cadence from being extracted as effect_size)
        self.assessment_interval_patterns = {
            'weekly': [
                r'every\s+week|weekly|q1w|q1\s*week',
                r'assessment\s+every\s+week|assessment\s+weekly'
            ],
            'biweekly': [
                r'every\s+(two|2)\s+weeks?|biweekly|q2w|q2\s*weeks?',
                r'assessment\s+every\s+(two|2)\s+weeks?|assessment\s+biweekly'
            ],
            'every_6_weeks': [
                r'every\s+(six|6)\s+weeks?|q6w|q6\s*weeks?',
                r'assessment\s+every\s+(six|6)\s+weeks?|assessment\s+q6w',
                r'assessment\s+every\s+(six|6)\s+weeks?'
            ],
            'monthly': [
                r'every\s+month|monthly|q1m|q1\s*month',
                r'assessment\s+every\s+month|assessment\s+monthly'
            ],
            'every_3_months': [
                r'every\s+(three|3)\s+months?|q3m|q3\s*months?',
                r'assessment\s+every\s+(three|3)\s+months?|assessment\s+q3m'
            ]
        }
        
        # Interim design patterns
        self.interim_design_patterns = {
            'gehan_two_stage': [
                r'gehan\s+two.?stage|gehan\s+two\s+stage',
                r'two.?stage\s+phase\s*2|two\s+stage\s+phase\s*II',
                r'gehan\s+design|gehan\s+method'
            ],
            'simon_two_stage': [
                r'simon\s+two.?stage|simon\s+two\s+stage'
            ]
        }
        
        # Statistics patterns
        self.stats_patterns = [
            r'kaplan.?meier|kaplan.?meir|kaplan\s+meier|kaplan\s+meir',
            r'log.?rank|log\s+rank',
            r'cox\s+proportional\s+hazards'
        ]
        
        # Analysis denominators patterns
        self.analysis_denominators_patterns = {
            'response_n': [
                r'(\d+)\s+patients?\s+for\s+response',
                r'response\s+in\s+(\d+)\s+patients?',
                r'(\d+)\s+patients?\s+assessable\s+for\s+response'
            ],
            'ttp_os_n': [
                r'(\d+)\s+patients?\s+for\s+(ttp|os|survival)',
                r'(ttp|os|survival)\s+in\s+(\d+)\s+patients?'
            ]
        }
        
        # Alpha structure patterns
        self.alpha_patterns = {
            'one_sided': [
                r'one.?sided|one.?tailed|one.?sided\s+test|one.?tailed\s+test',
                r'α\s*=\s*0\.05|alpha\s*=\s*0\.05',
                r'significance\s+level\s+0\.05'
            ],
            'two_sided': [
                r'two.?sided|two.?tailed|two.?sided\s+test|two.?tailed\s+test',
                r'α\s*=\s*0\.025|alpha\s*=\s*0\.025',
                r'significance\s+level\s+0\.025'
            ],
            'multiplicity': [
                r'bonferroni|bonferroni\s+correction|bonferroni\s+adjustment',
                r'holm|holm.?bonferroni|step.?down',
                r'gatekeeping|hierarchical|hierarchy',
                r'family.?wise|familywise|fwer'
            ]
        }
        
        # Interim analysis patterns
        self.interim_patterns = {
            'looks': [
                r'(\d+)%\s+and\s+(\d+)%\s+of\s+events',  # Put percentage pattern first
                r'(\d+)\s+(interim|interim\s+analysis|interim\s+looks?)',
                r'interim\s+analysis\s+at\s+(\d+)\s+',
                r'(\d+)\s+planned\s+analyses',
                r'interim\s+analysis\s+was\s+planned\s+at\s+(\d+)%'
            ],
            'timing': [
                r'(\d+)\s+(weeks?|months?|years?|days?)\s+(after|post|from)',
                r'(\d+)\s+(weeks?|months?|years?|days?)\s+(enrollment|randomization)',
                r'(\d+)\s+(weeks?|months?|years?|days?)\s+(follow.?up|followup)'
            ],
            'spending': [
                r'alpha\s+spending|spending\s+function|alpha\s+allocation',
                r'obrien.?fleming|obrien\s+fleming|o\'brien.?fleming',
                r'pocock|pocock\s+bound|pocock\s+boundary',
                r'lan.?demets|lan\s+demets|lan.?demets\s+boundary'
            ]
        }
        
        # Analysis set patterns
        self.analysis_set_patterns = {
            'ITT': r'(intent.?to.?treat|ITT|intention\s+to\s+treat)',
            'mITT': r'(modified\s+intent.?to.?treat|mITT|modified\s+ITT)',
            'PP': r'(per\s+protocol|PP|per.?protocol)',
            'safety': r'(safety\s+population|safety\s+set|safety\s+analysis)',
            'efficacy': r'(efficacy\s+population|efficacy\s+set|efficacy\s+analysis)'
        }
        
        # Missingness patterns
        self.missingness_patterns = {
            'MAR': [
                r'missing\s+at\s+random|MAR|missing\s+completely\s+at\s+random|MCAR',
                r'assumption\s+of\s+randomness|random\s+missing'
            ],
            'MNAR': [
                r'missing\s+not\s+at\s+random|MNAR|informative\s+missing',
                r'non.?random\s+missing|systematic\s+missing'
            ],
            'imputation': [
                r'multiple\s+imputation|MI|imputation|imputed',
                r'last\s+observation\s+carried\s+forward|LOCF',
                r'worst.?case|best.?case|baseline\s+carried\s+forward'
            ]
        }
        
        # Endpoint ascertainment patterns
        self.ascertainment_patterns = {
            'CEC': [
                r'central\s+endpoint\s+committee|CEC|central\s+review|central\s+adjudication',
                r'independent\s+review|independent\s+adjudication|blinded\s+review'
            ],
            'local': [
                r'local\s+investigator|local\s+assessment|site\s+assessment',
                r'investigator.?assessed|site.?assessed'
            ],
            'blinded': [
                r'blinded|blinding|masked|masking',
                r'double.?blind|single.?blind|triple.?blind'
            ]
        }

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required evidence spans and design information."""
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
                
        # Validate design_json is a dict
        if not isinstance(inputs['design_json'], dict):
            return False
            
        # Validate pocket_context is a PocketContextCard
        if not isinstance(inputs['pocket_context'], PocketContextCard):
            return False
                
        return True

    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process evidence spans to reconstruct study methodology.
        
        Args:
            inputs: Dict containing:
                - evidence_spans: List[EvidenceSpan] - Methods/Protocol/SAP spans
                - design_json: Dict - Basic design information (arms/N/endpoints)
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
            design_json = inputs['design_json']
            pocket_context = inputs['pocket_context']
            
            # Filter spans to focus on Methods sections
            methods_spans = self._filter_methods_spans(evidence_spans)
            
            # Extract methodological information
            method_info = self._extract_methodology(methods_spans, design_json, pocket_context)
            
            # Create MethodCard
            method_card = self._create_method_card(method_info, methods_spans)
            
            return WorkerResult(
                success=True,
                output={
                    'method_card': method_card,
                    'processed_spans': len(methods_spans),
                    'extracted_fields': len([f for f in method_info.values() if f is not None])
                },
                metadata={
                    'worker': 'MethodAuditor',
                    'version': '1.0',
                    'max_spans_processed': len(methods_spans)
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                error_message=f"Error processing methodology: {str(e)}",
                output={}
            )

    def _filter_methods_spans(self, spans: List[EvidenceSpan]) -> List[EvidenceSpan]:
        """Filter spans to focus on Methods sections with high confidence."""
        methods_spans = []
        
        for span in spans:
            # Focus on Methods, Protocol, and SAP sections
            if span.section.lower() in ['methods', 'protocol', 'sap', 'statistical_analysis_plan']:
                # Filter out low-quality spans
                if span.confidence >= 0.7:
                    methods_spans.append(span)
        
        return methods_spans
    
    def _find_supporting_spans(self, spans: List[EvidenceSpan], pattern: str) -> List[str]:
        """Find spans that contain a given regex pattern and return their span_ids."""
        supporting_span_ids = []
        compiled_pattern = re.compile(pattern, re.IGNORECASE)
        
        for span in spans:
            if span.quote and compiled_pattern.search(span.quote):
                supporting_span_ids.append(span.span_id)
        
        return supporting_span_ids

    def _extract_methodology(self, spans: List[EvidenceSpan], design_json: Dict[str, Any], 
                           pocket_context: PocketContextCard) -> Dict[str, Any]:
        """Extract methodological information from evidence spans."""
        method_info = {}
        
        # Combine all span text for analysis
        combined_text = ' '.join([span.quote for span in spans])
        
        # Extract core design information
        method_info.update(self._extract_core_design(combined_text, design_json))
        
        # Extract analysis information
        method_info.update(self._extract_analysis_info(combined_text, design_json))
        
        # Extract protocol information
        method_info.update(self._extract_protocol_info(combined_text, pocket_context))
        
        # Validate and add warnings
        method_info['warnings'] = self._validate_methodology(method_info, design_json)
        
        return method_info
    
    def _extract_core_design(self, text: str, design_json: Dict[str, Any]) -> Dict[str, Any]:
        """Extract core design information."""
        return {
            'estimand': self._extract_estimand(text, design_json),
            'alpha_structure': self._extract_alpha_structure(text),
            'interim': self._extract_interim_plan(text, []),  # spans passed separately
            'gehan_two_stage': self._extract_gehan_two_stage(text),
            'design_archetype': self._determine_design_archetype(text),
            'survival_method': self._extract_survival_method(text),
            'study_phase': self._extract_study_phase(text),
            'blinding_level': self._extract_blinding_level(text),
            'primary_endpoint': self._extract_primary_endpoint(text),
            'secondary_endpoints': self._extract_secondary_endpoints(text)
        }
    
    def _extract_analysis_info(self, text: str, design_json: Dict[str, Any]) -> Dict[str, Any]:
        """Extract analysis-related information."""
        return {
            'analysis_set': self._extract_analysis_sets(text, design_json),
            'missingness': self._extract_missingness_policies(text),
            'endpoint_ascertainment': self._extract_endpoint_ascertainment(text),
            'stats': self._extract_statistics_methods(text),
            'analysis_denominators': self._extract_analysis_denominators(text)
        }
    
    def _extract_protocol_info(self, text: str, pocket_context: PocketContextCard) -> Dict[str, Any]:
        """Extract protocol-related information."""
        return {
            'protocol_features': self._extract_protocol_features(text),
            'assay_thresholds': self._extract_assay_thresholds(text),
            'dose_exposure_rationale': self._extract_dose_rationale(text, pocket_context),
            'site_geography': self._extract_site_geography(text),
            'design_risks': self._extract_design_risks(text, pocket_context),
            'intervention': self._extract_intervention_details(text, pocket_context)
        }
    
    def _determine_design_archetype(self, text: str) -> str:
        """Determine design archetype based on extracted information."""
        gehan_result = self._extract_gehan_two_stage(text)
        if gehan_result:
            return 'single_arm_phase2_gehan'
        return 'not_reported'
    
    def _validate_methodology(self, method_info: Dict[str, Any], design_json: Dict[str, Any]) -> List[str]:
        """Validate methodology and return warnings."""
        warnings = []
        
        # Validate primary endpoint consistency
        if 'primary_endpoint' in design_json and method_info.get('primary_endpoint') != 'not_reported':
            trial_endpoint = design_json.get('primary_endpoint')
            if trial_endpoint and trial_endpoint != method_info['primary_endpoint']:
                warning_msg = f"Primary endpoint mismatch: paper='{method_info['primary_endpoint']}' vs trial_context='{trial_endpoint}'. Paper spans override trial context."
                warnings.append(warning_msg)
                self.logger.warning(warning_msg)
        
        # Validate Gehan design must-fill rule
        if method_info.get('gehan_two_stage'):
            if method_info.get('interim', {}).get('looks') != 1:
                error_msg = f"CRITICAL: Gehan design detected but interim_looks != 1. Got: {method_info.get('interim', {}).get('looks')}"
                warnings.append(error_msg)
                self.logger.error(error_msg)
        
        return warnings

    def _extract_estimand(self, text: str, design_json: Dict[str, Any]) -> Dict[str, Any]:
        """Extract estimand information from text."""
        estimand = {
            'population': 'unknown',
            'endpoint': 'unknown',
            'intercurrent_policy': 'unknown',
            'summary_measure': 'unknown'
        }
        
        # Extract population
        for pattern in self.estimand_patterns['population']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # For patterns with capture groups, use the last group for the actual population
                if len(match.groups()) > 1:
                    estimand['population'] = match.group(2).strip()
                else:
                    estimand['population'] = match.group(1).strip()
                break
        
        # Extract endpoint
        for pattern in self.estimand_patterns['endpoint']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # For patterns with capture groups, use the last group for the actual endpoint text
                if len(match.groups()) == 3:
                    estimand['endpoint'] = match.group(3).strip()  # Use group(3) for the actual endpoint text
                elif len(match.groups()) == 2:
                    estimand['endpoint'] = match.group(2).strip()  # Use group(2) for the actual endpoint text
                else:
                    estimand['endpoint'] = match.group(1).strip()
                break
        
        # Extract intercurrent event policy
        for pattern in self.estimand_patterns['intercurrent']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                estimand['intercurrent_policy'] = match.group(1).strip()
                break
        
        # Extract summary measure from design_json if available
        if 'primary_endpoint' in design_json:
            endpoint_info = design_json['primary_endpoint']
            if isinstance(endpoint_info, dict) and 'summary_measure' in endpoint_info:
                estimand['summary_measure'] = endpoint_info['summary_measure']
        
        return estimand

    def _extract_alpha_structure(self, text: str) -> Dict[str, Any]:
        """Extract alpha structure information from text."""
        alpha_structure = {
            'sidedness': 'not_reported',
            'alpha_threshold': None,
            'multiplicity_plan': 'not_reported',
            'hierarchy': 'not_reported',
            'gatekeeping': False
        }
        
        # Check for one-sided vs two-sided
        for pattern in self.alpha_patterns['one_sided']:
            if re.search(pattern, text, re.IGNORECASE):
                alpha_structure['sidedness'] = 'one_sided'
                break
        
        for pattern in self.alpha_patterns['two_sided']:
            if re.search(pattern, text, re.IGNORECASE):
                alpha_structure['sidedness'] = 'two_sided'
                break
        
        # Check for multiplicity adjustments
        for pattern in self.alpha_patterns['multiplicity']:
            if re.search(pattern, text, re.IGNORECASE):
                alpha_structure['multiplicity_plan'] = 'adjusted'
                if 'gatekeeping' in pattern or 'hierarchical' in pattern:
                    alpha_structure['gatekeeping'] = True
                    alpha_structure['hierarchy'] = 'hierarchical'
                break
        
        return alpha_structure

    def _extract_interim_plan(self, text: str, spans: List[EvidenceSpan]) -> Dict[str, Any]:
        """Extract interim analysis plan from text."""
        interim = {
            'design': 'not_reported',
            'looks': None,
            'timing': None,
            'spending_function': None,
            'stop_rules': None,
            'ssr': False,
            'field_provenance': {}  # Track which spans support each field
        }
        
        # Check for two-stage designs first
        for design, patterns in self.interim_design_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    interim['design'] = design
                    # Two-stage designs typically have 1 look after stage 1
                    interim['looks'] = 1
                    # Track provenance for design and looks
                    supporting_spans = self._find_supporting_spans(spans, pattern)
                    interim['field_provenance']['design'] = supporting_spans
                    interim['field_provenance']['looks'] = supporting_spans
                    break
            if interim['design'] != 'not_reported':
                break
        
        # Extract number of looks (only if not already set by design)
        if interim['looks'] is None:
            for pattern in self.interim_patterns['looks']:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    if r'(\d+)%\s+and\s+(\d+)%' in pattern:
                        # Special case for "50% and 75% of events"
                        interim['looks'] = 2
                    else:
                        interim['looks'] = int(match.group(1))
                    # Track provenance for looks
                    supporting_spans = self._find_supporting_spans(spans, pattern)
                    interim['field_provenance']['looks'] = supporting_spans
                    break
        
        # Extract timing
        for pattern in self.interim_patterns['timing']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                interim['timing'] = f"{match.group(1)} {match.group(2)}"
                # Track provenance for timing
                supporting_spans = self._find_supporting_spans(spans, pattern)
                interim['field_provenance']['timing'] = supporting_spans
                break
        
        # Extract spending function
        for pattern in self.interim_patterns['spending']:
            if re.search(pattern, text, re.IGNORECASE):
                if 'obrien' in pattern.lower():
                    interim['spending_function'] = 'O\'Brien-Fleming'
                elif 'pocock' in pattern.lower():
                    interim['spending_function'] = 'Pocock'
                elif 'lan' in pattern.lower():
                    interim['spending_function'] = 'Lan-DeMets'
                else:
                    interim['spending_function'] = 'specified'
                # Track provenance for spending function
                supporting_spans = self._find_supporting_spans(spans, pattern)
                interim['field_provenance']['spending_function'] = supporting_spans
                break
        
        # Check for sample size re-estimation
        ssr_pattern = r'sample\s+size\s+re.?estimation|SSR|sample\s+size\s+adjustment'
        if re.search(ssr_pattern, text, re.IGNORECASE):
            interim['ssr'] = True
            # Track provenance for SSR
            supporting_spans = self._find_supporting_spans(spans, ssr_pattern)
            interim['field_provenance']['ssr'] = supporting_spans
        
        return interim

    def _extract_gehan_two_stage(self, text: str) -> Optional[bool]:
        """Extract whether the study uses a Gehan two-stage design."""
        # Look for explicit mentions of Gehan two-stage design
        gehan_patterns = [
            r'gehan\s*\'?s?\s*two.?stage',  # "Gehan's two-stage", "Gehan two-stage"
            r'gehan\s+two.?stage|gehan\s+two\s+stage',
            r'gehan\s+design|gehan\s+method',
            r'two.?stage\s+phase\s*2.*gehan|two\s+stage\s+phase\s*II.*gehan',
            r'gehan\s*\'?s?\s*design',  # "Gehan's design"
            r'gehan\s*\'?s?\s*method'   # "Gehan's method"
        ]
        
        for pattern in gehan_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                self.logger.debug(f"Gehan pattern matched: '{pattern}' in text: '{text[:100]}...'")
                return True
        
        # Return None if not found (not False as default)
        return None

    def _extract_survival_method(self, text: str) -> str:
        """Extract survival method using explicit spans (KM vs inferred_KM)."""
        # Check for explicit KM mentions (since we have a direct KM span)
        km_patterns = [
            r'kaplan.?meier',
            r'km\s+method',
            r'estimated\s+by\s+kaplan',
            r'kaplan.?meier\s+method'
        ]
        
        for pattern in km_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return 'km'
        
        # Check for log-rank/Cox (inferred KM when only log-rank is present)
        logrank_patterns = [
            r'log.?rank',
            r'cox\s+regression',
            r'cox\s+proportional'
        ]
        
        for pattern in logrank_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return 'inferred_km'
        
        return 'not_reported'

    def _extract_analysis_sets(self, text: str, design_json: Dict[str, Any]) -> Dict[str, Any]:
        """Extract analysis set information from text."""
        analysis_sets = {
            'ITT': None,
            'mITT': None,
            'PP': None,
            'safety': None,
            'efficacy': None,
            'stratification_factors': []
        }
        
        # Check for analysis set mentions
        for set_name, pattern in self.analysis_set_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                analysis_sets[set_name] = True
        
        # Extract stratification factors
        stratification_patterns = [
            r'stratified\s+by\s+([^.]*)',
            r'stratification\s+by\s+([^.]*)',
            r'stratification\s+factors?\s+([^.]*)',
            r'blocked\s+by\s+([^.]*)'
        ]
        
        for pattern in stratification_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                factors_text = match.group(1)
                # Split on both commas and "and"
                factors = []
                for factor in factors_text.split(','):
                    factors.extend([f.strip() for f in factor.split(' and ')])
                analysis_sets['stratification_factors'] = [f for f in factors if f]
                break
        
        return analysis_sets

    def _extract_missingness_policies(self, text: str) -> Dict[str, Any]:
        """Extract missingness policies from text."""
        missingness = {
            'assumption': 'not_reported',
            'imputation_method': 'not_reported',
            'tipping_point': None,  # Only set if explicitly found
            'sensitivity_analysis': None  # Only set if explicitly found
        }
        
        # Only extract missingness assumptions if explicitly stated
        # Look for explicit statements about missingness assumptions
        explicit_mar_patterns = [
            r'assumed\s+MAR|assumption\s+of\s+MAR|missing\s+at\s+random\s+assumption',
            r'data\s+missing\s+at\s+random|MAR\s+assumption',
            r'under\s+MAR\s+assumption|assuming\s+MAR'
        ]
        
        explicit_mnar_patterns = [
            r'assumed\s+MNAR|assumption\s+of\s+MNAR|missing\s+not\s+at\s+random\s+assumption',
            r'data\s+missing\s+not\s+at\s+random|MNAR\s+assumption',
            r'under\s+MNAR\s+assumption|assuming\s+MNAR'
        ]
        
        # Check for explicit MAR assumption
        for pattern in explicit_mar_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                missingness['assumption'] = 'MAR'
                break
        
        # Check for explicit MNAR assumption
        for pattern in explicit_mnar_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                missingness['assumption'] = 'MNAR'
                break
        
        # Check for imputation methods (these are more commonly reported)
        imputation_patterns = [
            r'multiple\s+imputation|MI|imputation|imputed',
            r'last\s+observation\s+carried\s+forward|LOCF',
            r'worst.?case|best.?case|baseline\s+carried\s+forward'
        ]
        
        for pattern in imputation_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                missingness['imputation_method'] = 'imputation'
                break
        
        # Check for tipping point analysis
        if re.search(r'tipping\s+point|tipping.?point', text, re.IGNORECASE):
            missingness['tipping_point'] = True
        
        # Check for sensitivity analysis
        if re.search(r'sensitivity\s+analysis|sensitivity', text, re.IGNORECASE):
            missingness['sensitivity_analysis'] = True
        
        return missingness

    def _extract_endpoint_ascertainment(self, text: str) -> Dict[str, Any]:
        """Extract endpoint ascertainment information from text."""
        ascertainment = {
            'criteria': 'not_reported',
            'method': 'not_reported',
            'adjudication': 'not_reported',
            'assessment_interval': 'not_reported',
            'blinded': False
        }
        
        # Check for RECIST criteria
        for pattern in self.endpoint_ascertainment_patterns['RECIST']:
            if re.search(pattern, text, re.IGNORECASE):
                ascertainment['criteria'] = 'RECIST'
                break
        
        # Check for assessment interval using comprehensive patterns
        text_lower = text.lower()
        
        # First check the original endpoint ascertainment patterns
        for pattern in self.endpoint_ascertainment_patterns['assessment_interval']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if 'every (two|2) cycles' in pattern:
                    ascertainment['assessment_interval'] = 'every_2_cycles'
                elif 'every cycle' in pattern:
                    ascertainment['assessment_interval'] = 'every_cycle'
                elif 'weeks' in pattern:
                    ascertainment['assessment_interval'] = 'fixed_weeks'
                break
        
        # If not found, check the more comprehensive assessment interval patterns
        if ascertainment['assessment_interval'] == 'not_reported':
            for interval_type, patterns in self.assessment_interval_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, text_lower):
                        # Return standardized format
                        if interval_type == 'every_6_weeks':
                            ascertainment['assessment_interval'] = 'q6w'  # Standard abbreviation
                        elif interval_type == 'weekly':
                            ascertainment['assessment_interval'] = 'q1w'
                        elif interval_type == 'biweekly':
                            ascertainment['assessment_interval'] = 'q2w'
                        elif interval_type == 'monthly':
                            ascertainment['assessment_interval'] = 'q1m'
                        elif interval_type == 'every_3_months':
                            ascertainment['assessment_interval'] = 'q3m'
                        else:
                            ascertainment['assessment_interval'] = interval_type
                        break
                if ascertainment['assessment_interval'] != 'not_reported':
                    break
        
        # Check for CEC vs local assessment
        for method, patterns in self.ascertainment_patterns.items():
            if method in ['CEC', 'local']:  # Check methods first
                for pattern in patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        ascertainment['method'] = method
                        break
        
        # Check for blinding
        for pattern in self.ascertainment_patterns['blinded']:
            if re.search(pattern, text, re.IGNORECASE):
                ascertainment['blinded'] = True
                break
        
        # Determine adjudication status
        if ascertainment['method'] == 'CEC':
            ascertainment['adjudication'] = 'central'
        elif ascertainment['method'] == 'local':
            ascertainment['adjudication'] = 'local'
        
        return ascertainment

    def _extract_protocol_features(self, text: str) -> Dict[str, Any]:
        """Extract protocol features from text."""
        features = {
            'run_in': False,
            'enrichment': False,
            'crossover': False,
            'rescue': False,
            'washout': False
        }
        
        # Check for various protocol features
        if re.search(r'run.?in|runin', text, re.IGNORECASE):
            features['run_in'] = True
        
        if re.search(r'enrichment|enriched', text, re.IGNORECASE):
            features['enrichment'] = True
        
        if re.search(r'crossover|cross.?over', text, re.IGNORECASE):
            features['crossover'] = True
        
        if re.search(r'rescue|rescue\s+therapy', text, re.IGNORECASE):
            features['rescue'] = True
        
        if re.search(r'washout|wash.?out', text, re.IGNORECASE):
            features['washout'] = True
        
        return features

    def _extract_assay_thresholds(self, text: str) -> List[Dict[str, Any]]:
        """Extract assay thresholds from text."""
        thresholds = []
        
        # Look for common assay threshold patterns
        threshold_patterns = [
            r'(\w+)\s+(cutoff|threshold|limit)\s*[=:]\s*([0-9.]+)\s*(\w+)',
            r'(\w+)\s*[=:]\s*([0-9.]+)\s*(\w+)\s+(cutoff|threshold|limit)',
            r'minimum\s+(\w+)\s*[=:]\s*([0-9.]+)\s*(\w+)',
            r'(\w+)\s+(cutoff|threshold|limit)\s+was\s+set\s+at\s+([0-9.]+)\s*(\w+)',
            r'(\w+)\s+(cutoff|threshold|limit)\s+at\s+([0-9.]+)\s*(\w+)'
        ]
        
        for pattern in threshold_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                # Handle different pattern formats
                if r'was\s+set\s+at' in pattern:
                    # Pattern: (\w+)\s+(cutoff|threshold|limit)\s+was\s+set\s+at\s+([0-9.]+)\s*(\w+)
                    threshold = {
                        'assay_type': match.group(1),
                        'value': float(match.group(3)),  # Value is in group(3)
                        'units': match.group(4),         # Units are in group(4)
                        'threshold_type': match.group(2) # Type is in group(2)
                    }
                elif r'at\s+' in pattern and r'at\s+' not in r'(\w+)\s+(cutoff|threshold|limit)\s+at\s+([0-9.]+)\s*(\w+)':
                    # Pattern: (\w+)\s+(cutoff|threshold|limit)\s+at\s+([0-9.]+)\s*(\w+)
                    threshold = {
                        'assay_type': match.group(1),
                        'value': float(match.group(3)),  # Value is in group(3)
                        'units': match.group(4),         # Units are in group(4)
                        'threshold_type': match.group(2) # Type is in group(2)
                    }
                else:
                    # Standard patterns: (\w+)\s+(cutoff|threshold|limit)\s*[=:]\s*([0-9.]+)\s*(\w+)
                    threshold = {
                        'assay_type': match.group(1),
                        'value': float(match.group(3)),  # Value is in group(3)
                        'units': match.group(4),         # Units are in group(4)
                        'threshold_type': match.group(2) # Type is in group(2)
                    }
                thresholds.append(threshold)
        
        return thresholds

    def _extract_dose_rationale(self, text: str, pocket_context: PocketContextCard) -> str:
        """Extract dose-exposure rationale from text."""
        rationale_patterns = [
            r'dose\s+selection\s+([^.]*)',
            r'dose\s+rationale\s+([^.]*)',
            r'dose\s+escalation\s+([^.]*)',
            r'target\s+engagement\s+([^.]*)'
        ]
        
        for pattern in rationale_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Fall back to pocket context if available
        if pocket_context.intervention_class:
            return f"Based on {pocket_context.intervention_class} class considerations"
        
        return "unknown"

    def _extract_site_geography(self, text: str) -> Dict[str, Any]:
        """Extract site geography information from text."""
        geography = {
            'num_sites': 'not_reported',
            'regions': [],
            'dispersion': 'not_reported'
        }
        
        # Only extract from methods/protocol sections, not from affiliations
        # Look for explicit statements about study conduct locations
        
        # Extract number of sites from study design statements
        site_patterns = [
            r'(\d+)\s+(sites?|centers?|locations?)\s+(?:participated|involved|conducted)',
            r'study\s+conducted\s+at\s+(\d+)\s+(sites?|centers?|locations?)',
            r'(\d+)\s+(sites?|centers?|locations?)\s+(?:enrolled|recruited)',
            r'multicenter\s+study\s+with\s+(\d+)\s+(sites?|centers?|locations?)'
        ]
        
        for pattern in site_patterns:
            site_match = re.search(pattern, text, re.IGNORECASE)
            if site_match:
                geography['num_sites'] = int(site_match.group(1))
                break
        
        # Check for single-center mentions in study design context
        single_center_patterns = [
            r'single.?center\s+study',
            r'study\s+conducted\s+at\s+one\s+center',
            r'university\s+medical\s+center\s+study',
            r'single\s+institution\s+study'
        ]
        
        for pattern in single_center_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                geography['num_sites'] = 1
                break
        
        # Extract regions only from study conduct statements, not affiliations
        region_patterns = [
            r'study\s+conducted\s+in\s+([^.]*)',
            r'participating\s+sites\s+in\s+([^.]*)',
            r'study\s+sites\s+located\s+in\s+([^.]*)',
            r'centers\s+in\s+([^.]*)'
        ]
        
        for pattern in region_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                region_text = match.group(1).lower()
                # Extract specific regions from the matched text
                specific_regions = re.findall(r'(north\s+america|europe|asia|africa|south\s+america|australia|united\s+states|us|usa|canada|mexico|germany|france|uk|spain|italy|japan|china|india|netherlands)', region_text)
                for region in specific_regions:
                    if region not in geography['regions']:
                        geography['regions'].append(region)
        
        # Determine dispersion only if we have a valid number of sites
        if geography['num_sites'] != 'not_reported' and isinstance(geography['num_sites'], int):
            if geography['num_sites'] > 50:
                geography['dispersion'] = 'high'
            elif geography['num_sites'] > 20:
                geography['dispersion'] = 'medium'
            else:
                geography['dispersion'] = 'low'
        
        return geography

    def _extract_design_risks(self, text: str, pocket_context: PocketContextCard) -> List[str]:
        """Extract design risks from text."""
        risks = []
        
        # Common design risk patterns
        risk_keywords = {
            'small_sample_size': [r'small\s+sample', r'limited\s+power', r'underpowered', r'sample\s+size\s+was\s+limited'],
            'short_followup': [r'short\s+follow.?up', r'limited\s+follow.?up', r'brief\s+observation'],
            'heterogeneous_population': [r'heterogeneous', r'diverse\s+population', r'mixed\s+population'],
            'missing_data': [r'high\s+missingness', r'substantial\s+missing', r'missing\s+data'],
            'selection_bias': [r'selection\s+bias', r'recruitment\s+bias', r'enrollment\s+bias'],
            'performance_bias': [r'performance\s+bias', r'treatment\s+bias', r'intervention\s+bias'],
            'detection_bias': [r'detection\s+bias', r'measurement\s+bias', r'assessment\s+bias'],
            'attrition_bias': [r'attrition\s+bias', r'dropout\s+bias', r'loss\s+to\s+follow.?up'],
            # Add specific risks for single-arm early-phase studies
            'single_arm_phase2': [r'single.?arm|single\s+arm', r'phase\s*2|phase\s*II'],
            'open_label': [r'open.?label|open\s+label', r'blinding\s+(was\s+)?not\s+performed'],
            'single_center': [r'single.?center|single\s+center', r'one\s+center', r'university\s+medical\s+center'],
            'two_stage_selection': [r'two.?stage|two\s+stage', r'gehan|simon']
        }
        
        for risk, patterns in risk_keywords.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    risks.append(risk)
                    break
        
        return risks

    def _extract_study_phase(self, text: str) -> str:
        """Extract study phase from text."""
        # First, try to normalize any phase text found in the text
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

    def _extract_blinding_level(self, text: str) -> str:
        """Extract blinding level from text."""
        for level, patterns in self.blinding_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return level
        return 'not_reported'

    def _extract_primary_endpoint(self, text: str) -> str:
        """Extract primary endpoint from text."""
        # Look for RECIST-related endpoints
        if re.search(r'RECIST|response\s+evaluation\s+criteria', text, re.IGNORECASE):
            return 'ORR_RECIST'
        
        # Look for other common primary endpoints
        endpoint_patterns = [
            r'primary\s+(endpoint|outcome|objective)\s+([^.]*)',
            r'primary\s+([^.]*endpoint[^.]*)'
        ]
        
        for pattern in endpoint_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                endpoint_text = match.group(2) if len(match.groups()) > 1 else match.group(1)
                if 'response' in endpoint_text.lower():
                    return 'ORR_RECIST'
                elif 'survival' in endpoint_text.lower():
                    return 'OS'
                elif 'progression' in endpoint_text.lower():
                    return 'PFS'
        
        return 'not_reported'

    def _extract_secondary_endpoints(self, text: str) -> List[str]:
        """Extract secondary endpoints from text."""
        endpoints = []
        
        # Look for TTP/PFS
        if re.search(r'ttp|time\s+to\s+progression|progression.?free\s+survival|pfs', text, re.IGNORECASE):
            endpoints.append('TTP_or_PFS')
        
        # Look for OS
        if re.search(r'overall\s+survival|os', text, re.IGNORECASE):
            endpoints.append('OS')
        
        return endpoints

    def _extract_statistics_methods(self, text: str) -> List[str]:
        """Extract statistics methods from text."""
        methods = []
        
        for pattern in self.stats_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if 'kaplan' in pattern:
                    methods.append('Kaplan-Meier')
                elif 'log' in pattern:
                    methods.append('Log-rank')
                elif 'cox' in pattern:
                    methods.append('Cox proportional hazards')
        
        return methods

    def _extract_analysis_denominators(self, text: str) -> Dict[str, int]:
        """Extract analysis denominators from text."""
        denominators = {}
        
        # Extract response denominator
        for pattern in self.analysis_denominators_patterns['response_n']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                denominators['response_n'] = int(match.group(1))
                break
        
        # Extract TTP/OS denominator
        for pattern in self.analysis_denominators_patterns['ttp_os_n']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                denominators['ttp_os_n'] = int(match.group(1))
                break
        
        return denominators

    def _extract_intervention_details(self, text: str, pocket_context: PocketContextCard) -> Dict[str, Any]:
        """Extract intervention details from text."""
        intervention = {}
        
        # Look for PLD dosing
        pld_match = re.search(r'PLD|pegylated\s+liposomal\s+doxorubicin.*?(\d+)\s*mg/m²', text, re.IGNORECASE)
        if pld_match:
            intervention['pld_dose'] = f"{pld_match.group(1)} mg/m²"
        
        # Look for atrasentan dosing
        atrasentan_match = re.search(r'atrasentan.*?(\d+(?:\.\d+)?)\s*→\s*(\d+(?:\.\d+)?)\s*→\s*(\d+(?:\.\d+)?)\s*mg', text, re.IGNORECASE)
        if atrasentan_match:
            intervention['atrasentan_escalation'] = f"{atrasentan_match.group(1)}→{atrasentan_match.group(2)}→{atrasentan_match.group(3)} mg"
        
        return intervention
    


    def _create_method_card(self, method_info: Dict[str, Any], spans: List[EvidenceSpan]) -> MethodCard:
        """Create a MethodCard from extracted methodological information."""
        # Collect all span IDs for provenance
        span_ids = [span.span_id for span in spans]
        
        # Get doc_id from spans
        doc_id = None
        if spans:
            doc_id = spans[0].doc_id
        
        if not doc_id:
            raise ValueError("Cannot create MethodCard without a valid doc_id from spans")
        
        # Create the MethodCard with only explicitly extracted values (no defaults)
        method_card = MethodCard(
            doc_id=doc_id,
            estimand=method_info['estimand'],  # Store as real object, not JSON string
            alpha_structure=method_info['alpha_structure'],  # Store as real object, not JSON string
            interim_looks=method_info['interim'].get('looks'),
            interim_timing=method_info['interim'].get('timing'),
            spending_function=method_info['interim'].get('spending_function'),
            # Only set if explicitly extracted (not default False)
            sample_size_reassessment=method_info['interim'].get('ssr') if 'ssr' in method_info['interim'] else None,
            gehan_two_stage=method_info.get('gehan_two_stage') if 'gehan_two_stage' in method_info else None,
            design_archetype=method_info.get('design_archetype'),
            analysis_set=method_info['analysis_set'],  # Store as real object, not JSON string
            stratification_factors=method_info['analysis_set'].get('stratification_factors', []),
            missingness_assumption=method_info['missingness'].get('assumption'),
            imputation_method=method_info['missingness'].get('imputation_method'),
            # Only set if explicitly extracted (not default False)
            tipping_point_analysis=method_info['missingness'].get('tipping_point') if 'tipping_point' in method_info['missingness'] else None,
            endpoint_ascertainment=method_info['endpoint_ascertainment'].get('criteria'),
            assessment_interval=method_info['endpoint_ascertainment'].get('assessment_interval'),
            # Only set if explicitly extracted (not default False)
            is_blinded=method_info['endpoint_ascertainment'].get('blinded') if 'blinded' in method_info['endpoint_ascertainment'] else None,
            protocol_features=method_info['protocol_features'],
            assay_thresholds=method_info['assay_thresholds'],
            dose_exposure_rationale=method_info['dose_exposure_rationale'],
            site_geography=method_info['site_geography'],
            design_risks=method_info['design_risks'],
            # Add new fields
            study_phase=method_info.get('study_phase'),
            blinding_level=method_info.get('blinding_level'),
            primary_endpoint=method_info.get('primary_endpoint'),
            secondary_endpoints=method_info.get('secondary_endpoints', []),
            regions=method_info.get('site_geography', {}).get('regions', []),
            number_of_sites=method_info.get('site_geography', {}).get('num_sites'),
            warnings=method_info.get('warnings', [])
        )
        
        # Standardize provenance: use span_ids for machine checks, provenance_anchors as UI alias
        method_card.span_ids = span_ids
        method_card.provenance_anchors = span_ids  # Keep for backward compatibility
        
        # Add per-field provenance tracking
        if 'interim' in method_info and 'field_provenance' in method_info['interim']:
            for field_name, field_span_ids in method_info['interim']['field_provenance'].items():
                if field_span_ids:  # Only add if there are supporting spans
                    method_card.add_field_provenance(f'interim_{field_name}', field_span_ids)
        
        return method_card
