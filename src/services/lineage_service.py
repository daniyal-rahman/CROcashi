"""
Lineage service for tracking data provenance.
"""
import logging
from datetime import datetime
from typing import Dict, Optional, Any
from uuid import UUID

from sqlalchemy.orm import Session

from database.models.lineage import DataLineage
from database.models.sources import Source

logger = logging.getLogger(__name__)


class LineageService:
    """Service for tracking data lineage and provenance."""
    
    def __init__(self, session: Session):
        """Initialize lineage service."""
        self.session = session
    
    def get_or_create_source(
        self,
        source_name: str,
        source_type: str = 'other',
        reliability_score: Optional[float] = None,
        update_frequency: Optional[str] = None
    ) -> Source:
        """
        Get or create a source record.
        
        Args:
            source_name: Name of the source (e.g., 'clinicaltrials_gov')
            source_type: Type of source (regulatory, literature, financial, etc.)
            reliability_score: Optional reliability score (0-1)
            update_frequency: Optional update frequency
            
        Returns:
            Source object
        """
        source = self.session.query(Source).filter(
            Source.source_name == source_name,
            Source.deleted_at.is_(None)
        ).first()
        
        if not source:
            source = Source(
                source_name=source_name,
                source_type=source_type,
                reliability_score=reliability_score,
                update_frequency=update_frequency,
                is_active=True
            )
            self.session.add(source)
            # Note: flush() is fine here - caller should commit the transaction
            # flush() makes the ID available without committing
            self.session.flush()
        
        return source
    
    def create_lineage_record(
        self,
        table_name: str,
        record_id: UUID,
        source_id: UUID,
        raw_data_snapshot: Optional[Dict[str, Any]] = None,
        extraction_method: Optional[str] = None,
        extraction_metadata: Optional[Dict[str, Any]] = None,
        confidence_score: Optional[float] = None,
        extracted_at: Optional[datetime] = None
    ) -> DataLineage:
        """
        Create a data lineage record.
        
        Args:
            table_name: Name of the table (e.g., 'companies', 'drugs', 'events')
            record_id: UUID of the record in that table
            source_id: Source ID
            raw_data_snapshot: Optional snapshot of original source data
            extraction_method: How data was extracted (api, scraper, llm, etc.)
            extraction_metadata: Optional extraction metadata
            confidence_score: Optional confidence score (0-1)
            extracted_at: When data was extracted (defaults to now)
            
        Returns:
            Created DataLineage object
        """
        if extracted_at is None:
            extracted_at = datetime.now()
        
        lineage = DataLineage(
            table_name=table_name,
            record_id=record_id,
            source_id=source_id,
            raw_data_snapshot=raw_data_snapshot,
            extraction_method=extraction_method,
            extraction_metadata=extraction_metadata,
            confidence_score=confidence_score,
            extracted_at=extracted_at
        )
        
        self.session.add(lineage)
        return lineage
    
    def get_lineage_for_record(
        self,
        table_name: str,
        record_id: UUID
    ) -> list[DataLineage]:
        """
        Get all lineage records for a specific record.
        
        Args:
            table_name: Name of the table
            record_id: UUID of the record
            
        Returns:
            List of DataLineage objects
        """
        return self.session.query(DataLineage).filter(
            DataLineage.table_name == table_name,
            DataLineage.record_id == record_id,
            DataLineage.deleted_at.is_(None)
        ).all()

