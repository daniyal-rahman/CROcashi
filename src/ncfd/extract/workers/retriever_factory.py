"""
Retriever Factory

Creates the appropriate retriever based on configuration.
Defaults to LLM-first EnhancedRetriever for document + raw text retrieval.
"""

import logging
from typing import Dict, Any, Optional
from .base_worker import BaseWorker

logger = logging.getLogger(__name__)


def build_retriever(config: Optional[Dict[str, Any]] = None) -> BaseWorker:
    """
    Build retriever based on configuration.
    
    Args:
        config: Pipeline configuration
        
    Returns:
        Configured retriever instance (defaults to EnhancedRetriever)
    """
    config = config or {}
    
    # Get retriever configuration
    retriever_config = config.get('retriever', {})
    use_legacy_retriever = retriever_config.get('use_legacy_retriever', False)
    
    # Default: Use Enhanced Retriever for LLM-first architecture
    if not use_legacy_retriever:
        try:
            from .retriever_enhanced import EnhancedRetriever
            logger.info("🚀 Using EnhancedRetriever for LLM-first architecture")
            logger.info("   Mode: Documents + raw text → LLM quotes → backtraced spans")
            return EnhancedRetriever(
                max_span_length=retriever_config.get('max_span_length', 400),
                min_confidence=retriever_config.get('min_confidence', 0.7)
            )
        except ImportError as e:
            logger.warning(f"Enhanced retriever import failed: {e}")
            logger.info("🔄 Falling back to basic retriever")
    else:
        logger.warning("⚠️  DEPRECATED: Using legacy basic retriever (set use_legacy_retriever=false)")
            
    # Fallback to basic retriever (deprecated)
    try:
        from .retriever import Retriever
        logger.warning("⚠️  Using basic retriever (deprecated - low reliability)")
        return Retriever()
    except ImportError as e:
        logger.error(f"Cannot import any retriever: {e}")
        raise RuntimeError("No retriever implementation available")


def get_retriever_info(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get information about the retriever that would be created.
    
    Args:
        config: Pipeline configuration
        
    Returns:
        Dictionary with retriever information
    """
    config = config or {}
    retriever_config = config.get('retriever', {})
    
    use_legacy_retriever = retriever_config.get('use_legacy_retriever', False)
    
    if not use_legacy_retriever:
        return {
            'type': 'enhanced_llm_first',
            'description': 'LLM-first retriever: documents + raw text → LLM quotes → backtraced spans',
            'llm_first_mode': True,
            'span_generation': 'llm_backtrace',
            'reliability': 'high',
            'fallback_available': True
        }
    else:
        return {
            'type': 'basic_legacy',
            'description': 'Basic retriever (deprecated)',
            'llm_first_mode': False,
            'span_generation': 'basespan_triage',
            'reliability': 'medium',
            'deprecated': True
        }
