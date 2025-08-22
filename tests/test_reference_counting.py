"""
Tests for the storage reference counting system.

This module tests the reference counting functionality that prevents
data corruption from age-based cleanup operations.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from ncfd.storage.reference_manager import StorageReferenceManager


class TestStorageReferenceManager:
    """Test the StorageReferenceManager implementation."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = Mock()
        return session
    
    @pytest.fixture
    def reference_manager(self, mock_db_session):
        """Create storage reference manager with mock session."""
        return StorageReferenceManager(mock_db_session)
    
    def test_initialization(self, mock_db_session):
        """Test reference manager initialization."""
        manager = StorageReferenceManager(mock_db_session)
        assert manager.db_session == mock_db_session
    
    def test_increment_reference(self, reference_manager, mock_db_session):
        """Test incrementing reference count."""
        # Mock database result
        mock_result = Mock()
        mock_result.scalar.return_value = 2
        mock_db_session.execute.return_value = mock_result
        
        refcount = reference_manager.increment_reference(
            sha256="a" * 64,
            backend_type="local",
            reference_type="document",
            reference_id=123
        )
        
        assert refcount == 2
        mock_db_session.execute.assert_called_once()
        
        # Verify the SQL call
        call_args = mock_db_session.execute.call_args
        assert "increment_storage_refcount" in str(call_args[0][0])
    
    def test_decrement_reference(self, reference_manager, mock_db_session):
        """Test decrementing reference count."""
        # Mock database result
        mock_result = Mock()
        mock_result.scalar.return_value = 1
        mock_db_session.execute.return_value = mock_result
        
        refcount = reference_manager.decrement_reference(
            sha256="a" * 64,
            backend_type="local",
            reference_type="document",
            reference_id=123
        )
        
        assert refcount == 1
        mock_db_session.execute.assert_called_once()
        
        # Verify the SQL call
        call_args = mock_db_session.execute.call_args
        assert "decrement_storage_refcount" in str(call_args[0][0])
    
    def test_get_cleanup_candidates(self, reference_manager, mock_db_session):
        """Test getting cleanup candidates."""
        # Mock database result
        mock_result = Mock()
        mock_row1 = Mock()
        mock_row1.object_id = 1
        mock_row1.sha256 = "a" * 64
        mock_row1.storage_uri = "local://hash/filename"
        mock_row1.backend_type = "local"
        mock_row1.content_size = 1024
        mock_row1.refcount = 0
        mock_row1.created_at = "2025-01-01T00:00:00Z"
        mock_row1.last_accessed = "2025-01-01T00:00:00Z"
        
        mock_row2 = Mock()
        mock_row2.object_id = 2
        mock_row2.sha256 = "b" * 64
        mock_row2.storage_uri = "local://hash2/filename2"
        mock_row2.backend_type = "local"
        mock_row2.content_size = 2048
        mock_row2.refcount = 0
        mock_row2.created_at = "2025-01-01T00:00:00Z"
        mock_row2.last_accessed = "2025-01-01T00:00:00Z"
        
        mock_result.__iter__ = lambda self: iter([mock_row1, mock_row2])
        mock_db_session.execute.return_value = mock_result
        
        candidates = reference_manager.get_cleanup_candidates(max_age_days=30, min_refcount=0)
        
        assert len(candidates) == 2
        assert candidates[0]['sha256'] == "a" * 64
        assert candidates[0]['refcount'] == 0
        assert candidates[1]['sha256'] == "b" * 64
        assert candidates[1]['refcount'] == 0
        
        # Verify the SQL call
        call_args = mock_db_session.execute.call_args
        assert "get_cleanup_candidates" in str(call_args[0][0])
    
    def test_get_object_references(self, reference_manager, mock_db_session):
        """Test getting object references."""
        # Mock database result
        mock_result = Mock()
        mock_row1 = Mock()
        mock_row1.reference_type = "document"
        mock_row1.reference_id = 123
        mock_row1.created_at = "2025-01-01T00:00:00Z"
        
        mock_row2 = Mock()
        mock_row2.reference_type = "study"
        mock_row2.reference_id = 456
        mock_row2.created_at = "2025-01-01T00:00:00Z"
        
        mock_result.__iter__ = lambda self: iter([mock_row1, mock_row2])
        mock_db_session.execute.return_value = mock_result
        
        references = reference_manager.get_object_references(
            sha256="a" * 64,
            backend_type="local"
        )
        
        assert len(references) == 2
        assert references[0]['reference_type'] == "document"
        assert references[0]['reference_id'] == 123
        assert references[1]['reference_type'] == "study"
        assert references[1]['reference_id'] == 456
    
    def test_update_content_size(self, reference_manager, mock_db_session):
        """Test updating content size."""
        # Mock database result
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_db_session.execute.return_value = mock_result
        
        success = reference_manager.update_content_size(
            sha256="a" * 64,
            backend_type="local",
            content_size=1024
        )
        
        assert success is True
        mock_db_session.execute.assert_called_once()
        
        # Verify the SQL call
        call_args = mock_db_session.execute.call_args
        assert "UPDATE storage_objects" in str(call_args[0][0])
    
    def test_update_content_size_not_found(self, reference_manager, mock_db_session):
        """Test updating content size when object not found."""
        # Mock database result
        mock_result = Mock()
        mock_result.rowcount = 0
        mock_db_session.execute.return_value = mock_result
        
        success = reference_manager.update_content_size(
            sha256="a" * 64,
            backend_type="local",
            content_size=1024
        )
        
        assert success is False
    
    def test_get_storage_stats(self, reference_manager, mock_db_session):
        """Test getting storage statistics."""
        # Mock total stats result
        mock_stats_result = Mock()
        mock_stats_row = Mock()
        mock_stats_row.total_objects = 10
        mock_stats_row.total_size = 10240
        mock_stats_row.avg_size = 1024
        mock_stats_row.oldest_object = "2025-01-01T00:00:00Z"
        mock_stats_row.newest_object = "2025-01-15T00:00:00Z"
        mock_stats_result.fetchone.return_value = mock_stats_row
        
        # Mock refcount distribution result
        mock_refcount_result = Mock()
        mock_refcount_row1 = Mock()
        mock_refcount_row1.refcount = 0
        mock_refcount_row1.object_count = 5
        mock_refcount_row2 = Mock()
        mock_refcount_row2.refcount = 1
        mock_refcount_row2.object_count = 3
        mock_refcount_row3 = Mock()
        mock_refcount_row3.refcount = 2
        mock_refcount_row3.object_count = 2
        mock_refcount_result.__iter__ = lambda self: iter([mock_refcount_row1, mock_refcount_row2, mock_refcount_row3])
        
        # Mock backend distribution result
        mock_backend_result = Mock()
        mock_backend_row1 = Mock()
        mock_backend_row1.backend_type = "local"
        mock_backend_row1.object_count = 7
        mock_backend_row1.total_size = 7168
        mock_backend_row2 = Mock()
        mock_backend_row2.backend_type = "s3"
        mock_backend_row2.object_count = 3
        mock_backend_row2.total_size = 3072
        mock_backend_result.__iter__ = lambda self: iter([mock_backend_row1, mock_backend_row2])
        
        # Set up mock session to return different results for different calls
        mock_db_session.execute.side_effect = [
            mock_stats_result,
            mock_refcount_result,
            mock_backend_result
        ]
        
        stats = reference_manager.get_storage_stats()
        
        assert stats['total_objects'] == 10
        assert stats['total_size_bytes'] == 10240
        assert stats['total_size_gb'] == 10240 / (1024**3)
        assert stats['avg_size_bytes'] == 1024
        assert stats['oldest_object'] == "2025-01-01T00:00:00Z"
        assert stats['newest_object'] == "2025-01-15T00:00:00Z"
        assert stats['refcount_distribution'] == {0: 5, 1: 3, 2: 2}
        assert stats['backend_distribution']['local']['object_count'] == 7
        assert stats['backend_distribution']['s3']['object_count'] == 3
    
    def test_increment_reference_failure(self, reference_manager, mock_db_session):
        """Test handling of increment reference failure."""
        mock_db_session.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            reference_manager.increment_reference(
                sha256="a" * 64,
                backend_type="local",
                reference_type="document",
                reference_id=123
            )
    
    def test_decrement_reference_failure(self, reference_manager, mock_db_session):
        """Test handling of decrement reference failure."""
        mock_db_session.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            reference_manager.decrement_reference(
                sha256="a" * 64,
                backend_type="local",
                reference_type="document",
                reference_id=123
            )
    
    def test_get_cleanup_candidates_failure(self, reference_manager, mock_db_session):
        """Test handling of get cleanup candidates failure."""
        mock_db_session.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            reference_manager.get_cleanup_candidates(max_age_days=30, min_refcount=0)
    
    def test_get_object_references_failure(self, reference_manager, mock_db_session):
        """Test handling of get object references failure."""
        mock_db_session.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            reference_manager.get_object_references(
                sha256="a" * 64,
                backend_type="local"
            )
    
    def test_update_content_size_failure(self, reference_manager, mock_db_session):
        """Test handling of update content size failure."""
        mock_db_session.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            reference_manager.update_content_size(
                sha256="a" * 64,
                backend_type="local",
                content_size=1024
            )
    
    def test_get_storage_stats_failure(self, reference_manager, mock_db_session):
        """Test handling of get storage stats failure."""
        mock_db_session.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            reference_manager.get_storage_stats()


class TestReferenceCountingIntegration:
    """Test integration between storage backends and reference counting."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    def test_storage_backend_with_reference_manager(self, temp_dir):
        """Test storage backend integration with reference manager."""
        from ncfd.storage.fs import LocalStorageBackend
        from ncfd.storage.reference_manager import StorageReferenceManager
        
        # Create mock database session
        mock_db_session = Mock()
        
        # Create reference manager
        reference_manager = StorageReferenceManager(mock_db_session)
        
        # Create local storage backend
        config = {
            'fs': {
                'root': str(temp_dir),
                'max_size_gb': '1',
                'fallback_s3': False
            }
        }
        backend = LocalStorageBackend(config)
        
        # Set reference manager
        backend.set_reference_manager(reference_manager)
        
        # Test that reference manager is set
        assert hasattr(backend, 'reference_manager')
        assert backend.reference_manager == reference_manager
    
    def test_cleanup_unreferenced_method(self, temp_dir):
        """Test the cleanup_unreferenced method exists."""
        from ncfd.storage.fs import LocalStorageBackend
        
        config = {
            'fs': {
                'root': str(temp_dir),
                'max_size_gb': '1',
                'fallback_s3': False
            }
        }
        backend = LocalStorageBackend(config)
        
        # Test that the method exists
        assert hasattr(backend, 'cleanup_unreferenced')
        assert callable(backend.cleanup_unreferenced)
        
        # Test method call (should use fallback)
        result = backend.cleanup_unreferenced(max_age_days=30)
        assert isinstance(result, int)
