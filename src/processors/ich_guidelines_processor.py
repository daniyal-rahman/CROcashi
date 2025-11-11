"""
ICH Guidelines processor for extracting international regulatory guidance data.

Extracts:
- Regulatory events (guideline publications)
"""
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, RelationshipExtraction
)

logger = logging.getLogger(__name__)


class ICHGuidelinesProcessor(BaseProcessor):
    """
    Processor for ICH (International Council for Harmonisation) Guidelines.
    
    ICH Guidelines provide:
    - Guideline titles and publication dates
    - Regulatory event (guideline publication)
    """
    
    SOURCE_NAME = "ich_guidelines"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from ICH Guidelines data."""
        return raw_data.get('url') or raw_data.get('guideline_id') or raw_data.get('text', '')[:100] or ''
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from ICH Guidelines record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'regulatory_events': []
        }
        
        try:
            event = self._extract_regulatory_event(raw_data)
            if event:
                entities['regulatory_events'].append(event)
                self.metrics.entities_extracted += 1
            
        except Exception as e:
            logger.error(f"Error extracting ICH Guidelines data: {e}")
            self.add_error(f"Extraction error: {e}")
        
        self.metrics.end_time = datetime.now()
        return entities
    
    def extract_relationships(
        self,
        raw_data: Dict[str, Any],
        resolved_entities: Dict[str, UUID],
        id_to_entity: Dict[UUID, ExtractedEntity]
    ) -> List[RelationshipExtraction]:
        """Extract relationships after entities are resolved."""
        return []
    
    def _extract_regulatory_event(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract regulatory event (guideline publication)."""
        publication_date = datetime.now().date()
        
        title = raw_data.get('text') or raw_data.get('title', '')
        event_name = f"ICH Guideline: {title[:100]}" if title else "ICH Guideline"
        
        event = ExtractedEntity(
            entity_type=EntityType.REGULATORY_EVENT,
            name=event_name,
            identifiers={},
            context={
                'event_type': 'guideline',
                'event_date': publication_date,
                'regulatory_body': 'ICH',
                'country': 'International',
                'description': title
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data=raw_data
        )
        
        return event
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        return bool(entities.get('regulatory_events'))
