# src/ncfd/extract/workers/denominator_resolver.py
"""
Denominator Resolver

Scans Methods/Results/Table spans for patterns to determine analysis denominators.
Writes to MethodCard.analysis_denominators and attaches correct n to ResultsFactsheet rows.
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from collections import defaultdict

from ..workers.base_worker import BaseWorker, WorkerResult
from ...db.models import BaseSpan, Document
from ...db.session import get_session
from ..normalization.metric_registry import get_metric_registry
from .interfaces.denominator_resolver import IDenominatorResolver, DenominatorResult


@dataclass
class DenominatorPattern:
    """A pattern for extracting denominator information."""
    name: str
    pattern: str
    metric_family: str
    confidence: float
    section: str
    examples: List[str] = None
    
    def __post_init__(self):
        if self.examples is None:
            self.examples = []


@dataclass
class ResolvedDenominator:
    """A resolved denominator with its source and confidence."""
    n: int
    metric_family: str
    source_text: str
    span_id: int
    confidence: float
    section: str
    pattern_used: str


class DenominatorResolver(BaseWorker, IDenominatorResolver):
    """Worker for resolving analysis denominators from document spans."""
    
    def __init__(self):
        super().__init__(name="DenominatorResolver", version="1.0.0")
        self.metric_registry = get_metric_registry()
        self.denominator_patterns = self._initialize_patterns()
        
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Resolve denominators for a document."""
        doc_id = inputs.get("doc_id")
        if not doc_id:
            return WorkerResult(
                success=False,
                output=None,
                error_message="doc_id is required"
            )
        
        try:
            with get_session() as session:
                # Get document and its spans
                document = session.query(Document).filter(Document.doc_id == doc_id).first()
                if not document:
                    return WorkerResult(
                        success=False,
                        output=None,
                        error_message=f"Document {doc_id} not found"
                    )
                
                # Get all spans for the document
                spans = session.query(BaseSpan).filter(BaseSpan.doc_id == doc_id).all()
                
                # Resolve denominators
                resolved_denominators = self._resolve_denominators(spans)
                
                # Group by metric family
                grouped_denominators = self._group_denominators(resolved_denominators)
                
                # Resolve ambiguities
                final_denominators = self._resolve_ambiguities(grouped_denominators)
                
                # Convert to standardized format
                standardized_result = self._convert_to_standard_format(final_denominators)
                
                return WorkerResult(
                    success=True,
                    output={
                        "denominators": standardized_result,
                        "processed_spans": len(spans),
                        "extracted_denominators": standardized_result.count_extracted_denominators(),
                        "metadata": {
                            "doc_id": doc_id,
                            "patterns_used": [p.name for p in self.denominator_patterns],
                            "total_patterns_found": len(resolved_denominators),
                            "metric_families_covered": list(final_denominators.keys()),
                            "ambiguity_resolution": self._get_ambiguity_summary(grouped_denominators, final_denominators)
                        }
                    }
                )
                
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error resolving denominators for document {doc_id}: {str(e)}"
            )
    
    def _initialize_patterns(self) -> List[DenominatorPattern]:
        """Initialize denominator extraction patterns."""
        patterns = [
            # Fraction patterns (highest confidence for exact matches)
            DenominatorPattern(
                name="fraction_denominator",
                pattern=r"\b(\d+)\s*/\s*(\d+)\b",
                metric_family="response",
                confidence=0.98,
                section="Results",
                examples=["3/19", "4/19", "15/25"]
            ),
            
            # Response rate patterns with fractions
            DenominatorPattern(
                name="response_rate_fraction",
                pattern=r"response\s+(?:rate|was)\s+\d+(?:\.\d+)?\s*%.*\(\s*\d+\s*/\s*(\d+)\s*\)",
                metric_family="response",
                confidence=0.95,
                section="Results",
                examples=["response rate was 15.8% (3/19)", "response was 21.1% (4/19)"]
            ),
            
            # CA-125 specific patterns
            DenominatorPattern(
                name="ca125_fraction",
                pattern=r"CA-?125.*\(\s*\d+\s*/\s*(\d+)\s*\)",
                metric_family="response",
                confidence=0.95,
                section="Results",
                examples=["CA-125 response rate was 21.1% (4/19)"]
            ),
            
            # TTP/OS analysis patterns
            DenominatorPattern(
                name="ttp_os_analysis",
                pattern=r"(?:TTP|OS|time[-\s]to[-\s]progression|overall\s+survival)\s+(?:analysis|evaluation)\s+(?:included|analyzed)\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="survival",
                confidence=0.9,
                section="Methods",
                examples=["TTP and OS analysis included 22 patients", "OS analysis included n=22"]
            ),
            
            # TTP/OS top-up query patterns
            DenominatorPattern(
                name="ttp_os_topup",
                pattern=r"(?:TTP|OS|time[-\s]to[-\s]event)\s+(?:and\s+OS\s+)?analysis\s+(?:included|evaluated|analyzed)\s+(\d+)\s+patients",
                metric_family="survival",
                confidence=0.85,
                section="Methods",
                examples=["TTP and OS analysis included 22 patients", "time-to-event analysis included 22 patients"]
            ),
            
            # Response evaluation patterns
            DenominatorPattern(
                name="response_evaluable",
                pattern=r"evaluable\s+for\s+response\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="response",
                confidence=0.95,
                section="Methods",
                examples=["evaluable for response (n=19)", "evaluable for response n=19"]
            ),
            
            DenominatorPattern(
                name="response_assessment",
                pattern=r"response\s+assessment\s+(?:included|evaluated|analyzed)\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="response",
                confidence=0.9,
                section="Methods",
                examples=["response assessment included n=19", "response assessment evaluated (n=19)"]
            ),
            
            # Survival analysis patterns
            DenominatorPattern(
                name="survival_ttp_os",
                pattern=r"(?:TTP|OS|time[-\s]to[-\s]progression|overall\s+survival)\s+(?:analysis|evaluation)\s+(?:included|analyzed)\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="survival",
                confidence=0.9,
                section="Methods",
                examples=["TTP and OS analysis included 22 patients", "OS analysis included n=22"]
            ),
            
            DenominatorPattern(
                name="survival_evaluable",
                pattern=r"evaluable\s+for\s+(?:TTP|OS|survival)\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="survival",
                confidence=0.9,
                section="Methods",
                examples=["evaluable for TTP n=22", "evaluable for survival (n=22)"]
            ),
            
            # Safety analysis patterns
            DenominatorPattern(
                name="safety_evaluable",
                pattern=r"safety\s+(?:analysis|evaluation)\s+(?:included|analyzed)\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="safety",
                confidence=0.85,
                section="Methods",
                examples=["safety analysis included n=25", "safety evaluation analyzed (n=25)"]
            ),
            
            DenominatorPattern(
                name="safety_treated",
                pattern=r"treated\s+patients\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="safety",
                confidence=0.8,
                section="Methods",
                examples=["treated patients n=25", "treated patients (n=25)"]
            ),
            
            # Intent-to-treat patterns
            DenominatorPattern(
                name="itt_population",
                pattern=r"intent[-\s]to[-\s]treat\s+(?:population|cohort|group)\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="itt",
                confidence=0.9,
                section="Methods",
                examples=["intent-to-treat population n=30", "ITT cohort (n=30)"]
            ),
            
            DenominatorPattern(
                name="itt_analyzed",
                pattern=r"ITT\s+(?:analysis|population)\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="itt",
                confidence=0.85,
                section="Methods",
                examples=["ITT analysis n=30", "ITT population (n=30)"]
            ),
            
            # Per-protocol patterns
            DenominatorPattern(
                name="per_protocol",
                pattern=r"per[-\s]protocol\s+(?:population|cohort|group)\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="per_protocol",
                confidence=0.9,
                section="Methods",
                examples=["per-protocol population n=28", "per protocol cohort (n=28)"]
            ),
            
            # Results section patterns (lower confidence)
            DenominatorPattern(
                name="results_survival",
                pattern=r"(\d+)\s+patients?\s+(?:were|are)\s+evaluable\s+for\s+(?:survival|TTP|OS)",
                metric_family="survival",
                confidence=0.7,
                section="Results",
                examples=["22 patients were evaluable for survival", "22 patients are evaluable for TTP"]
            ),
            
            # Table patterns (highest confidence for exact matches)
            DenominatorPattern(
                name="table_total",
                pattern=r"total\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="total",
                confidence=0.98,
                section="Table",
                examples=["Total (n=25)", "Total n=25"]
            ),
            
            DenominatorPattern(
                name="table_evaluable",
                pattern=r"evaluable\s*\(?\s*n\s*=\s*(\d+)\s*\)?",
                metric_family="evaluable",
                confidence=0.95,
                section="Table",
                examples=["Evaluable (n=22)", "Evaluable n=22"]
            )
        ]
        
        return patterns
    
    def _resolve_denominators(self, spans: List[BaseSpan]) -> List[ResolvedDenominator]:
        """Resolve denominators from spans using patterns."""
        resolved = []
        
        for span in spans:
            for pattern in self.denominator_patterns:
                # Check if pattern matches this span
                matches = re.finditer(pattern.pattern, span.text, re.IGNORECASE)
                
                for match in matches:
                    try:
                        # Handle fraction patterns specially
                        if pattern.name == "fraction_denominator":
                            # For fraction patterns, use the denominator (second group)
                            n = int(match.group(2))
                        else:
                            # For all other patterns, use the first group
                            n = int(match.group(1))
                        
                        resolved_denom = ResolvedDenominator(
                            n=n,
                            metric_family=pattern.metric_family,
                            source_text=match.group(0),
                            span_id=span.span_id,
                            confidence=pattern.confidence,
                            section=span.section,
                            pattern_used=pattern.name
                        )
                        
                        resolved.append(resolved_denom)
                        
                    except (ValueError, IndexError):
                        # Skip invalid matches
                        continue
        
        return resolved
    
    def _group_denominators(self, resolved_denominators: List[ResolvedDenominator]) -> Dict[str, List[ResolvedDenominator]]:
        """Group denominators by metric family."""
        grouped = defaultdict(list)
        
        for denom in resolved_denominators:
            grouped[denom.metric_family].append(denom)
        
        return dict(grouped)
    
    def _resolve_ambiguities(self, grouped_denominators: Dict[str, List[ResolvedDenominator]]) -> Dict[str, ResolvedDenominator]:
        """Resolve ambiguities when multiple denominators exist for the same metric family."""
        final_denominators = {}
        
        for metric_family, denominators in grouped_denominators.items():
            if len(denominators) == 1:
                # No ambiguity
                final_denominators[metric_family] = denominators[0]
            else:
                # Resolve ambiguity using precedence rules
                resolved = self._resolve_family_ambiguity(denominators)
                final_denominators[metric_family] = resolved
        
        return final_denominators
    
    def _resolve_family_ambiguity(self, denominators: List[ResolvedDenominator]) -> ResolvedDenominator:
        """Resolve ambiguity for a specific metric family using precedence rules."""
        # Sort by confidence first
        sorted_by_confidence = sorted(denominators, key=lambda x: x.confidence, reverse=True)
        
        # If confidence is the same, use section precedence
        if len(set(d.confidence for d in denominators)) == 1:
            # Section precedence: Table > Results > Methods
            section_precedence = {"Table": 3, "Results": 2, "Methods": 1}
            sorted_by_section = sorted(
                sorted_by_confidence,
                key=lambda x: section_precedence.get(x.section, 0),
                reverse=True
            )
            return sorted_by_section[0]
        
        # Return highest confidence
        return sorted_by_confidence[0]
    
    def _get_ambiguity_summary(self, grouped: Dict[str, List[ResolvedDenominator]], 
                              final: Dict[str, ResolvedDenominator]) -> Dict[str, Any]:
        """Get a summary of ambiguity resolution."""
        summary = {}
        
        for metric_family, denominators in grouped.items():
            if len(denominators) > 1:
                summary[metric_family] = {
                    "candidates": len(denominators),
                    "resolved_to": {
                        "n": final[metric_family].n,
                        "confidence": final[metric_family].confidence,
                        "section": final[metric_family].section,
                        "pattern": final[metric_family].pattern_used
                    },
                    "alternatives": [
                        {
                            "n": d.n,
                            "confidence": d.confidence,
                            "section": d.section,
                            "pattern": d.pattern_used
                        }
                        for d in denominators if d != final[metric_family]
                    ]
                }
        
        return summary
    
    def _convert_to_standard_format(self, final_denominators: Dict[str, ResolvedDenominator]) -> DenominatorResult:
        """Convert internal format to standardized DenominatorResult."""
        result = DenominatorResult()
        
        for metric_family, denom in final_denominators.items():
            if metric_family == "response":
                result.response_n = denom.n
                result.response_n_span_ids = [str(denom.span_id)]
                result.confidence_scores["response"] = denom.confidence
                result.patterns_used["response"] = denom.pattern_used
            elif metric_family == "survival":
                result.ttp_os_n = denom.n
                result.ttp_os_n_span_ids = [str(denom.span_id)]
                result.confidence_scores["ttp_os"] = denom.confidence
                result.patterns_used["ttp_os"] = denom.pattern_used
            elif metric_family == "safety":
                result.safety_n = denom.n
                result.safety_n_span_ids = [str(denom.span_id)]
                result.confidence_scores["safety"] = denom.confidence
                result.patterns_used["safety"] = denom.pattern_used
            elif metric_family == "itt":
                result.itt_n = denom.n
                result.itt_n_span_ids = [str(denom.span_id)]
                result.confidence_scores["itt"] = denom.confidence
                result.patterns_used["itt"] = denom.pattern_used
            elif metric_family == "per_protocol":
                result.per_protocol_n = denom.n
                result.per_protocol_n_span_ids = [str(denom.span_id)]
                result.confidence_scores["per_protocol"] = denom.confidence
                result.patterns_used["per_protocol"] = denom.pattern_used
            elif metric_family == "total" or metric_family == "evaluable":
                # Map generic totals to treated_n as fallback
                if result.treated_n is None:
                    result.treated_n = denom.n
                    result.treated_n_span_ids = [str(denom.span_id)]
                    result.confidence_scores["treated"] = denom.confidence
                    result.patterns_used["treated"] = denom.pattern_used
        
        return result
    
    def get_method_card_denominators(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get denominators formatted for MethodCard.analysis_denominators."""
        try:
            result = self.process(inputs)
            if not result.success:
                return {"error": result.error_message}
            
            denominators = result.output.get("denominators")
            if not denominators:
                return {"error": "No denominators found"}
            
            return denominators.get_method_card_format()
                
        except Exception as e:
            return {"error": str(e)}
    
    def attach_denominators_to_factsheet(self, factsheet_data: Dict[str, Any], 
                                       inputs: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Attach correct denominators to ResultsFactsheet rows."""
        try:
            # Get denominators for this document
            denominators = self.get_method_card_denominators(inputs)
            if "error" in denominators:
                return False, [denominators["error"]]
            
            errors = []
            
            # Process each row
            for i, row in enumerate(factsheet_data.get("rows", [])):
                row_prefix = f"Row {i + 1}:"
                
                # Determine metric family
                metric_id = row.get("metric", "")
                metric_family = self._map_metric_to_denominator_family(metric_id)
                
                if metric_family:
                    key = f"{metric_family}_n"
                    if key in denominators:
                        row["n"] = denominators[key]
                        row["analysis_set"] = metric_family
                    elif "n" not in row or row["n"] is None:
                        errors.append(f"{row_prefix} No denominator found for metric {metric_id}")
                else:
                    # No metric family determined
                    if "n" not in row or row["n"] is None:
                        errors.append(f"{row_prefix} No denominator found for metric {metric_id}")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            return False, [f"Error attaching denominators: {str(e)}"]
    
    def _get_metric_family(self, metric_id: str) -> Optional[str]:
        """Get the metric family for a given metric ID."""
        metric = self.metric_registry.get_metric(metric_id)
        if not metric:
            return None
        
        # Map metric types to families
        if metric.metric_type.value == "survival":
            return "survival"
        elif metric.metric_type.value == "response":
            return "response"
        elif metric.metric_type.value == "safety":
            return "safety"
        elif metric.metric_type.value == "biomarker":
            return "response"  # Biomarkers often use response denominators
        else:
            return "general"
    
    def _map_metric_to_denominator_family(self, metric_id: str) -> Optional[str]:
        """Map specific metrics to their appropriate denominator families."""
        metric_lower = metric_id.lower()
        
        # Response metrics
        if any(term in metric_lower for term in ["orr", "orr_recist", "ca125", "ca125_response", "response"]):
            return "response"
        
        # Survival metrics
        if any(term in metric_lower for term in ["ttp", "median_ttp", "os", "median_os", "pfs", "median_pfs"]):
            return "survival"
        
        # Safety metrics
        if any(term in metric_lower for term in ["safety", "ae", "adverse"]):
            return "safety"
        
        # Default to response for unknown metrics
        return "response"
    
    def validate_denominator_consistency(self, inputs: Dict[str, Any], factsheet_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that denominators are consistent across the factsheet."""
        try:
            # Get denominators for this document
            denominators = self.get_method_card_denominators(inputs)
            if "error" in denominators:
                return {"error": denominators["error"]}
            
            # Check consistency
            consistency_report = {
                "doc_id": inputs.get("doc_id"),
                "denominators_found": denominators,
                "factsheet_consistency": {},
                "overall_consistent": True
            }
            
            for i, row in enumerate(factsheet_data.get("rows", [])):
                row_prefix = f"Row {i + 1}"
                metric_id = row.get("metric", "")
                row_n = row.get("n")
                
                if not row_n:
                    consistency_report["factsheet_consistency"][row_prefix] = {
                        "status": "missing_n",
                        "message": "No n value provided"
                    }
                    consistency_report["overall_consistent"] = False
                    continue
                
                # Check if n matches expected denominator
                metric_family = self._get_metric_family(metric_id)
                expected_n = denominators.get(f"{metric_family}_n") if metric_family else None
                
                if expected_n and row_n != expected_n:
                    consistency_report["factsheet_consistency"][row_prefix] = {
                        "status": "mismatch",
                        "expected": expected_n,
                        "found": row_n,
                        "message": f"n mismatch: expected {expected_n}, found {row_n}"
                    }
                    consistency_report["overall_consistent"] = False
                else:
                    consistency_report["factsheet_consistency"][row_prefix] = {
                        "status": "consistent",
                        "n": row_n
                    }
            
            return consistency_report
            
        except Exception as e:
            return {"error": str(e)}
