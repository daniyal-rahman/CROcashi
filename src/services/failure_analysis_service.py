"""
Failure analysis service for flexible querying and analysis.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from database.models.events import Event
from database.models.entities import Company, Drug, Disease
from database.models.clinical import ClinicalTrial

logger = logging.getLogger(__name__)


class FailureAnalysisService:
    """
    Service layer for flexible querying and failure analysis.
    
    Provides high-level methods for common query patterns without
    exposing database implementation details.
    """
    
    def __init__(self, session: Session):
        """Initialize failure analysis service."""
        self.session = session
    
    def get_program_events(
        self,
        entity_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        event_types: Optional[List[str]] = None,
        significance_levels: Optional[List[str]] = None
    ) -> List[Event]:
        """
        Get all events for a program/drug/trial/company.
        
        Args:
            entity_id: Entity ID to get events for
            start_date: Optional start date filter
            end_date: Optional end date filter
            event_types: Optional list of event types to filter
            significance_levels: Optional list of significance levels (critical, major, minor, trace)
            
        Returns:
            List of Event objects
        """
        try:
            # Validate date range
            if start_date and end_date and start_date > end_date:
                logger.warning(f"Invalid date range: start_date {start_date} > end_date {end_date}")
                return []
            
            # Use PostgreSQL array contains operator (@>)
            from sqlalchemy import func
            query = self.session.query(Event).filter(
                func.array_position(Event.entities_involved, entity_id) != None,
                Event.deleted_at.is_(None)
            )
            
            if start_date:
                query = query.filter(Event.event_date >= start_date)
            
            if end_date:
                query = query.filter(Event.event_date <= end_date)
            
            if event_types:
                query = query.filter(Event.event_type.in_(event_types))
            
            if significance_levels:
                query = query.filter(Event.event_significance.in_(significance_levels))
            
            return query.order_by(Event.event_date.desc()).all()
            
        except Exception as e:
            logger.error(f"Error in get_program_events: {e}", exc_info=True)
            return []
    
    def get_failure_signals(
        self,
        entity_id: UUID,
        signal_types: Optional[List[str]] = None
    ) -> List[Event]:
        """
        Get early warning signals for a program.
        
        Args:
            entity_id: Entity ID to get signals for
            signal_types: Optional list of signal types (e.g., ['enrollment_slowdown', 'personnel_change'])
            
        Returns:
            List of Event objects that represent warning signals
        """
        try:
            # Define failure signal event types
            failure_signals = [
                'trial.status.terminated',
                'trial.status.withdrawn',
                'trial.status.suspended',
                'regulatory.clinical_hold',
                'personnel.key_departure',
            ]
            
            if signal_types:
                failure_signals = [s for s in failure_signals if s in signal_types]
            
            return self.get_program_events(
                entity_id=entity_id,
                event_types=failure_signals,
                significance_levels=['critical', 'major']
            )
        except Exception as e:
            logger.error(f"Error in get_failure_signals: {e}", exc_info=True)
            return []
    
    def get_competitive_landscape(
        self,
        mechanism: Optional[str] = None,
        indication: Optional[str] = None,
        include_failed: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all programs in a therapeutic space.
        
        Args:
            mechanism: Optional mechanism name to filter
            indication: Optional disease/indication to filter
            include_failed: Whether to include failed/terminated programs
            
        Returns:
            List of dictionaries with program information
        """
        try:
            from database.models.relationships import DrugMechanism, DrugIndication
            from database.models.entities import Mechanism
            
            # Start with drugs query
            query = self.session.query(Drug).filter(Drug.deleted_at.is_(None))
            
            # Join through drug_mechanisms if mechanism specified
            if mechanism:
                query = query.join(
                    DrugMechanism, Drug.drug_id == DrugMechanism.drug_id
                ).join(
                    Mechanism, DrugMechanism.mechanism_id == Mechanism.mechanism_id
                ).filter(
                    Mechanism.mechanism_name.ilike(f'%{mechanism}%'),
                    DrugMechanism.deleted_at.is_(None),
                    Mechanism.deleted_at.is_(None)
                )
            
            # Join through drug_indications if indication specified
            if indication:
                query = query.join(
                    DrugIndication, Drug.drug_id == DrugIndication.drug_id
                ).join(
                    Disease, DrugIndication.disease_id == Disease.disease_id
                ).filter(
                    Disease.disease_name.ilike(f'%{indication}%'),
                    DrugIndication.deleted_at.is_(None),
                    Disease.deleted_at.is_(None)
                )
            
            # Filter out failed programs if requested
            if not include_failed:
                # Get drug IDs that have failure events
                from sqlalchemy import func
                try:
                    failed_drug_ids = self.session.query(Event).filter(
                        Event.event_type.in_(['trial.status.terminated', 'trial.status.withdrawn', 'program.milestone.rejected']),
                        Event.deleted_at.is_(None)
                    ).with_entities(
                        func.unnest(Event.entities_involved).label('entity_id')
                    ).subquery()
                    
                    query = query.filter(~Drug.drug_id.in_(
                        self.session.query(failed_drug_ids.c.entity_id)
                    ))
                except Exception as e:
                    logger.warning(f"Error filtering failed programs: {e}, including all programs")
                    # Continue without filtering if query fails
            
            drugs = query.distinct().all()
            
            # Build result list
            results = []
            for drug in drugs:
                result = {
                    'drug_id': str(drug.drug_id),
                    'drug_name': drug.primary_name,
                    'generic_name': drug.generic_name,
                    'drug_type': drug.drug_type,
                }
                
                # Get mechanisms (with null checks)
                mechanisms = []
                if hasattr(drug, 'mechanisms') and drug.mechanisms:
                    for m in drug.mechanisms:
                        if m.deleted_at:
                            continue
                        if hasattr(m, 'mechanism') and m.mechanism:
                            mechanisms.append(m.mechanism.mechanism_name)
                result['mechanisms'] = mechanisms
                
                # Get indications (with null checks)
                indications = []
                if hasattr(drug, 'indications') and drug.indications:
                    for ind in drug.indications:
                        if ind.deleted_at:
                            continue
                        if hasattr(ind, 'disease') and ind.disease:
                            indications.append({
                                'disease': ind.disease.disease_name,
                                'phase': ind.development_phase,
                                'approved': ind.approved
                            })
                result['indications'] = indications
                
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in get_competitive_landscape: {e}", exc_info=True)
            return []
    
    def calculate_failure_risk(self, entity_id: UUID) -> Dict[str, Any]:
        """
        Calculate failure risk score for a program.
        
        Args:
            entity_id: Entity ID to calculate risk for
            
        Returns:
            Dictionary with risk score and contributing factors
        """
        try:
            # Get recent events
            recent_events = self.get_program_events(
                entity_id=entity_id,
                start_date=date.today() - timedelta(days=365)
            )
            
            # Count failure signals
            failure_events = [e for e in recent_events if e.event_type in [
                'trial.status.terminated',
                'trial.status.withdrawn',
                'regulatory.clinical_hold',
            ]]
            
            # Simple risk calculation (placeholder)
            risk_score = min(len(failure_events) * 0.2, 1.0)
            
            return {
                'entity_id': str(entity_id),
                'risk_score': risk_score,
                'failure_events_count': len(failure_events),
                'recent_events_count': len(recent_events),
                'calculated_at': datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error in calculate_failure_risk: {e}", exc_info=True)
            return {
                'entity_id': str(entity_id),
                'risk_score': 0.0,
                'error': str(e),
                'calculated_at': datetime.now().isoformat(),
            }
    
    def get_entity_timeline(
        self,
        entity_id: UUID,
        include_related: bool = False
    ) -> List[Event]:
        """
        Get complete timeline for an entity with optional related entities.
        
        Args:
            entity_id: Entity ID to get timeline for
            include_related: Whether to include events from related entities
            
        Returns:
            List of Event objects ordered by date
        """
        try:
            # Get direct events
            entity_ids = [entity_id]
            
            if include_related:
                # Find related entity IDs based on relationships
                related_ids = set()
                
                # Check if it's a drug - get related trials, companies, diseases
                drug = self.session.query(Drug).filter(
                    Drug.drug_id == entity_id,
                    Drug.deleted_at.is_(None)
                ).first()
                
                if drug:
                    from database.models.relationships import (
                        TrialDrug, CompanyDrug, DrugIndication
                    )
                    # Get trials
                    trials = self.session.query(TrialDrug.trial_id).filter(
                        TrialDrug.drug_id == entity_id,
                        TrialDrug.deleted_at.is_(None)
                    ).all()
                    related_ids.update([t[0] for t in trials])
                    
                    # Get companies
                    companies = self.session.query(CompanyDrug.company_id).filter(
                        CompanyDrug.drug_id == entity_id,
                        CompanyDrug.deleted_at.is_(None)
                    ).all()
                    related_ids.update([c[0] for c in companies])
                    
                    # Get diseases
                    diseases = self.session.query(DrugIndication.disease_id).filter(
                        DrugIndication.drug_id == entity_id,
                        DrugIndication.deleted_at.is_(None)
                    ).all()
                    related_ids.update([d[0] for d in diseases])
                
                # Check if it's a company - get related drugs, trials
                company = self.session.query(Company).filter(
                    Company.company_id == entity_id,
                    Company.deleted_at.is_(None)
                ).first()
                
                if company:
                    from database.models.relationships import CompanyDrug, TrialSponsor
                    # Get drugs
                    drugs = self.session.query(CompanyDrug.drug_id).filter(
                        CompanyDrug.company_id == entity_id,
                        CompanyDrug.deleted_at.is_(None)
                    ).all()
                    related_ids.update([d[0] for d in drugs])
                    
                    # Get trials
                    trials = self.session.query(TrialSponsor.trial_id).filter(
                        TrialSponsor.entity_id == entity_id,
                        TrialSponsor.entity_type == 'company',
                        TrialSponsor.deleted_at.is_(None)
                    ).all()
                    related_ids.update([t[0] for t in trials])
                
                entity_ids.extend(list(related_ids))
            
            # Get events for all entity IDs
            from sqlalchemy import func
            all_events = []
            for eid in entity_ids:
                events = self.session.query(Event).filter(
                    func.array_position(Event.entities_involved, eid) != None,
                    Event.deleted_at.is_(None)
                ).all()
                all_events.extend(events)
            
            # Remove duplicates and sort by date
            seen = set()
            unique_events = []
            for event in all_events:
                if event.event_id not in seen:
                    seen.add(event.event_id)
                    unique_events.append(event)
            
            return sorted(unique_events, key=lambda e: e.event_date, reverse=True)
            
        except Exception as e:
            logger.error(f"Error in get_entity_timeline: {e}", exc_info=True)
            return self.get_program_events(entity_id=entity_id)
    
    def search_by_pattern(self, pattern_definition: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Flexible pattern matching - search for entities matching a pattern.
        
        Args:
            pattern_definition: Pattern definition dictionary (see pattern_matcher.py)
            
        Returns:
            List of matching entities with pattern match details
        """
        try:
            from src.services.pattern_matcher import PatternMatcher
            
            pattern_matcher = PatternMatcher(self.session)
            
            # Get all entities that might match (drugs, companies, trials)
            # This is a simplified search - in production you'd want more sophisticated entity discovery
            entity_candidates = []
            
            # Get drugs
            drugs = self.session.query(Drug).filter(Drug.deleted_at.is_(None)).limit(1000).all()
            entity_candidates.extend([(d.drug_id, 'drug') for d in drugs])
            
            # Get companies
            companies = self.session.query(Company).filter(Company.deleted_at.is_(None)).limit(1000).all()
            entity_candidates.extend([(c.company_id, 'company') for c in companies])
            
            # Get trials
            trials = self.session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).limit(1000).all()
            entity_candidates.extend([(t.trial_id, 'trial') for t in trials])
            
            # Check each candidate
            matches = []
            for entity_id, entity_type in entity_candidates:
                match_result = pattern_matcher.match_pattern(entity_id, pattern_definition)
                if match_result.get('pattern_matched', False):
                    matches.append({
                        'entity_id': str(entity_id),
                        'entity_type': entity_type,
                        'match_result': match_result
                    })
            
            return matches
            
        except Exception as e:
            logger.error(f"Error in search_by_pattern: {e}", exc_info=True)
            return []

