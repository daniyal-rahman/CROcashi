"""
IDenominatorResolver Interface

Defines the common interface for all denominator resolver implementations
to ensure consistent schema and behavior between deterministic and LLM approaches.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from ..base_worker import WorkerResult


@dataclass
class DenominatorResult:
    """Standardized denominator result with span provenance."""
    response_n: Optional[int] = None
    ttp_os_n: Optional[int] = None
    safety_n: Optional[int] = None
    treated_n: Optional[int] = None
    itt_n: Optional[int] = None
    per_protocol_n: Optional[int] = None
    
    # Span provenance
    response_n_span_ids: List[str] = None
    ttp_os_n_span_ids: List[str] = None
    safety_n_span_ids: List[str] = None
    treated_n_span_ids: List[str] = None
    itt_n_span_ids: List[str] = None
    per_protocol_n_span_ids: List[str] = None
    
    # Confidence and metadata
    confidence_scores: Dict[str, float] = None
    patterns_used: Dict[str, str] = None
    
    def __post_init__(self):
        if self.response_n_span_ids is None:
            self.response_n_span_ids = []
        if self.ttp_os_n_span_ids is None:
            self.ttp_os_n_span_ids = []
        if self.safety_n_span_ids is None:
            self.safety_n_span_ids = []
        if self.treated_n_span_ids is None:
            self.treated_n_span_ids = []
        if self.itt_n_span_ids is None:
            self.itt_n_span_ids = []
        if self.per_protocol_n_span_ids is None:
            self.per_protocol_n_span_ids = []
        if self.confidence_scores is None:
            self.confidence_scores = {}
        if self.patterns_used is None:
            self.patterns_used = {}
    
    def get_method_card_format(self) -> Dict[str, Any]:
        """Get denominators formatted for MethodCard.analysis_denominators."""
        method_card_denominators = {}
        
        if self.response_n is not None:
            method_card_denominators["response_n"] = self.response_n
        if self.ttp_os_n is not None:
            method_card_denominators["ttp_os_n"] = self.ttp_os_n
        if self.safety_n is not None:
            method_card_denominators["safety_n"] = self.safety_n
        if self.treated_n is not None:
            method_card_denominators["treated_n"] = self.treated_n
        if self.itt_n is not None:
            method_card_denominators["itt_n"] = self.itt_n
        if self.per_protocol_n is not None:
            method_card_denominators["per_protocol_n"] = self.per_protocol_n
            
        return method_card_denominators
    
    def count_extracted_denominators(self) -> int:
        """Count how many denominators were extracted."""
        count = 0
        if self.response_n is not None:
            count += 1
        if self.ttp_os_n is not None:
            count += 1
        if self.safety_n is not None:
            count += 1
        if self.treated_n is not None:
            count += 1
        if self.itt_n is not None:
            count += 1
        if self.per_protocol_n is not None:
            count += 1
        return count


class IDenominatorResolver(ABC):
    """
    Interface for denominator resolver implementations.
    
    This interface ensures both deterministic and LLM-based resolvers
    return the same data structure and support the same operations.
    """
    
    @abstractmethod
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process inputs to extract denominators.
        
        Args:
            inputs: Dict containing:
                - evidence_spans: List[EvidenceSpan] - Evidence spans to process
                - doc_id: Optional[int] - Document ID if database lookup needed
                - trial_context: Optional[Dict] - Additional trial context
                
        Returns:
            WorkerResult with DenominatorResult in output.denominators
            
        The WorkerResult.output should have this structure:
        {
            "denominators": DenominatorResult,
            "processed_spans": int,
            "extracted_denominators": int,
            "metadata": Dict[str, Any]
        }
        """
        pass
    
    @abstractmethod
    def get_method_card_denominators(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get denominators formatted for MethodCard.analysis_denominators.
        
        Args:
            inputs: Same as process() inputs
            
        Returns:
            Dict with keys like "response_n", "ttp_os_n", etc.
        """
        pass
    
    @abstractmethod
    def attach_denominators_to_factsheet(self, factsheet_data: Dict[str, Any], 
                                       inputs: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Attach correct denominators to ResultsFactsheet rows.
        
        Args:
            factsheet_data: ResultsFactsheet data to modify
            inputs: Same as process() inputs
            
        Returns:
            Tuple of (success: bool, errors: List[str])
        """
        pass
    
    def validate_denominator_consistency(self, inputs: Dict[str, Any], 
                                       factsheet_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that denominators are consistent across the factsheet.
        
        Args:
            inputs: Same as process() inputs
            factsheet_data: ResultsFactsheet data to validate
            
        Returns:
            Dict with consistency report
        """
        # Default implementation using the other methods
        result = self.process(inputs)
        if not result.success:
            return {"error": result.error_message}
        
        denominators = result.output.get("denominators")
        if not denominators:
            return {"error": "No denominators found"}
        
        # Basic consistency check
        method_card_denominators = denominators.get_method_card_format()
        consistency_report = {
            "denominators_found": method_card_denominators,
            "factsheet_consistency": {},
            "overall_consistent": True
        }
        
        for i, row in enumerate(factsheet_data.get("rows", [])):
            row_prefix = f"Row {i + 1}"
            row_n = row.get("n")
            
            if not row_n:
                consistency_report["factsheet_consistency"][row_prefix] = {
                    "status": "missing_n",
                    "message": "No n value provided"
                }
                consistency_report["overall_consistent"] = False
                continue
            
            consistency_report["factsheet_consistency"][row_prefix] = {
                "status": "present",
                "n": row_n
            }
        
        return consistency_report


# Factory function to create resolver instances
def create_denominator_resolver(strategy: str = "deterministic") -> IDenominatorResolver:
    """
    Factory function to create a denominator resolver instance.
    
    Args:
        strategy: Either "deterministic" or "llm"
        
    Returns:
        IDenominatorResolver implementation
        
    Raises:
        ValueError: If strategy is not supported
    """
    if strategy == "deterministic":
        from ..denominator_resolver import DenominatorResolver
        return DenominatorResolver()
    elif strategy == "llm":
        from ..llm.denominator_resolver import DenominatorResolver as LLMDenominatorResolver
        return LLMDenominatorResolver()
    else:
        raise ValueError(f"Unknown denominator resolver strategy: {strategy}")
