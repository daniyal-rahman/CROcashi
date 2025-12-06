"""
Pattern matching system for failure pattern recognition.
"""
import logging
from datetime import date, timedelta
from typing import Dict, List, Any, Optional
from uuid import UUID

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from database.models.events import Event
from src.services.failure_analysis_service import FailureAnalysisService

logger = logging.getLogger(__name__)


class PatternMatcher:
    """
    Pattern matching engine for detecting failure patterns.
    
    Supports flexible pattern definitions using JSON schema.
    Can evolve to DSL later if needed.
    """
    
    def __init__(self, session: Session):
        """Initialize pattern matcher."""
        self.session = session
        self.failure_service = FailureAnalysisService(session)
    
    def match_pattern(
        self,
        entity_id: UUID,
        pattern_definition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check if an entity matches a pattern definition.
        
        Pattern definition structure:
        {
            "conditions": [
                {
                    "type": "event_absence",
                    "event_type": "enrollment_update",
                    "time_window": "6 months"
                },
                {
                    "type": "event_presence",
                    "event_type": "investigator_departure",
                    "count": ">= 2"
                }
            ],
            "relationship_requirements": [
                {
                    "relationship_type": "investigator",
                    "min_count": 1
                }
            ]
        }
        
        Args:
            entity_id: Entity ID to check
            pattern_definition: Pattern definition dictionary
            
        Returns:
            Dictionary with match result and details
        """
        if not pattern_definition:
            return {
                'entity_id': str(entity_id),
                'pattern_matched': False,
                'error': 'Empty pattern definition'
            }
        
        conditions = pattern_definition.get('conditions', [])
        relationship_requirements = pattern_definition.get('relationship_requirements', [])
        
        match_results = []
        all_conditions_met = True
        
        # Check each condition
        for condition in conditions:
            condition_type = condition.get('type')
            result = self._check_condition(entity_id, condition)
            match_results.append({
                'condition': condition,
                'result': result,
                'met': result.get('met', False)
            })
            
            if not result.get('met', False):
                all_conditions_met = False
        
        # Check relationship requirements
        relationship_results = []
        for req in relationship_requirements:
            result = self._check_relationship_requirement(entity_id, req)
            relationship_results.append({
                'requirement': req,
                'result': result,
                'met': result.get('met', False)
            })
            
            if not result.get('met', False):
                all_conditions_met = False
        
        return {
            'entity_id': str(entity_id),
            'pattern_matched': all_conditions_met,
            'condition_results': match_results,
            'relationship_results': relationship_results,
            'matched_at': date.today().isoformat(),
        }
    
    def _check_condition(
        self,
        entity_id: UUID,
        condition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check a single condition against an entity."""
        condition_type = condition.get('type')
        
        if condition_type == 'event_absence':
            return self._check_event_absence(entity_id, condition)
        elif condition_type == 'event_presence':
            return self._check_event_presence(entity_id, condition)
        elif condition_type == 'event_count':
            return self._check_event_count(entity_id, condition)
        else:
            return {
                'met': False,
                'error': f'Unknown condition type: {condition_type}'
            }
    
    def _check_event_absence(
        self,
        entity_id: UUID,
        condition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check that an event type is absent in a time window."""
        event_type = condition.get('event_type')
        time_window = condition.get('time_window', '6 months')
        
        # Parse time window
        days = self._parse_time_window(time_window)
        start_date = date.today() - timedelta(days=days)
        
        # Check for events
        events = self.failure_service.get_program_events(
            entity_id=entity_id,
            start_date=start_date,
            event_types=[event_type]
        )
        
        return {
            'met': len(events) == 0,
            'events_found': len(events),
            'time_window_days': days,
        }
    
    def _check_event_presence(
        self,
        entity_id: UUID,
        condition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check that an event type is present."""
        event_type = condition.get('event_type')
        count_requirement = condition.get('count', '>= 1')
        
        events = self.failure_service.get_program_events(
            entity_id=entity_id,
            event_types=[event_type]
        )
        
        # Parse count requirement (e.g., ">= 2", "== 1", "> 0")
        count_met = self._check_count_requirement(len(events), count_requirement)
        
        return {
            'met': count_met,
            'events_found': len(events),
            'count_requirement': count_requirement,
        }
    
    def _check_event_count(
        self,
        entity_id: UUID,
        condition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check event count in a time window."""
        event_type = condition.get('event_type')
        time_window = condition.get('time_window', '6 months')
        count_requirement = condition.get('count', '>= 1')
        
        days = self._parse_time_window(time_window)
        start_date = date.today() - timedelta(days=days)
        
        events = self.failure_service.get_program_events(
            entity_id=entity_id,
            start_date=start_date,
            event_types=[event_type]
        )
        
        count_met = self._check_count_requirement(len(events), count_requirement)
        
        return {
            'met': count_met,
            'events_found': len(events),
            'time_window_days': days,
            'count_requirement': count_requirement,
        }
    
    def _parse_time_window(self, time_window: str) -> int:
        """Parse time window string to days."""
        try:
            # Simple parser for "6 months", "30 days", "1 year", etc.
            parts = time_window.lower().split()
            if len(parts) != 2:
                logger.warning(f"Invalid time window format: {time_window}, defaulting to 180 days")
                return 180  # Default to 6 months
            
            try:
                number = int(parts[0])
            except ValueError:
                logger.warning(f"Invalid number in time window: {time_window}, defaulting to 180 days")
                return 180
            
            unit = parts[1]
            
            if 'day' in unit:
                return number
            elif 'week' in unit:
                return number * 7
            elif 'month' in unit:
                return number * 30
            elif 'year' in unit:
                return number * 365
            else:
                logger.warning(f"Unknown time unit in time window: {time_window}, defaulting to 180 days")
                return 180  # Default
        except Exception as e:
            logger.error(f"Error parsing time window '{time_window}': {e}", exc_info=True)
            return 180  # Safe default
    
    def _check_count_requirement(self, count: int, requirement: str) -> bool:
        """Check if count meets requirement (e.g., ">= 2", "== 1")."""
        # Parse requirement
        if '>=' in requirement:
            threshold = int(requirement.replace('>=', '').strip())
            return count >= threshold
        elif '<=' in requirement:
            threshold = int(requirement.replace('<=', '').strip())
            return count <= threshold
        elif '==' in requirement or '=' in requirement:
            threshold = int(requirement.replace('==', '').replace('=', '').strip())
            return count == threshold
        elif '>' in requirement:
            threshold = int(requirement.replace('>', '').strip())
            return count > threshold
        elif '<' in requirement:
            threshold = int(requirement.replace('<', '').strip())
            return count < threshold
        else:
            return count >= 1  # Default
    
    def _check_relationship_requirement(
        self,
        entity_id: UUID,
        requirement: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check a relationship requirement against an entity."""
        try:
            relationship_type = requirement.get('relationship_type')
            min_count = requirement.get('min_count', 1)
            
            count = 0
            
            if relationship_type == 'investigator':
                # Check for trial-institution relationships
                from database.models.relationships import TrialSponsor
                from database.models.entities import Institution
                
                # If entity is a trial, check for investigator institutions
                from database.models.clinical import ClinicalTrial
                trial = self.session.query(ClinicalTrial).filter(
                    ClinicalTrial.trial_id == entity_id,
                    ClinicalTrial.deleted_at.is_(None)
                ).first()
                
                if trial:
                    sponsors = self.session.query(TrialSponsor).filter(
                        TrialSponsor.trial_id == entity_id,
                        TrialSponsor.entity_type == 'institution',
                        TrialSponsor.deleted_at.is_(None)
                    ).count()
                    count = sponsors
            
            elif relationship_type == 'sponsor':
                # Check for company-trial or company-drug relationships
                from database.models.relationships import TrialSponsor, CompanyDrug
                
                # If entity is a trial
                from database.models.clinical import ClinicalTrial
                trial = self.session.query(ClinicalTrial).filter(
                    ClinicalTrial.trial_id == entity_id,
                    ClinicalTrial.deleted_at.is_(None)
                ).first()
                
                if trial:
                    sponsors = self.session.query(TrialSponsor).filter(
                        TrialSponsor.trial_id == entity_id,
                        TrialSponsor.entity_type == 'company',
                        TrialSponsor.deleted_at.is_(None)
                    ).count()
                    count = sponsors
                else:
                    # If entity is a drug
                    from database.models.entities import Drug
                    drug = self.session.query(Drug).filter(
                        Drug.drug_id == entity_id,
                        Drug.deleted_at.is_(None)
                    ).first()
                    
                    if drug:
                        companies = self.session.query(CompanyDrug).filter(
                            CompanyDrug.drug_id == entity_id,
                            CompanyDrug.deleted_at.is_(None)
                        ).count()
                        count = companies
            
            elif relationship_type == 'indication':
                # Check for drug-disease relationships
                from database.models.relationships import DrugIndication
                from database.models.entities import Drug
                
                drug = self.session.query(Drug).filter(
                    Drug.drug_id == entity_id,
                    Drug.deleted_at.is_(None)
                ).first()
                
                if drug:
                    indications = self.session.query(DrugIndication).filter(
                        DrugIndication.drug_id == entity_id,
                        DrugIndication.deleted_at.is_(None)
                    ).count()
                    count = indications
            
            return {
                'met': count >= min_count,
                'count': count,
                'min_required': min_count,
            }
            
        except Exception as e:
            logger.error(f"Error checking relationship requirement: {e}", exc_info=True)
            return {
                'met': False,
                'error': str(e)
            }

