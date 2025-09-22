"""
Document Utilities

Shared utilities for document ID resolution and metadata retrieval.
"""

import logging
from typing import Optional, Dict, Any
from ...db.models import Document, DocumentText
from ...db.session import get_session

logger = logging.getLogger(__name__)


def resolve_external_doc_id(session, external_doc_id: str) -> Optional[int]:
    """
    Resolve external document ID to internal doc_id.
    
    Args:
        session: Database session
        external_doc_id: External document ID in various formats
        
    Returns:
        Internal doc_id (integer) or None if not found
    """
    if not external_doc_id:
        return None
    
    # Handle plain integer doc_id (from database)
    if external_doc_id.isdigit():
        return int(external_doc_id)
    
    if ':' in external_doc_id:
        source, identifier = external_doc_id.split(':', 1)
        source = source.lower()
        
        if source == 'ctgov':
            document = session.query(Document).filter(
                Document.nct_id == identifier
            ).first()
        elif source == 'pmc':
            document = session.query(Document).filter(
                Document.pmcid == identifier
            ).first()
        elif source == 'pmid':
            document = session.query(Document).filter(
                Document.pmid == identifier
            ).first()
        elif source == 'db':
            try:
                internal_id = int(identifier)
                document = session.query(Document).filter(
                    Document.doc_id == internal_id
                ).first()
            except ValueError:
                return None
        else:
            # Handle sec:, fda:, pr: etc.
            document = session.query(Document).filter(
                Document.source_type == source.upper(),
                Document.source_url.contains(identifier)
            ).first()
    else:
        try:
            internal_id = int(external_doc_id)
            document = session.query(Document).filter(
                Document.doc_id == internal_id
            ).first()
        except ValueError:
            return None
    
    return document.doc_id if document else None


def get_document_metadata(session, doc_id: str) -> Optional[Dict[str, Any]]:
    """
    Get document metadata from database.
    
    Args:
        session: Database session
        doc_id: Document ID (external or internal)
        
    Returns:
        Dictionary with document metadata or None if not found
    """
    try:
        # Resolve external doc_id to internal doc_id
        internal_doc_id = resolve_external_doc_id(session, doc_id)
        if not internal_doc_id:
            return None
        
        document = session.query(Document).filter(
            Document.doc_id == internal_doc_id
        ).first()
        
        if not document:
            return None
        
        return {
            "doc_id": internal_doc_id,
            "pmid": document.pmid,
            "pmcid": document.pmcid,
            "doi": document.doi,
            "title": document.title,
            "source_type": document.source_type,
            "nct_id": document.nct_id,
            "published_at": document.published_at
        }
        
    except Exception as e:
        logger.error(f"Error getting metadata for doc {doc_id}: {e}")
        return None


def get_document_text(session, doc_id: str, prefer_fulltext: bool = True) -> str:
    """
    Get document text content from database.
    
    Args:
        session: Database session
        doc_id: Document ID (external or internal)
        prefer_fulltext: Whether to prefer full text over abstract
        
    Returns:
        Document text content or empty string if not found
    """
    try:
        # Resolve external doc_id to internal doc_id
        internal_doc_id = resolve_external_doc_id(session, doc_id)
        if not internal_doc_id:
            return ""
        
        doc_text = session.query(DocumentText).filter(
            DocumentText.doc_id == internal_doc_id
        ).first()
        
        if not doc_text:
            return ""
        
        # Always prefer fulltext over abstract when available
        if doc_text.fulltext_text:
            fulltext_length = len(doc_text.fulltext_text)
            logger.debug(f"Retrieved {fulltext_length} characters of fulltext from database")
            return doc_text.fulltext_text
        
        # Fallback to abstract only if no fulltext available
        if doc_text.abstract_text:
            abstract_length = len(doc_text.abstract_text)
            logger.debug(f"Retrieved {abstract_length} characters of abstract text from database")
            return doc_text.abstract_text
        
        return ""
        
    except Exception as e:
        logger.error(f"Error getting text from database for doc {doc_id}: {e}")
        return ""


def get_standardized_doc_id(doc: Document) -> str:
    """
    Get standardized doc_id format per docs/ids.md.
    
    Args:
        doc: Document object from database
        
    Returns:
        Standardized doc_id string
    """
    # Priority order: nct_id > pmcid > pmid > source_type fallback > db fallback
    if doc.nct_id:
        return f"ctgov:{doc.nct_id}"
    elif doc.pmcid:
        return f"pmc:{doc.pmcid}"
    elif doc.pmid:
        return f"pmid:{doc.pmid}"
    elif doc.source_type:
        source_lower = doc.source_type.lower()
        if source_lower in ['sec', '8k', '10k', '10q']:
            return f"sec:{doc.doc_id}"
        elif source_lower in ['pr', 'press_release']:
            return f"pr:{doc.doc_id}"
        elif source_lower in ['fda']:
            return f"fda:{doc.doc_id}"
    
    # Fallback to db: prefix
    return f"db:{doc.doc_id}"
