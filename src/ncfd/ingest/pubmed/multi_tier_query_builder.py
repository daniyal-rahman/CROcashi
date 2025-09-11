"""
Multi-tier query builder for PubMed retrieval.

Implements the three-tier query system (A, B, C, D) with union + dedupe
as specified in the retrieval specification.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from ...entities.schema import EntityPack

logger = logging.getLogger(__name__)


@dataclass
class QueryTier:
    """Represents a query tier with metadata."""
    tier_type: str  # A, B, C, D
    query_string: str
    priority: int
    description: str
    expected_coverage: str  # high_precision, trial_focus, mechanism_aware, nct_backfill


@dataclass
class QueryResult:
    """Result from multi-tier query execution."""
    tier_type: str
    query_string: str
    pmids: List[str]
    total_count: int
    execution_time: float
    success: bool
    error_message: Optional[str] = None


class MultiTierQueryBuilder:
    """Builds multi-tier queries for PubMed retrieval."""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize multi-tier query builder.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.max_query_length = self.config.get('max_query_length', 2000)
        
        logger.info("Initialized multi-tier query builder")
    
    def build_all_queries(self, entity_pack: EntityPack) -> List[QueryTier]:
        """
        Build all query tiers (A, B, C, D) for an entity pack.
        
        Args:
            entity_pack: Entity pack to build queries for
            
        Returns:
            List of query tiers
        """
        queries = []
        
        try:
            # Query A: High-precision (drug/company + disease)
            query_a = self._build_query_a(entity_pack)
            if query_a:
                queries.append(QueryTier(
                    tier_type='A',
                    query_string=query_a,
                    priority=1,
                    description='High-precision: drug/company + disease',
                    expected_coverage='high_precision'
                ))
            
            # Query B: Trial-type focus
            query_b = self._build_query_b(entity_pack)
            if query_b:
                queries.append(QueryTier(
                    tier_type='B',
                    query_string=query_b,
                    priority=2,
                    description='Trial-type focus: drug + trial terms + disease',
                    expected_coverage='trial_focus'
                ))
            
            # Query C: Mechanism-aware but guarded
            query_c = self._build_query_c(entity_pack)
            if query_c:
                queries.append(QueryTier(
                    tier_type='C',
                    query_string=query_c,
                    priority=3,
                    description='Mechanism-aware: mechanism + drug/company + disease',
                    expected_coverage='mechanism_aware'
                ))
            
            # Query D: NCT-linked backfill
            query_d = self._build_query_d(entity_pack)
            if query_d:
                queries.append(QueryTier(
                    tier_type='D',
                    query_string=query_d,
                    priority=4,
                    description='NCT-linked backfill: registry-linked publications',
                    expected_coverage='nct_backfill'
                ))
            
            # Query E: Sponsor affiliation backfill (optional)
            query_e = self._build_query_e(entity_pack)
            if query_e:
                queries.append(QueryTier(
                    tier_type='E',
                    query_string=query_e,
                    priority=5,
                    description='Sponsor affiliation: company affiliation + drug',
                    expected_coverage='sponsor_affiliation'
                ))
            
            # Query F: Author-based search (optional) - COMMENTED OUT FOR TESTING
            # query_f = self._build_query_f(entity_pack)
            # if query_f:
            #     queries.append(QueryTier(
            #         tier_type='F',
            #         query_string=query_f,
            #         priority=6,
            #         description='Author-based: key researchers + drug/mechanism',
            #         expected_coverage='author_based'
            #     ))
            
            logger.info(f"Built {len(queries)} query tiers for entity pack {entity_pack.entity_id}")
            return queries
            
        except Exception as e:
            logger.error(f"Error building queries for entity pack {entity_pack.entity_id}: {e}")
            return []
    
    def _build_query_a(self, entity_pack: EntityPack) -> Optional[str]:
        """
        Build Query A: High-precision (drug/company + disease).
        
        Args:
            entity_pack: Entity pack
            
        Returns:
            Query string or None if invalid
        """
        try:
            # Get drug and company terms
            drug_terms = entity_pack.get_all_asset_terms()
            company_terms = entity_pack.get_all_company_terms()
            drug_company_terms = drug_terms + company_terms
            
            # Get disease terms
            disease_terms = entity_pack.get_all_indication_terms()
            
            if not drug_company_terms or not disease_terms:
                logger.warning("Missing required terms for Query A")
                return None
            
            # Build drug/company TIAB clause
            drug_company_tiab = self._build_tiab_clause(drug_company_terms)
            
            # Build disease clause (MeSH + TIAB with truncation)
            disease_mesh = self._build_mesh_clause(disease_terms[:1])  # Primary only for MeSH
            disease_tiab = self._build_disease_clause(disease_terms)
            
            query = f"""(
  {drug_company_tiab}
) AND (
  {disease_mesh} OR {disease_tiab}
)"""
            
            return self._validate_query(query)
            
        except Exception as e:
            logger.error(f"Error building Query A: {e}")
            return None
    
    def _build_query_b(self, entity_pack: EntityPack) -> Optional[str]:
        """
        Build Query B: Trial-type focus.
        
        Args:
            entity_pack: Entity pack
            
        Returns:
            Query string or None if invalid
        """
        try:
            # Get drug terms
            drug_terms = entity_pack.get_all_asset_terms()
            disease_terms = entity_pack.get_all_indication_terms()
            
            if not drug_terms or not disease_terms:
                logger.warning("Missing required terms for Query B")
                return None
            
            # Build drug TIAB clause
            drug_tiab = self._build_tiab_clause(drug_terms)
            
            # Build trial terms
            trial_terms = [
                "randomized controlled trial[pt]", 
                "clinical trial[pt]", 
                "trial[tiab]", 
                "placebo[tiab]"
            ]
            trial_clause = " OR ".join(trial_terms)
            
            # Build disease clause (MeSH + TIAB with truncation)
            disease_mesh = self._build_mesh_clause(disease_terms[:1])
            disease_tiab = self._build_disease_clause(disease_terms)
            
            query = f"""(
  {drug_tiab}
) AND (
  {trial_clause}
) AND (
  {disease_mesh} OR {disease_tiab}
)"""
            
            return self._validate_query(query)
            
        except Exception as e:
            logger.error(f"Error building Query B: {e}")
            return None
    
    def _build_query_c(self, entity_pack: EntityPack) -> Optional[str]:
        """
        Build Query C: Mechanism-aware but guarded.
        
        Args:
            entity_pack: Entity pack
            
        Returns:
            Query string or None if invalid
        """
        try:
            # Get mechanism terms (null-safe)
            mechanism_terms = list(getattr(getattr(entity_pack, "mechanism", None), "targets", []) or [])
            drug_terms = entity_pack.get_all_asset_terms()
            company_terms = entity_pack.get_all_company_terms()
            disease_terms = entity_pack.get_all_indication_terms()
            
            if not mechanism_terms or not drug_terms or not disease_terms:
                logger.warning("Missing required terms for Query C")
                return None
            
            # Build mechanism TIAB clause
            mechanism_tiab = self._build_tiab_clause(mechanism_terms)
            
            # Build drug/company TIAB clause
            drug_company_tiab = self._build_tiab_clause(drug_terms + company_terms)
            
            # Build disease clause (MeSH + TIAB with truncation)
            disease_mesh = self._build_mesh_clause(disease_terms[:1])
            disease_tiab = self._build_disease_clause(disease_terms)
            
            query = f"""(
  {mechanism_tiab}
) AND (
  {drug_company_tiab}
) AND (
  {disease_mesh} OR {disease_tiab}
)"""
            
            return self._validate_query(query)
            
        except Exception as e:
            logger.error(f"Error building Query C: {e}")
            return None
    
    def _build_query_d(self, entity_pack: EntityPack) -> Optional[str]:
        """
        Build Query D: NCT-linked backfill.
        
        Args:
            entity_pack: Entity pack
            
        Returns:
            Query string or None if invalid
        """
        try:
            nct_ids = list(getattr(getattr(entity_pack, "registries", None), "nct_ids", []) or [])
            
            if not nct_ids:
                logger.warning("No NCT IDs available for Query D")
                return None
            
            # Build NCT SI clause
            nct_clauses = [f"{nct_id}[si]" for nct_id in nct_ids]
            query = " OR ".join(nct_clauses)
            
            return self._validate_query(query)
            
        except Exception as e:
            logger.error(f"Error building Query D: {e}")
            return None
    
    def _build_query_e(self, entity_pack: EntityPack) -> Optional[str]:
        """
        Build Query E: Sponsor affiliation backfill.
        
        Args:
            entity_pack: Entity pack
            
        Returns:
            Query string or None if invalid
        """
        try:
            company_terms = entity_pack.get_all_company_terms()
            drug_terms = entity_pack.get_all_asset_terms()
            
            if not company_terms or not drug_terms:
                logger.warning("Missing required terms for Query E")
                return None
            
            # Build company affiliation clause
            company_ad_clauses = [f'"{company}"[ad]' for company in company_terms]
            company_ad_clause = " OR ".join(company_ad_clauses)
            
            # Build drug TIAB clause
            drug_tiab = self._build_tiab_clause(drug_terms)
            
            query = f"""(
  {company_ad_clause}
) AND (
  {drug_tiab}
)"""
            
            return self._validate_query(query)
            
        except Exception as e:
            logger.error(f"Error building Query E: {e}")
            return None
    
    def _build_query_f(self, entity_pack: EntityPack) -> Optional[str]:
        """
        Build Query F: Author-based search.
        
        Args:
            entity_pack: Entity pack
            
        Returns:
            Query string or None if invalid
        """
        try:
            # Get author terms
            author_terms = entity_pack.get_all_author_terms()
            if not author_terms:
                return None
            
            # Get drug and mechanism terms (null-safe)
            drug_terms = entity_pack.get_all_asset_terms()
            mechanism_terms = list(getattr(getattr(entity_pack, "mechanism", None), "targets", []) or [])
            
            # Build author clause
            author_clause = self._build_author_clause(author_terms)
            
            # Build drug/mechanism clause
            drug_mechanism_terms = drug_terms + mechanism_terms
            drug_mechanism_tiab = self._build_tiab_clause(drug_mechanism_terms)
            
            query = f"""(
  {author_clause}
) AND (
  {drug_mechanism_tiab}
)"""
            
            return self._validate_query(query)
            
        except Exception as e:
            logger.error(f"Error building Query F: {e}")
            return None
    
    def _build_author_clause(self, author_terms: List[str]) -> str:
        """
        Build author clause from terms.
        
        Args:
            author_terms: List of author names
            
        Returns:
            Author clause string
        """
        if not author_terms:
            return ""
        
        # Collect all unique author variants
        unique_variants = set()
        for term in author_terms:
            # Add original term
            unique_variants.add(term)
            
            # Add case variants
            if term.lower() != term:
                unique_variants.add(term.lower())
            if term.upper() != term:
                unique_variants.add(term.upper())
            
            # Handle common author name variations
            if ' ' in term:
                # Split name and create variations
                parts = term.split()
                if len(parts) >= 2:
                    # Last name, First initial
                    last_first = f"{parts[-1]} {parts[0][0]}"
                    unique_variants.add(last_first)
                    # Last name, First name
                    last_full = f"{parts[-1]} {parts[0]}"
                    unique_variants.add(last_full)
        
        # Build author clauses for unique variants
        author_clauses = [f'"{variant}"[au]' for variant in sorted(unique_variants)]
        return " OR ".join(author_clauses)
    
    def _build_tiab_clause(self, terms: List[str]) -> str:
        """
        Build TIAB clause from terms with smart quoting to preserve PubMed's ATM.
        
        Args:
            terms: List of terms
            
        Returns:
            TIAB clause string
        """
        if not terms:
            return ""
        
        # Collect all unique variants
        unique_variants = set()
        for term in terms:
            # Normalize punctuation first
            normalized_term = self._normalize_punctuation(term)
            unique_variants.add(normalized_term)
            
            # Add case variants (capitalize first letter)
            if normalized_term.lower() == normalized_term:
                unique_variants.add(normalized_term.capitalize())
            
            # Handle hyphen/space variants
            if '-' in normalized_term:
                space_variant = normalized_term.replace('-', ' ')
                unique_variants.add(space_variant)
                # Also add capitalized version
                unique_variants.add(space_variant.capitalize())
            elif ' ' in normalized_term:
                hyphen_variant = normalized_term.replace(' ', '-')
                unique_variants.add(hyphen_variant)
                # Also add capitalized version
                unique_variants.add(hyphen_variant.capitalize())
            
            # Add apostrophe/no-apostrophe variants for disease terms
            if "'" in normalized_term:
                # Add variant without apostrophe
                no_apostrophe = normalized_term.replace("'", "")
                if no_apostrophe != normalized_term:
                    unique_variants.add(no_apostrophe)
            elif normalized_term.endswith("s") and len(normalized_term) > 3:
                # Add variant with apostrophe for words ending in 's'
                with_apostrophe = normalized_term[:-1] + "'s"
                if with_apostrophe != normalized_term:
                    unique_variants.add(with_apostrophe)
        
        # Build TIAB clauses with smart quoting
        tiab_clauses = []
        for variant in sorted(unique_variants):
            if self._should_quote_term(variant):
                tiab_clauses.append(f'"{variant}"[tiab]')
            else:
                tiab_clauses.append(f'{variant}[tiab]')
        
        return " OR ".join(tiab_clauses)
    
    def _normalize_punctuation(self, term: str) -> str:
        """
        Normalize punctuation in terms to ASCII equivalents.
        
        Args:
            term: Input term
            
        Returns:
            Normalized term
        """
        # Replace curly quotes with straight quotes
        term = term.replace("'", "'").replace("'", "'")
        term = term.replace(""", '"').replace(""", '"')
        
        # Replace en/em dashes with hyphens
        term = term.replace("–", "-").replace("—", "-")
        
        # Replace non-breaking spaces
        term = term.replace("\u00A0", " ")
        
        return term
    
    def _should_quote_term(self, term: str) -> bool:
        """
        Determine if a term should be quoted in PubMed query.
        
        Args:
            term: Term to check
            
        Returns:
            True if term should be quoted
        """
        # Don't quote single words (preserve ATM)
        if ' ' not in term:
            return False
        
        # Quote multi-word phrases
        return True
    
    def _build_disease_clause(self, terms: List[str]) -> str:
        """
        Build disease clause with truncation and smart quoting for better recall.
        
        Args:
            terms: List of disease terms
            
        Returns:
            Disease clause string
        """
        if not terms:
            return ""
        
        # Collect all unique variants
        unique_variants = set()
        for term in terms:
            # Normalize punctuation first
            normalized_term = self._normalize_punctuation(term)
            unique_variants.add(normalized_term)
            
            # Add case variants
            if normalized_term.lower() == normalized_term:
                unique_variants.add(normalized_term.capitalize())
            
            # Add apostrophe/no-apostrophe variants
            if "'" in normalized_term:
                # Add variant without apostrophe
                no_apostrophe = normalized_term.replace("'", "")
                if no_apostrophe != normalized_term:
                    unique_variants.add(no_apostrophe)
            elif normalized_term.endswith("s") and len(normalized_term) > 3:
                # Add variant with apostrophe for words ending in 's'
                with_apostrophe = normalized_term[:-1] + "'s"
                if with_apostrophe != normalized_term:
                    unique_variants.add(with_apostrophe)
        
        # Build disease clauses with smart quoting and truncation
        disease_clauses = []
        for variant in sorted(unique_variants):
            # For single words, use truncation (no quotes to preserve ATM)
            if ' ' not in variant:
                disease_clauses.append(f'{variant}*[tiab]')
            else:
                # For multi-word phrases, quote them
                disease_clauses.append(f'"{variant}"[tiab]')
        
        return " OR ".join(disease_clauses)
    
    def _build_mesh_clause(self, terms: List[str]) -> str:
        """
        Build MeSH clause from terms.
        
        Args:
            terms: List of terms
            
        Returns:
            MeSH clause string
        """
        if not terms:
            return ""
        
        # MeSH terms should not be quoted to preserve ATM
        mesh_clauses = [f'{term}[mh]' for term in terms]
        return " OR ".join(mesh_clauses)
    
    def _validate_query(self, query: str) -> Optional[str]:
        """
        Validate query string.
        
        Args:
            query: Query string to validate
            
        Returns:
            Validated query or None if invalid
        """
        if not query or not query.strip():
            return None
        
        # Check query length
        if len(query) > self.max_query_length:
            logger.warning(f"Query too long ({len(query)} chars), truncating...")
            query = query[:self.max_query_length]
        
        # Check for balanced parentheses
        if query.count('(') != query.count(')'):
            logger.warning("Unbalanced parentheses in query")
            return None
        
        return query.strip()


class QueryUnion:
    """Handles union and deduplication of query results."""
    
    def __init__(self):
        """Initialize query union processor."""
        self.logger = logging.getLogger(__name__)
    
    def union_results(self, query_results: List[QueryResult]) -> Tuple[List[str], Dict[str, Any]]:
        """
        Union results from multiple queries and deduplicate.
        
        Args:
            query_results: List of query results
            
        Returns:
            Tuple of (deduplicated_pmids, union_stats)
        """
        try:
            all_pmids = []
            union_stats = {
                'total_queries': len(query_results),
                'successful_queries': 0,
                'failed_queries': 0,
                'total_pmids_before_dedup': 0,
                'total_pmids_after_dedup': 0,
                'query_breakdown': {}
            }
            
            # Collect PMIDs from all successful queries
            for result in query_results:
                if result.success:
                    all_pmids.extend(result.pmids)
                    union_stats['successful_queries'] += 1
                    union_stats['query_breakdown'][result.tier_type] = {
                        'pmids_count': len(result.pmids),
                        'total_count': result.total_count,
                        'execution_time': result.execution_time
                    }
                else:
                    union_stats['failed_queries'] += 1
                    union_stats['query_breakdown'][result.tier_type] = {
                        'error': result.error_message
                    }
            
            # Deduplicate PMIDs
            unique_pmids = list(set(all_pmids))
            
            union_stats['total_pmids_before_dedup'] = len(all_pmids)
            union_stats['total_pmids_after_dedup'] = len(unique_pmids)
            
            self.logger.info(f"Union results: {len(all_pmids)} total PMIDs, "
                           f"{len(unique_pmids)} unique PMIDs from {union_stats['successful_queries']} queries")
            
            return unique_pmids, union_stats
            
        except Exception as e:
            self.logger.error(f"Error unioning query results: {e}")
            return [], {'error': str(e)}


class QueryDeduplicator:
    """Handles deduplication of query results."""
    
    def __init__(self):
        """Initialize query deduplicator."""
        self.logger = logging.getLogger(__name__)
    
    def deduplicate_pmids(self, pmids: List[str]) -> Tuple[List[str], Dict[str, Any]]:
        """
        Deduplicate PMIDs while preserving order.
        
        Args:
            pmids: List of PMIDs
            
        Returns:
            Tuple of (deduplicated_pmids, dedup_stats)
        """
        try:
            seen = set()
            deduplicated = []
            dedup_stats = {
                'original_count': len(pmids),
                'duplicate_count': 0,
                'final_count': 0
            }
            
            for pmid in pmids:
                if pmid not in seen:
                    seen.add(pmid)
                    deduplicated.append(pmid)
                else:
                    dedup_stats['duplicate_count'] += 1
            
            dedup_stats['final_count'] = len(deduplicated)
            
            self.logger.info(f"Deduplication: {dedup_stats['original_count']} original, "
                           f"{dedup_stats['duplicate_count']} duplicates, "
                           f"{dedup_stats['final_count']} final")
            
            return deduplicated, dedup_stats
            
        except Exception as e:
            self.logger.error(f"Error deduplicating PMIDs: {e}")
            return pmids, {'error': str(e)}
