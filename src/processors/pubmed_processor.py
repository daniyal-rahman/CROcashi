"""
PubMed processor for extracting publication data and linking to trials.

Extracts:
- Publication entity (PMID, title, abstract, journal, date)
- Drug entities from title/abstract
- Disease entities from MeSH terms (if available)
- Links publications to trials via NCT IDs
"""
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, RelationshipExtraction
)

logger = logging.getLogger(__name__)

# Regex pattern for NCT IDs: NCT followed by 8 digits
NCT_ID_PATTERN = re.compile(r'NCT\d{8}', re.IGNORECASE)


class PubMedProcessor(BaseProcessor):
    """
    Processor for PubMed publication data.
    
    PubMed provides:
    - Unique PMID identifiers
    - Publication titles and abstracts
    - Journal information
    - Publication dates
    - MeSH terms for diseases
    """
    
    SOURCE_NAME = "pubmed"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """
        Get PMID from PubMed data.
        
        Args:
            raw_data: Raw PubMed esummary data
            
        Returns:
            PMID (e.g., "12345678")
        """
        # Try multiple possible field names
        pmid = raw_data.get('pmid') or raw_data.get('uid') or raw_data.get('Uid')
        if isinstance(pmid, list) and pmid:
            pmid = pmid[0]
        return str(pmid) if pmid else ''
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """
        Extract entities from a PubMed publication record.
        
        Args:
            raw_data: Raw PubMed esummary data
            
        Returns:
            Dict of entity lists by type
        """
        self.metrics.start_time = datetime.now()
        
        entities = {
            'publications': [],
            'drugs': [],
            'diseases': []
        }
        
        pmid = self.get_source_identifier(raw_data)
        
        try:
            # Extract publication entity
            publication = self._extract_publication(raw_data)
            if publication:
                entities['publications'].append(publication)
                self.metrics.entities_extracted += 1
            
            # Extract drug entities from title/abstract
            drugs = self._extract_drugs(raw_data)
            entities['drugs'].extend(drugs)
            self.metrics.entities_extracted += len(drugs)
            
            # Extract disease entities from MeSH terms
            diseases = self._extract_diseases(raw_data)
            entities['diseases'].extend(diseases)
            self.metrics.entities_extracted += len(diseases)
            
        except Exception as e:
            logger.error(f"Error extracting entities from PMID {pmid}: {e}")
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
        Extract relationships after entities are resolved.
        
        Args:
            raw_data: Raw publication data
            resolved_entities: Map of entity keys to resolved UUIDs
            id_to_entity: Map of resolved UUIDs to their extracted entities
            
        Returns:
            List of relationships to create
        """
        relationships = []
        
        pub_id = resolved_entities.get('publication')
        if not pub_id:
            logger.warning("No publication ID found in resolved entities")
            return relationships
        
        # Get publication entity for relationship stubs
        pub_entity = id_to_entity.get(pub_id)
        if not pub_entity:
            pub_entity = self._make_publication_entity(raw_data)
        
        # Extract NCT IDs from publication text and link to trials
        nct_ids = self._extract_nct_ids(raw_data)
        if nct_ids:
            # Query database for matching trials by nct_id
            from database.models.clinical import ClinicalTrial
            trials = self.session.query(ClinicalTrial).filter(
                ClinicalTrial.nct_id.in_([nct.upper() for nct in nct_ids])
            ).all()
            
            for trial in trials:
                # Create publication-trial relationship
                relationships.append(RelationshipExtraction(
                    relationship_type='publication_trial',
                    source_entity=pub_entity,
                    target_entity=self._make_trial_entity_stub(trial),
                    attributes={
                        'is_primary_publication': self._is_primary_publication(raw_data, trial)
                    },
                    temporal={}
                ))
        
        # Create publication-drug relationships
        for drug_id in resolved_entities.get('drugs', []):
            drug_entity = id_to_entity.get(drug_id)
            if drug_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='publication_drug',
                    source_entity=pub_entity,
                    target_entity=drug_entity,
                    attributes={
                        'mention_context': 'title_abstract',
                        'mention_type': 'drug_name'
                    },
                    temporal={}
                ))
        
        # Create publication-disease relationships
        for disease_id in resolved_entities.get('diseases', []):
            disease_entity = id_to_entity.get(disease_id)
            if disease_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='publication_disease',
                    source_entity=pub_entity,
                    target_entity=disease_entity,
                    attributes={
                        'mention_context': 'mesh_terms',
                        'mention_type': 'disease_term'
                    },
                    temporal={}
                ))
        
        return relationships
    
    def _extract_publication(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract publication entity."""
        pmid = self.get_source_identifier(raw_data)
        
        # Extract title
        title = raw_data.get('title', '')
        if isinstance(title, list):
            title = title[0] if title else ''
        
        # Extract abstract
        abstract = raw_data.get('abstract', '')
        if isinstance(abstract, list):
            abstract = abstract[0] if abstract else ''
        
        # Extract journal
        journal = raw_data.get('source', '')
        if isinstance(journal, list):
            journal = journal[0] if journal else ''
        
        # Extract publication date
        pub_date = self._extract_publication_date(raw_data)
        
        # Extract DOI
        doi = raw_data.get('elocationid', '')
        if isinstance(doi, list):
            doi = doi[0] if doi else ''
        # Sometimes DOI is in a different field
        if not doi:
            doi = raw_data.get('doi', '')
        
        # Determine publication type
        pub_type = self._determine_publication_type(raw_data, title, abstract)
        
        publication = ExtractedEntity(
            entity_type=EntityType.PUBLICATION,
            name=title or f"PubMed {pmid}",
            identifiers={
                'pmid': pmid,
                'doi': doi
            },
            context={
                'title': title,
                'abstract': abstract,
                'journal': journal,
                'publication_date': pub_date,
                'publication_type': pub_type,
                'is_clinical_trial_result': 'clinical trial' in (title + ' ' + abstract).lower()
            },
            source_name=self.SOURCE_NAME,
            source_identifier=pmid,
            raw_data=raw_data
        )
        
        return publication
    
    def _extract_drugs(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """
        Extract drug entities from title and abstract by searching for known drug names.
        
        Uses database drug names to find mentions in publication text.
        """
        drugs = []
        
        # Combine title and abstract for drug extraction
        title = raw_data.get('title', '')
        if isinstance(title, list):
            title = ' '.join(title) if title else ''
        
        abstract = raw_data.get('abstract', '')
        if isinstance(abstract, list):
            abstract = ' '.join(abstract) if abstract else ''
        
        text = title + ' ' + abstract
        if not text.strip():
            return drugs
        
        # Get all drug names from database (similar to SEC processor approach)
        drug_names = self._get_all_drug_names()
        if not drug_names:
            logger.debug("No drug names found in database for publication text search")
            return drugs
        
        # Search for drug mentions in text
        text_lower = text.lower()
        found_drugs = set()  # Track found drugs to avoid duplicates
        
        for drug_name in drug_names:
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(drug_name.lower()) + r'\b'
            if re.search(pattern, text_lower):
                # Normalize drug name
                normalized_name = self.normalize_drug_name(drug_name)
                
                # Avoid duplicates
                if normalized_name not in found_drugs:
                    found_drugs.add(normalized_name)
                    
                    drug = ExtractedEntity(
                        entity_type=EntityType.DRUG,
                        name=normalized_name,
                        identifiers={},
                        context={
                            'mention_context': 'title_abstract',
                            'source': 'text_search'
                        },
                        source_name=self.SOURCE_NAME,
                        source_identifier=self.get_source_identifier(raw_data),
                        raw_data={'drug_name': drug_name, 'extraction_method': 'text_search'}
                    )
                    drugs.append(drug)
        
        return drugs
    
    def _get_all_drug_names(self) -> set:
        """
        Get all drug names from database for text search.
        
        Returns:
            Set of normalized drug names
        """
        drug_names = set()
        
        try:
            from database.models import Drug
            
            # Query all drugs from database
            drugs = self.session.query(Drug).filter(
                Drug.deleted_at.is_(None)
            ).all()
            
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
            
            logger.debug(f"Loaded {len(drug_names)} drug names for publication text search")
            
        except Exception as e:
            logger.error(f"Error loading drug names from database: {e}")
            drug_names = set()
        
        return drug_names
    
    def _extract_diseases(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract disease entities from MeSH terms."""
        diseases = []
        
        # Extract MeSH terms
        mesh_terms = raw_data.get('meshterms', [])
        if isinstance(mesh_terms, str):
            mesh_terms = [mesh_terms]
        
        # MeSH terms are typically in format: "Term/Qualifier"
        for term in mesh_terms:
            if not term:
                continue
            
            # Split on '/' to get main term
            main_term = term.split('/')[0].strip()
            
            # Filter for disease-related terms (basic heuristic)
            # In production, would use MeSH hierarchy to identify disease terms
            disease_keywords = ['disease', 'syndrome', 'disorder', 'cancer', 'tumor', 'neoplasm']
            if any(keyword in main_term.lower() for keyword in disease_keywords):
                disease = ExtractedEntity(
                    entity_type=EntityType.DISEASE,
                    name=main_term,
                    identifiers={},
                    context={
                        'mesh_term': term,
                        'source_term': main_term
                    },
                    source_name=self.SOURCE_NAME,
                    source_identifier=self.get_source_identifier(raw_data),
                    raw_data={'mesh_term': term}
                )
                diseases.append(disease)
        
        return diseases
    
    def _extract_nct_ids(self, raw_data: Dict[str, Any]) -> List[str]:
        """
        Extract NCT IDs from publication text.
        
        Args:
            raw_data: Raw publication data
            
        Returns:
            List of NCT IDs found (e.g., ["NCT12345678"])
        """
        nct_ids = []
        
        # Combine title and abstract
        title = raw_data.get('title', '')
        if isinstance(title, list):
            title = ' '.join(title) if title else ''
        
        abstract = raw_data.get('abstract', '')
        if isinstance(abstract, list):
            abstract = ' '.join(abstract) if abstract else ''
        
        text = title + ' ' + abstract
        
        # Find all NCT IDs
        matches = NCT_ID_PATTERN.findall(text)
        nct_ids = list(set(matches))  # Remove duplicates
        
        return nct_ids
    
    def _extract_publication_date(self, raw_data: Dict[str, Any]) -> Optional[datetime]:
        """Extract publication date from PubMed data."""
        # Try multiple date fields
        pub_date = raw_data.get('pubdate', '')
        if isinstance(pub_date, list):
            pub_date = pub_date[0] if pub_date else ''
        
        if not pub_date:
            pub_date = raw_data.get('epubdate', '')
            if isinstance(pub_date, list):
                pub_date = pub_date[0] if pub_date else ''
        
        if pub_date:
            # Parse date - PubMed dates are often in format "YYYY Mon DD" or "YYYY"
            try:
                # Try full date format
                for fmt in ['%Y %b %d', '%Y %B %d', '%Y-%m-%d', '%Y/%m/%d', '%Y']:
                    try:
                        return datetime.strptime(pub_date, fmt)
                    except ValueError:
                        continue
            except Exception:
                pass
        
        return None
    
    def _determine_publication_type(
        self,
        raw_data: Dict[str, Any],
        title: str,
        abstract: str
    ) -> Optional[str]:
        """Determine publication type from content."""
        text = (title + ' ' + abstract).lower()
        
        if 'clinical trial' in text or 'randomized' in text:
            return 'clinical_trial'
        elif 'meta-analysis' in text or 'meta analysis' in text:
            return 'meta_analysis'
        elif 'review' in text and 'systematic' in text:
            return 'review'
        elif 'case report' in text:
            return 'case_report'
        
        return None
    
    def _is_primary_publication(
        self,
        raw_data: Dict[str, Any],
        trial: Any
    ) -> bool:
        """
        Determine if this is a primary publication for the trial.
        
        Args:
            raw_data: Raw publication data
            trial: ClinicalTrial database object
            
        Returns:
            True if likely primary publication
        """
        # Heuristic: primary publications often mention the trial in the title
        title = raw_data.get('title', '')
        if isinstance(title, list):
            title = ' '.join(title) if title else ''
        
        title_lower = title.lower()
        nct_id = trial.nct_id or ''
        
        # If NCT ID appears in title, likely primary
        if nct_id and nct_id.lower() in title_lower:
            return True
        
        # If title contains "results" or "outcome" with trial identifier, likely primary
        if any(word in title_lower for word in ['results', 'outcome', 'efficacy', 'safety']):
            if nct_id and nct_id.lower() in title_lower:
                return True
        
        return False
    
    def _make_publication_entity(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Helper to create publication entity stub for relationships."""
        pmid = self.get_source_identifier(raw_data)
        title = raw_data.get('title', '')
        if isinstance(title, list):
            title = title[0] if title else ''
        
        return ExtractedEntity(
            entity_type=EntityType.PUBLICATION,
            name=title or f"PubMed {pmid}",
            identifiers={'pmid': pmid},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=pmid
        )
    
    def _make_trial_entity_stub(self, trial: Any) -> ExtractedEntity:
        """Helper to create trial entity stub from database object."""
        return ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name=trial.trial_title or f"Trial {trial.nct_id}",
            identifiers={'nct_id': trial.nct_id},
            context={},
            source_name='clinicaltrials_gov',
            source_identifier=trial.nct_id or ''
        )

