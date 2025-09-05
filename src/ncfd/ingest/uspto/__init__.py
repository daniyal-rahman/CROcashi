"""
USPTO patent data ingestion module.

This module provides ingestion capabilities for US patent data including:
- Patent grants and applications
- Assignment records
- Patent family data (US-focused)
- Asset-patent linking
- Ownership timeline reconstruction
"""

from .patent_types import (
    PatentRecord,
    AssignmentRecord,
    PatentFamily,
    OwnershipEvent,
    PatentSearchQuery,
    IngestionResult
)

from .patent_client import USPTOPatentClient
from .assignment_client import USPTOAssignmentClient
from .patent_processor import PatentProcessor

__all__ = [
    'PatentRecord',
    'AssignmentRecord', 
    'PatentFamily',
    'OwnershipEvent',
    'PatentSearchQuery',
    'IngestionResult',
    'USPTOPatentClient',
    'USPTOAssignmentClient',
    'PatentProcessor'
]
