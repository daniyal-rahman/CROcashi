"""
ASCO (American Society of Clinical Oncology) conference abstracts processor.

Extracts:
- ConferencePresentation entity
- Company entities (from author affiliations)
- Drug entities (from abstract text)
- ClinicalTrial entities (from NCT IDs)
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
import re

from sqlalchemy.orm import Session

from database.models import Drug, ClinicalTrial
from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, RelationshipExtraction
)

logger = logging.getLogger(__name__)


class ASCOAbstractsProcessor(BaseProcessor):
    """
    Processor for ASCO conference abstracts.
    
    ASCO abstracts provide:
    - Conference presentation information
    - Trial results and updates
    - Drug efficacy and safety data
    - Early termination announcements
    - No-show detection (abstracts accepted but not presented)
    """
    
    SOURCE_NAME = "asco_abstracts"
    
    def __init__(self, session: Session):
        """Initialize ASCO abstracts processor."""
        super().__init__(session)
        self._drug_names_cache: Optional[set] = None
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get abstract ID from ASCO abstract data."""
        return raw_data.get('abstract_id', raw_data.get('abstract_url', ''))
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from ASCO abstract."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'conference_presentations': [],
            'companies': [],
            'drugs': [],
            'trials': []
        }
        
        try:
            # Extract conference presentation entity
            presentation = self._extract_presentation(raw_data)
            if presentation:
                entities['conference_presentations'].append(presentation)
                self.metrics.entities_extracted += 1
            
            # Extract company entities (from author affiliations)
            companies = self._extract_companies(raw_data)
            entities['companies'].extend(companies)
            self.metrics.entities_extracted += len(companies)
            
            # Extract drug entities
            drugs = self._extract_drugs(raw_data)
            entities['drugs'].extend(drugs)
            self.metrics.entities_extracted += len(drugs)
            
            # Extract trial entities (from NCT IDs)
            trials = self._extract_trials(raw_data)
            entities['trials'].extend(trials)
            self.metrics.entities_extracted += len(trials)
            
        except Exception as e:
            logger.error(f"Error extracting ASCO abstract data: {e}")
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
        
        # Get resolved presentation ID
        presentation_id = resolved_entities.get('presentation')
        if not presentation_id:
            presentations = resolved_entities.get('conference_presentations', [])
            if isinstance(presentations, list) and len(presentations) > 0:
                presentation_id = presentations[0]
            elif isinstance(presentations, UUID):
                presentation_id = presentations
        
        if not presentation_id:
            logger.warning("No presentation ID found in resolved entities")
            return relationships
        
        presentation_entity = id_to_entity.get(presentation_id)
        if not presentation_entity:
            return relationships
        
        # Presentation - Company relationships
        company_ids = resolved_entities.get('companies', [])
        if isinstance(company_ids, UUID):
            company_ids = [company_ids]
        elif not isinstance(company_ids, list):
            company_ids = []
        
        for company_id in company_ids:
            company_entity = id_to_entity.get(company_id)
            if company_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='presentation_company',
                    source_entity=presentation_entity,
                    target_entity=company_entity,
                    attributes={},
                    temporal={}
                ))
        
        # Presentation - Drug relationships
        drug_ids = resolved_entities.get('drugs', [])
        if isinstance(drug_ids, UUID):
            drug_ids = [drug_ids]
        elif not isinstance(drug_ids, list):
            drug_ids = []
        
        for drug_id in drug_ids:
            drug_entity = id_to_entity.get(drug_id)
            if drug_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='presentation_drug',
                    source_entity=presentation_entity,
                    target_entity=drug_entity,
                    attributes={},
                    temporal={}
                ))
        
        # Presentation - Trial relationships
        trial_ids = resolved_entities.get('trials', [])
        if not trial_ids:
            trial_id = resolved_entities.get('trial')
            if trial_id:
                trial_ids = [trial_id]
        
        if isinstance(trial_ids, UUID):
            trial_ids = [trial_ids]
        elif not isinstance(trial_ids, list):
            trial_ids = []
        
        for trial_id in trial_ids:
            trial_entity = id_to_entity.get(trial_id)
            if trial_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='presentation_trial',
                    source_entity=presentation_entity,
                    target_entity=trial_entity,
                    attributes={},
                    temporal={}
                ))
        
        return relationships
    
    def _extract_presentation(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract conference presentation entity from abstract data."""
        abstract_id = raw_data.get('abstract_id', '')
        title = raw_data.get('title', '')
        
        if not title:
            logger.warning("No title found in ASCO abstract")
            return None
        
        # Parse presentation date
        presentation_date = None
        presentation_date_str = raw_data.get('presentation_date')
        if presentation_date_str:
            presentation_date = self._parse_date(presentation_date_str)
        
        # Get conference name
        conference = raw_data.get('conference', 'ASCO')
        
        presentation = ExtractedEntity(
            entity_type=EntityType.CONFERENCE_PRESENTATION,
            name=title,
            identifiers={
                'abstract_id': abstract_id,
                'abstract_number': self._extract_abstract_number(abstract_id)
            },
            context={
                'conference': conference,  # Used to look up Conference entity
                'title': title,
                'abstract_text': raw_data.get('abstract_text', ''),
                'authors': raw_data.get('authors', []),
                'presentation_type': raw_data.get('presentation_type'),
                'presentation_date': presentation_date,
                'status': raw_data.get('status', 'accepted'),
                'session': raw_data.get('session'),
            },
            source_name=self.SOURCE_NAME,
            source_identifier=abstract_id,
            raw_data=raw_data
        )
        
        return presentation
    
    def _extract_companies(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract company entities from author affiliations."""
        companies = []
        
        companies_mentioned = raw_data.get('companies', [])
        if not isinstance(companies_mentioned, list):
            if isinstance(companies_mentioned, str):
                companies_mentioned = [companies_mentioned]
            elif companies_mentioned is None:
                companies_mentioned = []
            else:
                logger.warning(f"Unexpected type for companies: {type(companies_mentioned)}, converting to list")
                companies_mentioned = [str(companies_mentioned)]
        
        for company_name in companies_mentioned:
            if not company_name or len(company_name) < 3:
                continue
            
            normalized_name = self.normalize_company_name(company_name)
            
            company = ExtractedEntity(
                entity_type=EntityType.COMPANY,
                name=normalized_name,
                identifiers={},
                context={
                    'role': 'abstract_affiliation',
                    'source': 'author_affiliation'
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'company_name': company_name}
            )
            
            companies.append(company)
        
        return companies
    
    def _extract_drugs(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract drug entities from abstract."""
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
        
        # Also search abstract text for known drug names
        abstract_text = raw_data.get('abstract_text', '')
        drug_names_from_db = self._get_all_drug_names()
        
        # Combine both sources
        all_drug_names = set(drugs_mentioned)
        
        # Search text for known drug names
        if abstract_text and drug_names_from_db:
            text_lower = abstract_text.lower()
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
                    'mention_context': 'conference_abstract',
                    'source': 'drugs_mentioned' if drug_name in drugs_mentioned else 'text_extraction'
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'drug_name': drug_name}
            )
            
            drugs.append(drug)
        
        return drugs
    
    def _extract_trials(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract trial entities from NCT IDs in abstract."""
        trials = []
        
        nct_ids = raw_data.get('nct_ids', [])
        if not isinstance(nct_ids, list):
            if isinstance(nct_ids, str):
                nct_ids = [nct_ids]
            elif nct_ids is None:
                nct_ids = []
            else:
                logger.warning(f"Unexpected type for nct_ids: {type(nct_ids)}, converting to list")
                nct_ids = [str(nct_ids)]
        
        # Also search abstract text for NCT IDs
        abstract_text = raw_data.get('abstract_text', '')
        if abstract_text:
            nct_pattern = r'NCT\d{8}'
            nct_matches = re.findall(nct_pattern, abstract_text, re.IGNORECASE)
            nct_ids.extend(nct_matches)
        
        # Remove duplicates
        nct_ids = list(set(nct_ids))
        
        # Create trial entities
        for nct_id in nct_ids:
            if not nct_id:
                continue
            
            trial = ExtractedEntity(
                entity_type=EntityType.TRIAL,
                name=f"Trial {nct_id}",
                identifiers={
                    'nct_id': nct_id.upper()
                },
                context={
                    'mention_context': 'conference_abstract',
                    'source': 'nct_id_extraction'
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'nct_id': nct_id}
            )
            
            trials.append(trial)
        
        return trials
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date from various formats."""
        if not date_str or not isinstance(date_str, str):
            return None
        
        # Use base processor helper first
        parsed = self.extract_date_from_raw({'presentation_date': date_str}, 'presentation_date')
        if parsed:
            if isinstance(parsed, datetime):
                return parsed.date()
            return parsed
        
        # Fallback to additional formats not covered by base helper
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
    
    def _extract_abstract_number(self, abstract_id: str) -> str:
        """Extract abstract number from abstract ID."""
        if not abstract_id or not isinstance(abstract_id, str):
            return abstract_id or ''
        
        # Try to extract number from formats like "ASCO-2024-12345" or "12345"
        # Look for trailing number after last dash
        match = re.search(r'-(\d+)$', abstract_id)
        if match:
            return match.group(1)
        
        # If no dash, return full ID
        return abstract_id
    
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

