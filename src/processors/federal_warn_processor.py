"""
Federal WARN Notices processor for extracting financial distress signals via layoffs.

Extracts:
- Company entity (company issuing WARN notice)
- Event entity (unified event stream) for layoff event
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, RelationshipExtraction
)
from src.services.event_service import EventService
from src.services.lineage_service import LineageService

logger = logging.getLogger(__name__)


class FederalWARNProcessor(BaseProcessor):
    """
    Processor for Federal WARN Notices.
    
    Federal WARN Notices provide:
    - Company information (issuing layoff notice)
    - Notice date and effective date
    - Number of employees affected
    - Location/facility information
    - Reason for layoff
    """
    
    SOURCE_NAME = "federal_warn"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get notice ID from WARN notice data."""
        return raw_data.get('notice_id', raw_data.get('notice_url', ''))
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from WARN notice."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'companies': []
        }
        
        try:
            # Extract company entity
            company = self._extract_company(raw_data)
            if company:
                entities['companies'].append(company)
                self.metrics.entities_extracted += 1
            
        except Exception as e:
            logger.error(f"Error extracting Federal WARN notice data: {e}")
            self.add_error(f"Extraction error: {e}")
        
        self.metrics.end_time = datetime.now()
        return entities
    
    def extract_relationships(
        self,
        raw_data: Dict[str, Any],
        resolved_entities: Dict[str, UUID],
        id_to_entity: Dict[UUID, ExtractedEntity]
    ) -> List[RelationshipExtraction]:
        """
        Extract relationships and create Event entities for layoffs.
        
        Note: WARN notices create Event entities (unified event stream),
        not RegulatoryEvent entities, since they're financial/corporate events.
        """
        relationships = []
        
        # Get resolved company ID
        company_id = resolved_entities.get('company')
        if not company_id:
            companies = resolved_entities.get('companies', [])
            if isinstance(companies, list) and len(companies) > 0:
                company_id = companies[0]
            elif isinstance(companies, UUID):
                company_id = companies
        
        if not company_id:
            logger.warning("No company ID found in resolved entities for WARN notice")
            return relationships
        
        # Create Event entity directly using EventService
        try:
            event_service = EventService(self.session)
            lineage_service = LineageService(self.session)
            
            # Parse notice date
            notice_date_str = raw_data.get('notice_date', '')
            notice_date = self._parse_warn_date(notice_date_str)
            
            # If no date, use current date as fallback (required field)
            if not notice_date:
                logger.warning(f"Could not parse notice_date '{notice_date_str}' for WARN notice {raw_data.get('notice_id', 'unknown')}, using current date as fallback")
                notice_date = datetime.now().date()
            
            # Validate notice_id exists
            notice_id = raw_data.get('notice_id', '')
            if not notice_id:
                logger.error("Cannot create Event without notice_id")
                return relationships
            
            # Get source ID
            source = lineage_service.get_or_create_source(
                source_name=self.SOURCE_NAME,
                source_type='financial'  # WARN notices are financial signals
            )
            
            # Build event data
            event_data = {
                'notice_id': raw_data.get('notice_id', ''),
                'employees_affected': raw_data.get('employees_affected'),
                'location': raw_data.get('location'),
                'facility_name': raw_data.get('facility_name'),
                'reason': raw_data.get('reason'),
                'effective_date': raw_data.get('effective_date'),
                'notice_url': raw_data.get('notice_url', '')
            }
            
            # Create unified event
            event = event_service.create_event(
                event_type='corporate.layoff',  # Hierarchical event type
                event_date=notice_date,
                entities_involved=[company_id],
                event_data=event_data,
                source_id=source.source_id,
                confidence_score=1.0  # WARN notices are official, high confidence
            )
            
            # Flush to get event ID
            self.session.flush()
            
            logger.debug(f"Created layoff event {event.event_id} for company {company_id}")
            
        except Exception as e:
            logger.error(f"Error creating layoff event: {e}")
            self.add_error(f"Event creation error: {e}")
        
        return relationships
    
    def _extract_company(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract company (issuing WARN notice) from notice data."""
        company_name = raw_data.get('company_name', '')
        
        if not company_name:
            logger.warning("No company name found in Federal WARN notice")
            return None
        
        # Normalize company name
        company_name = self.normalize_company_name(company_name)
        
        company = ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={},
            context={
                'role': 'warn_notice_issuer',
                'location': raw_data.get('location'),
                'facility_name': raw_data.get('facility_name')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'company_name': company_name}
        )
        
        return company
    
    def _parse_warn_date(self, date_str: str) -> Optional[datetime]:
        """Parse date from WARN notice (various formats)."""
        if not date_str or not isinstance(date_str, str):
            return None
        
        # Use base processor helper first
        parsed = self.extract_date_from_raw({'notice_date': date_str}, 'notice_date')
        if parsed:
            if isinstance(parsed, datetime):
                return parsed.date()
            return parsed
        
        # Fallback to additional formats
        date_formats = [
            '%m/%d/%Y',
            '%m-%d-%Y',
            '%B %d, %Y',
            '%b %d, %Y'
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except (ValueError, AttributeError):
                continue
        
        return None

