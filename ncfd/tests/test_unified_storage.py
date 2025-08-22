"""
Tests for the unified storage manager.

This module tests the UnifiedStorageManager class which provides
cross-backend storage operations and URI resolution.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from ncfd.storage import (
    create_unified_storage_manager, parse_storage_uri, resolve_backend, StorageError
)
from ncfd.storage.manager import UnifiedStorageManager, StorageError as ManagerStorageError


class TestUnifiedStorageManager:
    """Test the UnifiedStorageManager implementation."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_local_backend(self):
        """Create mock local storage backend."""
        backend = Mock()
        backend.get_total_size.return_value = 1024
        backend.get_storage_info.return_value = {
            'type': 'local',
            'total_size_bytes': 1024,
            'total_size_gb': 1024 / (1024**3)
        }
        backend.list_content.return_value = ['local://hash1/file1.txt']
        backend.cleanup_old_content.return_value = 2
        return backend
    
    @pytest.fixture
    def mock_s3_backend(self):
        """Create mock S3 storage backend."""
        backend = Mock()
        backend.get_total_size.return_value = 2048
        backend.get_storage_info.return_value = {
            'type': 's3',
            'total_size_bytes': 2048,
            'total_size_gb': 2048 / (1024**3)
        }
        backend.list_content.return_value = ['s3://bucket/hash2/file2.txt']
        backend.cleanup_old_content.return_value = 1
        return backend
    
    @pytest.fixture
    def unified_manager(self, mock_local_backend, mock_s3_backend):
        """Create unified storage manager with mock backends."""
        backends = {
            'local': mock_local_backend,
            's3': mock_s3_backend
        }
        return UnifiedStorageManager(backends)
    
    def test_initialization(self, mock_local_backend, mock_s3_backend):
        """Test unified storage manager initialization."""
        backends = {
            'local': mock_local_backend,
            's3': mock_s3_backend
        }
        
        manager = UnifiedStorageManager(backends)
        
        assert manager.backends == backends
        assert manager.primary_backend == mock_local_backend
        assert 'local' in manager.backends
        assert 's3' in manager.backends
    
    def test_initialization_no_backends(self):
        """Test initialization with no backends."""
        with pytest.raises(ManagerStorageError, match="No primary storage backend available"):
            UnifiedStorageManager({})
    
    def test_initialization_s3_only(self, mock_s3_backend):
        """Test initialization with only S3 backend."""
        backends = {'s3': mock_s3_backend}
        manager = UnifiedStorageManager(backends)
        
        assert manager.primary_backend == mock_s3_backend
        assert 's3' in manager.backends
        assert 'local' not in manager.backends
    
    def test_store_with_backend_preference(self, unified_manager, mock_s3_backend):
        """Test storing content with specific backend preference."""
        content = b"Test content"
        sha256 = "a" * 64
        filename = "test.txt"
        
        # Mock S3 backend store method
        mock_s3_backend.store.return_value = "s3://bucket/docs/hash/filename"
        
        storage_uri = unified_manager.store(
            content, sha256, filename, backend_type='s3'
        )
        
        assert storage_uri == "s3://bucket/docs/hash/filename"
        mock_s3_backend.store.assert_called_once_with(content, sha256, filename, None)
    
    def test_store_with_primary_backend(self, unified_manager, mock_local_backend):
        """Test storing content with primary backend."""
        content = b"Test content"
        sha256 = "a" * 64
        filename = "test.txt"
        
        # Mock local backend store method
        mock_local_backend.store.return_value = "local://hash/filename"
        
        storage_uri = unified_manager.store(content, sha256, filename)
        
        assert storage_uri == "local://hash/filename"
        mock_local_backend.store.assert_called_once_with(content, sha256, filename, None)
    
    def test_retrieve_cross_backend(self, unified_manager, mock_s3_backend):
        """Test retrieving content from S3 backend."""
        storage_uri = "s3://bucket/docs/hash/filename"
        expected_content = b"S3 content"
        
        # Mock S3 backend retrieve method
        mock_s3_backend.retrieve.return_value = expected_content
        
        content = unified_manager.retrieve(storage_uri)
        
        assert content == expected_content
        mock_s3_backend.retrieve.assert_called_once_with(storage_uri)
    
    def test_exists_cross_backend(self, unified_manager, mock_s3_backend):
        """Test checking existence across backends."""
        storage_uri = "s3://bucket/docs/hash/filename"
        
        # Mock S3 backend exists method
        mock_s3_backend.exists.return_value = True
        
        exists = unified_manager.exists(storage_uri)
        
        assert exists is True
        mock_s3_backend.exists.assert_called_once_with(storage_uri)
    
    def test_delete_cross_backend(self, unified_manager, mock_s3_backend):
        """Test deleting content across backends."""
        storage_uri = "s3://bucket/docs/hash/filename"
        
        # Mock S3 backend delete method
        mock_s3_backend.delete.return_value = True
        
        success = unified_manager.delete(storage_uri)
        
        assert success is True
        mock_s3_backend.delete.assert_called_once_with(storage_uri)
    
    def test_get_size_cross_backend(self, unified_manager, mock_s3_backend):
        """Test getting content size across backends."""
        storage_uri = "s3://bucket/docs/hash/filename"
        expected_size = 1024
        
        # Mock S3 backend get_size method
        mock_s3_backend.get_size.return_value = expected_size
        
        size = unified_manager.get_size(storage_uri)
        
        assert size == expected_size
        mock_s3_backend.get_size.assert_called_once_with(storage_uri)
    
    def test_get_total_size_across_backends(self, unified_manager):
        """Test getting total size across all backends."""
        total_size = unified_manager.get_total_size()
        
        # Should sum both backends: 1024 + 2048 = 3072
        assert total_size == 3072
    
    def test_get_storage_info(self, unified_manager):
        """Test getting comprehensive storage information."""
        info = unified_manager.get_storage_info()
        
        assert info['type'] == 'unified'
        assert info['total_size_bytes'] == 3072
        assert info['total_size_gb'] == 3072 / (1024**3)
        assert 'local' in info['backends']
        assert 's3' in info['backends']
        assert info['backends']['local']['type'] == 'local'
        assert info['backends']['s3']['type'] == 's3'
    
    def test_list_content_all_backends(self, unified_manager):
        """Test listing content from all backends."""
        uris = unified_manager.list_content()
        
        # Should combine content from both backends
        expected_uris = [
            'local://hash1/file1.txt',
            's3://bucket/hash2/file2.txt'
        ]
        assert uris == expected_uris
    
    def test_list_content_specific_backend(self, unified_manager, mock_local_backend):
        """Test listing content from specific backend."""
        uris = unified_manager.list_content(backend_type='local')
        
        assert uris == ['local://hash1/file1.txt']
        mock_local_backend.list_content.assert_called_once()
    
    def test_list_content_invalid_backend(self, unified_manager):
        """Test listing content from invalid backend type."""
        with pytest.raises(ManagerStorageError, match="Backend type not available: invalid"):
            unified_manager.list_content(backend_type='invalid')
    
    def test_cleanup_old_content(self, unified_manager):
        """Test cleaning up old content across backends."""
        cleaned_count = unified_manager.cleanup_old_content(max_age_days=30)
        
        # Should sum cleanup from both backends: 2 + 1 = 3
        assert cleaned_count == 3
    
    def test_cleanup_backend_failure(self, unified_manager, mock_local_backend):
        """Test cleanup continues when one backend fails."""
        # Make local backend cleanup fail
        mock_local_backend.cleanup_old_content.side_effect = Exception("Cleanup failed")
        
        # Should still succeed with S3 backend
        cleaned_count = unified_manager.cleanup_old_content(max_age_days=30)
        
        assert cleaned_count == 1  # Only S3 backend succeeded


class TestUnifiedStorageFactory:
    """Test the unified storage manager factory function."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    def test_create_unified_manager_local_and_s3(self, temp_dir):
        """Test creating unified manager with both local and S3 backends."""
        config = {
            'fs': {
                'root': str(temp_dir),
                'max_size_gb': '1',
                'fallback_s3': False
            },
            's3': {
                'bucket': 'test-bucket',
                'access_key': 'test-key',
                'secret_key': 'test-secret',
                'endpoint_url': 'http://localhost:9000',
                'region': 'us-east-1',
                'use_ssl': False
            }
        }
        
        # Mock S3StorageBackend creation to avoid boto3 dependency
        with patch('ncfd.storage.s3.S3StorageBackend') as mock_s3_class:
            mock_s3_instance = Mock()
            mock_s3_class.return_value = mock_s3_instance
            
            manager = create_unified_storage_manager(config)
            
            assert isinstance(manager, UnifiedStorageManager)
            assert 'local' in manager.backends
            assert 's3' in manager.backends
    
    def test_create_unified_manager_local_only(self, temp_dir):
        """Test creating unified manager with only local backend."""
        config = {
            'fs': {
                'root': str(temp_dir),
                'max_size_gb': '1',
                'fallback_s3': False
            }
        }
        
        # Should succeed with local backend only
        manager = create_unified_storage_manager(config)
        assert isinstance(manager, UnifiedStorageManager)
        assert 'local' in manager.backends
        assert 's3' not in manager.backends
    
    def test_create_unified_manager_no_config(self):
        """Test creating unified manager with no configuration."""
        with pytest.raises(StorageError, match="Storage configuration is required"):
            create_unified_storage_manager({})


class TestUriParsing:
    """Test URI parsing and resolution functions."""
    
    def test_parse_local_uri(self):
        """Test parsing local storage URI."""
        backend_type, sha256, filename = parse_storage_uri("local://hash123/filename.txt")
        
        assert backend_type == "local"
        assert sha256 == "hash123"
        assert filename == "filename.txt"
    
    def test_parse_s3_uri(self):
        """Test parsing S3 storage URI."""
        backend_type, bucket, key = parse_storage_uri("s3://bucket-name/docs/hash/filename.txt")
        
        assert backend_type == "s3"
        assert bucket == "bucket-name"
        assert key == "docs/hash/filename.txt"
    
    def test_parse_invalid_uri(self):
        """Test parsing invalid URI."""
        with pytest.raises(StorageError, match="Invalid storage URI format"):
            parse_storage_uri("invalid-uri")
    
    def test_parse_local_uri_invalid_format(self):
        """Test parsing local URI with invalid format."""
        with pytest.raises(StorageError, match="Invalid local storage URI format"):
            parse_storage_uri("local://invalid")
    
    def test_parse_s3_uri_invalid_format(self):
        """Test parsing S3 URI with invalid format."""
        with pytest.raises(StorageError, match="Invalid S3 storage URI format"):
            parse_storage_uri("s3://bucket")
    
    def test_parse_unsupported_backend(self):
        """Test parsing URI with unsupported backend type."""
        with pytest.raises(StorageError, match="Unsupported storage backend type"):
            parse_storage_uri("unsupported://path")
    
    def test_resolve_backend(self):
        """Test backend resolution."""
        mock_local = Mock()
        mock_s3 = Mock()
        backends = {'local': mock_local, 's3': mock_s3}
        
        # Resolve local backend
        backend = resolve_backend("local://hash/filename", backends)
        assert backend == mock_local
        
        # Resolve S3 backend
        backend = resolve_backend("s3://bucket/key", backends)
        assert backend == mock_s3
    
    def test_resolve_backend_not_available(self):
        """Test backend resolution when backend not available."""
        backends = {'local': Mock()}
        
        with pytest.raises(StorageError, match="No backend available for type: s3"):
            resolve_backend("s3://bucket/key", backends)
