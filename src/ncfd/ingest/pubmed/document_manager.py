"""
Simplified Document Manager for Trial-Document Associations

This module provides a clean, simple interface for managing trial-document
relationships using the new simplified system where all association data
is stored directly in the documents table.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from ...db.session import session_scope
from ...db.models import Document, Trial
from ...utils.config_manager import get_config_manager
from ...utils.error_handler import get_error_handler, safe_execute

logger = logging.getLogger(__name__)


class DocumentManager:
    """Simplified manager for trial-document associations."""
    
    def add_document_to_trial(self, trial_id: int, doc_id: int, 
                            retrieval_tier: str = 'A', 
                            link_confidence: float = 0.8) -> bool:
        """
        Add document to trial with initial state.
        
        Args:
            trial_id: Trial ID
            doc_id: Document ID
            retrieval_tier: Retrieval tier (A, B, C, D)
            link_confidence: Confidence in the association (0.0-1.0)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                # Check if already associated
                existing = session.query(Document).filter(
                    Document.doc_id == doc_id,
                    Document.trial_id == trial_id
                ).first()
                
                if existing:
                    logger.debug(f"Document {doc_id} already associated with trial {trial_id}")
                    return True
                
                # Update document with trial association
                document = session.query(Document).filter(Document.doc_id == doc_id).first()
                if not document:
                    logger.error(f"Document {doc_id} not found")
                    return False
                
                document.trial_id = trial_id
                document.processing_status = 'discovered'
                document.retrieval_tier = retrieval_tier
                document.link_confidence = link_confidence
                document.processing_notes = f"Associated with trial {trial_id} via retrieval tier {retrieval_tier}"
                
                session.commit()
                logger.info(f"Associated document {doc_id} with trial {trial_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to associate document {doc_id} with trial {trial_id}: {e}")
            return False
    
    def score_document(self, doc_id: int, r_score: float, s_score: float,
                      r_components: Optional[Dict[str, Any]] = None,
                      s_components: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update document with R/S scores.
        
        Args:
            doc_id: Document ID
            r_score: Relevance score (0.0-1.0)
            s_score: Shortability score (0.0-1.0)
            r_components: R score components
            s_components: S score components
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                document = session.query(Document).filter(Document.doc_id == doc_id).first()
                if not document:
                    logger.error(f"Document {doc_id} not found")
                    return False
                
                # Update scores
                document.r_score = r_score
                document.s_score = s_score
                document.r_tier = self._determine_r_tier(r_score)
                document.s_tier = self._determine_s_tier(s_score)
                document.r_components = r_components
                document.s_components = s_components
                document.processing_status = 'scored'
                document.scored_at = datetime.now(timezone.utc)
                document.rs_decided_at = datetime.now(timezone.utc)
                
                session.commit()
                logger.debug(f"Scored document {doc_id}: R={r_score:.3f} ({document.r_tier}), S={s_score:.3f} ({document.s_tier})")
                return True
                
        except Exception as e:
            logger.error(f"Failed to score document {doc_id}: {e}")
            return False
    
    def select_documents_for_processing(self, trial_id: int, 
                                      max_documents: int = 20) -> List[int]:
        """
        Select top documents for processing based on priority.
        
        Args:
            trial_id: Trial ID
            max_documents: Maximum number of documents to select
            
        Returns:
            List of selected document IDs
        """
        try:
            with session_scope() as session:
                # Get scored documents ordered by priority
                candidates = session.query(Document).filter(
                    Document.trial_id == trial_id,
                    Document.processing_status == 'scored'
                ).order_by(
                    Document.r_score.desc(),
                    Document.s_score.desc()
                ).limit(max_documents).all()
                
                # Update status to selected
                doc_ids = []
                for document in candidates:
                    document.processing_status = 'selected'
                    document.selected_at = datetime.now(timezone.utc)
                    doc_ids.append(document.doc_id)
                
                session.commit()
                logger.info(f"Selected {len(doc_ids)} documents for trial {trial_id}")
                return doc_ids
                
        except Exception as e:
            logger.error(f"Failed to select documents for trial {trial_id}: {e}")
            return []
    
    def mark_document_processed(self, doc_id: int) -> bool:
        """
        Mark document as processed.
        
        Args:
            doc_id: Document ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                document = session.query(Document).filter(Document.doc_id == doc_id).first()
                if not document:
                    logger.error(f"Document {doc_id} not found")
                    return False
                
                document.processing_status = 'processed'
                document.processed_at = datetime.now(timezone.utc)
                
                session.commit()
                logger.debug(f"Marked document {doc_id} as processed")
                return True
                
        except Exception as e:
            logger.error(f"Failed to mark document {doc_id} as processed: {e}")
            return False
    
    def mark_study_card_generated(self, doc_id: int) -> bool:
        """
        Mark document as having study card generated.
        
        Args:
            doc_id: Document ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                document = session.query(Document).filter(Document.doc_id == doc_id).first()
                if not document:
                    logger.error(f"Document {doc_id} not found")
                    return False
                
                document.processing_status = 'study_card_generated'
                document.study_card_generated_at = datetime.now(timezone.utc)
                
                session.commit()
                logger.debug(f"Marked document {doc_id} as study card generated")
                return True
                
        except Exception as e:
            logger.error(f"Failed to mark document {doc_id} as study card generated: {e}")
            return False
    
    def get_trial_documents(self, trial_id: int, 
                          status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all documents for a trial, optionally filtered by status.
        
        Args:
            trial_id: Trial ID
            status: Optional processing status filter
            
        Returns:
            List of document data dictionaries
        """
        try:
            with session_scope() as session:
                # Use DocumentLink table to find documents linked to this trial
                from ncfd.db.models import DocumentLink
                linked_doc_ids = session.query(DocumentLink.doc_id).filter(
                    DocumentLink.trial_id == trial_id
                ).all()
                linked_doc_ids = [row[0] for row in linked_doc_ids]
                
                if not linked_doc_ids:
                    return []
                
                query = session.query(Document).filter(Document.doc_id.in_(linked_doc_ids))
                
                if status:
                    query = query.filter(Document.status == status)
                
                documents = query.all()
                
                return [
                    {
                        'doc_id': doc.doc_id,
                        'title': doc.title,
                        'pmid': doc.pmid,
                        'pmcid': doc.pmcid,
                        'processing_status': doc.processing_status,
                        'processing_priority': doc.processing_priority,
                        'retrieval_tier': doc.retrieval_tier,
                        'r_score': float(doc.r_score) if doc.r_score else None,
                        's_score': float(doc.s_score) if doc.s_score else None,
                        'r_tier': doc.r_tier,
                        's_tier': doc.s_tier,
                        'link_confidence': float(doc.link_confidence) if doc.link_confidence else None,
                        'discovered_at': doc.discovered_at,
                        'scored_at': doc.scored_at,
                        'selected_at': doc.selected_at,
                        'processed_at': doc.processed_at,
                        'study_card_generated_at': doc.study_card_generated_at,
                        'processing_notes': doc.processing_notes
                    }
                    for doc in documents
                ]
                
        except Exception as e:
            logger.error(f"Failed to get documents for trial {trial_id}: {e}")
            return []
    
    def get_trial_literature_summary(self, trial_id: int) -> Dict[str, Any]:
        """
        Get trial literature summary computed from documents.
        
        Args:
            trial_id: Trial ID
            
        Returns:
            Trial literature summary
        """
        try:
            with session_scope() as session:
                docs = session.query(Document).filter(Document.trial_id == trial_id).all()
                
                # Compute metrics
                total_docs = len(docs)
                scored_docs = len([d for d in docs if d.processing_status in ['scored', 'selected', 'processed', 'study_card_generated']])
                selected_docs = len([d for d in docs if d.processing_status in ['selected', 'processed', 'study_card_generated']])
                processed_docs = len([d for d in docs if d.processing_status in ['processed', 'study_card_generated']])
                study_card_docs = len([d for d in docs if d.processing_status == 'study_card_generated'])
                
                # Best S score among R≥2 documents
                r2_plus_docs = [d for d in docs if d.r_tier in ['R2', 'R3']]
                best_s_rge2 = max([float(d.s_score) for d in r2_plus_docs if d.s_score], default=None)
                
                # Processing status distribution
                status_counts = {}
                for doc in docs:
                    status = doc.processing_status
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                return {
                    'trial_id': trial_id,
                    'total_documents': total_docs,
                    'scored_documents': scored_docs,
                    'selected_documents': selected_docs,
                    'processed_documents': processed_docs,
                    'study_cards_generated': study_card_docs,
                    'best_s_rge2': best_s_rge2,
                    'status_distribution': status_counts,
                    'processing_status': self._determine_trial_status(docs)
                }
                
        except Exception as e:
            logger.error(f"Failed to get literature summary for trial {trial_id}: {e}")
            return {}
    
    def _determine_r_tier(self, r_score: float) -> str:
        """Determine R tier based on score."""
        if r_score >= 0.75:
            return "R3"
        elif r_score >= 0.55:
            return "R2"
        elif r_score >= 0.35:
            return "R1"
        else:
            return "R0"
    
    def _determine_s_tier(self, s_score: float) -> str:
        """Determine S tier based on score."""
        if s_score >= 0.70:
            return "S3"
        elif s_score >= 0.45:
            return "S2"
        elif s_score >= 0.20:
            return "S1"
        else:
            return "S0"
    
    def _determine_trial_status(self, docs: List[Document]) -> str:
        """Determine overall trial processing status."""
        if not docs:
            return 'no_documents'
        
        statuses = [doc.processing_status for doc in docs]
        
        if 'study_card_generated' in statuses:
            return 'study_cards_generated'
        elif 'processed' in statuses:
            return 'processing_complete'
        elif 'selected' in statuses:
            return 'documents_selected'
        elif 'scored' in statuses:
            return 'documents_scored'
        else:
            return 'documents_discovered'
