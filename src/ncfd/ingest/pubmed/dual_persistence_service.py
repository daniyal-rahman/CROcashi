"""
Dual Persistence Service - Manages raw and processed document storage.

Implements the dual persistence strategy:
1. Retrieval: Store ALL documents found during retrieval (human verification)
2. Processing: Store only filtered, processed documents (LLM processing)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from ...db.session import session_scope
from ...db.retrieval_models import RetrievalSession, RetrievalDocument, ProcessedDocument

logger = logging.getLogger(__name__)


@dataclass
class DualPersistenceResult:
    """Result from dual persistence operations."""
    success: bool
    retrieval_documents_stored: int
    processed_documents_stored: int
    session_id: Optional[str] = None
    error_message: Optional[str] = None


class DualPersistenceService:
    """Manages dual persistence of retrieval and processed documents."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize dual persistence service."""
        self.config = config or {}
        logger.info("Dual persistence service initialized")
    
    async def create_retrieval_session(
        self, 
        trial_id: int,
        asset_aliases: List[str],
        indication_terms: List[str],
        query_metadata: Dict[str, Any],
        session_id: Optional[str] = None
    ) -> str:
        """Create a new retrieval session for tracking."""
        if session_id is None:
            session_id = str(uuid.uuid4())  # Use full UUID, not truncated
        
        with session_scope() as session:
            retrieval_session = RetrievalSession(
                trial_id=trial_id,
                session_id=session_id,
                asset_aliases={"aliases": asset_aliases},
                indication_terms={"terms": indication_terms},
                query_metadata=query_metadata,
                status='running'
            )
            session.add(retrieval_session)
            session.commit()
            
        logger.error(f"DEBUG: Created retrieval session {session_id} for trial {trial_id}")
        
        # Verify the session was created by immediately checking for it
        with session_scope() as verify_session:
            verify_result = verify_session.query(RetrievalSession).filter(
                RetrievalSession.session_id == session_id
            ).first()
            if verify_result:
                logger.error(f"DEBUG: Verified retrieval session {session_id} exists in database")
            else:
                logger.error(f"DEBUG: Failed to verify retrieval session {session_id} exists in database")
        
        return session_id
    
    async def store_retrieval_documents(
        self,
        trial_id: int,
        session_id: str,
        documents: List[Dict[str, Any]],
        retrieval_metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Store all retrieved documents (raw data for human verification)."""
        logger.error(f"DEBUG: store_retrieval_documents called with session_id: {session_id}")
        if not documents:
            return 0
        
        # Get the session ID from the database with retry logic
        with session_scope() as session:
            # Try to find the session, with a small retry in case of timing issues
            retrieval_session = None
            for attempt in range(3):
                retrieval_session = session.query(RetrievalSession).filter(
                    RetrievalSession.session_id == session_id
                ).first()
                
                if retrieval_session:
                    break
                    
                if attempt < 2:  # Don't sleep on last attempt
                    import time
                    time.sleep(0.1)  # Small delay to allow for transaction commit
            
            if not retrieval_session:
                logger.error(f"Retrieval session {session_id} not found after 3 attempts")
                return 0
            
            stored_count = 0
            failed_count = 0
            duplicate_count = 0
            
            for doc in documents:
                try:
                    pmid = doc.get('pmid')
                    if not pmid:
                        logger.warning(f"Document missing PMID: {doc}")
                        failed_count += 1
                        continue
                    
                    # Check for existing document with same trial_id and pmid
                    existing = session.query(RetrievalDocument).filter(
                        RetrievalDocument.trial_id == trial_id,
                        RetrievalDocument.pmid == pmid
                    ).first()
                    
                    if existing:
                        logger.debug(f"Document {pmid} already exists for trial {trial_id}, skipping")
                        duplicate_count += 1
                        continue
                    
                    retrieval_doc = RetrievalDocument(
                        trial_id=trial_id,
                        session_id=retrieval_session.id,
                        pmid=doc.get('pmid'),
                        title=doc.get('title'),
                        abstract=doc.get('abstract'),
                        authors=doc.get('authors'),
                        journal=doc.get('journal'),
                        published_at=doc.get('published_at'),
                        retrieval_score=doc.get('retrieval_score'),
                        retrieval_tier=doc.get('retrieval_tier'),
                        query_tier=doc.get('query_tier'),
                        policy_engine_passed=doc.get('policy_engine_passed'),
                        guardrails_passed=doc.get('guardrails_passed'),
                        retrieval_metadata=doc.get('retrieval_metadata', {})
                    )
                    session.add(retrieval_doc)
                    stored_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to store retrieval document {doc.get('pmid', 'unknown')}: {e}")
                    failed_count += 1
                    continue
            
            session.commit()
            logger.info(f"Stored {stored_count} retrieval documents, {failed_count} failed, {duplicate_count} duplicates skipped")
            return stored_count
    
    async def store_processed_documents(
        self,
        trial_id: int,
        documents: List[Dict[str, Any]]
    ) -> int:
        """Store processed documents (filtered data for LLM processing)."""
        if not documents:
            return 0
        
        with session_scope() as session:
            stored_count = 0
            failed_count = 0
            duplicate_count = 0
            
            for doc in documents:
                try:
                    pmid = doc.get('pmid')
                    if not pmid:
                        logger.warning(f"Processed document missing PMID: {doc}")
                        failed_count += 1
                        continue
                    
                    # Check for existing processed document with same trial_id and pmid
                    existing = session.query(ProcessedDocument).filter(
                        ProcessedDocument.trial_id == trial_id,
                        ProcessedDocument.pmid == pmid
                    ).first()
                    
                    if existing:
                        logger.debug(f"Processed document {pmid} already exists for trial {trial_id}, skipping")
                        duplicate_count += 1
                        continue
                    
                    processed_doc = ProcessedDocument(
                        trial_id=trial_id,
                        retrieval_doc_id=doc.get('retrieval_doc_id'),
                        pmid=doc.get('pmid'),
                        title=doc.get('title'),
                        abstract=doc.get('abstract'),
                        r_score=doc.get('r_score'),
                        s_score=doc.get('s_score'),
                        rs_tier=doc.get('rs_tier'),
                        entities=doc.get('entities'),
                        processing_metadata=doc.get('processing_metadata', {})
                    )
                    session.add(processed_doc)
                    stored_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to store processed document {doc.get('pmid', 'unknown')}: {e}")
                    failed_count += 1
                    continue
            
            session.commit()
            logger.info(f"Stored {stored_count} processed documents, {failed_count} failed, {duplicate_count} duplicates skipped")
            return stored_count
    
    async def get_existing_documents_count(self, trial_id: int) -> int:
        """Get count of existing processed documents for a trial."""
        with session_scope() as session:
            count = session.query(ProcessedDocument).filter(
                ProcessedDocument.trial_id == trial_id
            ).count()
            logger.debug(f"Found {count} existing processed documents for trial {trial_id}")
            return count
    
    async def get_existing_documents(self, trial_id: int) -> List[Dict[str, Any]]:
        """Get existing processed documents for a trial."""
        with session_scope() as session:
            docs = session.query(ProcessedDocument).filter(
                ProcessedDocument.trial_id == trial_id
            ).all()
            
            result = []
            for doc in docs:
                result.append({
                    'pmid': doc.pmid,
                    'title': doc.title,
                    'abstract': doc.abstract,
                    'r_score': doc.r_score,
                    's_score': doc.s_score,
                    'rs_tier': doc.rs_tier,
                    'entities': doc.entities,
                    'retrieval_doc_id': doc.retrieval_doc_id,
                    'processing_metadata': doc.processing_metadata
                })
            
            logger.debug(f"Retrieved {len(result)} existing processed documents for trial {trial_id}")
            return result
    
    async def update_session_completion(
        self,
        session_id: str,
        total_documents_found: int,
        documents_after_policy_engine: int,
        documents_after_guardrails: int,
        documents_after_processing: int,
        execution_time_seconds: float,
        status: str = 'completed'
    ) -> bool:
        """Update retrieval session with completion data."""
        try:
            with session_scope() as session:
                retrieval_session = session.query(RetrievalSession).filter(
                    RetrievalSession.session_id == session_id
                ).first()
                
                if not retrieval_session:
                    logger.error(f"Retrieval session {session_id} not found")
                    return False
                
                retrieval_session.total_documents_found = total_documents_found
                retrieval_session.documents_after_policy_engine = documents_after_policy_engine
                retrieval_session.documents_after_guardrails = documents_after_guardrails
                retrieval_session.documents_after_processing = documents_after_processing
                retrieval_session.execution_time_seconds = execution_time_seconds
                retrieval_session.status = status
                retrieval_session.completed_at = datetime.now(timezone.utc)
                
                session.commit()
                logger.info(f"Updated session {session_id} with completion data")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return False
    
    async def get_retrieval_documents(
        self, 
        trial_id: int, 
        session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get retrieval documents for a trial."""
        with session_scope() as session:
            query = session.query(RetrievalDocument).filter(
                RetrievalDocument.trial_id == trial_id
            )
            
            if session_id:
                # Get the session ID from the database
                retrieval_session = session.query(RetrievalSession).filter(
                    RetrievalSession.session_id == session_id
                ).first()
                if retrieval_session:
                    query = query.filter(RetrievalDocument.session_id == retrieval_session.id)
            
            documents = query.all()
            return [
                {
                    'id': doc.id,
                    'pmid': doc.pmid,
                    'title': doc.title,
                    'abstract': doc.abstract,
                    'authors': doc.authors,
                    'journal': doc.journal,
                    'published_at': doc.published_at,
                    'retrieval_score': doc.retrieval_score,
                    'retrieval_tier': doc.retrieval_tier,
                    'query_tier': doc.query_tier,
                    'policy_engine_passed': doc.policy_engine_passed,
                    'guardrails_passed': doc.guardrails_passed,
                    'retrieval_metadata': doc.retrieval_metadata,
                    'created_at': doc.created_at
                }
                for doc in documents
            ]
    
    async def get_processed_documents(
        self, 
        trial_id: int
    ) -> List[Dict[str, Any]]:
        """Get processed documents for a trial."""
        with session_scope() as session:
            documents = session.query(ProcessedDocument).filter(
                ProcessedDocument.trial_id == trial_id
            ).all()
            
            return [
                {
                    'id': doc.id,
                    'retrieval_doc_id': doc.retrieval_doc_id,
                    'pmid': doc.pmid,
                    'title': doc.title,
                    'abstract': doc.abstract,
                    'r_score': doc.r_score,
                    's_score': doc.s_score,
                    'rs_tier': doc.rs_tier,
                    'entities': doc.entities,
                    'processing_metadata': doc.processing_metadata,
                    'created_at': doc.created_at
                }
                for doc in documents
            ]
    
    async def get_session_metrics(
        self, 
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get metrics for a retrieval session."""
        with session_scope() as session:
            retrieval_session = session.query(RetrievalSession).filter(
                RetrievalSession.session_id == session_id
            ).first()
            
            if not retrieval_session:
                return None
            
            return {
                'session_id': retrieval_session.session_id,
                'trial_id': retrieval_session.trial_id,
                'status': retrieval_session.status,
                'total_documents_found': retrieval_session.total_documents_found,
                'documents_after_policy_engine': retrieval_session.documents_after_policy_engine,
                'documents_after_guardrails': retrieval_session.documents_after_guardrails,
                'documents_after_processing': retrieval_session.documents_after_processing,
                'execution_time_seconds': retrieval_session.execution_time_seconds,
                'created_at': retrieval_session.created_at,
                'completed_at': retrieval_session.completed_at
            }
