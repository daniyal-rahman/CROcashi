"""
Extract module for NCFD.

Contains document processing and extraction components:
- LateFusionOrchestrator: Dual-path processing with late fusion
"""

from .late_fusion_orchestrator import LateFusionOrchestrator

__all__ = ['LateFusionOrchestrator']