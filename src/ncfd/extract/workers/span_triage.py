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
    section: Optional[str] = None
    priority: int = 1  # Higher priority = more important
    must_fill: bool = False
    metric_family: Optional[str] = None


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
                
                # Build indices if not already built
                if not self.indexer.bm25_index:
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
        """Generate default queries for common required fields."""
        default_queries = []
        
        # Methods section queries
        if "endpoints" in required_fields:
            default_queries.extend([
                TriageQuery("endpoints_primary", "primary endpoint response rate", "Methods", 1, True),
                TriageQuery("endpoints_secondary", "secondary endpoint progression survival", "Methods", 1, True)
            ])
        
        if "ascertainment" in required_fields:
            default_queries.extend([
                TriageQuery("recist_criteria", "RECIST criteria response assessment", "Methods", 1, True),
                TriageQuery("assessment_interval", "assessment interval every cycles", "Methods", 1, False)
            ])
        
        if "survival_method" in required_fields:
            default_queries.extend([
                TriageQuery("kaplan_meier", "Kaplan-Meier survival analysis", "Methods", 1, True),
                TriageQuery("log_rank", "log-rank test Cox regression", "Methods", 1, False)
            ])
        
        if "design_archetype" in required_fields:
            default_queries.extend([
                TriageQuery("gehan_design", "Gehan two-stage design", "Methods", 1, True),
                TriageQuery("interim_looks", "interim analysis stopping rules", "Methods", 1, True)
            ])
        
        if "analysis_denominators" in required_fields:
            default_queries.extend([
                TriageQuery("response_n", "evaluable for response patients", "Methods", 1, True),
                TriageQuery("ttp_os_n", "TTP OS analysis included patients", "Methods", 1, True)
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
            default_queries.extend([
                TriageQuery("median_ttp", "median time to progression", "Results", 1, True),
                TriageQuery("median_os", "median overall survival", "Results", 1, True)
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
            
            # Check coverage
            coverage = {}
            for field in required_fields:
                must_hit_spans = triage_result.output.get("must_hit_spans", {})
                selected_spans = triage_result.output.get("selected_spans", {})
                
                field_spans = must_hit_spans.get(field, []) + selected_spans.get(field, [])
                coverage[field] = {
                    "spans_found": len(field_spans),
                    "adequate": len(field_spans) > 0
                }
            
            return {
                "doc_id": doc_id,
                "coverage": coverage,
                "overall_adequate": all(cov["adequate"] for cov in coverage.values()),
                "total_spans": triage_result.output["total_spans_selected"]
            }
            
        except Exception as e:
            return {"error": str(e)}
