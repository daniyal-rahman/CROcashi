"""
Reviewer Notes Analyzer

Analyzes study data to identify:
- Limitations in study design, sample size, follow-up, endpoints, analysis, and generalizability
- Statistical, clinical, regulatory, methodological, and reporting oddities
- Geographic outliers and their impact
- Unexplained discrepancies between different data sources
- Overall quality assessment and evidence strength
"""

from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
import re
import json
from datetime import datetime


class LimitationType(Enum):
    """Types of study limitations."""
    STUDY_DESIGN = "study_design"
    SAMPLE_SIZE = "sample_size"
    FOLLOW_UP = "follow_up"
    ENDPOINTS = "endpoints"
    ANALYSIS = "analysis"
    GENERALIZABILITY = "generalizability"
    OTHER = "other"


class LimitationSeverity(Enum):
    """Severity levels for limitations."""
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"


class OddityType(Enum):
    """Types of oddities in study data."""
    STATISTICAL = "statistical"
    CLINICAL = "clinical"
    REGULATORY = "regulatory"
    METHODOLOGICAL = "methodological"
    REPORTING = "reporting"
    OTHER = "other"


class GeographicImpact(Enum):
    """Impact levels of geographic outliers."""
    MINIMAL = "minimal"
    MODERATE = "moderate"
    SIGNIFICANT = "significant"


class DiscrepancyType(Enum):
    """Types of unexplained discrepancies."""
    NUMBERS = "numbers"
    DATES = "dates"
    DEMOGRAPHICS = "demographics"
    OUTCOMES = "outcomes"
    OTHER = "other"


class OverallQuality(Enum):
    """Overall quality ratings."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class EvidenceStrength(Enum):
    """Evidence strength ratings."""
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "insufficient"


@dataclass
class Limitation:
    """A study limitation."""
    type: LimitationType
    description: str
    severity: LimitationSeverity
    evidence: List[Dict[str, Any]]


@dataclass
class Oddity:
    """A study oddity."""
    type: OddityType
    description: str
    evidence: List[Dict[str, Any]]


@dataclass
class GeographicOutlier:
    """A geographic outlier."""
    regions: List[str]
    description: str
    impact: GeographicImpact
    evidence: List[Dict[str, Any]]


@dataclass
class Discrepancy:
    """An unexplained discrepancy."""
    type: DiscrepancyType
    description: str
    source1: str
    source2: str
    evidence: List[Dict[str, Any]]


@dataclass
class QualityAssessment:
    """Overall quality assessment."""
    overall_quality: OverallQuality
    data_completeness: float
    evidence_strength: EvidenceStrength
    reviewer_confidence: float


@dataclass
class ReviewerNotesResult:
    """Complete reviewer notes analysis."""
    limitations: List[Limitation]
    oddities: List[Oddity]
    geographic_outliers: List[GeographicOutlier]
    unexplained_discrepancies: List[Discrepancy]
    quality_assessment: QualityAssessment
    confidence: float


class ReviewerNotesAnalyzer:
    """Analyzes study data to generate comprehensive reviewer notes."""
    
    def __init__(self):
        # Limitation detection patterns
        self.limitation_patterns = {
            LimitationType.STUDY_DESIGN: [
                r'\b(single\s+arm|non\s+randomized|open\s+label|unblinded)\b',
                r'\b(historical\s+control|retrospective|observational)\b',
                r'\b(exploratory|pilot|feasibility|phase\s+1)\b',
                r'\b(limited\s+power|underpowered|small\s+sample)\b'
            ],
            LimitationType.SAMPLE_SIZE: [
                r'\b(small\s+sample|limited\s+power|underpowered)\b',
                r'\b(insufficient\s+power|low\s+power|power\s+calculation)\b',
                r'\b(sample\s+size\s+limitation|n\s*[<≤]\s*\d+)\b'
            ],
            LimitationType.FOLLOW_UP: [
                r'\b(short\s+follow\s+up|limited\s+follow\s+up)\b',
                r'\b(insufficient\s+follow\s+up|early\s+termination)\b',
                r'\b(loss\s+to\s+follow\s+up|dropout|attrition)\b'
            ],
            LimitationType.ENDPOINTS: [
                r'\b(surrogate\s+endpoint|intermediate\s+endpoint)\b',
                r'\b(endpoint\s+change|protocol\s+amendment)\b',
                r'\b(composite\s+endpoint|multiple\s+endpoints)\b'
            ],
            LimitationType.ANALYSIS: [
                r'\b(post\s+hoc|exploratory\s+analysis)\b',
                r'\b(missing\s+data|imputation|sensitivity\s+analysis)\b',
                r'\b(subgroup\s+analysis|interaction\s+test)\b'
            ],
            LimitationType.GENERALIZABILITY: [
                r'\b(limited\s+generalizability|narrow\s+population)\b',
                r'\b(specific\s+population|restricted\s+cohort)\b',
                r'\b(geographic\s+limitation|single\s+center)\b'
            ]
        }
        
        # Oddity detection patterns
        self.oddity_patterns = {
            OddityType.STATISTICAL: [
                r'\b(p\s*[<≤]\s*0\.001|highly\s+significant)\b',
                r'\b(effect\s+size\s+anomaly|outlier|extreme\s+value)\b',
                r'\b(statistical\s+power\s+issue|multiple\s+testing)\b',
                r'\b(confidence\s+interval\s+wide|large\s+standard\s+error)\b'
            ],
            OddityType.CLINICAL: [
                r'\b(unexpected\s+outcome|paradoxical\s+result)\b',
                r'\b(adverse\s+event\s+pattern|safety\s+signal)\b',
                r'\b(clinical\s+relevance|meaningful\s+change)\b',
                r'\b(patient\s+population\s+mismatch|enrollment\s+issue)\b'
            ],
            OddityType.REGULATORY: [
                r'\b(protocol\s+violation|deviation|non\s+compliance)\b',
                r'\b(regulatory\s+requirement|FDA\s+guidance)\b',
                r'\b(approval\s+process|regulatory\s+pathway)\b'
            ],
            OddityType.METHODOLOGICAL: [
                r'\b(method\s+change|procedure\s+modification)\b',
                r'\b(quality\s+control|validation\s+issue)\b',
                r'\b(measurement\s+error|bias|confounding)\b'
            ],
            OddityType.REPORTING: [
                r'\b(incomplete\s+reporting|missing\s+data)\b',
                r'\b(inconsistent\s+reporting|data\s+mismatch)\b',
                r'\b(transparency\s+issue|disclosure\s+gap)\b'
            ]
        }
        
        # Geographic outlier patterns
        self.geographic_patterns = [
            r'\b(United\s+States|US|USA|America)\b',
            r'\b(Europe|European|EU|European\s+Union)\b',
            r'\b(Asia|Asian|China|Japan|India)\b',
            r'\b(Latin\s+America|South\s+America|Brazil|Argentina)\b',
            r'\b(Africa|African|South\s+Africa|Nigeria)\b',
            r'\b(Australia|Australian|Oceania)\b'
        ]
        
        # Discrepancy detection patterns
        self.discrepancy_patterns = {
            DiscrepancyType.NUMBERS: [
                r'\b(discrepancy|mismatch|inconsistency)\b',
                r'\b(different\s+number|conflicting\s+data)\b',
                r'\b(registry\s+vs\s+publication|trial\s+vs\s+paper)\b'
            ],
            DiscrepancyType.DATES: [
                r'\b(date\s+mismatch|timeline\s+discrepancy)\b',
                r'\b(completion\s+date|enrollment\s+date)\b',
                r'\b(protocol\s+amendment\s+date|change\s+date)\b'
            ],
            DiscrepancyType.DEMOGRAPHICS: [
                r'\b(demographic\s+mismatch|population\s+difference)\b',
                r'\b(age\s+range|gender\s+distribution)\b',
                r'\b(ethnicity|race|geographic\s+distribution)\b'
            ],
            DiscrepancyType.OUTCOMES: [
                r'\b(outcome\s+mismatch|result\s+discrepancy)\b',
                r'\b(efficacy\s+data|safety\s+data)\b',
                r'\b(primary\s+vs\s+secondary|ITT\s+vs\s+PP)\b'
            ]
        }
    
    def analyze_reviewer_notes(self, study_data: Dict[str, Any]) -> ReviewerNotesResult:
        """Analyze study data to generate comprehensive reviewer notes."""
        text_content = self._extract_text_content(study_data)
        
        # Analyze limitations
        limitations = self._analyze_limitations(text_content, study_data)
        
        # Analyze oddities
        oddities = self._analyze_oddities(text_content, study_data)
        
        # Analyze geographic outliers
        geographic_outliers = self._analyze_geographic_outliers(text_content, study_data)
        
        # Analyze discrepancies
        discrepancies = self._analyze_discrepancies(text_content, study_data)
        
        # Generate quality assessment
        quality_assessment = self._generate_quality_assessment(
            limitations, oddities, geographic_outliers, discrepancies, study_data
        )
        
        # Calculate overall confidence
        confidence = self._calculate_reviewer_confidence(
            limitations, oddities, geographic_outliers, discrepancies, text_content
        )
        
        return ReviewerNotesResult(
            limitations=limitations,
            oddities=oddities,
            geographic_outliers=geographic_outliers,
            unexplained_discrepancies=discrepancies,
            quality_assessment=quality_assessment,
            confidence=confidence
        )
    
    def _extract_text_content(self, study_data: Dict[str, Any]) -> str:
        """Extract all text content from study data for analysis."""
        text_parts = []
        
        # Extract from various sections
        sections = ['extracted_jsonb', 'doc', 'trial', 'primary_endpoints', 
                   'secondary_endpoints', 'populations', 'results', 'protocol_changes']
        
        for section in sections:
            if section in study_data:
                section_data = study_data[section]
                if isinstance(section_data, dict):
                    text_parts.append(self._extract_text_from_dict(section_data))
                elif isinstance(section_data, list):
                    for item in section_data:
                        if isinstance(item, dict):
                            text_parts.append(self._extract_text_from_dict(item))
        
        return ' '.join(text_parts)
    
    def _extract_text_from_dict(self, data: Dict[str, Any]) -> str:
        """Extract text content from a dictionary."""
        text_parts = []
        
        for key, value in data.items():
            if isinstance(value, str):
                text_parts.append(value)
            elif isinstance(value, dict):
                text_parts.append(self._extract_text_from_dict(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        text_parts.append(self._extract_text_from_dict(item))
                    elif isinstance(item, str):
                        text_parts.append(item)
        
        return ' '.join(text_parts)
    
    def _analyze_limitations(self, text_content: str, study_data: Dict[str, Any]) -> List[Limitation]:
        """Analyze study limitations."""
        limitations = []
        
        for limitation_type, patterns in self.limitation_patterns.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text_content, re.IGNORECASE):
                    # Get context around the match
                    start = max(0, match.start() - 100)
                    end = min(len(text_content), match.end() + 100)
                    context = text_content[start:end]
                    
                    # Determine severity based on context and type
                    severity = self._determine_limitation_severity(
                        limitation_type, match.group(), context
                    )
                    
                    limitations.append(Limitation(
                        type=limitation_type,
                        description=match.group(),
                        severity=severity,
                        evidence=[{
                            'loc': {
                                'scheme': 'char_offsets',
                                'start': match.start(),
                                'end': match.end()
                            },
                            'text_preview': context.strip()
                        }]
                    ))
        
        # Add specific limitations based on study data analysis
        specific_limitations = self._identify_specific_limitations(study_data)
        limitations.extend(specific_limitations)
        
        return limitations[:20]  # Limit to top 20 limitations
    
    def _analyze_oddities(self, text_content: str, study_data: Dict[str, Any]) -> List[Oddity]:
        """Analyze study oddities."""
        oddities = []
        
        for oddity_type, patterns in self.oddity_patterns.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text_content, re.IGNORECASE):
                    # Get context around the match
                    start = max(0, match.start() - 100)
                    end = min(len(text_content), match.end() + 100)
                    context = text_content[start:end]
                    
                    oddities.append(Oddity(
                        type=oddity_type,
                        description=match.group(),
                        evidence=[{
                            'loc': {
                                'scheme': 'char_offsets',
                                'start': match.start(),
                                'end': match.end()
                            },
                            'text_preview': context.strip()
                        }]
                    ))
        
        # Add specific oddities based on study data analysis
        specific_oddities = self._identify_specific_oddities(study_data)
        oddities.extend(specific_oddities)
        
        return oddities[:15]  # Limit to top 15 oddities
    
    def _analyze_geographic_outliers(self, text_content: str, study_data: Dict[str, Any]) -> List[GeographicOutlier]:
        """Analyze geographic outliers."""
        geographic_outliers = []
        
        # Find geographic references
        for pattern in self.geographic_patterns:
            for match in re.finditer(pattern, text_content, re.IGNORECASE):
                region = match.group()
                
                # Get context around the match
                start = max(0, match.start() - 150)
                end = min(len(text_content), match.end() + 150)
                context = text_content[start:end]
                
                # Determine impact based on context
                impact = self._determine_geographic_impact(region, context)
                
                # Check if this region is mentioned multiple times (potential outlier)
                region_count = len(re.findall(re.escape(region), text_content, re.IGNORECASE))
                
                if region_count > 3:  # Only flag as outlier if mentioned frequently
                    geographic_outliers.append(GeographicOutlier(
                        regions=[region],
                        description=f"Frequent reference to {region} region",
                        impact=impact,
                        evidence=[{
                            'loc': {
                                'scheme': 'char_offsets',
                                'start': match.start(),
                                'end': match.end()
                            },
                            'text_preview': context.strip()
                        }]
                    ))
        
        return geographic_outliers[:10]  # Limit to top 10 outliers
    
    def _analyze_discrepancies(self, text_content: str, study_data: Dict[str, Any]) -> List[Discrepancy]:
        """Analyze unexplained discrepancies."""
        discrepancies = []
        
        for discrepancy_type, patterns in self.discrepancy_patterns.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text_content, re.IGNORECASE):
                    # Get context around the match
                    start = max(0, match.start() - 150)
                    end = min(len(text_content), match.end() + 150)
                    context = text_content[start:end]
                    
                    # Try to identify the sources of discrepancy
                    source1, source2 = self._identify_discrepancy_sources(context, discrepancy_type)
                    
                    discrepancies.append(Discrepancy(
                        type=discrepancy_type,
                        description=match.group(),
                        source1=source1,
                        source2=source2,
                        evidence=[{
                            'loc': {
                                'scheme': 'char_offsets',
                                'start': match.start(),
                                'end': match.end()
                            },
                            'text_preview': context.strip()
                        }]
                    ))
        
        # Add specific discrepancies based on study data analysis
        specific_discrepancies = self._identify_specific_discrepancies(study_data)
        discrepancies.extend(specific_discrepancies)
        
        return discrepancies[:15]  # Limit to top 15 discrepancies
    
    def _identify_specific_limitations(self, study_data: Dict[str, Any]) -> List[Limitation]:
        """Identify specific limitations based on study data structure."""
        limitations = []
        
        # Check sample size limitations
        if 'sample_size' in study_data:
            sample_data = study_data['sample_size']
            if isinstance(sample_data, dict):
                total_n = sample_data.get('total_n')
                power = sample_data.get('power')
                
                if total_n and total_n < 100:
                    limitations.append(Limitation(
                        type=LimitationType.SAMPLE_SIZE,
                        description=f"Small sample size (n={total_n})",
                        severity=LimitationSeverity.MAJOR,
                        evidence=[{
                            'loc': {'scheme': 'section_heading', 'section': 'sample_size'},
                            'text_preview': f"Total sample size: {total_n}"
                        }]
                    ))
                
                if power and power < 0.8:
                    limitations.append(Limitation(
                        type=LimitationType.SAMPLE_SIZE,
                        description=f"Underpowered study (power={power:.2f})",
                        severity=LimitationSeverity.MAJOR,
                        evidence=[{
                            'loc': {'scheme': 'section_heading', 'section': 'sample_size'},
                            'text_preview': f"Statistical power: {power:.2f}"
                        }]
                    ))
        
        # Check follow-up limitations
        if 'trial' in study_data:
            trial_data = study_data['trial']
            if isinstance(trial_data, dict):
                status = trial_data.get('status')
                if status and 'terminated' in status.lower():
                    limitations.append(Limitation(
                        type=LimitationType.FOLLOW_UP,
                        description="Study terminated early",
                        severity=LimitationSeverity.CRITICAL,
                        evidence=[{
                            'loc': {'scheme': 'section_heading', 'section': 'trial'},
                            'text_preview': f"Trial status: {status}"
                        }]
                    ))
        
        # Check endpoint limitations
        if 'primary_endpoints' in study_data:
            primary_endpoints = study_data['primary_endpoints']
            if isinstance(primary_endpoints, list) and len(primary_endpoints) > 3:
                limitations.append(Limitation(
                    type=LimitationType.ENDPOINTS,
                    description="Multiple primary endpoints may reduce statistical power",
                    severity=LimitationSeverity.MODERATE,
                    evidence=[{
                        'loc': {'scheme': 'section_heading', 'section': 'primary_endpoints'},
                        'text_preview': f"Number of primary endpoints: {len(primary_endpoints)}"
                    }]
                ))
        
        return limitations
    
    def _identify_specific_oddities(self, study_data: Dict[str, Any]) -> List[Oddity]:
        """Identify specific oddities based on study data structure."""
        oddities = []
        
        # Check for statistical oddities
        if 'results' in study_data:
            results_data = study_data['results']
            if isinstance(results_data, dict):
                # Check for extremely low p-values
                if 'primary' in results_data:
                    primary_results = results_data['primary']
                    if isinstance(primary_results, list):
                        for result in primary_results:
                            if isinstance(result, dict) and 'p_value' in result:
                                try:
                                    p_value = float(result['p_value'])
                                    if p_value < 0.001:
                                        oddities.append(Oddity(
                                            type=OddityType.STATISTICAL,
                                            description=f"Extremely low p-value (p={p_value:.6f})",
                                            evidence=[{
                                                'loc': {'scheme': 'section_heading', 'section': 'results'},
                                                'text_preview': f"Primary result p-value: {p_value}"
                                            }]
                                        ))
                                except (ValueError, TypeError):
                                    pass
        
        # Check for clinical oddities
        if 'populations' in study_data:
            populations_data = study_data['populations']
            if isinstance(populations_data, dict):
                # Check for high dropout rates
                dropout_pct = populations_data.get('dropouts_overall_pct')
                if dropout_pct and dropout_pct > 20:
                    oddities.append(Oddity(
                        type=OddityType.CLINICAL,
                        description=f"High dropout rate ({dropout_pct}%)",
                        evidence=[{
                            'loc': {'scheme': 'section_heading', 'section': 'populations'},
                            'text_preview': f"Overall dropout rate: {dropout_pct}%"
                        }]
                    ))
        
        return oddities
    
    def _identify_specific_discrepancies(self, study_data: Dict[str, Any]) -> List[Discrepancy]:
        """Identify specific discrepancies based on study data structure."""
        discrepancies = []
        
        # Check for ITT vs PP discrepancies
        if 'populations' in study_data and 'results' in study_data:
            populations_data = study_data['populations']
            results_data = study_data['results']
            
            if isinstance(populations_data, dict) and isinstance(results_data, dict):
                analysis_primary_on = populations_data.get('analysis_primary_on')
                
                if analysis_primary_on and analysis_primary_on != 'ITT':
                    discrepancies.append(Discrepancy(
                        type=DiscrepancyType.OUTCOMES,
                        description="Primary analysis not on ITT population",
                        source1="Protocol (ITT)",
                        source2=f"Actual analysis ({analysis_primary_on})",
                        evidence=[{
                            'loc': {'scheme': 'section_heading', 'section': 'populations'},
                            'text_preview': f"Primary analysis on: {analysis_primary_on}"
                        }]
                    ))
        
        # Check for protocol changes
        if 'protocol_changes' in study_data:
            protocol_changes = study_data['protocol_changes']
            if isinstance(protocol_changes, list) and len(protocol_changes) > 0:
                for change in protocol_changes:
                    if isinstance(change, dict):
                        post_lpr = change.get('post_LPR')
                        if post_lpr:
                            discrepancies.append(Discrepancy(
                                type=DiscrepancyType.DATES,
                                description="Protocol change after LPR",
                                source1="Original protocol",
                                source2="Modified protocol",
                                evidence=[{
                                    'loc': {'scheme': 'section_heading', 'section': 'protocol_changes'},
                                    'text_preview': f"Protocol change: {change.get('change', 'Unknown')}"
                                }]
                            ))
        
        return discrepancies
    
    def _determine_limitation_severity(self, limitation_type: LimitationType, 
                                     description: str, context: str) -> LimitationSeverity:
        """Determine the severity of a limitation."""
        description_lower = description.lower()
        context_lower = context.lower()
        
        # Critical limitations
        if any(word in description_lower for word in ['terminated', 'stopped', 'failed']):
            return LimitationSeverity.CRITICAL
        
        if any(word in context_lower for word in ['critical', 'severe', 'major', 'significant']):
            return LimitationSeverity.CRITICAL
        
        # Major limitations
        if any(word in description_lower for word in ['underpowered', 'small sample', 'insufficient']):
            return LimitationSeverity.MAJOR
        
        if limitation_type in [LimitationType.SAMPLE_SIZE, LimitationType.FOLLOW_UP]:
            return LimitationSeverity.MAJOR
        
        # Moderate limitations
        if any(word in description_lower for word in ['limited', 'restricted', 'narrow']):
            return LimitationSeverity.MODERATE
        
        if limitation_type in [LimitationType.ENDPOINTS, LimitationType.ANALYSIS]:
            return LimitationSeverity.MODERATE
        
        # Default to minor
        return LimitationSeverity.MINOR
    
    def _determine_geographic_impact(self, region: str, context: str) -> GeographicImpact:
        """Determine the impact of a geographic outlier."""
        context_lower = context.lower()
        
        # Look for impact indicators in context
        if any(word in context_lower for word in ['significant', 'major', 'important', 'key']):
            return GeographicImpact.SIGNIFICANT
        
        if any(word in context_lower for word in ['moderate', 'some', 'partial']):
            return GeographicImpact.MODERATE
        
        # Default to minimal
        return GeographicImpact.MINIMAL
    
    def _identify_discrepancy_sources(self, context: str, discrepancy_type: DiscrepancyType) -> Tuple[str, str]:
        """Identify the sources of a discrepancy."""
        context_lower = context.lower()
        
        if discrepancy_type == DiscrepancyType.NUMBERS:
            if 'registry' in context_lower and 'publication' in context_lower:
                return "Registry", "Publication"
            elif 'trial' in context_lower and 'paper' in context_lower:
                return "Trial data", "Publication"
            else:
                return "Source 1", "Source 2"
        
        elif discrepancy_type == DiscrepancyType.DATES:
            if 'protocol' in context_lower and 'amendment' in context_lower:
                return "Original protocol", "Amended protocol"
            elif 'enrollment' in context_lower and 'completion' in context_lower:
                return "Enrollment date", "Completion date"
            else:
                return "Date 1", "Date 2"
        
        elif discrepancy_type == DiscrepancyType.DEMOGRAPHICS:
            if 'itt' in context_lower and 'pp' in context_lower:
                return "ITT population", "PP population"
            else:
                return "Population 1", "Population 2"
        
        elif discrepancy_type == DiscrepancyType.OUTCOMES:
            if 'primary' in context_lower and 'secondary' in context_lower:
                return "Primary endpoint", "Secondary endpoint"
            else:
                return "Outcome 1", "Outcome 2"
        
        return "Source 1", "Source 2"
    
    def _generate_quality_assessment(self, limitations: List[Limitation], 
                                   oddities: List[Oddity], 
                                   geographic_outliers: List[GeographicOutlier],
                                   discrepancies: List[Discrepancy],
                                   study_data: Dict[str, Any]) -> QualityAssessment:
        """Generate overall quality assessment."""
        
        # Calculate data completeness
        data_completeness = self._calculate_data_completeness(study_data)
        
        # Determine evidence strength
        evidence_strength = self._determine_evidence_strength(
            limitations, oddities, discrepancies, study_data
        )
        
        # Determine overall quality
        overall_quality = self._determine_overall_quality(
            limitations, oddities, evidence_strength, data_completeness
        )
        
        # Calculate reviewer confidence
        reviewer_confidence = self._calculate_reviewer_confidence(
            limitations, oddities, geographic_outliers, discrepancies, ""
        )
        
        return QualityAssessment(
            overall_quality=overall_quality,
            data_completeness=data_completeness,
            evidence_strength=evidence_strength,
            reviewer_confidence=reviewer_confidence
        )
    
    def _calculate_data_completeness(self, study_data: Dict[str, Any]) -> float:
        """Calculate data completeness score."""
        required_fields = [
            'trial.nct_id', 'trial.phase', 'trial.indication',
            'primary_endpoints', 'populations', 'arms', 'sample_size',
            'results.primary'
        ]
        
        optional_fields = [
            'secondary_endpoints', 'results.secondary', 'protocol_changes',
            'contradictions', 'signals'
        ]
        
        required_count = 0
        optional_count = 0
        
        for field_path in required_fields:
            if self._field_exists(study_data, field_path):
                required_count += 1
        
        for field_path in optional_fields:
            if self._field_exists(study_data, field_path):
                optional_count += 1
        
        # Weight required fields more heavily
        required_score = required_count / len(required_fields) * 0.7
        optional_score = optional_count / len(optional_fields) * 0.3
        
        return min(required_score + optional_score, 1.0)
    
    def _field_exists(self, data: Dict[str, Any], field_path: str) -> bool:
        """Check if a field exists in nested data structure."""
        keys = field_path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return False
        
        return True
    
    def _determine_evidence_strength(self, limitations: List[Limitation], 
                                   oddities: List[Oddity],
                                   discrepancies: List[Discrepancy],
                                   study_data: Dict[str, Any]) -> EvidenceStrength:
        """Determine evidence strength rating."""
        
        # Count critical and major limitations
        critical_limitations = sum(1 for l in limitations if l.severity == LimitationSeverity.CRITICAL)
        major_limitations = sum(1 for l in limitations if l.severity == LimitationSeverity.MAJOR)
        
        # Count statistical and clinical oddities
        statistical_oddities = sum(1 for o in oddities if o.type == OddityType.STATISTICAL)
        clinical_oddities = sum(1 for o in oddities if o.type == OddityType.CLINICAL)
        
        # Count outcome discrepancies
        outcome_discrepancies = sum(1 for d in discrepancies if d.type == DiscrepancyType.OUTCOMES)
        
        # Determine strength based on issues
        total_issues = critical_limitations + major_limitations + statistical_oddities + clinical_oddities + outcome_discrepancies
        
        if total_issues == 0:
            return EvidenceStrength.STRONG
        elif total_issues <= 2:
            return EvidenceStrength.MODERATE
        elif total_issues <= 5:
            return EvidenceStrength.WEAK
        else:
            return EvidenceStrength.WEAK
    
    def _determine_overall_quality(self, limitations: List[Limitation],
                                 oddities: List[Oddity],
                                 evidence_strength: EvidenceStrength,
                                 data_completeness: float) -> OverallQuality:
        """Determine overall quality rating."""
        
        # Count critical and major limitations
        critical_limitations = sum(1 for l in limitations if l.severity == LimitationSeverity.CRITICAL)
        major_limitations = sum(1 for l in limitations if l.severity == LimitationSeverity.MAJOR)
        
        # Quality scoring
        quality_score = 0.0
        
        # Base score from data completeness
        quality_score += data_completeness * 0.4
        
        # Evidence strength contribution
        if evidence_strength == EvidenceStrength.STRONG:
            quality_score += 0.3
        elif evidence_strength == EvidenceStrength.MODERATE:
            quality_score += 0.2
        elif evidence_strength == EvidenceStrength.WEAK:
            quality_score += 0.1
        
        # Penalty for limitations
        quality_score -= critical_limitations * 0.2
        quality_score -= major_limitations * 0.1
        
        # Penalty for oddities
        quality_score -= len(oddities) * 0.02
        
        # Ensure score is between 0 and 1
        quality_score = max(0.0, min(1.0, quality_score))
        
        # Convert to quality rating
        if quality_score >= 0.8:
            return OverallQuality.EXCELLENT
        elif quality_score >= 0.6:
            return OverallQuality.GOOD
        elif quality_score >= 0.4:
            return OverallQuality.FAIR
        else:
            return OverallQuality.POOR
    
    def _calculate_reviewer_confidence(self, limitations: List[Limitation],
                                     oddities: List[Oddity],
                                     geographic_outliers: List[GeographicOutlier],
                                     discrepancies: List[Discrepancy],
                                     text_content: str) -> float:
        """Calculate confidence in reviewer analysis."""
        
        # Base confidence
        confidence = 0.5
        
        # Bonus for finding issues (indicates thorough analysis)
        total_issues = len(limitations) + len(oddities) + len(geographic_outliers) + len(discrepancies)
        if total_issues > 0:
            confidence += min(total_issues * 0.05, 0.3)
        
        # Bonus for text length (more content to analyze)
        if text_content:
            length_factor = min(len(text_content) / 5000, 0.2)
            confidence += length_factor
        
        # Penalty for too many issues (might indicate poor data quality)
        if total_issues > 20:
            confidence -= 0.1
        
        return min(confidence, 1.0)
