"""
PubMed query template engine for generating search queries from entity packs.
"""

import logging
from typing import List, Optional
from ...entities.schema import EntityPack

logger = logging.getLogger(__name__)


class PubMedQueryTemplates:
    """Generates PubMed query variants from entity packs."""
    
    def __init__(self):
        """Initialize query template engine."""
        pass
    
    def build_query_variants(self, pack: EntityPack) -> List[str]:
        """
        Build all query variants for an entity pack.
        
        Args:
            pack: Entity pack to build queries for
            
        Returns:
            List of query strings
        """
        drug_terms = pack.get_all_asset_terms()
        company_terms = pack.get_all_company_terms()
        disease_terms = pack.get_all_indication_terms()
        nct_ids = pack.registries.nct_ids
        mechanism_terms = pack.mechanism.targets
        
        queries = []
        
        # Query A: High-precision (drug/company + disease)
        query_a = self._build_query_a(drug_terms, company_terms, disease_terms)
        if query_a:
            queries.append(query_a)
        
        # Query B: Trial-type focus
        query_b = self._build_query_b(drug_terms, disease_terms)
        if query_b:
            queries.append(query_b)
        
        # Query C: Mechanism-aware but guarded
        if mechanism_terms:
            query_c = self._build_query_c(mechanism_terms, drug_terms, company_terms, disease_terms)
            if query_c:
                queries.append(query_c)
        
        # Query D: NCT-linked backfill
        if nct_ids:
            query_d = self._build_query_d(nct_ids)
            if query_d:
                queries.append(query_d)
        
        # Query E: Sponsor affiliation backfill
        if company_terms:
            query_e = self._build_query_e(company_terms, drug_terms)
            if query_e:
                queries.append(query_e)
        
        logger.info(f"Generated {len(queries)} query variants for {pack.entity_id}")
        return queries
    
    def _build_query_a(self, drug_terms: List[str], company_terms: List[str], disease_terms: List[str]) -> str:
        """High-precision query: drug/company + disease."""
        drug_company_tiab = self._build_tiab_clause(drug_terms + company_terms)
        disease_mesh = self._build_mesh_clause(disease_terms[:1])  # Primary only for MeSH
        disease_tiab = self._build_tiab_clause(disease_terms)
        
        return f"""(
      {drug_company_tiab}
    ) AND (
      {disease_mesh} OR {disease_tiab}
    )"""
    
    def _build_query_b(self, drug_terms: List[str], disease_terms: List[str]) -> str:
        """Trial-type focus query."""
        drug_tiab = self._build_tiab_clause(drug_terms)
        trial_terms = [
            "randomized controlled trial[pt]", 
            "clinical trial[pt]", 
            "trial[tiab]", 
            "placebo[tiab]"
        ]
        disease_mesh = self._build_mesh_clause(disease_terms[:1])
        disease_tiab = self._build_tiab_clause(disease_terms)
        
        return f"""(
      {drug_tiab}
    ) AND (
      {' OR '.join(trial_terms)}
    ) AND (
      {disease_mesh} OR {disease_tiab}
    )"""
    
    def _build_query_c(self, mechanism_terms: List[str], drug_terms: List[str], 
                      company_terms: List[str], disease_terms: List[str]) -> str:
        """Mechanism-aware but guarded query."""
        mechanism_tiab = self._build_tiab_clause(mechanism_terms)
        drug_company_tiab = self._build_tiab_clause(drug_terms + company_terms)
        disease_mesh = self._build_mesh_clause(disease_terms[:1])
        disease_tiab = self._build_tiab_clause(disease_terms)
        
        return f"""(
      {mechanism_tiab}
    ) AND (
      {drug_company_tiab}
    ) AND (
      {disease_mesh} OR {disease_tiab}
    )"""
    
    def _build_query_d(self, nct_ids: List[str]) -> str:
        """NCT-linked backfill query."""
        return " OR ".join(f"{nct}[si]" for nct in nct_ids)
    
    def _build_query_e(self, company_terms: List[str], drug_terms: List[str]) -> str:
        """Sponsor affiliation backfill query."""
        company_ad = " OR ".join(f'"{term}"[ad]' for term in company_terms)
        drug_tiab = self._build_tiab_clause(drug_terms)
        
        return f"""(
      {company_ad}
    ) AND (
      {drug_tiab}
    )"""
    
    def _build_tiab_clause(self, terms: List[str]) -> str:
        """Build title/abstract clause."""
        if not terms:
            return ""
        
        clauses = []
        for term in terms:
            if ' ' in term:
                # Multi-word terms get phrase matching
                clauses.append(f'"{term}"[tiab]')
            else:
                # Single words get term matching
                clauses.append(f"{term}[tiab]")
        
        return " OR ".join(clauses)
    
    def _build_mesh_clause(self, terms: List[str]) -> str:
        """Build MeSH clause."""
        if not terms:
            return ""
        
        return " OR ".join(f'"{term}"[mh]' for term in terms)
    
    def build_simple_query(self, pack: EntityPack) -> str:
        """
        Build a simple query combining all terms.
        
        Args:
            pack: Entity pack to build query for
            
        Returns:
            Simple query string
        """
        all_terms = (pack.get_all_asset_terms() + 
                    pack.get_all_company_terms() + 
                    pack.get_all_indication_terms())
        
        return self._build_tiab_clause(all_terms)
    
    def build_mechanism_only_query(self, pack: EntityPack) -> str:
        """
        Build a query using only mechanism terms (for testing).
        
        Args:
            pack: Entity pack to build query for
            
        Returns:
            Mechanism-only query string
        """
        if not pack.mechanism.targets:
            return ""
        
        return self._build_tiab_clause(pack.mechanism.targets)
    
    def validate_query(self, query: str) -> bool:
        """
        Validate a query string.
        
        Args:
            query: Query string to validate
            
        Returns:
            True if query is valid, False otherwise
        """
        if not query or not query.strip():
            return False
        
        # Check for balanced parentheses
        if query.count('(') != query.count(')'):
            logger.warning("Unbalanced parentheses in query")
            return False
        
        # Check for basic structure
        if 'AND' not in query and 'OR' not in query:
            logger.warning("Query lacks boolean operators")
            return False
        
        return True
    
    def get_query_stats(self, queries: List[str]) -> dict:
        """
        Get statistics about generated queries.
        
        Args:
            queries: List of query strings
            
        Returns:
            Dictionary with query statistics
        """
        if not queries:
            return {"count": 0, "total_length": 0, "avg_length": 0}
        
        total_length = sum(len(q) for q in queries)
        avg_length = total_length / len(queries)
        
        return {
            "count": len(queries),
            "total_length": total_length,
            "avg_length": avg_length,
            "max_length": max(len(q) for q in queries),
            "min_length": min(len(q) for q in queries)
        }
