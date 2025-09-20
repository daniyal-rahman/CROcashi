"""
PubMed Client Manager - Singleton pattern for coordinated API access.

Ensures only one PubMed client instance is used across all components,
preventing rate limit conflicts and ensuring consistent configuration.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from .client import PubMedClient
from .request_queue import get_request_queue, RequestPriority
from .monitoring import get_monitor, AlertLevel

logger = logging.getLogger(__name__)


class PubMedClientManager:
    """Singleton manager for PubMed client instances."""
    
    _instance: Optional['PubMedClientManager'] = None
    _client: Optional[PubMedClient] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._request_queue = asyncio.Queue()
            self._active_requests = 0
            self._total_requests = 0
            self._rate_limit_hits = 0
            self._last_rate_limit_hit = None
            logger.info("PubMed Client Manager initialized")
    
    async def get_client(self, config: Dict[str, Any]) -> PubMedClient:
        """
        Get or create the singleton PubMed client.
        
        Args:
            config: Configuration dictionary for client initialization
            
        Returns:
            PubMedClient instance
        """
        async with self._lock:
            if self._client is None:
                # Extract client configuration
                client_config = config.get('client_config', {})
                
                # Map configuration parameters to PubMedClient constructor parameters
                mapped_config = {}
                if 'rate_limit_requests_per_minute' in client_config:
                    # Convert requests per minute to requests per second
                    mapped_config['rate_limit_per_sec'] = client_config['rate_limit_requests_per_minute'] / 60
                elif 'rate_limit_per_sec' in client_config:
                    mapped_config['rate_limit_per_sec'] = client_config['rate_limit_per_sec']
                else:
                    mapped_config['rate_limit_per_sec'] = 8  # Default to 8 req/sec
                
                # Map other parameters
                mapped_config.update({
                    'batch_size': client_config.get('batch_size', 100),
                    'timeout_seconds': client_config.get('timeout_seconds', 30),
                    'max_retries': client_config.get('max_retries', 3),
                    'backoff_base': client_config.get('backoff_base', 2.0),
                    'circuit_breaker_threshold': client_config.get('circuit_breaker_threshold', 5),
                    'api_key': client_config.get('api_key'),
                    'email': client_config.get('email', 'ncfd@example.com'),
                    'tool': client_config.get('tool', 'NCFD')
                })
                
                self._client = PubMedClient(**mapped_config)
                logger.info(f"Created singleton PubMed client with rate_limit_per_sec={mapped_config['rate_limit_per_sec']}")
            
            return self._client
    
    async def execute_request(self, request_func, *args, **kwargs):
        """
        Execute a request through the coordinated client and request queue.
        
        Args:
            request_func: Function to execute (e.g., client.esearch)
            *args: Arguments for the request function
            **kwargs: Keyword arguments for the request function
            
        Returns:
            Result of the request function
        """
        # Submit to request queue for coordination
        queue = get_request_queue()
        
        async def _execute_with_client():
            async with self._lock:
                self._active_requests += 1
                self._total_requests += 1
                
                try:
                    # Get the client
                    client = await self.get_client({})
                    
                    # Execute the request
                    result = await request_func(client, *args, **kwargs)
                    
                    # Update statistics
                    rate_limit_info = client.get_rate_limit_info()
                    if rate_limit_info['consecutive_failures'] > 0:
                        self._rate_limit_hits += 1
                        self._last_rate_limit_hit = datetime.now(timezone.utc)
                    
                    return result
                    
                except Exception as e:
                    # Check if it's a rate limit error
                    if "429" in str(e) or "rate limit" in str(e).lower():
                        self._rate_limit_hits += 1
                        self._last_rate_limit_hit = datetime.now(timezone.utc)
                        logger.warning(f"Rate limit hit during request: {e}")
                        
                        # Report to monitor
                        monitor = get_monitor()
                        await monitor._create_alert(
                            AlertLevel.WARNING,
                            f"Rate limit hit: {e}",
                            "client_manager",
                            {"error": str(e)}
                        )
                    raise
                finally:
                    self._active_requests -= 1
        
        # Submit to queue with appropriate priority
        priority = RequestPriority.NORMAL
        if 'esearch' in str(request_func):
            priority = RequestPriority.HIGH  # Search requests are high priority
        elif 'efetch' in str(request_func):
            priority = RequestPriority.NORMAL  # Fetch requests are normal priority
        
        return await queue.submit_request(
            _execute_with_client,
            priority=priority,
            component="client_manager"
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get client usage statistics."""
        return {
            'total_requests': self._total_requests,
            'active_requests': self._active_requests,
            'rate_limit_hits': self._rate_limit_hits,
            'last_rate_limit_hit': self._last_rate_limit_hit.isoformat() if self._last_rate_limit_hit else None,
            'client_initialized': self._client is not None
        }
    
    async def health_check(self) -> bool:
        """Perform health check on the client."""
        try:
            client = await self.get_client({})
            return await client.health_check()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def close(self):
        """Close the client and cleanup resources."""
        async with self._lock:
            if self._client:
                await self._client.__aexit__(None, None, None)
                self._client = None
                logger.info("PubMed client closed")


# Global instance
_client_manager = PubMedClientManager()


def get_client_manager() -> PubMedClientManager:
    """Get the global client manager instance."""
    return _client_manager


async def get_pubmed_client(config: Dict[str, Any]) -> PubMedClient:
    """Convenience function to get the singleton client."""
    manager = get_client_manager()
    return await manager.get_client(config)


async def execute_pubmed_request(request_func, *args, **kwargs):
    """Convenience function to execute a request through the manager."""
    manager = get_client_manager()
    return await manager.execute_request(request_func, *args, **kwargs)
