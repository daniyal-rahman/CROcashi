"""
Relationship inference service for creating relationships from existing data.

This service infers relationships that aren't directly extracted from source data,
such as company-drug relationships from trial sponsorships, publication-trial
relationships from NCT IDs, and publication-drug relationships from text search.
"""
import logging
import re
from datetime import datetime
from uuid import uuid4
from typing import Dict, Any, List, Set, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class RelationshipInferenceService:
    """
    Service for inferring relationships from existing data.
    
    Implements:
    - Company-drug inference from trial sponsorships
    - Publication-trial inference from NCT IDs in text
    - Publication-drug inference from drug mentions in text
    - Publication-company inference from affiliations
    - Filing-drug inference from drug mentions in text
    """
    
    def __init__(self, session: Session, batch_size: int = 1000, commit_batch_size: int = 500):
        """
        Initialize relationship inference service.
        
        Args:
            session: Database session
            batch_size: Number of entities to process in memory at once (default: 1000)
            commit_batch_size: Number of relationships to create before committing (default: 500)
        """
        self.session = session
        self.batch_size = batch_size
        self.commit_batch_size = commit_batch_size
        self._drug_names_cache: Optional[Set[str]] = None
        self._drug_name_to_id_cache: Optional[Dict[str, Any]] = None
    
    def infer_company_drug_relationships(self, commit: bool = True) -> Dict[str, Any]:
        """
        Infer company-drug relationships from trial sponsorships.
        
        Logic: If Company X sponsors Trial Y that tests Drug Z,
        then Company X has a relationship with Drug Z.
        
        Args:
            commit: If True, commit transaction at end. If False, caller handles commit.
        
        Returns:
            Dict with statistics about inferred relationships
        """
        logger.info("Starting company-drug relationship inference...")
        
        try:
            # Use Python uuid4() for UUID generation (more compatible)
            # We'll generate UUIDs in Python and insert them
            from database.models.relationships import CompanyDrug
            from database.models import Company, Drug
            
            # Get all company-drug pairs from trial sponsorships
            query_pairs = text("""
                SELECT DISTINCT
                    ts.entity_id as company_id,
                    td.drug_id
                FROM trial_sponsors ts
                JOIN trial_drugs td ON ts.trial_id = td.trial_id
                WHERE ts.entity_type = 'company'
                AND ts.deleted_at IS NULL
                AND td.deleted_at IS NULL
                AND NOT EXISTS (
                    SELECT 1 FROM company_drugs cd
                    WHERE cd.company_id = ts.entity_id
                    AND cd.drug_id = td.drug_id
                    AND cd.deleted_at IS NULL
                )
            """)
            
            pairs = self.session.execute(query_pairs).fetchall()
            
            logger.info(f"Found {len(pairs)} company-drug pairs to process...")
            
            # Create relationship records
            created_count = 0
            for company_id, drug_id in pairs:
                # Check if relationship already exists (double-check)
                existing = self.session.query(CompanyDrug).filter(
                    CompanyDrug.company_id == company_id,
                    CompanyDrug.drug_id == drug_id,
                    CompanyDrug.deleted_at.is_(None)
                ).first()
                
                if not existing:
                    new_rel = CompanyDrug(
                        id=uuid4(),
                        company_id=company_id,
                        drug_id=drug_id,
                        relationship_type='developer',
                        development_stage=None,
                        data_sources={
                            'source': 'inferred_from_trial',
                            'inference_method': 'trial_sponsorship',
                            'confidence': 0.9
                        }
                    )
                    self.session.add(new_rel)
                    created_count += 1
                    
                    # Flush and commit periodically to avoid large transactions
                    if created_count % self.commit_batch_size == 0:
                        self.session.flush()
                        if commit:
                            self.session.commit()
                            logger.debug(f"Committed batch: {created_count} relationships created so far")
            
            self.session.flush()  # Final flush
            if commit:
                self.session.commit()
            
            # Count how many relationships were created (total inferred)
            count_query = text("""
                SELECT COUNT(*) as count
                FROM company_drugs
                WHERE data_sources->>'source' = 'inferred_from_trial'
                AND deleted_at IS NULL
            """)
            count_result = self.session.execute(count_query).fetchone()
            total_count = count_result[0] if count_result else 0
            
            logger.info(f"Created {created_count} new company-drug relationships (total inferred: {total_count})")
            
            return {
                'status': 'success',
                'relationships_created': created_count,
                'relationships_inferred': total_count,
                'method': 'trial_sponsorship'
            }
            
        except Exception as e:
            logger.error(f"Error inferring company-drug relationships: {e}")
            self.session.rollback()
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def infer_all_relationships(self, atomic: bool = True) -> Dict[str, Any]:
        """
        Run all inference methods.
        
        Args:
            atomic: If True, wrap all methods in a single transaction (all-or-nothing).
                   If False, each method commits separately (allows partial success).
        
        Returns:
            Dict with results from all inference methods
        """
        if atomic:
            # Wrap all inference in a single transaction
            try:
                results = {}
                
                # Company-drug inference
                results['company_drug'] = self.infer_company_drug_relationships(commit=False)
                
                # Publication relationships
                results['publication_trial'] = self.infer_publication_trial_relationships(commit=False)
                results['publication_drug'] = self.infer_publication_drug_relationships(commit=False)
                results['publication_company'] = self.infer_publication_company_relationships(commit=False)
                
                # Filing relationships
                results['filing_drug'] = self.infer_filing_drug_relationships(commit=False)
                
                # Commit all at once
                self.session.commit()
                logger.info("All relationship inference completed successfully (atomic transaction)")
                
                return results
            except Exception as e:
                logger.error(f"Error in atomic relationship inference: {e}")
                self.session.rollback()
                raise
        else:
            # Each method commits separately (allows partial success)
            results = {}
            
            # Company-drug inference
            results['company_drug'] = self.infer_company_drug_relationships()
            
            # Publication relationships
            results['publication_trial'] = self.infer_publication_trial_relationships()
            results['publication_drug'] = self.infer_publication_drug_relationships()
            results['publication_company'] = self.infer_publication_company_relationships()
            
            # Filing relationships
            results['filing_drug'] = self.infer_filing_drug_relationships()
            
            return results
    
    def rebuild_all(self, clear_existing: bool = True) -> Dict[str, Any]:
        """
        Rebuild all relationships from scratch.
        
        Args:
            clear_existing: If True, delete all inferred relationships before rebuilding
            
        Returns:
            Dict with results from all inference methods
        """
        if clear_existing:
            self._clear_all_relationships()
        
        return self.infer_all_relationships()
    
    def _clear_all_relationships(self):
        """Delete all inferred relationships (for clean rebuild).
        
        CRITICAL: Only deletes relationships with data_sources->>'source' = 'inferred_from_text'
        to preserve relationships created during entity extraction.
        """
        logger.info("Clearing all inferred relationships...")
        
        from database.models.relationships import (
            PublicationTrial, PublicationDrug, PublicationCompany,
            FilingDrug
        )
        from sqlalchemy import text
        
        try:
            # Clear publication relationships (only inferred ones)
            # Filter by data_sources->>'source' = 'inferred_from_text'
            self.session.execute(
                text("""
                    DELETE FROM publication_trials
                    WHERE data_sources->>'source' = 'inferred_from_text'
                """)
            )
            self.session.execute(
                text("""
                    DELETE FROM publication_drugs
                    WHERE data_sources->>'source' = 'inferred_from_text'
                """)
            )
            self.session.execute(
                text("""
                    DELETE FROM publication_companies
                    WHERE data_sources->>'source' = 'inferred_from_text'
                """)
            )
            
            # Clear filing relationships (only inferred ones)
            self.session.execute(
                text("""
                    DELETE FROM filing_drugs
                    WHERE data_sources->>'source' = 'inferred_from_text'
                """)
            )
            
            # Note: We don't clear CompanyDrug relationships that are inferred
            # because they may have been created through other means too
            # If needed, can add: WHERE data_sources->>'source' = 'inferred_from_trial'
            
            self.session.commit()
            logger.info("Cleared all inferred relationships")
        except Exception as e:
            logger.error(f"Error clearing relationships: {e}")
            self.session.rollback()
            raise
    
    # Helper methods for text extraction
    
    def _extract_nct_ids_from_text(self, text: str) -> List[str]:
        """
        Extract NCT IDs from text using regex.
        
        Args:
            text: Text to search
            
        Returns:
            List of unique NCT IDs found (e.g., ["NCT12345678"])
        """
        if not text:
            return []
        
        nct_pattern = re.compile(r'NCT\d{8}', re.IGNORECASE)
        matches = nct_pattern.findall(text)
        return list(set(matches))  # Remove duplicates
    
    def _load_all_drug_names(self) -> Set[str]:
        """
        Load and normalize all drug names from database.
        
        Returns:
            Set of normalized drug names for text search
        """
        if self._drug_names_cache is not None:
            return self._drug_names_cache
        
        # Build cache by loading drug name mapping
        self._load_drug_name_mapping()
        
        return self._drug_names_cache or set()
    
    def _load_drug_name_mapping(self) -> Dict[str, Any]:
        """
        Load drug name to drug entity mapping for efficient lookup.
        
        Returns:
            Dict mapping normalized drug names to Drug entities
        """
        if self._drug_name_to_id_cache is not None:
            return self._drug_name_to_id_cache
        
        from database.models import Drug
        from src.entity_resolution.base_processor import BaseProcessor
        
        drug_names = set()
        name_to_drug = {}
        
        try:
            drugs = self.session.query(Drug).filter(Drug.deleted_at.is_(None)).all()
            
            for drug in drugs:
                # Add primary name
                if drug.primary_name:
                    normalized = BaseProcessor.normalize_drug_name_static(drug.primary_name)
                    drug_names.add(normalized)
                    name_to_drug[normalized] = drug
                
                # Add generic name
                if drug.generic_name:
                    normalized = BaseProcessor.normalize_drug_name_static(drug.generic_name)
                    drug_names.add(normalized)
                    name_to_drug[normalized] = drug
                
                # Add aliases
                if drug.aliases:
                    for alias in drug.aliases:
                        if alias:
                            normalized = BaseProcessor.normalize_drug_name_static(alias)
                            drug_names.add(normalized)
                            name_to_drug[normalized] = drug
            
            self._drug_names_cache = drug_names
            self._drug_name_to_id_cache = name_to_drug
            logger.debug(f"Loaded {len(drug_names)} drug names for text search")
            
        except Exception as e:
            logger.error(f"Error loading drug names from database: {e}")
            drug_names = set()
            name_to_drug = {}
        
        return name_to_drug
    
    def _search_text_for_drugs(self, text: str, drug_names: Set[str]) -> List[str]:
        """
        Find drug mentions in text using word boundaries.
        
        Args:
            text: Text to search
            drug_names: Set of normalized drug names to search for
            
        Returns:
            List of drug names found in text
        """
        if not text or not drug_names:
            return []
        
        text_lower = text.lower()
        found_drugs = set()
        
        for drug_name in drug_names:
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(drug_name.lower()) + r'\b'
            if re.search(pattern, text_lower):
                found_drugs.add(drug_name)
        
        return list(found_drugs)
    
    def _normalize_text_for_search(self, text: str) -> str:
        """
        Normalize text for searching (basic normalization).
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        return text.strip()
    
    # Inference methods
    
    def infer_publication_trial_relationships(self, commit: bool = True) -> Dict[str, Any]:
        """
        Infer publication-trial relationships from NCT IDs in publication text.
        
        Args:
            commit: If True, commit transaction at end. If False, caller handles commit.
        
        Returns:
            Dict with statistics about inferred relationships
        """
        logger.info("Starting publication-trial relationship inference...")
        
        try:
            from database.models.publications import Publication
            from database.models.clinical import ClinicalTrial
            from database.models.relationships import PublicationTrial
            
            # Count total publications for batching
            total_count = self.session.query(Publication).filter(
                Publication.deleted_at.is_(None)
            ).count()
            
            logger.info(f"Processing {total_count} publications in batches of {self.batch_size}...")
            
            relationships_created = 0
            nct_ids_found = 0
            trials_matched = 0
            offset = 0
            
            # Process in batches to avoid loading all into memory
            while offset < total_count:
                # Fetch batch
                publications = self.session.query(Publication).filter(
                    Publication.deleted_at.is_(None)
                ).offset(offset).limit(self.batch_size).all()
                
                if not publications:
                    break
                
                for pub in publications:
                    # Combine title and abstract for NCT ID extraction
                    text = ""
                    if pub.title:
                        text += pub.title + " "
                    if pub.abstract:
                        text += pub.abstract
                    
                    if not text.strip():
                        continue
                    
                    # Extract NCT IDs from text
                    nct_ids = self._extract_nct_ids_from_text(text)
                    
                    if not nct_ids:
                        continue
                    
                    nct_ids_found += len(nct_ids)
                    
                    # For each NCT ID, find matching trial
                    for nct_id in nct_ids:
                        # Query database for matching trial
                        trial = self.session.query(ClinicalTrial).filter(
                            ClinicalTrial.nct_id == nct_id.upper()
                        ).filter(
                            ClinicalTrial.deleted_at.is_(None)
                        ).first()
                        
                        if not trial:
                            logger.debug(f"Trial {nct_id} not found in database")
                            continue
                        
                        trials_matched += 1
                        
                        # Check if relationship already exists
                        existing = self.session.query(PublicationTrial).filter(
                            PublicationTrial.pub_id == pub.pub_id,
                            PublicationTrial.trial_id == trial.trial_id
                        ).first()
                        
                        if existing:
                            continue
                        
                        # Determine if primary publication (heuristic: NCT ID in title)
                        is_primary = nct_id.upper() in (pub.title or "").upper()
                        
                        # Create relationship
                        new_rel = PublicationTrial(
                            pub_id=pub.pub_id,
                            trial_id=trial.trial_id,
                            is_primary_publication=is_primary,
                            data_sources={
                                'source': 'inferred_from_text',
                                'inference_method': 'nct_id_extraction',
                                'confidence': 0.95,
                                'inferred_at': datetime.now().isoformat()
                            }
                        )
                        self.session.add(new_rel)
                        relationships_created += 1
                        
                        # Flush and commit periodically to avoid large transactions
                        if relationships_created % self.commit_batch_size == 0:
                            self.session.flush()
                            if commit:
                                self.session.commit()
                                logger.debug(f"Committed batch: {relationships_created} relationships created so far")
                
                offset += len(publications)
                logger.debug(f"Processed batch: {offset}/{total_count} publications")
            
            self.session.flush()  # Final flush
            if commit:
                self.session.commit()
            
            logger.info(
                f"Created {relationships_created} publication-trial relationships "
                f"(found {nct_ids_found} NCT IDs, matched {trials_matched} trials)"
            )
            
            return {
                'status': 'success',
                'relationships_created': relationships_created,
                'publications_processed': total_count,
                'nct_ids_found': nct_ids_found,
                'trials_matched': trials_matched,
                'method': 'nct_id_extraction'
            }
            
        except Exception as e:
            logger.error(f"Error inferring publication-trial relationships: {e}")
            self.session.rollback()
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def infer_publication_drug_relationships(self, commit: bool = True) -> Dict[str, Any]:
        """
        Infer publication-drug relationships from drug mentions in publication text.
        
        Args:
            commit: If True, commit transaction at end. If False, caller handles commit.
        
        Returns:
            Dict with statistics about inferred relationships
        """
        logger.info("Starting publication-drug relationship inference...")
        
        try:
            from database.models.publications import Publication
            from database.models import Drug
            from database.models.relationships import PublicationDrug
            from src.entity_resolution.base_processor import BaseProcessor
            
            # Load all drug names (cached)
            drug_names = self._load_all_drug_names()
            
            if not drug_names:
                logger.warning("No drug names found in database")
                return {
                    'status': 'error',
                    'error': 'No drug names available for matching'
                }
            
            # Count total publications for batching
            total_count = self.session.query(Publication).filter(
                Publication.deleted_at.is_(None)
            ).count()
            
            logger.info(f"Processing {total_count} publications in batches of {self.batch_size}...")
            
            # Load drug name mapping once for efficient lookup
            name_to_drug = self._load_drug_name_mapping()
            
            relationships_created = 0
            drugs_found = 0
            offset = 0
            
            # Process in batches to avoid loading all into memory
            while offset < total_count:
                # Fetch batch
                publications = self.session.query(Publication).filter(
                    Publication.deleted_at.is_(None)
                ).offset(offset).limit(self.batch_size).all()
                
                if not publications:
                    break
                
                for pub in publications:
                    # Combine title and abstract for drug search
                    text = ""
                    if pub.title:
                        text += pub.title + " "
                    if pub.abstract:
                        text += pub.abstract
                    
                    if not text.strip():
                        continue
                    
                    # Search for drug mentions
                    found_drug_names = self._search_text_for_drugs(text, drug_names)
                    
                    if not found_drug_names:
                        continue
                    
                    drugs_found += len(found_drug_names)
                    
                    # For each drug found, resolve to drug entity and create relationship
                    for drug_name in found_drug_names:
                        # Look up drug by normalized name (mapping loaded before loop)
                        drug = name_to_drug.get(drug_name)
                        
                        if not drug:
                            continue
                        
                        # Check if relationship already exists
                        existing = self.session.query(PublicationDrug).filter(
                            PublicationDrug.pub_id == pub.pub_id,
                            PublicationDrug.drug_id == drug.drug_id
                        ).first()
                        
                        if existing:
                            continue
                        
                        # Create relationship
                        new_rel = PublicationDrug(
                            pub_id=pub.pub_id,
                            drug_id=drug.drug_id,
                            mention_context='title_abstract',
                            data_sources={
                                'source': 'inferred_from_text',
                                'inference_method': 'text_search',
                                'confidence': 0.8,
                                'inferred_at': datetime.now().isoformat()
                            }
                        )
                        self.session.add(new_rel)
                        relationships_created += 1
                        
                        # Flush and commit periodically to avoid large transactions
                        if relationships_created % self.commit_batch_size == 0:
                            self.session.flush()
                            if commit:
                                self.session.commit()
                                logger.debug(f"Committed batch: {relationships_created} relationships created so far")
                
                offset += len(publications)
                logger.debug(f"Processed batch: {offset}/{total_count} publications")
            
            self.session.flush()  # Final flush
            if commit:
                self.session.commit()
            
            logger.info(
                f"Created {relationships_created} publication-drug relationships "
                f"(found {drugs_found} drug mentions)"
            )
            
            return {
                'status': 'success',
                'relationships_created': relationships_created,
                'publications_processed': total_count,
                'drugs_found': drugs_found,
                'method': 'text_search'
            }
            
        except Exception as e:
            logger.error(f"Error inferring publication-drug relationships: {e}")
            self.session.rollback()
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def infer_publication_company_relationships(self, commit: bool = True) -> Dict[str, Any]:
        """
        Infer publication-company relationships from affiliations and funding sources.
        
        Note: This is limited by what data is stored in publication context.
        
        Args:
            commit: If True, commit transaction at end. If False, caller handles commit.
        
        Returns:
            Dict with statistics about inferred relationships
        """
        logger.info("Starting publication-company relationship inference...")
        
        try:
            from database.models.publications import Publication
            from database.models import Company
            from database.models.relationships import PublicationCompany
            from src.entity_resolution.base_processor import BaseProcessor
            
            # Count total publications for batching
            total_count = self.session.query(Publication).filter(
                Publication.deleted_at.is_(None)
            ).count()
            
            logger.info(f"Processing {total_count} publications in batches of {self.batch_size}...")
            
            relationships_created = 0
            offset = 0
            
            # Note: This implementation is limited because publication context
            # may not have structured company affiliation data
            # In production, would need to extract from author affiliations,
            # funding sources, etc. if stored in context field
            
            # Process in batches to avoid loading all into memory
            while offset < total_count:
                # Fetch batch
                publications = self.session.query(Publication).filter(
                    Publication.deleted_at.is_(None)
                ).offset(offset).limit(self.batch_size).all()
                
                if not publications:
                    break
                
                for pub in publications:
                    # Check if context has company information
                    if not pub.data_sources or not isinstance(pub.data_sources, dict):
                        continue
                    
                    # Try to extract company names from context
                    # This is a placeholder - actual implementation would depend on
                    # how company data is stored in publication context
                    # For now, we'll skip this as it requires structured data
                    pass
                
                offset += len(publications)
                logger.debug(f"Processed batch: {offset}/{total_count} publications")
            
            if commit:
                self.session.commit()
            
            logger.info(
                f"Created {relationships_created} publication-company relationships "
                f"(limited by available data)"
            )
            
            return {
                'status': 'success',
                'relationships_created': relationships_created,
                'publications_processed': total_count,
                'method': 'context_extraction',
                'note': 'Limited by available publication context data'
            }
            
        except Exception as e:
            logger.error(f"Error inferring publication-company relationships: {e}")
            self.session.rollback()
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def infer_filing_drug_relationships(self, commit: bool = True) -> Dict[str, Any]:
        """
        Infer filing-drug relationships from drug mentions in SEC filing text.
        
        Args:
            commit: If True, commit transaction at end. If False, caller handles commit.
        
        Returns:
            Dict with statistics about inferred relationships
        """
        logger.info("Starting filing-drug relationship inference...")
        
        try:
            from database.models.publications import SECFiling
            from database.models import Drug
            from database.models.relationships import FilingDrug
            from src.entity_resolution.base_processor import BaseProcessor
            
            # Load all drug names (cached)
            drug_names = self._load_all_drug_names()
            
            if not drug_names:
                logger.warning("No drug names found in database")
                return {
                    'status': 'error',
                    'error': 'No drug names available for matching'
                }
            
            # Count total filings for batching
            total_count = self.session.query(SECFiling).filter(
                SECFiling.deleted_at.is_(None)
            ).count()
            
            logger.info(f"Processing {total_count} SEC filings in batches of {self.batch_size}...")
            
            # Load drug name mapping once for efficient lookup
            name_to_drug = self._load_drug_name_mapping()
            
            relationships_created = 0
            drugs_found = 0
            filings_with_text = 0
            offset = 0
            
            # Process in batches to avoid loading all into memory
            while offset < total_count:
                # Fetch batch
                filings = self.session.query(SECFiling).filter(
                    SECFiling.deleted_at.is_(None)
                ).offset(offset).limit(self.batch_size).all()
                
                if not filings:
                    break
                
                for filing in filings:
                    # Get filing text
                    text = filing.full_text
                    
                    if not text or not text.strip():
                        continue
                    
                    filings_with_text += 1
                    
                    # Search for drug mentions
                    found_drug_names = self._search_text_for_drugs(text, drug_names)
                    
                    if not found_drug_names:
                        continue
                    
                    drugs_found += len(found_drug_names)
                    
                    # For each drug found, resolve to drug entity and create relationship
                    for drug_name in found_drug_names:
                        # Look up drug by normalized name (mapping loaded before loop)
                        drug = name_to_drug.get(drug_name)
                        
                        if not drug:
                            continue
                        
                        # Check if relationship already exists
                        existing = self.session.query(FilingDrug).filter(
                            FilingDrug.filing_id == filing.filing_id,
                            FilingDrug.drug_id == drug.drug_id
                        ).first()
                        
                        if existing:
                            continue
                        
                        # Determine mention type based on context (simplified)
                        # In production, would analyze text context more carefully
                        mention_type = None  # Could be 'pipeline_update', 'termination', etc.
                        
                        # Create relationship
                        new_rel = FilingDrug(
                            filing_id=filing.filing_id,
                            drug_id=drug.drug_id,
                            mention_type=mention_type,
                            data_sources={
                                'source': 'inferred_from_text',
                                'inference_method': 'text_search',
                                'confidence': 0.8,
                                'inferred_at': datetime.now().isoformat()
                            }
                        )
                        self.session.add(new_rel)
                        relationships_created += 1
                        
                        # Flush and commit periodically to avoid large transactions
                        if relationships_created % self.commit_batch_size == 0:
                            self.session.flush()
                            if commit:
                                self.session.commit()
                                logger.debug(f"Committed batch: {relationships_created} relationships created so far")
                
                offset += len(filings)
                logger.debug(f"Processed batch: {offset}/{total_count} filings")
            
            self.session.flush()  # Final flush
            if commit:
                self.session.commit()
            
            logger.info(
                f"Created {relationships_created} filing-drug relationships "
                f"(processed {filings_with_text} filings with text, found {drugs_found} drug mentions)"
            )
            
            return {
                'status': 'success',
                'relationships_created': relationships_created,
                'filings_processed': total_count,
                'filings_with_text': filings_with_text,
                'drugs_found': drugs_found,
                'method': 'text_search'
            }
            
        except Exception as e:
            logger.error(f"Error inferring filing-drug relationships: {e}")
            self.session.rollback()
            return {
                'status': 'error',
                'error': str(e)
            }

