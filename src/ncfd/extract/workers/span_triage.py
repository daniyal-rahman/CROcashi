"""
Span Triage Worker

Implements budgeted selection of BaseSpans/DerivedSpans for LLM processing.
"""

from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from collections import defaultdict

from ..workers.base_worker import BaseWorker, WorkerResult
from ...db.models import BaseSpan, DerivedSpan, Document
from ...db.session import get_session
from .span_indexer import SpanIndexer


@dataclass
class TriageConfig:
    """Configuration for span triage."""
    # Budgets per section
    methods_budget: int = 12
    results_budget: int = 12
    tables_budget: int = 5
    
    # Top-up settings
    topup_per_field: int = 3
    max_topup_attempts: int = 1
    
    # Retrieval settings
    use_bm25: bool = True
    use_dense: bool = True
    min_similarity_threshold: float = 0.3
    
    # Must-hit slots (reserved for critical fields)
    must_hit_slots: Dict[str, int] = None
    
    def __post_init__(self):
        if self.must_hit_slots is None:
            self.must_hit_slots = {
                "statistics_km": 2,
                "endpoints_recist": 2,
                "design_archetype": 2,
                "response_breakdown": 2,
                "survival_medians": 2
            }


@dataclass
class TriageQuery:
    """A query for span triage."""
    field_name: str
    query_text: str
    section: Optional[str] = None  # Normalized section string ("Methods"|"Results"|"Table")
    priority: int = 1  # Higher priority = more important
    must_fill: bool = False
    metric_family: Optional[str] = None
    
    def __post_init__(self):
        """Post-initialization to normalize section if needed."""
        from ..section_normalizer import section_normalizer
        
        if isinstance(self.section, str):
            # Normalize string section to canonical form
            normalized = section_normalizer.normalize_section(self.section)
            # Convert back to string using the primary section name
            self.section = section_normalizer.get_primary_section_name(normalized)
        elif self.section is None:
            # Default to "Methods" section (string)
            self.section = "Methods"


class SpanTriageWorker(BaseWorker):
    """Worker for budgeted span selection and triage."""
    
    def __init__(self, config: Optional[TriageConfig] = None):
        super().__init__(name="SpanTriageWorker", version="1.0.0")
        self.config = config or TriageConfig()
        self.indexer = SpanIndexer()
        
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Perform span triage for a document."""
        doc_id = inputs.get("doc_id")
        queries = inputs.get("queries", [])
        required_fields = inputs.get("required_fields", [])
        
        if not doc_id:
            return WorkerResult(
                success=False,
                output=None,
                error_message="doc_id is required"
            )
        
        try:
            with get_session() as session:
                # Get document
                document = session.query(Document).filter(Document.doc_id == doc_id).first()
                if not document:
                    return WorkerResult(
                        success=False,
                        output=None,
                        error_message=f"Document {doc_id} not found"
                    )
                
                # Build indices if not already built for this document
                if getattr(self.indexer, "_indexed_doc_id", None) != doc_id:
                    self.indexer.process({"doc_id": doc_id})
                
                # Generate default queries if none provided
                if not queries:
                    queries = self._generate_default_queries(required_fields)
                
                # Perform triage
                triage_result = self._perform_triage(session, doc_id, queries)
                
                return WorkerResult(
                    success=True,
                    output=triage_result,
                    metadata={
                        "doc_id": doc_id,
                        "queries_processed": len(queries),
                        "config": self.config.__dict__
                    }
                )
                
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error performing span triage for document {doc_id}: {str(e)}"
            )
    
    def _generate_default_queries(self, required_fields: List[str]) -> List[TriageQuery]:
        """Generate default queries for common required fields using expanded synonyms."""
        from ..query_synonym_manager import query_synonym_manager
        
        default_queries = []
        
        # Methods section queries
        if "endpoints" in required_fields:
            default_queries.extend([
                TriageQuery("endpoints_primary", "primary endpoint response rate", "Methods", 1, True),
                TriageQuery("endpoints_secondary", "secondary endpoint progression survival", "Methods", 1, True)
            ])
        
        if "ascertainment" in required_fields:
            # Use expanded RECIST synonyms
            recist_synonyms = query_synonym_manager.get_must_hit_synonyms("recist")
            recist_query = " ".join(recist_synonyms) if recist_synonyms else "RECIST criteria response assessment"
            
            default_queries.extend([
                TriageQuery("recist_criteria", recist_query, "Methods", 1, True),
                TriageQuery("assessment_interval", "assessment interval every cycles", "Methods", 1, False)
            ])
        
        if "survival_method" in required_fields:
            # Use expanded KM and Cox synonyms
            km_synonyms = query_synonym_manager.get_must_hit_synonyms("km")
            cox_synonyms = query_synonym_manager.get_must_hit_synonyms("cox")
            
            km_query = " ".join(km_synonyms) if km_synonyms else "Kaplan-Meier survival analysis"
            cox_query = " ".join(cox_synonyms) if cox_synonyms else "log-rank test Cox regression"
            
            default_queries.extend([
                TriageQuery("kaplan_meier", km_query, "Methods", 1, True),
                TriageQuery("log_rank", cox_query, "Methods", 1, False)
            ])
        
        if "design_archetype" in required_fields:
            # Use expanded Gehan synonyms
            gehan_synonyms = query_synonym_manager.get_must_hit_synonyms("gehan")
            gehan_query = " ".join(gehan_synonyms) if gehan_synonyms else "Gehan two-stage design"
            
            default_queries.extend([
                TriageQuery("gehan_design", gehan_query, "Methods", 1, True),
                TriageQuery("interim_looks", "interim analysis stopping rules", "Methods", 1, True)
            ])
        
        if "analysis_denominators" in required_fields:
            # Use expanded TTP/OS synonyms
            ttp_synonyms = query_synonym_manager.get_must_hit_synonyms("ttp")
            os_synonyms = query_synonym_manager.get_must_hit_synonyms("os")
            
            ttp_os_query = " ".join(ttp_synonyms + os_synonyms) if ttp_synonyms and os_synonyms else "TTP OS analysis included patients"
            
            default_queries.extend([
                TriageQuery("response_n", "evaluable for response patients", "Methods", 1, True),
                TriageQuery("ttp_os_n", ttp_os_query, "Methods", 1, True)
            ])
        
        if "site_geography" in required_fields:
            default_queries.extend([
                TriageQuery("num_sites", "number of sites centers", "Methods", 1, False),
                TriageQuery("regions", "geographic regions countries", "Methods", 1, False)
            ])
        
        # Results section queries
        if "response_breakdown" in required_fields:
            default_queries.extend([
                TriageQuery("orr_recist", "overall response rate RECIST", "Results", 1, True),
                TriageQuery("ca125_response", "CA-125 response rate", "Results", 1, True)
            ])
        
        if "survival_medians" in required_fields:
            # Use expanded TTP/OS synonyms for median queries
            ttp_synonyms = query_synonym_manager.get_must_hit_synonyms("ttp")
            os_synonyms = query_synonym_manager.get_must_hit_synonyms("os")
            
            median_ttp_query = "median " + " ".join(ttp_synonyms) if ttp_synonyms else "median time to progression"
            median_os_query = "median " + " ".join(os_synonyms) if os_synonyms else "median overall survival"
            
            default_queries.extend([
                TriageQuery("median_ttp", median_ttp_query, "Results", 1, True),
                TriageQuery("median_os", median_os_query, "Results", 1, True)
            ])
        
        # Table queries
        if "tables" in required_fields:
            default_queries.extend([
                TriageQuery("response_table", "response rate table", "Table", 1, False),
                TriageQuery("survival_table", "survival analysis table", "Table", 1, False)
            ])
        
        return default_queries
    
    def _perform_triage(self, session, doc_id: int, queries: List[TriageQuery]) -> Dict[str, Any]:
        """Perform the actual span triage."""
        # Initialize budgets
        budgets = {
            "Methods": self.config.methods_budget,
            "Results": self.config.results_budget,
            "Table": self.config.tables_budget
        }
        
        # Track selected spans
        selected_spans = defaultdict(list)
        must_hit_spans = defaultdict(list)
        
        # FIXED: Initialize must-fill fields upfront to ensure top-up runs for empty fields
        must_fill_field_names = {query.field_name for query in queries if query.must_fill}
        for field_name in must_fill_field_names:
            must_hit_spans[field_name] = []  # Initialize with empty list
        
        # First pass: process all queries
        for query in queries:
            section = query.section or self._infer_section(query.field_name)
            
            # Check if we have budget for this section
            if budgets[section] <= 0:
                continue
            
            # Search for relevant spans
            search_results = self.indexer.search(
                query=query.query_text,
                section=section,
                top_k=min(5, budgets[section]),
                use_bm25=self.config.use_bm25,
                use_dense=self.config.use_dense
            )
            
            # Select spans based on priority and budget
            selected = self._select_spans_for_query(
                search_results, query, budgets, section
            )
            
            if selected:
                if query.must_fill:
                    must_hit_spans[query.field_name].extend(selected)
                else:
                    selected_spans[query.field_name].extend(selected)
        
        # Second pass: top-up for must-fill fields that are empty
        topup_results = self._perform_topup(session, doc_id, must_hit_spans, budgets)
        
        # Final result
        return {
            "selected_spans": dict(selected_spans),
            "must_hit_spans": dict(must_hit_spans),
            "topup_results": topup_results,
            "budget_remaining": budgets,
            "total_spans_selected": sum(len(spans) for spans in selected_spans.values()) + 
                                   sum(len(spans) for spans in must_hit_spans.values())
        }
    
    def _select_spans_for_query(self, search_results: List[Dict], query: TriageQuery, 
                               budgets: Dict[str, int], section: str) -> List[int]:
        """Select spans for a specific query within budget constraints."""
        selected = []
        available_budget = budgets[section]
        
        # Sort by combined score
        sorted_results = sorted(search_results, key=lambda x: x['combined_score'], reverse=True)
        
        for result in sorted_results:
            if len(selected) >= available_budget:
                break
            
            span_id = result['span_id']
            
            # Check if span is already selected
            if not self._is_span_already_selected(span_id, selected, section):
                selected.append(span_id)
                budgets[section] -= 1
        
        return selected
    
    def _is_span_already_selected(self, span_id: int, selected_spans: List[int], section: str) -> bool:
        """Check if a span is already selected (avoid duplicates)."""
        return span_id in selected_spans
    
    def _perform_topup(self, session, doc_id: int, must_hit_spans: Dict[str, List], 
                       budgets: Dict[str, int]) -> Dict[str, Any]:
        """Perform top-up for must-fill fields that are empty."""
        topup_results = {}
        
        for field_name, spans in must_hit_spans.items():
            if not spans:  # Field is empty, need top-up
                # Determine section for this field
                section = self._infer_section(field_name)
                
                if budgets[section] >= self.config.topup_per_field:
                    # Generate additional queries for this field
                    topup_queries = self._generate_topup_queries(field_name)
                    
                    for query in topup_queries:
                        if budgets[section] <= 0:
                            break
                        
                        # Search with broader terms
                        search_results = self.indexer.search(
                            query=query.query_text,
                            section=section,
                            top_k=self.config.topup_per_field,
                            use_bm25=self.config.use_bm25,
                            use_dense=self.config.use_dense
                        )
                        
                        # Select additional spans
                        additional_spans = self._select_spans_for_query(
                            search_results, query, budgets, section
                        )
                        
                        if additional_spans:
                            must_hit_spans[field_name].extend(additional_spans)
                            topup_results[field_name] = {
                                "spans_added": len(additional_spans),
                                "queries_used": [q.query_text for q in topup_queries]
                            }
                            break
        
        return topup_results
    
    def _build_parent_children_mapping(self, required_fields: List[str]) -> Dict[str, List[str]]:
        """Build mapping from parent field names to their child query field names."""
        parent_to_children = {}
        
        for field in required_fields:
            if field == "endpoints":
                parent_to_children[field] = ["endpoints_primary", "endpoints_secondary"]
            elif field == "ascertainment":
                parent_to_children[field] = ["recist_criteria", "assessment_interval"]
            elif field == "survival_method":
                parent_to_children[field] = ["kaplan_meier", "log_rank"]
            elif field == "design_archetype":
                parent_to_children[field] = ["gehan_design", "interim_looks"]
            elif field == "analysis_denominators":
                parent_to_children[field] = ["itt_population", "pp_population"]
            elif field == "response_breakdown":
                parent_to_children[field] = ["orr_recist", "response_breakdown"]
            elif field == "survival_medians":
                parent_to_children[field] = ["median_os", "median_pfs"]
            elif field == "safety_summary":
                parent_to_children[field] = ["ae_summary", "grade_breakdown"]
            elif field == "table_processing":
                parent_to_children[field] = ["survival_table", "response_table"]
            else:
                # For fields without children, use the field name itself
                parent_to_children[field] = [field]
        
        return parent_to_children
    
    def _generate_topup_queries(self, field_name: str) -> List[TriageQuery]:
        """Generate additional queries for top-up attempts."""
        topup_queries = []
        
        if "endpoints" in field_name:
            topup_queries.extend([
                TriageQuery(f"{field_name}_topup1", "endpoint objective", "Methods", 2, True),
                TriageQuery(f"{field_name}_topup2", "primary outcome measure", "Methods", 2, True)
            ])
        elif "survival" in field_name:
            topup_queries.extend([
                TriageQuery(f"{field_name}_topup1", "survival analysis method", "Methods", 2, True),
                TriageQuery(f"{field_name}_topup2", "time to event", "Methods", 2, True)
            ])
        elif "design" in field_name:
            topup_queries.extend([
                TriageQuery(f"{field_name}_topup1", "study design phase", "Methods", 2, True),
                TriageQuery(f"{field_name}_topup2", "trial design", "Methods", 2, True)
            ])
        else:
            # Generic top-up
            topup_queries.append(
                TriageQuery(f"{field_name}_topup", field_name.replace("_", " "), None, 2, True)
            )
        
        return topup_queries
    
    def _infer_section(self, field_name: str) -> str:
        """Infer the most likely section for a field."""
        field_lower = field_name.lower()
        
        if any(keyword in field_lower for keyword in [
            "endpoint", "design", "method", "protocol", "statistic", "analysis"
        ]):
            return "Methods"
        elif any(keyword in field_lower for keyword in [
            "response", "survival", "outcome", "efficacy", "result"
        ]):
            return "Results"
        elif "table" in field_lower:
            return "Table"
        else:
            return "Methods"  # Default to Methods
    
    def get_triage_summary(self, doc_id: int) -> Dict[str, Any]:
        """Get a summary of triage results for a document."""
        try:
            with get_session() as session:
                # Count spans by section
                base_spans = session.query(BaseSpan).filter(BaseSpan.doc_id == doc_id).all()
                derived_spans = session.query(DerivedSpan).filter(DerivedSpan.doc_id == doc_id).all()
                
                section_counts = defaultdict(int)
                for span in base_spans:
                    section_counts[span.section] += 1
                
                return {
                    "doc_id": doc_id,
                    "base_spans": len(base_spans),
                    "derived_spans": len(derived_spans),
                    "section_distribution": dict(section_counts),
                    "total_spans": len(base_spans) + len(derived_spans)
                }
                
        except Exception as e:
            return {"error": str(e)}
    
    def validate_triage_coverage(self, doc_id: int, required_fields: List[str]) -> Dict[str, Any]:
        """Validate that triage provides adequate coverage for required fields."""
        try:
            # Perform triage
            triage_result = self.process({
                "doc_id": doc_id,
                "required_fields": required_fields
            })
            
            if not triage_result.success:
                return {"error": triage_result.error_message}
            
            # FIXED: Create parent→children mapping for coverage calculation
            parent_to_children = self._build_parent_children_mapping(required_fields)
            
            # Check coverage
            coverage = {}
            must_hit_spans = triage_result.output.get("must_hit_spans", {})
            selected_spans = triage_result.output.get("selected_spans", {})
            
            for field in required_fields:
                # Get all child field names for this parent field
                child_fields = parent_to_children.get(field, [field])  # Fallback to field itself if no children
                
                # Sum spans across all child fields
                total_spans = []
                for child_field in child_fields:
                    child_must_hit = must_hit_spans.get(child_field, [])
                    child_selected = selected_spans.get(child_field, [])
                    total_spans.extend(child_must_hit + child_selected)
                
                coverage[field] = {
                    "spans_found": len(total_spans),
                    "adequate": len(total_spans) > 0,
                    "child_fields": child_fields,
                    "child_coverage": {child: len(must_hit_spans.get(child, []) + selected_spans.get(child, [])) 
                                     for child in child_fields}
                }
            
            return {
                "doc_id": doc_id,
                "coverage": coverage,
                "overall_adequate": all(cov["adequate"] for cov in coverage.values()),
                "total_spans": triage_result.output["total_spans_selected"]
            }
            
        except Exception as e:
            return {"error": str(e)}
