"""
Caching layer for company risk service using Redis.
"""
import json
import logging
import os
from typing import Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)

# Try to import Redis, but make it optional
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available. Caching will be disabled.")


class Cache:
    """
    Redis-based cache wrapper with fallback to no-op if Redis unavailable.
    """
    
    def __init__(self):
        """Initialize cache client."""
        self.client = None
        self.enabled = False
        
        if REDIS_AVAILABLE:
            try:
                redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
                self.client = redis.from_url(redis_url, decode_responses=True)
                # Test connection
                self.client.ping()
                self.enabled = True
                logger.info("Redis cache enabled")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Caching disabled.")
                self.enabled = False
        else:
            logger.info("Redis not installed. Caching disabled.")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        if not self.enabled or not self.client:
            return None
        
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}", exc_info=True)
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds (default 1 hour)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.client:
            return False
        
        try:
            serialized = json.dumps(value, default=str)  # Use str for dates/UUIDs
            self.client.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}", exc_info=True)
            return False
    
    def delete(self, key: str) -> bool:
        """
        Delete key from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.client:
            return False
        
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}", exc_info=True)
            return False
    
    def invalidate_company(self, company_id: str) -> bool:
        """
        Invalidate all cache entries for a company.
        
        Args:
            company_id: Company UUID string
            
        Returns:
            True if successful
        """
        if not self.enabled or not self.client:
            return False
        
        try:
            # Delete all keys matching company patterns
            patterns = [
                f"risk_score:{company_id}",
                f"company_metrics:{company_id}",
                f"company_timeline:{company_id}:*"
            ]
            
            for pattern in patterns:
                if '*' in pattern:
                    # Use SCAN for pattern matching
                    keys = self.client.keys(pattern)
                    if keys:
                        self.client.delete(*keys)
                else:
                    self.client.delete(pattern)
            
            return True
        except Exception as e:
            logger.error(f"Error invalidating cache for company {company_id}: {e}", exc_info=True)
            return False


# Global cache instance
_cache_instance: Optional[Cache] = None


def get_cache() -> Cache:
    """
    Get global cache instance (singleton).
    
    Returns:
        Cache instance
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = Cache()
    return _cache_instance


def cached(ttl: int = 3600, key_prefix: str = ""):
    """
    Decorator for caching function results.
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache keys
        
    Usage:
        @cached(ttl=3600, key_prefix="risk_score")
        def calculate_risk(company_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache()
            
            # Build cache key from function name and arguments
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try to get from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Call function
            result = func(*args, **kwargs)
            
            # Store in cache
            cache.set(cache_key, result, ttl=ttl)
            
            return result
        return wrapper
    return decorator

