"""
Real-time failure tracker service.
"""
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from database.models.events import Event
from database.models.entities import Company, Drug, Disease
from database.models.clinical import ClinicalTrial
from src.services.failure_analysis_service import FailureAnalysisService

logger = logging.getLogger(__name__)


class FailureTracker:
    """
    Real-time failure tracker for monitoring trial and program failures.
    
    This is the first customer-facing feature - simple but valuable.
    """
    
    FAILURE_EVENT_TYPES = [
        'trial.status.terminated',
        'trial.status.withdrawn',
        'program.milestone.rejected',
        'regulatory.rejection',
    ]
    
    def __init__(self, session: Session):
        """Initialize failure tracker."""
        self.session = session
        self.failure_service = FailureAnalysisService(session)
    
    def get_recent_failures(
        self,
        days: int = 30,
        therapeutic_area: Optional[str] = None,
        phase: Optional[str] = None,
        company_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent failures with enriched entity details.
        
        Args:
            days: Number of days to look back
            therapeutic_area: Optional therapeutic area filter
            phase: Optional trial phase filter
            company_id: Optional company filter
            
        Returns:
            List of failure dictionaries with enriched details
        """
        start_date = date.today() - timedelta(days=days)
        
        # Query for failure events
        query = self.session.query(Event).filter(
            Event.event_type.in_(self.FAILURE_EVENT_TYPES),
            Event.event_date >= start_date,
            Event.deleted_at.is_(None)
        )
        
        if company_id:
            # Use PostgreSQL array contains operator
            from sqlalchemy import func
            query = query.filter(func.array_position(Event.entities_involved, company_id) != None)
        
        events = query.order_by(Event.event_date.desc()).all()
        
        # Enrich with entity details
        enriched_failures = []
        for event in events:
            failure = {
                'event_id': str(event.event_id),
                'event_type': event.event_type,
                'event_date': event.event_date.isoformat(),
                'event_data': event.event_data or {},
                'entities': self._get_entity_details(event.entities_involved),
            }
            enriched_failures.append(failure)
        
        # Apply additional filters if needed
        if therapeutic_area or phase:
            filtered_failures = []
            for failure in enriched_failures:
                # Get trial from entities if available
                trial_id = None
                try:
                    if 'trial' in failure['entities']:
                        trial_id = UUID(failure['entities']['trial']['id'])
                    elif 'drug' in failure['entities']:
                        # Try to find trial through drug
                        drug_id = UUID(failure['entities']['drug']['id'])
                        from database.models.relationships import TrialDrug
                        trial_link = self.session.query(TrialDrug).filter(
                            TrialDrug.drug_id == drug_id,
                            TrialDrug.deleted_at.is_(None)
                        ).first()
                        if trial_link:
                            trial_id = trial_link.trial_id
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning(f"Invalid UUID in entity details: {e}")
                    continue
                
                # Filter by therapeutic area
                if therapeutic_area and trial_id:
                    from database.models.relationships import TrialDisease
                    disease_link = self.session.query(TrialDisease).join(
                        Disease, TrialDisease.disease_id == Disease.disease_id
                    ).filter(
                        TrialDisease.trial_id == trial_id,
                        Disease.disease_name.ilike(f'%{therapeutic_area}%'),
                        TrialDisease.deleted_at.is_(None),
                        Disease.deleted_at.is_(None)
                    ).first()
                    if not disease_link:
                        continue
                
                # Filter by phase
                if phase and trial_id:
                    trial = self.session.query(ClinicalTrial).filter(
                        ClinicalTrial.trial_id == trial_id,
                        ClinicalTrial.deleted_at.is_(None)
                    ).first()
                    if trial and trial.phase != phase:
                        continue
                
                filtered_failures.append(failure)
            
            return filtered_failures
        
        return enriched_failures
    
    def _get_entity_details(self, entity_ids: List[UUID]) -> Dict[str, Any]:
        """Get details for entities involved in an event."""
        entities = {}
        
        try:
            from database.models.entities import Disease, Target, Institution
            from database.models.publications import Publication, Patent
            from database.models.clinical import RegulatoryEvent
            from database.models.publications import SECFiling
            
            for entity_id in entity_ids:
                # Try to find entity in different tables (order by most common first)
                
                # Company
                company = self.session.query(Company).filter(
                    Company.company_id == entity_id,
                    Company.deleted_at.is_(None)
                ).first()
                if company:
                    entities['company'] = {
                        'id': str(company.company_id),
                        'name': company.name,
                    }
                    continue
                
                # Drug
                drug = self.session.query(Drug).filter(
                    Drug.drug_id == entity_id,
                    Drug.deleted_at.is_(None)
                ).first()
                if drug:
                    entities['drug'] = {
                        'id': str(drug.drug_id),
                        'name': drug.primary_name,
                    }
                    continue
                
                # Trial
                trial = self.session.query(ClinicalTrial).filter(
                    ClinicalTrial.trial_id == entity_id,
                    ClinicalTrial.deleted_at.is_(None)
                ).first()
                if trial:
                    entities['trial'] = {
                        'id': str(trial.trial_id),
                        'nct_id': trial.nct_id,
                        'title': trial.trial_title,
                    }
                    continue
                
                # Disease
                disease = self.session.query(Disease).filter(
                    Disease.disease_id == entity_id,
                    Disease.deleted_at.is_(None)
                ).first()
                if disease:
                    entities['disease'] = {
                        'id': str(disease.disease_id),
                        'name': disease.disease_name,
                    }
                    continue
                
                # Institution
                institution = self.session.query(Institution).filter(
                    Institution.institution_id == entity_id,
                    Institution.deleted_at.is_(None)
                ).first()
                if institution:
                    entities['institution'] = {
                        'id': str(institution.institution_id),
                        'name': institution.name,
                    }
                    continue
                
                # Publication
                publication = self.session.query(Publication).filter(
                    Publication.pub_id == entity_id,
                    Publication.deleted_at.is_(None)
                ).first()
                if publication:
                    entities['publication'] = {
                        'id': str(publication.pub_id),
                        'title': publication.title,
                        'pmid': publication.pmid,
                    }
                    continue
                
                # Patent
                patent = self.session.query(Patent).filter(
                    Patent.patent_id == entity_id,
                    Patent.deleted_at.is_(None)
                ).first()
                if patent:
                    entities['patent'] = {
                        'id': str(patent.patent_id),
                        'patent_number': patent.patent_number,
                    }
                    continue
                
                # Regulatory Event
                reg_event = self.session.query(RegulatoryEvent).filter(
                    RegulatoryEvent.event_id == entity_id,
                    RegulatoryEvent.deleted_at.is_(None)
                ).first()
                if reg_event:
                    entities['regulatory_event'] = {
                        'id': str(reg_event.event_id),
                        'event_type': reg_event.event_type,
                        'event_date': reg_event.event_date.isoformat() if reg_event.event_date else None,
                    }
                    continue
                
                # SEC Filing
                sec_filing = self.session.query(SECFiling).filter(
                    SECFiling.filing_id == entity_id,
                    SECFiling.deleted_at.is_(None)
                ).first()
                if sec_filing:
                    entities['sec_filing'] = {
                        'id': str(sec_filing.filing_id),
                        'filing_type': sec_filing.filing_type,
                        'accession_number': sec_filing.accession_number,
                    }
                    continue
                
                # Target
                target = self.session.query(Target).filter(
                    Target.target_id == entity_id,
                    Target.deleted_at.is_(None)
                ).first()
                if target:
                    entities['target'] = {
                        'id': str(target.target_id),
                        'name': target.target_name,
                    }
                    continue
                
                # Unknown entity type
                logger.warning(f"Unknown entity type for ID: {entity_id}")
                entities['unknown'] = {
                    'id': str(entity_id),
                    'note': 'Entity type not identified'
                }
        
        except Exception as e:
            logger.error(f"Error in _get_entity_details: {e}", exc_info=True)
        
        return entities
    
    def get_failure_statistics(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get failure statistics for the time period.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dictionary with failure statistics
        """
        start_date = date.today() - timedelta(days=days)
        
        failures = self.session.query(Event).filter(
            Event.event_type.in_(self.FAILURE_EVENT_TYPES),
            Event.event_date >= start_date,
            Event.deleted_at.is_(None)
        ).all()
        
        # Count by type
        by_type = {}
        for failure in failures:
            event_type = failure.event_type
            by_type[event_type] = by_type.get(event_type, 0) + 1
        
        return {
            'total_failures': len(failures),
            'by_type': by_type,
            'period_days': days,
            'start_date': start_date.isoformat(),
            'end_date': date.today().isoformat(),
        }

