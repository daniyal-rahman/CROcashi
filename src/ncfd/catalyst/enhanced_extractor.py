"""
Enhanced Study Card Field Extractor

Extends the basic field extractor with specialized parsing for:
- Tone analysis and claim strength
- Conflicts of interest and funding
- Publication details and registry discrepancies
- Data location mapping with tables, figures, and quote spans
"""

from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
import re
import json
from .extractor import StudyCardFieldExtractor, ExtractedField, FieldExtractionResult


class ToneCategory(Enum):
    """Categories for tone analysis."""
    CAUTIOUS = "cautious"
    NEUTRAL = "neutral"
    DEFINITIVE = "definitive"


class ClaimStrength(Enum):
    """Levels of claim strength."""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class ConflictType(Enum):
    """Types of conflicts of interest."""
    FINANCIAL = "financial"
    EMPLOYMENT = "employment"
    ADVISORY = "advisory"
    EQUITY = "equity"
    PATENTS = "patents"
    NONE_DECLARED = "none_declared"
    OTHER = "other"


class FundingType(Enum):
    """Types of funding sources."""
    INDUSTRY = "industry"
    GOVERNMENT = "government"
    ACADEMIC = "academic"
    FOUNDATION = "foundation"
    MIXED = "mixed"
    NOT_DISCLOSED = "not_disclosed"


class JournalType(Enum):
    """Types of journals."""
    HIGH_IMPACT = "high_impact"
    SPECIALTY = "specialty"
    GENERAL = "general"
    SUPPLEMENT = "supplement"
    PREPRINT = "preprint"
    CONFERENCE = "conference"
    OTHER = "other"


class FigureType(Enum):
    """Types of figures in publications."""
    KAPLAN_MEIER = "kaplan_meier"
    FOREST_PLOT = "forest_plot"
    WATERFALL = "waterfall"
    SCATTER = "scatter"
    BAR_CHART = "bar_chart"
    FLOW_DIAGRAM = "flow_diagram"
    OTHER = "other"


@dataclass
class ToneAnalysisResult:
    """Result of tone analysis."""
    overall_tone: ToneCategory
    claim_strength: Dict[str, ClaimStrength]
    cautious_language: List[Dict[str, Any]]
    definitive_language: List[Dict[str, Any]]
    confidence: float


@dataclass
class ConflictsFundingResult:
    """Result of conflicts and funding analysis."""
    conflicts_of_interest: List[Dict[str, Any]]
    funding_sources: List[Dict[str, Any]]
    sponsor_role: Dict[str, Optional[bool]]
    confidence: float


@dataclass
class PublicationDetailsResult:
    """Result of publication details analysis."""
    journal_type: JournalType
    journal_name: Optional[str]
    impact_factor: Optional[float]
    open_access: Optional[bool]
    peer_reviewed: Optional[bool]
    publication_date: Optional[str]
    doi: Optional[str]
    pmid: Optional[str]
    registry_discrepancies: List[Dict[str, Any]]
    confidence: float


@dataclass
class DataLocationResult:
    """Result of data location mapping."""
    tables: List[Dict[str, Any]]
    figures: List[Dict[str, Any]]
    quote_spans: List[Dict[str, Any]]
    confidence: float


class EnhancedStudyCardExtractor:
    """Enhanced field extractor for comprehensive study card analysis."""
    
    def __init__(self):
        self.basic_extractor = StudyCardFieldExtractor()
        
        # Tone analysis patterns
        self.cautious_patterns = [
            r'\b(may|might|could|possibly|potentially|suggests?|indicates?|appears?|seems?)\b',
            r'\b(preliminary|initial|exploratory|hypothesis|hypothesized)\b',
            r'\b(limited|restricted|constrained|cautious|careful)\b',
            r'\b(need\s+to\s+confirm|requires?\s+validation|further\s+study)\b',
            r'\b(not\s+conclusive|inconclusive|uncertain|unclear)\b'
        ]
        
        self.definitive_patterns = [
            r'\b(clearly|definitively|conclusively|unequivocally|demonstrates?|proves?|establishes?)\b',
            r'\b(significant|highly\s+significant|statistically\s+significant)\b',
            r'\b(robust|strong|compelling|convincing|definitive)\b',
            r'\b(confirm|validate|verify|demonstrate|establish)\b',
            r'\b(clear|obvious|evident|apparent|definite)\b'
        ]
        
        # Conflict detection patterns
        self.conflict_patterns = {
            'financial': [
                r'\b(consulting\s+fees?|honoraria|speakers?\s+bureau|advisory\s+board)\b',
                r'\b(stock\s+options?|equity|ownership|financial\s+interest)\b',
                r'\b(grant|funding|sponsorship|research\s+support)\b'
            ],
            'employment': [
                r'\b(employee|employment|salary|compensation)\b',
                r'\b(consultant|advisor|expert|witness)\b'
            ],
            'patents': [
                r'\b(patent|inventor|intellectual\s+property|IP)\b',
                r'\b(licensing|royalties|commercialization)\b'
            ]
        }
        
        # Funding detection patterns
        self.funding_patterns = {
            'industry': [
                r'\b(pharmaceutical|biotech|company|corporation|inc\.|ltd\.)\b',
                r'\b(industry\s+sponsored|commercial\s+sponsor)\b'
            ],
            'government': [
                r'\b(NIH|NSF|FDA|CDC|government|federal|national)\b',
                r'\b(grants?|funding|support)\b'
            ],
            'academic': [
                r'\b(university|college|institution|academic|research)\b',
                r'\b(endowment|foundation|trust)\b'
            ]
        }
        
        # Journal type detection patterns
        self.journal_patterns = {
            'high_impact': [
                r'\b(Nature|Science|Cell|NEJM|Lancet|JAMA|BMJ)\b',
                r'\b(impact\s+factor\s*[>≥]\s*\d+)\b'
            ],
            'specialty': [
                r'\b(Journal\s+of|J\.|Annals\s+of|Archives\s+of)\b',
                r'\b(specialty|specialized|field-specific)\b'
            ],
            'conference': [
                r'\b(conference|proceedings|abstract|poster|presentation)\b',
                r'\b(ASCO|ASH|AACR|ESMO|ASCO-GI)\b'
            ]
        }
    
    def extract_enhanced_fields(self, study_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract all enhanced fields from study data."""
        result = {}
        
        # Extract basic fields first
        basic_result = self.basic_extractor.extract_study_card_fields(1, 1, study_data)
        result['basic_fields'] = basic_result
        
        # Extract enhanced fields
        result['tone_analysis'] = self._extract_tone_analysis(study_data)
        result['conflicts_funding'] = self._extract_conflicts_funding(study_data)
        result['publication_details'] = self._extract_publication_details(study_data)
        result['data_location'] = self._extract_data_location(study_data)
        
        return result
    
    def _extract_tone_analysis(self, study_data: Dict[str, Any]) -> ToneAnalysisResult:
        """Extract tone analysis from study data."""
        text_content = self._extract_text_content(study_data)
        
        # Analyze overall tone
        cautious_score = self._count_pattern_matches(text_content, self.cautious_patterns)
        definitive_score = self._count_pattern_matches(text_content, self.definitive_patterns)
        
        if definitive_score > cautious_score * 2:
            overall_tone = ToneCategory.DEFINITIVE
        elif cautious_score > definitive_score * 2:
            overall_tone = ToneCategory.CAUTIOUS
        else:
            overall_tone = ToneCategory.NEUTRAL
        
        # Analyze claim strength for different sections
        claim_strength = {
            'primary_endpoint': self._analyze_endpoint_claim_strength(study_data, 'primary_endpoints'),
            'secondary_endpoints': self._analyze_endpoint_claim_strength(study_data, 'secondary_endpoints'),
            'subgroup_analyses': self._analyze_subgroup_claim_strength(study_data)
        }
        
        # Extract specific language examples
        cautious_language = self._extract_cautious_language(text_content)
        definitive_language = self._extract_definitive_language(text_content)
        
        # Calculate confidence
        confidence = self._calculate_tone_confidence(
            cautious_score, definitive_score, len(text_content)
        )
        
        return ToneAnalysisResult(
            overall_tone=overall_tone,
            claim_strength=claim_strength,
            cautious_language=cautious_language,
            definitive_language=definitive_language,
            confidence=confidence
        )
    
    def _extract_conflicts_funding(self, study_data: Dict[str, Any]) -> ConflictsFundingResult:
        """Extract conflicts of interest and funding information."""
        text_content = self._extract_text_content(study_data)
        
        # Extract conflicts of interest
        conflicts = []
        for conflict_type, patterns in self.conflict_patterns.items():
            matches = self._find_pattern_matches(text_content, patterns)
            for match in matches:
                conflicts.append({
                    'type': conflict_type,
                    'description': match['text'],
                    'entities': self._extract_entities(match['text']),
                    'evidence': [{'loc': match['location'], 'text_preview': match['text']}]
                })
        
        # Extract funding sources
        funding_sources = []
        for funding_type, patterns in self.funding_patterns.items():
            matches = self._find_pattern_matches(text_content, patterns)
            for match in matches:
                funding_sources.append({
                    'type': funding_type,
                    'entity': self._extract_funding_entity(match['text']),
                    'grant_number': self._extract_grant_number(match['text']),
                    'evidence': [{'loc': match['location'], 'text_preview': match['text']}]
                })
        
        # Extract sponsor role information
        sponsor_role = self._extract_sponsor_role(study_data)
        
        # Calculate confidence
        confidence = self._calculate_conflicts_confidence(
            len(conflicts), len(funding_sources), len(text_content)
        )
        
        return ConflictsFundingResult(
            conflicts_of_interest=conflicts,
            funding_sources=funding_sources,
            sponsor_role=sponsor_role,
            confidence=confidence
        )
    
    def _extract_publication_details(self, study_data: Dict[str, Any]) -> PublicationDetailsResult:
        """Extract publication details and metadata."""
        text_content = self._extract_text_content(study_data)
        
        # Determine journal type
        journal_type = self._determine_journal_type(text_content)
        
        # Extract journal name
        journal_name = self._extract_journal_name(study_data)
        
        # Extract impact factor
        impact_factor = self._extract_impact_factor(text_content)
        
        # Determine open access status
        open_access = self._determine_open_access(text_content)
        
        # Determine peer review status
        peer_reviewed = self._determine_peer_reviewed(text_content)
        
        # Extract publication date
        publication_date = self._extract_publication_date(study_data)
        
        # Extract identifiers
        doi = self._extract_doi(study_data)
        pmid = self._extract_pmid(study_data)
        
        # Extract registry discrepancies
        registry_discrepancies = self._extract_registry_discrepancies(study_data)
        
        # Calculate confidence
        confidence = self._calculate_publication_confidence(
            journal_type, journal_name, impact_factor, open_access
        )
        
        return PublicationDetailsResult(
            journal_type=journal_type,
            journal_name=journal_name,
            impact_factor=impact_factor,
            open_access=open_access,
            peer_reviewed=peer_reviewed,
            publication_date=publication_date,
            doi=doi,
            pmid=pmid,
            registry_discrepancies=registry_discrepancies,
            confidence=confidence
        )
    
    def _extract_data_location(self, study_data: Dict[str, Any]) -> DataLocationResult:
        """Extract data location mapping information."""
        # Extract table information
        tables = self._extract_table_mapping(study_data)
        
        # Extract figure information
        figures = self._extract_figure_mapping(study_data)
        
        # Extract quote spans
        quote_spans = self._extract_quote_spans(study_data)
        
        # Calculate confidence
        confidence = self._calculate_location_confidence(
            len(tables), len(figures), len(quote_spans)
        )
        
        return DataLocationResult(
            tables=tables,
            figures=figures,
            quote_spans=quote_spans,
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
    
    def _count_pattern_matches(self, text: str, patterns: List[str]) -> int:
        """Count pattern matches in text."""
        count = 0
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            count += len(matches)
        return count
    
    def _find_pattern_matches(self, text: str, patterns: List[str]) -> List[Dict[str, Any]]:
        """Find pattern matches with location information."""
        matches = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                matches.append({
                    'text': match.group(),
                    'start': match.start(),
                    'end': match.end(),
                    'location': {
                        'scheme': 'char_offsets',
                        'start': match.start(),
                        'end': match.end()
                    }
                })
        return matches
    
    def _analyze_endpoint_claim_strength(self, study_data: Dict[str, Any], endpoint_key: str) -> ClaimStrength:
        """Analyze claim strength for endpoints."""
        if endpoint_key not in study_data:
            return ClaimStrength.WEAK
        
        endpoints = study_data[endpoint_key]
        if not isinstance(endpoints, list):
            return ClaimStrength.WEAK
        
        # Analyze evidence and results
        evidence_count = 0
        strong_evidence_count = 0
        
        for endpoint in endpoints:
            if isinstance(endpoint, dict):
                # Check for evidence
                if 'evidence' in endpoint and endpoint['evidence']:
                    evidence_count += 1
                    if len(endpoint['evidence']) > 1:
                        strong_evidence_count += 1
                
                # Check for strong language in definition
                if 'definition' in endpoint and endpoint['definition']:
                    definition = endpoint['definition'].lower()
                    if any(word in definition for word in ['significant', 'robust', 'clear', 'definitive']):
                        strong_evidence_count += 1
        
        if strong_evidence_count >= evidence_count * 0.7:
            return ClaimStrength.STRONG
        elif strong_evidence_count >= evidence_count * 0.4:
            return ClaimStrength.MODERATE
        else:
            return ClaimStrength.WEAK
    
    def _analyze_subgroup_claim_strength(self, study_data: Dict[str, Any]) -> ClaimStrength:
        """Analyze claim strength for subgroup analyses."""
        if 'results' not in study_data or 'subgroups' not in study_data['results']:
            return ClaimStrength.WEAK
        
        subgroups = study_data['results']['subgroups']
        if not isinstance(subgroups, list):
            return ClaimStrength.WEAK
        
        # Analyze subgroup evidence
        strong_subgroups = 0
        for subgroup in subgroups:
            if isinstance(subgroup, dict):
                # Check for strong evidence
                if 'evidence' in subgroup and subgroup['evidence']:
                    if len(subgroup['evidence']) > 1:
                        strong_subgroups += 1
                
                # Check for statistical significance
                if 'p_value' in subgroup and subgroup['p_value']:
                    try:
                        p_value = float(subgroup['p_value'])
                        if p_value < 0.05:
                            strong_subgroups += 1
                    except (ValueError, TypeError):
                        pass
        
        if strong_subgroups >= len(subgroups) * 0.7:
            return ClaimStrength.STRONG
        elif strong_subgroups >= len(subgroups) * 0.4:
            return ClaimStrength.MODERATE
        else:
            return ClaimStrength.WEAK
    
    def _extract_cautious_language(self, text: str) -> List[Dict[str, Any]]:
        """Extract examples of cautious language."""
        cautious_examples = []
        for pattern in self.cautious_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Get context around the match
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]
                
                cautious_examples.append({
                    'phrase': match.group(),
                    'context': context.strip(),
                    'evidence': [{
                        'loc': {
                            'scheme': 'char_offsets',
                            'start': match.start(),
                            'end': match.end()
                        },
                        'text_preview': context.strip()
                    }]
                })
        
        return cautious_examples[:10]  # Limit to top 10 examples
    
    def _extract_definitive_language(self, text: str) -> List[Dict[str, Any]]:
        """Extract examples of definitive language."""
        definitive_examples = []
        for pattern in self.definitive_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Get context around the match
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]
                
                definitive_examples.append({
                    'phrase': match.group(),
                    'context': context.strip(),
                    'evidence': [{
                        'loc': {
                            'scheme': 'char_offsets',
                            'start': match.start(),
                            'end': match.end()
                        },
                        'text_preview': context.strip()
                    }]
                })
        
        return definitive_examples[:10]  # Limit to top 10 examples
    
    def _extract_entities(self, text: str) -> List[str]:
        """Extract entity names from text."""
        # Simple entity extraction - look for capitalized words
        entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        return list(set(entities))[:5]  # Limit to top 5 entities
    
    def _extract_funding_entity(self, text: str) -> str:
        """Extract funding entity name from text."""
        # Look for company/institution names
        entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        return entities[0] if entities else "Unknown"
    
    def _extract_grant_number(self, text: str) -> Optional[str]:
        """Extract grant number from text."""
        # Look for grant number patterns
        grant_patterns = [
            r'\b[A-Z]{2,4}\d{4,6}\b',  # e.g., NIH12345
            r'\b\d{2}[A-Z]{2,4}\d{4,6}\b',  # e.g., 21AI12345
            r'\b[A-Z]{2,4}-\d{4,6}\b'  # e.g., NIH-12345
        ]
        
        for pattern in grant_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group()
        
        return None
    
    def _extract_sponsor_role(self, study_data: Dict[str, Any]) -> Dict[str, Optional[bool]]:
        """Extract sponsor role information."""
        # This would typically come from specific fields in the study data
        # For now, return default values
        return {
            'trial_design': None,
            'data_collection': None,
            'data_analysis': None,
            'manuscript_preparation': None
        }
    
    def _determine_journal_type(self, text: str) -> JournalType:
        """Determine journal type from text content."""
        for journal_type, patterns in self.journal_patterns.items():
            if self._count_pattern_matches(text, patterns) > 0:
                if journal_type == 'high_impact':
                    return JournalType.HIGH_IMPACT
                elif journal_type == 'specialty':
                    return JournalType.SPECIALTY
                elif journal_type == 'conference':
                    return JournalType.CONFERENCE
        
        return JournalType.GENERAL
    
    def _extract_journal_name(self, study_data: Dict[str, Any]) -> Optional[str]:
        """Extract journal name from study data."""
        # Look in various locations for journal name
        if 'doc' in study_data and 'source_id' in study_data['doc']:
            return study_data['doc']['source_id']
        
        # Could also look in extracted_jsonb for journal information
        return None
    
    def _extract_impact_factor(self, text: str) -> Optional[float]:
        """Extract impact factor from text."""
        # Look for impact factor patterns
        impact_patterns = [
            r'impact\s+factor\s*[=:]\s*(\d+\.?\d*)',
            r'IF\s*[=:]\s*(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*impact\s+factor'
        ]
        
        for pattern in impact_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        return None
    
    def _determine_open_access(self, text: str) -> Optional[bool]:
        """Determine if publication is open access."""
        open_access_patterns = [
            r'\bopen\s+access\b',
            r'\bOA\b',
            r'\bfree\s+access\b',
            r'\bpublicly\s+available\b'
        ]
        
        if self._count_pattern_matches(text, open_access_patterns) > 0:
            return True
        
        # Could also check for paywall indicators
        paywall_patterns = [
            r'\bpaywall\b',
            r'\bsubscription\s+required\b',
            r'\bpay\s+per\s+view\b'
        ]
        
        if self._count_pattern_matches(text, paywall_patterns) > 0:
            return False
        
        return None
    
    def _determine_peer_reviewed(self, text: str) -> Optional[bool]:
        """Determine if publication is peer reviewed."""
        peer_review_patterns = [
            r'\bpeer\s+reviewed\b',
            r'\bpeer\s+review\b',
            r'\brefereed\b'
        ]
        
        if self._count_pattern_matches(text, peer_review_patterns) > 0:
            return True
        
        # Look for preprint indicators
        preprint_patterns = [
            r'\bpreprint\b',
            r'\bmedRxiv\b',
            r'\bbioRxiv\b',
            r'\barXiv\b'
        ]
        
        if self._count_pattern_matches(text, preprint_patterns) > 0:
            return False
        
        return None
    
    def _extract_publication_date(self, study_data: Dict[str, Any]) -> Optional[str]:
        """Extract publication date from study data."""
        if 'doc' in study_data and 'year' in study_data['doc']:
            return str(study_data['doc']['year'])
        return None
    
    def _extract_doi(self, study_data: Dict[str, Any]) -> Optional[str]:
        """Extract DOI from study data."""
        if 'doc' in study_data and 'url' in study_data['doc']:
            url = study_data['doc']['url']
            # Look for DOI in URL
            doi_match = re.search(r'doi\.org/([^/\s]+)', url)
            if doi_match:
                return doi_match.group(1)
        return None
    
    def _extract_pmid(self, study_data: Dict[str, Any]) -> Optional[str]:
        """Extract PMID from study data."""
        # Look for PMID patterns in various fields
        text_content = self._extract_text_content(study_data)
        pmid_match = re.search(r'\bPMID\s*[=:]\s*(\d+)\b', text_content)
        if pmid_match:
            return pmid_match.group(1)
        return None
    
    def _extract_registry_discrepancies(self, study_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract registry discrepancies."""
        # This would compare registry data with publication data
        # For now, return empty list
        return []
    
    def _extract_table_mapping(self, study_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract table mapping information."""
        # Look for table references in the data
        tables = []
        text_content = self._extract_text_content(study_data)
        
        # Find table references
        table_patterns = [
            r'\bTable\s+(\d+[A-Z]?)\b',
            r'\bTable\s+(\d+[A-Z]?)\s*[:.]\s*([^.\n]+)',
            r'\b(Tab\.?\s+\d+[A-Z]?)\b'
        ]
        
        for pattern in table_patterns:
            for match in re.finditer(pattern, text_content, re.IGNORECASE):
                table_id = match.group(1)
                caption = match.group(2) if len(match.groups()) > 1 else f"Table {table_id}"
                
                tables.append({
                    'table_id': table_id,
                    'caption': caption,
                    'data_types': self._infer_table_data_types(caption),
                    'location': {
                        'scheme': 'char_offsets',
                        'start': match.start(),
                        'end': match.end()
                    }
                })
        
        return tables
    
    def _extract_figure_mapping(self, study_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract figure mapping information."""
        # Look for figure references in the data
        figures = []
        text_content = self._extract_text_content(study_data)
        
        # Find figure references
        figure_patterns = [
            r'\bFigure\s+(\d+[A-Z]?)\b',
            r'\bFigure\s+(\d+[A-Z]?)\s*[:.]\s*([^.\n]+)',
            r'\b(Fig\.?\s+\d+[A-Z]?)\b'
        ]
        
        for pattern in figure_patterns:
            for match in re.finditer(pattern, text_content, re.IGNORECASE):
                figure_id = match.group(1)
                caption = match.group(2) if len(match.groups()) > 1 else f"Figure {figure_id}"
                
                figures.append({
                    'figure_id': figure_id,
                    'caption': caption,
                    'figure_type': self._infer_figure_type(caption),
                    'data_types': self._infer_figure_data_types(caption),
                    'location': {
                        'scheme': 'char_offsets',
                        'start': match.start(),
                        'end': match.end()
                    }
                })
        
        return figures
    
    def _extract_quote_spans(self, study_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract quote spans for key data points."""
        # Look for quoted text and key statements
        quote_spans = []
        text_content = self._extract_text_content(study_data)
        
        # Find quoted text
        quote_patterns = [
            r'"([^"]{20,100})"',  # Quoted text 20-100 chars
            r"'([^']{20,100})'",  # Single quoted text
            r'``([^`]{20,100})``'  # Double backtick quotes
        ]
        
        for pattern in quote_patterns:
            for match in re.finditer(pattern, text_content):
                quote_text = match.group(1)
                context = self._get_context(text_content, match.start(), match.end())
                
                quote_spans.append({
                    'text': quote_text,
                    'context': context,
                    'data_type': self._classify_quote_type(quote_text),
                    'location': {
                        'scheme': 'char_offsets',
                        'start': match.start(),
                        'end': match.end()
                    }
                })
        
        return quote_spans[:20]  # Limit to top 20 quotes
    
    def _infer_table_data_types(self, caption: str) -> List[str]:
        """Infer data types from table caption."""
        caption_lower = caption.lower()
        data_types = []
        
        if any(word in caption_lower for word in ['demographic', 'baseline', 'characteristic']):
            data_types.append('demographics')
        if any(word in caption_lower for word in ['efficacy', 'outcome', 'endpoint', 'result']):
            data_types.append('efficacy')
        if any(word in caption_lower for word in ['safety', 'adverse', 'toxicity', 'side effect']):
            data_types.append('safety')
        if any(word in caption_lower for word in ['subgroup', 'subgroup analysis']):
            data_types.append('subgroup')
        
        if not data_types:
            data_types.append('other')
        
        return data_types
    
    def _infer_figure_type(self, caption: str) -> FigureType:
        """Infer figure type from caption."""
        caption_lower = caption.lower()
        
        if any(word in caption_lower for word in ['kaplan', 'meier', 'survival', 'km']):
            return FigureType.KAPLAN_MEIER
        elif any(word in caption_lower for word in ['forest', 'plot', 'meta']):
            return FigureType.FOREST_PLOT
        elif any(word in caption_lower for word in ['waterfall', 'response']):
            return FigureType.WATERFALL
        elif any(word in caption_lower for word in ['scatter', 'correlation']):
            return FigureType.SCATTER
        elif any(word in caption_lower for word in ['bar', 'chart', 'histogram']):
            return FigureType.BAR_CHART
        elif any(word in caption_lower for word in ['flow', 'diagram', 'consort']):
            return FigureType.FLOW_DIAGRAM
        else:
            return FigureType.OTHER
    
    def _infer_figure_data_types(self, caption: str) -> List[str]:
        """Infer data types from figure caption."""
        caption_lower = caption.lower()
        data_types = []
        
        if any(word in caption_lower for word in ['survival', 'kaplan', 'meier']):
            data_types.append('survival')
        if any(word in caption_lower for word in ['efficacy', 'outcome', 'endpoint']):
            data_types.append('efficacy')
        if any(word in caption_lower for word in ['safety', 'adverse', 'toxicity']):
            data_types.append('safety')
        if any(word in caption_lower for word in ['subgroup', 'subgroup analysis']):
            data_types.append('subgroup')
        if any(word in caption_lower for word in ['patient', 'flow', 'consort']):
            data_types.append('patient_flow')
        
        if not data_types:
            data_types.append('other')
        
        return data_types
    
    def _get_context(self, text: str, start: int, end: int) -> str:
        """Get context around a text span."""
        context_start = max(0, start - 100)
        context_end = min(len(text), end + 100)
        return text[context_start:context_end].strip()
    
    def _classify_quote_type(self, quote_text: str) -> str:
        """Classify the type of quoted text."""
        quote_lower = quote_text.lower()
        
        # Look for numeric data
        if re.search(r'\d+\.?\d*', quote_text):
            return 'numeric'
        
        # Look for interpretation language
        if any(word in quote_lower for word in ['conclude', 'suggest', 'indicate', 'demonstrate']):
            return 'interpretation'
        
        # Look for limitation language
        if any(word in quote_lower for word in ['limit', 'constraint', 'caveat', 'caution']):
            return 'limitation'
        
        # Look for conclusion language
        if any(word in quote_lower for word in ['therefore', 'thus', 'hence', 'consequently']):
            return 'conclusion'
        
        return 'qualitative'
    
    def _calculate_tone_confidence(self, cautious_score: int, definitive_score: int, text_length: int) -> float:
        """Calculate confidence in tone analysis."""
        if text_length == 0:
            return 0.0
        
        # Normalize scores by text length
        normalized_cautious = cautious_score / text_length * 1000
        normalized_definitive = definitive_score / text_length * 1000
        
        # Higher confidence with more matches and balanced analysis
        total_matches = cautious_score + definitive_score
        if total_matches == 0:
            return 0.3  # Low confidence with no matches
        
        # Balance factor - prefer balanced analysis
        balance_factor = 1.0 - abs(normalized_cautious - normalized_definitive) / max(normalized_cautious + normalized_definitive, 1)
        
        # Length factor - prefer longer texts
        length_factor = min(text_length / 1000, 1.0)
        
        confidence = (total_matches / 10 + balance_factor + length_factor) / 3
        return min(confidence, 1.0)
    
    def _calculate_conflicts_confidence(self, conflicts_count: int, funding_count: int, text_length: int) -> float:
        """Calculate confidence in conflicts and funding analysis."""
        if text_length == 0:
            return 0.0
        
        # Base confidence on finding relevant information
        base_confidence = 0.5
        
        # Bonus for finding conflicts/funding info
        if conflicts_count > 0 or funding_count > 0:
            base_confidence += 0.3
        
        # Length factor - longer texts provide more context
        length_factor = min(text_length / 2000, 0.2)
        
        return min(base_confidence + length_factor, 1.0)
    
    def _calculate_publication_confidence(self, journal_type: JournalType, journal_name: Optional[str], 
                                        impact_factor: Optional[float], open_access: Optional[bool]) -> float:
        """Calculate confidence in publication details."""
        confidence = 0.3  # Base confidence
        
        # Bonus for journal type determination
        if journal_type != JournalType.OTHER:
            confidence += 0.2
        
        # Bonus for journal name
        if journal_name:
            confidence += 0.2
        
        # Bonus for impact factor
        if impact_factor:
            confidence += 0.2
        
        # Bonus for open access determination
        if open_access is not None:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _calculate_location_confidence(self, tables_count: int, figures_count: int, quotes_count: int) -> float:
        """Calculate confidence in data location mapping."""
        total_elements = tables_count + figures_count + quotes_count
        
        if total_elements == 0:
            return 0.1  # Very low confidence with no elements
        
        # Higher confidence with more elements found
        element_factor = min(total_elements / 10, 0.5)
        
        # Diversity factor - prefer finding different types
        diversity_factor = 0.0
        if tables_count > 0:
            diversity_factor += 0.2
        if figures_count > 0:
            diversity_factor += 0.2
        if quotes_count > 0:
            diversity_factor += 0.1
        
        return min(0.3 + element_factor + diversity_factor, 1.0)
