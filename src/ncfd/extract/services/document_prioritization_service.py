"""
Document Prioritization Service for Study Card Pipeline.

Handles document scoring, prioritization, and selection for LLM processing.
This service extracts the document prioritization logic from the main pipeline.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

from ncfd.ingest.pubmed.document_manager import DocumentManager
from ncfd.ingest.pubmed.retrieval.pre_llm_guardrails import PreLLMGuardrailsSystem, PreLLMGuardrailsConfig
from ncfd.db.session import session_scope
from ncfd.db.models import Document
from .document_prioritization_helpers import DocumentPrioritizationHelpers

logger = logging.getLogger(__name__)


@dataclass
class DocumentPriorityResult:
    """Result of document prioritization."""
    prioritized_documents: List[Dict[str, Any]]
    raw_doc_texts: Dict[str, str]
    total_documents: int
    selected_documents: int
    prioritization_scores: Dict[str, float]
    selection_reason: str
    processing_stats: Dict[str, Any]


class DocumentPrioritizationService:
    """
    Service for prioritizing and selecting documents for LLM processing.
    
    This service handles:
    - Document scoring based on R/S scores and other factors
    - Document prioritization and ranking
    - Selection of documents for LLM processing
    - Rate limiting and filtering
    - Pre-LLM guardrails filtering
    - Raw text management and prioritization
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the document prioritization service.
        
        Args:
            config: Configuration dictionary with prioritization settings
        """
        self.config = config
        self.prioritization_config = config.get('prioritization', {})
        
        # Initialize document manager
        self.document_manager = DocumentManager()
        
        # Initialize pre-LLM guardrails
        guardrails_config = PreLLMGuardrailsConfig(
            reject_off_topic=config.get('guardrails', {}).get('reject_off_topic', True),
            reject_high_risk=config.get('guardrails', {}).get('reject_high_risk', True),
            high_risk_threshold=config.get('guardrails', {}).get('high_risk_threshold', 0.6),
            require_relevance=config.get('guardrails', {}).get('require_relevance', True),
            log_decisions=config.get('guardrails', {}).get('log_decisions', True),
            log_rejections=config.get('guardrails', {}).get('log_rejections', True)
        )
        self.pre_llm_guardrails = PreLLMGuardrailsSystem(guardrails_config)
        
        # Configuration values
        self.max_documents_per_trial = self.prioritization_config.get('max_documents_per_trial', 20)
        self.min_r_score = self.prioritization_config.get('min_r_score', 0.0)
        self.min_s_score = self.prioritization_config.get('min_s_score', 0.0)
        self.high_priority_r_threshold = self.prioritization_config.get('high_priority_r_threshold', 0.6)
        self.prioritization_weights = self.prioritization_config.get('weights', {
            'r_score': 0.4,
            's_score': 0.3,
            'recency': 0.2,
            'relevance': 0.1
        })
    
    async def prioritize_documents(
        self, 
        documents: List[Any], 
        raw_doc_texts: Dict[str, str],
        trial_id: str,
        trial_context: Dict[str, Any],
        entity_pack: Optional[Any] = None
    ) -> DocumentPriorityResult:
        """
        Apply document prioritization and rate limiting to retrieved documents.
        
        Args:
            documents: List of DocumentCard objects from retrieval
            raw_doc_texts: Dictionary of raw document texts
            trial_id: Trial ID for context
            trial_context: Trial context information
            entity_pack: Entity pack for relevance scoring
            
        Returns:
            DocumentPriorityResult with prioritized documents
        """
        logger.info(f"Applying document prioritization for trial {trial_id}")
        
        try:
            # Service only works with DocumentCard objects from retrieval - no fallback to database
            if not documents:
                logger.warning(f"No documents provided for trial {trial_id} - service requires DocumentCard objects from retrieval")
                return DocumentPriorityResult(
                    prioritized_documents=[],
                    raw_doc_texts={},
                    total_documents=0,
                    selected_documents=0,
                    prioritization_scores={},
                    selection_reason='No documents provided from retrieval',
                    processing_stats={'total_documents': 0, 'total_candidates': 0, 'selected_documents': 0, 'priority_counts': {}, 'text_availability': {}, 'rs_score_stats': {}, 'rate_limit_applied': False}
                )
            
            logger.info(f"Processing {len(documents)} documents from retrieval")
            
            # Get document data from database for R/S scores
            trial_documents = self.document_manager.get_trial_documents(trial_id)
            
            # Debug logging for trial documents
            logger.info(f"🔍 DEBUG: Retrieved {len(trial_documents)} documents for trial {trial_id}")
            for i, doc in enumerate(trial_documents[:5]):  # Show first 5
                logger.info(f"  Doc {i+1}: doc_id={doc.get('doc_id')}, pmcid={doc.get('pmcid')}, title={doc.get('title', '')[:50]}...")
            
            if not trial_documents:
                logger.warning(f"No documents found for trial {trial_id}")
                return DocumentPriorityResult(
                    prioritized_documents=[],
                    raw_doc_texts={},
                    total_documents=0,
                    selected_documents=0,
                    prioritization_scores={},
                    selection_reason="No documents found for trial",
                    processing_stats={
                        "total_documents": 0, 
                        "total_candidates": 0,
                        "selected_documents": 0,
                        "priority_counts": {},
                        "text_availability": {},
                        "rs_score_stats": {},
                        "rate_limit_applied": False
                    }
                )
            
            # Filter to only include documents that were retrieved (have documents)
            doc_ids = [doc_card.doc_id for doc_card in documents]
            trial_docs_by_id = {doc['doc_id']: doc for doc in trial_documents if doc['doc_id'] in doc_ids}
            
            # Create a lookup map for document details
            doc_details = {}
            for doc_id, doc_data in trial_docs_by_id.items():
                # Use string keys for consistent lookup
                doc_details[str(doc_id)] = {
                    'doc_data': doc_data,
                    'has_full_text': False,  # Will be determined from raw_doc_texts
                    'has_abstract': bool(doc_data.get('title') if isinstance(doc_data, dict) else doc_data.title)  # Use title as proxy for abstract
                }
                
            # Convert document cards to processing candidates with prioritization
            candidates = []
            
            for i, doc_card in enumerate(documents):
                doc_info = doc_details.get(str(doc_card.doc_id))
                if not doc_info:
                    logger.warning(f"No database details found for doc_id {doc_card.doc_id}")
                    continue
                
                doc_data = doc_info['doc_data']
                
                # Determine text availability from raw_doc_texts
                doc_id_key = str(doc_card.doc_id)
                raw_text = raw_doc_texts.get(doc_id_key, '')
                has_text = bool(raw_text and raw_text.strip())
                
                # For now, treat any text as both fulltext and abstract since we don't distinguish
                has_full_text = has_text
                has_abstract = has_text
                
                # Get R/S scores from document data
                if isinstance(doc_data, dict):
                    r_score = doc_data.get('r_score', 0.0)
                    s_score = doc_data.get('s_score', 0.0)
                    r_tier = doc_data.get('r_tier', 'R0')
                    s_tier = doc_data.get('s_tier', 'S0')
                else:
                    # DocumentCard object - these don't have R/S scores, use defaults
                    r_score = 0.0
                    s_score = 0.0
                    r_tier = 'R0'
                    s_tier = 'S0'
                
                # Determine priority
                priority = self._determine_document_priority(
                    r_score=r_score,
                    r_tier=r_tier,
                    s_score=s_score,
                    s_tier=s_tier,
                    has_full_text=has_full_text,
                    has_abstract=has_abstract,
                    doc=None  # We don't need the full document object
                )
                
                # Calculate processing score
                processing_score = DocumentPrioritizationHelpers.calculate_processing_score(
                    r_score=r_score,
                    s_score=s_score,
                    has_full_text=has_full_text,
                    has_abstract=has_abstract,
                    full_text_length=len(raw_text),
                    abstract_length=len(raw_text)
                )
                
                candidate = {
                    'doc_id': doc_card.doc_id,
                    'priority': priority,
                    'processing_score': processing_score,
                    'r_score': r_score,
                    's_score': s_score,
                    'r_tier': r_tier,
                    's_tier': s_tier,
                    'has_full_text': has_full_text,
                    'has_abstract': has_abstract,
                    'title': doc_data.get('title', 'No title') if isinstance(doc_data, dict) else (doc_data.title or 'No title'),
                    'pmid': doc_data.get('pmid') if isinstance(doc_data, dict) else doc_data.pmid,
                    'pmcid': doc_data.get('pmcid') if isinstance(doc_data, dict) else doc_data.pmcid,
                    'retrieval_tier': doc_data.get('retrieval_tier', 'A') if isinstance(doc_data, dict) else 'A'
                }
                
                candidates.append(candidate)
            
            # Sort candidates by priority and processing score
            sorted_candidates = DocumentPrioritizationHelpers.sort_document_candidates(candidates)
            
            # Debug logging for candidates
            logger.info(f"🔍 DEBUG: Created {len(candidates)} candidates")
            for i, candidate in enumerate(candidates[:5]):  # Show first 5
                logger.info(f"  Candidate {i+1}: doc_id={candidate.get('doc_id')}, pmcid={candidate.get('pmcid')}, r_score={candidate.get('r_score')}, title={candidate.get('title', '')[:50]}...")
            
            # Apply rate limiting using pure R/S score ranking
            selected_candidates = DocumentPrioritizationHelpers.apply_document_rate_limits(
                sorted_candidates, 
                self.max_documents_per_trial, 
                self.high_priority_r_threshold
            )
            
            # Generate processing statistics
            stats = DocumentPrioritizationHelpers.generate_document_processing_stats(trial_documents, candidates, selected_candidates)
            
            # Log detailed R/S score rankings and expected Cassava papers
            self._log_document_rankings(selected_candidates, candidates)
            
            # Apply Pre-LLM guardrails filtering
            logger.info(f"🔒 Applying Pre-LLM guardrails filtering to {len(selected_candidates)} candidates")
            guardrails_filtered_candidates = await self._apply_pre_llm_guardrails(
                selected_candidates, trial_context, entity_pack
            )
            logger.info(f"✅ Guardrails filtering complete: {len(guardrails_filtered_candidates)} documents passed guardrails")
            
            # Convert selected candidates back to document cards and raw texts
            prioritized_doc_cards = []
            prioritized_raw_texts = {}
            
            for candidate in guardrails_filtered_candidates:
                # Find matching document card from original retrieval
                matching_doc_card = None
                for doc_card in documents:
                    if doc_card.doc_id == candidate['doc_id']:
                        matching_doc_card = doc_card
                        break
                
                if matching_doc_card:
                    prioritized_doc_cards.append(matching_doc_card)
                    # Ensure consistent key type for raw_doc_texts lookup
                    doc_id_key = str(candidate['doc_id'])
                    
                    # Always prioritize EnhancedRetriever's raw text first (it has the full retrieved text)
                    if doc_id_key in raw_doc_texts and raw_doc_texts[doc_id_key]:
                        prioritized_raw_texts[doc_id_key] = raw_doc_texts[doc_id_key]
                    else:
                        prioritized_raw_texts[doc_id_key] = ""
                        logger.warning(f"No text available for doc_id {candidate['doc_id']} (key={doc_id_key})")
            
            logger.info(f"Document prioritization applied: {len(prioritized_doc_cards)} documents selected from {len(candidates)} candidates")
            
            # Mark selected documents as 'selected' for processing
            await DocumentPrioritizationHelpers.mark_documents_as_selected(prioritized_doc_cards)
            
            # Extract scores for reporting
            prioritization_scores = {
                candidate['doc_id']: candidate.get('processing_score', 0.0) 
                for candidate in selected_candidates
            }
            
            selection_reason = f"Selected {len(prioritized_doc_cards)} documents from {len(candidates)} candidates using R/S score ranking"
            
            return DocumentPriorityResult(
                prioritized_documents=guardrails_filtered_candidates,  # Return candidate dictionaries with R/S scores
                raw_doc_texts=prioritized_raw_texts,
                total_documents=len(trial_documents),
                selected_documents=len(guardrails_filtered_candidates),
                prioritization_scores=prioritization_scores,
                selection_reason=selection_reason,
                processing_stats=stats
            )
                
        except Exception as e:
            logger.error(f"Error applying document prioritization for trial {trial_id}: {e}")
            logger.warning("Falling back to simple sort by R/S score")
            
            # Fallback: simple sort by R/S score and limit to top documents
            try:
                fallback_docs = sorted(
                    documents, 
                    key=lambda x: getattr(x, 'r_score', 0.0) + getattr(x, 's_score', 0.0), 
                    reverse=True
                )[:self.max_documents_per_trial]
                
                fallback_texts = {str(card.doc_id): raw_doc_texts.get(str(card.doc_id), "") for card in fallback_docs}
                
                return DocumentPriorityResult(
                    prioritized_documents=fallback_docs,
                    raw_doc_texts=fallback_texts,
                    total_documents=len(documents),
                    selected_documents=len(fallback_docs),
                    prioritization_scores={},
                    selection_reason=f"Fallback: selected {len(fallback_docs)} documents",
                    processing_stats={"error": str(e), "fallback_used": True}
                )
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                return DocumentPriorityResult(
                    prioritized_documents=[],
                    raw_doc_texts={},
                    total_documents=len(documents),
                    selected_documents=0,
                    prioritization_scores={},
                    selection_reason="Failed to prioritize documents",
                    processing_stats={"error": str(e), "fallback_failed": True}
                )
    
    def _determine_document_priority(self, r_score, r_tier, s_score, s_tier, has_full_text, has_abstract, doc=None):
        """Determine document priority based on R/S scores, text availability, and document characteristics."""
        
        # Convert tiers to scores if scores are missing
        if r_score is None and r_tier:
            r_score = DocumentPrioritizationHelpers.tier_to_score(r_tier)
        if s_score is None and s_tier:
            s_score = DocumentPrioritizationHelpers.tier_to_score(s_tier)
        
        # Convert to float to avoid Decimal + float errors
        r_score = float(r_score) if r_score is not None else 0.0
        s_score = float(s_score) if s_score is not None else 0.0
        
        # Boost priority for documents with PMCID (proxy for full text availability)
        pmcid_boost = 0.0
        if doc and hasattr(doc, 'pmcid') and doc.pmcid:
            pmcid_boost = 0.2
        
        # Boost priority for clinical trial publications
        clinical_trial_boost = 0.0
        if doc and hasattr(doc, 'publication_type') and doc.publication_type:
            pub_type = doc.publication_type.lower()
            if any(term in pub_type for term in ['clinical trial', 'randomized controlled trial', 'controlled clinical trial']):
                clinical_trial_boost = 0.3
        
        # Boost priority for documents with NCT IDs
        nct_boost = 0.0
        if doc and hasattr(doc, 'title') and doc.title:
            title = doc.title.lower()
            if 'nct' in title or 'clinicaltrials.gov' in title:
                nct_boost = 0.2
        
        # Apply boosts
        effective_r_score = r_score + pmcid_boost + clinical_trial_boost + nct_boost
        effective_s_score = s_score + pmcid_boost + clinical_trial_boost + nct_boost
        
        # HIGH priority: Strong R/S scores OR PMCID presence OR clinical trial
        if (effective_r_score >= 0.6 or effective_s_score >= 0.6) and (has_full_text or has_abstract):
            return "HIGH"
        
        # MEDIUM priority: Moderate R/S scores OR PMCID presence
        if (effective_r_score >= 0.3 or effective_s_score >= 0.3) and (has_full_text or has_abstract):
            return "MEDIUM"
        
        # LOW priority: Any R/S score with text
        if (effective_r_score >= 0.1 or effective_s_score >= 0.1) and (has_full_text or has_abstract):
            return "LOW"
        
        # FALLBACK: Any R/S score with abstract only
        if (effective_r_score >= 0.1 or effective_s_score >= 0.1) and has_abstract and not has_full_text:
            return "FALLBACK"
        
        # Default to low priority
        return "LOW"
    
    async def _apply_pre_llm_guardrails(
        self, 
        candidates: List[Dict[str, Any]], 
        trial_context: Dict[str, Any],
        entity_pack: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """Apply Pre-LLM guardrails filtering to candidates."""
        filtered_candidates = []
        guardrails_rejections = []
        
        for candidate in candidates:
            try:
                # Get document from database for guardrails check
                with session_scope() as session:
                    document = session.query(Document).filter(Document.doc_id == candidate['doc_id']).first()
                    if not document:
                        logger.warning(f"Document {candidate['doc_id']} not found in database, skipping guardrails")
                        filtered_candidates.append(candidate)
                        continue
                    
                    # Apply guardrails check
                    guardrails_result = self.pre_llm_guardrails.should_process_document(document, entity_pack)
                    
                    if guardrails_result.should_process:
                        logger.debug(f"✅ Document {candidate['doc_id']} passed guardrails (risk: {guardrails_result.risk_score:.2f})")
                        filtered_candidates.append(candidate)
                    else:
                        logger.warning(f"❌ Document {candidate['doc_id']} rejected by guardrails: {guardrails_result.reason}")
                        guardrails_rejections.append({
                            'doc_id': candidate['doc_id'],
                            'title': document.title,
                            'reason': guardrails_result.reason,
                            'risk_score': guardrails_result.risk_score
                        })
                        
            except Exception as e:
                logger.error(f"Error applying guardrails to document {candidate['doc_id']}: {e}")
                # On error, include the document to avoid losing it
                filtered_candidates.append(candidate)
        
        logger.info(f"Pre-LLM guardrails filtering: {len(filtered_candidates)} documents passed, {len(guardrails_rejections)} rejected")
        
        # Log rejection details
        for rejection in guardrails_rejections:
            logger.info(f"Rejected document {rejection['doc_id']}: {rejection['reason']} (risk: {rejection['risk_score']:.2f})")
        
        return filtered_candidates
    
    def _log_document_rankings(self, selected_docs: List[Dict[str, Any]], all_candidates: List[Dict[str, Any]]):
        """
        Log R ranking for each selected document showing its position out of total documents found.
        Specifically track the 3 expected Cassava papers that should show warnings if not found.
        
        Args:
            selected_docs: Documents that were selected for processing (can be empty)
            all_candidates: All candidate documents that were considered
        """
        if not all_candidates:
            return
        
        # Expected Cassava papers that should show warnings if not found
        expected_cassava_papers = {
            "PMC10531384": "Simufilam Reverses Aberrant Receptor Interactions (2023)",
            "PMC10339288": "Simufilam suppresses overactive mTOR and restores its (2023)",
            "PTI-125": "PTI-125 Reduces Biomarkers of Alzheimer's Disease in Patients (2020)"
        }
        
        # Create a mapping of doc_id to R score for all candidates
        candidate_r_scores = {}
        candidate_metadata = {}
        for candidate in all_candidates:
            if candidate.get('r_score') is not None:
                candidate_r_scores[candidate['doc_id']] = float(candidate['r_score'])
                # Store metadata for identification
                candidate_metadata[candidate['doc_id']] = {
                    'pmcid': candidate.get('pmcid'),
                    'title': candidate.get('title', ''),
                    'pmid': candidate.get('pmid'),
                    'has_full_text': candidate.get('has_full_text', False),
                    'has_abstract': candidate.get('has_abstract', False)
                }
        
        # Sort all candidates by R score (descending) to determine rankings
        sorted_candidates = sorted(
            candidate_r_scores.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        # Create ranking lookup
        r_rankings = {}
        for rank, (doc_id, r_score) in enumerate(sorted_candidates, 1):
            r_rankings[doc_id] = rank
        
        total_docs_with_r_scores = len(sorted_candidates)
        
        # Check for expected Cassava papers in all candidates (not just selected)
        logger.info("🔍 CASSAVA EXPECTED PAPERS R RANKING:")
        found_expected_papers = []
        
        for doc_id, metadata in candidate_metadata.items():
            pmcid = metadata.get('pmcid')
            title = metadata.get('title', '').lower()
            
            # Check if this is one of the expected papers
            is_expected = False
            paper_name = None
            
            if pmcid in expected_cassava_papers:
                is_expected = True
                paper_name = expected_cassava_papers[pmcid]
            elif "pti-125" in title and "biomarkers" in title and "alzheimer" in title:
                is_expected = True
                paper_name = expected_cassava_papers["PTI-125"]
            
            if is_expected:
                r_score = candidate_r_scores.get(doc_id, 0.0)
                r_rank = r_rankings.get(doc_id, "N/A")
                has_full_text = metadata.get('has_full_text', False)
                has_abstract = metadata.get('has_abstract', False)
                text_status = "Full Text" if has_full_text else ("Abstract Only" if has_abstract else "No Text")
                found_expected_papers.append((doc_id, paper_name, r_score, r_rank))
                logger.info(f"  ✅ {paper_name}")
                logger.info(f"     Doc {doc_id}: R={r_score:.3f} (Rank {r_rank}/{total_docs_with_r_scores}) - {text_status}")
        
        # Check for missing expected papers
        missing_papers = []
        found_pmcids = {metadata.get('pmcid') for _, metadata in candidate_metadata.items()}
        found_titles = {metadata.get('title', '').lower() for _, metadata in candidate_metadata.items()}
        
        for paper_id, paper_name in expected_cassava_papers.items():
            found = False
            
            # Check by PMCID
            if paper_id in found_pmcids:
                found = True
            # Check by title for PTI-125 (which doesn't have PMCID)
            elif paper_id == "PTI-125" and any("pti-125" in title and "biomarkers" in title and "alzheimer" in title for title in found_titles):
                found = True
                
            if not found:
                missing_papers.append(paper_name)
        
        if missing_papers:
            logger.warning("  ❌ MISSING EXPECTED PAPERS:")
            for paper_name in missing_papers:
                logger.warning(f"     {paper_name}")
        
        # Log selected documents or all candidates if none selected
        if selected_docs:
            logger.info("📊 TOP 5 SELECTED DOCUMENTS R RANKING:")
            for i, doc in enumerate(selected_docs[:5], 1):
                doc_id = doc['doc_id']
                r_score = doc.get('r_score')
                has_full_text = doc.get('has_full_text', False)
                has_abstract = doc.get('has_abstract', False)
                text_status = "Full Text" if has_full_text else ("Abstract Only" if has_abstract else "No Text")
                
                if r_score is not None:
                    r_rank = r_rankings.get(doc_id, "N/A")
                    r_score_float = float(r_score)
                    logger.info(f"  {i:2d}. Doc {doc_id}: R={r_score_float:.3f} (Rank {r_rank}/{total_docs_with_r_scores}) - {text_status}")
                else:
                    logger.info(f"  {i:2d}. Doc {doc_id}: R=N/A (No R score) - {text_status}")
        else:
            logger.info("📊 ALL CANDIDATE DOCUMENTS R RANKING (None Selected):")
            for i, (doc_id, r_score) in enumerate(sorted_candidates[:10], 1):  # Show top 10
                r_rank = r_rankings.get(doc_id, "N/A")
                metadata = candidate_metadata.get(doc_id, {})
                has_full_text = metadata.get('has_full_text', False)
                has_abstract = metadata.get('has_abstract', False)
                text_status = "Full Text" if has_full_text else ("Abstract Only" if has_abstract else "No Text")
                logger.info(f"  {i:2d}. Doc {doc_id}: R={r_score:.3f} (Rank {r_rank}/{total_docs_with_r_scores}) - {text_status}")
        
        # Log text availability summary
        full_text_count = sum(1 for doc in all_candidates if doc.get('has_full_text', False))
        abstract_only_count = sum(1 for doc in all_candidates if doc.get('has_abstract', False) and not doc.get('has_full_text', False))
        no_text_count = len(all_candidates) - full_text_count - abstract_only_count
        
        logger.info(f"📄 TEXT AVAILABILITY SUMMARY:")
        logger.info(f"  Full Text: {full_text_count} documents")
        logger.info(f"  Abstract Only: {abstract_only_count} documents")
        logger.info(f"  No Text: {no_text_count} documents")
    
