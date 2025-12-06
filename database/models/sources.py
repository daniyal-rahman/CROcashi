"""
Source metadata models for tracking data source reliability and update frequency.
"""
import uuid
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from database.models.base import BaseModel


class Source(BaseModel):
    """Source metadata for tracking data source reliability and update frequency."""
    
    __tablename__ = 'sources'
    
    source_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    source_name = Column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
        comment='clinicaltrials_gov, sec_edgar, pubmed, fda_drugs, etc.'
    )
    source_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='regulatory, literature, financial, social, patent, clinical'
    )
    reliability_score = Column(
        Numeric(3, 2),
        nullable=True,
        comment='0-1 reliability score based on historical accuracy'
    )
    update_frequency = Column(
        String(50),
        nullable=True,
        index=True,
        comment='daily, weekly, monthly, on_demand, real_time'
    )
    last_checked = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment='Last time we checked this source for updates'
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment='Whether this source is currently being ingested'
    )
    base_url = Column(String(1000), nullable=True, comment='Base URL for API or website')
    documentation_url = Column(String(1000), nullable=True)
    source_metadata = Column(
        JSONB,
        nullable=True,
        comment='Additional source-specific metadata (API keys, rate limits, etc.)'
    )
    
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('regulatory', 'literature', 'financial', 'social', 'patent', 'clinical', 'other')",
            name='check_source_type'
        ),
        CheckConstraint(
            "update_frequency IN ('daily', 'weekly', 'monthly', 'on_demand', 'real_time') OR update_frequency IS NULL",
            name='check_update_frequency'
        ),
        CheckConstraint(
            "reliability_score IS NULL OR (reliability_score >= 0 AND reliability_score <= 1)",
            name='check_reliability_score'
        ),
        {'comment': 'Source metadata for tracking reliability and update frequency'}
    )

