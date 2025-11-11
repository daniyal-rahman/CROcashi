"""
WHO Outbreak News processor for extracting global health signals.

Extracts:
- Disease entities (outbreak diseases)
- Event entities (outbreak events)
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
from src.services.event_service import EventService
from src.services.lineage_service import LineageService

logger = logging.getLogger(__name__)


class WHOOutbreakNewsProcessor(BaseProcessor):
    """
    Processor for WHO Disease Outbreak News data.
    
    WHO Outbreak News provides:
    - Disease information (outbreak diseases)
    - Outbreak dates and locations
    - Event information (outbreak events)
    """
    
    SOURCE_NAME = "who_outbreak_news"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from WHO Outbreak News data."""
        return raw_data.get('link') or raw_data.get('title', '')[:100] or ''
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from WHO Outbreak News record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'diseases': []
        }
        
        try:
            disease = self._extract_disease(raw_data)
            if disease:
                entities['diseases'].append(disease)
                self.metrics.entities_extracted += 1
            
        except Exception as e:
            logger.error(f"Error extracting WHO Outbreak News data: {e}")
            self.add_error(f"Extraction error: {e}")
        
        self.metrics.end_time = datetime.now()
        return entities
    
    def extract_relationships(
        self,
        raw_data: Dict[str, Any],
        resolved_entities: Dict[str, UUID],
        id_to_entity: Dict[UUID, ExtractedEntity]
    ) -> List[RelationshipExtraction]:
        """Extract relationships and create Event entities for outbreaks."""
        relationships = []
        
        disease_id = resolved_entities.get('disease')
        if not disease_id:
            diseases = resolved_entities.get('diseases', [])
            if isinstance(diseases, list) and len(diseases) > 0:
                disease_id = diseases[0]
            elif isinstance(diseases, UUID):
                disease_id = diseases
        
        if not disease_id:
            return relationships
        
        try:
            event_service = EventService(self.session)
            lineage_service = LineageService(self.session)
            
            published_str = raw_data.get('published', '')
            outbreak_date = self._parse_date(published_str)
            
            if not outbreak_date:
                outbreak_date = datetime.now().date()
            
            source = lineage_service.get_or_create_source(
                source_name=self.SOURCE_NAME,
                source_type='regulatory'
            )
            
            event_data = {
                'title': raw_data.get('title', ''),
                'summary': raw_data.get('summary', ''),
                'link': raw_data.get('link', ''),
                'location': raw_data.get('location', '')
            }
            
            event = event_service.create_event(
                event_type='disease.outbreak',
                event_date=outbreak_date,
                entities_involved=[disease_id],
                event_data=event_data,
                source_id=source.source_id,
                confidence_score=0.9
            )
            
            self.session.flush()
            
        except Exception as e:
            logger.error(f"Error creating outbreak event: {e}")
            self.add_error(f"Event creation error: {e}")
        
        return relationships
    
    def _extract_disease(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract disease entity from outbreak news."""
        title = raw_data.get('title', '')
        summary = raw_data.get('summary', '')
        
        # Try to extract disease name from title or summary
        disease_name = None
        if title:
            # Common patterns: "Disease Name Outbreak" or "Outbreak of Disease Name"
            import re
            patterns = [
                r'([A-Z][a-zA-Z\s]+?)\s+outbreak',
                r'outbreak\s+of\s+([A-Z][a-zA-Z\s]+)',
                r'([A-Z][a-zA-Z\s]+?)\s+in\s+[A-Z]',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    disease_name = match.group(1).strip()
                    break
        
        if not disease_name and summary:
            # Try summary
            for pattern in patterns:
                match = re.search(pattern, summary[:200], re.IGNORECASE)
                if match:
                    disease_name = match.group(1).strip()
                    break
        
        if not disease_name:
            logger.warning("No disease name found in WHO Outbreak News")
            return None
        
        disease = ExtractedEntity(
            entity_type=EntityType.DISEASE,
            name=disease_name,
            identifiers={},
            context={
                'is_outbreak': True,
                'source': 'who_outbreak_news'
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'disease_name': disease_name, 'title': title}
        )
        
        return disease
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from outbreak news."""
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
        return bool(entities.get('diseases'))
