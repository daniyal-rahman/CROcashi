"""
DateTime utilities for consistent timezone-aware timestamp handling.

This module provides utilities to ensure all datetime operations use UTC
and are timezone-aware throughout the codebase.
"""

from datetime import datetime, timezone
from typing import Union, Optional
import logging

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """
    Get current UTC timestamp.
    
    Returns:
        Current datetime in UTC timezone
    """
    return datetime.now(timezone.utc)


def ensure_utc(dt: Union[datetime, str, None]) -> Optional[datetime]:
    """
    Ensure a datetime is timezone-aware and in UTC.
    
    Args:
        dt: Datetime object, ISO string, or None
        
    Returns:
        Timezone-aware datetime in UTC, or None if input is None
        
    Raises:
        ValueError: If dt is a string that cannot be parsed
    """
    if dt is None:
        return None
    
    if isinstance(dt, str):
        try:
            # Parse ISO string
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError as e:
            raise ValueError(f"Could not parse datetime string '{dt}': {e}")
    
    if dt.tzinfo is None:
        # Assume naive datetime is in UTC
        dt = dt.replace(tzinfo=timezone.utc)
        logger.warning(f"Naive datetime converted to UTC: {dt}")
    elif dt.tzinfo != timezone.utc:
        # Convert to UTC
        dt = dt.astimezone(timezone.utc)
        logger.debug(f"Datetime converted to UTC: {dt}")
    
    return dt


def format_utc_iso(dt: Optional[datetime] = None) -> str:
    """
    Format datetime as ISO string in UTC.
    
    Args:
        dt: Datetime to format, or current time if None
        
    Returns:
        ISO formatted string in UTC
    """
    if dt is None:
        dt = utc_now()
    else:
        dt = ensure_utc(dt)
    
    return dt.isoformat()


def parse_utc_iso(iso_string: str) -> datetime:
    """
    Parse ISO string and ensure it's in UTC.
    
    Args:
        iso_string: ISO formatted datetime string
        
    Returns:
        Timezone-aware datetime in UTC
        
    Raises:
        ValueError: If string cannot be parsed
    """
    return ensure_utc(iso_string)


def utc_timestamp() -> float:
    """
    Get current UTC timestamp as float.
    
    Returns:
        Current UTC timestamp as float
    """
    return utc_now().timestamp()


def is_utc(dt: datetime) -> bool:
    """
    Check if datetime is in UTC timezone.
    
    Args:
        dt: Datetime to check
        
    Returns:
        True if datetime is timezone-aware and in UTC
    """
    return dt.tzinfo == timezone.utc


def is_naive(dt: datetime) -> bool:
    """
    Check if datetime is naive (no timezone info).
    
    Args:
        dt: Datetime to check
        
    Returns:
        True if datetime has no timezone info
    """
    return dt.tzinfo is None
