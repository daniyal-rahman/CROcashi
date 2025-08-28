"""
Budget monitoring and cost control for the literature pipeline.

This module tracks costs across all pipeline stages and enforces
budget limits to prevent runaway spending.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import os

# Import database models
try:
    from ..db.models import CostRecord as DBCostRecord, OperationTypeEnum
except ImportError:
    # Fallback for testing or when models not available
    DBCostRecord = None
    OperationTypeEnum = None

logger = logging.getLogger(__name__)


class BudgetStatus(Enum):
    """Budget status enumeration."""
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"
    EXCEEDED = "exceeded"


class BudgetPeriod(Enum):
    """Budget period enumeration."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class CostRecord:
    """Record of a single cost transaction."""
    operation_id: str
    trial_id: str
    operation_type: str
    cost: float
    timestamp: datetime
    execution_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'operation_id': self.operation_id,
            'trial_id': self.trial_id,
            'operation_type': self.operation_type,
            'cost': self.cost,
            'timestamp': self.timestamp.isoformat(),
            'execution_id': self.execution_id,
            'metadata': self.metadata
        }


@dataclass
class BudgetSummary:
    """Summary of budget status and costs."""
    period: BudgetPeriod
    start_date: datetime
    end_date: datetime
    total_cost: float
    cost_limit: float
    remaining_budget: float
    status: BudgetStatus
    cost_breakdown: Dict[str, float] = field(default_factory=dict)
    trial_costs: Dict[str, float] = field(default_factory=dict)
    
    @property
    def utilization_percentage(self) -> float:
        """Calculate budget utilization percentage."""
        if self.cost_limit <= 0:
            return 0.0
        return (self.total_cost / self.cost_limit) * 100
    
    @property
    def is_exceeded(self) -> bool:
        """Check if budget is exceeded."""
        return self.total_cost > self.cost_limit


class BudgetMonitor:
    """
    Monitors and controls budget for the literature pipeline.
    
    Tracks costs across all operations and enforces budget limits
    to prevent runaway spending.
    """
    
    def __init__(self, config: Dict[str, Any], db_session=None):
        """
        Initialize the budget monitor.
        
        Args:
            config: Budget configuration dictionary
            db_session: Database session for persistence
        """
        self.config = config
        self.db_session = db_session
        
        # Budget limits
        self.daily_limit = config.get('daily_cost_limit', 100.0)
        self.monthly_limit = config.get('monthly_cost_limit', 2500.0)
        self.trial_limit = config.get('trial_cost_limit', 10.0)
        
        # Cost estimates per operation
        self.cost_estimates = config.get('costs', {
            'metadata_fetch': 0.001,
            'abstract_fetch': 0.01,
            'full_text_fetch': 0.50,
            'llm_evaluation': 0.05
        })
        
        # Alert thresholds
        self.alert_thresholds = config.get('alert_thresholds', {
            'warning': 0.75,
            'critical': 0.90,
            'emergency': 0.95
        })
        
        # Budget reset schedule
        self.reset_schedule = config.get('reset_schedule', 'monthly')
        self.reset_day = config.get('reset_day', 1)
        
        # Cost tracking
        self.cost_records: List[CostRecord] = []
        self.trial_costs: Dict[str, float] = {}
        self.period_costs: Dict[str, float] = {}
        
        # Budget state
        self.current_period_start = self._get_period_start()
        self.last_reset = datetime.now()
        
        # Load existing cost data if available
        self._load_cost_data()
        
        logger.info(f"Budget monitor initialized with limits: daily=${self.daily_limit}, monthly=${self.monthly_limit}")
    
    def record_cost(self, operation_id: str, trial_id: str, operation_type: str, 
                   cost: float, metadata: Optional[Dict[str, Any]] = None,
                   execution_id: Optional[str] = None) -> bool:
        """
        Record a cost for an operation.
        
        Args:
            operation_id: Unique identifier for the operation
            trial_id: Trial identifier
            operation_type: Type of operation (metadata_fetch, abstract_fetch, etc.)
            cost: Cost in USD
            metadata: Additional operation metadata
            execution_id: Execution identifier for cost tracking
            
        Returns:
            True if cost was recorded successfully, False otherwise
        """
        try:
            # Validate operation type
            valid_operation_types = ['metadata_fetch', 'abstract_fetch', 'full_text_fetch', 'llm_evaluation']
            if operation_type not in valid_operation_types:
                logger.error(f"Invalid operation type: {operation_type}")
                return False
            
            # Check if we can afford this operation
            if not self.can_afford_operation(operation_type, trial_id):
                logger.warning(f"Period cost would exceed limit: ${self._get_current_period_cost() + cost:.3f} > ${self._get_current_period_limit()}")
                return False
            
            # Record the cost in memory
            cost_record = CostRecord(
                operation_id=operation_id,
                trial_id=trial_id,
                operation_type=operation_type,
                cost=cost,
                timestamp=datetime.now(),
                execution_id=execution_id,
                metadata=metadata or {}
            )
            
            # Store in memory
            self.cost_records.append(cost_record)
            
            # Persist to database if session available and model exists
            if self.db_session and DBCostRecord:
                try:
                    # Convert operation_type to enum if available
                    db_operation_type = operation_type
                    # Note: OperationTypeEnum is a PostgreSQL enum type, not a Python enum class
                    # We can use the string values directly since they match the enum values
                    # The database will validate that the string is a valid enum value
                    
                    # Create database model instance
                    db_cost_record = DBCostRecord(
                        transaction_id=operation_id,
                        trial_id=trial_id,
                        run_id=execution_id or f"pipeline_{int(time.time())}",  # Use execution_id if provided
                        operation_type=db_operation_type,
                        cost_amount=cost,
                        operation_metadata=metadata or {}
                    )
                    self.db_session.add(db_cost_record)
                    # Don't commit here - let the caller manage the transaction
                    logger.debug(f"Added cost record to database session: {operation_type} for trial {trial_id}: ${cost:.3f}")
                except Exception as e:
                    logger.error(f"Failed to add cost record to database session: {e}")
                    # Continue with in-memory tracking even if DB persistence fails
            
            # Update running totals
            self.trial_costs[trial_id] = self.trial_costs.get(trial_id, 0.0) + cost
            self._update_period_costs(cost)
            
            # Check if we need to reset budget
            self._check_budget_reset()
            
            # Log the cost
            logger.debug(f"Recorded cost: {operation_type} for trial {trial_id}: ${cost:.3f}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to record cost: {e}")
            return False
    
    def estimate_operation_cost(self, operation_type: str) -> float:
        """
        Get estimated cost for an operation type.
        
        Args:
            operation_type: Type of operation
            
        Returns:
            Estimated cost in USD
        """
        return self.cost_estimates.get(operation_type, 0.0)
    
    def can_afford_operation(self, operation_type: str, trial_id: str) -> bool:
        """
        Check if we can afford an operation.
        
        Args:
            operation_type: Type of operation
            trial_id: Trial identifier
            
        Returns:
            True if operation can be afforded, False otherwise
        """
        estimated_cost = self.estimate_operation_cost(operation_type)
        
        # Check trial limit
        current_trial_cost = self.trial_costs.get(trial_id, 0.0)
        if current_trial_cost + estimated_cost > self.trial_limit:
            return False
        
        # Check period limit
        current_period_cost = self._get_current_period_cost()
        if current_period_cost + estimated_cost > self._get_current_period_limit():
            return False
        
        return True
    
    def get_budget_status(self) -> BudgetStatus:
        """
        Get current budget status.
        
        Returns:
            BudgetStatus indicating current budget health
        """
        current_cost = self._get_current_period_cost()
        current_limit = self._get_current_period_limit()
        
        if current_cost >= current_limit:
            return BudgetStatus.EXCEEDED
        
        utilization = current_cost / current_limit
        
        if utilization >= self.alert_thresholds['emergency']:
            return BudgetStatus.EMERGENCY
        elif utilization >= self.alert_thresholds['critical']:
            return BudgetStatus.CRITICAL
        elif utilization >= self.alert_thresholds['warning']:
            return BudgetStatus.WARNING
        else:
            return BudgetStatus.OK
    
    def get_execution_cost(self, execution_id: str) -> float:
        """
        Get total cost for a specific execution.
        
        Args:
            execution_id: Execution identifier
            
        Returns:
            Total cost for the execution
        """
        if self.db_session and DBCostRecord:
            try:
                from sqlalchemy import text
                result = self.db_session.execute(text(
                    "SELECT COALESCE(SUM(cost_amount), 0) FROM cost_records WHERE run_id = :execution_id"
                ), {'execution_id': execution_id})
                return float(result.scalar() or 0.0)
            except Exception as e:
                logger.warning(f"Failed to query execution cost from database: {e}")
        
        # Fallback to in-memory records
        execution_costs = [record.cost for record in self.cost_records if record.execution_id == execution_id]
        return sum(execution_costs)
    
    def get_budget_summary(self, period: Optional[BudgetPeriod] = None) -> BudgetSummary:
        """
        Get budget summary for a specific period.
        
        Args:
            period: Budget period (if None, uses current period)
            
        Returns:
            BudgetSummary with detailed budget information
        """
        if period is None:
            period = self._get_current_period()
        
        start_date = self._get_period_start(period)
        end_date = self._get_period_end(period)
        total_cost = self._get_period_cost(period)
        cost_limit = self._get_period_limit(period)
        
        # Calculate cost breakdown by operation type
        cost_breakdown = {}
        for record in self.cost_records:
            if start_date <= record.timestamp <= end_date:
                op_type = record.operation_type
                cost_breakdown[op_type] = cost_breakdown.get(op_type, 0.0) + record.cost
        
        # Calculate trial costs for the period
        trial_costs = {}
        for record in self.cost_records:
            if start_date <= record.timestamp <= end_date:
                trial_id = record.trial_id
                trial_costs[trial_id] = trial_costs.get(trial_id, 0.0) + record.cost
        
        status = self.get_budget_status()
        
        return BudgetSummary(
            period=period,
            start_date=start_date,
            end_date=end_date,
            total_cost=total_cost,
            cost_limit=cost_limit,
            remaining_budget=max(0, cost_limit - total_cost),
            status=status,
            cost_breakdown=cost_breakdown,
            trial_costs=trial_costs
        )
    
    def get_cost_alerts(self) -> List[Dict[str, Any]]:
        """
        Get current cost alerts.
        
        Returns:
            List of alert dictionaries
        """
        alerts = []
        status = self.get_budget_status()
        
        if status == BudgetStatus.EXCEEDED:
            alerts.append({
                'level': 'error',
                'message': 'Budget exceeded',
                'status': status.value,
                'timestamp': datetime.now().isoformat()
            })
        elif status in [BudgetStatus.EMERGENCY, BudgetStatus.CRITICAL, BudgetStatus.WARNING]:
            alerts.append({
                'level': 'warning',
                'message': f'Budget at {status.value} level',
                'status': status.value,
                'timestamp': datetime.now().isoformat()
            })
        
        return alerts
    
    def reset_budget(self, force: bool = False) -> bool:
        """
        Reset the budget for the current period.
        
        Args:
            force: Force reset even if not scheduled
            
        Returns:
            True if budget was reset, False otherwise
        """
        try:
            if not force and not self._should_reset_budget():
                return False
            
            # Archive current cost records
            self._archive_cost_data()
            
            # Reset tracking
            self.cost_records = []
            self.trial_costs = {}
            self.period_costs = {}
            
            # Update reset tracking
            self.current_period_start = self._get_period_start()
            self.last_reset = datetime.now()
            
            logger.info("Budget reset completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset budget: {e}")
            return False
    
    def get_cost_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive cost statistics.
        
        Returns:
            Dictionary with cost statistics
        """
        try:
            current_summary = self.get_budget_summary()
            
            stats = {
                'current_period': {
                    'period': current_summary.period.value,
                    'start_date': current_summary.start_date.isoformat(),
                    'end_date': current_summary.end_date.isoformat(),
                    'total_cost': current_summary.total_cost,
                    'cost_limit': current_summary.cost_limit,
                    'remaining_budget': current_summary.remaining_budget,
                    'utilization_percentage': current_summary.utilization_percentage,
                    'status': current_summary.status.value
                },
                'cost_breakdown': current_summary.cost_breakdown,
                'trial_costs': current_summary.trial_costs,
                'alerts': self.get_cost_alerts(),
                'last_reset': self.last_reset.isoformat(),
                'next_reset': self._get_next_reset_date().isoformat()
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get cost statistics: {e}")
            return {'error': str(e)}
    
    def _get_current_period(self) -> BudgetPeriod:
        """Get current budget period."""
        if self.reset_schedule == 'daily':
            return BudgetPeriod.DAILY
        elif self.reset_schedule == 'weekly':
            return BudgetPeriod.WEEKLY
        else:
            return BudgetPeriod.MONTHLY
    
    def _get_period_start(self, period: Optional[BudgetPeriod] = None) -> datetime:
        """Get start date for a budget period."""
        if period is None:
            period = self._get_current_period()
        
        now = datetime.now()
        
        if period == BudgetPeriod.DAILY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == BudgetPeriod.WEEKLY:
            # Start of week (Monday)
            days_since_monday = now.weekday()
            return (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # MONTHLY
            # For monthly periods, find the most recent reset day
            # If current day is before reset_day, use previous month
            if now.day < self.reset_day:
                # Use previous month
                if now.month == 1:
                    return now.replace(year=now.year - 1, month=12, day=self.reset_day, hour=0, minute=0, second=0, microsecond=0)
                else:
                    return now.replace(month=now.month - 1, day=self.reset_day, hour=0, minute=0, second=0, microsecond=0)
            else:
                # Use current month
                return now.replace(day=self.reset_day, hour=0, minute=0, second=0, microsecond=0)
    
    def _get_period_end(self, period: Optional[BudgetPeriod] = None) -> datetime:
        """Get end date for a budget period."""
        if period is None:
            period = self._get_current_period()
        
        start = self._get_period_start(period)
        
        if period == BudgetPeriod.DAILY:
            return start + timedelta(days=1)
        elif period == BudgetPeriod.WEEKLY:
            return start + timedelta(weeks=1)
        else:  # MONTHLY
            # Add one month
            if start.month == 12:
                return start.replace(year=start.year + 1, month=1)
            else:
                return start.replace(month=start.month + 1)
    
    def _get_current_period_cost(self) -> float:
        """Get total cost for current period."""
        period = self._get_current_period()
        return self._get_period_cost(period)
    
    def _get_period_cost(self, period: BudgetPeriod) -> float:
        """Get total cost for a specific period."""
        start_date = self._get_period_start(period)
        end_date = self._get_period_end(period)
        
        # Try to get costs from database first
        if self.db_session:
            try:
                from ..db.models import CostRecord
                from sqlalchemy import text
                
                # Query costs from database for the period
                query = text("""
                    SELECT SUM(cost_amount) as total_cost
                    FROM cost_records 
                    WHERE recorded_at >= :start_date AND recorded_at < :end_date
                """)
                
                result = self.db_session.execute(query, {
                    'start_date': start_date,
                    'end_date': end_date
                }).fetchone()
                
                if result and result[0]:
                    logger.debug(f"Retrieved period cost from database: ${result[0]:.4f}")
                    return float(result[0])
                    
            except Exception as e:
                logger.warning(f"Failed to query database for period cost: {e}")
        
        # Fallback to in-memory records
        total_cost = 0.0
        for record in self.cost_records:
            if start_date <= record.timestamp <= end_date:
                total_cost += record.cost
        
        return total_cost
    
    def _get_current_period_limit(self) -> float:
        """Get cost limit for current period."""
        period = self._get_current_period()
        return self._get_period_limit(period)
    
    def _get_period_limit(self, period: BudgetPeriod) -> float:
        """Get cost limit for a specific period."""
        if period == BudgetPeriod.DAILY:
            return self.daily_limit
        elif period == BudgetPeriod.WEEKLY:
            return self.daily_limit * 7
        else:  # MONTHLY
            return self.monthly_limit
    
    def _update_period_costs(self, cost: float) -> None:
        """Update period cost tracking."""
        period_key = self._get_current_period().value
        self.period_costs[period_key] = self.period_costs.get(period_key, 0.0) + cost
    
    def _should_reset_budget(self) -> bool:
        """Check if budget should be reset."""
        now = datetime.now()
        next_reset = self._get_next_reset_date()
        return now >= next_reset
    
    def _get_next_reset_date(self) -> datetime:
        """Get next budget reset date."""
        if self.reset_schedule == 'daily':
            return self.last_reset + timedelta(days=1)
        elif self.reset_schedule == 'weekly':
            return self.last_reset + timedelta(weeks=1)
        else:  # MONTHLY
            # Add one month
            if self.last_reset.month == 12:
                return self.last_reset.replace(year=self.last_reset.year + 1, month=1)
            else:
                return self.last_reset.replace(month=self.last_reset.month + 1)
    
    def _check_budget_reset(self) -> None:
        """Check if budget needs to be reset."""
        if self._should_reset_budget():
            logger.info("Scheduled budget reset triggered")
            self.reset_budget()
    
    def _load_cost_data(self) -> None:
        """Load existing cost data from storage."""
        try:
            # This would typically load from a database or file
            # For now, we'll just log that we're loading data
            logger.debug("Loading existing cost data...")
        except Exception as e:
            logger.warning(f"Failed to load cost data: {e}")
    
    def _archive_cost_data(self) -> None:
        """Archive current cost data."""
        try:
            # This would typically save to a database or file
            # For now, we'll just log that we're archiving data
            logger.debug("Archiving cost data...")
        except Exception as e:
            logger.warning(f"Failed to archive cost data: {e}")
    
    def commit_pending_costs(self) -> bool:
        """
        Commit all pending cost records to the database.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.db_session:
            logger.warning("No database session available for committing costs")
            return False
        
        try:
            self.db_session.commit()
            logger.info("Successfully committed all pending cost records")
            return True
        except Exception as e:
            logger.error(f"Failed to commit pending cost records: {e}")
            self.db_session.rollback()
            return False


class BudgetGuard:
    """
    Budget guard that can be used to enforce budget limits.
    
    This class provides a context manager interface for
    automatically checking and recording costs.
    """
    
    def __init__(self, budget_monitor: BudgetMonitor, trial_id: str, operation_type: str):
        """
        Initialize the budget guard.
        
        Args:
            budget_monitor: Budget monitor instance
            trial_id: Trial identifier
            operation_type: Type of operation
        """
        self.budget_monitor = budget_monitor
        self.trial_id = trial_id
        self.operation_type = operation_type
        self.operation_id = f"{trial_id}_{operation_type}_{int(time.time())}"
        self.cost_recorded = False
    
    def __enter__(self):
        """Enter the budget guard context."""
        # Check if we can afford the operation
        if not self.budget_monitor.can_afford_operation(self.operation_type, self.trial_id):
            raise BudgetExceededError(
                f"Cannot afford {self.operation_type} for trial {self.trial_id}"
            )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the budget guard context."""
        # Record the cost if no exception occurred
        if exc_type is None and not self.cost_recorded:
            estimated_cost = self.budget_monitor.estimate_operation_cost(self.operation_type)
            self.budget_monitor.record_cost(
                self.operation_id,
                self.trial_id,
                self.operation_type,
                estimated_cost
            )
            self.cost_recorded = True
    
    def record_actual_cost(self, actual_cost: float, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Record the actual cost of the operation.
        
        Args:
            actual_cost: Actual cost incurred
            metadata: Additional metadata
        """
        if not self.cost_recorded:
            self.budget_monitor.record_cost(
                self.operation_id,
                self.trial_id,
                self.operation_type,
                actual_cost,
                metadata
            )
            self.cost_recorded = True


class BudgetExceededError(Exception):
    """Exception raised when budget is exceeded."""
    pass


# Convenience function for budget monitoring
def create_budget_monitor(config: Dict[str, Any]) -> BudgetMonitor:
    """
    Create a budget monitor instance.
    
    Args:
        config: Budget configuration dictionary
        
    Returns:
        BudgetMonitor instance
    """
    return BudgetMonitor(config)
