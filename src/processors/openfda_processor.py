"""
OpenFDA processor for extracting drug label data.

Extracts:
- Drug entity (brand name, generic name, NDC codes)
- Company entities (manufacturers)
- Disease entities (indications)
- Drug-company relationships (manufacturer)
- Drug-indication relationships
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


class OpenFDAProcessor(BaseProcessor):
    """
    Processor for OpenFDA drug label data.
    
    OpenFDA provides:
    - Drug labels with brand/generic names
    - Manufacturer information
    - Indications and usage
    - Product NDC codes
    - SPL IDs (unique per label)
    """
    
    SOURCE_NAME = "openfda"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from OpenFDA data."""
        # Try spl_id first (unique per label)
        spl_id = raw_data.get('spl_id')
        if spl_id:
            return spl_id
        
        # Fallback to product_ndc from openfda wrapper
        openfda = raw_data.get('openfda', {})
        if isinstance(openfda, dict):
            product_ndc = openfda.get('product_ndc')
            if isinstance(product_ndc, list) and len(product_ndc) > 0:
                return product_ndc[0]
            elif isinstance(product_ndc, str):
                return product_ndc
        
        return ''
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from OpenFDA drug label record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'drugs': [],
            'companies': [],
            'diseases': [],
        }
        
        try:
            # Extract drug entity
            drug = self._extract_drug(raw_data)
            if drug:
                entities['drugs'].append(drug)
                self.metrics.entities_extracted += 1
            
            # Extract company entities (manufacturers)
            companies = self._extract_companies(raw_data)
            entities['companies'].extend(companies)
            self.metrics.entities_extracted += len(companies)
            
            # Extract indication diseases
            diseases = self._extract_indications(raw_data)
            entities['diseases'].extend(diseases)
            self.metrics.entities_extracted += len(diseases)
            
        except Exception as e:
            logger.error(f"Error extracting OpenFDA data: {e}")
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
        
        # Get drug ID (use first if multiple)
        drug_ids = resolved_entities.get('drugs', [])
        drug_id = drug_ids[0] if drug_ids else None
        
        if not drug_id:
            logger.warning("No drug ID found in resolved entities")
            return relationships
        
        # Get drug entity for relationship stubs
        drug_entity = id_to_entity.get(drug_id)
        if not drug_entity:
            drug_entity = self._make_drug_entity(raw_data)
        
        # Company-drug relationships (manufacturers)
        for company_id in resolved_entities.get('companies', []):
            company_entity = id_to_entity.get(company_id)
            if not company_entity:
                # Skip if company entity not found (shouldn't happen, but handle gracefully)
                logger.warning(f"Company entity not found in id_to_entity for company_id: {company_id}")
                continue
            relationships.append(RelationshipExtraction(
                relationship_type='company_drug',
                source_entity=company_entity,
                target_entity=drug_entity,
                attributes={
                    'relationship_type': 'developer'  # Changed from 'manufacturer' - not in allowed values
                },
                temporal={}
            ))
        
        # Drug-indication relationships
        for disease_id in resolved_entities.get('diseases', []):
            disease_entity = id_to_entity.get(disease_id)
            if not disease_entity:
                # Try to create stub from raw data (fallback)
                # This shouldn't happen if pipeline works correctly
                continue
            relationships.append(RelationshipExtraction(
                relationship_type='drug_indication',
                source_entity=drug_entity,
                target_entity=disease_entity,
                attributes={
                    'approved': True
                },
                temporal={}
            ))
        
        return relationships
    
    def _extract_drug(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract drug entity from OpenFDA data."""
        openfda = raw_data.get('openfda', {})
        if not isinstance(openfda, dict):
            openfda = {}
        
        # Extract brand name (preferred) or generic name
        brand_names = openfda.get('brand_name', [])
        generic_names = openfda.get('generic_name', [])
        
        # Safely extract first string value from arrays
        brand_name = None
        if isinstance(brand_names, list) and len(brand_names) > 0:
            brand_name = brand_names[0] if isinstance(brand_names[0], str) else None
        
        generic_name = None
        if isinstance(generic_names, list) and len(generic_names) > 0:
            generic_name = generic_names[0] if isinstance(generic_names[0], str) else None
        
        # Use brand name as primary if available, otherwise generic
        primary_name = brand_name if brand_name else generic_name
        
        if not primary_name:
            logger.warning("No drug name found in OpenFDA record")
            return None
        
        # Normalize names
        primary_name = self.normalize_drug_name(primary_name)
        if generic_name:
            generic_name = self.normalize_drug_name(generic_name)
        
        # Extract product NDC
        product_ndc = openfda.get('product_ndc', [])
        if isinstance(product_ndc, list) and len(product_ndc) > 0:
            product_ndc = product_ndc[0] if isinstance(product_ndc[0], str) else None
        elif not isinstance(product_ndc, str):
            product_ndc = None
        
        # Extract spl_id
        spl_id = raw_data.get('spl_id')
        
        drug = ExtractedEntity(
            entity_type=EntityType.DRUG,
            name=primary_name,
            identifiers={
                'product_ndc': product_ndc,
                'spl_id': spl_id
            } if product_ndc or spl_id else {},
            context={
                'brand_name': brand_name,
                'generic_name': generic_name,
                'product_ndc': product_ndc,
                'spl_id': spl_id
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data=raw_data
        )
        
        return drug
    
    def _extract_companies(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract company entities from manufacturer fields."""
        companies = []
        openfda = raw_data.get('openfda', {})
        
        if not isinstance(openfda, dict):
            return companies
        
        # Extract manufacturer names (array)
        manufacturer_names = openfda.get('manufacturer_name', [])
        if not isinstance(manufacturer_names, list):
            manufacturer_names = [manufacturer_names] if manufacturer_names else []
        
        for manufacturer_name in manufacturer_names:
            if not manufacturer_name or not isinstance(manufacturer_name, str):
                continue
            
            # Normalize company name
            company_name = self.normalize_company_name(manufacturer_name.strip())
            if not company_name:
                continue
            
            company = ExtractedEntity(
                entity_type=EntityType.COMPANY,
                name=company_name,
                identifiers={},
                context={
                    'role': 'manufacturer',
                    'spl_id': raw_data.get('spl_id')
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'company_name': company_name}
            )
            
            companies.append(company)
        
        return companies
    
    def _extract_indications(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract disease entities from indications_and_usage field."""
        diseases = []
        
        # Try to get indications from openfda wrapper first
        openfda = raw_data.get('openfda', {})
        if isinstance(openfda, dict):
            indication_list = openfda.get('indication_and_usage', [])
            if isinstance(indication_list, list) and len(indication_list) > 0:
                # Process all indications (not just first) to capture multiple diseases
                for indication_text in indication_list:
                    if isinstance(indication_text, str):
                        disease = self._parse_indication_text(indication_text, raw_data)
                        if disease:
                            diseases.append(disease)
        
        # Fallback to top-level indications_and_usage field
        if not diseases:
            indications = raw_data.get('indications_and_usage', [])
            if isinstance(indications, list) and len(indications) > 0:
                # Process all indications to capture multiple diseases
                for indication_text in indications:
                    if isinstance(indication_text, str):
                        disease = self._parse_indication_text(indication_text, raw_data)
                        if disease:
                            diseases.append(disease)
        
        return diseases
    
    def _parse_indication_text(self, text: str, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """
        Parse indication text to extract disease name.
        
        This is a simple implementation - in production, you might want
        more sophisticated NLP or entity extraction.
        """
        if not text or not isinstance(text, str):
            return None
        
        # Simple extraction: look for common patterns
        # This is a placeholder - real implementation would use NLP
        text = text.strip()
        if len(text) < 3:
            return None
        
        # Use first sentence or first 100 chars as disease name
        # This is very basic - real implementation should extract actual disease names
        disease_name = text.split('.')[0].strip()
        if len(disease_name) > 200:
            disease_name = disease_name[:200]
        
        if not disease_name:
            return None
        
        # Basic normalization (strip and title case)
        disease_name = disease_name.strip()
        if not disease_name:
            return None
        
        disease = ExtractedEntity(
            entity_type=EntityType.DISEASE,
            name=disease_name,
            identifiers={},
            context={
                'source': 'openfda_indication',
                'extraction_method': 'simple_text_parsing'
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'indication_text': text[:500]}  # Store first 500 chars
        )
        
        return disease
    
    def _make_drug_entity(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Helper to create drug entity stub for relationships."""
        openfda = raw_data.get('openfda', {})
        if not isinstance(openfda, dict):
            openfda = {}
        
        brand_names = openfda.get('brand_name', [])
        generic_names = openfda.get('generic_name', [])
        
        # Safely extract first string value from arrays
        brand_name = None
        if isinstance(brand_names, list) and len(brand_names) > 0:
            brand_name = brand_names[0] if isinstance(brand_names[0], str) else None
        
        generic_name = None
        if isinstance(generic_names, list) and len(generic_names) > 0:
            generic_name = generic_names[0] if isinstance(generic_names[0], str) else None
        
        primary_name = brand_name if brand_name else generic_name
        if not primary_name:
            # Don't create entity with "Unknown Drug" - return None
            # This should not happen if _extract_drug worked, but handle gracefully
            logger.warning("No drug name found in _make_drug_entity fallback")
            return None
        
        # CRITICAL: Normalize name to match original extraction (for stub key matching)
        primary_name = self.normalize_drug_name(primary_name)
        
        # CRITICAL: Include identifiers to match original extraction (for stub key matching)
        product_ndc = openfda.get('product_ndc', [])
        if isinstance(product_ndc, list) and len(product_ndc) > 0:
            product_ndc = product_ndc[0] if isinstance(product_ndc[0], str) else None
        elif not isinstance(product_ndc, str):
            product_ndc = None
        
        spl_id = raw_data.get('spl_id')
        
        return ExtractedEntity(
            entity_type=EntityType.DRUG,
            name=primary_name,
            identifiers={
                'product_ndc': product_ndc,
                'spl_id': spl_id
            } if product_ndc or spl_id else {},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data)
        )
    
    def _make_company_entity(self, raw_data: Dict[str, Any], company_name: str) -> ExtractedEntity:
        """Helper to create company entity stub for relationships."""
        return ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data)
        )

