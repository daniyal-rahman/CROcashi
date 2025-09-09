"""
Trial-specific PubMed query builder.

Constructs boolean queries from asset aliases + indication terms + optional NCT,
with catalyst-window filters for recency bias.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple, Any
import re

from .query_builder import PubMedQueryBuilder

logger = logging.getLogger(__name__)


class TrialQueryBuilder:
    """Builds PubMed queries specific to individual trials."""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize trial query builder.
        
        Args:
            config: Configuration dictionary with query parameters
        """
        self.config = config or {}
        self.base_builder = PubMedQueryBuilder(config)
        
        # Catalyst window settings
        self.catalyst_window_months = self.config.get('catalyst_window_months', 18)
        self.recency_bias = self.config.get('recency_bias', True)
        
        # Query optimization settings
        self.max_asset_aliases = self.config.get('max_asset_aliases', 10)
        self.max_indication_terms = self.config.get('max_indication_terms', 15)
        self.max_query_length = self.config.get('max_query_length', 2000)
        self.include_basic_science = self.config.get('include_basic_science', True)
        
        # Trial-specific filters
        self.required_publication_types = [
            "Clinical Trial",
            "Randomized Controlled Trial", 
            "Controlled Clinical Trial",
            "Clinical Study"
        ]
        
        # Basic science publication types for mechanism-of-action papers
        self.basic_science_publication_types = [
            "Journal Article",
            "Research Support, Non-U.S. Gov't",
            "Research Support, U.S. Gov't, Non-P.H.S.",
            "Research Support, U.S. Gov't, P.H.S.",
            "Research Support, N.I.H., Extramural",
            "Research Support, N.I.H., Intramural",
            "Research Support, U.S. Gov't",
            "Comparative Study",
            "Evaluation Study",
            "Validation Study"
        ]
        
        self.optional_publication_types = [
            "Case Report",
            "Review",
            "Meta-Analysis",
            "Systematic Review"
        ]
    
    def build_trial_query(
        self,
        trial_id: str,
        asset_aliases: List[str],
        indication_terms: List[str],
        trial_nct: Optional[str] = None,
        trial_phase: Optional[str] = None,
        trial_design: Optional[str] = None,
        catalyst_date: Optional[datetime] = None,
        include_optional_types: bool = False,
        max_results: int = 1000
    ) -> Dict[str, Any]:
        """
        Build a comprehensive PubMed query for a specific trial.
        
        Args:
            trial_id: Unique trial identifier
            asset_aliases: List of asset names/aliases (INN, codes, etc.)
            indication_terms: List of disease/indication terms
            trial_nct: Optional NCT ID for exact matching
            trial_phase: Optional trial phase for filtering
            trial_design: Optional trial design for filtering
            catalyst_date: Optional catalyst date for recency bias
            include_optional_types: Whether to include optional publication types
            max_results: Maximum number of results to return
            
        Returns:
            Dictionary containing query string and metadata
        """
        try:
            # Validate inputs and get trimmed lists
            validated_assets, validated_indications = self._validate_trial_inputs(
                trial_id, asset_aliases, indication_terms
            )
            
            # Build core query components
            asset_query = self._build_asset_query_component(validated_assets)
            indication_query = self._build_indication_query_component(validated_indications)
            publication_query = self._build_publication_type_query(
                include_optional_types, 
                include_basic_science=self.include_basic_science
            )
            
            # Build trial-specific filters
            trial_filters = self._build_trial_filters(trial_phase, trial_design)
            
            # Build catalyst window query
            catalyst_query = self._build_catalyst_window_query(catalyst_date)
            
            # Combine all components
            combined_query = self._combine_query_components(
                asset_query, indication_query, publication_query, 
                trial_filters, catalyst_query
            )
            
            # Add NCT-specific boost if available
            if trial_nct:
                combined_query = self._add_nct_boost(combined_query, trial_nct)
            
            # Optimize and validate final query
            final_query = self._optimize_trial_query(combined_query)
            
            # Build query metadata
            query_metadata = self._build_query_metadata(
                trial_id, validated_assets, validated_indications, trial_nct,
                trial_phase, trial_design, catalyst_date, final_query
            )
            
            logger.info(f"Built trial query for {trial_id}: {len(final_query)} chars, "
                       f"{len(validated_assets)} assets, {len(validated_indications)} indications")
            
            return {
                'query_string': final_query,
                'metadata': query_metadata,
                'trial_id': trial_id,
                'max_results': max_results
            }
            
        except Exception as e:
            logger.error(f"Failed to build trial query for {trial_id}: {e}")
            raise
    
    def _validate_trial_inputs(
        self, 
        trial_id: str, 
        asset_aliases: List[str], 
        indication_terms: List[str]
    ) -> Tuple[List[str], List[str]]:
        """Validate trial query inputs and return trimmed lists."""
        if not trial_id or not trial_id.strip():
            raise ValueError("Trial ID is required")
        
        if not asset_aliases or not isinstance(asset_aliases, list):
            raise ValueError("Asset aliases must be a non-empty list")
        
        if not indication_terms or not isinstance(indication_terms, list):
            raise ValueError("Indication terms must be a non-empty list")
        
        # Check for reasonable limits and trim if necessary
        validated_assets = asset_aliases.copy()
        validated_indications = indication_terms.copy()
        
        if len(validated_assets) > self.max_asset_aliases:
            logger.warning(f"Too many asset aliases ({len(validated_assets)}), "
                          f"truncating to {self.max_asset_aliases}")
            validated_assets = validated_assets[:self.max_asset_aliases]
        
        if len(validated_indications) > self.max_indication_terms:
            logger.warning(f"Too many indication terms ({len(validated_indications)}), "
                          f"truncating to {self.max_indication_terms}")
            validated_indications = validated_indications[:self.max_indication_terms]
        
        return validated_assets, validated_indications
    
    def _build_asset_query_component(self, asset_aliases: List[str]) -> str:
        """Build the asset/compound query component."""
        if not asset_aliases:
            return ""
        
        # Clean and normalize asset aliases
        cleaned_aliases = []
        for alias in asset_aliases:
            cleaned = self._clean_asset_alias(alias)
            if cleaned:
                cleaned_aliases.append(cleaned)
        
        if not cleaned_aliases:
            return ""
        
        # Build asset query with OR logic and proper field tags
        asset_terms = []
        for alias in cleaned_aliases:
            # Handle different asset name patterns
            if self._is_acronym(alias):
                # Acronyms get exact matching with field tag
                asset_terms.append(f'"{alias}"[tiab]')
            elif ' ' in alias:
                # Multi-word terms get phrase matching with field tag
                asset_terms.append(f'"{alias}"[tiab]')
            else:
                # Single words get term matching with field tag
                asset_terms.append(f'{alias}[tiab]')
        
        # Combine with OR
        if len(asset_terms) == 1:
            return asset_terms[0]
        else:
            return f"({' OR '.join(asset_terms)})"
    
    def _expand_disease_term(self, term: str) -> List[str]:
        """Expand disease terms for better search coverage."""
        term_lower = term.lower().strip()
        
        # Common disease expansions
        expansions = {
            "alzheimer's disease": ["alzheimer's disease", "alzheimer disease", "alzheimer", "ad"],
            "alzheimer disease": ["alzheimer disease", "alzheimer's disease", "alzheimer", "ad"],
            "alzheimer": ["alzheimer", "alzheimer's disease", "alzheimer disease", "ad"],
            "parkinson's disease": ["parkinson's disease", "parkinson disease", "parkinson", "pd"],
            "parkinson disease": ["parkinson disease", "parkinson's disease", "parkinson", "pd"],
            "parkinson": ["parkinson", "parkinson's disease", "parkinson disease", "pd"],
            "multiple sclerosis": ["multiple sclerosis", "ms"],
            "amyotrophic lateral sclerosis": ["amyotrophic lateral sclerosis", "als", "lou gehrig"],
            "huntington's disease": ["huntington's disease", "huntington disease", "huntington"],
            "diabetes": ["diabetes", "diabetes mellitus", "dm"],
            "hypertension": ["hypertension", "high blood pressure", "htn"],
            "cancer": ["cancer", "carcinoma", "tumor", "tumour", "neoplasm"],
            "breast cancer": ["breast cancer", "breast carcinoma", "mammary cancer"],
            "lung cancer": ["lung cancer", "pulmonary cancer", "lung carcinoma"],
            "prostate cancer": ["prostate cancer", "prostatic cancer", "prostate carcinoma"]
        }
        
        # Return expanded terms if found, otherwise return original term
        return expansions.get(term_lower, [term])
    
    def _build_indication_query_component(self, indication_terms: List[str]) -> str:
        """Build the indication/disease query component."""
        if not indication_terms:
            return ""
        
        # Clean and normalize indication terms
        cleaned_terms = []
        for term in indication_terms:
            cleaned = self._clean_indication_term(term)
            if cleaned:
                cleaned_terms.append(cleaned)
        
        if not cleaned_terms:
            return ""
        
        # Build indication query with OR logic and proper field tags
        indication_queries = []
        for term in cleaned_terms:
            # Expand common disease terms for better coverage
            expanded_terms = self._expand_disease_term(term)
            
            for expanded_term in expanded_terms:
                if ' ' in expanded_term:
                    # Multi-word indications get phrase matching with field tag
                    indication_queries.append(f'"{expanded_term}"[tiab]')
                else:
                    # Single words get term matching with field tag
                    indication_queries.append(f'{expanded_term}[tiab]')
        
        # Combine with OR
        if len(indication_queries) == 1:
            return indication_queries[0]
        else:
            return f"({' OR '.join(indication_queries)})"
    
    def _build_publication_type_query(self, include_optional: bool = False, include_basic_science: bool = True) -> str:
        """Build publication type filter query."""
        pub_types = self.required_publication_types.copy()
        
        if include_optional:
            pub_types.extend(self.optional_publication_types)
            
        if include_basic_science:
            pub_types.extend(self.basic_science_publication_types)
        
        # Build publication type query with correct field tag [pt]
        pub_type_terms = [f'"{pt}"[pt]' for pt in pub_types]
        
        if len(pub_type_terms) == 1:
            return pub_type_terms[0]
        else:
            return f"({' OR '.join(pub_type_terms)})"
    
    def _build_trial_filters(
        self, 
        trial_phase: Optional[str], 
        trial_design: Optional[str]
    ) -> str:
        """Build trial-specific filters."""
        filters = []
        
        # Phase filter
        if trial_phase:
            phase_query = self._build_phase_filter(trial_phase)
            if phase_query:
                filters.append(phase_query)
        
        # Design filter
        if trial_design:
            design_query = self._build_design_filter(trial_design)
            if design_query:
                filters.append(design_query)
        
        return " AND ".join(filters) if filters else ""
    
    def _build_phase_filter(self, phase: str) -> str:
        """Build phase-specific filter."""
        phase_mappings = {
            'PHASE1': ['"Clinical Trial, Phase I"[pt]', 'phase 1[tiab]', 'phase I[tiab]'],
            'PHASE2': ['"Clinical Trial, Phase II"[pt]', 'phase 2[tiab]', 'phase II[tiab]'],
            'PHASE3': ['"Clinical Trial, Phase III"[pt]', 'phase 3[tiab]', 'phase III[tiab]'],
            'PHASE4': ['"Clinical Trial, Phase IV"[pt]', 'phase 4[tiab]', 'phase IV[tiab]']
        }
        
        phase_upper = phase.upper()
        if phase_upper in phase_mappings:
            terms = phase_mappings[phase_upper]
            return f"({' OR '.join(terms)})"
        
        # Generic phase search
        return f'"{phase}"[tiab]'
    
    def _build_design_filter(self, design: str) -> str:
        """Build design-specific filter."""
        design_mappings = {
            'RANDOMIZED': ['randomized[tiab]', 'randomised[tiab]'],
            'CONTROLLED': ['controlled[tiab]', 'control[tiab]'],
            'DOUBLE_BLIND': ['double-blind[tiab]', 'double blind[tiab]'],
            'SINGLE_BLIND': ['single-blind[tiab]', 'single blind[tiab]'],
            'PLACEBO_CONTROLLED': ['placebo-controlled[tiab]', 'placebo controlled[tiab]'],
            'OPEN_LABEL': ['open-label[tiab]', 'open label[tiab]']
        }
        
        design_upper = design.upper()
        if design_upper in design_mappings:
            terms = design_mappings[design_upper]
            return f"({' OR '.join(terms)})"
        
        # Generic design search
        return f'"{design}"[tiab]'
    
    def _build_catalyst_window_query(self, catalyst_date: Optional[datetime]) -> str:
        """Build catalyst window query for recency bias."""
        if not catalyst_date or not self.recency_bias:
            return ""
        
        try:
            # Calculate date range (±catalyst_window_months from catalyst date)
            start_date = catalyst_date - timedelta(days=30 * self.catalyst_window_months)
            end_date = catalyst_date + timedelta(days=30 * self.catalyst_window_months)
            
            # Format dates for PubMed
            start_str = start_date.strftime("%Y/%m/%d")
            end_str = end_date.strftime("%Y/%m/%d")
            
            # Build date range query
            date_query = f'"{start_str}"[dp] : "{end_str}"[dp]'
            
            logger.info(f"Built catalyst window query: {start_str} to {end_str}")
            return date_query
            
        except Exception as e:
            logger.warning(f"Failed to build catalyst window query: {e}")
            return ""
    
    def _combine_query_components(
        self,
        asset_query: str,
        indication_query: str,
        publication_query: str,
        trial_filters: str,
        catalyst_query: str
    ) -> str:
        """Combine all query components with AND logic."""
        components = []
        
        # Add required components
        if asset_query:
            components.append(asset_query)
        
        if indication_query:
            components.append(indication_query)
        
        if publication_query:
            components.append(publication_query)
        
        # Add optional components
        if trial_filters:
            components.append(trial_filters)
        
        if catalyst_query:
            components.append(catalyst_query)
        
        # Combine with AND
        if not components:
            return ""
        elif len(components) == 1:
            return components[0]
        else:
            return " AND ".join(components)
    
    def _add_nct_boost(self, base_query: str, nct_id: str) -> str:
        """Add NCT ID boost to the query."""
        if not nct_id or not nct_id.strip():
            return base_query
        
        # Clean NCT ID
        clean_nct = nct_id.strip().upper()
        
        # Add both specific NCT and general NCT pattern for broader matching
        # Use both [tiab] and [si] (Secondary Source ID) for better coverage
        specific_nct_query = f'"{clean_nct}"[tiab] OR "{clean_nct}"[si]'
        
        # Add general NCT pattern to catch any NCT ID
        general_nct_query = 'NCT[0-9]{8}[tiab] OR NCT[0-9]{8}[si]'
        
        # Combine specific NCT, general NCT pattern, and base query
        nct_query = f'{specific_nct_query} OR {general_nct_query}'
        
        # Combine with OR for broader matching
        return f"({base_query}) OR ({nct_query})"
    
    def _optimize_trial_query(self, query: str) -> str:
        """Optimize the trial query for better performance."""
        if not query:
            return query
        
        # Remove extra whitespace
        optimized = ' '.join(query.split())
        
        # Check query length and trim safely if needed
        if len(optimized) > self.max_query_length:
            logger.warning(f"Query too long ({len(optimized)} chars), trimming safely...")
            optimized = self._safe_trim_query(optimized)
        
        # Validate query structure
        is_valid, issues = self.base_builder.validate_query(optimized)
        if not is_valid:
            logger.warning(f"Query validation issues: {issues}")
            # Try to fix common issues
            optimized = self._fix_query_issues(optimized, issues)
        
        return optimized
    
    def _safe_trim_query(self, query: str) -> str:
        """Safely trim query by dropping lowest-priority components."""
        # Priority order for trimming (lowest priority first)
        trim_priorities = [
            # Lowest priority - optional design terms
            r'\s+AND\s+"[^"]*"[tiab]',  # Design terms like "randomized[tiab]"
            # Medium priority - extra aliases (keep first few)
            r'\s+OR\s+"[^"]*"[tiab]',   # Extra asset/indication aliases
            # Higher priority - catalyst window
            r'\s+AND\s+"\d{4}/\d{2}/\d{2}"\[dp\]\s*:\s*"\d{4}/\d{2}/\d{2}"\[dp\]',
        ]
        
        trimmed_query = query
        for pattern in trim_priorities:
            if len(trimmed_query) <= self.max_query_length:
                break
            
            # Find and remove the last occurrence of this pattern
            matches = list(re.finditer(pattern, trimmed_query))
            if matches:
                last_match = matches[-1]
                start, end = last_match.span()
                
                # Ensure we don't break the query structure
                if start > 0 and trimmed_query[start-1] == '(':
                    # Find matching closing parenthesis
                    paren_count = 1
                    for i in range(start-1, -1, -1):
                        if trimmed_query[i] == '(':
                            paren_count -= 1
                        elif trimmed_query[i] == ')':
                            paren_count += 1
                        if paren_count == 0:
                            # Remove the entire parenthesized group
                            trimmed_query = trimmed_query[:i] + trimmed_query[end:]
                            break
                else:
                    # Remove just the pattern
                    trimmed_query = trimmed_query[:start] + trimmed_query[end:]
                
                # Clean up any dangling operators
                trimmed_query = re.sub(r'\s+(AND|OR)\s*$', '', trimmed_query)
                trimmed_query = re.sub(r'^\s*(AND|OR)\s+', '', trimmed_query)
        
        # Final safety check - if still too long, truncate at word boundary
        if len(trimmed_query) > self.max_query_length:
            # Find last complete word before max length
            last_space = trimmed_query.rfind(' ', 0, self.max_query_length)
            if last_space > 0:
                trimmed_query = trimmed_query[:last_space]
            else:
                # Fallback to hard truncation
                trimmed_query = trimmed_query[:self.max_query_length]
        
        return trimmed_query
    
    def _fix_query_issues(self, query: str, issues: List[str]) -> str:
        """Attempt to fix common query issues."""
        fixed_query = query
        
        # Fix unbalanced parentheses
        if "Unbalanced parentheses" in issues:
            open_count = query.count('(')
            close_count = query.count(')')
            if open_count > close_count:
                fixed_query = query + ')' * (open_count - close_count)
            elif close_count > open_count:
                fixed_query = '(' * (close_count - open_count) + query
        
        # Fix trailing operators
        if "Query starts or ends with OR/AND" in issues:
            fixed_query = fixed_query.strip()
            if fixed_query.startswith(('AND ', 'OR ')):
                fixed_query = fixed_query[4:]
            if fixed_query.endswith((' AND', ' OR')):
                fixed_query = fixed_query[:-4]
        
        return fixed_query
    
    def _build_query_metadata(
        self,
        trial_id: str,
        asset_aliases: List[str],
        indication_terms: List[str],
        trial_nct: Optional[str],
        trial_phase: Optional[str],
        trial_design: Optional[str],
        catalyst_date: Optional[datetime],
        final_query: str
    ) -> Dict[str, Any]:
        """Build comprehensive query metadata."""
        return {
            'trial_id': trial_id,
            'asset_aliases': asset_aliases,
            'indication_terms': indication_terms,
            'trial_nct': trial_nct,
            'trial_phase': trial_phase,
            'trial_design': trial_design,
            'catalyst_date': catalyst_date.isoformat() if catalyst_date else None,
            'catalyst_window_months': self.catalyst_window_months,
            'query_length': len(final_query),
            'query_components': {
                'has_assets': bool(asset_aliases),
                'has_indications': bool(indication_terms),
                'has_nct': bool(trial_nct),
                'has_phase': bool(trial_phase),
                'has_design': bool(trial_design),
                'has_catalyst_window': bool(catalyst_date)
            },
            'built_at': datetime.now(timezone.utc).isoformat()
        }
    
    def _clean_asset_alias(self, alias: str) -> str:
        """Clean and normalize asset alias."""
        if not alias or not isinstance(alias, str):
            return ""
        
        # Remove extra whitespace and normalize
        cleaned = ' '.join(alias.strip().split())
        
        # Remove common drug suffixes that might interfere
        suffixes_to_remove = [
            'hydrochloride', 'hcl', 'sulfate', 'citrate', 'phosphate',
            'acetate', 'sodium', 'potassium', 'tablet', 'capsule'
        ]
        
        for suffix in suffixes_to_remove:
            if cleaned.lower().endswith(f' {suffix}'):
                cleaned = cleaned[:-len(suffix)].strip()
                break
        
        return cleaned
    
    def _clean_indication_term(self, term: str) -> str:
        """Clean and normalize indication term without destructive modifications."""
        if not term or not isinstance(term, str):
            return ""
        
        # Remove extra whitespace and normalize
        cleaned = ' '.join(term.strip().split())
        
        # Don't remove clinically important modifiers
        # Instead, consider adding OR expansions for broader matching
        # This preserves terms like "metastatic", "refractory", "relapsed"
        
        return cleaned
    
    def _is_acronym(self, text: str) -> bool:
        """Check if text is likely an acronym."""
        if not text:
            return False
        
        # Acronyms are typically 2-6 uppercase letters
        if len(text) <= 6 and text.isupper() and text.isalpha():
            return True
        
        # Check for common acronym patterns
        if re.match(r'^[A-Z]{2,6}$', text):
            return True
        
        return False
    
    def get_trial_query_stats(self, query_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Get statistics about a trial query."""
        return {
            'trial_id': query_metadata.get('trial_id'),
            'query_length': query_metadata.get('query_length', 0),
            'component_count': sum(query_metadata.get('query_components', {}).values()),
            'asset_count': len(query_metadata.get('asset_aliases', [])),
            'indication_count': len(query_metadata.get('indication_terms', [])),
            'has_catalyst_window': query_metadata.get('query_components', {}).get('has_catalyst_window', False),
            'catalyst_window_months': query_metadata.get('catalyst_window_months')
        }
