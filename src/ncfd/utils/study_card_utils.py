"""
Study card utility functions.
"""

import hashlib
from typing import Optional


def generate_span_id(doc_id: int, page: Optional[int], char_start: Optional[int], char_end: Optional[int]) -> str:
    """Generate a unique span ID based on document and position."""
    # Create a hash of the span position
    position_str = f"{doc_id}_{page}_{char_start}_{char_end}"
    return hashlib.md5(position_str.encode()).hexdigest()[:12]


def validate_span_coordinates(page: Optional[int], char_start: Optional[int], char_end: Optional[int]) -> bool:
    """Validate that span coordinates are reasonable."""
    # Basic validation - coordinates should be non-negative and char_end > char_start
    if char_start is not None and char_start < 0:
        return False
    if char_end is not None and char_end < 0:
        return False
    if char_start is not None and char_end is not None and char_end <= char_start:
        return False
    if page is not None and page < 0:
        return False
    
    return True
