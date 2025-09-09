"""
Priority computation service for task prioritization.

Implements the unified priority calculation formula for all task types.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PriorityComponents:
    """Components of priority calculation for audit."""
    best_s_rge2: float
    uncertainty: float
    n_docs_selected: int
    time_to_catalyst: Optional[float]
    company_pressure: float
    final_priority: float


class PriorityService:
    """Service for computing task priorities."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize priority service.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Priority weights (from the specification)
        self.best_s_weight = self.config.get('best_s_weight', 0.55)
        self.time_weight = self.config.get('time_weight', 0.25)
        self.uncertainty_weight = self.config.get('uncertainty_weight', 0.15)
        self.company_pressure_weight = self.config.get('company_pressure_weight', 0.05)
        
        # Time decay parameters
        self.catalyst_decay_days = self.config.get('catalyst_decay_days', 120)
        
        self.logger = logger
    
    def calculate_task_priority(
        self,
        task_type: str,
        trial_id: int,
        trial_data: Dict[str, Any],
        company_data: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Calculate priority for a task using the unified formula.
        
        Formula: priority = 0.55*best_s_rge2 + 0.25*exp(-time_to_catalyst/120) + 0.15*uncertainty + 0.05*company_pressure
        
        Args:
            task_type: Type of task (PUBMED_U1, PUBMED_OA, STUDYCARD)
            trial_id: Trial ID
            trial_data: Trial literature state and metadata
            company_data: Optional company-specific data
            
        Returns:
            Priority score (higher = more important)
        """
        try:
            # Extract components
            best_s_rge2 = trial_data.get('best_S_Rge2', 0.0)
            uncertainty = trial_data.get('uncertainty', 0.0)
            n_docs_selected = trial_data.get('n_docs_selected', 0)
            
            # Calculate time to catalyst
            time_to_catalyst = self._calculate_time_to_catalyst(trial_data)
            time_weight = self._calculate_time_weight(time_to_catalyst)
            
            # Calculate company pressure
            company_pressure = self._calculate_company_pressure(company_data)
            
            # Apply task-specific adjustments
            task_adjustment = self._get_task_adjustment(task_type, trial_data)
            
            # Calculate final priority
            priority = (
                self.best_s_weight * best_s_rge2 +
                self.time_weight * time_weight +
                self.uncertainty_weight * uncertainty +
                self.company_pressure_weight * company_pressure +
                task_adjustment
            )
            
            # Add trial ID for deterministic ordering (small contribution)
            priority += trial_id / 1000000.0
            
            # Log components for audit
            components = PriorityComponents(
                best_s_rge2=best_s_rge2,
                uncertainty=uncertainty,
                n_docs_selected=n_docs_selected,
                time_to_catalyst=time_to_catalyst,
                company_pressure=company_pressure,
                final_priority=priority
            )
            
            self.logger.debug(f"Priority calculation for trial {trial_id}, task {task_type}: {components}")
            
            return priority
            
        except Exception as e:
            self.logger.error(f"Error calculating priority for trial {trial_id}: {e}")
            # Return default priority based on trial ID
            return trial_id / 1000000.0
    
    def _calculate_time_to_catalyst(self, trial_data: Dict[str, Any]) -> Optional[float]:
        """
        Calculate time to next catalyst event.
        
        Args:
            trial_data: Trial data
            
        Returns:
            Time to catalyst in days, or None if unknown
        """
        try:
            # Try to get catalyst date from trial data
            catalyst_date = trial_data.get('catalyst_date')
            if catalyst_date:
                if isinstance(catalyst_date, str):
                    catalyst_date = datetime.fromisoformat(catalyst_date.replace('Z', '+00:00'))
                elif isinstance(catalyst_date, datetime):
                    pass
                else:
                    return None
                
                now = datetime.now(timezone.utc)
                time_diff = (catalyst_date - now).total_seconds() / (24 * 3600)  # Convert to days
                return max(0, time_diff)  # Don't return negative values
            
            # Fallback: estimate based on trial phase and status
            phase = trial_data.get('phase', '').lower()
            status = trial_data.get('status', '').lower()
            
            if 'recruiting' in status:
                return 90.0  # 3 months for recruiting trials
            elif 'active' in status:
                return 180.0  # 6 months for active trials
            elif 'completed' in status:
                return 30.0  # 1 month for completed trials (results soon)
            elif phase in ['phase_1', 'phase_i']:
                return 120.0  # 4 months for Phase I
            elif phase in ['phase_2', 'phase_ii']:
                return 150.0  # 5 months for Phase II
            elif phase in ['phase_3', 'phase_iii']:
                return 180.0  # 6 months for Phase III
            
            return 120.0  # Default 4 months
            
        except Exception as e:
            self.logger.warning(f"Failed to calculate time to catalyst: {e}")
            return None
    
    def _calculate_time_weight(self, time_to_catalyst: Optional[float]) -> float:
        """
        Calculate time weight using exponential decay.
        
        Args:
            time_to_catalyst: Time to catalyst in days
            
        Returns:
            Time weight (0-1)
        """
        if time_to_catalyst is None:
            return 0.5  # Default moderate weight
        
        # Exponential decay: exp(-time_to_catalyst/120)
        import math
        return math.exp(-time_to_catalyst / self.catalyst_decay_days)
    
    def _calculate_company_pressure(self, company_data: Optional[Dict[str, Any]]) -> float:
        """
        Calculate company pressure factor.
        
        Args:
            company_data: Company-specific data
            
        Returns:
            Company pressure (0-1)
        """
        if not company_data:
            return 0.0
        
        try:
            # Factors that increase company pressure
            pressure = 0.0
            
            # Market cap (larger companies get higher priority)
            market_cap = company_data.get('market_cap', 0)
            if market_cap > 0:
                # Log scale: log10(market_cap) / 10, capped at 1.0
                import math
                pressure += min(math.log10(market_cap) / 10, 1.0)
            
            # Recent news/events
            recent_events = company_data.get('recent_events', 0)
            pressure += min(recent_events / 10, 0.5)  # Cap at 0.5
            
            # Analyst coverage
            analyst_coverage = company_data.get('analyst_coverage', 0)
            pressure += min(analyst_coverage / 20, 0.3)  # Cap at 0.3
            
            return min(pressure, 1.0)  # Cap at 1.0
            
        except Exception as e:
            self.logger.warning(f"Failed to calculate company pressure: {e}")
            return 0.0
    
    def _get_task_adjustment(self, task_type: str, trial_data: Dict[str, Any]) -> float:
        """
        Get task-specific priority adjustment.
        
        Args:
            task_type: Type of task
            trial_data: Trial data
            
        Returns:
            Task adjustment factor
        """
        # Base adjustments by task type
        adjustments = {
            'PUBMED_U1': 0.0,      # Base priority
            'PUBMED_OA': 0.1,      # Slightly higher (full text is valuable)
            'STUDYCARD': 0.2,      # Highest (final output)
            'CTGOV_ENRICH': -0.1,  # Lower (data collection)
            'SEC_SCAN': -0.1       # Lower (data collection)
        }
        
        base_adjustment = adjustments.get(task_type, 0.0)
        
        # Additional adjustments based on trial state
        n_docs_selected = trial_data.get('n_docs_selected', 0)
        if n_docs_selected > 0:
            # More documents = higher priority for processing stages
            if task_type in ['PUBMED_OA', 'STUDYCARD']:
                base_adjustment += min(n_docs_selected / 20, 0.1)  # Cap at 0.1
        
        return base_adjustment
    
    def recalculate_priorities(self, task_type: str) -> int:
        """
        Recalculate priorities for all tasks of a given type.
        
        Args:
            task_type: Type of tasks to recalculate
            
        Returns:
            Number of tasks updated
        """
        try:
            from .queue_service import TaskQueueService
            from .db_service import PubMedDBService
            from ...db.session import session_scope
            from ...db.models import TrialLitState, Trial
            
            queue_service = TaskQueueService()
            db_service = PubMedDBService()
            
            updated_count = 0
            
            with session_scope() as session:
                # Get all tasks of this type
                tasks = session.query(Task).filter(Task.task_type == task_type).all()
                
                for task in tasks:
                    if not task.trial_id:
                        continue
                    
                    # Get trial literature state
                    lit_state = session.query(TrialLitState).filter(
                        TrialLitState.trial_id == task.trial_id
                    ).first()
                    
                    if not lit_state:
                        continue
                    
                    # Get trial data
                    trial = session.query(Trial).filter(
                        Trial.trial_id == task.trial_id
                    ).first()
                    
                    if not trial:
                        continue
                    
                    # Prepare trial data
                    trial_data = {
                        'best_S_Rge2': float(lit_state.best_S_Rge2) if lit_state.best_S_Rge2 else 0.0,
                        'uncertainty': float(lit_state.uncertainty) if lit_state.uncertainty else 0.0,
                        'n_docs_selected': lit_state.n_docs_selected or 0,
                        'phase': trial.phase,
                        'status': trial.status,
                        'catalyst_date': trial.catalyst_date
                    }
                    
                    # Calculate new priority
                    new_priority = self.calculate_task_priority(
                        task_type, task.trial_id, trial_data
                    )
                    
                    # Update task priority
                    task.priority = new_priority
                    updated_count += 1
            
            self.logger.info(f"Recalculated priorities for {updated_count} {task_type} tasks")
            return updated_count
            
        except Exception as e:
            self.logger.error(f"Error recalculating priorities for {task_type}: {e}")
            return 0
