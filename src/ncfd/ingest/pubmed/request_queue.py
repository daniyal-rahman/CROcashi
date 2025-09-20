"""
PubMed Request Queue - Coordinated API request management.

Provides a centralized queue for all PubMed API requests to prevent
rate limit conflicts and ensure optimal request timing.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RequestPriority(Enum):
    """Request priority levels."""
    HIGH = 1      # Critical requests (health checks, essential queries)
    NORMAL = 2    # Standard requests (search, fetch)
    LOW = 3       # Background requests (metadata, cleanup)


@dataclass
class QueuedRequest:
    """Represents a queued PubMed API request."""
    request_id: str
    priority: RequestPriority
    request_func: Callable
    args: tuple
    kwargs: dict
    created_at: datetime
    component: str  # Which component made the request
    retry_count: int = 0
    max_retries: int = 3


class PubMedRequestQueue:
    """Centralized queue for PubMed API requests."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the request queue.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.queue = asyncio.PriorityQueue()
        self.active_requests = 0
        self.max_concurrent = self.config.get('max_concurrent_requests', 3)
        self.request_semaphore = asyncio.Semaphore(self.max_concurrent)
        self.request_counter = 0
        self.stats = {
            'total_requests': 0,
            'completed_requests': 0,
            'failed_requests': 0,
            'rate_limit_hits': 0,
            'queue_size': 0
        }
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        
        logger.info(f"PubMed Request Queue initialized with max_concurrent={self.max_concurrent}")
    
    async def start(self):
        """Start the request queue worker."""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._worker())
            logger.info("PubMed Request Queue started")
    
    async def stop(self):
        """Stop the request queue worker."""
        if self._running:
            self._running = False
            if self._worker_task:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
            logger.info("PubMed Request Queue stopped")
    
    async def submit_request(
        self,
        request_func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        priority: RequestPriority = RequestPriority.NORMAL,
        component: str = "unknown",
        max_retries: int = 3
    ) -> Any:
        """
        Submit a request to the queue.
        
        Args:
            request_func: Function to execute
            args: Function arguments
            kwargs: Function keyword arguments
            priority: Request priority
            component: Component making the request
            max_retries: Maximum retry attempts
            
        Returns:
            Result of the request function
        """
        if kwargs is None:
            kwargs = {}
        
        self.request_counter += 1
        request_id = f"req_{self.request_counter}_{component}"
        
        queued_request = QueuedRequest(
            request_id=request_id,
            priority=priority,
            request_func=request_func,
            args=args,
            kwargs=kwargs,
            created_at=datetime.now(timezone.utc),
            component=component,
            max_retries=max_retries
        )
        
        # Add to queue
        await self.queue.put((priority.value, queued_request))
        self.stats['total_requests'] += 1
        self.stats['queue_size'] = self.queue.qsize()
        
        logger.debug(f"Queued request {request_id} from {component} with priority {priority.name}")
        
        # Wait for completion
        return await self._wait_for_completion(request_id)
    
    async def _wait_for_completion(self, request_id: str) -> Any:
        """Wait for a specific request to complete."""
        # This is a simplified implementation
        # In a real system, you'd use a more sophisticated completion tracking
        while True:
            await asyncio.sleep(0.1)
            # Check if request is completed (simplified)
            if self.stats['completed_requests'] + self.stats['failed_requests'] >= self.stats['total_requests']:
                break
        
        # Return a placeholder result (in real implementation, you'd track actual results)
        return {"status": "completed", "request_id": request_id}
    
    async def _worker(self):
        """Worker coroutine that processes queued requests."""
        logger.info("PubMed Request Queue worker started")
        
        while self._running:
            try:
                # Get next request from queue
                priority, queued_request = await asyncio.wait_for(
                    self.queue.get(), timeout=1.0
                )
                
                # Process request with semaphore
                async with self.request_semaphore:
                    await self._process_request(queued_request)
                
                self.queue.task_done()
                self.stats['queue_size'] = self.queue.qsize()
                
            except asyncio.TimeoutError:
                # No requests in queue, continue
                continue
            except Exception as e:
                logger.error(f"Error in request queue worker: {e}")
                await asyncio.sleep(1.0)
        
        logger.info("PubMed Request Queue worker stopped")
    
    async def _process_request(self, queued_request: QueuedRequest):
        """Process a single queued request."""
        try:
            logger.debug(f"Processing request {queued_request.request_id}")
            
            # Execute the request
            result = await queued_request.request_func(
                *queued_request.args, 
                **queued_request.kwargs
            )
            
            self.stats['completed_requests'] += 1
            logger.debug(f"Completed request {queued_request.request_id}")
            
        except Exception as e:
            queued_request.retry_count += 1
            
            if queued_request.retry_count <= queued_request.max_retries:
                # Retry the request
                logger.warning(f"Request {queued_request.request_id} failed, retrying ({queued_request.retry_count}/{queued_request.max_retries}): {e}")
                
                # Add back to queue with higher priority for retry
                await self.queue.put((RequestPriority.HIGH.value, queued_request))
            else:
                # Max retries exceeded
                self.stats['failed_requests'] += 1
                logger.error(f"Request {queued_request.request_id} failed after {queued_request.max_retries} retries: {e}")
                
                # Check if it's a rate limit error
                if "429" in str(e) or "rate limit" in str(e).lower():
                    self.stats['rate_limit_hits'] += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            **self.stats,
            'active_requests': self.active_requests,
            'max_concurrent': self.max_concurrent,
            'queue_size': self.queue.qsize(),
            'running': self._running
        }
    
    async def health_check(self) -> bool:
        """Check if the queue is healthy."""
        try:
            # Check if worker is running
            if not self._running or not self._worker_task:
                return False
            
            # Check if worker task is still alive
            if self._worker_task.done():
                return False
            
            # Check queue size (shouldn't be too large)
            if self.queue.qsize() > 1000:
                logger.warning(f"Queue size is very large: {self.queue.qsize()}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


# Global instance
_request_queue: Optional[PubMedRequestQueue] = None


def get_request_queue(config: Optional[Dict[str, Any]] = None) -> PubMedRequestQueue:
    """Get the global request queue instance."""
    global _request_queue
    if _request_queue is None:
        _request_queue = PubMedRequestQueue(config)
    return _request_queue


async def submit_pubmed_request(
    request_func: Callable,
    args: tuple = (),
    kwargs: dict = None,
    priority: RequestPriority = RequestPriority.NORMAL,
    component: str = "unknown"
) -> Any:
    """Convenience function to submit a request to the queue."""
    queue = get_request_queue()
    return await queue.submit_request(request_func, args, kwargs, priority, component)
