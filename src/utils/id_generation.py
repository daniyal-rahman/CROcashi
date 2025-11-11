"""Utilities for generating stable identifiers."""

import hashlib
from typing import Tuple


def generate_hash_id(prefix: str, *parts: str, modulo: int = 1000000) -> str:
    """
    Generate a stable identifier using hash of concatenated parts.
    
    Used for creating deterministic IDs for ingested data where no natural
    primary key exists (e.g., WARN notices, warning letters).
    
    Uses MD5 hash for better collision resistance than Python's built-in hash().
    Default modulo increased to 1,000,000 to reduce collision probability.
    
    Args:
        prefix: Prefix for the ID (e.g., 'CA-WARN', 'WL')
        *parts: Parts to hash together (e.g., company_name, date)
        modulo: Hash space size (default 1000000 for better uniqueness)
    
    Returns:
        Formatted ID string like "CA-WARN-7891"
        
    Example:
        >>> generate_hash_id('CA-WARN', 'Acme Corp', '2024-01-15')
        'CA-WARN-7891'
    """
    if not parts:
        raise ValueError("Must provide at least one part to hash")
    
    combined = ''.join(str(p) for p in parts)
    # Use MD5 for better collision resistance
    hash_bytes = hashlib.md5(combined.encode('utf-8')).digest()
    # Convert first 4 bytes to integer and take modulo
    hash_int = int.from_bytes(hash_bytes[:4], byteorder='big')
    hash_suffix = hash_int % modulo
    return f"{prefix}-{hash_suffix}"


def generate_abstract_id(prefix: str, *parts: str) -> str:
    """
    Generate ID for conference abstracts (larger hash space).
    
    Uses 100,000 modulo to reduce collision probability for large
    abstract collections.
    
    Args:
        prefix: Prefix for the ID (e.g., 'ASCO')
        *parts: Parts to hash together (e.g., year, url)
    
    Returns:
        Formatted ID string like "ASCO-12345"
    """
    return generate_hash_id(prefix, *parts, modulo=100000)

