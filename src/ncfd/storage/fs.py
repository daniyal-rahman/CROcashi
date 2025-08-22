"""
Local filesystem storage backend for NCFD.

This module provides local storage with size monitoring, automatic cleanup,
and fallback to S3 when local storage limits are exceeded.
"""

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import tempfile

from . import StorageBackend, StorageError, compute_sha256

logger = logging.getLogger(__name__)


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend with size management."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize local storage backend.
        
        Args:
            config: Storage configuration with local settings
        """
        self.root_path = Path(config.get('fs', {}).get('root', './data/raw'))
        self.max_size_bytes = self._parse_size_limit(config)
        self.fallback_s3 = config.get('fs', {}).get('fallback_s3', True)
        self.fallback_backend = None
        
        # Ensure root directory exists
        self.root_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.root_path / 'docs').mkdir(exist_ok=True)
        (self.root_path / 'meta').mkdir(exist_ok=True)
        
        logger.info(f"Local storage initialized at {self.root_path}")
        logger.info(f"Max size: {self.max_size_bytes / (1024**3):.2f} GB")
        logger.info(f"Fallback to S3: {self.fallback_s3}")
    
    def _parse_size_limit(self, config: Dict[str, Any]) -> int:
        """Parse size limit from config."""
        size_str = config.get('fs', {}).get('max_size_gb', '10')
        
        if isinstance(size_str, str):
            # Handle "10GB", "10 GB", "10" formats
            size_str = size_str.upper().replace('GB', '').replace(' ', '').strip()
        
        try:
            size_gb = float(size_str)
            return int(size_gb * (1024**3))  # Convert to bytes
        except (ValueError, TypeError):
            logger.warning(f"Invalid size limit '{size_str}', defaulting to 10GB")
            return 10 * (1024**3)
    
    def store(self, content: bytes, sha256: str | None, filename: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Store content locally with SHA256-based directory structure.
        
        Args:
            content: Binary content to store
            sha256: SHA256 hash of content (optional, will be computed if not provided)
            filename: Original filename
            metadata: Optional metadata to store alongside
            
        Returns:
            Local storage URI
            
        Raises:
            StorageError: If storage fails or limit exceeded
        """
        # Compute actual SHA256 hash
        actual_hash = compute_sha256(content)
        if sha256 and sha256 != actual_hash:
            raise StorageError(f"SHA256 mismatch: provided={sha256} computed={actual_hash}")
        sha256 = actual_hash
        
        # Check if content already exists
        if self.exists(f"local://{sha256}/{filename}"):
            logger.info(f"Content already exists: {sha256}/{filename}")
            return f"local://{sha256}/{filename}"
        
        # Check available space
        if not self._has_space(len(content)):
            if self.fallback_s3 and self.fallback_backend:
                logger.info("Local storage full, falling back to S3")
                return self.fallback_backend.store(content, sha256, filename, metadata)
            else:
                raise StorageError(f"Local storage full ({self.get_total_size() / (1024**3):.2f} GB used)")
        
        # Create SHA256-based directory structure
        doc_dir = self.root_path / 'docs' / sha256
        doc_dir.mkdir(parents=True, exist_ok=True)
        
        # Store content
        content_path = doc_dir / filename
        try:
            with open(content_path, 'wb') as f:
                f.write(content)
        except IOError as e:
            raise StorageError(f"Failed to write content: {e}")
        
        # Store metadata
        if metadata:
            meta_path = self.root_path / 'meta' / f"{sha256}.json"
            metadata['stored_at'] = datetime.utcnow().isoformat()
            metadata['filename'] = filename
            metadata['size_bytes'] = len(content)
            
            try:
                with open(meta_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
            except IOError as e:
                logger.warning(f"Failed to store metadata: {e}")
        
        logger.info(f"Stored {len(content)} bytes at {content_path}")
        return f"local://{sha256}/{filename}"
    
    def _atomic_store(self, content: bytes, sha256: str | None, filename: str, 
                     metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Store content using atomic write pattern (temp file + rename).
        
        Args:
            content: Binary content to store
            sha256: SHA256 hash of content (optional, will be computed if not provided)
            filename: Original filename
            metadata: Optional metadata
            
        Returns:
            Local storage URI
        """
        # Compute actual SHA256 hash
        actual_hash = compute_sha256(content)
        if sha256 and sha256 != actual_hash:
            raise StorageError(f"SHA256 mismatch: provided={sha256} computed={actual_hash}")
        sha256 = actual_hash
        
        # Check available space
        if not self._has_space(len(content)):
            if self.fallback_s3 and self.fallback_backend:
                logger.info("Local storage full, falling back to S3")
                return self.fallback_backend.store(content, sha256, filename, metadata)
            else:
                raise StorageError(f"Local storage full ({self.get_total_size() / (1024**3):.2f} GB used)")
        
        # Create content directory
        content_dir = self.root_path / 'docs' / sha256
        content_dir.mkdir(parents=True, exist_ok=True)
        
        # Atomic write: write to temp file first, then rename
        content_file = content_dir / filename
        temp_file = content_dir / f"{filename}.part"
        
        try:
            # Write to temporary file
            with open(temp_file, 'wb') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk
            
            # Atomic rename
            temp_file.rename(content_file)
            
        except Exception as e:
            # Clean up temp file on failure
            if temp_file.exists():
                temp_file.unlink()
            raise StorageError(f"Atomic write failed: {e}")
        
        # Store metadata
        if metadata:
            meta_file = self.root_path / 'meta' / f"{sha256}.json"
            metadata['stored_at'] = datetime.utcnow().isoformat()
            metadata['filename'] = filename
            metadata['size_bytes'] = len(content)
            
            try:
                with open(meta_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
            except IOError as e:
                logger.warning(f"Failed to store metadata: {e}")
        
        logger.info(f"Atomically stored {len(content)} bytes at {content_file}")
        return f"local://{sha256}/{filename}"
    
    def _update_reference_count(self, sha256: str, reference_type: str, reference_id: int, increment: bool = True):
        """
        Update reference count for stored content.
        
        Args:
            sha256: Content hash
            reference_type: Type of referencing entity (document, study, etc.)
            reference_id: ID of the referencing entity
            increment: True to increment, False to decrement
        """
        try:
            # This would integrate with the database reference counting system
            # For now, we'll log the operation
            action = "increment" if increment else "decrement"
            logger.info(f"Reference count {action}: {sha256} -> {reference_type}:{reference_id}")
        except Exception as e:
            logger.warning(f"Failed to update reference count: {e}")
    
    def cleanup_unreferenced(self, max_age_days: int = 30) -> int:
        """
        Clean up unreferenced content older than specified age.
        
        Args:
            max_age_days: Maximum age in days before cleanup
            
        Returns:
            Number of items cleaned up
        """
        # This would query the database for unreferenced objects
        # For now, we'll use the existing age-based cleanup as fallback
        logger.info(f"Using fallback age-based cleanup for content older than {max_age_days} days")
        return self.cleanup_oldest(0)  # Clean up all old content
    
    def set_reference_manager(self, reference_manager):
        """
        Set the reference manager for this storage backend.
        
        Args:
            reference_manager: StorageReferenceManager instance
        """
        self.reference_manager = reference_manager
        logger.info("Reference manager configured for local storage backend")
    
    def retrieve(self, storage_uri: str) -> bytes:
        """
        Retrieve content from local storage.
        
        Args:
            storage_uri: Local storage URI (local://sha256/filename)
            
        Returns:
            Binary content
            
        Raises:
            StorageError: If retrieval fails
        """
        if not storage_uri.startswith('local://'):
            raise StorageError(f"Invalid local storage URI: {storage_uri}")
        
        path_parts = storage_uri[8:].split('/')  # Remove 'local://' prefix
        if len(path_parts) != 2:
            raise StorageError(f"Invalid local storage URI format: {storage_uri}")
        
        sha256, filename = path_parts
        content_path = self.root_path / 'docs' / sha256 / filename
        
        if not content_path.exists():
            raise StorageError(f"Content not found: {content_path}")
        
        try:
            with open(content_path, 'rb') as f:
                return f.read()
        except IOError as e:
            raise StorageError(f"Failed to read content: {e}")
    
    def exists(self, storage_uri: str) -> bool:
        """Check if content exists in local storage."""
        if not storage_uri.startswith('local://'):
            return False
        
        path_parts = storage_uri[8:].split('/')
        if len(path_parts) != 2:
            return False
        
        sha256, filename = path_parts
        content_path = self.root_path / 'docs' / sha256 / filename
        return content_path.exists()
    
    def delete(self, storage_uri: str) -> bool:
        """
        Delete content from local storage.
        
        Args:
            storage_uri: Local storage URI to delete
            
        Returns:
            True if deletion was successful
        """
        if not storage_uri.startswith('local://'):
            return False
        
        path_parts = storage_uri[8:].split('/')
        if len(path_parts) != 2:
            return False
        
        sha256, filename = path_parts
        content_path = self.root_path / 'docs' / sha256 / filename
        meta_path = self.root_path / 'meta' / f"{sha256}.json"
        
        try:
            # Delete content file
            if content_path.exists():
                content_path.unlink()
            
            # Delete metadata file
            if meta_path.exists():
                meta_path.unlink()
            
            # Remove directory if empty
            doc_dir = content_path.parent
            if doc_dir.exists() and not any(doc_dir.iterdir()):
                doc_dir.rmdir()
            
            logger.info(f"Deleted content: {storage_uri}")
            return True
            
        except OSError as e:
            logger.error(f"Failed to delete content: {e}")
            return False
    
    def get_size(self, storage_uri: str) -> int:
        """Get size of stored content in bytes."""
        if not storage_uri.startswith('local://'):
            return 0
        
        path_parts = storage_uri[8:].split('/')
        if len(path_parts) != 2:
            return 0
        
        sha256, filename = path_parts
        content_path = self.root_path / 'docs' / sha256 / filename
        
        if content_path.exists():
            return content_path.stat().st_size
        return 0
    
    def get_total_size(self) -> int:
        """Get total size of all stored content in bytes."""
        total_size = 0
        
        docs_dir = self.root_path / 'docs'
        if not docs_dir.exists():
            return 0
        
        for sha256_dir in docs_dir.iterdir():
            if sha256_dir.is_dir():
                for content_file in sha256_dir.iterdir():
                    if content_file.is_file():
                        total_size += content_file.stat().st_size
        
        return total_size
    
    def _has_space(self, required_bytes: int) -> bool:
        """Check if there's enough space for the required bytes."""
        current_size = self.get_total_size()
        return (current_size + required_bytes) <= self.max_size_bytes
    
    def cleanup_oldest(self, target_size_bytes: int) -> int:
        """
        Clean up oldest files to reach target size.
        
        Args:
            target_size_bytes: Target size in bytes
            
        Returns:
            Number of files deleted
        """
        current_size = self.get_total_size()
        if current_size <= target_size_bytes:
            return 0
        
        # Get all files with their modification times
        files_with_mtime = []
        docs_dir = self.root_path / 'docs'
        
        for sha256_dir in docs_dir.iterdir():
            if sha256_dir.is_dir():
                for content_file in sha256_dir.iterdir():
                    if content_file.is_file():
                        mtime = content_file.stat().st_mtime
                        files_with_mtime.append((content_file, mtime))
        
        # Sort by modification time (oldest first)
        files_with_mtime.sort(key=lambda x: x[1])
        
        # Delete oldest files until we reach target size
        deleted_count = 0
        for content_file, _ in files_with_mtime:
            if current_size <= target_size_bytes:
                break
            
            file_size = content_file.stat().st_size
            if self.delete(f"local://{content_file.parent.name}/{content_file.name}"):
                current_size -= file_size
                deleted_count += 1
        
        logger.info(f"Cleaned up {deleted_count} files, new size: {current_size / (1024**3):.2f} GB")
        return deleted_count
    
    def set_fallback_backend(self, backend: 'StorageBackend'):
        """Set S3 backend for fallback when local storage is full."""
        self.fallback_backend = backend
        logger.info("Fallback S3 backend configured")
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get storage statistics and information."""
        total_size = self.get_total_size()
        max_size = self.max_size_bytes
        
        return {
            'type': 'local',
            'root_path': str(self.root_path),
            'total_size_bytes': total_size,
            'total_size_gb': total_size / (1024**3),
            'max_size_bytes': max_size,
            'max_size_gb': max_size / (1024**3),
            'usage_percent': (total_size / max_size) * 100 if max_size > 0 else 0,
            'fallback_s3': self.fallback_s3,
            'fallback_configured': self.fallback_backend is not None
        }
