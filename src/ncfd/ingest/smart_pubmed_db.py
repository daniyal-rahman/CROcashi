#!/usr/bin/env python3
"""
Database-integrated smart PubMed search pipeline.

This version stores search results and decisions in the database.
"""

import logging
import time
import random
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import requests
from urllib.parse import urlencode
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from .smart_pubmed import SmartPubMedClient, PubMedSummary, SearchResult
from ..db.models import Document, DocumentTextPage, DocumentCitation, DocumentNote

logger = logging.getLogger(__name__)


@dataclass
class DatabaseSearchResult:
    """Database-integrated search result with storage info."""
    search_result: SearchResult
    documents_created: int
    documents_updated: int
    errors: List[str]


class SmartPubMedDBClient(SmartPubMedClient):
    """
    Database-integrated smart PubMed client.
    
    Extends SmartPubMedClient with database storage capabilities.
    """
    
    def __init__(self, db_session: Session):
        super().__init__()
        self.db_session = db_session
    
    def smart_search_with_storage(
        self,
        drug_synonyms: List[str],
        disease: Optional[str] = None,
        nct_id: Optional[str] = None,
        k_top: int = 20,
        promote_threshold: int = 4,
        store_all: bool = False
    ) -> DatabaseSearchResult:
        """
        Execute smart search and store results in database.
        
        Args:
            drug_synonyms: List of drug names/codes
            disease: Optional disease/indication
            nct_id: Optional NCT ID to anchor search
            k_top: Number of top results to evaluate
            promote_threshold: Score threshold for promotion
            store_all: Whether to store all results or just promoted ones
            
        Returns:
            DatabaseSearchResult with storage information
        """
        logger.info(f"Starting database-integrated smart search for drug: {drug_synonyms}")
        
        # Execute the smart search
        search_result = self.smart_search(
            drug_synonyms=drug_synonyms,
            disease=disease,
            nct_id=nct_id,
            k_top=k_top,
            promote_threshold=promote_threshold
        )
        
        # Store results in database
        storage_result = self._store_search_results(search_result, store_all)
        
        return DatabaseSearchResult(
            search_result=search_result,
            documents_created=storage_result["created"],
            documents_updated=storage_result["updated"],
            errors=storage_result["errors"]
        )
    
    def _store_search_results(self, search_result: SearchResult, store_all: bool) -> Dict[str, Any]:
        """
        Store search results in the database.
        
        Args:
            search_result: The search result to store
            store_all: Whether to store all results or just promoted ones
            
        Returns:
            Dict with storage statistics
        """
        documents_to_store = search_result.top_summaries if store_all else []
        
        if search_result.decision == "promote" and search_result.promoted_ids:
            # Get promoted summaries
            promoted_summaries = [
                s for s in search_result.top_summaries 
                if s.pmid in search_result.promoted_ids
            ]
            documents_to_store.extend(promoted_summaries)
        
        # Remove duplicates
        unique_docs = {}
        for doc in documents_to_store:
            if doc.pmid not in unique_docs:
                unique_docs[doc.pmid] = doc
        
        documents_to_store = list(unique_docs.values())
        
        logger.info(f"Storing {len(documents_to_store)} documents in database")
        
        created_count = 0
        updated_count = 0
        errors = []
        
        for summary in documents_to_store:
            try:
                result = self._store_single_document(summary)
                if result == "created":
                    created_count += 1
                elif result == "updated":
                    updated_count += 1
                    
            except Exception as e:
                error_msg = f"Failed to store PMID {summary.pmid}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Add search metadata note
        try:
            self._add_search_metadata_note(search_result)
        except Exception as e:
            error_msg = f"Failed to add search metadata note: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
        
        return {
            "created": created_count,
            "updated": updated_count,
            "errors": errors
        }
    
    def _store_single_document(self, summary: PubMedSummary) -> str:
        """
        Store a single document summary in the database.
        
        Args:
            summary: PubMed summary to store
            
        Returns:
            "created", "updated", or "error"
        """
        # Check if document already exists
        existing_doc = self.db_session.query(Document).filter(
            Document.pmid == summary.pmid
        ).first()
        
        if existing_doc:
            logger.info(f"Document already exists for PMID {summary.pmid}, updating...")
            return self._update_existing_document(existing_doc, summary)
        else:
            logger.info(f"Creating new document for PMID {summary.pmid}")
            return self._create_new_document(summary)
    
    def _create_new_document(self, summary: PubMedSummary) -> str:
        """Create a new document record."""
        try:
            # Create document
            doc = Document(
                source_type='Paper',
                title=summary.title,
                pmid=summary.pmid,
                status='discovered',
                discovered_at=datetime.now(),
                published_at=self._parse_pub_date(summary.pub_date)
            )
            
            self.db_session.add(doc)
            self.db_session.flush()  # Get the doc_id
            
            # Create citation
            citation = DocumentCitation(
                doc_id=doc.doc_id,
                pmid=summary.pmid
            )
            self.db_session.add(citation)
            
            # Add search metadata as note
            note = DocumentNote(
                doc_id=doc.doc_id,
                note_type='search_metadata',
                note_text=f"Score: {summary.score}, Types: {', '.join(summary.pub_types)}, Journal: {summary.journal}"
            )
            self.db_session.add(note)
            
            # Add NCT IDs if present
            nct_ids = [aid for aid in summary.secondary_ids if 'NCT' in aid]
            if nct_ids:
                for nct_id in nct_ids:
                    nct_note = DocumentNote(
                        doc_id=doc.doc_id,
                        note_type='nct_id',
                        note_text=nct_id
                    )
                    self.db_session.add(nct_note)
            
            self.db_session.commit()
            logger.info(f"Created document {doc.doc_id} for PMID {summary.pmid}")
            return "created"
            
        except Exception as e:
            self.db_session.rollback()
            logger.error(f"Failed to create document for PMID {summary.pmid}: {e}")
            raise
    
    def _update_existing_document(self, existing_doc: Document, summary: PubMedSummary) -> str:
        """Update an existing document record."""
        try:
            # Update basic fields
            existing_doc.title = summary.title
            existing_doc.status = 'updated'
            
            # Add or update search metadata note
            existing_note = self.db_session.query(DocumentNote).filter(
                and_(
                    DocumentNote.doc_id == existing_doc.doc_id,
                    DocumentNote.note_type == 'search_metadata'
                )
            ).first()
            
            if existing_note:
                existing_note.note_text = f"Score: {summary.score}, Types: {', '.join(summary.pub_types)}, Journal: {summary.journal}"
            else:
                note = DocumentNote(
                    doc_id=existing_doc.doc_id,
                    note_type='search_metadata',
                    note_text=f"Score: {summary.score}, Types: {', '.join(summary.pub_types)}, Journal: {summary.journal}"
                )
                self.db_session.add(note)
            
            self.db_session.commit()
            logger.info(f"Updated document {existing_doc.doc_id} for PMID {summary.pmid}")
            return "updated"
            
        except Exception as e:
            self.db_session.rollback()
            logger.error(f"Failed to update document for PMID {summary.pmid}: {e}")
            raise
    
    def _add_search_metadata_note(self, search_result: SearchResult):
        """Add a note about the search metadata."""
        # Find a document to attach the note to (use the first one)
        if not search_result.top_summaries:
            return
        
        first_doc = self.db_session.query(Document).filter(
            Document.pmid == search_result.top_summaries[0].pmid
        ).first()
        
        if first_doc:
            search_note = DocumentNote(
                doc_id=first_doc.doc_id,
                note_type='search_summary',
                note_text=f"Search decision: {search_result.decision}, Reason: {search_result.reason}, Total hits: {search_result.total_hits}, Promoted: {len(search_result.promoted_ids) if search_result.promoted_ids else 0}"
            )
            self.db_session.add(search_note)
            self.db_session.commit()
    
    def _parse_pub_date(self, pub_date: str) -> Optional[datetime]:
        """Parse publication date string to datetime."""
        try:
            # Handle various date formats
            if not pub_date:
                return None
            
            # Try common formats
            formats = [
                "%Y %b",  # "2023 Jan"
                "%Y %B",  # "2023 January" 
                "%Y",     # "2023"
                "%Y %b %d",  # "2023 Jan 15"
                "%Y %B %d"   # "2023 January 15"
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(pub_date, fmt)
                except ValueError:
                    continue
            
            return None
            
        except Exception:
            return None
    
    def get_stored_documents(self, drug_name: str, limit: int = 100) -> List[Document]:
        """Retrieve stored documents for a drug."""
        # Search in document notes for drug mentions
        notes = self.db_session.query(DocumentNote).filter(
            and_(
                DocumentNote.note_type == 'search_metadata',
                DocumentNote.note_text.contains(drug_name)
            )
        ).limit(limit).all()
        
        doc_ids = [note.doc_id for note in notes]
        
        if doc_ids:
            return self.db_session.query(Document).filter(
                Document.doc_id.in_(doc_ids)
            ).all()
        
        return []
    
    def get_search_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored documents."""
        total_docs = self.db_session.query(Document).count()
        discovered_docs = self.db_session.query(Document).filter(
            Document.status == 'discovered'
        ).count()
        updated_docs = self.db_session.query(Document).filter(
            Document.status == 'updated'
        ).count()
        
        # Count by source type
        source_types = self.db_session.query(Document.source_type).distinct().all()
        type_counts = {}
        for source_type in source_types:
            count = self.db_session.query(Document).filter(
                Document.source_type == source_type[0]
            ).count()
            type_counts[source_type[0]] = count
        
        return {
            "total_documents": total_docs,
            "discovered_documents": discovered_docs,
            "updated_documents": updated_docs,
            "by_source_type": type_counts
        }


# Convenience function for database-integrated search
def quick_smart_search_db(
    db_session: Session,
    drug_name: str,
    disease: Optional[str] = None,
    nct_id: Optional[str] = None
) -> DatabaseSearchResult:
    """
    Quick database-integrated smart search for a single drug.
    
    Args:
        db_session: Database session
        drug_name: Drug name (e.g., "ruxolitinib")
        disease: Optional disease (e.g., "myelofibrosis")
        nct_id: Optional NCT ID
        
    Returns:
        DatabaseSearchResult with decision and storage info
    """
    client = SmartPubMedDBClient(db_session)
    return client.smart_search_with_storage(
        drug_synonyms=[drug_name],
        disease=disease,
        nct_id=nct_id
    )
