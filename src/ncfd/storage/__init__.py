"""
Storage module for NCFD document storage.

This module provides a unified interface for storing documents in either
local filesystem or S3, with automatic fallback and size management.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, BinaryIO
from pathlib import Path
import logging
import hashlib





logger = logging.getLogger(__name__)


def compute_sha256(content: bytes) -> str:
    """
    Compute SHA256 hash of content.
    
    Args:
        content: Binary content to hash
        
    Returns:
        SHA256 hash as hexadecimal string
    """
    return hashlib.sha256(content).hexdigest()


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


def resolve_backend(storage_uri: str, backends: Dict[str, 'StorageBackend']) -> 'StorageBackend':
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


class StorageBackend(ABC):
    """Abstract base class for storage backends."""
    
    @abstractmethod
    def store(self, content: bytes, sha256: str | None, filename: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Store content with SHA256 hash and return storage URI.
        
        Args:
            content: Binary content to store
            sha256: SHA256 hash of content (optional, will be computed if not provided)
            filename: Original filename
            metadata: Optional metadata to store alongside
            
        Returns:
            Storage URI for the stored content
            
        Raises:
            StorageError: If storage fails or hash verification fails
        """
        pass
    
    @abstractmethod
    def retrieve(self, storage_uri: str) -> bytes:
        """
        Retrieve content by storage URI.
        
        Args:
            storage_uri: URI returned by store()
            
        Returns:
            Binary content
            
        Raises:
            StorageError: If retrieval fails
        """
        pass
    
    @abstractmethod
    def exists(self, storage_uri: str) -> bool:
        """
        Check if content exists at storage URI.
        
        Args:
            storage_uri: URI to check
            
        Returns:
            True if content exists
        """
        pass
    
    @abstractmethod
    def delete(self, storage_uri: str) -> bool:
        """
        Delete content at storage URI.
        
        Args:
            storage_uri: URI to delete
            
        Returns:
            True if deletion was successful
        """
        pass
    
    @abstractmethod
    def get_size(self, storage_uri: str) -> int:
        """
        Get size of stored content in bytes.
        
        Args:
            storage_uri: URI to check
            
        Returns:
            Size in bytes
        """
        pass
    
    @abstractmethod
    def get_total_size(self) -> int:
        """
        Get total size of all stored content in bytes.
        
        Returns:
            Total size in bytes
        """
        pass
    
    @abstractmethod
    def get_storage_info(self) -> Dict[str, Any]:
        """
        Get comprehensive storage information and statistics.
        
        Returns:
            Dictionary containing storage type, size info, configuration, and status
        """
        pass


class StorageError(Exception):
    """Exception raised for storage-related errors."""
    pass


def create_storage_backend(config: Dict[str, Any], **kwargs) -> StorageBackend:
    """
    Create storage backend based on configuration.
    
    Args:
        config: Storage configuration dictionary
        **kwargs: Additional arguments for dependency injection (e.g., client, resource)
        
    Returns:
        Configured storage backend
    """
    storage_type = config.get('kind', 's3')
    
    if storage_type == 'local':
        from .fs import LocalStorageBackend
        return LocalStorageBackend(config)
    elif storage_type == 's3':
        from .s3 import S3StorageBackend
        return S3StorageBackend(config, **kwargs)
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")


def create_unified_storage_manager(config: Dict[str, Any], **kwargs) -> 'UnifiedStorageManager':
    """
    Create a unified storage manager with multiple backends.
    
    Args:
        config: Storage configuration with multiple backend configurations
        
    Returns:
        Configured unified storage manager
        
    Raises:
        StorageError: If configuration is invalid or backend creation fails
    """
    if not config:
        raise StorageError("Storage configuration is required")
    
    backends = {}
    
    # Create local backend if configured
    if 'fs' in config:
        local_config = {'kind': 'local', 'fs': config['fs']}
        from .fs import LocalStorageBackend
        backends['local'] = LocalStorageBackend(local_config)
    
    # Create S3 backend if configured
    if 's3' in config:
        s3_config = {'kind': 's3', 's3': config['s3']}
        from .s3 import S3StorageBackend
        # Extract S3-specific kwargs for dependency injection
        s3_kwargs = {k: v for k, v in kwargs.items() if k in ['client', 'resource']}
        backends['s3'] = S3StorageBackend(s3_config, **s3_kwargs)
    
    if not backends:
        raise StorageError("No storage backends configured")
    
    from .manager import UnifiedStorageManager
    return UnifiedStorageManager(backends, **kwargs)


__all__ = [
    'StorageBackend',
    'StorageError',
    'compute_sha256',
    'parse_storage_uri',
    'resolve_backend',
    'create_storage_backend',
    'create_unified_storage_manager'
]
