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
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
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
    
    # Common disease synonyms/abbreviations for normalization
    DISEASE_SYNONYMS = {
        'htn': 'hypertension',
        'dm': 'diabetes mellitus',
        't2dm': 'type 2 diabetes mellitus',
        't1dm': 'type 1 diabetes mellitus',
        'niddm': 'type 2 diabetes mellitus',
        'iddm': 'type 1 diabetes mellitus',
        'mi': 'myocardial infarction',
        'cad': 'coronary artery disease',
        'chf': 'congestive heart failure',
        'copd': 'chronic obstructive pulmonary disease',
        'uti': 'urinary tract infection',
        'uri': 'upper respiratory infection',
        'gerd': 'gastroesophageal reflux disease',
        'ra': 'rheumatoid arthritis',
        'oa': 'osteoarthritis',
        'ms': 'multiple sclerosis',
        'als': 'amyotrophic lateral sclerosis',
        'hiv': 'human immunodeficiency virus infection',
        'aids': 'acquired immunodeficiency syndrome',
        'tb': 'tuberculosis',
        'dvt': 'deep vein thrombosis',
        'pe': 'pulmonary embolism',
        'afib': 'atrial fibrillation',
        'nsclc': 'non-small cell lung cancer',
        'sclc': 'small cell lung cancer',
        'cml': 'chronic myeloid leukemia',
        'aml': 'acute myeloid leukemia',
        'all': 'acute lymphoblastic leukemia',
        'cll': 'chronic lymphocytic leukemia',
        'hcc': 'hepatocellular carcinoma',
        'rcc': 'renal cell carcinoma',
        'bph': 'benign prostatic hyperplasia',
        'ibs': 'irritable bowel syndrome',
        'ibd': 'inflammatory bowel disease',
        'ckd': 'chronic kidney disease',
        'esrd': 'end-stage renal disease',
        'nash': 'nonalcoholic steatohepatitis',
        'nafld': 'nonalcoholic fatty liver disease',
        'pcos': 'polycystic ovary syndrome',
        'adhd': 'attention deficit hyperactivity disorder',
        'ptsd': 'post-traumatic stress disorder',
        'ocd': 'obsessive-compulsive disorder',
        'gad': 'generalized anxiety disorder',
        'mdd': 'major depressive disorder',
    }

    # Words that indicate the text is NOT a disease name
    NON_DISEASE_WORDS = {
        'indicated', 'indication', 'indications', 'treatment', 'use', 'uses',
        'used', 'using', 'therapy', 'management', 'prevention', 'prophylaxis',
        'relief', 'control', 'reduction', 'maintenance', 'adjunct', 'adjunctive',
        'supplement', 'supplemental', 'combination', 'monotherapy', 'adults',
        'children', 'pediatric', 'patients', 'persons', 'individuals', 'people',
        'temporarily', 'symptomatic', 'symptoms', 'associated', 'due', 'caused',
        'following', 'including', 'such', 'other', 'various', 'certain', 'some',
        'acute', 'chronic', 'mild', 'moderate', 'severe', 'serious', 'life-threatening',
        'handwashing', 'decrease', 'bacteria', 'skin', 'hands', 'antiseptic',
        'pain', 'and', 'or',  # Filter out generic symptom phrases
    }

    def _extract_indications(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract disease entities from indications_and_usage field."""
        diseases = []
        seen_diseases: Set[str] = set()  # Track to avoid duplicates

        # Collect all indication texts
        indication_texts = []

        # Try to get indications from openfda wrapper first
        openfda = raw_data.get('openfda', {})
        if isinstance(openfda, dict):
            indication_list = openfda.get('indication_and_usage', [])
            if isinstance(indication_list, list):
                for text in indication_list:
                    if isinstance(text, str) and text.strip():
                        indication_texts.append(text)

        # Also check top-level indications_and_usage field
        indications = raw_data.get('indications_and_usage', [])
        if isinstance(indications, list):
            for text in indications:
                if isinstance(text, str) and text.strip():
                    indication_texts.append(text)

        # Process all indication texts and extract disease names
        for indication_text in indication_texts:
            extracted = self._extract_diseases_from_text(indication_text, raw_data)
            for disease in extracted:
                # Deduplicate by normalized name
                normalized = disease.name.lower()
                if normalized not in seen_diseases:
                    seen_diseases.add(normalized)
                    diseases.append(disease)

        return diseases

    def _clean_indication_text(self, text: str) -> str:
        """Remove boilerplate prefixes from indication text."""
        if not text:
            return ''

        # Remove common boilerplate prefixes
        prefixes_to_remove = [
            r'^INDICATIONS?\s*(AND\s*USAGE)?:?\s*',
            r'^Uses?\s*:?\s*',
            r'^1\s+INDICATIONS?\s*(AND\s*USAGE)?:?\s*',
            r'^\d+(\.\d+)?\s+',  # Remove leading section numbers like "1.1 "
            r'^•\s*',  # Remove bullet points
        ]

        result = text.strip()
        for pattern in prefixes_to_remove:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        return result.strip()

    def _extract_diseases_from_text(self, text: str, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract actual disease names from indication text using pattern matching."""
        if not text or not isinstance(text, str):
            return []

        diseases = []
        cleaned_text = self._clean_indication_text(text)

        if len(cleaned_text) < 3:
            return []

        # Patterns to extract disease names
        # These patterns look for common indication phrases followed by disease names
        extraction_patterns = [
            # "treatment of [DISEASE]"
            r'treatment\s+of\s+(?:the\s+)?([A-Za-z][A-Za-z\s\-\']+?)(?:\s+in\s+|\s+with\s+|\s+for\s+|\s+associated\s+|,|\.|;|$)',
            # "indicated for [DISEASE]"
            r'indicated\s+for\s+(?:the\s+)?(?:treatment\s+of\s+)?(?:the\s+)?([A-Za-z][A-Za-z\s\-\']+?)(?:\s+in\s+|\s+with\s+|\s+for\s+|,|\.|;|$)',
            # "used to treat [DISEASE]"
            r'used\s+to\s+treat\s+([A-Za-z][A-Za-z\s\-\']+?)(?:\s+in\s+|\s+with\s+|\s+for\s+|,|\.|;|$)',
            # "used for [DISEASE]"
            r'used\s+for\s+(?:the\s+)?(?:treatment\s+of\s+)?(?:the\s+)?([A-Za-z][A-Za-z\s\-\']+?)(?:\s+in\s+|\s+with\s+|\s+for\s+|,|\.|;|$)',
            # "prevention of [DISEASE]"
            r'prevention\s+of\s+([A-Za-z][A-Za-z\s\-\']+?)(?:\s+in\s+|\s+with\s+|\s+for\s+|,|\.|;|$)',
            # "prophylaxis of [DISEASE]"
            r'prophylaxis\s+of\s+([A-Za-z][A-Za-z\s\-\']+?)(?:\s+in\s+|\s+with\s+|\s+for\s+|,|\.|;|$)',
            # "management of [DISEASE]"
            r'management\s+of\s+([A-Za-z][A-Za-z\s\-\']+?)(?:\s+in\s+|\s+with\s+|\s+for\s+|,|\.|;|$)',
            # "relief of [DISEASE/SYMPTOMS]"
            r'relief\s+of\s+([A-Za-z][A-Za-z\s\-\']+?)(?:\s+in\s+|\s+with\s+|\s+for\s+|,|\.|;|$)',
            # "patients with [DISEASE]"
            r'patients\s+with\s+([A-Za-z][A-Za-z\s\-\']+?)(?:\s+who\s+|\s+that\s+|\s+and\s+|,|\.|;|$)',
            # Direct disease name patterns (capitalized multi-word disease names)
            r'\b((?:Type\s+[12]\s+)?Diabetes(?:\s+Mellitus)?)\b',
            r'\b(Hypertension)\b',
            r'\b(Heart\s+Failure)\b',
            r'\b(Coronary\s+Artery\s+Disease)\b',
            r'\b(Atrial\s+Fibrillation)\b',
            r'\b(Chronic\s+Obstructive\s+Pulmonary\s+Disease)\b',
            r'\b(Rheumatoid\s+Arthritis)\b',
            r'\b(Osteoarthritis)\b',
            r'\b(Major\s+Depressive\s+Disorder)\b',
            r'\b(Generalized\s+Anxiety\s+Disorder)\b',
            r'\b(Schizophrenia)\b',
            r'\b(Bipolar\s+Disorder)\b',
            r'\b(Epilepsy)\b',
            r'\b(Parkinson(?:\'s)?\s+Disease)\b',
            r'\b(Alzheimer(?:\'s)?\s+Disease)\b',
            r'\b(Multiple\s+Sclerosis)\b',
            r'\b(Hepatitis\s+[ABC])\b',
            r'\b(HIV(?:\s+Infection)?)\b',
            r'\b(Tuberculosis)\b',
            r'\b(Pneumonia)\b',
            r'\b(Asthma)\b',
            r'\b(Psoriasis)\b',
            r'\b(Eczema)\b',
            r'\b(Acne)\b',
            r'\b(Migraine)\b',
            r'\b(Glaucoma)\b',
            r'\b(Hyperlipidemia)\b',
            r'\b(Hypercholesterolemia)\b',
            r'\b(Hypothyroidism)\b',
            r'\b(Hyperthyroidism)\b',
            r'\b(Osteoporosis)\b',
            r'\b(Gout)\b',
            r'\b(Anemia)\b',
            r'\b(Leukemia)\b',
            r'\b(Lymphoma)\b',
            r'\b(Melanoma)\b',
            r'\b((?:Breast|Lung|Prostate|Colon|Colorectal|Ovarian|Pancreatic)\s+Cancer)\b',
            # Additional common conditions
            r'\b((?:Seasonal|Perennial|Allergic)\s+(?:Allergic\s+)?Rhinitis)\b',
            r'\b(Conjunctivitis)\b',
            r'\b(Sinusitis)\b',
            r'\b(Bronchitis)\b',
            r'\b(Urticaria)\b',
            r'\b(Dermatitis)\b',
            r'\b(Neuropathy)\b',
            r'\b(Neuropathic\s+Pain)\b',
            r'\b(Chronic\s+Pain)\b',
            r'\b(Insomnia)\b',
            r'\b(Anxiety)\b',
            r'\b(Depression)\b',
            r'\b(Nausea)\b',
            r'\b(Vomiting)\b',
            r'\b(Constipation)\b',
            r'\b(Diarrhea)\b',
            r'\b(Gastritis)\b',
            r'\b(Ulcer(?:s)?)\b',
            r'\b(Edema)\b',
            r'\b(Thrombosis)\b',
            r'\b(Embolism)\b',
            r'\b(Stroke)\b',
            r'\b(Seizure(?:s)?)\b',
            r'\b(Infection(?:s)?)\b',
            r'\b(Inflammation)\b',
            r'\b(Arthralgia)\b',
            r'\b(Myalgia)\b',
            r'\b(Fibromyalgia)\b',
            # "associated with [DISEASE]" pattern
            r'associated\s+with\s+([A-Za-z][A-Za-z\s\-\']+?)(?:\s+in\s+|\s+and\s+|,|\.|;|$)',
            # "symptoms of [DISEASE]" pattern
            r'symptoms\s+(?:of|due\s+to)\s+([A-Za-z][A-Za-z\s\-\']+?)(?:\s+in\s+|\s+and\s+|,|\.|;|$)',
        ]

        extracted_names: Set[str] = set()

        for pattern in extraction_patterns:
            matches = re.findall(pattern, cleaned_text, re.IGNORECASE)
            for match in matches:
                disease_name = self._normalize_disease_name(match)
                if disease_name and self._is_valid_disease_name(disease_name):
                    extracted_names.add(disease_name)

        # Create entities for each extracted disease
        for disease_name in extracted_names:
            disease = ExtractedEntity(
                entity_type=EntityType.DISEASE,
                name=disease_name,
                identifiers={},
                context={
                    'source': 'openfda_indication',
                    'extraction_method': 'pattern_matching'
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'indication_text': text[:500]}  # Store first 500 chars
            )
            diseases.append(disease)

        return diseases

    def _normalize_disease_name(self, name: str) -> str:
        """Normalize a disease name for consistency."""
        if not name:
            return ''

        # Strip and normalize whitespace
        name = ' '.join(name.split())

        # Check if it's a known abbreviation
        name_lower = name.lower()
        if name_lower in self.DISEASE_SYNONYMS:
            name = self.DISEASE_SYNONYMS[name_lower]

        # Title case the name
        name = name.title()

        # Fix common title case issues
        name = name.replace("'S ", "'s ")  # Parkinson'S -> Parkinson's
        name = re.sub(r'\bHiv\b', 'HIV', name)
        name = re.sub(r'\bAids\b', 'AIDS', name)
        name = re.sub(r'\bCopd\b', 'COPD', name)

        return name.strip()

    def _is_valid_disease_name(self, name: str) -> bool:
        """Check if extracted text is a valid disease name."""
        if not name or len(name) < 3:
            return False

        # Check if name is too long (likely a sentence, not a disease name)
        if len(name) > 100:
            return False

        # Check if it contains too many words (likely not a disease name)
        words = name.split()
        if len(words) > 8:
            return False

        # Check if it's mostly non-disease words
        name_lower = name.lower()
        name_words = set(name_lower.split())
        non_disease_overlap = name_words.intersection(self.NON_DISEASE_WORDS)

        # If more than half the words are non-disease words, reject
        if len(non_disease_overlap) > len(name_words) / 2:
            return False

        # Reject if it starts with common non-disease patterns
        if re.match(r'^(this|the|for|to|in|as|is|are|was|were|be|been|being)\s', name_lower):
            return False

        return True
    
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

