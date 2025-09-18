"""
Simplified Resolver System

This module provides a clean, three-tier resolver system:
1. Exact Match (deterministic)
2. Fuzzy Match (Jaro-Winkler similarity)  
3. LLM Match (with web search for aliases/subsidiaries)

The LLM tier serves as a learning system that discovers new company relationships
and feeds them back into the database for better future matching.
"""

from .simple_resolver import resolve_sponsor_simple, SimpleResolver, ResolutionOutput
from .simple_persist import (
    save_resolution, 
    add_to_review_queue, 
    get_resolution_stats,
    learn_aliases_from_discoveries
)
from .simple_cli import app as cli_app
from .deterministic import resolve_company
from .normalize import norm_name, has_academic_keywords

__all__ = [
    # Main resolver
    "resolve_sponsor_simple",
    "SimpleResolver", 
    "ResolutionOutput",
    
    # Persistence
    "save_resolution",
    "add_to_review_queue",
    "get_resolution_stats",
    "learn_aliases_from_discoveries",
    
    # CLI
    "cli_app",
    
    # Utilities
    "resolve_company",
    "norm_name",
    "has_academic_keywords",
]
