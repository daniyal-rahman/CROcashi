"""
Span-Limited LLM Normalizer

LLM worker that normalizes and validates extracted data using only triaged spans.
Implements span-limited processing to prevent hallucinations and ensure auditability.
"""

import json
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass

from ..base_worker import BaseWorker, WorkerResult
from ....db.models import BaseSpan, DerivedSpan
from ....db.session import get_session
from ...normalization.metric_registry import get_metric_registry
from ...config.span_config_loader import get_span_config


@dataclass
class NormalizationInput:
    """Input data for normalization."""
    metric_id: str
    raw_value: Union[str, float, int]
    raw_unit: str
    raw_n: Optional[int] = None
    span_ids: List[int] = None
    confidence: float = 0.8
    
    def __post_init__(self):
        if self.span_ids is None:
            self.span_ids = []


@dataclass
class NormalizationResult:
    """Result of normalization process."""
    input_data: NormalizationInput
    normalized_value: Optional[float] = None
    normalized_unit: Optional[str] = None
    is_valid: bool = False
    validation_errors: List[str] = None
    confidence: float = 0.8
    reasoning: str = ""
    
    def __post_init__(self):
        if self.validation_errors is None:
            self.validation_errors = []


@dataclass
class ValidationContext:
    """Context for validation including spans and registry."""
    spans: List[Dict[str, Any]]
    metric_registry: Any
    doc_id: int


class SpanLimitedNormalizer(BaseWorker):
    """LLM worker for normalizing extracted data using span-limited input."""
    
    def __init__(self):
        super().__init__(name="SpanLimitedNormalizer", version="1.0.0")
        self.config = get_span_config()
        self.metric_registry = get_metric_registry()
        
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Normalize extracted data using span-limited processing."""
        doc_id = inputs.get("doc_id")
        extracted_data = inputs.get("extracted_data", [])
        spans = inputs.get("spans", [])
        
        if not doc_id:
            return WorkerResult(
                success=False,
                output=None,
                error_message="doc_id is required"
            )
        
        if not extracted_data:
            return WorkerResult(
                success=False,
                output=None,
                error_message="extracted_data is required"
            )
        
        if not spans:
            return WorkerResult(
                success=False,
                output=None,
                error_message="spans are required for span-limited processing"
            )
        
        try:
            # Create validation context
            context = ValidationContext(
                spans=spans,
                metric_registry=self.metric_registry,
                doc_id=doc_id
            )
            
            # Normalize each extracted data item
            normalization_results = []
            for data_item in extracted_data:
                result = self._normalize_data_item(data_item, context)
                normalization_results.append(result)
            
            # Generate summary
            summary = self._generate_normalization_summary(normalization_results)
            
            return WorkerResult(
                success=True,
                output={
                    "normalized_data": [
                        {
                            "metric_id": result.input_data.metric_id,
                            "original_value": result.input_data.raw_value,
                            "original_unit": result.input_data.raw_unit,
                            "normalized_value": result.normalized_value,
                            "normalized_unit": result.normalized_unit,
                            "is_valid": result.is_valid,
                            "validation_errors": result.validation_errors,
                            "confidence": result.confidence,
                            "reasoning": result.reasoning,
                            "span_ids": result.input_data.span_ids
                        }
                        for result in normalization_results
                    ],
                    "summary": summary,
                    "total_items": len(normalization_results),
                    "valid_items": sum(1 for r in normalization_results if r.is_valid),
                    "invalid_items": sum(1 for r in normalization_results if not r.is_valid)
                },
                metadata={
                    "doc_id": doc_id,
                    "spans_used": len(spans),
                    "span_limited": True
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error normalizing data for document {doc_id}: {str(e)}"
            )
    
    def _normalize_data_item(self, data_item: Dict[str, Any], 
                            context: ValidationContext) -> NormalizationResult:
        """Normalize a single data item using span-limited context."""
        # Create input data
        input_data = NormalizationInput(
            metric_id=data_item.get("metric_id", ""),
            raw_value=data_item.get("value"),
            raw_unit=data_item.get("unit", ""),
            raw_n=data_item.get("n"),
            span_ids=data_item.get("span_ids", []),
            confidence=data_item.get("confidence", 0.8)
        )
        
        # Validate input
        if not self._validate_input_data(input_data):
            return NormalizationResult(
                input_data=input_data,
                is_valid=False,
                validation_errors=["Invalid input data format"],
                reasoning="Input data validation failed"
            )
        
        # Check if metric exists in registry
        metric = context.metric_registry.get_metric(input_data.metric_id)
        if not metric:
            return NormalizationResult(
                input_data=input_data,
                is_valid=False,
                validation_errors=[f"Unknown metric: {input_data.metric_id}"],
                reasoning=f"Metric {input_data.metric_id} not found in registry"
            )
        
        # Validate against registry
        validation_result = self._validate_against_registry(input_data, metric)
        if not validation_result["is_valid"]:
            return NormalizationResult(
                input_data=input_data,
                is_valid=False,
                validation_errors=validation_result["errors"],
                reasoning="Registry validation failed"
            )
        
        # Perform normalization
        normalization_result = self._perform_normalization(input_data, metric)
        
        # Validate span references
        span_validation = self._validate_span_references(input_data, context)
        if not span_validation["is_valid"]:
            normalization_result.validation_errors.extend(span_validation["errors"])
            normalization_result.is_valid = False
        
        return normalization_result
    
    def _validate_input_data(self, input_data: NormalizationInput) -> bool:
        """Validate basic input data format."""
        if not input_data.metric_id:
            return False
        
        if input_data.raw_value is None:
            return False
        
        if not input_data.raw_unit:
            return False
        
        # Check if raw_value can be converted to float
        try:
            float(input_data.raw_value)
        except (ValueError, TypeError):
            return False
        
        return True
    
    def _validate_against_registry(self, input_data: NormalizationInput, 
                                 metric: Any) -> Dict[str, Any]:
        """Validate data against metric registry."""
        try:
            value = float(input_data.raw_value)
            unit = input_data.raw_unit
            n = input_data.raw_n
            
            is_valid, errors = self.metric_registry.validate_metric_value(
                input_data.metric_id, value, unit, n
            )
            
            return {
                "is_valid": is_valid,
                "errors": errors
            }
            
        except Exception as e:
            return {
                "is_valid": False,
                "errors": [f"Validation error: {str(e)}"]
            }
    
    def _perform_normalization(self, input_data: NormalizationInput, 
                             metric: Any) -> NormalizationResult:
        """Perform normalization using metric registry."""
        try:
            value = float(input_data.raw_value)
            unit = input_data.raw_unit
            
            # Normalize value
            normalized = self.metric_registry.normalize_value(
                input_data.metric_id, value, unit
            )
            
            if normalized.is_valid:
                return NormalizationResult(
                    input_data=input_data,
                    normalized_value=normalized.normalized_value,
                    normalized_unit=normalized.normalized_unit,
                    is_valid=True,
                    confidence=input_data.confidence,
                    reasoning=f"Successfully normalized {value} {unit} to {normalized.normalized_value} {normalized.normalized_unit}"
                )
            else:
                return NormalizationResult(
                    input_data=input_data,
                    is_valid=False,
                    validation_errors=[normalized.error_message],
                    reasoning=f"Normalization failed: {normalized.error_message}"
                )
                
        except Exception as e:
            return NormalizationResult(
                input_data=input_data,
                is_valid=False,
                validation_errors=[f"Normalization error: {str(e)}"],
                reasoning=f"Exception during normalization: {str(e)}"
            )
    
    def _validate_span_references(self, input_data: NormalizationInput, 
                                context: ValidationContext) -> Dict[str, Any]:
        """Validate that span references are valid and accessible."""
        if not input_data.span_ids:
            return {
                "is_valid": False,
                "errors": ["No span references provided"]
            }
        
        # Get span IDs from context
        available_span_ids = {span.get("span_id") for span in context.spans}
        
        # Check if all referenced spans are available
        missing_spans = []
        for span_id in input_data.span_ids:
            if span_id not in available_span_ids:
                missing_spans.append(span_id)
        
        if missing_spans:
            return {
                "is_valid": False,
                "errors": [f"Span references not found in context: {missing_spans}"]
            }
        
        return {
            "is_valid": True,
            "errors": []
        }
    
    def _generate_normalization_summary(self, results: List[NormalizationResult]) -> Dict[str, Any]:
        """Generate a summary of normalization results."""
        total = len(results)
        valid = sum(1 for r in results if r.is_valid)
        invalid = total - valid
        
        # Count by metric type
        metric_counts = {}
        for result in results:
            metric_id = result.input_data.metric_id
            metric_counts[metric_id] = metric_counts.get(metric_id, 0) + 1
        
        # Count validation errors
        error_counts = {}
        for result in results:
            for error in result.validation_errors:
                error_counts[error] = error_counts.get(error, 0) + 1
        
        # Average confidence
        avg_confidence = sum(r.confidence for r in results) / total if total > 0 else 0.0
        
        return {
            "total_items": total,
            "valid_items": valid,
            "invalid_items": invalid,
            "success_rate": valid / total if total > 0 else 0.0,
            "metric_distribution": metric_counts,
            "common_errors": error_counts,
            "average_confidence": avg_confidence
        }
    
    def validate_results_factsheet(self, factsheet_data: Dict[str, Any], 
                                 spans: List[Dict[str, Any]], doc_id: int) -> Dict[str, Any]:
        """Validate a complete ResultsFactsheet using span-limited processing."""
        try:
            # Create validation context
            context = ValidationContext(
                spans=spans,
                metric_registry=self.metric_registry,
                doc_id=doc_id
            )
            
            # Extract data from factsheet
            extracted_data = []
            for i, row in enumerate(factsheet_data.get("rows", [])):
                extracted_data.append({
                    "metric_id": row.get("metric", ""),
                    "value": row.get("value"),
                    "unit": row.get("unit", ""),
                    "n": row.get("n"),
                    "span_ids": row.get("span_ids", []),
                    "row_index": i
                })
            
            # Normalize each row
            normalization_results = []
            for data_item in extracted_data:
                result = self._normalize_data_item(data_item, context)
                normalization_results.append(result)
            
            # Generate validation report
            validation_report = {
                "doc_id": doc_id,
                "total_rows": len(extracted_data),
                "valid_rows": sum(1 for r in normalization_results if r.is_valid),
                "invalid_rows": sum(1 for r in normalization_results if not r.is_valid),
                "row_validation": [],
                "overall_valid": all(r.is_valid for r in normalization_results)
            }
            
            for i, result in enumerate(normalization_results):
                row_report = {
                    "row_index": i,
                    "metric_id": result.input_data.metric_id,
                    "is_valid": result.is_valid,
                    "validation_errors": result.validation_errors,
                    "normalized_value": result.normalized_value,
                    "normalized_unit": result.normalized_unit,
                    "span_ids": result.input_data.span_ids
                }
                validation_report["row_validation"].append(row_report)
            
            return validation_report
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_normalization_suggestions(self, invalid_results: List[NormalizationResult]) -> List[Dict[str, Any]]:
        """Get suggestions for fixing invalid normalization results."""
        suggestions = []
        
        for result in invalid_results:
            suggestion = {
                "metric_id": result.input_data.metric_id,
                "original_value": result.input_data.raw_value,
                "original_unit": result.input_data.raw_unit,
                "issues": result.validation_errors,
                "suggestions": []
            }
            
            # Generate specific suggestions based on error types
            for error in result.validation_errors:
                if "unit" in error.lower():
                    suggestion["suggestions"].append("Check unit format and ensure it matches allowed units")
                elif "value" in error.lower():
                    suggestion["suggestions"].append("Verify numeric value is within expected range")
                elif "span" in error.lower():
                    suggestion["suggestions"].append("Ensure span references are valid and accessible")
                else:
                    suggestion["suggestions"].append("Review data format and registry requirements")
            
            suggestions.append(suggestion)
        
        return suggestions
    
    def export_normalized_data(self, results: List[NormalizationResult]) -> List[Dict[str, Any]]:
        """Export normalized data in a standardized format."""
        exported = []
        
        for result in results:
            if result.is_valid:
                exported_item = {
                    "metric_id": result.input_data.metric_id,
                    "original": {
                        "value": result.input_data.raw_value,
                        "unit": result.input_data.raw_unit,
                        "n": result.input_data.raw_n
                    },
                    "normalized": {
                        "value": result.normalized_value,
                        "unit": result.normalized_unit
                    },
                    "confidence": result.confidence,
                    "span_ids": result.input_data.span_ids,
                    "metadata": {
                        "normalized_at": "2024-01-01T00:00:00Z",  # Should use actual timestamp
                        "normalizer_version": self.version,
                        "reasoning": result.reasoning
                    }
                }
                exported.append(exported_item)
        
        return exported
