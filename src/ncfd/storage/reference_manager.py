"""
Storage reference manager for NCFD.

This module manages storage object references to prevent data corruption
from age-based cleanup operations.
"""

import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class StorageReferenceManager:
    """
    Manages storage object references to prevent data corruption.
    
    This class handles:
    - Incrementing/decrementing reference counts
    - Tracking what entities reference storage objects
    - Identifying objects safe for cleanup
    - Preventing deletion of referenced content
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize the storage reference manager.
        
        Args:
            db_session: Database session for reference operations
        """
        self.db_session = db_session
    
    def increment_reference(self, sha256: str, backend_type: str, 
                           reference_type: str, reference_id: int) -> int:
        """
        Increment reference count for a storage object.
        
        Args:
            sha256: Content hash
            backend_type: Storage backend type (local, s3)
            reference_type: Type of referencing entity (document, study, etc.)
            reference_id: ID of the referencing entity
            
        Returns:
            New reference count
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = self.db_session.execute(
                text("SELECT increment_storage_refcount(:sha256, :backend_type, :reference_type, :reference_id)"),
                {
                    'sha256': sha256,
                    'backend_type': backend_type,
                    'reference_type': reference_type,
                    'reference_id': reference_id
                }
            )
            
            refcount = result.scalar()
            logger.info(f"Incremented reference count for {sha256}:{backend_type} -> {refcount}")
            return refcount
            
        except Exception as e:
            logger.error(f"Failed to increment reference count: {e}")
            raise
    
    def decrement_reference(self, sha256: str, backend_type: str,
                           reference_type: str, reference_id: int) -> int:
        """
        Decrement reference count for a storage object.
        
        Args:
            sha256: Content hash
            backend_type: Storage backend type (local, s3)
            reference_type: Type of referencing entity
            reference_id: ID of the referencing entity
            
        Returns:
            New reference count
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = self.db_session.execute(
                text("SELECT decrement_storage_refcount(:sha256, :backend_type, :reference_type, :reference_id)"),
                {
                    'sha256': sha256,
                    'backend_type': backend_type,
                    'reference_type': reference_type,
                    'reference_id': reference_id
                }
            )
            
            refcount = result.scalar()
            logger.info(f"Decremented reference count for {sha256}:{backend_type} -> {refcount}")
            return refcount
            
        except Exception as e:
            logger.error(f"Failed to decrement reference count: {e}")
            raise
    
    def get_cleanup_candidates(self, max_age_days: int = 30, 
                              min_refcount: int = 0) -> List[Dict[str, Any]]:
        """
        Get storage objects eligible for cleanup.
        
        Args:
            max_age_days: Maximum age in days before cleanup
            min_refcount: Minimum reference count for cleanup eligibility
            
        Returns:
            List of objects safe for cleanup
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = self.db_session.execute(
                text("SELECT * FROM get_cleanup_candidates(:max_age, :min_refcount)"),
                {
                    'max_age': max_age_days,
                    'min_refcount': min_refcount
                }
            )
            
            candidates = []
            for row in result:
                candidates.append({
                    'object_id': row.object_id,
                    'sha256': row.sha256,
                    'storage_uri': row.storage_uri,
                    'backend_type': row.backend_type,
                    'content_size': row.content_size,
                    'refcount': row.refcount,
                    'created_at': row.created_at,
                    'last_accessed': row.last_accessed
                })
            
            logger.info(f"Found {len(candidates)} cleanup candidates")
            return candidates
            
        except Exception as e:
            logger.error(f"Failed to get cleanup candidates: {e}")
            raise
    
    def get_object_references(self, sha256: str, backend_type: str) -> List[Dict[str, Any]]:
        """
        Get all references to a storage object.
        
        Args:
            sha256: Content hash
            backend_type: Storage backend type
            
        Returns:
            List of references to the object
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = self.db_session.execute(
                text("""
                    SELECT sr.reference_type, sr.reference_id, sr.created_at
                    FROM storage_references sr
                    JOIN storage_objects so ON sr.object_id = so.object_id
                    WHERE so.sha256 = :sha256 AND so.backend_type = :backend_type
                """),
                {
                    'sha256': sha256,
                    'backend_type': backend_type
                }
            )
            
            references = []
            for row in result:
                references.append({
                    'reference_type': row.reference_type,
                    'reference_id': row.reference_id,
                    'created_at': row.created_at
                })
            
            logger.info(f"Found {len(references)} references for {sha256}:{backend_type}")
            return references
            
        except Exception as e:
            logger.error(f"Failed to get object references: {e}")
            raise
    
    def update_content_size(self, sha256: str, backend_type: str, content_size: int) -> bool:
        """
        Update the content size for a storage object.
        
        Args:
            sha256: Content hash
            backend_type: Storage backend type
            content_size: Size in bytes
            
        Returns:
            True if update was successful
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = self.db_session.execute(
                text("""
                    UPDATE storage_objects 
                    SET content_size = :content_size
                    WHERE sha256 = :sha256 AND backend_type = :backend_type
                """),
                {
                    'sha256': sha256,
                    'backend_type': backend_type,
                    'content_size': content_size
                }
            )
            
            updated = result.rowcount > 0
            if updated:
                logger.info(f"Updated content size for {sha256}:{backend_type} -> {content_size} bytes")
            else:
                logger.warning(f"No storage object found for {sha256}:{backend_type}")
            
            return updated
            
        except Exception as e:
            logger.error(f"Failed to update content size: {e}")
            raise
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive storage statistics.
        
        Returns:
            Dictionary with storage statistics
            
        Raises:
            Exception: If database operation fails
        """
        try:
            # Total objects and size
            result = self.db_session.execute(text("""
                SELECT 
                    COUNT(*) as total_objects,
                    SUM(content_size) as total_size,
                    AVG(content_size) as avg_size,
                    MIN(created_at) as oldest_object,
                    MAX(created_at) as newest_object
                FROM storage_objects
            """))
            
            stats = result.fetchone()
            
            # Reference count distribution
            refcount_result = self.db_session.execute(text("""
                SELECT 
                    refcount,
                    COUNT(*) as object_count
                FROM storage_objects
                GROUP BY refcount
                ORDER BY refcount
            """))
            
            refcount_distribution = {}
            for row in refcount_result:
                refcount_distribution[row.refcount] = row.object_count
            
            # Backend distribution
            backend_result = self.db_session.execute(text("""
                SELECT 
                    backend_type,
                    COUNT(*) as object_count,
                    SUM(content_size) as total_size
                FROM storage_objects
                GROUP BY backend_type
            """))
            
            backend_distribution = {}
            for row in backend_result:
                backend_distribution[row.backend_type] = {
                    'object_count': row.object_count,
                    'total_size': row.total_size
                }
            
            return {
                'total_objects': stats.total_objects,
                'total_size_bytes': stats.total_size or 0,
                'total_size_gb': (stats.total_size or 0) / (1024**3),
                'avg_size_bytes': stats.avg_size or 0,
                'oldest_object': stats.oldest_object,
                'newest_object': stats.newest_object,
                'refcount_distribution': refcount_distribution,
                'backend_distribution': backend_distribution
            }
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            raise
