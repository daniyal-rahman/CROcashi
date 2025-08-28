"""
Document queue management for literature processing.

This module implements the trial priority queue system that manages which trials
should be processed next based on their priority scores and available documents.
"""

import logging
import heapq
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)


class TrialStatus(Enum):
    """Trial processing status."""
    ACTIVE = "active"
    READY_FOR_EVALUATION = "ready_for_evaluation"  # Add missing status for LLM evaluation
    STOPPED = "stopped"  # Add missing status for stopped trials
    PROMOTED = "promoted"  # Add missing status for promoted trials
    PARKED = "parked"
    COMPLETE = "complete"
    FAILED = "failed"
    REVIEW = "review"


@dataclass
class TrialQueueEntry:
    """Entry in the trial priority queue."""
    trial_id: str
    priority_score: float
    last_updated: datetime
    status: TrialStatus
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        """For heapq comparison - higher priority comes first."""
        return self.priority_score > other.priority_score


@dataclass
class DocumentCandidate:
    """Document candidate for processing."""
    doc_id: str
    trial_id: str
    source_type: str  # 'pubmed', 'conference', 'pr', 'sec', etc.
    u0_score: float
    u1_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Ensure metadata is initialized."""
        if self.metadata is None:
            self.metadata = {}


class DocumentQueue:
    """
    Manages the priority queue for trial processing and document candidates.
    
    This class implements the global queue re-prioritization system from the
    pruning strategy, where trials bubble up/down based on:
    - Time to catalyst
    - P(short) * uncertainty
    - Next document utility
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the document queue.
        
        Args:
            config: Configuration dictionary with queue parameters
        """
        self.config = config
        
        # Queue configuration
        self.max_trials_per_batch = config.get('max_trials_per_batch', 10)
        self.max_candidates_per_trial = config.get('max_candidates_per_trial', 20)
        self.parking_duration_days = config.get('parking_duration_days', 90)
        self.review_sample_rate = config.get('review_sample_rate', 0.05)
        
        # Internal state
        self._trial_queue: List[TrialQueueEntry] = []
        self._trial_candidates: Dict[str, List[DocumentCandidate]] = {}
        self._trial_status: Dict[str, TrialStatus] = {}
        self._trial_metadata: Dict[str, Dict[str, Any]] = {}
        self._parked_trials: Dict[str, datetime] = {}
        
        # Statistics
        self.stats = {
            'trials_processed': 0,
            'trials_parked': 0,
            'trials_completed': 0,
            'candidates_added': 0,
            'priority_updates': 0
        }
        
        logger.info("Document queue initialized with config: %s", config)
    
    def add_trial_candidates(self, trial_id: str, 
                           candidates: List[DocumentCandidate]) -> None:
        """
        Add document candidates for a trial.
        
        Args:
            trial_id: Trial identifier
            candidates: List of document candidates
        """
        if trial_id not in self._trial_candidates:
            self._trial_candidates[trial_id] = []
        
        # Add new candidates
        for candidate in candidates:
            if candidate.doc_id not in [c.doc_id for c in self._trial_candidates[trial_id]]:
                self._trial_candidates[trial_id].append(candidate)
                self.stats['candidates_added'] += 1
        
        # Sort candidates by U0 score (descending)
        self._trial_candidates[trial_id].sort(
            key=lambda x: x.u0_score, reverse=True
        )
        
        # Limit candidates per trial
        if len(self._trial_candidates[trial_id]) > self.max_candidates_per_trial:
            self._trial_candidates[trial_id] = self._trial_candidates[trial_id][:self.max_candidates_per_trial]
        
        # Update trial metadata with candidate information
        if trial_id not in self._trial_metadata:
            self._trial_metadata[trial_id] = {}
        
        self._trial_metadata[trial_id].update({
            'total_candidates': len(self._trial_candidates[trial_id]),
            'max_u0_score': max(c.u0_score for c in self._trial_candidates[trial_id]) if candidates else 0.0,
            'last_candidate_update': datetime.now()
        })
        
        # Ensure trial is in the queue
        if trial_id not in self._trial_status:
            self._trial_status[trial_id] = TrialStatus.ACTIVE
            self._add_trial_to_queue(trial_id)
        
        logger.debug("Added %d candidates for trial %s", len(candidates), trial_id)
    
    def update_trial_candidates(self, trial_id: str, candidates: List[DocumentCandidate]) -> None:
        """
        Update the candidates for a specific trial with Stage B results.
        
        Args:
            trial_id: Trial identifier
            candidates: List of updated document candidates with Stage B results
        """
        if trial_id not in self._trial_candidates:
            self._trial_candidates[trial_id] = []
        
        # Update existing candidates or add new ones
        existing_doc_ids = {c.doc_id for c in self._trial_candidates[trial_id]}
        
        for candidate in candidates:
            if candidate.doc_id in existing_doc_ids:
                # Update existing candidate
                for existing in self._trial_candidates[trial_id]:
                    if existing.doc_id == candidate.doc_id:
                        # Update with Stage B results
                        existing.u1_score = getattr(candidate, 'u1_score', None)
                        existing.abstract = getattr(candidate, 'abstract', None)
                        existing.stage_b_completed = getattr(candidate, 'stage_b_completed', False)
                        existing.stage_b_result = getattr(candidate, 'stage_b_result', None)
                        break
            else:
                # Add new candidate
                self._trial_candidates[trial_id].append(candidate)
        
        logger.info(f"Updated trial {trial_id} with {len(candidates)} Stage B candidates")
        
        # Update trial status to READY_FOR_EVALUATION if we have Stage B results
        if any(getattr(c, 'stage_b_completed', False) for c in self._trial_candidates[trial_id]):
            self.update_trial_status(trial_id, TrialStatus.READY_FOR_EVALUATION)
            logger.info(f"Trial {trial_id} status updated to READY_FOR_EVALUATION after Stage B completion")
    
    def get_next_trial_batch(self, batch_size: Optional[int] = None) -> List[str]:
        """
        Get the next batch of trials to process.
        
        Args:
            batch_size: Number of trials to return, uses config default if None
            
        Returns:
            List of trial IDs to process next
        """
        batch_size = batch_size or self.max_trials_per_batch
        
        # Process parked trials that are ready for review
        self._process_parked_trials()
        
        # Get active trials from the priority queue
        active_trials = []
        for entry in self._trial_queue:
            if entry.status == TrialStatus.ACTIVE and len(active_trials) < batch_size:
                active_trials.append(entry.trial_id)
        
        # If we don't have enough active trials, check for trials that need review
        if len(active_trials) < batch_size:
            review_trials = self._get_trials_needing_review(batch_size - len(active_trials))
            active_trials.extend(review_trials)
        
        logger.info("Returning batch of %d trials for processing", len(active_trials))
        return active_trials
    
    def update_trial_priority(self, trial_id: str, new_priority: float) -> None:
        """
        Update the priority score for a trial.
        
        Args:
            trial_id: Trial identifier
            new_priority: New priority score (0.0 to 1.0)
        """
        # Find the trial in the queue
        for entry in self._trial_queue:
            if entry.trial_id == trial_id:
                old_priority = entry.priority_score
                entry.priority_score = max(0.0, min(1.0, new_priority))
                entry.last_updated = datetime.now()
                
                # Update metadata
                if trial_id in self._trial_metadata:
                    self._trial_metadata[trial_id]['priority_score'] = new_priority
                    self._trial_metadata[trial_id]['last_priority_update'] = datetime.now()
                
                # Re-heapify the queue
                heapq.heapify(self._trial_queue)
                
                self.stats['priority_updates'] += 1
                logger.debug("Updated priority for trial %s: %.3f -> %.3f", 
                           trial_id, old_priority, new_priority)
                return
        
        # If trial not found, add it to the queue
        logger.warning("Trial %s not found in queue, adding with priority %.3f", 
                      trial_id, new_priority)
        self._add_trial_to_queue(trial_id, new_priority)
    
    def mark_trial_complete(self, trial_id: str, status: TrialStatus) -> None:
        """
        Mark a trial as complete or change its status.
        
        Args:
            trial_id: Trial identifier
            status: New status for the trial
        """
        if status == TrialStatus.COMPLETE:
            self.stats['trials_completed'] += 1
            logger.info("Marking trial %s as complete", trial_id)
        elif status == TrialStatus.PARKED:
            self.stats['trials_parked'] += 1
            self._parked_trials[trial_id] = datetime.now()
            logger.info("Parking trial %s for %d days", trial_id, self.parking_duration_days)
        elif status == TrialStatus.FAILED:
            logger.warning("Marking trial %s as failed", trial_id)
        
        # Update trial status
        self._trial_status[trial_id] = status
        
        # Update queue entry if it exists
        for entry in self._trial_queue:
            if entry.trial_id == trial_id:
                entry.status = status
                break
        
        # Remove from active queue if not active
        if status != TrialStatus.ACTIVE:
            self._trial_queue = [e for e in self._trial_queue if e.trial_id != trial_id]
            heapq.heapify(self._trial_queue)
    
    def get_trial_candidates(self, trial_id: str) -> List[DocumentCandidate]:
        """
        Get all candidates for a specific trial.
        
        Args:
            trial_id: Trial identifier
            
        Returns:
            List of document candidates
        """
        candidates = self._trial_candidates.get(trial_id, [])
        logger.info(f"🔍 DOCUMENT QUEUE: get_trial_candidates({trial_id}) returned {len(candidates)} candidates")
        
        # Log first few candidates for debugging
        for i, candidate in enumerate(candidates[:3]):
            logger.info(f"🔍 DOCUMENT QUEUE: Candidate {i+1}: doc_id={candidate.doc_id}, u0={candidate.u0_score}, u1={getattr(candidate, 'u1_score', 'N/A')}")
        
        return candidates
    
    def get_trial_status(self, trial_id: str) -> Optional[TrialStatus]:
        """
        Get the current status of a trial.
        
        Args:
            trial_id: Trial identifier
            
        Returns:
            Trial status or None if not found
        """
        return self._trial_status.get(trial_id)
    
    def update_trial_status(self, trial_id: str, status: TrialStatus) -> None:
        """
        Update the status of a trial.
        
        Args:
            trial_id: Trial identifier
            status: New status for the trial
        """
        self._trial_status[trial_id] = status
        logger.debug(f"Updated trial {trial_id} status to {status.value}")
        
        # If setting to READY_FOR_EVALUATION, ensure trial is in queue
        if status == TrialStatus.READY_FOR_EVALUATION:
            # Check if trial is already in queue
            in_queue = any(entry.trial_id == trial_id for entry in self._trial_queue)
            if not in_queue:
                self._add_trial_to_queue(trial_id, priority=0.8)  # High priority for evaluation
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the queue.
        
        Returns:
            Dictionary with queue statistics
        """
        active_count = sum(1 for e in self._trial_queue if e.status == TrialStatus.ACTIVE)
        parked_count = len(self._parked_trials)
        total_candidates = sum(len(candidates) for candidates in self._trial_candidates.values())
        
        return {
            **self.stats,
            'queue_size': len(self._trial_queue),
            'active_trials': active_count,
            'parked_trials': parked_count,
            'total_candidates': total_candidates,
            'trials_with_candidates': len(self._trial_candidates)
        }
    
    def _add_trial_to_queue(self, trial_id: str, priority: float = 0.5) -> None:
        """Add a trial to the priority queue."""
        entry = TrialQueueEntry(
            trial_id=trial_id,
            priority_score=priority,
            last_updated=datetime.now(),
            status=TrialStatus.ACTIVE,
            metadata=self._trial_metadata.get(trial_id, {})
        )
        
        heapq.heappush(self._trial_queue, entry)
        logger.debug("Added trial %s to queue with priority %.3f", trial_id, priority)
    
    def _process_parked_trials(self) -> None:
        """Process parked trials that are ready for review."""
        current_time = datetime.now()
        ready_for_review = []
        
        for trial_id, parked_time in self._parked_trials.items():
            if current_time - parked_time >= timedelta(days=self.parking_duration_days):
                ready_for_review.append(trial_id)
        
        for trial_id in ready_for_review:
            # Sample based on review rate
            if self._should_review_trial(trial_id):
                self._trial_status[trial_id] = TrialStatus.REVIEW
                self._add_trial_to_queue(trial_id, priority=0.3)  # Lower priority for review
                logger.info("Trial %s ready for review after parking", trial_id)
            else:
                # Keep parked
                self._parked_trials[trial_id] = current_time  # Reset timer
        
        # Remove processed trials from parked list
        for trial_id in ready_for_review:
            del self._parked_trials[trial_id]
    
    def _should_review_trial(self, trial_id: str) -> bool:
        """Determine if a parked trial should be reviewed."""
        import random
        return random.random() < self.review_sample_rate
    
    def _get_trials_needing_review(self, count: int) -> List[str]:
        """Get trials that need review."""
        review_trials = [
            trial_id for trial_id, status in self._trial_status.items()
            if status == TrialStatus.REVIEW
        ]
        return review_trials[:count]
    
    def export_queue_state(self) -> Dict[str, Any]:
        """Export the current queue state for debugging/monitoring."""
        return {
            'queue_entries': [
                {
                    'trial_id': entry.trial_id,
                    'priority_score': entry.priority_score,
                    'status': entry.status.value,
                    'last_updated': entry.last_updated.isoformat(),
                    'metadata': entry.metadata
                }
                for entry in self._trial_queue
            ],
            'trial_candidates': {
                trial_id: [
                    {
                        'doc_id': c.doc_id,
                        'u0_score': c.u0_score,
                        'u1_score': c.u1_score,
                        'source_type': c.source_type,
                        'created_at': c.created_at.isoformat()
                    }
                    for c in candidates
                ]
                for trial_id, candidates in self._trial_candidates.items()
            },
            'trial_status': {
                trial_id: status.value for trial_id, status in self._trial_status.items()
            },
            'parked_trials': {
                trial_id: parked_time.isoformat()
                for trial_id, parked_time in self._parked_trials.items()
            },
            'stats': self.get_queue_stats()
        }
