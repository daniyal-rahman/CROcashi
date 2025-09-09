"""
Queue service for task management using the tasks table.

Handles task enqueueing, leasing, completion, and failure tracking.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import text

from ...db.models import Task
from ...db.session import session_scope

logger = logging.getLogger(__name__)


class TaskQueueService:
    """Service for managing tasks in the priority queue."""
    
    def __init__(self, worker_id: str = "default_worker"):
        """Initialize the queue service."""
        self.logger = logger
        self.worker_id = worker_id
    
    def enqueue_task(
        self,
        task_type: str,
        task_key: str,
        priority: float,
        payload: Dict[str, Any],
        trial_id: Optional[int] = None,
        company_id: Optional[int] = None
    ) -> bool:
        """
        Enqueue a new task.
        
        Args:
            task_type: Type of task (e.g., 'PUBMED_U1', 'PUBMED_OA', 'STUDYCARD')
            task_key: Unique key for idempotency (e.g., 'trial:123:U1')
            priority: Task priority (higher = more important)
            payload: Task-specific data
            trial_id: Optional trial ID
            company_id: Optional company ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                # Check if task already exists
                existing = session.query(Task).filter(
                    Task.task_type == task_type,
                    Task.task_key == task_key
                ).first()
                
                if existing:
                    # Update existing task
                    existing.priority = priority
                    existing.payload = payload
                    existing.trial_id = trial_id
                    existing.company_id = company_id
                    existing.status = 'queued'
                    existing.leased_by = None
                    existing.leased_until = None
                    existing.attempts = 0
                    existing.updated_at = datetime.now(timezone.utc)
                    self.logger.debug(f"Updated existing task {task_type}:{task_key}")
                else:
                    # Create new task
                    task = Task(
                        task_type=task_type,
                        task_key=task_key,
                        trial_id=trial_id,
                        company_id=company_id,
                        priority=priority,
                        status='queued',
                        payload=payload,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    session.add(task)
                    self.logger.debug(f"Created new task {task_type}:{task_key}")
                
                return True
                
        except (IntegrityError, SQLAlchemyError) as e:
            self.logger.error(f"Database error enqueueing task {task_type}:{task_key}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error enqueueing task {task_type}:{task_key}: {e}")
            return False
    
    def lease_next(
        self,
        task_types: List[str],
        lease_seconds: int = 600
    ) -> Optional[Dict[str, Any]]:
        """
        Lease the next available task.
        
        Args:
            task_types: List of task types to consider
            lease_seconds: Lease duration in seconds
            
        Returns:
            Task data if successful, None if no tasks available
        """
        try:
            with session_scope() as session:
                # Use FOR UPDATE SKIP LOCKED to avoid conflicts
                task = session.query(Task).filter(
                    Task.task_type.in_(task_types),
                    Task.status == 'queued'
                ).order_by(
                    Task.priority.desc(),
                    Task.created_at.asc()
                ).with_for_update(skip_locked=True).first()
                
                if not task:
                    return None
                
                # Lease the task
                lease_until = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
                task.status = 'leased'
                task.leased_by = self.worker_id
                task.leased_until = lease_until
                task.updated_at = datetime.now(timezone.utc)
                
                self.logger.debug(f"Leased task {task.task_type}:{task.task_key} until {lease_until}")
                
                return {
                    'id': task.id,
                    'task_type': task.task_type,
                    'task_key': task.task_key,
                    'trial_id': task.trial_id,
                    'company_id': task.company_id,
                    'priority': task.priority,
                    'payload': task.payload,
                    'attempts': task.attempts,
                    'leased_until': lease_until.isoformat()
                }
                
        except (IntegrityError, SQLAlchemyError) as e:
            self.logger.error(f"Database error leasing task: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error leasing task: {e}")
            return None
    
    def complete_task(self, task_id: int) -> bool:
        """
        Mark a task as completed.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                task = session.query(Task).filter(Task.id == task_id).first()
                if not task:
                    self.logger.warning(f"Task {task_id} not found")
                    return False
                
                task.status = 'done'
                task.leased_by = None
                task.leased_until = None
                task.updated_at = datetime.now(timezone.utc)
                
                self.logger.debug(f"Completed task {task_id}")
                return True
                
        except (IntegrityError, SQLAlchemyError) as e:
            self.logger.error(f"Database error completing task {task_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error completing task {task_id}: {e}")
            return False
    
    def fail_task(self, task_id: int, reason: str) -> bool:
        """
        Mark a task as failed.
        
        Args:
            task_id: Task ID
            reason: Failure reason
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                task = session.query(Task).filter(Task.id == task_id).first()
                if not task:
                    self.logger.warning(f"Task {task_id} not found")
                    return False
                
                task.status = 'failed'
                task.leased_by = None
                task.leased_until = None
                task.attempts += 1
                task.updated_at = datetime.now(timezone.utc)
                
                # Add failure reason to payload
                if task.payload is None:
                    task.payload = {}
                task.payload['failure_reason'] = reason
                task.payload['failed_at'] = datetime.now(timezone.utc).isoformat()
                
                self.logger.debug(f"Failed task {task_id}: {reason}")
                return True
                
        except (IntegrityError, SQLAlchemyError) as e:
            self.logger.error(f"Database error failing task {task_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error failing task {task_id}: {e}")
            return False
    
    def park_task(self, task_id: int, reason: str) -> bool:
        """
        Park a task (temporarily remove from queue).
        
        Args:
            task_id: Task ID
            reason: Parking reason
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                task = session.query(Task).filter(Task.id == task_id).first()
                if not task:
                    self.logger.warning(f"Task {task_id} not found")
                    return False
                
                task.status = 'parked'
                task.leased_by = None
                task.leased_until = None
                task.updated_at = datetime.now(timezone.utc)
                
                # Add parking reason to payload
                if task.payload is None:
                    task.payload = {}
                task.payload['parked_reason'] = reason
                task.payload['parked_at'] = datetime.now(timezone.utc).isoformat()
                
                self.logger.debug(f"Parked task {task_id}: {reason}")
                return True
                
        except (IntegrityError, SQLAlchemyError) as e:
            self.logger.error(f"Database error parking task {task_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error parking task {task_id}: {e}")
            return False
    
    def cancel_task(self, task_id: int, reason: str) -> bool:
        """
        Cancel a task.
        
        Args:
            task_id: Task ID
            reason: Cancellation reason
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                task = session.query(Task).filter(Task.id == task_id).first()
                if not task:
                    self.logger.warning(f"Task {task_id} not found")
                    return False
                
                task.status = 'canceled'
                task.leased_by = None
                task.leased_until = None
                task.updated_at = datetime.now(timezone.utc)
                
                # Add cancellation reason to payload
                if task.payload is None:
                    task.payload = {}
                task.payload['canceled_reason'] = reason
                task.payload['canceled_at'] = datetime.now(timezone.utc).isoformat()
                
                self.logger.debug(f"Canceled task {task_id}: {reason}")
                return True
                
        except (IntegrityError, SQLAlchemyError) as e:
            self.logger.error(f"Database error canceling task {task_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error canceling task {task_id}: {e}")
            return False
    
    def get_queue_stats(self, task_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get queue statistics.
        
        Args:
            task_types: Optional list of task types to filter by
            
        Returns:
            Queue statistics
        """
        try:
            with session_scope() as session:
                query = session.query(Task)
                if task_types:
                    query = query.filter(Task.task_type.in_(task_types))
                
                stats = {
                    'total': query.count(),
                    'queued': query.filter(Task.status == 'queued').count(),
                    'leased': query.filter(Task.status == 'leased').count(),
                    'done': query.filter(Task.status == 'done').count(),
                    'failed': query.filter(Task.status == 'failed').count(),
                    'parked': query.filter(Task.status == 'parked').count(),
                    'canceled': query.filter(Task.status == 'canceled').count()
                }
                
                return stats
                
        except Exception as e:
            self.logger.error(f"Error getting queue stats: {e}")
            return {}
    
    def cleanup_expired_leases(self) -> int:
        """
        Clean up expired leases (mark as queued again).
        
        Returns:
            Number of leases cleaned up
        """
        try:
            with session_scope() as session:
                now = datetime.now(timezone.utc)
                
                # Find expired leases
                expired_tasks = session.query(Task).filter(
                    Task.status == 'leased',
                    Task.leased_until < now
                ).all()
                
                count = 0
                for task in expired_tasks:
                    task.status = 'queued'
                    task.leased_by = None
                    task.leased_until = None
                    task.updated_at = now
                    count += 1
                
                if count > 0:
                    self.logger.info(f"Cleaned up {count} expired leases")
                
                return count
                
        except Exception as e:
            self.logger.error(f"Error cleaning up expired leases: {e}")
            return 0
