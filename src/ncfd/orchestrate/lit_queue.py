"""
Literature queue management for PubMed literature processing.

Handles global trial queue management, prioritization policies, and periodic reprioritization.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TrialQueueItem:
    """Trial item in the literature queue."""
    trial_id: str
    nct_id: Optional[str]
    asset: str
    indication: str
    best_S_Rge2: float
    time_to_catalyst: Optional[float]  # Days to catalyst
    uncertainty: float
    max_expected_utility: float
    priority: float
    status: str  # active, stopped, parked, promoted
    added_at: datetime
    last_updated: datetime


class LiteratureQueue:
    """Global trial queue management for PubMed literature processing."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the literature queue.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.queue: List[TrialQueueItem] = []
        self.logger = logging.getLogger(__name__)
        
        # Priority weights
        self.best_s_weight = self.config.get('best_s_weight', 0.55)
        self.time_weight = self.config.get('time_weight', 0.25)
        self.uncertainty_weight = self.config.get('uncertainty_weight', 0.15)
        self.utility_weight = self.config.get('utility_weight', 0.05)
        
        # Queue settings
        self.max_queue_size = self.config.get('max_queue_size', 1000)
        self.park_after_days = self.config.get('park_after_days', 30)
        
    def add_trial(self, trial: Dict[str, Any]) -> bool:
        """
        Add a trial to the queue.
        
        Args:
            trial: Trial state dictionary
            
        Returns:
            True if added successfully, False otherwise
        """
        if len(self.queue) >= self.max_queue_size:
            self.logger.warning(f"Queue full ({len(self.queue)} items), cannot add trial {trial.get('trial_id')}")
            return False
        
        # Calculate priority
        priority = self._calculate_priority(trial)
        
        # Create queue item
        queue_item = TrialQueueItem(
            trial_id=trial.get('trial_id', 'unknown'),
            nct_id=trial.get('nct_id'),
            asset=trial.get('asset', 'unknown'),
            indication=trial.get('indication', 'unknown'),
            best_S_Rge2=trial.get('best_S_Rge2', 0.0),
            time_to_catalyst=trial.get('time_to_catalyst'),
            uncertainty=trial.get('uncertainty', 0.5),
            max_expected_utility=trial.get('max_expected_utility_next_doc', 0.1),
            priority=priority,
            status='active',
            added_at=datetime.now(),
            last_updated=datetime.now()
        )
        
        self.queue.append(queue_item)
        self.logger.info(f"Added trial {trial.get('trial_id')} to queue with priority {priority:.3f}")
        return True
    
    def get_next_trial(self) -> Optional[TrialQueueItem]:
        """
        Get the next trial from the queue.
        
        Returns:
            Next trial item or None if queue is empty
        """
        if not self.queue:
            return None
        
        # Sort by priority (highest first)
        self.queue.sort(key=lambda x: x.priority, reverse=True)
        
        # Return first active trial
        for item in self.queue:
            if item.status == 'active':
                return item
        
        return None
    
    def update_trial_status(self, trial_id: str, status: str) -> bool:
        """
        Update trial status in the queue.
        
        Args:
            trial_id: Trial ID to update
            status: New status (active, stopped, parked, promoted)
            
        Returns:
            True if updated successfully, False otherwise
        """
        for item in self.queue:
            if item.trial_id == trial_id:
                item.status = status
                item.last_updated = datetime.now()
                self.logger.info(f"Updated trial {trial_id} status to {status}")
                return True
        
        self.logger.warning(f"Trial {trial_id} not found in queue")
        return False
    
    def reprioritize_queue(self) -> None:
        """
        Reprioritize the entire queue based on current metrics.
        """
        self.logger.info("Reprioritizing literature queue")
        
        for item in self.queue:
            if item.status == 'active':
                # Recalculate priority
                item.priority = self._calculate_priority_from_item(item)
                item.last_updated = datetime.now()
        
        # Sort by priority
        self.queue.sort(key=lambda x: x.priority, reverse=True)
        
        self.logger.info(f"Queue reprioritized, {len([i for i in self.queue if i.status == 'active'])} active trials")
    
    def cleanup_parked_trials(self) -> int:
        """
        Remove trials that have been parked for too long.
        
        Returns:
            Number of trials removed
        """
        cutoff_date = datetime.now() - timedelta(days=self.park_after_days)
        initial_count = len(self.queue)
        
        self.queue = [
            item for item in self.queue 
            if not (item.status == 'parked' and item.last_updated < cutoff_date)
        ]
        
        removed_count = initial_count - len(self.queue)
        if removed_count > 0:
            self.logger.info(f"Removed {removed_count} parked trials older than {self.park_after_days} days")
        
        return removed_count
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.
        
        Returns:
            Dictionary with queue statistics
        """
        active_trials = [item for item in self.queue if item.status == 'active']
        parked_trials = [item for item in self.queue if item.status == 'parked']
        stopped_trials = [item for item in self.queue if item.status == 'stopped']
        promoted_trials = [item for item in self.queue if item.status == 'promoted']
        
        return {
            'total_trials': len(self.queue),
            'active_trials': len(active_trials),
            'parked_trials': len(parked_trials),
            'stopped_trials': len(stopped_trials),
            'promoted_trials': len(promoted_trials),
            'avg_priority': sum(item.priority for item in active_trials) / len(active_trials) if active_trials else 0.0,
            'avg_best_S_Rge2': sum(item.best_S_Rge2 for item in active_trials) / len(active_trials) if active_trials else 0.0
        }
    
    def _calculate_priority(self, trial: Dict[str, Any]) -> float:
        """
        Calculate priority for a trial.
        
        Args:
            trial: Trial state dictionary
            
        Returns:
            Priority score (0.0-1.0)
        """
        best_S_Rge2 = trial.get('best_S_Rge2', 0.0)
        time_to_catalyst = trial.get('time_to_catalyst')
        uncertainty = trial.get('uncertainty', 0.5)
        max_expected_utility = trial.get('max_expected_utility_next_doc', 0.1)
        
        # Time to catalyst weight
        if time_to_catalyst is None:
            time_weight = 0.5
        elif time_to_catalyst < 180:  # <6 months
            time_weight = 1.0
        elif time_to_catalyst < 365:  # 6-12 months
            time_weight = 0.8
        elif time_to_catalyst < 547:  # 12-18 months
            time_weight = 0.6
        else:  # >18 months
            time_weight = 0.4
        
        # Calculate priority
        priority = (
            self.best_s_weight * best_S_Rge2 +
            self.time_weight * time_weight +
            self.uncertainty_weight * uncertainty +
            self.utility_weight * max_expected_utility
        )
        
        return max(0.0, min(1.0, priority))
    
    def _calculate_priority_from_item(self, item: TrialQueueItem) -> float:
        """
        Calculate priority for a queue item.
        
        Args:
            item: Queue item
            
        Returns:
            Priority score (0.0-1.0)
        """
        # Time to catalyst weight
        if item.time_to_catalyst is None:
            time_weight = 0.5
        elif item.time_to_catalyst < 180:  # <6 months
            time_weight = 1.0
        elif item.time_to_catalyst < 365:  # 6-12 months
            time_weight = 0.8
        elif item.time_to_catalyst < 547:  # 12-18 months
            time_weight = 0.6
        else:  # >18 months
            time_weight = 0.4
        
        # Calculate priority
        priority = (
            self.best_s_weight * item.best_S_Rge2 +
            self.time_weight * time_weight +
            self.uncertainty_weight * item.uncertainty +
            self.utility_weight * item.max_expected_utility
        )
        
        return max(0.0, min(1.0, priority))
