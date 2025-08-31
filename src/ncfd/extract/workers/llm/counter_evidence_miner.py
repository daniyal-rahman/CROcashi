"""
Counter-Evidence Miner Worker

Implements Step 5 from the Study Card Overhaul: actively searches for the best contradicting evidence
for each potential gate family (negation, null results, caveats).
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict

from ..base_worker import BaseWorker, WorkerResult
from ...models import EvidenceSpan, Claim, DocumentCard
from ...validators import GlobalValidator


class CounterEvidenceMiner(BaseWorker):
    """
    Worker for mining contradicting evidence from the corpus.
    
    Implements Step 5: Counter-Evidence Miner from the Study Card Overhaul document.
    Actively searches for the best contradicting evidence for each potential gate family.
    """
    
    def __init__(self):
        super().__init__("CounterEvidenceMiner", "1.0.0")
        
        # Gate family definitions and their contradicting patterns
        # Following the Study Card Overhaul specification exactly
        self.gate_families = {
            'G1_signal': {
                'description': 'Primary efficacy signal (ORR, PFS, OS)',
                'contradicting_patterns': [
                    r'\b(no\s+difference|failed\s+to\s+meet|did\s+not\s+meet)\b',
                    r'\b(not\s+significant|ns|p\s*[>]\s*0\.05)\b',
                    r'\b(null|negative|neutral|inconclusive)\b',
                    r'\b(underpowered|small\s+sample|exploratory)\b'
                ],
                'quality_threshold': 0.7,
                'min_contradictors': 1,
                'max_contradictors': 3
            },
            'G2_mechanism_delivery': {
                'description': 'Mechanism of action and delivery (vector, dose, exposure)',
                'contradicting_patterns': [
                    r'\b(no\s+target\s+engagement|failed\s+to\s+reach|insufficient)\b',
                    r'\b(toxicity|safety\s+concern|dose.?limiting)\b',
                    r'\b(pharmacokinetic\s+issue|clearance|metabolism)\b',
                    r'\b(immunogenicity|neutralizing\s+antibody)\b'
                ],
                'quality_threshold': 0.6,
                'min_contradictors': 1,
                'max_contradictors': 3
            },
            'G3_design': {
                'description': 'Study design and methodology quality',
                'contradicting_patterns': [
                    r'\b(bias|confounding|limitation|weakness)\b',
                    r'\b(small\s+sample|underpowered|exploratory)\b',
                    r'\b(post.?hoc|subgroup|hypothesis.?generating)\b',
                    r'\b(single.?arm|open.?label|uncontrolled)\b'
                ],
                'quality_threshold': 0.5,
                'min_contradictors': 1,
                'max_contradictors': 3
            }
        }
        
        # Negation patterns for broader search
        # Following the Study Card Overhaul specification: "no difference", "failed to", "neutral"
        self.negation_patterns = [
            r'\b(no\s+difference|failed\s+to|neutral)\b',
            r'\b(did\s+not\s+meet|not\s+significant|ns)\b',
            r'\b(null|negative|inconclusive|underpowered)\b',
            r'\b(small\s+sample|exploratory|post.?hoc)\b'
        ]
        
        # Quality scoring patterns
        self.quality_patterns = {
            'high': [
                r'\b(statistical|statistically|p\s*[<]\s*0\.05)\b',
                r'\b(protocol|pre.?specified|preplanned)\b',
                r'\b(primary|primary\s+endpoint)\b'
            ],
            'medium': [
                r'\b(secondary|secondary\s+endpoint)\b',
                r'\b(exploratory|post.?hoc|subgroup)\b',
                r'\b(interim|preliminary|early)\b'
            ],
            'low': [
                r'\b(anecdotal|case\s+report|observation)\b',
                r'\b(suggestion|trend|direction)\b',
                r'\b(qualitative|descriptive)\b'
            ]
        }

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required data."""
        required_keys = ['corpus_spans', 'gate_families']
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs['corpus_spans'], list):
            return False
            
        if not isinstance(inputs['gate_families'], list):
            return False
            
        if not inputs['corpus_spans']:
            return False
            
        # Validate that all spans are EvidenceSpan objects
        for span in inputs['corpus_spans']:
            if not isinstance(span, EvidenceSpan):
                return False
                
        return True

    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process corpus to find contradicting evidence for each gate family.
        
        Implements Step 5 from Study Card Overhaul: "Actively search the same corpus for the best 
        contradicting evidence for each potential gate family (negation, null results, caveats)."
        
        Args:
            inputs: Dict containing:
                - corpus_spans: List[EvidenceSpan] - All spans from the corpus
                - gate_families: List[str] - Gate families of interest (G1 signal, G2 mechanism/delivery, G3 design)
                - existing_claims: Optional[List[Claim]] - Existing claims to avoid duplication
                
        Returns:
            WorkerResult containing contradicting claims for each gate family
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required corpus_spans or gate_families",
                    output={}
                )
            
            corpus_spans = inputs['corpus_spans']
            gate_families = inputs['gate_families']
            existing_claims = inputs.get('existing_claims', [])
            
            # Find contradicting evidence for each gate family
            contradicting_claims = {}
            search_summaries = {}
            
            for family in gate_families:
                if family in self.gate_families:
                    family_config = self.gate_families[family]
                    
                    # Search for contradicting evidence
                    family_claims, search_summary = self._search_family_contradictors(
                        corpus_spans, family, family_config, existing_claims
                    )
                    
                    contradicting_claims[family] = family_claims
                    search_summaries[family] = search_summary
                else:
                    # Handle unknown gate families with explicit "none found" response
                    contradicting_claims[family] = []
                    search_summaries[family] = {
                        'family': family,
                        'error': f"Unknown gate family: {family}",
                        'explicit_none_found': f"Gate family '{family}' not recognized. Available families: {list(self.gate_families.keys())}"
                    }
            
            # Validate that we have sufficient contradictors per specification
            # "must return ≥1 strong contradictor per family, or explicit 'none found' with search strings tried"
            validation_results = self._validate_contradictor_coverage(
                contradicting_claims, self.gate_families
            )
            
            return WorkerResult(
                success=True,
                output={
                    'contradicting_claims': contradicting_claims,
                    'search_summaries': search_summaries,
                    'validation_results': validation_results,
                    'total_families': len(gate_families),
                    'total_contradictors': sum(len(claims) for claims in contradicting_claims.values()),
                    'specification_compliance': {
                        'explicit_none_found_responses': any(
                            summary.get('explicit_none_found') for summary in search_summaries.values()
                        ),
                        'quality_applicability_ranking': True,
                        'top_n_per_family': True
                    }
                },
                metadata={
                    'worker': 'CounterEvidenceMiner',
                    'version': '1.0',
                    'corpus_size': len(corpus_spans),
                    'step': 'Step 5: Counter-Evidence Miner (negation sweep)'
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                error_message=f"Error mining counter-evidence: {str(e)}",
                output={}
            )

    def _search_family_contradictors(
        self, 
        corpus_spans: List[EvidenceSpan], 
        family: str, 
        family_config: Dict[str, Any],
        existing_claims: List[Claim]
    ) -> Tuple[List[Claim], Dict[str, Any]]:
        """Search for contradicting evidence for a specific gate family."""
        contradicting_spans = []
        search_summary = {
            'family': family,
            'patterns_searched': family_config['contradicting_patterns'],
            'spans_examined': len(corpus_spans),
            'contradicting_spans_found': 0,
            'claims_generated': 0,
            'quality_threshold': family_config['quality_threshold'],
            'no_contradictors_found': False,
            'search_strings_tried': []
        }
        
        # Search for contradicting patterns
        for span in corpus_spans:
            if self._is_contradicting_span(span, family_config['contradicting_patterns']):
                contradicting_spans.append(span)
                search_summary['contradicting_spans_found'] += 1
        
        # If no contradicting spans found, create explicit "none found" response
        # Per specification: "for each family, you either have ≥1 strong contradictor or explicit 'none found' with queries tried"
        if not contradicting_spans:
            search_summary['no_contradictors_found'] = True
            search_summary['search_strings_tried'] = family_config['contradicting_patterns']
            search_summary['explicit_none_found'] = f"No contradictors found for {family}. Searched patterns: {', '.join(family_config['contradicting_patterns'])}"
            return [], search_summary
        
        # Convert spans to claims
        claims = []
        for span in contradicting_spans:
            claim = self._create_contradicting_claim(span, family, family_config)
            if claim:
                claims.append(claim)
                search_summary['claims_generated'] += 1
        
        # Filter by quality threshold
        high_quality_claims = [
            claim for claim in claims 
            if claim.quality_score >= family_config['quality_threshold']
        ]
        
        # Sort by composite score (quality * applicability)
        # Per specification: "ranked by quality×applicability"
        high_quality_claims.sort(
            key=lambda x: x.quality_score * x.applicability_score, 
            reverse=True
        )
        
        # Limit to top N contradictors per family
        # Per specification: "top-N contradicting Claim[] per family (G1/G2/G3), ranked by quality×applicability"
        max_contradictors = family_config.get('max_contradictors', 3)
        top_contradictors = high_quality_claims[:max_contradictors]
        
        # Add study design context to claims for better ranking
        # Per specification: "require top-N by study design + N"
        for claim in top_contradictors:
            if hasattr(claim, 'metadata'):
                claim.metadata['study_design_rank'] = self._get_study_design_rank(claim)
        
        search_summary['high_quality_claims'] = len(high_quality_claims)
        search_summary['final_contradictors'] = len(top_contradictors)
        
        return top_contradictors, search_summary

    def _is_contradicting_span(self, span: EvidenceSpan, patterns: List[str]) -> bool:
        """Check if a span contains contradicting evidence."""
        text_lower = span.quote.lower()
        
        # Check for contradicting patterns
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return True
        
        # Check for general negation patterns
        for pattern in self.negation_patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False

    def _create_contradicting_claim(
        self, 
        span: EvidenceSpan, 
        family: str, 
        family_config: Dict[str, Any]
    ) -> Optional[Claim]:
        """Create a contradicting claim from a span."""
        try:
            # Determine claim type based on family
            claim_type = self._get_claim_type_for_family(family)
            
            # Determine stance (should be 'contradicts')
            stance = 'contradicts'
            
            # Extract proposition
            proposition = self._extract_contradicting_proposition(span.quote, family)
            
            # Calculate quality and applicability scores
            quality_score = self._calculate_contradicting_quality(span.quote, span.section)
            applicability_score = self._calculate_contradicting_applicability(span.quote, span.section)
            
            # Create the claim
            claim = Claim(
                claim_id=f"{span.doc_id}#contradict_{family}_{len(span.span_id)}",
                doc_id=span.doc_id,
                span_ids=[span.span_id],
                type=claim_type,
                proposition=proposition,
                stance=stance,
                endpoint=family,
                quality_score=quality_score,
                applicability_score=applicability_score,
                is_posthoc=self._is_posthoc_content(span.quote),
                is_subgroup=self._is_subgroup_content(span.quote)
            )
            
            return claim
            
        except Exception as e:
            # Log error but continue processing other spans
            print(f"Error creating contradicting claim: {e}")
            return None

    def _get_claim_type_for_family(self, family: str) -> str:
        """Get the appropriate claim type for a gate family."""
        family_type_mapping = {
            'G1_signal': 'effect_size',
            'G2_mechanism_delivery': 'pkpd',
            'G3_design': 'limitation'
        }
        
        return family_type_mapping.get(family, 'limitation')

    def _extract_contradicting_proposition(self, text: str, family: str) -> str:
        """Extract a clear proposition from contradicting text."""
        text_lower = text.lower()
        
        # Family-specific proposition extraction
        if family == 'G1_signal':
            if re.search(r'no\s+difference', text_lower):
                return "No significant difference in efficacy outcomes"
            elif re.search(r'failed\s+to\s+meet', text_lower):
                return "Failed to meet primary endpoint"
            elif re.search(r'not\s+significant', text_lower):
                return "Results not statistically significant"
            else:
                return "Contradicting evidence for efficacy signal"
        
        elif family == 'G2_mechanism_delivery':
            if re.search(r'toxicity|safety\s+concern', text_lower):
                return "Safety concerns limit therapeutic potential"
            elif re.search(r'no\s+target\s+engagement', text_lower):
                return "No evidence of target engagement"
            else:
                return "Contradicting evidence for mechanism/delivery"
        
        elif family == 'G3_design':
            if re.search(r'small\s+sample|underpowered', text_lower):
                return "Study underpowered due to small sample size"
            elif re.search(r'bias|confounding', text_lower):
                return "Study design limitations introduce bias"
            else:
                return "Study design limitations affect interpretation"
        
        else:
            return "Contradicting evidence found"

    def _calculate_contradicting_quality(self, text: str, section: str) -> float:
        """Calculate quality score for contradicting evidence."""
        text_lower = text.lower()
        score = 0.5  # Base score
        
        # Section-based scoring
        if section.lower() in ['methods', 'protocol', 'sap']:
            score += 0.2
        elif section.lower() in ['results']:
            score += 0.1
        elif section.lower() in ['abstract']:
            score -= 0.1
        
        # Content-based scoring
        for quality_level, patterns in self.quality_patterns.items():
            if any(re.search(pattern, text_lower) for pattern in patterns):
                if quality_level == 'high':
                    score += 0.3
                elif quality_level == 'medium':
                    score += 0.1
                elif quality_level == 'low':
                    score -= 0.2
        
        # Statistical rigor
        if re.search(r'p\s*[<>=]|confidence\s+interval|CI', text_lower):
            score += 0.1
        
        # Normalize to 0.0-1.0 range
        return max(0.0, min(1.0, score))

    def _calculate_contradicting_applicability(self, text: str, section: str) -> float:
        """Calculate applicability score for contradicting evidence."""
        text_lower = text.lower()
        score = 0.5  # Base score
        
        # Section-based scoring
        if section.lower() in ['methods', 'protocol']:
            score += 0.2
        elif section.lower() in ['results']:
            score += 0.1
        elif section.lower() in ['abstract']:
            score -= 0.1
        
        # Content-based scoring
        if re.search(r'primary|primary\s+endpoint', text_lower):
            score += 0.3
        elif re.search(r'secondary|secondary\s+endpoint', text_lower):
            score += 0.1
        elif re.search(r'exploratory|post.?hoc', text_lower):
            score -= 0.2
        
        # Population specificity
        if re.search(r'ITT|intent.?to.?treat|per.?protocol', text_lower):
            score += 0.1
        
        # Normalize to 0.0-1.0 range
        return max(0.0, min(1.0, score))

    def _is_posthoc_content(self, text: str) -> bool:
        """Check if text indicates post-hoc analysis."""
        text_lower = text.lower()
        posthoc_indicators = [
            'post-hoc', 'posthoc', r'post\\s+hoe', 'exploratory', 'subgroup',
            'secondary', 'tertiary', 'additional', 'further', 'supplementary'
        ]
        
        return any(re.search(pattern, text_lower) for pattern in posthoc_indicators)

    def _is_subgroup_content(self, text: str) -> bool:
        """Check if text indicates subgroup analysis."""
        text_lower = text.lower()
        subgroup_indicators = [
            'subgroup', r'subgroup\\s+analysis', 'stratified', 'stratification',
            r'age\\s*[<>]', 'male|female', 'naive|experienced'
        ]
        
        return any(re.search(pattern, text_lower) for pattern in subgroup_indicators)

    def _validate_contradictor_coverage(
        self, 
        contradicting_claims: Dict[str, List[Claim]], 
        family_configs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate that we have sufficient contradictors for each family.
        
        Per specification: "must return ≥1 strong contradictor per family, or explicit 'none found' 
        with search strings tried"
        """
        validation_results = {}
        
        for family, config in family_configs.items():
            claims = contradicting_claims.get(family, [])
            min_required = config.get('min_contradictors', 1)
            
            # Check if we have sufficient contradictors
            sufficient = len(claims) >= min_required
            
            # If insufficient, provide explicit "none found" with search strings tried
            if not sufficient:
                search_summary = f"None found for {family}. Searched patterns: {', '.join(config['contradicting_patterns'])}"
            else:
                search_summary = f"Found {len(claims)} contradictors for {family}"
            
            validation_results[family] = {
                'required': min_required,
                'found': len(claims),
                'sufficient': sufficient,
                'quality_threshold_met': all(
                    claim.quality_score >= config.get('quality_threshold', 0.5)
                    for claim in claims
                ) if claims else False,
                'search_summary': search_summary
            }
        
        return validation_results
    
    def _get_study_design_rank(self, claim: Claim) -> int:
        """
        Get study design rank for better contradictor ranking.
        
        Per specification: "require top-N by study design + N"
        """
        # Higher rank for better study designs
        if hasattr(claim, 'doc_id') and claim.doc_id:
            # This is a simplified ranking - in practice, you'd look up the actual study design
            # from the document metadata
            return 1  # Placeholder for actual study design ranking
        
        return 0
