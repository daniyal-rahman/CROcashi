"""
Base model class with common fields.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class BaseModel(Base):
    """Abstract base class with common fields."""
    
    __abstract__ = True
    
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment='Record creation timestamp'
    )
    last_updated = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment='Last update timestamp'
    )
    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment='Soft delete timestamp. NULL = not deleted'
    )
    deletion_reason = Column(
        Text,
        nullable=True,
        comment='Reason for deletion (if soft deleted)'
    )
    
    def __repr__(self) -> str:
        """Default __repr__ implementation."""
        class_name = self.__class__.__name__
        attrs = ', '.join([
            f"{k}={v!r}" for k, v in self.__dict__.items()
            if not k.startswith('_')
        ][:5])  # Limit to first 5 attributes
        return f"<{class_name}({attrs})>"


def generate_uuid() -> str:
    """Generate UUID for primary keys."""
    return str(uuid.uuid4())

