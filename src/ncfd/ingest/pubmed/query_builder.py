"""
PubMed query builder for constructing optimized ESearch queries.

Handles query construction, optimization, and validation for clinical trial literature searches.
"""

import logging
import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


class PubMedQueryBuilder:
    """Builds and optimizes PubMed ESearch queries for clinical trial literature."""
    
    # Common MeSH terms for clinical trials
    CLINICAL_TRIAL_MESH = [
        "Clinical Trial",
        "Randomized Controlled Trial",
        "Controlled Clinical Trial",
        "Clinical Trial, Phase I",
        "Clinical Trial, Phase II", 
        "Clinical Trial, Phase III",
        "Clinical Trial, Phase IV"
    ]
    
    # Common publication types
    PUBLICATION_TYPES = [
        "Clinical Trial",
        "Randomized Controlled Trial",
        "Controlled Clinical Trial",
        "Clinical Study",
        "Case Report",
        "Review",
        "Meta-Analysis",
        "Systematic Review"
    ]
    
    # Common study design terms
    STUDY_DESIGNS = [
        "randomized",
        "controlled",
        "double-blind",
        "single-blind",
        "placebo-controlled",
        "active-controlled",
        "crossover",
        "parallel",
        "sequential"
    ]
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize query builder.
        
        Args:
            config: Configuration dictionary with query parameters
        """
        self.config = config or {}
        self.max_query_length = self.config.get('max_query_length', 2000)
        self.max_terms = self.config.get('max_terms', 50)
        
    def build_trial_query(
        self,
        asset_names: List[str],
        indications: List[str],
        trial_phases: Optional[List[str]] = None,
        date_range: Optional[Tuple[str, str]] = None,
        publication_types: Optional[List[str]] = None,
        study_designs: Optional[List[str]] = None,
        exclude_terms: Optional[List[str]] = None
    ) -> str:
        """
        Build a comprehensive PubMed query for clinical trial literature.
        
        Args:
            asset_names: List of drug/compound names
            indications: List of disease/indication terms
            trial_phases: List of trial phases to include
            date_range: Tuple of (start_date, end_date) in YYYY/MM/DD format
            publication_types: List of publication types to include
            study_designs: List of study design terms
            exclude_terms: Terms to exclude from results
            
        Returns:
            Formatted PubMed query string
        """
        query_parts = []
        
        # 1. Asset names (drugs/compounds)
        if asset_names:
            asset_query = self._build_asset_query(asset_names)
            query_parts.append(asset_query)
        
        # 2. Indications (diseases/conditions)
        if indications:
            indication_query = self._build_indication_query(indications)
            query_parts.append(indication_query)
        
        # 3. Clinical trial filters
        trial_query = self._build_trial_filter_query(
            trial_phases, publication_types, study_designs
        )
        query_parts.append(trial_query)
        
        # 4. Date range
        if date_range:
            date_query = self._build_date_query(date_range)
            query_parts.append(date_query)
        
        # 5. Combine all parts
        combined_query = " AND ".join(query_parts)
        
        # 6. Apply exclusions
        if exclude_terms:
            exclusion_query = self._build_exclusion_query(exclude_terms)
            combined_query = f"({combined_query}) NOT ({exclusion_query})"
        
        # 7. Validate and optimize
        final_query = self._optimize_query(combined_query)
        
        logger.info(f"Built PubMed query: {final_query[:200]}...")
        return final_query
    
    def _build_asset_query(self, asset_names: List[str]) -> str:
        """Build query part for asset names."""
        if not asset_names:
            return ""
        
        # Handle different asset name formats
        asset_terms = []
        for asset in asset_names:
            # Clean and normalize asset name
            clean_asset = self._clean_term(asset)
            
            # Handle common patterns
            if re.match(r'^[A-Z]{1,5}$', clean_asset):
                # Likely an acronym - search as exact term
                asset_terms.append(f'"{clean_asset}"')
            elif re.search(r'\s+', clean_asset):
                # Multi-word term - search as phrase
                asset_terms.append(f'"{clean_asset}"')
            else:
                # Single word - search as term
                asset_terms.append(clean_asset)
        
        # Combine with OR
        return f"({' OR '.join(asset_terms)})"
    
    def _build_indication_query(self, indications: List[str]) -> str:
        """Build query part for indications."""
        if not indications:
            return ""
        
        indication_terms = []
        for indication in indications:
            clean_indication = self._clean_term(indication)
            
            # Handle common indication patterns
            if re.search(r'\s+', clean_indication):
                # Multi-word indication - search as phrase
                indication_terms.append(f'"{clean_indication}"')
            else:
                # Single word - search as term
                indication_terms.append(clean_indication)
        
        # Combine with OR
        return f"({' OR '.join(indication_terms)})"
    
    def _build_trial_filter_query(
        self,
        trial_phases: Optional[List[str]],
        publication_types: Optional[List[str]],
        study_designs: Optional[List[str]]
    ) -> str:
        """Build query part for clinical trial filters."""
        filter_parts = []
        
        # Publication types
        if publication_types:
            pub_type_terms = [f'"{pt}"[ptyp]' for pt in publication_types]
            filter_parts.append(f"({' OR '.join(pub_type_terms)})")
        else:
            # Default to clinical trial publication types
            default_pub_types = [f'"{pt}"[ptyp]' for pt in self.PUBLICATION_TYPES[:4]]
            filter_parts.append(f"({' OR '.join(default_pub_types)})")
        
        # Study designs
        if study_designs:
            design_terms = [f'"{design}"[tiab]' for design in study_designs]
            filter_parts.append(f"({' OR '.join(design_terms)})")
        
        # Trial phases
        if trial_phases:
            phase_terms = []
            for phase in trial_phases:
                if phase.upper() in ['PHASE 1', 'PHASE I', '1', 'I']:
                    phase_terms.append('"Clinical Trial, Phase I"[ptyp]')
                elif phase.upper() in ['PHASE 2', 'PHASE II', '2', 'II']:
                    phase_terms.append('"Clinical Trial, Phase II"[ptyp]')
                elif phase.upper() in ['PHASE 3', 'PHASE III', '3', 'III']:
                    phase_terms.append('"Clinical Trial, Phase III"[ptyp]')
                elif phase.upper() in ['PHASE 4', 'PHASE IV', '4', 'IV']:
                    phase_terms.append('"Clinical Trial, Phase IV"[ptyp]')
                else:
                    # Generic phase search
                    phase_terms.append(f'"{phase}"[tiab]')
            
            if phase_terms:
                filter_parts.append(f"({' OR '.join(phase_terms)})")
        
        # Combine all filters with AND
        if filter_parts:
            return " AND ".join(filter_parts)
        else:
            return ""
    
    def _build_date_query(self, date_range: Tuple[str, str]) -> str:
        """Build query part for date range."""
        start_date, end_date = date_range
        
        # Validate date format
        if not re.match(r'^\d{4}/\d{2}/\d{2}$', start_date) or \
           not re.match(r'^\d{4}/\d{2}/\d{2}$', end_date):
            logger.warning(f"Invalid date format: {start_date} - {end_date}")
            return ""
        
        return f'"{start_date}"[dp] : "{end_date}"[dp]'
    
    def _build_exclusion_query(self, exclude_terms: List[str]) -> str:
        """Build query part for exclusion terms."""
        if not exclude_terms:
            return ""
        
        exclusion_terms = []
        for term in exclude_terms:
            clean_term = self._clean_term(term)
            if re.search(r'\s+', clean_term):
                exclusion_terms.append(f'"{clean_term}"')
            else:
                exclusion_terms.append(clean_term)
        
        return " OR ".join(exclusion_terms)
    
    def _clean_term(self, term: str) -> str:
        """Clean and normalize a search term."""
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', term.strip())
        
        # Handle special characters that might break PubMed queries
        cleaned = re.sub(r'[^\w\s\-]', '', cleaned)
        
        return cleaned
    
    def _optimize_query(self, query: str) -> str:
        """Optimize the query for better PubMed performance."""
        # Remove extra whitespace
        query = re.sub(r'\s+', ' ', query.strip())
        
        # Check query length
        if len(query) > self.max_query_length:
            logger.warning(f"Query too long ({len(query)} chars), truncating...")
            query = query[:self.max_query_length]
        
        # Count terms
        term_count = len(query.split())
        if term_count > self.max_terms:
            logger.warning(f"Query has too many terms ({term_count}), simplifying...")
            # Keep only essential parts
            query = self._simplify_query(query)
        
        return query
    
    def _simplify_query(self, query: str) -> str:
        """Simplify a complex query by keeping essential parts."""
        # Extract asset and indication parts (most important)
        asset_match = re.search(r'\([^)]*\)', query)
        if asset_match:
            return asset_match.group(0)
        
        # Fallback: take first 100 characters
        return query[:100]
    
    def build_phase_specific_query(
        self,
        asset_names: List[str],
        indications: List[str],
        phase: str,
        date_range: Optional[Tuple[str, str]] = None
    ) -> str:
        """
        Build a phase-specific query for clinical trials.
        
        Args:
            asset_names: List of drug/compound names
            indications: List of disease/indication terms
            phase: Specific trial phase
            date_range: Optional date range
            
        Returns:
            Phase-specific PubMed query
        """
        return self.build_trial_query(
            asset_names=asset_names,
            indications=indications,
            trial_phases=[phase],
            date_range=date_range,
            publication_types=[f"Clinical Trial, Phase {phase}"],
            study_designs=self.STUDY_DESIGNS
        )
    
    def build_safety_query(
        self,
        asset_names: List[str],
        indications: List[str],
        safety_terms: Optional[List[str]] = None
    ) -> str:
        """
        Build a query focused on safety and adverse events.
        
        Args:
            asset_names: List of drug/compound names
            indications: List of disease/indication terms
            safety_terms: Additional safety-related terms
            
        Returns:
            Safety-focused PubMed query
        """
        default_safety_terms = [
            "adverse event",
            "safety",
            "toxicity",
            "side effect",
            "adverse reaction",
            "tolerability"
        ]
        
        safety_terms = safety_terms or default_safety_terms
        
        # Build base query
        base_query = self.build_trial_query(
            asset_names=asset_names,
            indications=indications,
            publication_types=["Clinical Trial", "Case Report"]
        )
        
        # Add safety terms
        safety_query = self._build_safety_query_part(safety_terms)
        
        return f"({base_query}) AND ({safety_query})"
    
    def _build_safety_query_part(self, safety_terms: List[str]) -> str:
        """Build the safety-related part of a query."""
        safety_parts = []
        
        for term in safety_terms:
            clean_term = self._clean_term(term)
            if re.search(r'\s+', clean_term):
                safety_parts.append(f'"{clean_term}"[tiab]')
            else:
                safety_parts.append(f'{clean_term}[tiab]')
        
        return " OR ".join(safety_parts)
    
    def build_efficacy_query(
        self,
        asset_names: List[str],
        indications: List[str],
        efficacy_terms: Optional[List[str]] = None
    ) -> str:
        """
        Build a query focused on efficacy and outcomes.
        
        Args:
            asset_names: List of drug/compound names
            indications: List of disease/indication terms
            efficacy_terms: Additional efficacy-related terms
            
        Returns:
            Efficacy-focused PubMed query
        """
        default_efficacy_terms = [
            "efficacy",
            "effectiveness",
            "response rate",
            "survival",
            "progression-free survival",
            "overall survival",
            "remission",
            "cure"
        ]
        
        efficacy_terms = efficacy_terms or default_efficacy_terms
        
        # Build base query
        base_query = self.build_trial_query(
            asset_names=asset_names,
            indications=indications,
            publication_types=["Clinical Trial", "Randomized Controlled Trial"]
        )
        
        # Add efficacy terms
        efficacy_query = self._build_efficacy_query_part(efficacy_terms)
        
        return f"({base_query}) AND ({efficacy_query})"
    
    def _build_efficacy_query_part(self, efficacy_terms: List[str]) -> str:
        """Build the efficacy-related part of a query."""
        efficacy_parts = []
        
        for term in efficacy_terms:
            clean_term = self._clean_term(term)
            if re.search(r'\s+', clean_term):
                efficacy_parts.append(f'"{clean_term}"[tiab]')
            else:
                efficacy_parts.append(f'{clean_term}[tiab]')
        
        return " OR ".join(efficacy_parts)
    
    def validate_query(self, query: str) -> Tuple[bool, List[str]]:
        """
        Validate a PubMed query for potential issues.
        
        Args:
            query: PubMed query string to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Check query length
        if len(query) > self.max_query_length:
            issues.append(f"Query too long: {len(query)} characters (max: {self.max_query_length})")
        
        # Check for balanced parentheses
        if query.count('(') != query.count(')'):
            issues.append("Unbalanced parentheses")
        
        # Check for empty OR/AND clauses
        if re.search(r'\s+(OR|AND)\s+$', query) or re.search(r'^\s+(OR|AND)\s+', query):
            issues.append("Query starts or ends with OR/AND")
        
        # Check for double operators
        if re.search(r'\s+(OR|AND)\s+(OR|AND)\s+', query):
            issues.append("Double OR/AND operators")
        
        # Check for missing quotes around phrases
        if re.search(r'\w+\s+\w+', query) and not re.search(r'"[^"]+"', query):
            issues.append("Consider using quotes around multi-word terms")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def get_query_stats(self, query: str) -> Dict[str, any]:
        """
        Get statistics about a PubMed query.
        
        Args:
            query: PubMed query string
            
        Returns:
            Dictionary with query statistics
        """
        return {
            'length': len(query),
            'term_count': len(query.split()),
            'parentheses_count': query.count('('),
            'quote_count': query.count('"'),
            'and_count': query.count(' AND '),
            'or_count': query.count(' OR '),
            'not_count': query.count(' NOT '),
            'field_specifiers': len(re.findall(r'\[[^\]]+\]', query))
        }
