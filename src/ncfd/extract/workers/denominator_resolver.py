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


class DenominatorResolver(BaseWorker):
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
                
                return WorkerResult(
                    success=True,
                    output={
                        "resolved_denominators": final_denominators,
                        "total_patterns_found": len(resolved_denominators),
                        "metric_families_covered": list(final_denominators.keys()),
                        "ambiguity_resolution": self._get_ambiguity_summary(grouped_denominators, final_denominators)
                    },
                    metadata={
                        "doc_id": doc_id,
                        "patterns_used": [p.name for p in self.denominator_patterns]
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
                name="results_response",
                pattern=r"(\d+)\s+patients?\s+(?:achieved|showed|had)\s+(?:response|CR|PR|SD)",
                metric_family="response",
                confidence=0.7,
                section="Results",
                examples=["19 patients achieved response", "19 patients showed PR"]
            ),
            
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
    
    def get_method_card_denominators(self, doc_id: int) -> Dict[str, Any]:
        """Get denominators formatted for MethodCard.analysis_denominators."""
        try:
            with get_session() as session:
                spans = session.query(BaseSpan).filter(BaseSpan.doc_id == doc_id).all()
                resolved_denominators = self._resolve_denominators(spans)
                grouped = self._group_denominators(resolved_denominators)
                final = self._resolve_ambiguities(grouped)
                
                # Format for MethodCard
                method_card_denominators = {}
                
                for metric_family, denom in final.items():
                    if metric_family == "response":
                        method_card_denominators["response_n"] = denom.n
                    elif metric_family == "survival":
                        method_card_denominators["ttp_os_n"] = denom.n
                    elif metric_family == "safety":
                        method_card_denominators["safety_n"] = denom.n
                    elif metric_family == "itt":
                        method_card_denominators["itt_n"] = denom.n
                    elif metric_family == "per_protocol":
                        method_card_denominators["per_protocol_n"] = denom.n
                    else:
                        method_card_denominators[f"{metric_family}_n"] = denom.n
                
                return method_card_denominators
                
        except Exception as e:
            return {"error": str(e)}
    
    def attach_denominators_to_factsheet(self, factsheet_data: Dict[str, Any], 
                                       doc_id: int) -> Tuple[bool, List[str]]:
        """Attach correct denominators to ResultsFactsheet rows."""
        try:
            # Get denominators for this document
            denominators = self.get_method_card_denominators(doc_id)
            if "error" in denominators:
                return False, [denominators["error"]]
            
            errors = []
            
            # Process each row
            for i, row in enumerate(factsheet_data.get("rows", [])):
                row_prefix = f"Row {i + 1}:"
                
                # Determine metric family
                metric_id = row.get("metric", "")
                metric_family = self._get_metric_family(metric_id)
                
                if metric_family and metric_family in denominators:
                    # Attach denominator
                    row["n"] = denominators[metric_family]
                    row["analysis_set"] = metric_family
                else:
                    # No denominator found for this metric
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
    
    def validate_denominator_consistency(self, doc_id: int, factsheet_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that denominators are consistent across the factsheet."""
        try:
            # Get denominators for this document
            denominators = self.get_method_card_denominators(doc_id)
            if "error" in denominators:
                return {"error": denominators["error"]}
            
            # Check consistency
            consistency_report = {
                "doc_id": doc_id,
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
