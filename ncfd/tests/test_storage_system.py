"""
Tests for the storage system including local storage, S3 fallback, and integration.

This module tests the complete storage functionality with proper mocking
to avoid requiring actual S3 credentials or local file system access.
"""

import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from ncfd.storage import (
    StorageBackend, StorageError, create_storage_backend
)

# Mock boto3 exceptions for S3 tests
try:
    from botocore.exceptions import ClientError
except ImportError:
    class ClientError(Exception):
        def __init__(self, error_response, operation_name):
            self.response = error_response
            self.operation_name = operation_name


class TestStorageBackend:
    """Test the abstract StorageBackend interface."""
    
    def test_abstract_methods(self):
        """Test that StorageBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            StorageBackend()


class TestLocalStorageBackend:
    """Test the LocalStorageBackend implementation."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def local_config(self, temp_dir):
        """Create local storage configuration."""
        return {
            'fs': {
                'root': str(temp_dir),
                'max_size_gb': '1',  # 1 GB limit
                'fallback_s3': True
            }
        }
    
    def test_initialization(self, local_config, temp_dir):
        """Test local storage backend initialization."""
        from ncfd.storage.fs import LocalStorageBackend
        backend = LocalStorageBackend(local_config)
        
        assert backend.root_path == temp_dir
        assert backend.max_size_bytes == 1024**3  # 1 GB in bytes
        assert backend.fallback_s3 is True
        assert backend.fallback_backend is None
        
        # Check that directories were created
        assert (temp_dir / 'docs').exists()
        assert (temp_dir / 'meta').exists()
    
    def test_parse_size_limit_various_formats(self, temp_dir):
        """Test parsing of various size limit formats."""
        from ncfd.storage.fs import LocalStorageBackend
        configs = [
            {'fs': {'max_size_gb': '5'}},
            {'fs': {'max_size_gb': '5GB'}},
            {'fs': {'max_size_gb': '5 GB'}},
            {'fs': {'max_size_gb': 10}},
        ]
        
        for config in configs:
            backend = LocalStorageBackend(config)
            expected_gb = float(str(config['fs']['max_size_gb']).replace('GB', '').replace(' ', ''))
            assert backend.max_size_bytes == int(expected_gb * (1024**3))
    
    def test_store_and_retrieve(self, local_config, temp_dir):
        """Test storing and retrieving content."""
        from ncfd.storage.fs import LocalStorageBackend
        backend = LocalStorageBackend(local_config)
        
        content = b"Test document content"
        import hashlib
        sha256 = hashlib.sha256(content).hexdigest()
        filename = "test.txt"
        metadata = {"source": "test"}
        
        # Store content
        storage_uri = backend.store(content, sha256, filename, metadata)
        assert storage_uri == f"local://{sha256}/{filename}"
        
        # Check that content exists
        assert backend.exists(storage_uri)
        
        # Retrieve content
        retrieved = backend.retrieve(storage_uri)
        assert retrieved == content
        
        # Check file structure
        content_path = temp_dir / 'docs' / sha256 / filename
        assert content_path.exists()
        
        # Check metadata
        meta_path = temp_dir / 'meta' / f"{sha256}.json"
        assert meta_path.exists()
        
        with open(meta_path) as f:
            stored_meta = json.load(f)
        assert stored_meta['filename'] == filename
        assert stored_meta['size_bytes'] == len(content)
        assert stored_meta['source'] == 'test'
    
    def test_store_duplicate_content(self, local_config):
        """Test that storing duplicate content returns existing URI."""
        from ncfd.storage.fs import LocalStorageBackend
        backend = LocalStorageBackend(local_config)
        
        content = b"Duplicate content"
        import hashlib
        sha256 = hashlib.sha256(content).hexdigest()
        filename = "duplicate.txt"
        
        # Store first time
        uri1 = backend.store(content, sha256, filename)
        
        # Store again
        uri2 = backend.store(content, sha256, filename)
        
        assert uri1 == uri2
        assert backend.exists(uri1)
    
    def test_sha256_verification_local(self, local_config):
        """Test that SHA256 verification prevents hash mismatches."""
        from ncfd.storage.fs import LocalStorageBackend
        from ncfd.storage import StorageError
        backend = LocalStorageBackend(local_config)
        
        content = b"Test content for hash verification"
        correct_sha256 = "a" * 64  # Wrong hash
        filename = "test.txt"
        
        # Should fail due to hash mismatch
        with pytest.raises(StorageError, match="SHA256 mismatch"):
            backend.store(content, correct_sha256, filename)
        
        # Should succeed with correct hash
        import hashlib
        correct_sha256 = hashlib.sha256(content).hexdigest()
        storage_uri = backend.store(content, correct_sha256, filename)
        assert backend.exists(storage_uri)
    
    def test_storage_size_limits(self, temp_dir):
        """Test storage size limits and fallback behavior."""
        from ncfd.storage.fs import LocalStorageBackend
        # Create config with very small limit
        config = {
            'fs': {
                'root': str(temp_dir),
                'max_size_gb': '0.000001',  # ~1KB limit
                'fallback_s3': True
            }
        }
        
        backend = LocalStorageBackend(config)
        
        # Try to store content larger than limit
        large_content = b"x" * 2000  # 2KB
        
        import hashlib
        correct_sha256 = hashlib.sha256(large_content).hexdigest()
        with pytest.raises(StorageError, match="Local storage full"):
            backend.store(large_content, correct_sha256, "large.txt")
    
    def test_retrieve_nonexistent(self, local_config):
        """Test retrieving non-existent content."""
        from ncfd.storage.fs import LocalStorageBackend
        backend = LocalStorageBackend(local_config)
        
        with pytest.raises(StorageError, match="Content not found"):
            backend.retrieve("local://nonexistent/file.txt")
    
    def test_invalid_uri_format(self, local_config):
        """Test handling of invalid URI formats."""
        from ncfd.storage.fs import LocalStorageBackend
        backend = LocalStorageBackend(local_config)
        
        # Test invalid URI
        assert not backend.exists("invalid://uri")
        assert backend.get_size("invalid://uri") == 0
        
        with pytest.raises(StorageError, match="Invalid local storage URI"):
            backend.retrieve("invalid://uri")
    
    def test_delete_content(self, local_config):
        """Test deleting content."""
        from ncfd.storage.fs import LocalStorageBackend
        backend = LocalStorageBackend(local_config)
        
        content = b"Content to delete"
        import hashlib
        sha256 = hashlib.sha256(content).hexdigest()
        filename = "delete.txt"
        
        # Store content
        storage_uri = backend.store(content, sha256, filename)
        assert backend.exists(storage_uri)
        
        # Delete content
        assert backend.delete(storage_uri)
        assert not backend.exists(storage_uri)
    
    def test_get_storage_info(self, local_config):
        """Test storage information retrieval."""
        from ncfd.storage.fs import LocalStorageBackend
        backend = LocalStorageBackend(local_config)
        
        info = backend.get_storage_info()
        
        assert info['type'] == 'local'
        assert info['fallback_s3'] is True
        assert info['fallback_configured'] is False
        assert info['total_size_gb'] == 0.0
        assert info['usage_percent'] == 0.0
    
    def test_cleanup_oldest(self, local_config):
        """Test cleanup of oldest files."""
        from ncfd.storage.fs import LocalStorageBackend
        backend = LocalStorageBackend(local_config)
        
        # Store multiple files
        import hashlib
        for i in range(3):
            content = f"Content {i}".encode()
            sha256 = hashlib.sha256(content).hexdigest()
            filename = f"file{i}.txt"
            backend.store(content, sha256, filename)
        
        # Get initial size
        initial_size = backend.get_total_size()
        assert initial_size > 0
        
        # Clean up to target size (half of current)
        target_size = initial_size // 2
        deleted_count = backend.cleanup_oldest(target_size)
        
        assert deleted_count > 0
        assert backend.get_total_size() <= target_size


class TestS3StorageBackend:
    """Test the S3StorageBackend implementation."""
    
    @pytest.fixture
    def mock_boto3(self):
        """Mock boto3 and botocore for S3 tests that need it."""
        with patch('ncfd.storage.s3.BOTO3_AVAILABLE', True):
            with patch.dict('sys.modules', {
                'boto3': Mock(),
                'botocore': Mock(),
                'botocore.exceptions': Mock()
            }):
                yield
    
    @pytest.fixture
    def s3_config(self):
        """Create S3 storage configuration."""
        return {
            's3': {
                'endpoint_url': 'http://localhost:9000',
                'region': 'us-east-1',
                'bucket': 'test-bucket',
                'access_key': 'test-key',
                'secret_key': 'test-secret',
                'use_ssl': False
            }
        }
    
    def test_initialization_success(self, s3_config, mock_boto3):
        """Test successful S3 backend initialization."""
        from ncfd.storage.s3 import S3StorageBackend
        
        with patch('boto3.client') as mock_boto3_client:
            mock_client = Mock()
            mock_client.head_bucket.return_value = {}
            mock_boto3_client.return_value = mock_client
            
            backend = S3StorageBackend(s3_config)
        
        assert backend.bucket == 'test-bucket'
        assert backend.endpoint_url == 'http://localhost:9000'
        assert backend.region == 'us-east-1'
        assert backend.use_ssl is False
        
        # Verify S3 client was created
        mock_boto3_client.assert_called_once()
        mock_client.head_bucket.assert_called_once_with(Bucket='test-bucket')
    
    def test_initialization_no_bucket(self, mock_boto3):
        """Test S3 backend initialization without bucket."""
        from ncfd.storage.s3 import S3StorageBackend
        config = {'s3': {'access_key': 'key', 'secret_key': 'secret'}}
        
        with pytest.raises(ValueError, match="S3 bucket must be specified"):
            S3StorageBackend(config)
    
    def test_initialization_bucket_not_found(self, s3_config):
        """Test S3 backend initialization with non-existent bucket."""
        from ncfd.storage.s3 import S3StorageBackend
        
        # Mock boto3 client that raises ClientError for bucket not found
        with patch('boto3.client') as mock_boto3_client:
            mock_client = Mock()
            mock_client.head_bucket.side_effect = ClientError(
                {'Error': {'Code': 'NoSuchBucket', 'Message': 'Bucket not found'}},
                'HeadBucket'
            )
            mock_boto3_client.return_value = mock_client
            
            with pytest.raises(StorageError, match="S3 bucket not found"):
                S3StorageBackend(s3_config)
    
    def test_store_content(self, s3_config, mock_boto3):
        """Test storing content in S3."""
        from ncfd.storage.s3 import S3StorageBackend
        
        # Mock successful S3 operations
        with patch('boto3.client') as mock_boto3_client:
            mock_client = Mock()
            mock_client.head_bucket.return_value = {}
            mock_client.put_object.return_value = {}
            mock_boto3_client.return_value = mock_client
            
            backend = S3StorageBackend(s3_config)
            
            # Mock the exists method to return False (content doesn't exist)
            backend.exists = Mock(return_value=False)
        
        content = b"Test S3 content"
        import hashlib
        sha256 = hashlib.sha256(content).hexdigest()
        filename = "s3_test.txt"
        metadata = {"source": "s3_test"}
        
        storage_uri = backend.store(content, sha256, filename, metadata)
        
        assert storage_uri == f"s3://test-bucket/docs/{sha256}/{filename}"
        
        # Verify S3 operations were called
        assert mock_client.put_object.call_count == 2  # Content + metadata
    
    def test_retrieve_content(self, s3_config, mock_boto3):
        """Test retrieving content from S3."""
        from ncfd.storage.s3 import S3StorageBackend
        
        # Mock successful S3 operations
        with patch('boto3.client') as mock_boto3_client:
            mock_client = Mock()
            mock_client.head_bucket.return_value = Mock()
            mock_client.get_object.return_value = {'Body': Mock()}
            mock_client.get_object.return_value['Body'].read.return_value = b"S3 content"
            mock_boto3_client.return_value = mock_client
            
            backend = S3StorageBackend(s3_config)
        
        storage_uri = f"s3://test-bucket/docs/{'f' * 64}/retrieve.txt"
        content = backend.retrieve(storage_uri)
        
        assert content == b"S3 content"
        mock_client.get_object.assert_called_once()
    
    def test_sha256_verification_s3(self, s3_config, mock_boto3):
        """Test that S3 storage verifies SHA256 hashes."""
        from ncfd.storage.s3 import S3StorageBackend
        from ncfd.storage import StorageError
        
        # Mock successful S3 operations
        with patch('boto3.client') as mock_boto3_client:
            mock_client = Mock()
            mock_client.head_bucket.return_value = {}
            mock_client.put_object.return_value = {}
            mock_boto3_client.return_value = mock_client
            
            backend = S3StorageBackend(s3_config)
            
            # Mock the exists method to return False (content doesn't exist)
            backend.exists = Mock(return_value=False)
        
        content = b"Test S3 content for hash verification"
        wrong_sha256 = "e" * 64  # Wrong hash
        filename = "s3_test.txt"
        
        # Should fail due to hash mismatch
        with pytest.raises(StorageError, match="SHA256 mismatch"):
            backend.store(content, wrong_sha256, filename)
        
        # Should succeed with correct hash
        import hashlib
        correct_sha256 = hashlib.sha256(content).hexdigest()
        storage_uri = backend.store(content, correct_sha256, filename)
        assert storage_uri.startswith("s3://test-bucket/")


class TestStorageFactory:
    """Test the storage backend factory function."""
    
    def test_create_local_storage(self):
        """Test creating local storage backend."""
        from ncfd.storage.fs import LocalStorageBackend
        config = {'kind': 'local', 'fs': {'root': './test_data'}}
        
        backend = create_storage_backend(config)
        assert isinstance(backend, LocalStorageBackend)
        assert backend.root_path == Path('./test_data')
    
    def test_create_s3_storage(self):
        """Test creating S3 storage backend."""
        config = {
            'kind': 's3',
            's3': {
                'bucket': 'test-bucket',
                'access_key': 'key',
                'secret_key': 'secret'
            }
        }
        
        # Mock boto3 and botocore at the module level
        with patch('ncfd.storage.s3.BOTO3_AVAILABLE', True):
            with patch.dict('sys.modules', {
                'boto3': Mock(),
                'botocore': Mock(),
                'botocore.exceptions': Mock()
            }):
                with patch('boto3.client') as mock_boto3:
                    mock_client = Mock()
                    mock_client.head_bucket.return_value = {}
                    mock_boto3.return_value = mock_client
                    
                    backend = create_storage_backend(config)
                    assert backend.bucket == 'test-bucket'
    
    def test_create_unknown_storage(self):
        """Test creating unknown storage type."""
        config = {'kind': 'unknown'}
        
        with pytest.raises(ValueError, match="Unknown storage type"):
            create_storage_backend(config)
    
    def test_create_default_storage(self):
        """Test creating default storage (S3)."""
        config = {
            's3': {
                'bucket': 'default-bucket',
                'access_key': 'default-key',
                'secret_key': 'default-secret'
            }
        }  # No kind specified, should default to s3
        
        # Mock boto3 and botocore at the module level
        with patch('ncfd.storage.s3.BOTO3_AVAILABLE', True):
            with patch.dict('sys.modules', {
                'boto3': Mock(),
                'botocore': Mock(),
                'botocore.exceptions': Mock()
            }):
                with patch('boto3.client') as mock_boto3:
                    mock_client = Mock()
                    mock_client.head_bucket.return_value = {}
                    mock_boto3.return_value = mock_client
                    
                    backend = create_storage_backend(config)
                    assert backend.bucket == 'default-bucket'


class TestStorageIntegration:
    """Test storage integration with document ingester."""
    
    @patch('ncfd.storage.create_storage_backend')
    def test_document_ingester_storage_integration(self, mock_create_storage):
        """Test that document ingester properly integrates with storage."""
        from ncfd.ingest.document_ingest import DocumentIngester
        
        # Mock storage backend
        mock_backend = Mock()
        mock_create_storage.return_value = mock_backend
        
        # Mock storage config
        storage_config = {
            'kind': 'local',
            'fs': {
                'root': './test_data',
                'max_size_gb': '5',
                'fallback_s3': True
            }
        }
        
        # Mock database session
        mock_session = Mock()
        
        # Create document ingester
        ingester = DocumentIngester(mock_session, storage_config)
        
        # Verify storage backend was created (local + S3 fallback)
        assert mock_create_storage.call_count >= 1
        # First call should be with the local storage config
        mock_create_storage.assert_any_call(storage_config)
        assert ingester.storage_backend == mock_backend
        
        # Test storage fallback setup
        if hasattr(mock_backend, 'set_fallback_backend'):
            # Should have called set_fallback_backend for S3 fallback
            pass  # This would be tested in a more comprehensive integration test


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
