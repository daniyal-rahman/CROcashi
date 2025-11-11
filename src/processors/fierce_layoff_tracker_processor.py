"""
FierceBiotech Layoff Tracker processor for extracting employment distress signals.

Extracts:
- Company entities (companies with layoffs)
- Event entities (layoff events)
"""
import logging
import re
from datetime import datetime, date
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


class FierceLayoffTrackerProcessor(BaseProcessor):
    """
    Processor for FierceBiotech Layoff Tracker data.
    
    FierceBiotech Layoff Tracker provides:
    - Company information (companies with layoffs)
    - Layoff dates
    - Number of employees affected
    - Layoff reasons
    """
    
    SOURCE_NAME = "fierce_layoff_tracker"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from FierceBiotech layoff record."""
        return raw_data.get('url') or raw_data.get('title', '')[:100] or ''
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from FierceBiotech layoff record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'companies': []
        }
        
        try:
            company = self._extract_company(raw_data)
            if company:
                entities['companies'].append(company)
                self.metrics.entities_extracted += 1
            
        except Exception as e:
            logger.error(f"Error extracting FierceBiotech layoff data: {e}")
            self.add_error(f"Extraction error: {e}")
        
        self.metrics.end_time = datetime.now()
        return entities
    
    def extract_relationships(
        self,
        raw_data: Dict[str, Any],
        resolved_entities: Dict[str, UUID],
        id_to_entity: Dict[UUID, ExtractedEntity]
    ) -> List[RelationshipExtraction]:
        """Extract relationships and create Event entities for layoffs."""
        relationships = []
        
        company_id = resolved_entities.get('company')
        if not company_id:
            companies = resolved_entities.get('companies', [])
            if isinstance(companies, list) and len(companies) > 0:
                company_id = companies[0]
            elif isinstance(companies, UUID):
                company_id = companies
        
        if not company_id:
            return relationships
        
        try:
            event_service = EventService(self.session)
            lineage_service = LineageService(self.session)
            
            layoff_date_str = raw_data.get('layoff_date', '')
            layoff_date = self._parse_date(layoff_date_str)
            
            if not layoff_date:
                layoff_date = datetime.now().date()
            
            source = lineage_service.get_or_create_source(
                source_name=self.SOURCE_NAME,
                source_type='financial'
            )
            
            event_data = {
                'title': raw_data.get('title', ''),
                'employees_affected': raw_data.get('employees_affected'),
                'reason': raw_data.get('reason'),
                'url': raw_data.get('url', '')
            }
            
            event = event_service.create_event(
                event_type='corporate.layoff',
                event_date=layoff_date,
                entities_involved=[company_id],
                event_data=event_data,
                source_id=source.source_id,
                confidence_score=0.8
            )
            
            self.session.flush()
            
        except Exception as e:
            logger.error(f"Error creating layoff event: {e}")
            self.add_error(f"Event creation error: {e}")
        
        return relationships
    
    def _extract_company(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract company from layoff record."""
        title = raw_data.get('title', '')
        
        company_name = None
        if title:
            patterns = [
                r'^([A-Z][a-zA-Z\s&,\.]+(?:Inc\.?|LLC|Corp\.?|Ltd\.?|Pharmaceuticals?|Biotech|Therapeutics?))\s+',
                r'([A-Z][a-zA-Z\s&,\.]+(?:Inc\.?|LLC|Corp\.?|Ltd\.?|Pharmaceuticals?|Biotech|Therapeutics?))',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, title)
                if match:
                    company_name = match.group(1).strip()
                    break
        
        if not company_name:
            logger.warning("No company name found in FierceBiotech layoff record")
            return None
        
        company_name = self.normalize_company_name(company_name)
        
        company = ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={},
            context={
                'role': 'layoff_company',
                'source': 'fiercebiotech'
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'company_name': company_name, 'title': title}
        )
        
        return company
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from layoff record."""
        if not date_str:
            return None
        
        parsed = self.extract_date_from_raw({'date': date_str}, 'date')
        if parsed and hasattr(parsed, 'date'):
            return parsed.date()
        elif isinstance(parsed, date):
            return parsed
        
        return None
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        return bool(entities.get('companies'))
