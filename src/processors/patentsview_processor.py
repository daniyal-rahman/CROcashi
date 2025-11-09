"""
PatentsView processor for extracting patent and company data.

Extracts:
- Patent entity (patent number, title, dates, assignees)
- Company entities (from assignee_organization field)
- Patent-company relationships (assignee ownership)
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


class PatentsViewProcessor(BaseProcessor):
    """
    Processor for PatentsView API data.
    
    PatentsView provides:
    - Unique patent numbers
    - Patent titles and dates
    - Assignee organizations (companies)
    - Patent metadata
    """
    
    SOURCE_NAME = "patentsview"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get patent number from PatentsView data."""
        return raw_data.get('patent_number', '')
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from PatentsView patent record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'patents': [],  # Will be converted to 'patent' (singular) by pipeline
            'companies': [],  # Will be stored as 'companies' (plural) by pipeline
            'drugs': [],  # Drug names extracted from patent titles
        }
        
        try:
            # Extract patent entity
            patent = self._extract_patent(raw_data)
            if patent:
                entities['patents'].append(patent)
                self.metrics.entities_extracted += 1
            
            # Extract company entities from assignees
            companies = self._extract_companies(raw_data)
            entities['companies'].extend(companies)
            self.metrics.entities_extracted += len(companies)
            
            # Extract drug entities from patent title
            drugs = self._extract_drugs_from_title(raw_data)
            entities['drugs'].extend(drugs)
            self.metrics.entities_extracted += len(drugs)
            
        except Exception as e:
            logger.error(f"Error extracting PatentsView data: {e}")
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
        
        # Pipeline converts 'patents' -> 'patent' (singular) if only one
        patent_id = resolved_entities.get('patent')
        if not patent_id:
            logger.warning("No patent ID found in resolved entities")
            return relationships
        
        # Get patent entity for relationship stubs
        patent_entity = id_to_entity.get(patent_id)
        if not patent_entity:
            patent_entity = self._make_patent_entity(raw_data)
        
        # Create patent-company relationships
        for company_id in resolved_entities.get('companies', []):
            company_entity = id_to_entity.get(company_id)
            if not company_entity:
                # Skip if company entity not found (shouldn't happen, but handle gracefully)
                logger.warning(f"Company entity not found in id_to_entity for company_id: {company_id}")
                continue
            relationships.append(RelationshipExtraction(
                relationship_type='patent_company',
                source_entity=patent_entity,
                target_entity=company_entity,
                attributes={
                    'ownership_type': 'assignee'
                },
                temporal={}
            ))
        
        # Create patent-drug relationships
        for drug_id in resolved_entities.get('drugs', []):
            drug_entity = id_to_entity.get(drug_id)
            if drug_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='patent_drug',
                    source_entity=patent_entity,
                    target_entity=drug_entity,
                    attributes={},
                    temporal={}
                ))
        
        return relationships
    
    def _extract_patent(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract patent entity from PatentsView data."""
        patent_number = raw_data.get('patent_number')
        
        if not patent_number:
            logger.warning("Patent number missing from record")
            return None
        
        # Parse patent date
        patent_date = self.extract_date_from_raw(raw_data, 'patent_date')
        
        # Extract assignees for context (will be used for relationships)
        # Store as list of company name strings for database (ARRAY(Text))
        assignees_raw = self._extract_assignee_list(raw_data)
        assignee_names = []
        for assignee in assignees_raw:
            if isinstance(assignee, str):
                assignee_names.append(assignee)
            elif isinstance(assignee, dict):
                # Extract company name from object
                org_name = assignee.get('organization') or assignee.get('name')
                if org_name and isinstance(org_name, str):
                    assignee_names.append(org_name)
        
        patent = ExtractedEntity(
            entity_type=EntityType.PATENT,
            name=raw_data.get('title', f"Patent {patent_number}"),
            identifiers={
                'patent_number': patent_number
            },
            context={
                'title': raw_data.get('title'),
                'patent_office': 'USPTO',
                'publication_date': patent_date,
                'assignees': assignee_names  # Store as list of strings for database
            },
            source_name=self.SOURCE_NAME,
            source_identifier=patent_number,
            raw_data=raw_data
        )
        
        return patent
    
    def _extract_companies(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract company entities from assignee_organization field."""
        companies = []
        
        assignees = self._extract_assignee_list(raw_data)
        
        for assignee in assignees:
            # Only extract company assignees, skip individuals
            if not isinstance(assignee, dict):
                # String assignee - treat as company
                company_name = assignee if isinstance(assignee, str) else str(assignee)
            elif assignee.get('type') == 'individual':
                # Skip individual assignees
                continue
            elif 'organization' in assignee:
                # Company assignee
                company_name = assignee.get('organization')
            else:
                # Try to extract name from other fields
                company_name = assignee.get('name') or assignee.get('assignee_organization')
            
            if not company_name or not isinstance(company_name, str):
                continue
            
            # Normalize company name
            company_name = self.normalize_company_name(company_name.strip())
            
            if not company_name:
                continue
            
            company = ExtractedEntity(
                entity_type=EntityType.COMPANY,
                name=company_name,
                identifiers={},
                context={
                    'role': 'patent_assignee',
                    'patent_number': raw_data.get('patent_number')
                },
                source_name=self.SOURCE_NAME,
                source_identifier=raw_data.get('patent_number', ''),
                raw_data={'company_name': company_name}
            )
            
            companies.append(company)
        
        return companies
    
    def _extract_assignee_list(self, raw_data: Dict[str, Any]) -> List[Any]:
        """
        Extract assignee list from raw data, handling multiple formats.
        
        Handles:
        - String: "Pfizer Inc."
        - Array of strings: ["Pfizer Inc.", "Merck & Co."]
        - Array of objects: [{"organization": "Pfizer", "type": "company"}, ...]
        """
        assignee_org = raw_data.get('assignee_organization')
        
        if not assignee_org:
            return []
        
        # If it's a string, convert to list
        if isinstance(assignee_org, str):
            return [assignee_org]
        
        # If it's already a list, return as-is
        if isinstance(assignee_org, list):
            return assignee_org
        
        # Fallback: try to extract from other fields
        return []
    
    def _make_patent_entity(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Helper to create patent entity stub for relationships."""
        patent_number = raw_data.get('patent_number', '')
        return ExtractedEntity(
            entity_type=EntityType.PATENT,
            name=raw_data.get('title', f"Patent {patent_number}"),
            identifiers={'patent_number': patent_number},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=patent_number
        )
    
    def _extract_drugs_from_title(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """
        Extract drug names from patent title using common drug name patterns.
        
        Args:
            raw_data: Raw patent data
            
        Returns:
            List of extracted drug entities
        """
        import re
        drugs = []
        
        title = raw_data.get('title', '')
        if not title or not isinstance(title, str):
            return drugs
        
        # Common drug suffixes
        drug_suffixes = [
            r'-mab\b',  # Monoclonal antibodies (e.g., trastuzumab)
            r'-nib\b',  # Kinase inhibitors (e.g., imatinib)
            r'-zumab\b',  # Humanized mAbs (e.g., bevacizumab)
            r'-tinib\b',  # Tyrosine kinase inhibitors (e.g., erlotinib)
            r'-olol\b',  # Beta blockers (e.g., propranolol)
            r'-pril\b',  # ACE inhibitors (e.g., lisinopril)
            r'-statin\b',  # Statins (e.g., atorvastatin)
            r'-prazole\b',  # PPIs (e.g., omeprazole)
            r'-cycline\b',  # Antibiotics (e.g., doxycycline)
            r'-cillin\b',  # Penicillins (e.g., amoxicillin)
        ]
        
        # Pattern to find capitalized words followed by drug suffixes
        # Look for patterns like "DrugName-mab" or "Drug Name-mab"
        title_words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:-[a-z]+)?\b', title)
        
        potential_drugs = []
        for word in title_words:
            # Check if word ends with a drug suffix
            for suffix_pattern in drug_suffixes:
                if re.search(suffix_pattern, word, re.IGNORECASE):
                    # Extract the base drug name (before the suffix)
                    base_name = re.sub(suffix_pattern, '', word, flags=re.IGNORECASE).strip()
                    if base_name:
                        potential_drugs.append(word)
                        break
        
        # Also look for common drug name patterns in title
        # Common drug prefixes/patterns
        drug_patterns = [
            r'\b[A-Z][a-z]+(?:-[A-Z][a-z]+)*\s+(?:injection|tablet|capsule|solution)\b',
            r'\b(?:anti|pro|pre|post)-?[A-Z][a-z]+\b',  # Anti-inflammatory, etc.
        ]
        
        for pattern in drug_patterns:
            matches = re.findall(pattern, title, re.IGNORECASE)
            potential_drugs.extend(matches)
        
        # Remove duplicates and normalize
        seen = set()
        for drug_name in potential_drugs:
            # Normalize drug name
            normalized = self.normalize_drug_name(drug_name)
            
            # Filter out common non-drug words
            non_drug_words = {
                'method', 'process', 'composition', 'compound', 'formulation',
                'treatment', 'therapy', 'disease', 'disorder', 'syndrome',
                'patient', 'subject', 'administration', 'dosage', 'dose'
            }
            
            if normalized.lower() in non_drug_words:
                continue
            
            # Skip if too short (likely not a drug name)
            if len(normalized) < 4:
                continue
            
            # Skip if already seen
            if normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            
            # Create drug entity
            drug = ExtractedEntity(
                entity_type=EntityType.DRUG,
                name=normalized,
                identifiers={},
                context={
                    'extraction_source': 'patent_title',
                    'patent_number': raw_data.get('patent_number'),
                    'original_text': drug_name
                },
                source_name=self.SOURCE_NAME,
                source_identifier=raw_data.get('patent_number', ''),
                raw_data={'drug_name': drug_name, 'title': title}
            )
            
            drugs.append(drug)
        
        return drugs
    
    def _make_company_entity(self, raw_data: Dict[str, Any], company_name: str) -> ExtractedEntity:
        """Helper to create company entity stub for relationships."""
        # CRITICAL: Normalize to match original extraction (for stub key matching)
        if company_name:
            company_name = self.normalize_company_name(company_name)
        return ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=raw_data.get('patent_number', '')
        )

