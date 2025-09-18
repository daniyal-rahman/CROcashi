"""
Intelligent Document Text Cache

Provides runtime document text caching with memory + database storage.
"""

import logging
import time
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from .text_generator import RuntimeTextGenerator
from .config import RUNTIME_TEXT_CONFIG
from ...db.models import Document, DocumentText
from ...db.session import get_session

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry for document text."""
    text: str
    source: str
    cached_at: datetime
    access_count: int
    last_accessed: datetime
    metadata: Optional[Dict[str, Any]] = None


class DocumentTextCache:
    """Runtime document text cache with intelligent retrieval."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or RUNTIME_TEXT_CONFIG
        self.cache_config = self.config.get("cache", {})
        self.quality_config = self.config.get("quality", {})
        
        # Memory cache
        self.memory_cache: Dict[str, CacheEntry] = {}
        self.max_cache_size = self.cache_config.get("max_documents", 1000)
        self.ttl_hours = self.cache_config.get("ttl_hours", 24)
        
        # Statistics
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "api_calls": 0,
            "cache_evictions": 0
        }
        
        # Initialize text generator
        self.text_generator = RuntimeTextGenerator(self.config)
        
        logger.info(f"Document text cache initialized (max_size={self.max_cache_size}, ttl={self.ttl_hours}h)")
    
    async def get_document_text(self, doc_id: str, prefer_fulltext: bool = True) -> str:
        """
        Get document text with intelligent caching and runtime generation.
        
        Args:
            doc_id: Document ID
            prefer_fulltext: Whether to prefer full text over abstract
            
        Returns:
            Document text content
        """
        try:
            # 1. Check memory cache first
            if doc_id in self.memory_cache:
                entry = self.memory_cache[doc_id]
                if self._is_cache_entry_valid(entry):
                    entry.access_count += 1
                    entry.last_accessed = datetime.now(timezone.utc)
                    self.cache_stats["hits"] += 1
                    
                    logger.debug(f"Cache hit for doc {doc_id} (source: {entry.source}, length: {len(entry.text)})")
                    return entry.text
                else:
                    # Remove expired entry
                    del self.memory_cache[doc_id]
            
            # 2. Check database cache
            db_text = await self._get_from_database(doc_id, prefer_fulltext)
            if db_text:
                self._cache_in_memory(doc_id, db_text, "database")
                self.cache_stats["hits"] += 1
                logger.debug(f"Database cache hit for doc {doc_id} (length: {len(db_text)})")
                return db_text
            
            # 3. Generate at runtime
            self.cache_stats["misses"] += 1
            self.cache_stats["api_calls"] += 1
            
            logger.info(f"Generating text at runtime for doc {doc_id}")
            runtime_text = await self.text_generator.generate_text(doc_id)
            
            if runtime_text:
                # Cache the generated text
                self._cache_in_memory(doc_id, runtime_text, "runtime")
                await self._store_in_database(doc_id, runtime_text)
                
                logger.info(f"Generated and cached {len(runtime_text)} chars for doc {doc_id}")
                return runtime_text
            else:
                logger.warning(f"No text generated for doc {doc_id}")
                return ""
                
        except Exception as e:
            logger.error(f"Error getting text for doc {doc_id}: {e}")
            return ""
    
    def _is_cache_entry_valid(self, entry: CacheEntry) -> bool:
        """Check if cache entry is still valid."""
        now = datetime.now(timezone.utc)
        age_hours = (now - entry.cached_at).total_seconds() / 3600
        return age_hours < self.ttl_hours
    
    async def _get_from_database(self, doc_id: str, prefer_fulltext: bool = True) -> str:
        """Get text from database cache."""
        try:
            with get_session() as session:
                # Resolve external doc_id to internal doc_id
                internal_doc_id = self._resolve_external_doc_id(session, doc_id)
                if not internal_doc_id:
                    return ""
                
                doc_text = session.query(DocumentText).filter(
                    DocumentText.doc_id == internal_doc_id
                ).first()
                
                if not doc_text:
                    return ""
                
                # Try fulltext first if preferred
                if prefer_fulltext and doc_text.fulltext_text:
                    fulltext_length = len(doc_text.fulltext_text)
                    min_length = self.quality_config.get("min_fulltext_length", 500)
                    if fulltext_length >= min_length:
                        return doc_text.fulltext_text
                
                # Fallback to abstract
                if doc_text.abstract_text:
                    abstract_length = len(doc_text.abstract_text)
                    min_length = self.quality_config.get("min_abstract_length", 100)
                    if abstract_length >= min_length:
                        return doc_text.abstract_text
                
                return ""
                
        except Exception as e:
            logger.error(f"Error getting text from database for doc {doc_id}: {e}")
            return ""
    
    def _resolve_external_doc_id(self, session, doc_id: str) -> Optional[int]:
        """Resolve external doc_id format to internal doc_id."""
        try:
            if doc_id.startswith('db:'):
                return int(doc_id.split(':')[1])
            elif doc_id.startswith('pmid:'):
                pmid = doc_id.split(':')[1]
                doc = session.query(Document).filter(Document.pmid == pmid).first()
                return doc.doc_id if doc else None
            elif doc_id.startswith('pmcid:'):
                pmcid = doc_id.split(':')[1]
                doc = session.query(Document).filter(Document.pmcid == pmcid).first()
                return doc.doc_id if doc else None
            else:
                # Assume it's already an internal doc_id
                return int(doc_id)
        except (ValueError, AttributeError):
            return None
    
    def _cache_in_memory(self, doc_id: str, text: str, source: str, metadata: Optional[Dict[str, Any]] = None):
        """Cache text in memory."""
        try:
            # Check cache size limit
            if len(self.memory_cache) >= self.max_cache_size:
                self._evict_oldest_entries()
            
            # Create cache entry
            entry = CacheEntry(
                text=text,
                source=source,
                cached_at=datetime.now(timezone.utc),
                access_count=1,
                last_accessed=datetime.now(timezone.utc),
                metadata=metadata
            )
            
            self.memory_cache[doc_id] = entry
            logger.debug(f"Cached {len(text)} chars for doc {doc_id} in memory (source: {source})")
            
        except Exception as e:
            logger.error(f"Error caching text in memory for doc {doc_id}: {e}")
    
    def _evict_oldest_entries(self):
        """Evict oldest cache entries to make room."""
        try:
            # Sort by last accessed time and remove oldest 10%
            sorted_entries = sorted(
                self.memory_cache.items(),
                key=lambda x: x[1].last_accessed
            )
            
            evict_count = max(1, len(sorted_entries) // 10)
            for doc_id, _ in sorted_entries[:evict_count]:
                del self.memory_cache[doc_id]
                self.cache_stats["cache_evictions"] += 1
            
            logger.debug(f"Evicted {evict_count} cache entries")
            
        except Exception as e:
            logger.error(f"Error evicting cache entries: {e}")
    
    async def _store_in_database(self, doc_id: str, text: str):
        """Store generated text in database."""
        try:
            with get_session() as session:
                # Resolve external doc_id to internal doc_id
                internal_doc_id = self._resolve_external_doc_id(session, doc_id)
                if not internal_doc_id:
                    return
                
                # Check if document_text record exists
                doc_text = session.query(DocumentText).filter(
                    DocumentText.doc_id == internal_doc_id
                ).first()
                
                if doc_text:
                    # Update existing record
                    if len(text) >= self.quality_config.get("min_fulltext_length", 500):
                        doc_text.fulltext_text = text
                        doc_text.char_count_fulltext = len(text)
                        doc_text.fulltext_ttl_date = None  # No TTL for generated text
                    else:
                        doc_text.abstract_text = text
                        doc_text.char_count_abstract = len(text)
                else:
                    # Create new record
                    doc_text = DocumentText(
                        doc_id=internal_doc_id,
                        abstract_text=text if len(text) < self.quality_config.get("min_fulltext_length", 500) else None,
                        fulltext_text=text if len(text) >= self.quality_config.get("min_fulltext_length", 500) else None,
                        char_count_abstract=len(text) if len(text) < self.quality_config.get("min_fulltext_length", 500) else None,
                        char_count_fulltext=len(text) if len(text) >= self.quality_config.get("min_fulltext_length", 500) else None,
                        fulltext_ttl_date=None
                    )
                    session.add(doc_text)
                
                session.commit()
                logger.debug(f"Stored {len(text)} chars in database for doc {doc_id}")
                
        except Exception as e:
            logger.error(f"Error storing text in database for doc {doc_id}: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        hit_rate = 0
        if self.cache_stats["hits"] + self.cache_stats["misses"] > 0:
            hit_rate = self.cache_stats["hits"] / (self.cache_stats["hits"] + self.cache_stats["misses"])
        
        return {
            **self.cache_stats,
            "hit_rate": hit_rate,
            "memory_cache_size": len(self.memory_cache),
            "max_cache_size": self.max_cache_size
        }
    
    def clear_cache(self):
        """Clear memory cache."""
        self.memory_cache.clear()
        logger.info("Memory cache cleared")
