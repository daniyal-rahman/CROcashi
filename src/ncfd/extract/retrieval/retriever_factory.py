"""
Retriever Factory

Creates the EnhancedRetriever for LLM-first architecture.
"""

import logging
from typing import Dict, Any, Optional
from ..base_extract_worker import BaseWorker
from ...utils.config_manager import get_config_manager

logger = logging.getLogger(__name__)


def build_retriever(config: Optional[Dict[str, Any]] = None) -> BaseWorker:
    """
    Build EnhancedRetriever for LLM-first architecture.
    
    Args:
        config: Pipeline configuration
        
    Returns:
        Configured EnhancedRetriever instance
    """
    config_manager = get_config_manager()
    
    # Get retriever configuration using centralized config manager
    retriever_config = config_manager.get_section('retriever', config)
    
    try:
        from .retriever_enhanced import EnhancedRetriever
        logger.info("🚀 Using EnhancedRetriever for LLM-first architecture")
        logger.info("   Mode: Documents + raw text → LLM quotes → backtraced spans")
        return EnhancedRetriever(
            max_span_length=retriever_config.get('max_span_length', 400),
            min_confidence=retriever_config.get('min_confidence', 0.7)
        )
    except ImportError as e:
        logger.error(f"Cannot import EnhancedRetriever: {e}")
        raise RuntimeError("EnhancedRetriever is required but not available")


def get_retriever_info(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get information about the retriever that would be created.
    
    Args:
        config: Pipeline configuration
        
    Returns:
        Dictionary with retriever information
    """
    return {
        'type': 'enhanced_llm_first',
        'description': 'LLM-first retriever: documents + raw text → LLM quotes → backtraced spans',
        'llm_first_mode': True,
        'span_generation': 'llm_backtrace',
        'reliability': 'high',
        'fallback_available': False
    }
