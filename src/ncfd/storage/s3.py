"""
S3 storage backend for NCFD.

This module provides S3-compatible storage for documents with proper
error handling and metadata management.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    # Create mock classes for when boto3 is not available
    class ClientError(Exception):
        def __init__(self, error_response, operation_name):
            self.response = error_response
            self.operation_name = operation_name
    
    class NoCredentialsError(Exception):
        pass

from . import StorageBackend, StorageError, compute_sha256

logger = logging.getLogger(__name__)


class S3StorageBackend(StorageBackend):
    """S3-compatible storage backend."""
    
    def __init__(self, config: Dict[str, Any], client=None, resource=None):
        """
        Initialize S3 storage backend.
        
        Args:
            config: Storage configuration with S3 settings
            client: Optional boto3 S3 client for dependency injection/testing
            resource: Optional boto3 S3 resource for dependency injection/testing
        """
        s3_config = config.get('s3', {})
        
        # S3 configuration
        self.endpoint_url = s3_config.get('endpoint_url')
        self.region = s3_config.get('region', 'us-east-1')
        self.bucket = s3_config.get('bucket')
        self.access_key = s3_config.get('access_key')
        self.secret_key = s3_config.get('secret_key')
        self.use_ssl = s3_config.get('use_ssl', True)
        
        if not self.bucket:
            raise ValueError("S3 bucket must be specified in config")
        
        # Initialize S3 client with dependency injection support
        try:
            if client is not None:
                # Use injected client (for testing/mocking)
                self.s3_client = client
                self._boto3 = None
            else:
                # Check if boto3 is available at runtime
                try:
                    self._boto3 = __import__('boto3')
                except ImportError as e:
                    raise StorageError("boto3 missing; pip install boto3") from e
                
                self.s3_client = self._boto3.client(
                    's3',
                    endpoint_url=self.endpoint_url,
                    region_name=self.region,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    use_ssl=self.use_ssl,
                    verify=True
                )
                
                # Test connection only for real clients
                self.s3_client.head_bucket(Bucket=self.bucket)
                logger.info(f"S3 storage initialized: {self.bucket} at {self.endpoint_url or 'AWS'}")
                
        except NoCredentialsError:
            raise StorageError("S3 credentials not found")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                raise StorageError(f"S3 bucket not found: {self.bucket}")
            elif error_code == 'AccessDenied':
                raise StorageError(f"Access denied to S3 bucket: {self.bucket}")
            else:
                raise StorageError(f"S3 initialization failed: {e}")
        except Exception as e:
            raise StorageError(f"Failed to initialize S3 client: {e}")
    
    def store(self, content: bytes, sha256: str | None, filename: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Store content in S3 with SHA256-based key structure.
        
        Args:
            content: Binary content to store
            sha256: SHA256 hash of content (optional, will be computed if not provided)
            filename: Original filename
            metadata: Optional metadata to store alongside
            
        Returns:
            S3 storage URI
            
        Raises:
            StorageError: If storage fails
        """
        # Compute actual SHA256 hash
        actual_hash = compute_sha256(content)
        if sha256 and sha256 != actual_hash:
            raise StorageError(f"SHA256 mismatch: provided={sha256} computed={actual_hash}")
        sha256 = actual_hash
        
        # Check if content already exists
        storage_uri = f"s3://{self.bucket}/docs/{sha256}/{filename}"
        if self.exists(storage_uri):
            logger.info(f"Content already exists in S3: {sha256}/{filename}")
            return storage_uri
        
        # Create S3 key
        s3_key = f"docs/{sha256}/{filename}"
        
        # Prepare metadata
        s3_metadata = {
            'sha256': sha256,
            'filename': filename,
            'stored_at': datetime.utcnow().isoformat(),
            'size_bytes': str(len(content))
        }
        
        if metadata:
            s3_metadata.update(metadata)
        
        try:
            # Upload content
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=content,
                Metadata=s3_metadata,
                ContentType=self._get_content_type(filename)
            )
            
            # Store metadata separately
            meta_key = f"meta/{sha256}.json"
            meta_data = {
                'sha256': sha256,
                'filename': filename,
                's3_key': s3_key,
                'stored_at': s3_metadata['stored_at'],
                'size_bytes': len(content),
                'metadata': metadata or {}
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=meta_key,
                Body=json.dumps(meta_data, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"Stored {len(content)} bytes in S3: {s3_key}")
            return storage_uri
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                raise StorageError(f"S3 bucket not found: {self.bucket}")
            elif error_code == 'AccessDenied':
                raise StorageError(f"Access denied to S3 bucket: {self.bucket}")
            else:
                raise StorageError(f"S3 upload failed: {e}")
        except Exception as e:
            raise StorageError(f"Failed to store content in S3: {e}")
    
    def retrieve(self, storage_uri: str) -> bytes:
        """
        Retrieve content from S3.
        
        Args:
            storage_uri: S3 storage URI (s3://bucket/docs/sha256/filename)
            
        Returns:
            Binary content
            
        Raises:
            StorageError: If retrieval fails
        """
        if not storage_uri.startswith(f"s3://{self.bucket}/"):
            raise StorageError(f"Invalid S3 storage URI: {storage_uri}")
        
        # Extract S3 key from URI
        s3_key = storage_uri.replace(f"s3://{self.bucket}/", "")
        
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
            return response['Body'].read()
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise StorageError(f"Content not found in S3: {s3_key}")
            elif error_code == 'AccessDenied':
                raise StorageError(f"Access denied to S3 object: {s3_key}")
            else:
                raise StorageError(f"S3 retrieval failed: {e}")
        except Exception as e:
            raise StorageError(f"Failed to retrieve content from S3: {e}")
    
    def exists(self, storage_uri: str) -> bool:
        """Check if content exists in S3."""
        if not storage_uri.startswith(f"s3://{self.bucket}/"):
            return False
        
        s3_key = storage_uri.replace(f"s3://{self.bucket}/", "")
        
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                return False
            else:
                logger.warning(f"Error checking S3 object existence: {e}")
                return False
        except Exception as e:
            logger.warning(f"Failed to check S3 object existence: {e}")
            return False
    
    def delete(self, storage_uri: str) -> bool:
        """
        Delete content from S3.
        
        Args:
            storage_uri: S3 storage URI to delete
            
        Returns:
            True if deletion was successful
        """
        if not storage_uri.startswith(f"s3://{self.bucket}/"):
            return False
        
        s3_key = storage_uri.replace(f"s3://{self.bucket}/", "")
        meta_key = f"meta/{s3_key.split('/')[-2]}.json"
        
        try:
            # Delete content object
            self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)
            
            # Delete metadata object
            try:
                self.s3_client.delete_object(Bucket=self.bucket, Key=meta_key)
            except ClientError:
                # Metadata might not exist, ignore
                pass
            
            logger.info(f"Deleted content from S3: {s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete S3 object: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to delete content from S3: {e}")
            return False
    
    def get_size(self, storage_uri: str) -> int:
        """Get size of stored content in bytes."""
        if not storage_uri.startswith(f"s3://{self.bucket}/"):
            return 0
        
        s3_key = storage_uri.replace(f"s3://{self.bucket}/", "")
        
        try:
            response = self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            return response['ContentLength']
        except ClientError:
            return 0
        except Exception:
            return 0
    
    def get_total_size(self) -> int:
        """Get total size of all stored content in bytes."""
        total_size = 0
        
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket,
                Prefix='docs/'
            )
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        total_size += obj['Size']
            
            return total_size
            
        except ClientError as e:
            logger.error(f"Failed to calculate S3 total size: {e}")
            return 0
        except Exception as e:
            logger.error(f"Failed to calculate S3 total size: {e}")
            return 0
    
    def _get_content_type(self, filename: str) -> str:
        """Determine content type based on filename extension."""
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        
        content_types = {
            'pdf': 'application/pdf',
            'html': 'text/html',
            'htm': 'text/html',
            'txt': 'text/plain',
            'json': 'application/json',
            'xml': 'application/xml',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif'
        }
        
        return content_types.get(ext, 'application/octet-stream')
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get storage statistics and information."""
        total_size = self.get_total_size()
        
        return {
            'type': 's3',
            'bucket': self.bucket,
            'endpoint_url': self.endpoint_url,
            'region': self.region,
            'total_size_bytes': total_size,
            'total_size_gb': total_size / (1024**3),
            'use_ssl': self.use_ssl
        }
