"""
Base Worker Class

Abstract base class for all study card workers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json


@dataclass
class WorkerResult:
    """Result from a worker execution."""
    success: bool
    output: Any
    error_message: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseWorker(ABC):
    """Abstract base class for all study card workers."""
    
    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.created_at = datetime.now(datetime.UTC)
        self.execution_count = 0
        self.total_execution_time = 0.0
        self.error_count = 0
        
    @abstractmethod
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Process inputs and return results. Must be implemented by subclasses."""
        pass
    
    def execute(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Execute the worker with timing and error handling."""
        start_time = datetime.now(datetime.UTC)
        self.execution_count += 1
        
        try:
            # Validate inputs
            if not self._validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    output=None,
                    error_message="Input validation failed",
                    metadata={"worker": self.name, "version": self.version}
                )
            
            # Process inputs
            result = self.process(inputs)
            
            # Calculate execution time
            execution_time = (datetime.now(datetime.UTC) - start_time).total_seconds()
            result.execution_time = execution_time
            self.total_execution_time += execution_time
            
            # Add metadata
            if result.metadata is None:
                result.metadata = {}
            result.metadata.update({
                "worker": self.name,
                "version": self.version,
                "execution_count": self.execution_count
            })
            
            return result
            
        except Exception as e:
            execution_time = (datetime.now(datetime.UTC) - start_time).total_seconds()
            self.error_count += 1
            self.total_execution_time += execution_time
            
            return WorkerResult(
                success=False,
                output=None,
                error_message=str(e),
                execution_time=execution_time,
                metadata={
                    "worker": self.name,
                    "version": self.version,
                    "execution_count": self.execution_count,
                    "error_count": self.error_count
                }
            )
    
    def _validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate input parameters. Override in subclasses for specific validation."""
        return inputs is not None and isinstance(inputs, dict)
    
    def _compute_input_hash(self, inputs: Dict[str, Any]) -> str:
        """Compute a hash of the inputs for caching and lineage tracking."""
        # Sort keys to ensure consistent hashing
        sorted_inputs = json.dumps(inputs, sort_keys=True, default=str)
        return hashlib.sha256(sorted_inputs.encode()).hexdigest()
    
    def _add_provenance(self, output: Any, inputs: Dict[str, Any]) -> Any:
        """Add provenance information to the output."""
        if hasattr(output, 'input_hash'):
            output.input_hash = self._compute_input_hash(inputs)
        if hasattr(output, 'created_by'):
            output.created_by = self.name
        if hasattr(output, 'parent_ids'):
            # Add input IDs as parent IDs if they exist
            parent_ids = []
            for key, value in inputs.items():
                if hasattr(value, 'span_id'):
                    # Use span_id as canonical identifier for EvidenceSpan objects
                    parent_ids.append(value.span_id)
                elif hasattr(value, 'internal_id'):
                    # Use internal_id for other objects
                    parent_ids.append(value.internal_id)
                elif isinstance(value, list):
                    for item in value:
                        if hasattr(item, 'span_id'):
                            # Use span_id as canonical identifier for EvidenceSpan objects
                            parent_ids.append(item.span_id)
                        elif hasattr(item, 'internal_id'):
                            # Use internal_id for other objects
                            parent_ids.append(item.internal_id)
            if parent_ids:
                output.parent_ids = parent_ids
        return output
    
    @property
    def average_execution_time(self) -> float:
        """Get the average execution time."""
        if self.execution_count == 0:
            return 0.0
        return self.total_execution_time / self.execution_count
    
    @property
    def error_rate(self) -> float:
        """Get the error rate."""
        if self.execution_count == 0:
            return 0.0
        return self.error_count / self.execution_count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        return {
            "name": self.name,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "execution_count": self.execution_count,
            "total_execution_time": self.total_execution_time,
            "average_execution_time": self.average_execution_time,
            "error_count": self.error_count,
            "error_rate": self.error_rate
        }
    
    def reset_stats(self) -> None:
        """Reset worker statistics."""
        self.execution_count = 0
        self.total_execution_time = 0.0
        self.error_count = 0
