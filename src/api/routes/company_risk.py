"""
Company risk API routes.
"""
import logging
from datetime import date
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.services.company_risk_service import CompanyRiskService
from src.api.models.company_risk import (
    CompanyRiskProfile,
    CompanyMetrics,
    CompanyTimelineResponse,
    TimelineEvent,
    CompanySearchResponse,
    CompanySearchResult
)

logger = logging.getLogger(__name__)

router = APIRouter()


def get_risk_service(db: Session = Depends(get_db)) -> CompanyRiskService:
    """Get company risk service dependency."""
    return CompanyRiskService(db)


@router.get("/companies/{company_id}/risk-profile", response_model=CompanyRiskProfile)
async def get_company_risk_profile(
    company_id: UUID,
    service: CompanyRiskService = Depends(get_risk_service)
):
    """
    Get risk profile for a company.
    
    Returns risk score (0-100), risk category, and component breakdown.
    """
    try:
        result = service.calculate_company_risk_score(company_id)
        
        if 'error' in result:
            raise HTTPException(status_code=404, detail=result['error'])
        
        return CompanyRiskProfile(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting risk profile for {company_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/{company_id}/metrics", response_model=CompanyMetrics)
async def get_company_metrics(
    company_id: UUID,
    service: CompanyRiskService = Depends(get_risk_service)
):
    """
    Get raw metrics for a company.
    
    Returns total trials, active trials, success rates by phase, etc.
    """
    try:
        metrics = service.get_company_metrics(company_id)
        
        if 'error' in metrics:
            raise HTTPException(status_code=404, detail=metrics['error'])
        
        return CompanyMetrics(**metrics)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting metrics for {company_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/{company_id}/timeline", response_model=CompanyTimelineResponse)
async def get_company_timeline(
    company_id: UUID,
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    event_types: Optional[List[str]] = Query(None, description="Filter by event types"),
    service: CompanyRiskService = Depends(get_risk_service)
):
    """
    Get timeline of events for a company.
    
    Returns chronological list of events with optional date and type filters.
    """
    try:
        events = service.get_company_timeline(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            event_types=event_types
        )
        
        timeline_events = [
            TimelineEvent(
                event_id=str(e.event_id),
                event_type=e.event_type,
                event_date=e.event_date.isoformat(),
                event_significance=e.event_significance,
                entities_involved=[str(eid) for eid in e.entities_involved],
                event_data=e.event_data,
                source_id=str(e.source_id) if e.source_id else None,
                confidence_score=float(e.confidence_score) if e.confidence_score else None
            )
            for e in events
        ]
        
        return CompanyTimelineResponse(
            company_id=str(company_id),
            events=timeline_events,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            total_events=len(timeline_events)
        )
        
    except Exception as e:
        logger.error(f"Error getting timeline for {company_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/failures/recent", response_model=List[Dict])
async def get_recent_failures(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    service: CompanyRiskService = Depends(get_risk_service)
):
    """
    Get recent high-risk/failed trials.
    
    Returns list of recent failures with company and trial details.
    """
    try:
        from src.services.failure_tracker import FailureTracker
        from database.config import get_db_session
        
        # Get session from service
        db = service.session
        tracker = FailureTracker(db)
        
        failures = tracker.get_recent_failures(days=days)
        
        # Limit results
        failures = failures[:limit]
        
        return failures
        
    except Exception as e:
        logger.error(f"Error getting recent failures: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/search", response_model=CompanySearchResponse)
async def search_companies(
    q: Optional[str] = Query(None, description="Search query for company name"),
    risk_category: Optional[str] = Query(None, description="Filter by risk category (LOW, MODERATE, HIGH, CRITICAL)"),
    therapeutic_area: Optional[str] = Query(None, description="Filter by therapeutic area"),
    min_programs: Optional[int] = Query(None, ge=0, description="Minimum number of programs"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    service: CompanyRiskService = Depends(get_risk_service)
):
    """
    Search companies with filters.
    
    Returns list of companies matching criteria with risk scores.
    """
    try:
        from database.models.entities import Company
        from database.models.relationships import TrialSponsor, TrialDisease
        from database.models.entities import Disease
        from sqlalchemy import func
        
        # Get database session from service
        db = service.session
        
        # Start with base query
        query = db.query(Company).filter(
            Company.deleted_at.is_(None)
        )
        
        # Apply company name search if provided
        if q:
            query = query.filter(Company.name.ilike(f'%{q}%'))
        
        # Apply filters
        if therapeutic_area:
            # Join through trials and diseases
            query = query.join(
                TrialSponsor, Company.company_id == TrialSponsor.entity_id
            ).join(
                TrialDisease, TrialSponsor.trial_id == TrialDisease.trial_id
            ).join(
                Disease, TrialDisease.disease_id == Disease.disease_id
            ).filter(
                Disease.disease_name.ilike(f'%{therapeutic_area}%'),
                TrialSponsor.entity_type == 'company',
                TrialSponsor.deleted_at.is_(None),
                TrialDisease.deleted_at.is_(None),
                Disease.deleted_at.is_(None)
            ).distinct()
        
        if min_programs:
            # Subquery to count trials per company
            trial_counts = db.query(
                TrialSponsor.entity_id,
                func.count(TrialSponsor.trial_id).label('trial_count')
            ).filter(
                TrialSponsor.entity_type == 'company',
                TrialSponsor.deleted_at.is_(None)
            ).group_by(TrialSponsor.entity_id).subquery()
            
            query = query.join(
                trial_counts, Company.company_id == trial_counts.c.entity_id
            ).filter(trial_counts.c.trial_count >= min_programs).distinct()
        
        # Get total count BEFORE applying limit/offset (for accurate pagination)
        total = query.count()
        
        # Get companies with pagination
        companies = query.limit(limit).offset(offset).all()
        
        # Calculate risk scores for each company (with error handling)
        results = []
        for company in companies:
            try:
                risk_result = service.calculate_company_risk_score(company.company_id)
                
                # Check for errors in risk result
                if 'error' in risk_result:
                    logger.warning(f"Error calculating risk score for {company.company_id} ({company.name}): {risk_result.get('error')}")
                    # Don't skip - return with default risk score instead
                    risk_result = {
                        'risk_score': 0.0,
                        'risk_category': 'LOW',
                        'error': risk_result.get('error')
                    }
                
                # Apply risk category filter early to avoid unnecessary metric calculation
                if risk_category and risk_result.get('risk_category') != risk_category:
                    continue
                
                metrics = service.get_company_metrics(company.company_id)
                
                # Check for errors in metrics
                if 'error' in metrics:
                    logger.warning(f"Error getting metrics for {company.company_id} ({company.name}): {metrics.get('error')}")
                    # Don't skip - return with default metrics instead
                    metrics = {
                        'total_trials': 0,
                        'active_trials': 0,
                        'terminated_count': 0,
                        'error': metrics.get('error')
                    }
                
                results.append(CompanySearchResult(
                    company_id=str(company.company_id),
                    company_name=company.name,
                    risk_score=risk_result.get('risk_score', 0.0),
                    risk_category=risk_result.get('risk_category', 'LOW'),
                    total_trials=metrics.get('total_trials', 0),
                    active_trials=metrics.get('active_trials', 0),
                    terminated_count=metrics.get('terminated_count', 0)
                ))
            except Exception as e:
                logger.error(f"Error processing company {company.company_id}: {e}", exc_info=True)
                # Continue with next company instead of failing entire search
                continue
        
        return CompanySearchResponse(
            companies=results,
            total=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Error searching companies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

