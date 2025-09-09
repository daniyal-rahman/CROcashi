"""
Database service for PubMed literature processing.

Handles persistence of R/S scores, trial-document relationships, and trial literature state.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ...db.models import Document, DocumentText, DocumentLink, DocRSScore, TrialDocCandidate, TrialLitState, PubMedMeta, DocumentCitation
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
                        existing.decided_at = datetime.now(timezone.utc)
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
                            decided_at=datetime.now(timezone.utc)
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
    
    def store_abstracts(
        self, 
        documents: List[Dict[str, Any]], 
        abstracts_fetched: Dict[str, str]
    ) -> Tuple[int, int]:
        """
        Store abstract text for documents in document_text table.
        
        Args:
            documents: List of document data from Stage U0
            abstracts_fetched: Dictionary mapping PMID to abstract text
            
        Returns:
            Tuple of (successful_inserts, failed_inserts)
        """
        successful = 0
        failed = 0
        
        with session_scope() as session:
            for doc_data in documents:
                try:
                    pmid = doc_data.get('pmid')
                    if not pmid or pmid not in abstracts_fetched:
                        self.logger.warning(f"No abstract text available for PMID {pmid}")
                        failed += 1
                        continue
                    
                    # Look up document by PMID
                    document = session.query(Document).filter(Document.pmid == pmid).first()
                    if not document:
                        self.logger.warning(f"Document with PMID {pmid} not found in database")
                        failed += 1
                        continue
                    
                    abstract_text = abstracts_fetched[pmid].strip()
                    if not abstract_text:
                        self.logger.warning(f"Empty abstract text for PMID {pmid}")
                        failed += 1
                        continue
                    
                    # Check if document_text record already exists
                    doc_text = session.query(DocumentText).filter(
                        DocumentText.doc_id == document.doc_id
                    ).first()
                    
                    if doc_text:
                        # Update existing record
                        doc_text.abstract_text = abstract_text
                        doc_text.char_count_abstract = len(abstract_text)
                        self.logger.debug(f"Updated abstract for document {document.doc_id}")
                    else:
                        # Create new record
                        doc_text = DocumentText(
                            doc_id=document.doc_id,
                            abstract_text=abstract_text,
                            char_count_abstract=len(abstract_text),
                            fulltext_text=None,
                            fulltext_ttl_date=None,
                            char_count_fulltext=None
                        )
                        session.add(doc_text)
                        self.logger.debug(f"Created abstract record for document {document.doc_id}")
                    
                    # Update document status
                    document.status = 'parsed'
                    document.parsed_at = datetime.now(timezone.utc)
                    
                    successful += 1
                    
                except (IntegrityError, SQLAlchemyError) as e:
                    failed += 1
                    self.logger.error(f"Database error storing abstract for PMID {pmid}: {e}")
                    continue
                except Exception as e:
                    failed += 1
                    self.logger.error(f"Unexpected error storing abstract for PMID {pmid}: {e}")
                    continue
        
        self.logger.info(f"Stored abstracts: {successful} successful, {failed} failed")
        return successful, failed
    
    def store_documents_metadata(self, valid_documents: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Store document metadata from U0 stage into documents table.
        
        Args:
            valid_documents: List of valid document metadata from U0 mapping
            
        Returns:
            Tuple of (successful_inserts, failed_inserts)
        """
        successful = 0
        failed = 0
        
        with session_scope() as session:
            for doc_data in valid_documents:
                try:
                    pmid = doc_data.get('pmid')
                    if not pmid:
                        self.logger.warning(f"Document missing PMID: {doc_data}")
                        failed += 1
                        continue
                    
                    # Check if document already exists
                    existing = session.query(Document).filter(Document.pmid == pmid).first()
                    
                    if existing:
                        # Update existing document
                        existing.title = doc_data.get('title', existing.title)
                        existing.publisher = doc_data.get('fulljournalname', existing.publisher)
                        existing.published_at = doc_data.get('published_at', existing.published_at)
                        existing.nct_id = doc_data.get('nct_id', existing.nct_id)
                        existing.status = 'discovered'
                        self.logger.debug(f"Updated document for PMID {pmid}")
                    else:
                        # Create new document
                        document = Document(
                            source_type='Paper',
                            pmid=pmid,
                            title=doc_data.get('title'),
                            publisher=doc_data.get('fulljournalname'),
                            published_at=doc_data.get('published_at'),
                            nct_id=doc_data.get('nct_id'),
                            content_type='abstract',  # Will be updated to 'fulltext' in OA stage
                            status='discovered',
                            discovered_at=datetime.now(timezone.utc)
                        )
                        session.add(document)
                        session.flush()  # Get the doc_id
                        
                        # Create empty document_text record
                        doc_text = DocumentText(
                            doc_id=document.doc_id,
                            abstract_text=None,
                            fulltext_text=None,
                            char_count_abstract=None,
                            char_count_fulltext=None
                        )
                        session.add(doc_text)
                        
                        # Store citation data if available
                        if 'citation' in doc_data:
                            citation_data = doc_data['citation']
                            citation = DocumentCitation(
                                doc_id=document.doc_id,
                                doi=citation_data.get('doi'),
                                pmid=pmid,
                                pmcid=citation_data.get('pmcid'),
                                nct_id=citation_data.get('nct_id'),
                                journal=citation_data.get('journal'),
                                volume=citation_data.get('volume'),
                                issue=citation_data.get('issue'),
                                pages=citation_data.get('pages'),
                                article_type=citation_data.get('article_type'),
                                pub_year=citation_data.get('pub_year'),
                                mesh_jsonb=citation_data.get('mesh_jsonb', []),
                                substances_jsonb=citation_data.get('substances_jsonb', [])
                            )
                            session.add(citation)
                            self.logger.debug(f"Created citation for PMID {pmid}")
                        
                        self.logger.debug(f"Created document for PMID {pmid} with doc_id {document.doc_id}")
                    
                    successful += 1
                    
                except (IntegrityError, SQLAlchemyError) as e:
                    failed += 1
                    self.logger.error(f"Database error storing document metadata for PMID {pmid}: {e}")
                    continue
                except Exception as e:
                    failed += 1
                    self.logger.error(f"Unexpected error storing document metadata for PMID {pmid}: {e}")
                    continue
        
        self.logger.info(f"Stored document metadata: {successful} successful, {failed} failed")
        return successful, failed
    
    def store_document_links(self, trial_id: int, docs_with_links: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Store document-trial links from U1 stage into document_links table.
        
        Args:
            trial_id: Trial ID (integer)
            docs_with_links: List of documents with their link information
            
        Returns:
            Tuple of (successful_inserts, failed_inserts)
        """
        successful = 0
        failed = 0
        
        with session_scope() as session:
            # Get trial information to extract company_id
            from ...db.models import Trial
            trial = session.query(Trial).filter(Trial.trial_id == trial_id).first()
            if not trial:
                self.logger.error(f"Trial {trial_id} not found")
                return 0, len(docs_with_links)
            
            company_id = trial.sponsor_company_id
            for doc_data in docs_with_links:
                try:
                    pmid = doc_data.get('pmid')
                    if not pmid:
                        self.logger.warning(f"Document missing PMID: {doc_data}")
                        failed += 1
                        continue
                    
                    # Look up document by PMID
                    document = session.query(Document).filter(Document.pmid == pmid).first()
                    if not document:
                        self.logger.warning(f"Document with PMID {pmid} not found in database")
                        failed += 1
                        continue
                    
                    # Get links from document data
                    document_links = doc_data.get('document_links', [])
                    if not document_links:
                        self.logger.debug(f"No links found for document PMID {pmid}")
                        continue
                    
                    # Store each link
                    for link_data in document_links:
                        try:
                            # Check if link already exists
                            existing = session.query(DocumentLink).filter(
                                DocumentLink.doc_id == document.doc_id,
                                DocumentLink.trial_id == trial_id,
                                DocumentLink.nct_id == link_data.get('nct_id')
                            ).first()
                            
                            if existing:
                                # Update existing link
                                existing.confidence = Decimal(str(link_data.get('confidence', 0.5)))
                                existing.heuristics = link_data.get('heuristics')
                                existing.evidence_json = link_data.get('evidence_json')
                                existing.link_type = link_data.get('link_type', 'heuristic')
                                existing.company_id = company_id  # Update company_id
                                self.logger.debug(f"Updated document link for doc {document.doc_id}, trial {trial_id}")
                            else:
                                # Create new link
                                doc_link = DocumentLink(
                                    doc_id=document.doc_id,
                                    trial_id=trial_id,
                                    nct_id=link_data.get('nct_id'),
                                    asset_id=None,  # No asset_id for basic science papers
                                    company_id=company_id,
                                    confidence=Decimal(str(link_data.get('confidence', 0.5))),
                                    heuristics=link_data.get('heuristics'),
                                    evidence_json=link_data.get('evidence_json'),
                                    link_type=link_data.get('link_type', 'heuristic')
                                )
                                session.add(doc_link)
                                self.logger.debug(f"Created document link for doc {document.doc_id}, trial {trial_id}")
                        
                        except Exception as e:
                            self.logger.error(f"Error storing link for doc {document.doc_id}: {e}")
                            continue
                    
                    successful += 1
                    
                except (IntegrityError, SQLAlchemyError) as e:
                    failed += 1
                    self.logger.error(f"Database error storing document links for PMID {pmid}: {e}")
                    continue
                except Exception as e:
                    failed += 1
                    self.logger.error(f"Unexpected error storing document links for PMID {pmid}: {e}")
                    continue
        
        self.logger.info(f"Stored document links: {successful} successful, {failed} failed")
        return successful, failed
    
    def store_fulltext(self, doc_id: int, full_text: str, ttl_date: Optional[datetime] = None) -> bool:
        """
        Store full text content for a document.
        
        Args:
            doc_id: Document ID
            full_text: Full text content
            ttl_date: Optional TTL date for the full text
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                # Update document_text record
                doc_text = session.query(DocumentText).filter(
                    DocumentText.doc_id == doc_id
                ).first()
                
                if doc_text:
                    doc_text.fulltext_text = full_text
                    doc_text.char_count_fulltext = len(full_text)
                    doc_text.fulltext_ttl_date = ttl_date
                else:
                    # Create new document_text record if it doesn't exist
                    doc_text = DocumentText(
                        doc_id=doc_id,
                        fulltext_text=full_text,
                        char_count_fulltext=len(full_text),
                        fulltext_ttl_date=ttl_date,
                        abstract_text=None,
                        char_count_abstract=None
                    )
                    session.add(doc_text)
                
                # Update document status and timestamps
                document = session.query(Document).filter(Document.doc_id == doc_id).first()
                if document:
                    document.content_type = 'fulltext'
                    document.parsed_at = datetime.now(timezone.utc)
                    document.linked_at = datetime.now(timezone.utc)
                
                self.logger.debug(f"Stored full text for document {doc_id} ({len(full_text)} chars)")
                return True
                
        except (IntegrityError, SQLAlchemyError) as e:
            self.logger.error(f"Database error storing full text for doc {doc_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error storing full text for doc {doc_id}: {e}")
            return False
    
    def get_selected_candidate_pmids(self, trial_id: int, stage: str = 'U1_abstract') -> List[str]:
        """
        Get PMIDs of selected candidate documents for a trial.
        
        Args:
            trial_id: Trial ID
            stage: Stage filter (default: 'U1_abstract')
            
        Returns:
            List of PMIDs for selected candidates
        """
        try:
            with session_scope() as session:
                # Query selected candidates with their PMIDs
                candidates = session.query(TrialDocCandidate, Document.pmid).join(
                    Document, TrialDocCandidate.doc_id == Document.doc_id
                ).filter(
                    TrialDocCandidate.trial_id == trial_id,
                    TrialDocCandidate.stage == stage,
                    TrialDocCandidate.selected == True
                ).all()
                
                pmids = [pmid for candidate, pmid in candidates if pmid]
                self.logger.debug(f"Found {len(pmids)} selected candidate PMIDs for trial {trial_id}")
                return pmids
                
        except Exception as e:
            self.logger.error(f"Failed to get selected candidate PMIDs for trial {trial_id}: {e}")
            return []
    
    def upsert_documents_metadata(
        self, 
        trial_id: int, 
        mapped_docs: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Upsert document metadata and PubMed metadata for U1+ discovery stage.
        
        Args:
            trial_id: Trial ID
            mapped_docs: List of mapped document data from PubMedMapper
            
        Returns:
            Tuple of (successful_inserts, failed_inserts)
        """
        successful = 0
        failed = 0
        
        with session_scope() as session:
            for doc_data in mapped_docs:
                try:
                    pmid = doc_data.get('pmid')
                    if not pmid:
                        self.logger.warning(f"Document missing PMID: {doc_data}")
                        failed += 1
                        continue
                    
                    # Check if document already exists
                    existing_doc = session.query(Document).filter(Document.pmid == pmid).first()
                    
                    if existing_doc:
                        # Update existing document
                        existing_doc.title = doc_data.get('title', existing_doc.title)
                        existing_doc.publisher = doc_data.get('publisher', existing_doc.publisher)
                        existing_doc.published_at = doc_data.get('published_at', existing_doc.published_at)
                        existing_doc.nct_id = doc_data.get('nct_id', existing_doc.nct_id)
                        existing_doc.status = 'discovered'
                        existing_doc.discovered_at = datetime.now(timezone.utc)
                        doc_id = existing_doc.doc_id
                        self.logger.debug(f"Updated document for PMID {pmid}")
                    else:
                        # Create new document
                        document = Document(
                            source_type='Paper',
                            pmid=pmid,
                            title=doc_data.get('title'),
                            publisher=doc_data.get('publisher'),
                            published_at=doc_data.get('published_at'),
                            nct_id=doc_data.get('nct_id'),
                            content_type='abstract',
                            status='discovered',
                            discovered_at=datetime.now(timezone.utc)
                        )
                        session.add(document)
                        session.flush()  # Get the doc_id
                        doc_id = document.doc_id
                        
                        # Create empty document_text record
                        doc_text = DocumentText(
                            doc_id=doc_id,
                            abstract_text=None,
                            fulltext_text=None,
                            char_count_abstract=None,
                            char_count_fulltext=None
                        )
                        session.add(doc_text)
                        self.logger.debug(f"Created document for PMID {pmid} with doc_id {doc_id}")
                    
                    # Handle PubMed metadata
                    pubmed_meta_data = doc_data.get('pubmed_meta')
                    if pubmed_meta_data:
                        # Check if PubMed metadata already exists
                        existing_meta = session.query(PubMedMeta).filter(
                            PubMedMeta.doc_id == doc_id
                        ).first()
                        
                        if existing_meta:
                            # Update existing PubMed metadata
                            existing_meta.pmid = pmid
                            existing_meta.language = pubmed_meta_data.get('language')
                            existing_meta.authors_jsonb = pubmed_meta_data.get('authors_jsonb')
                            existing_meta.affiliations_jsonb = pubmed_meta_data.get('affiliations_jsonb')
                            existing_meta.esummary_jsonb = pubmed_meta_data.get('esummary_jsonb')
                            existing_meta.efetch_header_jsonb = pubmed_meta_data.get('efetch_header_jsonb')
                            self.logger.debug(f"Updated PubMed metadata for doc_id {doc_id}")
                        else:
                            # Create new PubMed metadata
                            pubmed_meta = PubMedMeta(
                                doc_id=doc_id,
                                pmid=pmid,
                                language=pubmed_meta_data.get('language'),
                                authors_jsonb=pubmed_meta_data.get('authors_jsonb'),
                                affiliations_jsonb=pubmed_meta_data.get('affiliations_jsonb'),
                                esummary_jsonb=pubmed_meta_data.get('esummary_jsonb'),
                                efetch_header_jsonb=pubmed_meta_data.get('efetch_header_jsonb')
                            )
                            session.add(pubmed_meta)
                            self.logger.debug(f"Created PubMed metadata for doc_id {doc_id}")
                    
                    # Handle citation data
                    citation_data = doc_data.get('citation')
                    if citation_data:
                        # Check if citation already exists
                        existing_citation = session.query(DocumentCitation).filter(
                            DocumentCitation.doc_id == doc_id
                        ).first()
                        
                        if existing_citation:
                            # Update existing citation
                            existing_citation.doi = citation_data.get('doi')
                            existing_citation.pmcid = citation_data.get('pmcid')
                            existing_citation.nct_id = citation_data.get('nct_id')
                            existing_citation.journal = citation_data.get('journal')
                            existing_citation.volume = citation_data.get('volume')
                            existing_citation.issue = citation_data.get('issue')
                            existing_citation.pages = citation_data.get('pages')
                            existing_citation.article_type = citation_data.get('article_type')
                            existing_citation.pub_year = citation_data.get('pub_year')
                            existing_citation.mesh_jsonb = citation_data.get('mesh_jsonb', [])
                            existing_citation.substances_jsonb = citation_data.get('substances_jsonb', [])
                            self.logger.debug(f"Updated citation for doc_id {doc_id}")
                        else:
                            # Create new citation
                            citation = DocumentCitation(
                                doc_id=doc_id,
                                doi=citation_data.get('doi'),
                                pmid=pmid,
                                pmcid=citation_data.get('pmcid'),
                                nct_id=citation_data.get('nct_id'),
                                journal=citation_data.get('journal'),
                                volume=citation_data.get('volume'),
                                issue=citation_data.get('issue'),
                                pages=citation_data.get('pages'),
                                article_type=citation_data.get('article_type'),
                                pub_year=citation_data.get('pub_year'),
                                mesh_jsonb=citation_data.get('mesh_jsonb', []),
                                substances_jsonb=citation_data.get('substances_jsonb', [])
                            )
                            session.add(citation)
                            self.logger.debug(f"Created citation for doc_id {doc_id}")
                    
                    successful += 1
                    
                except (IntegrityError, SQLAlchemyError) as e:
                    failed += 1
                    self.logger.error(f"Database error upserting document metadata for PMID {pmid}: {e}")
                    continue
                except Exception as e:
                    failed += 1
                    self.logger.error(f"Unexpected error upserting document metadata for PMID {pmid}: {e}")
                    continue
        
        self.logger.info(f"Upserted document metadata: {successful} successful, {failed} failed")
        return successful, failed
    
    def store_trial_doc_candidates_discovery(
        self, 
        trial_id: int, 
        candidates: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Store trial-document candidates for discovery stage (U1_discovery).
        
        Args:
            trial_id: Trial ID
            candidates: List of candidate records from discovery
            
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
                        existing.selected = candidate.get('selected', True)
                        existing.dropped_reason = candidate.get('dropped_reason')
                        existing.notes = candidate.get('notes')
                        self.logger.debug(f"Updated trial-doc candidate for trial {trial_id}, doc {doc_id}")
                    else:
                        # Create new record
                        trial_doc = TrialDocCandidate(
                            trial_id=trial_id,
                            doc_id=doc_id,
                            stage=candidate['stage'],
                            selected=candidate.get('selected', True),
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
        
        self.logger.info(f"Stored trial-doc candidates (discovery): {successful} successful, {failed} failed")
        return successful, failed
