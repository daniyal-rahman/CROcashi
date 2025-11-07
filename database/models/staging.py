"""
Staging tables for raw data before entity resolution.
"""
import uuid
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from database.models.base import BaseModel


class StagingRawData(BaseModel):
    """Staging table for raw data before processing."""
    
    __tablename__ = 'staging_raw_data'
    
    staging_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    source_system = Column(
        String(200),
        nullable=False,
        index=True,
        comment='clinicaltrials_gov, sec_edgar, pubmed, drugbank, fda, etc.'
    )
    source_record_id = Column(
        String(500),
        nullable=False,
        index=True
    )
    
    raw_data = Column(
        JSONB,
        nullable=False,
        comment='Entire source record'
    )
    extracted_fields = Column(
        JSONB,
        nullable=True,
        comment='Key fields pulled out'
    )
    
    ingested_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=func.now()
    )
    
    processed = Column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    processed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    processing_errors = Column(Text, nullable=True)
    
    __table_args__ = (
        {'comment': 'Staging table for raw ingested data'}
    )

