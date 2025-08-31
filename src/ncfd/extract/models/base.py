"""
Base models for study card system.
"""

from abc import ABC
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Any, Optional
import uuid
import json


@dataclass
class ProvenanceMixin:
    """Mixin for tracking data lineage and provenance."""
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    version: int = 1
    input_hash: Optional[str] = None
    parent_ids: list = field(default_factory=list)
    provenance_span_ids: list = field(default_factory=list)  # Renamed to avoid conflict
    notes: list = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling datetime and other non-serializable types."""
        data = asdict(self)
        # Convert datetime to ISO string
        if isinstance(data.get('created_at'), datetime):
            data['created_at'] = data['created_at'].isoformat()
        return data


@dataclass
class BaseModel(ABC):
    """Base class for all study card models."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "draft"  # draft, validated, frozen
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> bool:
        """Validate the model. Override in subclasses."""
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert datetime to ISO string if present
        if isinstance(data.get('created_at'), datetime):
            data['created_at'] = data['created_at'].isoformat()
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseModel':
        """Create instance from dictionary."""
        # Handle datetime conversion
        if 'created_at' in data and isinstance(data['created_at'], str):
            try:
                data['created_at'] = datetime.fromisoformat(data['created_at'])
            except ValueError:
                data['created_at'] = datetime.utcnow()
        return cls(**data)
