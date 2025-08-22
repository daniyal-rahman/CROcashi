"""
Demo script for the unified storage manager.

This script demonstrates the unified storage manager functionality
with cross-backend operations and URI resolution.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def demo_unified_storage():
    """Demonstrate unified storage manager functionality."""
    print("\n🚀 Unified Storage Manager Demo")
    print("=" * 50)
    
    # Create temporary directory for demo
    temp_dir = tempfile.mkdtemp()
    print(f"📁 Using temporary directory: {temp_dir}")
    
    try:
        # Import storage components
        from ncfd.storage import create_unified_storage_manager, StorageError
        
        # Create unified storage config with both local and S3 backends
        config = {
            'fs': {
                'root': temp_dir,
                'max_size_gb': '0.001',  # 1MB limit
                'fallback_s3': False
            },
            's3': {
                'bucket': 'demo-bucket',
                'access_key': 'demo-key',
                'secret_key': 'demo-secret',
                'endpoint_url': 'http://localhost:9000',
                'region': 'us-east-1',
                'use_ssl': False
            }
        }
        
        print("\n1. Initializing Unified Storage Manager")
        print("-" * 40)
        
        # Mock boto3 to avoid actual S3 client creation
        import unittest.mock
        with unittest.mock.patch('boto3.client') as mock_boto3:
            mock_client = unittest.mock.Mock()
            mock_client.head_bucket.return_value = {}
            mock_boto3.return_value = mock_client
            
            manager = create_unified_storage_manager(config)
            print(f"✅ Unified storage manager initialized")
            print(f"   Available backends: {list(manager.backends.keys())}")
            print(f"   Primary backend: {manager.backends['local'].__class__.__name__}")
        
        print("\n2. Cross-Backend Storage Operations")
        print("-" * 40)
        
        # Store content with different backend preferences
        documents = [
            ("local_doc.txt", b"Content for local storage", "local"),
            ("s3_doc.txt", b"Content for S3 storage", "s3"),
            ("auto_doc.txt", b"Content with auto backend selection", None)
        ]
        
        stored_uris = []
        
        for filename, content, backend_type in documents:
            import hashlib
            sha256 = hashlib.sha256(content).hexdigest()
            
            backend_desc = backend_type or "auto"
            print(f"   📄 Storing: {filename} ({len(content)} bytes) -> {backend_desc}")
            
            try:
                storage_uri = manager.store(content, sha256, filename, backend_type=backend_type)
                stored_uris.append(storage_uri)
                print(f"      ✅ Stored at: {storage_uri}")
            except StorageError as e:
                print(f"      ❌ Storage failed: {e}")
        
        print("\n3. Cross-Backend Retrieval")
        print("-" * 40)
        
        for storage_uri in stored_uris:
            try:
                content = manager.retrieve(storage_uri)
                print(f"   📖 Retrieved: {storage_uri}")
                print(f"      Content: {content[:30]}...")
            except StorageError as e:
                print(f"   ❌ Retrieval failed: {e}")
        
        print("\n4. Cross-Backend Operations")
        print("-" * 40)
        
        # Test existence checks
        for storage_uri in stored_uris:
            exists = manager.exists(storage_uri)
            print(f"   🔍 Exists check: {storage_uri} -> {exists}")
        
        # Test size checks
        for storage_uri in stored_uris:
            try:
                size = manager.get_size(storage_uri)
                print(f"   📏 Size check: {storage_uri} -> {size} bytes")
            except StorageError as e:
                print(f"   ❌ Size check failed: {e}")
        
        print("\n5. Unified Storage Information")
        print("-" * 40)
        
        info = manager.get_storage_info()
        print(f"   Storage type: {info['type']}")
        print(f"   Total size: {info['total_size_bytes']} bytes")
        print(f"   Total size: {info['total_size_gb']:.6f} GB")
        
        for backend_type, backend_info in info['backends'].items():
            print(f"   {backend_type.upper()} backend:")
            print(f"      Type: {backend_info.get('type', 'unknown')}")
            print(f"      Size: {backend_info.get('total_size_bytes', 0)} bytes")
        
        print("\n6. Content Listing")
        print("-" * 40)
        
        # List content from all backends
        all_content = manager.list_content()
        print(f"   📋 Total content URIs: {len(all_content)}")
        for uri in all_content:
            print(f"      {uri}")
        
        # List content from specific backends
        for backend_type in ['local', 's3']:
            try:
                backend_content = manager.list_content(backend_type=backend_type)
                print(f"   📋 {backend_type.upper()} content: {len(backend_content)} URIs")
                for uri in backend_content:
                    print(f"      {uri}")
            except StorageError as e:
                print(f"   ❌ Failed to list {backend_type} content: {e}")
        
        print("\n7. URI Resolution Demo")
        print("-" * 40)
        
        from ncfd.storage import parse_storage_uri, resolve_backend
        
        for uri in stored_uris:
            try:
                backend_type, path, filename = parse_storage_uri(uri)
                print(f"   🔍 Parsed URI: {uri}")
                print(f"      Backend: {backend_type}")
                print(f"      Path: {path}")
                print(f"      Filename: {filename}")
                
                # Resolve backend
                backend = resolve_backend(uri, manager.backends)
                print(f"      Resolved to: {backend.__class__.__name__}")
                
            except StorageError as e:
                print(f"   ❌ URI parsing failed: {e}")
        
        print("\n🎉 Unified Storage Demo Completed Successfully!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure you're running from the correct directory")
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir)
        print(f"\n🧹 Cleaned up temporary directory: {temp_dir}")


if __name__ == "__main__":
    demo_unified_storage()
