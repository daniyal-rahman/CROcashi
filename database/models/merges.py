"""
Entity merge tracking models.
"""
import uuid
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from database.models.base import BaseModel


class EntityMerge(BaseModel):
    """
    Tracks when entities are merged together.
    
    When two entities are discovered to be the same, we merge them.
    This table keeps an audit trail of all merges, allowing us to:
    - Track which entity was merged into which
    - Potentially reverse merges if needed
    - Understand entity resolution history
    """
    
    __tablename__ = 'entity_merges'
    
    merge_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    source_entity_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment='The entity being merged away (source)'
    )
    target_entity_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment='The canonical entity (target) that source is merged into'
    )
    entity_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='company, drug, disease, target, institution, trial, publication'
    )
    merged_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment='When the merge occurred'
    )
    merge_reason = Column(
        Text,
        nullable=True,
        comment='Why these entities were merged (duplicate, alias match, etc.)'
    )
    reversible = Column(
        Boolean,
        default=True,
        nullable=False,
        comment='Whether this merge can be reversed'
    )
    merged_by = Column(
        String(200),
        nullable=True,
        index=True,
        comment='system, manual, or user_id who performed the merge'
    )
    
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('company', 'drug', 'disease', 'target', 'institution', 'trial', 'publication', 'patent')",
            name='check_merge_entity_type'
        ),
        {'comment': 'Entity merge tracking for audit trail'}
    )

