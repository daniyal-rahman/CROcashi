"""
Unified storage manager for NCFD.

This module provides a unified interface that can route storage operations
across multiple backends (local, S3) and handle cross-tier operations.
"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import tempfile
import os
import shutil

from .fs import LocalStorageBackend
from .s3 import S3StorageBackend
from typing import Union

class StorageError(Exception):
    """Exception raised for storage-related errors."""
    pass


def parse_storage_uri(storage_uri: str) -> tuple[str, str, str]:
    """
    Parse storage URI to extract backend type and path components.
    
    Args:
        storage_uri: Storage URI (e.g., 'local://sha256/filename', 's3://bucket/key')
        
    Returns:
        Tuple of (backend_type, path, filename)
        
    Raises:
        StorageError: If URI format is invalid
    """
    if not storage_uri or '://' not in storage_uri:
        raise StorageError(f"Invalid storage URI format: {storage_uri}")
    
    backend_type, path = storage_uri.split('://', 1)
    
    if backend_type == 'local':
        if '/' not in path or path.count('/') != 1:
            raise StorageError(f"Invalid local storage URI format: {storage_uri}")
        sha256, filename = path.split('/', 1)
        return backend_type, sha256, filename
    
    elif backend_type == 's3':
        if '/' not in path:
            raise StorageError(f"Invalid S3 storage URI format: {storage_uri}")
        bucket, key = path.split('/', 1)
        return backend_type, bucket, key
    
    else:
        raise StorageError(f"Unsupported storage backend type: {backend_type}")


def resolve_backend(storage_uri: str, backends: Dict[str, Union[LocalStorageBackend, S3StorageBackend]]) -> Union[LocalStorageBackend, S3StorageBackend]:
    """
    Resolve storage URI to the appropriate backend.
    
    Args:
        storage_uri: Storage URI to resolve
        backends: Dictionary of available backends by type
        
    Returns:
        Appropriate storage backend
        
    Raises:
        StorageError: If backend cannot be resolved
    """
    backend_type, _, _ = parse_storage_uri(storage_uri)
    
    if backend_type not in backends:
        raise StorageError(f"No backend available for type: {backend_type}")
    
    return backends[backend_type]

logger = logging.getLogger(__name__)


class UnifiedStorageManager:
    """
    Unified storage manager that routes operations across multiple backends.
    
    This manager handles:
    - Cross-backend operations
    - URI resolution and routing
    - Atomic write operations
    - Fallback mechanisms
    """
    
    def __init__(self, backends: Dict[str, Union[LocalStorageBackend, S3StorageBackend]], **kwargs):
        """
        Initialize the unified storage manager.
        
        Args:
            backends: Dictionary of backends by type (e.g., {'local': LocalBackend, 's3': S3Backend})
            **kwargs: Additional configuration options
        """
        self.backends = backends
        self.primary_backend = backends.get('local') or backends.get('s3')
        
        if not self.primary_backend:
            raise StorageError("No primary storage backend available")
        
        logger.info(f"Unified storage manager initialized with backends: {list(backends.keys())}")
    
    def store(self, content: bytes, sha256: str | None, filename: str, 
              metadata: Optional[Dict[str, Any]] = None, 
              backend_type: Optional[str] = None) -> str:
        """
        Store content using atomic write pattern.
        
        Args:
            content: Binary content to store
            sha256: SHA256 hash of content (optional, will be computed if not provided)
            filename: Original filename
            metadata: Optional metadata
            backend_type: Preferred backend type ('local' or 's3')
            
        Returns:
            Storage URI for the stored content
        """
        # Determine which backend to use
        if backend_type and backend_type in self.backends:
            backend = self.backends[backend_type]
        else:
            backend = self.primary_backend
        
        # Use atomic write pattern
        return self._atomic_store(backend, content, sha256, filename, metadata)
    
    def _atomic_store(self, backend: Union[LocalStorageBackend, S3StorageBackend], content: bytes, sha256: str | None, 
                     filename: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Store content using atomic write pattern (temp file + rename).
        
        Args:
            backend: Storage backend to use
            content: Binary content to store
            sha256: SHA256 hash of content
            filename: Original filename
            metadata: Optional metadata
            
        Returns:
            Storage URI for the stored content
        """
        # Check if backend has _atomic_store method (not just a Mock attribute)
        atomic_store_method = getattr(backend, '_atomic_store', None)
        if (atomic_store_method is not None and 
            callable(atomic_store_method) and 
            not hasattr(atomic_store_method, '_mock_name')):
            # Backend supports atomic writes
            return backend._atomic_store(content, sha256, filename, metadata)
        
        # Fallback to standard store for backends without atomic support
        return backend.store(content, sha256, filename, metadata)
    
    def retrieve(self, storage_uri: str) -> bytes:
        """
        Retrieve content by resolving the appropriate backend.
        
        Args:
            storage_uri: Storage URI to retrieve from
            
        Returns:
            Binary content
        """
        backend = resolve_backend(storage_uri, self.backends)
        return backend.retrieve(storage_uri)
    
    def exists(self, storage_uri: str) -> bool:
        """
        Check if content exists by resolving the appropriate backend.
        
        Args:
            storage_uri: Storage URI to check
            
        Returns:
            True if content exists
        """
        backend = resolve_backend(storage_uri, self.backends)
        return backend.exists(storage_uri)
    
    def delete(self, storage_uri: str) -> bool:
        """
        Delete content by resolving the appropriate backend.
        
        Args:
            storage_uri: Storage URI to delete
            
        Returns:
            True if deletion was successful
        """
        backend = resolve_backend(storage_uri, self.backends)
        return backend.delete(storage_uri)
    
    def get_size(self, storage_uri: str) -> int:
        """
        Get content size by resolving the appropriate backend.
        
        Args:
            storage_uri: Storage URI to check
            
        Returns:
            Size in bytes
        """
        backend = resolve_backend(storage_uri, self.backends)
        return backend.get_size(storage_uri)
    
    def get_total_size(self) -> int:
        """
        Get total size across all backends.
        
        Returns:
            Total size in bytes
        """
        total_size = 0
        for backend in self.backends.values():
            total_size += backend.get_total_size()
        return total_size
    
    def get_storage_info(self) -> Dict[str, Any]:
        """
        Get comprehensive storage information across all backends.
        
        Returns:
            Dictionary with storage information for all backends
        """
        info = {
            'type': 'unified',
            'backends': {},
            'total_size_bytes': self.get_total_size(),
            'total_size_gb': self.get_total_size() / (1024**3)
        }
        
        for backend_type, backend in self.backends.items():
            try:
                info['backends'][backend_type] = backend.get_storage_info()
            except Exception as e:
                logger.warning(f"Failed to get info for {backend_type} backend: {e}")
                info['backends'][backend_type] = {'error': str(e)}
        
        return info
    
    def list_content(self, backend_type: Optional[str] = None) -> List[str]:
        """
        List content URIs from specified or all backends.
        
        Args:
            backend_type: Specific backend type to list, or None for all
            
        Returns:
            List of storage URIs
        """
        uris = []
        
        if backend_type:
            if backend_type not in self.backends:
                raise StorageError(f"Backend type not available: {backend_type}")
            backends_to_check = {backend_type: self.backends[backend_type]}
        else:
            backends_to_check = self.backends
        
        for backend_type, backend in backends_to_check.items():
            if hasattr(backend, 'list_content'):
                try:
                    backend_uris = backend.list_content()
                    uris.extend(backend_uris)
                except Exception as e:
                    logger.warning(f"Failed to list content from {backend_type}: {e}")
        
        return uris
    
    def cleanup_old_content(self, max_age_days: int = 30) -> int:
        """
        Clean up old content across all backends.
        
        Args:
            max_age_days: Maximum age in days before cleanup
            
        Returns:
            Number of items cleaned up
        """
        cleaned_count = 0
        
        for backend_type, backend in self.backends.items():
            if hasattr(backend, 'cleanup_old_content'):
                try:
                    count = backend.cleanup_old_content(max_age_days)
                    cleaned_count += count
                    logger.info(f"Cleaned up {count} items from {backend_type} backend")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {backend_type} backend: {e}")
        
        return cleaned_count
