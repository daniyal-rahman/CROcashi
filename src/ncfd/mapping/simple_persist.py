"""
Simplified Persistence Layer for Resolver System

This module provides clean persistence functions for the simplified resolver system.
Replaces the complex probabilistic persistence with simple, clear functions.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.models import SponsorResolution, ManualReviewQueue, LLMDiscovery, CompanyAlias
from .normalize import norm_name

logger = logging.getLogger(__name__)


def save_resolution(
    session: Session,
    nct_id: str,
    sponsor_text: str,
    company_id: Optional[int],
    match_method: str,
    confidence: float,
    evidence: Dict[str, Any]
) -> None:
    """
    Save resolution result to sponsor_resolutions table.
    
    Args:
        session: Database session
        nct_id: Clinical trial NCT ID
        sponsor_text: Raw sponsor text
        company_id: Resolved company ID (None if no match)
        match_method: exact, fuzzy, llm, manual
        confidence: Confidence score (0.0-1.0)
        evidence: Evidence dictionary
    """
    try:
        resolution = SponsorResolution(
            nct_id=nct_id,
            sponsor_text=sponsor_text,
            sponsor_text_norm=norm_name(sponsor_text),
            company_id=company_id,
            match_method=match_method,
            confidence=confidence,
            evidence=evidence
        )
        session.add(resolution)
        session.commit()
        logger.info(f"Saved resolution: {nct_id} -> {company_id} ({match_method})")
    except Exception as e:
        logger.error(f"Error saving resolution: {e}")
        session.rollback()
        raise


def add_to_review_queue(
    session: Session,
    nct_id: str,
    sponsor_text: str,
    reason: str = "no_match_found"
) -> None:
    """
    Add unresolved sponsor to manual review queue.
    
    Args:
        session: Database session
        nct_id: Clinical trial NCT ID
        sponsor_text: Raw sponsor text
        reason: Reason for review
    """
    try:
        # Check if already in queue
        existing = session.query(ManualReviewQueue).filter(
            ManualReviewQueue.nct_id == nct_id,
            ManualReviewQueue.status == "pending"
        ).first()
        
        if not existing:
            review_item = ManualReviewQueue(
                nct_id=nct_id,
                sponsor_text=sponsor_text,
                status="pending"
            )
            session.add(review_item)
            session.commit()
            logger.info(f"Added to review queue: {nct_id} - {sponsor_text}")
        else:
            logger.info(f"Already in review queue: {nct_id}")
    except Exception as e:
        logger.error(f"Error adding to review queue: {e}")
        session.rollback()
        raise


def save_llm_discovery(
    session: Session,
    nct_id: str,
    sponsor_text: str,
    discovered_company_id: Optional[int],
    discovered_aliases: Optional[List[str]],
    llm_response: Dict[str, Any],
    confidence: Optional[float]
) -> None:
    """
    Save LLM discovery for learning system.
    
    Args:
        session: Database session
        nct_id: Clinical trial NCT ID
        sponsor_text: Raw sponsor text
        discovered_company_id: Company ID discovered by LLM
        discovered_aliases: New aliases discovered
        llm_response: Full LLM response
        confidence: LLM confidence score
    """
    try:
        discovery = LLMDiscovery(
            nct_id=nct_id,
            sponsor_text=sponsor_text,
            discovered_company_id=discovered_company_id,
            discovered_aliases=discovered_aliases,
            llm_response=llm_response,
            confidence=confidence
        )
        session.add(discovery)
        session.commit()
        logger.info(f"Saved LLM discovery: {nct_id} -> {discovered_company_id}")
    except Exception as e:
        logger.error(f"Error saving LLM discovery: {e}")
        session.rollback()
        raise


def learn_aliases_from_discoveries(session: Session, min_confidence: float = 0.85) -> int:
    """
    Process LLM discoveries to learn new aliases.
    
    Args:
        session: Database session
        min_confidence: Minimum confidence threshold for learning
        
    Returns:
        Number of aliases learned
    """
    try:
        # Get high-confidence LLM discoveries
        discoveries = session.query(LLMDiscovery).filter(
            LLMDiscovery.confidence >= min_confidence,
            LLMDiscovery.discovered_company_id.isnot(None),
            LLMDiscovery.discovered_aliases.isnot(None)
        ).all()
        
        aliases_learned = 0
        
        for discovery in discoveries:
            if discovery.discovered_aliases:
                for alias_text in discovery.discovered_aliases:
                    # Check if alias already exists
                    existing = session.query(CompanyAlias).filter(
                        CompanyAlias.company_id == discovery.discovered_company_id,
                        CompanyAlias.alias_norm == norm_name(alias_text)
                    ).first()
                    
                    if not existing:
                        # Add new alias
                        new_alias = CompanyAlias(
                            company_id=discovered_company_id,
                            alias=alias_text,
                            alias_norm=norm_name(alias_text),
                            alias_type="llm_discovered",
                            source="llm_discovery"
                        )
                        session.add(new_alias)
                        aliases_learned += 1
                        logger.info(f"Learned alias: {alias_text} -> company {discovery.discovered_company_id}")
        
        session.commit()
        logger.info(f"Learned {aliases_learned} new aliases from LLM discoveries")
        return aliases_learned
        
    except Exception as e:
        logger.error(f"Error learning aliases: {e}")
        session.rollback()
        raise


def get_pending_reviews(session: Session, limit: int = 100) -> List[ManualReviewQueue]:
    """
    Get pending review items.
    
    Args:
        session: Database session
        limit: Maximum number of items to return
        
    Returns:
        List of pending review items
    """
    return session.query(ManualReviewQueue).filter(
        ManualReviewQueue.status == "pending"
    ).limit(limit).all()


def complete_review(
    session: Session,
    review_id: int,
    company_id: Optional[int],
    notes: Optional[str] = None
) -> None:
    """
    Complete a manual review item.
    
    Args:
        session: Database session
        review_id: Review item ID
        company_id: Assigned company ID (None if skipped)
        notes: Review notes
    """
    try:
        review_item = session.query(ManualReviewQueue).filter(
            ManualReviewQueue.id == review_id
        ).first()
        
        if review_item:
            review_item.status = "completed"
            review_item.assigned_company_id = company_id
            review_item.notes = notes
            
            # Save resolution if company was assigned
            if company_id:
                save_resolution(
                    session=session,
                    nct_id=review_item.nct_id,
                    sponsor_text=review_item.sponsor_text,
                    company_id=company_id,
                    match_method="manual",
                    confidence=1.0,
                    evidence={"method": "manual_review", "review_id": review_id}
                )
            
            session.commit()
            logger.info(f"Completed review {review_id}: {company_id}")
        else:
            logger.warning(f"Review item {review_id} not found")
            
    except Exception as e:
        logger.error(f"Error completing review: {e}")
        session.rollback()
        raise


def skip_review(session: Session, review_id: int, notes: Optional[str] = None) -> None:
    """
    Skip a manual review item.
    
    Args:
        session: Database session
        review_id: Review item ID
        notes: Skip reason
    """
    try:
        review_item = session.query(ManualReviewQueue).filter(
            ManualReviewQueue.id == review_id
        ).first()
        
        if review_item:
            review_item.status = "skipped"
            review_item.notes = notes
            session.commit()
            logger.info(f"Skipped review {review_id}")
        else:
            logger.warning(f"Review item {review_id} not found")
            
    except Exception as e:
        logger.error(f"Error skipping review: {e}")
        session.rollback()
        raise


def get_resolution_stats(session: Session) -> Dict[str, Any]:
    """
    Get resolution statistics.
    
    Args:
        session: Database session
        
    Returns:
        Dictionary with resolution statistics
    """
    try:
        # Count by match method
        result = session.execute(text("""
            SELECT 
                match_method,
                COUNT(*) as count,
                AVG(confidence) as avg_confidence
            FROM sponsor_resolutions
            GROUP BY match_method
            ORDER BY count DESC
        """))
        
        method_stats = {}
        for row in result:
            method_stats[row.match_method] = {
                "count": row.count,
                "avg_confidence": float(row.avg_confidence) if row.avg_confidence else 0.0
            }
        
        # Count pending reviews
        pending_count = session.query(ManualReviewQueue).filter(
            ManualReviewQueue.status == "pending"
        ).count()
        
        # Count LLM discoveries
        discovery_count = session.query(LLMDiscovery).count()
        
        return {
            "method_stats": method_stats,
            "pending_reviews": pending_count,
            "llm_discoveries": discovery_count
        }
        
    except Exception as e:
        logger.error(f"Error getting resolution stats: {e}")
        return {}
