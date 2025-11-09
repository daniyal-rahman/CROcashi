"""
Data lineage models for comprehensive source provenance tracking.
"""
import uuid
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database.models.base import BaseModel


class DataLineage(BaseModel):
    """
    Data lineage tracking for comprehensive source provenance.
    
    Tracks where each record came from, when it was extracted,
    and how it was processed. Only tracks key tables (entities, 
    relationships, events, derived data).
    """
    
    __tablename__ = 'data_lineage'
    
    lineage_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    table_name = Column(
        String(200),
        nullable=False,
        index=True,
        comment='Which table: companies, drugs, events, entity_relationships, etc.'
    )
    record_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment='Foreign key to the actual record in the referenced table'
    )
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey('sources.source_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    extracted_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment='When this data was extracted from the source'
    )
    raw_data_snapshot = Column(
        JSONB,
        nullable=True,
        comment='Original source data snapshot for reproducibility'
    )
    extraction_method = Column(
        String(50),
        nullable=True,
        index=True,
        comment='manual, api, scraper, llm, parser'
    )
    extraction_metadata = Column(
        JSONB,
        nullable=True,
        comment='Extraction parameters, version, configuration, etc.'
    )
    confidence_score = Column(
        Numeric(3, 2),
        nullable=True,
        comment='0-1 confidence score for this extraction'
    )
    
    source = relationship('Source', backref='lineage_records')
    
    __table_args__ = (
        CheckConstraint(
            "extraction_method IN ('manual', 'api', 'scraper', 'llm', 'parser', 'other') OR extraction_method IS NULL",
            name='check_extraction_method'
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name='check_lineage_confidence_score'
        ),
        {'comment': 'Data lineage tracking for source provenance'}
    )

