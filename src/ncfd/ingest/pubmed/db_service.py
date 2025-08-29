"""
Database service for PubMed literature processing.

Handles persistence of R/S scores, trial-document relationships, and trial literature state.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ...db.models import Document, DocRSScore, TrialDocCandidate, TrialLitState
from ...db.session import session_scope

logger = logging.getLogger(__name__)


class PubMedDBService:
    """Database service for PubMed literature processing."""
    
    def __init__(self):
        """Initialize the database service."""
        self.logger = logger
    
    def store_rs_scores(
        self, 
        trial_id: int, 
        rs_scores: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Store R/S scores for documents.
        
        Args:
            trial_id: Trial ID
            rs_scores: List of R/S score records
            
        Returns:
            Tuple of (successful_inserts, failed_inserts)
        """
        successful = 0
        failed = 0
        
        with session_scope() as session:
            for score_record in rs_scores:
                try:
                    # If doc_id is None, try to look it up by PMID
                    doc_id = score_record.get('doc_id')
                    if doc_id is None and score_record.get('pmid'):
                        # Look up document by PMID
                        document = session.query(Document).filter(
                            Document.pmid == score_record['pmid']
                        ).first()
                        if document:
                            doc_id = document.doc_id
                        else:
                            self.logger.warning(f"Document with PMID {score_record['pmid']} not found in database")
                            failed += 1
                            continue
                    
                    if doc_id is None:
                        self.logger.warning(f"No doc_id available for R/S score: {score_record}")
                        failed += 1
                        continue
                    
                    # Check if record already exists
                    existing = session.query(DocRSScore).filter(
                        DocRSScore.trial_id == trial_id,
                        DocRSScore.doc_id == doc_id
                    ).first()
                    
                    if existing:
                        # Update existing record
                        existing.R_score = Decimal(str(score_record['R_score']))
                        existing.R_tier = score_record['R_tier']
                        existing.S_score = Decimal(str(score_record['S_score']))
                        existing.S_tier = score_record['S_tier']
                        existing.R_components_jsonb = score_record.get('R_components_jsonb')
                        existing.S_components_jsonb = score_record.get('S_components_jsonb')
                        existing.decided_at = datetime.utcnow()
                        self.logger.debug(f"Updated R/S score for trial {trial_id}, doc {doc_id}")
                    else:
                        # Create new record
                        rs_score = DocRSScore(
                            trial_id=trial_id,
                            doc_id=doc_id,
                            R_score=Decimal(str(score_record['R_score'])),
                            R_tier=score_record['R_tier'],
                            S_score=Decimal(str(score_record['S_score'])),
                            S_tier=score_record['S_tier'],
                            R_components_jsonb=score_record.get('R_components_jsonb'),
                            S_components_jsonb=score_record.get('S_components_jsonb'),
                            decided_at=datetime.utcnow()
                        )
                        session.add(rs_score)
                        self.logger.debug(f"Created R/S score for trial {trial_id}, doc {doc_id}")
                    
                    successful += 1
                    
                except (IntegrityError, SQLAlchemyError) as e:
                    failed += 1
                    self.logger.error(f"Failed to store R/S score for trial {trial_id}, doc {score_record.get('doc_id', 'unknown')}: {e}")
                    continue
                except Exception as e:
                    failed += 1
                    self.logger.error(f"Unexpected error storing R/S score: {e}")
                    continue
        
        self.logger.info(f"Stored R/S scores: {successful} successful, {failed} failed")
        return successful, failed
    
    def store_trial_doc_candidates(
        self, 
        trial_id: int, 
        candidates: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Store trial-document candidate relationships.
        
        Args:
            trial_id: Trial ID
            candidates: List of candidate records
            
        Returns:
            Tuple of (successful_inserts, failed_inserts)
        """
        successful = 0
        failed = 0
        
        with session_scope() as session:
            for candidate in candidates:
                try:
                    # If doc_id is None, try to look it up by PMID
                    doc_id = candidate.get('doc_id')
                    if doc_id is None and candidate.get('pmid'):
                        # Look up document by PMID
                        document = session.query(Document).filter(
                            Document.pmid == candidate['pmid']
                        ).first()
                        if document:
                            doc_id = document.doc_id
                        else:
                            self.logger.warning(f"Document with PMID {candidate['pmid']} not found in database")
                            failed += 1
                            continue
                    
                    if doc_id is None:
                        self.logger.warning(f"No doc_id available for candidate: {candidate}")
                        failed += 1
                        continue
                    
                    # Check if record already exists
                    existing = session.query(TrialDocCandidate).filter(
                        TrialDocCandidate.trial_id == trial_id,
                        TrialDocCandidate.doc_id == doc_id
                    ).first()
                    
                    if existing:
                        # Update existing record
                        existing.stage = candidate['stage']
                        existing.selected = candidate.get('selected')
                        existing.dropped_reason = candidate.get('dropped_reason')
                        existing.notes = candidate.get('notes')
                        self.logger.debug(f"Updated trial-doc candidate for trial {trial_id}, doc {doc_id}")
                    else:
                        # Create new record
                        trial_doc = TrialDocCandidate(
                            trial_id=trial_id,
                            doc_id=doc_id,
                            stage=candidate['stage'],
                            selected=candidate.get('selected'),
                            dropped_reason=candidate.get('dropped_reason'),
                            notes=candidate.get('notes')
                        )
                        session.add(trial_doc)
                        self.logger.debug(f"Created trial-doc candidate for trial {trial_id}, doc {doc_id}")
                    
                    successful += 1
                    
                except (IntegrityError, SQLAlchemyError) as e:
                    failed += 1
                    self.logger.error(f"Failed to store trial-doc candidate for trial {trial_id}, doc {candidate.get('doc_id', 'unknown')}: {e}")
                    continue
                except Exception as e:
                    failed += 1
                    self.logger.error(f"Unexpected error storing trial-doc candidate: {e}")
                    continue
        
        self.logger.info(f"Stored trial-doc candidates: {successful} successful, {failed} failed")
        return successful, failed
    
    def update_trial_lit_state(
        self, 
        trial_id: int, 
        state_data: Dict[str, Any]
    ) -> bool:
        """
        Update trial literature state.
        
        Args:
            trial_id: Trial ID
            state_data: State data to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                # Check if record exists
                existing = session.query(TrialLitState).filter(
                    TrialLitState.trial_id == trial_id
                ).first()
                
                if existing:
                    # Update existing record
                    for key, value in state_data.items():
                        if hasattr(existing, key) and value is not None:
                            if key in ['best_S_Rge2', 'p_short', 'uncertainty', 'max_expected_utility_next_doc']:
                                setattr(existing, key, Decimal(str(value)))
                            else:
                                setattr(existing, key, value)
                    self.logger.debug(f"Updated trial lit state for trial {trial_id}")
                else:
                    # Create new record
                    lit_state = TrialLitState(
                        trial_id=trial_id,
                        best_S_Rge2=Decimal(str(state_data.get('best_S_Rge2', 0))) if state_data.get('best_S_Rge2') is not None else None,
                        n_docs_seen=state_data.get('n_docs_seen', 0),
                        n_docs_selected=state_data.get('n_docs_selected', 0),
                        p_short=Decimal(str(state_data.get('p_short', 0))) if state_data.get('p_short') is not None else None,
                        uncertainty=Decimal(str(state_data.get('uncertainty', 0))) if state_data.get('uncertainty') is not None else None,
                        max_expected_utility_next_doc=Decimal(str(state_data.get('max_expected_utility_next_doc', 0))) if state_data.get('max_expected_utility_next_doc') is not None else None,
                        status=state_data.get('status', 'active')
                    )
                    session.add(lit_state)
                    self.logger.debug(f"Created trial lit state for trial {trial_id}")
                
                return True
                
        except (IntegrityError, SQLAlchemyError) as e:
            self.logger.error(f"Failed to update trial lit state for trial {trial_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error updating trial lit state: {e}")
            return False
    
    def get_trial_lit_state(self, trial_id: int) -> Optional[Dict[str, Any]]:
        """
        Get trial literature state.
        
        Args:
            trial_id: Trial ID
            
        Returns:
            Trial literature state or None if not found
        """
        try:
            with session_scope() as session:
                lit_state = session.query(TrialLitState).filter(
                    TrialLitState.trial_id == trial_id
                ).first()
                
                if lit_state:
                    return {
                        'trial_id': lit_state.trial_id,
                        'best_S_Rge2': float(lit_state.best_S_Rge2) if lit_state.best_S_Rge2 else None,
                        'n_docs_seen': lit_state.n_docs_seen,
                        'n_docs_selected': lit_state.n_docs_selected,
                        'p_short': float(lit_state.p_short) if lit_state.p_short else None,
                        'uncertainty': float(lit_state.uncertainty) if lit_state.uncertainty else None,
                        'max_expected_utility_next_doc': float(lit_state.max_expected_utility_next_doc) if lit_state.max_expected_utility_next_doc else None,
                        'status': lit_state.status
                    }
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get trial lit state for trial {trial_id}: {e}")
            return None
    
    def get_document_rs_scores(self, trial_id: int) -> List[Dict[str, Any]]:
        """
        Get R/S scores for documents in a trial.
        
        Args:
            trial_id: Trial ID
            
        Returns:
            List of R/S score records
        """
        try:
            with session_scope() as session:
                rs_scores = session.query(DocRSScore).filter(
                    DocRSScore.trial_id == trial_id
                ).all()
                
                return [
                    {
                        'trial_id': score.trial_id,
                        'doc_id': score.doc_id,
                        'R_score': float(score.R_score),
                        'R_tier': score.R_tier,
                        'S_score': float(score.S_score),
                        'S_tier': score.S_tier,
                        'R_components_jsonb': score.R_components_jsonb,
                        'S_components_jsonb': score.S_components_jsonb,
                        'decided_at': score.decided_at.isoformat() if score.decided_at else None
                    }
                    for score in rs_scores
                ]
                
        except Exception as e:
            self.logger.error(f"Failed to get R/S scores for trial {trial_id}: {e}")
            return []
    
    def get_trial_doc_candidates(self, trial_id: int, stage: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get trial-document candidates.
        
        Args:
            trial_id: Trial ID
            stage: Optional stage filter
            
        Returns:
            List of candidate records
        """
        try:
            with session_scope() as session:
                query = session.query(TrialDocCandidate).filter(
                    TrialDocCandidate.trial_id == trial_id
                )
                
                if stage:
                    query = query.filter(TrialDocCandidate.stage == stage)
                
                candidates = query.all()
                
                return [
                    {
                        'trial_id': candidate.trial_id,
                        'doc_id': candidate.doc_id,
                        'stage': candidate.stage,
                        'selected': candidate.selected,
                        'dropped_reason': candidate.dropped_reason,
                        'notes': candidate.notes
                    }
                    for candidate in candidates
                ]
                
        except Exception as e:
            self.logger.error(f"Failed to get trial-doc candidates for trial {trial_id}: {e}")
            return []
    
    def calculate_trial_metrics(self, trial_id: int) -> Dict[str, Any]:
        """
        Calculate trial-level metrics from R/S scores.
        
        Args:
            trial_id: Trial ID
            
        Returns:
            Trial metrics
        """
        try:
            with session_scope() as session:
                # Get all R/S scores for the trial
                rs_scores = session.query(DocRSScore).filter(
                    DocRSScore.trial_id == trial_id
                ).all()
                
                if not rs_scores:
                    return {
                        'best_S_Rge2': None,
                        'n_docs_seen': 0,
                        'n_docs_selected': 0,
                        'p_short': None,
                        'uncertainty': None
                    }
                
                # Calculate best S score among R≥2 documents
                r2_plus_scores = [float(score.S_score) for score in rs_scores 
                                 if score.R_tier in ['R2', 'R3']]
                best_S_Rge2 = max(r2_plus_scores) if r2_plus_scores else None
                
                # Count documents
                n_docs_seen = len(rs_scores)
                n_docs_selected = len([score for score in rs_scores 
                                     if score.S_tier in ['S2', 'S3']])
                
                # Calculate p_short (probability of shortable)
                shortable_docs = len([score for score in rs_scores 
                                    if score.S_tier in ['S2', 'S3']])
                p_short = shortable_docs / n_docs_seen if n_docs_seen > 0 else 0
                
                # Calculate uncertainty (P*(1-P))
                uncertainty = p_short * (1 - p_short) if p_short is not None else 0
                
                return {
                    'best_S_Rge2': best_S_Rge2,
                    'n_docs_seen': n_docs_seen,
                    'n_docs_selected': n_docs_selected,
                    'p_short': p_short,
                    'uncertainty': uncertainty
                }
                
        except Exception as e:
            self.logger.error(f"Failed to calculate trial metrics for trial {trial_id}: {e}")
            return {
                'best_S_Rge2': None,
                'n_docs_seen': 0,
                'n_docs_selected': 0,
                'p_short': None,
                'uncertainty': None
            }
