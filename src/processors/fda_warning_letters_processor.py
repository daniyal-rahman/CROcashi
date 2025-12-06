"""
FDA Warning Letters processor for extracting regulatory compliance failures.

Extracts:
- Company entity (recipient of warning letter)
- Drug entities (from drugs_mentioned or text extraction)
- RegulatoryEvent entity (compliance failure event)
"""
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from database.models import Drug
from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, RelationshipExtraction
)

logger = logging.getLogger(__name__)


class FDAWarningLettersProcessor(BaseProcessor):
    """
    Processor for FDA Warning Letters.
    
    FDA Warning Letters provide:
    - Company information (recipient)
    - Issue date
    - Violation types (GMP violations, data integrity, etc.)
    - Drug/product mentions
    - Facility information
    """
    
    SOURCE_NAME = "fda_warning_letters"
    
    def __init__(self, session: Session):
        """Initialize FDA Warning Letters processor."""
        super().__init__(session)
        self._drug_names_cache: Optional[set] = None
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get letter ID from warning letter data."""
        return raw_data.get('letter_id', raw_data.get('letter_url', ''))
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from FDA Warning Letter."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'companies': [],
            'drugs': [],
            'regulatory_events': []
        }
        
        try:
            # Extract company entity
            company = self._extract_company(raw_data)
            if company:
                entities['companies'].append(company)
                self.metrics.entities_extracted += 1
            
            # Extract drug entities
            drugs = self._extract_drugs(raw_data)
            entities['drugs'].extend(drugs)
            self.metrics.entities_extracted += len(drugs)
            
            # Extract regulatory event
            event = self._extract_regulatory_event(raw_data)
            if event:
                entities['regulatory_events'].append(event)
                self.metrics.entities_extracted += 1
            
        except Exception as e:
            logger.error(f"Error extracting FDA Warning Letter data: {e}")
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
        
        # Get resolved entity IDs
        company_id = resolved_entities.get('company')
        if not company_id:
            companies = resolved_entities.get('companies', [])
            if isinstance(companies, list) and len(companies) > 0:
                company_id = companies[0]
            elif isinstance(companies, UUID):
                company_id = companies
        
        event_ids = resolved_entities.get('regulatory_events', [])
        if isinstance(event_ids, UUID):
            event_ids = [event_ids]
        elif not isinstance(event_ids, list):
            event_ids = []
        
        # Regulatory event - company relationship
        for event_id in event_ids:
            event_entity = id_to_entity.get(event_id)
            if not event_entity or not company_id:
                continue
            
            company_entity = id_to_entity.get(company_id)
            if company_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='regulatory_company_event',
                    source_entity=event_entity,
                    target_entity=company_entity,
                    attributes={},
                    temporal={}
                ))
        
        # Regulatory event - drug relationships
        for event_id in event_ids:
            event_entity = id_to_entity.get(event_id)
            if not event_entity:
                continue
            
            for drug_id in resolved_entities.get('drugs', []):
                drug_entity = id_to_entity.get(drug_id)
                if drug_entity:
                    relationships.append(RelationshipExtraction(
                        relationship_type='regulatory_drug_event',
                        source_entity=event_entity,
                        target_entity=drug_entity,
                        attributes={},
                        temporal={}
                    ))
        
        return relationships
    
    def _extract_company(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract company (recipient) from warning letter data."""
        company_name = raw_data.get('company_name', '')
        
        if not company_name:
            logger.warning("No company name found in FDA Warning Letter")
            return None
        
        # Normalize company name
        company_name = self.normalize_company_name(company_name)
        
        company = ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={},
            context={
                'role': 'warning_letter_recipient',
                'facility_name': raw_data.get('facility_name')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'company_name': company_name}
        )
        
        return company
    
    def _extract_drugs(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract drug entities from warning letter."""
        drugs = []
        
        # Get drugs from drugs_mentioned field
        drugs_mentioned = raw_data.get('drugs_mentioned', [])
        if not isinstance(drugs_mentioned, list):
            if isinstance(drugs_mentioned, str):
                drugs_mentioned = [drugs_mentioned]
            elif drugs_mentioned is None:
                drugs_mentioned = []
            else:
                logger.warning(f"Unexpected type for drugs_mentioned: {type(drugs_mentioned)}, converting to list")
                drugs_mentioned = [str(drugs_mentioned)]
        
        # Also search letter text for known drug names
        letter_text = raw_data.get('letter_text', '')
        drug_names_from_db = self._get_all_drug_names()
        
        # Combine both sources
        all_drug_names = set(drugs_mentioned)
        
        # Search text for known drug names
        if letter_text and drug_names_from_db:
            text_lower = letter_text.lower()
            for drug_name in drug_names_from_db:
                if drug_name.lower() in text_lower:
                    all_drug_names.add(drug_name)
        
        # Create drug entities
        for drug_name in all_drug_names:
            if not drug_name or len(drug_name) < 3:
                continue
            
            normalized_name = self.normalize_drug_name(drug_name)
            
            drug = ExtractedEntity(
                entity_type=EntityType.DRUG,
                name=normalized_name,
                identifiers={},
                context={
                    'mention_context': 'warning_letter',
                    'source': 'drugs_mentioned' if drug_name in drugs_mentioned else 'text_extraction'
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'drug_name': drug_name}
            )
            
            drugs.append(drug)
        
        return drugs
    
    def _extract_regulatory_event(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract regulatory event (compliance failure) from warning letter."""
        letter_id = raw_data.get('letter_id', '')
        issue_date_str = raw_data.get('issue_date', '')
        
        if not letter_id:
            return None
        
        # Parse issue date
        issue_date = None
        if issue_date_str:
            issue_date = self._parse_warning_letter_date(issue_date_str)
        
        # If no date, use current date as fallback (required field)
        if not issue_date:
            logger.warning(f"Could not parse issue_date '{issue_date_str}' for warning letter {letter_id}, using current date as fallback")
            issue_date = datetime.now().date()
        
        violation_types = raw_data.get('violation_types', [])
        facility_name = raw_data.get('facility_name', '')
        
        # Create description
        description_parts = [f"FDA Warning Letter issued to {raw_data.get('company_name', 'Company')}"]
        if facility_name:
            description_parts.append(f"at facility: {facility_name}")
        if violation_types:
            description_parts.append(f"Violations: {', '.join(violation_types)}")
        
        description = ". ".join(description_parts)
        
        event = ExtractedEntity(
            entity_type=EntityType.REGULATORY_EVENT,
            name=f"FDA Warning Letter: {letter_id}",
            identifiers={},
            context={
                'event_type': 'rejection',  # Warning letters are a form of regulatory rejection
                'event_date': issue_date,
                'regulatory_body': 'FDA',
                'country': 'US',
                'description': description,
                'violation_types': violation_types,
                'facility_name': facility_name,
                'letter_url': raw_data.get('letter_url', '')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=letter_id,
            raw_data=raw_data
        )
        
        return event
    
    def _parse_warning_letter_date(self, date_str: str) -> Optional[datetime]:
        """Parse date from warning letter (various formats)."""
        if not date_str or not isinstance(date_str, str):
            return None
        
        # Use base processor helper first
        parsed = self.extract_date_from_raw({'issue_date': date_str}, 'issue_date')
        if parsed:
            if isinstance(parsed, datetime):
                return parsed.date()
            return parsed
        
        # Fallback to additional formats not covered by base helper
        date_formats = [
            '%m/%d/%Y',
            '%m-%d-%Y',
            '%B %d, %Y',
            '%b %d, %Y',
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except (ValueError, AttributeError):
                continue
        
        return None
    
    def _get_all_drug_names(self) -> set:
        """Get all drug names from database for text search."""
        if self._drug_names_cache is not None:
            return self._drug_names_cache
        
        drug_names = set()
        
        try:
            # Query all drugs from database
            drugs = self.session.query(Drug).all()
            
            for drug in drugs:
                # Add primary name
                if drug.primary_name:
                    normalized = self.normalize_drug_name(drug.primary_name)
                    drug_names.add(normalized)
                
                # Add generic name
                if drug.generic_name:
                    normalized = self.normalize_drug_name(drug.generic_name)
                    drug_names.add(normalized)
                
                # Add aliases
                if drug.aliases:
                    for alias in drug.aliases:
                        if alias:
                            normalized = self.normalize_drug_name(alias)
                            drug_names.add(normalized)
            
            self._drug_names_cache = drug_names
            logger.info(f"Loaded {len(drug_names)} drug names for text search")
            
        except Exception as e:
            logger.error(f"Error loading drug names from database: {e}")
            drug_names = set()
        
        return drug_names

