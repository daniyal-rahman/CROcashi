"""
USPTO Public PAIR processor for extracting patent application data.

Extracts:
- Patent entity (application number, title, dates, assignees)
- Company entities (from assignee information)
- Patent-company relationships
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

logger = logging.getLogger(__name__)


class USPTOPublicPairProcessor(BaseProcessor):
    """
    Processor for USPTO Public PAIR (Patent Application Information Retrieval) data.
    
    USPTO Public PAIR provides:
    - Patent application numbers
    - Patent titles and dates
    - Assignee information (companies)
    - Patent status
    """
    
    SOURCE_NAME = "uspto_public_pair"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from USPTO Public PAIR data."""
        return raw_data.get('application_number') or raw_data.get('patent_number') or raw_data.get('id', '')
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from USPTO Public PAIR record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'patents': [],
            'companies': []
        }
        
        try:
            patent = self._extract_patent(raw_data)
            if patent:
                entities['patents'].append(patent)
                self.metrics.entities_extracted += 1
            
            companies = self._extract_companies(raw_data)
            entities['companies'].extend(companies)
            self.metrics.entities_extracted += len(companies)
            
        except Exception as e:
            logger.error(f"Error extracting USPTO Public PAIR data: {e}")
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
        relationships = []
        
        patent_id = resolved_entities.get('patent')
        if not patent_id:
            patents = resolved_entities.get('patents', [])
            if isinstance(patents, list) and len(patents) > 0:
                patent_id = patents[0]
            elif isinstance(patents, UUID):
                patent_id = patents
        
        if not patent_id:
            return relationships
        
        patent_entity = id_to_entity.get(patent_id)
        if not patent_entity:
            return relationships
        
        # Patent-company relationships
        company_ids = resolved_entities.get('companies', [])
        if isinstance(company_ids, UUID):
            company_ids = [company_ids]
        elif not isinstance(company_ids, list):
            company_ids = []
        
        for company_id in company_ids:
            company_entity = id_to_entity.get(company_id)
            if company_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='patent_company',
                    source_entity=patent_entity,
                    target_entity=company_entity,
                    attributes={},
                    temporal={}
                ))
        
        return relationships
    
    def _extract_patent(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract patent entity from USPTO Public PAIR data."""
        patent_number = raw_data.get('patent_number') or raw_data.get('application_number', '')
        
        if not patent_number:
            logger.warning("Patent/application number missing from USPTO Public PAIR record")
            return None
        
        patent_date = self.extract_date_from_raw(raw_data, 'filing_date')
        publication_date = self.extract_date_from_raw(raw_data, 'publication_date')
        
        patent = ExtractedEntity(
            entity_type=EntityType.PATENT,
            name=raw_data.get('title', f"Patent Application {patent_number}"),
            identifiers={
                'patent_number': patent_number,
                'application_number': raw_data.get('application_number'),
                'patent_office': 'USPTO'
            },
            context={
                'title': raw_data.get('title'),
                'patent_office': 'USPTO',
                'filing_date': patent_date,
                'publication_date': publication_date,
                'status': raw_data.get('status', '')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=patent_number,
            raw_data=raw_data
        )
        
        return patent
    
    def _extract_companies(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract company entities from assignee information."""
        companies = []
        
        assignees = raw_data.get('assignees', [])
        if isinstance(assignees, str):
            assignees = [assignees]
        elif not isinstance(assignees, list):
            assignees = []
        
        for assignee in assignees:
            if isinstance(assignee, dict):
                company_name = assignee.get('name') or assignee.get('organization', '')
            else:
                company_name = str(assignee)
            
            if company_name and len(company_name) > 2:
                company = ExtractedEntity(
                    entity_type=EntityType.COMPANY,
                    name=self.normalize_company_name(company_name),
                    identifiers={},
                    context={
                        'role': 'patent_assignee',
                        'patent_office': 'USPTO'
                    },
                    source_name=self.SOURCE_NAME,
                    source_identifier=self.get_source_identifier(raw_data),
                    raw_data={'company_name': company_name}
                )
                companies.append(company)
        
        return companies
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        return bool(entities.get('patents'))
