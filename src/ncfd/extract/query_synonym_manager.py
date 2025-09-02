"""
Query Synonym Manager

Handles disease- and endpoint-specific query synonyms for flexible and
configurable query generation.
"""

from typing import Dict, List, Any, Optional
import yaml
from pathlib import Path
from .section_normalizer import NormalizedSection, section_normalizer


class QuerySynonymManager:
    """Manages disease- and endpoint-specific query synonyms."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize with query synonyms configuration."""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "query_synonyms.yaml"
        
        self.config_path = Path(config_path)
        self.synonyms = self._load_synonyms()
    
    def _load_synonyms(self) -> Dict[str, Any]:
        """Load query synonyms from configuration file."""
        if not self.config_path.exists():
            return self._get_default_synonyms()
        
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load query synonyms from {self.config_path}: {e}")
            return self._get_default_synonyms()
    
    def _get_default_synonyms(self) -> Dict[str, Any]:
        """Get default synonyms if config file is not available."""
        return {
            "disease_synonyms": {
                "ovarian_cancer": {
                    "primary_terms": ["ovarian cancer", "ovarian carcinoma", "EOC"],
                    "response_terms": ["CA-125 response", "CA125 response"],
                    "survival_terms": ["PFS", "TTP", "OS"]
                }
            },
            "endpoint_synonyms": {
                "primary_endpoint": {
                    "response_rate": ["primary endpoint", "ORR", "response rate"],
                    "survival": ["primary endpoint", "PFS", "OS", "TTP"]
                }
            },
            "method_synonyms": {
                "survival_analysis": {
                    "kaplan_meier": ["Kaplan-Meier", "KM", "survival analysis"],
                    "log_rank": ["log-rank test", "log rank test"]
                }
            }
        }
    
    def get_disease_synonyms(self, disease: str, category: str) -> List[str]:
        """Get disease-specific synonyms for a category."""
        disease_lower = disease.lower().replace(" ", "_")
        synonyms = self.synonyms.get("disease_synonyms", {})
        
        if disease_lower in synonyms:
            return synonyms[disease_lower].get(category, [])
        
        # Try partial matching
        for disease_key, disease_syns in synonyms.items():
            if disease_lower in disease_key or disease_key in disease_lower:
                return disease_syns.get(category, [])
        
        return []
    
    def get_endpoint_synonyms(self, endpoint_type: str, category: str) -> List[str]:
        """Get endpoint-specific synonyms for a category."""
        synonyms = self.synonyms.get("endpoint_synonyms", {})
        return synonyms.get(endpoint_type, {}).get(category, [])
    
    def get_method_synonyms(self, method_type: str, category: str) -> List[str]:
        """Get method-specific synonyms for a category."""
        synonyms = self.synonyms.get("method_synonyms", {})
        return synonyms.get(method_type, {}).get(category, [])
    
    def get_field_synonyms(self, field_type: str, category: str) -> List[str]:
        """Get field-specific synonyms for a category."""
        synonyms = self.synonyms.get("field_synonyms", {})
        return synonyms.get(field_type, {}).get(category, [])
    
    def get_must_hit_synonyms(self, field: str) -> List[str]:
        """Get must-hit synonyms for a critical field."""
        must_hit_synonyms = self.synonyms.get("must_hit", {})
        return must_hit_synonyms.get(field, [])
    
    def get_all_must_hit_synonyms(self) -> Dict[str, List[str]]:
        """Get all must-hit synonyms."""
        return self.synonyms.get("must_hit", {})
    
    def expand_query(self, base_query: str, disease: Optional[str] = None, 
                    endpoint_type: Optional[str] = None) -> List[str]:
        """Expand a base query with disease and endpoint synonyms."""
        queries = [base_query]
        
        if disease:
            # Add disease-specific terms
            disease_terms = self.get_disease_synonyms(disease, "primary_terms")
            for term in disease_terms:
                queries.append(f"{term} {base_query}")
                queries.append(f"{base_query} {term}")
        
        if endpoint_type:
            # Add endpoint-specific terms
            endpoint_terms = self.get_endpoint_synonyms(endpoint_type, "response_rate")
            for term in endpoint_terms:
                queries.append(f"{base_query} {term}")
        
        return list(set(queries))  # Remove duplicates
    
    def create_field_queries(self, required_fields: List[str], 
                           trial_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create field-specific queries with synonyms."""
        queries = []
        disease = trial_context.get("disease", "").lower()
        endpoint_type = trial_context.get("endpoint_type", "primary_endpoint")
        
        for field in required_fields:
            field_queries = self._create_queries_for_field(
                field, disease, endpoint_type, trial_context
            )
            queries.extend(field_queries)
        
        return queries
    
    def _create_queries_for_field(self, field: str, disease: str, 
                                endpoint_type: str, trial_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create queries for a specific field."""
        queries = []
        
        # Field-specific query generation
        if field == "endpoints":
            base_queries = [
                "primary endpoint response rate",
                "secondary endpoint progression survival"
            ]
            for base_query in base_queries:
                expanded_queries = self.expand_query(base_query, disease, endpoint_type)
                for query_text in expanded_queries:
                    queries.append({
                        "field_name": f"endpoints_{len(queries)}",
                        "query_text": query_text,
                        "section": NormalizedSection.METHODS,
                        "priority": 1,
                        "must_fill": True
                    })
        
        elif field == "survival_method":
            kaplan_synonyms = self.get_method_synonyms("survival_analysis", "kaplan_meier")
            logrank_synonyms = self.get_method_synonyms("survival_analysis", "log_rank")
            
            for synonym in kaplan_synonyms:
                queries.append({
                    "field_name": "kaplan_meier",
                    "query_text": f"{synonym} survival analysis",
                    "section": NormalizedSection.METHODS,
                    "priority": 1,
                    "must_fill": True
                })
            
            for synonym in logrank_synonyms:
                queries.append({
                    "field_name": "log_rank",
                    "query_text": f"{synonym} Cox regression",
                    "section": NormalizedSection.METHODS,
                    "priority": 1,
                    "must_fill": False
                })
        
        elif field == "design_archetype":
            gehan_synonyms = self.get_method_synonyms("statistical_design", "gehan_design")
            interim_synonyms = self.get_method_synonyms("statistical_design", "interim_analysis")
            
            for synonym in gehan_synonyms:
                queries.append({
                    "field_name": "gehan_design",
                    "query_text": f"{synonym} design",
                    "section": NormalizedSection.METHODS,
                    "priority": 1,
                    "must_fill": True
                })
            
            for synonym in interim_synonyms:
                queries.append({
                    "field_name": "interim_looks",
                    "query_text": f"{synonym} stopping rules",
                    "section": NormalizedSection.METHODS,
                    "priority": 1,
                    "must_fill": False
                })
        
        elif field == "response_breakdown":
            response_synonyms = self.get_field_synonyms("endpoints", "response")
            for synonym in response_synonyms:
                queries.append({
                    "field_name": "orr_recist",
                    "query_text": f"overall {synonym} RECIST",
                    "section": NormalizedSection.RESULTS,
                    "priority": 1,
                    "must_fill": True
                })
                
                queries.append({
                    "field_name": "response_breakdown",
                    "query_text": f"complete partial stable progressive disease {synonym}",
                    "section": NormalizedSection.RESULTS,
                    "priority": 1,
                    "must_fill": False
                })
        
        elif field == "survival_medians":
            survival_synonyms = self.get_field_synonyms("endpoints", "survival")
            for synonym in survival_synonyms:
                queries.append({
                    "field_name": "median_os",
                    "query_text": f"median overall survival {synonym}",
                    "section": NormalizedSection.RESULTS,
                    "priority": 1,
                    "must_fill": True
                })
                
                queries.append({
                    "field_name": "median_pfs",
                    "query_text": f"median progression free survival {synonym}",
                    "section": NormalizedSection.RESULTS,
                    "priority": 1,
                    "must_fill": True
                })
        
        return queries


# Global instance for easy access
query_synonym_manager = QuerySynonymManager()
