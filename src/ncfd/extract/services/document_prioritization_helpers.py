"""
Helper methods for Document Prioritization Service.

This module contains the complex helper methods extracted from the original pipeline.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from ncfd.db.session import session_scope
from ncfd.db.models import Document

logger = logging.getLogger(__name__)


class DocumentPrioritizationHelpers:
    """Helper methods for document prioritization logic."""
    
    @staticmethod
    def tier_to_score(tier):
        """Convert R/S tier to approximate score."""
        tier_mapping = {
            'R0': 0.0, 'R1': 0.4, 'R2': 0.6, 'R3': 0.8,
            'S0': 0.0, 'S1': 0.4, 'S2': 0.6, 'S3': 0.8
        }
        return tier_mapping.get(tier, 0.0)
    
    @staticmethod
    def calculate_processing_score(r_score, s_score, has_full_text, has_abstract, full_text_length, abstract_length):
        """Calculate overall processing score for document prioritization."""
        
        # Base score from R/S scores
        r_score = float(r_score) if r_score else 0.0
        s_score = float(s_score) if s_score else 0.0
        base_score = (r_score + s_score) / 2.0
        
        # Text availability bonus
        text_bonus = 0.0
        if has_full_text:
            text_bonus += 0.3
            # Bonus for longer full text
            if full_text_length and full_text_length > 1000:
                text_bonus += min(0.2, full_text_length / 10000.0)  # Cap at 0.2
        elif has_abstract:
            text_bonus += 0.1
            # Bonus for longer abstract
            if abstract_length and abstract_length > 200:
                text_bonus += min(0.1, abstract_length / 2000.0)  # Cap at 0.1
        
        # Combine base score and text bonus
        processing_score = base_score + text_bonus
        
        return min(1.0, processing_score)  # Cap at 1.0
    
    @staticmethod
    def sort_document_candidates(candidates):
        """Sort candidates by priority and processing score."""
        
        def sort_key(candidate):
            # Primary sort: priority (HIGH=1, MEDIUM=2, LOW=3, FALLBACK=4)
            priority_order = {"HIGH": 1, "MEDIUM": 2, "LOW": 3, "FALLBACK": 4}
            priority_value = priority_order.get(candidate['priority'], 5)
            
            # Secondary sort: processing score (higher = better)
            processing_score = float(candidate['processing_score']) if candidate['processing_score'] is not None else 0.0
            
            # Tertiary sort: R score (higher = better)
            r_score = float(candidate['r_score']) if candidate['r_score'] is not None else 0.0
            
            # Final sort: S score (higher = better)
            s_score = float(candidate['s_score']) if candidate['s_score'] is not None else 0.0
            
            return (priority_value, -processing_score, -r_score, -s_score)
        
        return sorted(candidates, key=sort_key)
    
    @staticmethod
    def apply_document_rate_limits(candidates, max_documents_per_trial=20, high_priority_r_threshold=0.6):
        """
        Apply rate limiting using pure R/S score ranking instead of priority buckets.
        
        Handles documents without R/S scores (None values) which occur when:
        - Documents were pulled at runtime but have no text for R/S scoring
        - R/S scoring process ran but couldn't extract text from documents
        
        Fallback strategy:
        1. Select documents with R≥0.6, ranked by S score
        2. Fill remaining slots with documents R<0.6, ranked by R score  
        3. Fill remaining slots with documents without R/S scores (no text for scoring)
        4. Final fallback: any documents with text
        """
        
        logger.info(f"Applying document rate limits with {len(candidates)} candidates")
        
        logger.info(f"Starting R/S score ranking with R threshold={high_priority_r_threshold}, max_docs={max_documents_per_trial}")
        
        # Debug: Check for documents with missing R/S scores
        missing_r_scores = [c for c in candidates if c['r_score'] is None]
        missing_s_scores = [c for c in candidates if c['s_score'] is None]
        if missing_r_scores:
            logger.warning(f"Found {len(missing_r_scores)} documents with missing R scores (likely no text for R/S scoring)")
        if missing_s_scores:
            logger.warning(f"Found {len(missing_s_scores)} documents with missing S scores (likely no text for R/S scoring)")
        
        # Step 1: Filter by R threshold (R≥0.6) and text availability
        relevant_docs = [
            c for c in candidates 
            if c['r_score'] is not None and c['r_score'] >= high_priority_r_threshold and (c['has_full_text'] or c['has_abstract'])
        ]
        
        logger.info(f"Found {len(relevant_docs)} documents meeting R≥{high_priority_r_threshold} threshold")
        
        # If no documents meet the R threshold, fall back to selecting documents with any R/S scores
        if not relevant_docs:
            # First try documents with any R/S scores (even if below threshold)
            fallback_docs = [
                c for c in candidates 
                if c['r_score'] is not None and (c['has_full_text'] or c['has_abstract'])
            ]
            
            if fallback_docs:
                # Sort by R score (descending) for fallback
                fallback_docs.sort(key=lambda x: (-float(x['r_score']) if x['r_score'] is not None else 0, x['doc_id']))
                relevant_docs = fallback_docs
                logger.info(f"Fallback selected {len(relevant_docs)} documents with R/S scores (below threshold)")
            else:
                # Final fallback: any documents with text (no R/S scores)
                logger.warning("No documents have R/S scores (likely no text available for R/S scoring), falling back to any documents with text")
                relevant_docs = [
                    c for c in candidates 
                    if c['has_full_text'] or c['has_abstract']
                ]
                # Sort by doc_id for deterministic ordering
                relevant_docs.sort(key=lambda x: x['doc_id'])
                logger.info(f"Final fallback selected {len(relevant_docs)} documents with text (no R/S scores available)")
        
        # Step 2: Sort by S score (descending), then R score (descending) as tiebreaker
        def sort_key(doc):
            # Primary: S score (higher = better) - only for docs with valid scores
            s_score = float(doc['s_score']) if doc['s_score'] is not None else -1.0  # Use -1 to put None scores last
            # Secondary: R score (higher = better) - only for docs with valid scores
            r_score = float(doc['r_score']) if doc['r_score'] is not None else -1.0  # Use -1 to put None scores last
            # Tertiary: doc_id for deterministic ordering (lower = better for consistency)
            doc_id = doc['doc_id']
            return (-s_score, -r_score, doc_id)
        
        sorted_docs = sorted(relevant_docs, key=sort_key)
        
        # Step 3: Take top K documents
        selected = sorted_docs[:max_documents_per_trial]
        
        # Step 4: Fallback logic - if not enough relevant docs, fill with next best R scores
        if len(selected) < max_documents_per_trial:
            remaining_slots = max_documents_per_trial - len(selected)
            fallback_limit = max_documents_per_trial // 2  # Half of rate limit
            
            # Get documents that didn't meet R threshold, sorted by R score
            fallback_docs = [
                c for c in candidates 
                if c['r_score'] is not None and c['r_score'] < high_priority_r_threshold and (c['has_full_text'] or c['has_abstract'])
            ]
            
            # Sort fallback docs by R score (descending)
            fallback_docs.sort(key=lambda x: (-float(x['r_score']) if x['r_score'] is not None else 0, x['doc_id']))
            
            # Add up to fallback_limit or remaining_slots, whichever is smaller
            fallback_count = min(remaining_slots, fallback_limit, len(fallback_docs))
            selected.extend(fallback_docs[:fallback_count])
            
            logger.info(f"Added {fallback_count} fallback documents (R<{high_priority_r_threshold})")
            
            # If still not enough documents, add documents without R/S scores (no text for scoring)
            remaining_slots = max_documents_per_trial - len(selected)
            if remaining_slots > 0:
                no_rs_docs = [
                    c for c in candidates 
                    if c['r_score'] is None and (c['has_full_text'] or c['has_abstract'])
                ]
                # Sort by doc_id for deterministic ordering
                no_rs_docs.sort(key=lambda x: x['doc_id'])
                
                # Add up to remaining slots
                no_rs_count = min(remaining_slots, len(no_rs_docs))
                selected.extend(no_rs_docs[:no_rs_count])
                
                if no_rs_count > 0:
                    logger.info(f"Added {no_rs_count} documents without R/S scores (no text for scoring)")
        
        # Final fallback: if still no documents selected, take any documents with text
        if not selected:
            logger.warning("No documents selected by R/S ranking, taking any documents with text")
            fallback_docs = [
                c for c in candidates 
                if c['has_full_text'] or c['has_abstract']
            ]
            # Sort by doc_id for deterministic ordering
            fallback_docs.sort(key=lambda x: x['doc_id'])
            selected = fallback_docs[:max_documents_per_trial]
            logger.info(f"Selected {len(selected)} documents as final fallback (no R/S scores available - likely no text for scoring)")
        
        # Final validation: filter out documents without text to prevent quality gate failures
        validated_selected = []
        for doc in selected:
            if doc['has_full_text'] or doc['has_abstract']:
                validated_selected.append(doc)
            else:
                logger.warning(f"Filtering out doc {doc['doc_id']} - no text available (will cause quality gate failure)")
        
        if len(validated_selected) < len(selected):
            logger.warning(f"Filtered out {len(selected) - len(validated_selected)} documents without text")
            selected = validated_selected
        
        logger.info(f"Rate limiting completed: {len(selected)} documents selected from {len(candidates)} candidates")
        
        return selected
    
    @staticmethod
    def generate_document_processing_stats(trial_documents, candidates, selected_candidates):
        """Generate processing statistics for document prioritization."""
        stats = {
            "total_documents": len(trial_documents),
            "total_candidates": len(candidates),
            "selected_documents": len(selected_candidates),
            "priority_counts": {},
            "text_availability": {},
            "rs_score_stats": {},
            "rate_limit_applied": True
        }
        
        # Count by priority
        for candidate in selected_candidates:
            priority = candidate.get('priority', 'UNKNOWN')
            stats["priority_counts"][priority] = stats["priority_counts"].get(priority, 0) + 1
        
        # Text availability stats
        stats["text_availability"] = {
            "has_full_text": sum(1 for c in selected_candidates if c.get('has_full_text', False)),
            "has_abstract": sum(1 for c in selected_candidates if c.get('has_abstract', False)),
            "no_text": sum(1 for c in selected_candidates if not (c.get('has_full_text', False) or c.get('has_abstract', False)))
        }
        
        # R/S score stats
        r_scores = [c.get('r_score', 0) for c in selected_candidates if c.get('r_score') is not None]
        s_scores = [c.get('s_score', 0) for c in selected_candidates if c.get('s_score') is not None]
        
        stats["rs_score_stats"] = {
            "avg_r_score": sum(r_scores) / len(r_scores) if r_scores else 0,
            "avg_s_score": sum(s_scores) / len(s_scores) if s_scores else 0,
            "max_r_score": max(r_scores) if r_scores else 0,
            "max_s_score": max(s_scores) if s_scores else 0,
            "documents_with_rs_scores": len(r_scores)
        }
        
        return stats
    
    @staticmethod
    async def mark_documents_as_selected(prioritized_doc_cards):
        """Mark selected documents as 'selected' for processing."""
        for doc_card in prioritized_doc_cards:
            try:
                # Update document status to 'selected' using DocumentManager
                with session_scope() as session:
                    doc = session.query(Document).filter(Document.doc_id == doc_card.doc_id).first()
                    if doc:
                        doc.processing_status = 'selected'
                        doc.selected_at = datetime.now(timezone.utc)
                        session.commit()
                        logger.debug(f"Marked document {doc_card.doc_id} as selected")
            except Exception as e:
                logger.warning(f"Failed to mark document {doc_card.doc_id} as selected: {e}")
