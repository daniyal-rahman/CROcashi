"""
Global concurrency manager for LLM providers.
Ensures all providers share the same concurrency limits.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)

class ConcurrencyManager:
    """Global concurrency manager for LLM providers."""
    
    _instance: Optional['ConcurrencyManager'] = None
    _semaphore: Optional[asyncio.Semaphore] = None
    _max_concurrent: int = 10
    _active_tasks: int = 0
    _task_start_times: List[float] = []
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def configure(self, max_concurrent_requests: int = 10):
        """Configure the global concurrency limit."""
        # Only configure if not already configured
        if self._semaphore is None:
            self._max_concurrent = max_concurrent_requests
            self._semaphore = asyncio.Semaphore(max_concurrent_requests)
            self._active_tasks = 0
            self._task_start_times = []
            logger.info(f"Global concurrency manager configured: {max_concurrent_requests} max concurrent requests")
        else:
            logger.debug(f"Global concurrency manager already configured: {self._max_concurrent} max concurrent requests (ignoring {max_concurrent_requests})")
    
    def reset(self):
        """Reset the concurrency manager (for testing)."""
        self._semaphore = None
        self._max_concurrent = 10
        self._active_tasks = 0
        self._task_start_times = []
        logger.info("Global concurrency manager reset")
    
    def get_semaphore(self) -> asyncio.Semaphore:
        """Get the global semaphore."""
        if self._semaphore is None:
            self.configure()  # Use default if not configured
        return self._semaphore
    
    def get_max_concurrent(self) -> int:
        """Get the maximum concurrent requests."""
        return self._max_concurrent
    
    async def execute_with_concurrency_control(self, task_func: Callable, *args, **kwargs) -> Any:
        """Execute a task with proper concurrency control."""
        # Acquire semaphore BEFORE starting the task
        async with self._semaphore:
            self._active_tasks += 1
            start_time = time.time()
            self._task_start_times.append(start_time)
            
            logger.debug(f"🔒 Task started: {self._active_tasks}/{self._max_concurrent} active tasks")
            
            try:
                result = await task_func(*args, **kwargs)
                return result
            finally:
                self._active_tasks -= 1
                self._task_start_times = [t for t in self._task_start_times if t != start_time]
                logger.debug(f"🔓 Task completed: {self._active_tasks}/{self._max_concurrent} active tasks")
    
    def get_active_task_count(self) -> int:
        """Get the current number of active tasks."""
        return self._active_tasks
    
    def get_task_start_times(self) -> List[float]:
        """Get the start times of active tasks."""
        return self._task_start_times.copy()

# Global instance
concurrency_manager = ConcurrencyManager()
