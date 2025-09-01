"""
Claimizer Worker

Implements Step 4 from the Study Card Overhaul: converts spans into atomic, testable Claim objects
with proper normalization, deduplication, and quality scoring.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict

from ..base_worker import BaseWorker, WorkerResult
from ...models import EvidenceSpan, Claim
from ...validators import GlobalValidator


class Claimizer(BaseWorker):
    """
    Worker for converting evidence spans into atomic, testable Claim objects.
    
    Implements Step 4: Claimizer v0 from the Study Card Overhaul document.
    Converts spans into Claims with proper normalization, deduplication, and quality scoring.
    """
    
    def __init__(self):
        super().__init__("Claimizer", "1.0.0")
        
        # Claim type patterns for classification
        self.type_patterns = {
            'design_fact': [
                r'\b(blinding|randomization|stratification|allocation)\b',
                r'\b(single.?center|multi.?center|sites?)\b',
                r'\b(phase\s+\d+|stage\s+\d+)\b',
                r'\b(interim|look|stopping)\b',
                r'\b(gehan|two.?stage|adaptive)\b'
            ],
            'effect_size': [
                r'\b(median|mean|hazard\s+ratio|HR|odds\s+ratio|OR)\b',
                r'\b(response\s+rate|ORR|progression|survival)\b',
                r'\b(confidence\s+interval|CI|p.?value|p\s*[<>=])\b'
            ],
            'safety': [
                r'\b(grade\s*\d+\+?\s*AE)\b',  # "Grade 3+ AE"
                r'\b(grade\s*\d+\+?\s*adverse\s+event)\b',  # "Grade 3+ adverse event"
                r'\b(grade\s*\d+\+?\s*toxicity)\b',  # "Grade 3+ toxicity"
                r'\b(adverse\s+event|AE)\b',  # "adverse event", "AE"
                r'\b(toxicity|toxic)\b',  # "toxicity", "toxic"
                r'\b(safety|safety\s+profile)\b',  # "safety", "safety profile"
                r'\b(grade\s*\d+)\b',  # "grade 3", "grade 4"
            ],
            'prevalence': [
                r'\b(incidence|frequency|rate|percentage|%)\b',
                r'\b(discontinuation|withdrawal|completion)\b'
            ],
            'assay_cutoff': [
                r'\b(CA.?125|biomarker|cut.?off|threshold)\b',
                r'\b(assay|test|measurement|level)\b',
                r'\b(positive|negative|elevated|normal)\b'
            ],
            'pkpd': [
                r'\b(pharmacokinetic|PK|pharmacodynamic|PD)\b',
                r'\b(clearance|volume|half.?life|Cmax|AUC)\b',
                r'\b(dose.?response|exposure|concentration)\b'
            ],
            'operational': [
                r'\b(enrollment|recruitment|screening|eligibility)\b',
                r'\b(protocol|amendment|deviation|violation)\b',
                r'\b(monitoring|audit|quality|compliance)\b'
            ],
            'limitation': [
                r'\b(limitation|weakness|bias|confounding)\b',
                r'\b(small\s+sample|underpowered|exploratory)\b',
                r'\b(post.?hoc|subgroup|hypothesis.?generating)\b'
            ]
        }
        
        # Stance detection patterns
        self.stance_patterns = {
            'supports': [
                r'\b(significant|significant|p\s*[<]\s*0\.05|p\s*[<]\s*0\.01)\b',
                r'\b(improved|better|superior|efficacy|benefit)\b',
                r'\b(met|achieved|reached|demonstrated)\b'
            ],
            'contradicts': [
                r'\b(no\s+difference|failed|negative|null|neutral)\b',
                r'\b(not\s+significant|ns|p\s*[>]\s*0\.05)\b',
                r'\b(worse|inferior|harm|toxicity)\b'
            ],
            'neutral': [
                r'\b(trend|suggestive|promising|encouraging)\b',
                r'\b(exploratory|hypothesis|preliminary)\b',
                r'\b(well.?tolerated|acceptable|feasible)\b'
            ]
        }
        
        # Quality indicators
        self.quality_indicators = {
            'high': [
                r'\b(primary|primary\s+endpoint|primary\s+analysis)\b',
                r'\b(statistical|statistically|p\s*[<]\s*0\.05)\b',
                r'\b(protocol|pre.?specified|preplanned)\b'
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
        """Validate that inputs contain required evidence spans."""
        required_keys = ['evidence_spans']
        
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

    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process evidence spans to create atomic, testable Claim objects.
        
        Args:
            inputs: Dict containing:
                - evidence_spans: List[EvidenceSpan] - All spans to convert to claims
                
        Returns:
            WorkerResult containing Claim objects
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required evidence_spans",
                    output={}
                )
            
            evidence_spans = inputs['evidence_spans']
            
            # Convert spans to claims
            claims = []
            for span in evidence_spans:
                span_claims = self._extract_claims_from_span(span)
                claims.extend(span_claims)
            
            # Deduplicate and merge claims
            deduplicated_claims = self._deduplicate_claims(claims)
            
            # Normalize units and values
            normalized_claims = self._normalize_claims(deduplicated_claims)
            
            # Score quality and applicability
            scored_claims = self._score_claims(normalized_claims)
            
            # Add provenance information
            for claim in scored_claims:
                self._add_provenance(claim, inputs)
            
            # Global validation: hard fail on empty span_ids
            if not GlobalValidator.hard_fail_on_empty_provenance(scored_claims):
                return WorkerResult(
                    success=False,
                    error_message="CRITICAL PROVENANCE VIOLATION: Claims with empty span_ids violate the requirement 'Every numeric must be span-anchored'",
                    output={}
                )
            
            return WorkerResult(
                success=True,
                output={
                    'claims': scored_claims,
                    'processed_spans': len(evidence_spans),
                    'total_claims': len(claims),
                    'final_claims': len(scored_claims)
                },
                metadata={
                    'worker': 'Claimizer',
                    'version': '1.0',
                    'max_spans_processed': len(evidence_spans)
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                error_message=f"Error processing claims: {str(e)}",
                output={}
            )

    def _extract_claims_from_span(self, span: EvidenceSpan) -> List[Claim]:
        """Extract multiple claims from a single evidence span."""
        claims = []
        text = span.quote
        
        # Determine claim type based on content and section
        claim_type = self._classify_claim_type(text, span.section)
        
        # Determine stance based on content
        stance = self._classify_stance(text)
        
        # Extract numeric claims if present
        numeric_claims = self._extract_numeric_claims(text, span, claim_type, stance)
        claims.extend(numeric_claims)
        
        # Extract non-numeric claims
        non_numeric_claims = self._extract_non_numeric_claims(text, span, claim_type, stance)
        claims.extend(non_numeric_claims)
        
        return claims

    def _classify_claim_type(self, text: str, section: str) -> str:
        """Classify the type of claim based on content and section with safety priority."""
        text_lower = text.lower()
        
        # PRIORITY 1: Safety classification (highest priority to prevent misclassification)
        if any(re.search(pattern, text_lower) for pattern in self.type_patterns['safety']):
            return 'safety'
        
        # Section-based classification
        if section.lower() in ['methods', 'protocol', 'sap']:
            if any(re.search(pattern, text_lower) for pattern in self.type_patterns['design_fact']):
                return 'design_fact'
            elif any(re.search(pattern, text_lower) for pattern in self.type_patterns['operational']):
                return 'operational'
        
        elif section.lower() in ['results', 'abstract']:
            if any(re.search(pattern, text_lower) for pattern in self.type_patterns['effect_size']):
                return 'effect_size'
            elif any(re.search(pattern, text_lower) for pattern in self.type_patterns['prevalence']):
                return 'prevalence'
        
        # Content-based classification (excluding safety which was already checked)
        for claim_type, patterns in self.type_patterns.items():
            if claim_type != 'safety' and any(re.search(pattern, text_lower) for pattern in patterns):
                return claim_type
        
        # Default based on section
        if section.lower() in ['methods', 'protocol', 'sap']:
            return 'design_fact'
        elif section.lower() in ['results', 'abstract']:
            return 'effect_size'
        else:
            return 'operational'

    def _classify_stance(self, text: str) -> str:
        """Classify the stance of the claim based on content."""
        text_lower = text.lower()
        
        for stance, patterns in self.stance_patterns.items():
            if any(re.search(pattern, text_lower) for pattern in patterns):
                return stance
        
        return 'neutral'

    def _extract_numeric_claims(self, text: str, span: EvidenceSpan, claim_type: str, stance: str) -> List[Claim]:
        """Extract numeric claims from text with CI guards and proper confidence interval handling."""
        claims = []
        
        # First, extract confidence intervals to avoid mis-extracting CI levels as effect values
        ci_patterns = [
            r'(\d+\.?\d*)%\s*CI\s*[:\-]\s*([0-9.]+)\s*[-–—]\s*([0-9.]+)',  # "95% CI: 3.4-39.6"
            r'CI\s*[:\-]\s*([0-9.]+)\s*[-–—]\s*([0-9.]+)',  # "CI: 3.4-39.6"
            r'(\d+\.?\d*)%\s*confidence\s*interval\s*[:\-]\s*([0-9.]+)\s*[-–—]\s*([0-9.]+)',  # "95% confidence interval: 3.4-39.6"
        ]
        
        ci_extracted = []
        for pattern in ci_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) == 3:  # "95% CI: 3.4-39.6"
                    ci_level = float(match.group(1))
                    ci_lower = float(match.group(2))
                    ci_upper = float(match.group(3))
                    ci_extracted.append({
                        'level': ci_level,
                        'lower': ci_lower,
                        'upper': ci_upper,
                        'start': match.start(),
                        'end': match.end()
                    })
                elif len(match.groups()) == 2:  # "CI: 3.4-39.6"
                    ci_lower = float(match.group(1))
                    ci_upper = float(match.group(2))
                    ci_extracted.append({
                        'level': None,
                        'lower': ci_lower,
                        'upper': ci_upper,
                        'start': match.start(),
                        'end': match.end()
                    })
        
        # Extract different types of numeric values with CI guards
        numeric_patterns = [
            # Response rates (with CI guard)
            (r'(\d+\.?\d*)\s*%', 'percent', 'response_rate'),
            # Counts
            (r'(\d+)\s+(patients?|subjects?|participants?)', 'count', 'enrollment'),
            # Generic time values (will be classified as survival or duration based on context)
            (r'(\d+\.?\d*)\s+(weeks?|months?|years?)', 'time', 'time_value'),
            # Hazard ratios
            (r'HR\s*[=]\s*(\d+\.?\d*)', 'ratio', 'hazard_ratio'),
            # P-values
            (r'p\s*[<>=]\s*(\d+\.?\d*)', 'p_value', 'statistical'),
        ]
        
        for pattern, unit_type, metric_name in numeric_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                value = match.group(1)
                match_start = match.start()
                match_end = match.end()
                
                # CI GUARD: Check if this percentage is within ±10 tokens of a CI pattern
                if unit_type == 'percent':
                    is_ci_level = False
                    for ci in ci_extracted:
                        # Check if this percentage is close to a CI pattern
                        if abs(match_start - ci['start']) <= 10 or abs(match_end - ci['end']) <= 10:
                            # Check if this percentage matches the CI level
                            if abs(float(value) - (ci['level'] or 95)) < 0.1:  # Allow small floating point differences
                                is_ci_level = True
                                break
                    
                    if is_ci_level:
                        print(f"DEBUG: Skipping {value}% as it appears to be a CI level, not an effect value")
                        continue
                
                # Convert to appropriate type
                try:
                    if unit_type == 'percent':
                        numeric_value = float(value)
                        units = 'percent'
                    elif unit_type == 'count':
                        numeric_value = int(value)
                        units = 'count'
                    elif unit_type in ['time', 'survival']:
                        numeric_value = float(value)
                        # Extract time unit
                        time_match = re.search(r'(\d+\.?\d*)\s+(weeks?|months?|years?)', match.group(0), re.IGNORECASE)
                        if time_match:
                            units = time_match.group(2).lower()
                            if units.endswith('s'):
                                units = units[:-1]  # Remove plural
                        else:
                            units = 'weeks'
                    elif unit_type == 'ratio':
                        numeric_value = float(value)
                        units = 'ratio'
                    elif unit_type == 'p_value':
                        numeric_value = float(value)
                        units = 'p_value'
                    else:
                        continue
                except ValueError:
                    continue
                
                # Find associated confidence interval for this claim
                ci_lower = None
                ci_upper = None
                if unit_type == 'percent':
                    # Look for CI within ±20 tokens of this percentage
                    for ci in ci_extracted:
                        if abs(match_start - ci['start']) <= 20 or abs(match_end - ci['end']) <= 20:
                            ci_lower = ci['lower']
                            ci_upper = ci['upper']
                            break
                
                # Determine proper endpoint based on claim type and content
                endpoint = self._determine_endpoint(claim_type, metric_name, text, numeric_value)
                
                # Create claim
                claim = Claim(
                    claim_id=f"{span.doc_id}#claim_{len(claims)}",
                    doc_id=span.doc_id,
                    span_ids=[span.span_id],
                    type=claim_type,
                    proposition=f"{metric_name}: {value}",
                    stance=stance,
                    value=numeric_value,
                    units=units,
                    endpoint=endpoint,
                    ci_lower=ci_lower,
                    ci_upper=ci_upper,
                    quality_score=self._calculate_quality_score(text, span.section),
                    applicability_score=self._calculate_applicability_score(text, span.section)
                )
                
                claims.append(claim)
        
        return claims
    
    def _determine_endpoint(self, claim_type: str, metric_name: str, text: str, value: float) -> str:
        """
        Determine the proper endpoint based on claim type and content.
        
        This prevents misclassification of safety metrics as efficacy metrics
        and ensures survival endpoints get proper labels.
        """
        text_lower = text.lower()
        
        # Safety claims get specific safety endpoints
        if claim_type == 'safety':
            # Check for grade-specific patterns
            if re.search(r'grade\s*(\d+)\+?\s*AE', text_lower):
                grade = re.search(r'grade\s*(\d+)\+?\s*AE', text_lower).group(1)
                return f"grade≥{grade}_AE_rate"
            elif re.search(r'grade\s*(\d+)\+?\s*adverse\s+event', text_lower):
                grade = re.search(r'grade\s*(\d+)\+?\s*adverse\s+event', text_lower).group(1)
                return f"grade≥{grade}_AE_rate"
            elif re.search(r'grade\s*(\d+)\+?\s*toxicity', text_lower):
                grade = re.search(r'grade\s*(\d+)\+?\s*toxicity', text_lower).group(1)
                return f"grade≥{grade}_toxicity_rate"
            elif re.search(r'grade\s*(\d+)', text_lower):
                grade = re.search(r'grade\s*(\d+)', text_lower).group(1)
                return f"grade≥{grade}_AE_rate"
            elif re.search(r'adverse\s+event|AE', text_lower):
                return "overall_AE_rate"
            elif re.search(r'toxicity|toxic', text_lower):
                return "overall_toxicity_rate"
            else:
                return "safety_metric"
        
        # Time value classification (survival vs generic duration)
        if metric_name == 'time_value':
            # Look for specific survival terms in the text
            if re.search(r'\bPFS\b', text, re.IGNORECASE):
                return "median_pfs"
            elif re.search(r'\bTTP\b', text, re.IGNORECASE):
                return "median_ttp"
            elif re.search(r'\bOS\b', text, re.IGNORECASE):
                return "median_os"
            elif re.search(r'\btime\s+to\s+progression\b', text, re.IGNORECASE):
                return "median_ttp"  # Time to progression is TTP, not PFS
            elif re.search(r'\bprogression.?free\s+survival\b', text, re.IGNORECASE):
                return "median_pfs"  # Progression-free survival is PFS
            elif re.search(r'\bprogression\b', text, re.IGNORECASE):
                # Check if this is TTP or PFS based on context
                if re.search(r'\btime\s+to\s+progression\b', text, re.IGNORECASE):
                    return "median_ttp"
                elif re.search(r'\bprogression.?free\s+survival\b', text, re.IGNORECASE):
                    return "median_pfs"
                else:
                    return "median_pfs"  # Default to PFS for generic progression
            elif re.search(r'\boverall\s+survival\b', text, re.IGNORECASE):
                return "median_os"
            else:
                # Check if any survival terms are nearby (within the same sentence)
                survival_terms = ['pfs', 'ttp', 'os', 'progression', 'survival']
                if any(term in text_lower for term in survival_terms):
                    # Determine based on context
                    if 'time to progression' in text_lower:
                        return "median_ttp"
                    elif 'progression' in text_lower:
                        return "median_pfs"
                    elif 'survival' in text_lower:
                        return "median_os"
                    else:
                        return "survival_endpoint"  # Generic fallback
                else:
                    # No survival terms found - this is generic duration
                    return "duration"
        
        # For non-safety, non-survival claims, use the metric name
        return metric_name

    def _extract_non_numeric_claims(self, text: str, span: EvidenceSpan, claim_type: str, stance: str) -> List[Claim]:
        """Extract non-numeric claims from text."""
        claims = []
        
        # Extract design facts
        if claim_type == 'design_fact':
            design_patterns = [
                (r'(single.?center|multi.?center)', 'center_type'),
                (r'(open.?label|blinded|double.?blind)', 'blinding'),
                (r'(phase\s+\d+|stage\s+\d+)', 'study_phase'),
                (r'(gehan|two.?stage|adaptive)', 'interim_design'),
            ]
            
            for pattern, fact_type in design_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    claim = Claim(
                        claim_id=f"{span.doc_id}#claim_{len(claims)}",
                        doc_id=span.doc_id,
                        span_ids=[span.span_id],
                        type=claim_type,
                        proposition=f"{fact_type}: {match.group(1)}",
                        stance=stance,
                        endpoint=fact_type,
                        quality_score=self._calculate_quality_score(text, span.section),
                        applicability_score=self._calculate_applicability_score(text, span.section)
                    )
                    claims.append(claim)
        
        # Extract limitations
        elif claim_type == 'limitation':
            limitation_patterns = [
                (r'(small\s+sample|underpowered)', 'sample_size'),
                (r'(exploratory|post.?hoc)', 'analysis_type'),
                (r'(bias|confounding)', 'study_quality'),
            ]
            
            for pattern, limitation_type in limitation_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    claim = Claim(
                        claim_id=f"{span.doc_id}#claim_{len(claims)}",
                        doc_id=span.doc_id,
                        span_ids=[span.span_id],
                        type=claim_type,
                        proposition=f"{limitation_type}: {match.group(1)}",
                        stance=stance,
                        endpoint=limitation_type,
                        quality_score=self._calculate_quality_score(text, span.section),
                        applicability_score=self._calculate_applicability_score(text, span.section)
                    )
                    claims.append(claim)
        
        return claims

    def _calculate_quality_score(self, text: str, section: str) -> float:
        """Calculate quality score based on content and section."""
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
        for quality_level, patterns in self.quality_indicators.items():
            if any(re.search(pattern, text_lower) for pattern in patterns):
                if quality_level == 'high':
                    score += 0.3
                elif quality_level == 'medium':
                    score += 0.1
                elif quality_level == 'low':
                    score -= 0.2
        
        # Confidence interval presence
        if re.search(r'confidence\s+interval|CI|95%', text_lower):
            score += 0.1
        
        # P-value presence
        if re.search(r'p\s*[<>=]', text_lower):
            score += 0.1
        
        # Normalize to 0.0-1.0 range
        return max(0.0, min(1.0, score))

    def _calculate_applicability_score(self, text: str, section: str) -> float:
        """Calculate applicability score based on content and section."""
        text_lower = text.lower()
        score = 0.5  # Base score
        
        # Section-based scoring
        if section.lower() in ['methods', 'protocol']:
            score += 0.2  # Methods are generally more applicable
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
        
        # Statistical rigor
        if re.search(r'statistical|statistically|p\s*[<]\s*0\.05', text_lower):
            score += 0.1
        
        # Normalize to 0.0-1.0 range
        return max(0.0, min(1.0, score))

    def _deduplicate_claims(self, claims: List[Claim]) -> List[Claim]:
        """Deduplicate claims based on proposition and type."""
        seen = {}
        deduplicated = []
        
        for claim in claims:
            # Create a key for deduplication
            key = (claim.type, claim.proposition, claim.doc_id)
            
            if key not in seen:
                seen[key] = claim
                deduplicated.append(claim)
            else:
                # Merge span_ids
                existing_claim = seen[key]
                for span_id in claim.span_ids:
                    if span_id not in existing_claim.span_ids:
                        existing_claim.add_span(span_id)
                
                # Update quality scores (take the higher)
                existing_claim.quality_score = max(existing_claim.quality_score, claim.quality_score)
                existing_claim.applicability_score = max(existing_claim.applicability_score, claim.applicability_score)
        
        return deduplicated

    def _normalize_claims(self, claims: List[Claim]) -> List[Claim]:
        """Normalize units and values in claims."""
        for claim in claims:
            if claim.units:
                # Normalize time units
                if claim.units in ['weeks', 'week']:
                    claim.units = 'weeks'
                elif claim.units in ['months', 'month']:
                    claim.units = 'months'
                elif claim.units in ['years', 'year']:
                    claim.units = 'years'
                
                # Normalize percentage units
                if claim.units in ['%', 'percent']:
                    claim.units = 'percent'
                
                # Normalize count units
                if claim.units in ['patients', 'subjects', 'participants']:
                    claim.units = 'count'
        
        return claims

    def _score_claims(self, claims: List[Claim]) -> List[Claim]:
        """Score claims for quality and applicability."""
        for claim in claims:
            # Calculate quality score
            claim.quality_score = self._calculate_quality_score(claim.proposition, claim.doc_id)
            
            # Calculate applicability score
            claim.applicability_score = self._calculate_applicability_score(claim.proposition, claim.doc_id)
            
            # Set overall score as average
            claim.score = (claim.quality_score + claim.applicability_score) / 2.0
        
        return claims

    def _add_provenance(self, claim: Claim, inputs: Dict[str, Any]) -> None:
        """Add provenance information to the claim."""
        # Set input_hash for lineage tracking
        claim.input_hash = self._compute_input_hash(inputs)
        
        # Set created_by
        claim.created_by = self.name
        
        # Set parent_ids (span IDs)
        if claim.span_ids:
            claim.parent_ids = claim.span_ids.copy()
