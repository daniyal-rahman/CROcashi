"""
Processing module for PubMed pipeline.

Implements Steps 7-8 of the retrieval pipeline:
7. Abstract fetching and entity extraction
8. R/S scoring and document selection
"""

from .abstract_processor import AbstractProcessor, ProcessingResult

__all__ = [
    "AbstractProcessor",
    "ProcessingResult"
]
