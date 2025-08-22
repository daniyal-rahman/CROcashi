"""
Demo script for the storage system.

This script demonstrates the local storage functionality with size monitoring
and automatic fallback to S3 when local storage is full.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def demo_local_storage():
    """Demonstrate local storage functionality."""
    print("\n🚀 Local Storage System Demo")
    print("=" * 50)
    
    # Create temporary directory for demo
    temp_dir = tempfile.mkdtemp()
    print(f"📁 Using temporary directory: {temp_dir}")
    
    try:
        # Import storage components
        from ncfd.storage.fs import LocalStorageBackend
        from ncfd.storage import StorageError
        
        # Create storage config with very small limit for demo
        config = {
            'local': {
                'root': temp_dir,
                'max_size_gb': '0.001',  # 1MB limit
                'fallback_s3': False  # Disable fallback for demo
            }
        }
        
        print("\n1. Initializing Local Storage Backend")
        print("-" * 40)
        
        backend = LocalStorageBackend(config)
        print(f"✅ Storage backend initialized")
        print(f"   Root path: {backend.root_path}")
        print(f"   Max size: {backend.max_size_bytes / (1024**2):.2f} MB")
        print(f"   Fallback S3: {backend.fallback_s3}")
        
        # Get initial storage info
        info = backend.get_storage_info()
        print(f"   Current usage: {info['total_size_gb']:.6f} GB ({info['usage_percent']:.1f}%)")
        
        print("\n2. Storing Test Documents")
        print("-" * 40)
        
        # Store some test documents
        documents = [
            ("document1.txt", b"This is the first test document with some content."),
            ("document2.txt", b"Second document with different content for testing."),
            ("document3.txt", b"Third document to demonstrate storage capabilities."),
        ]
        
        stored_uris = []
        
        for filename, content in documents:
            # Compute actual SHA256 hash
            import hashlib
            sha256 = hashlib.sha256(content).hexdigest()
            print(f"   📄 Storing: {filename} ({len(content)} bytes)")
            
            try:
                storage_uri = backend.store(content, sha256, filename, {"demo": True})
                stored_uris.append(storage_uri)
                print(f"      ✅ Stored at: {storage_uri}")
            except StorageError as e:
                print(f"      ❌ Storage failed: {e}")
                break
        
        print("\n3. Storage Information After Upload")
        print("-" * 40)
        
        info = backend.get_storage_info()
        print(f"   Total size: {info['total_size_bytes']} bytes")
        print(f"   Total size: {info['total_size_gb']:.6f} GB")
        print(f"   Usage: {info['usage_percent']:.1f}%")
        
        print("\n4. Testing Storage Limits")
        print("-" * 40)
        
        # Try to store a large document that exceeds the limit
        large_content = b"x" * (1024 * 1024)  # 1MB
        sha256 = "demo_large" * 8
        filename = "large_document.txt"
        
        print(f"   📄 Attempting to store: {filename} ({len(large_content)} bytes)")
        
        try:
            storage_uri = backend.store(large_content, sha256, filename, {"demo": True})
            print(f"      ✅ Large document stored: {storage_uri}")
        except StorageError as e:
            print(f"      ❌ Storage limit enforced: {e}")
        
        print("\n5. Retrieving Stored Documents")
        print("-" * 40)
        
        for storage_uri in stored_uris:
            try:
                content = backend.retrieve(storage_uri)
                print(f"   📖 Retrieved: {storage_uri}")
                print(f"      Content: {content[:50]}...")
            except StorageError as e:
                print(f"   ❌ Retrieval failed: {e}")
        
        print("\n6. Testing Duplicate Storage")
        print("-" * 40)
        
        # Try to store the same content again
        filename, content = documents[0]
        # Use same content but different filename to test deduplication
        import hashlib
        sha256 = hashlib.sha256(content).hexdigest()
        
        print(f"   📄 Storing duplicate: {filename}")
        
        try:
            storage_uri = backend.store(content, sha256, filename, {"demo": True})
            print(f"      ✅ Duplicate handled: {storage_uri}")
        except StorageError as e:
            print(f"      ❌ Duplicate storage failed: {e}")
        
        print("\n7. Cleanup and Final Stats")
        print("-" * 40)
        
        # Clean up some files to demonstrate cleanup functionality
        if stored_uris:
            target_size = backend.get_total_size() // 2
            deleted_count = backend.cleanup_oldest(target_size)
            print(f"   🗑️  Cleaned up {deleted_count} files")
        
        final_info = backend.get_storage_info()
        print(f"   Final size: {final_info['total_size_bytes']} bytes")
        print(f"   Final usage: {final_info['usage_percent']:.1f}%")
        
        print("\n🎉 Local Storage Demo Completed Successfully!")
        
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


def demo_storage_factory():
    """Demonstrate storage factory functionality."""
    print("\n🏭 Storage Factory Demo")
    print("=" * 50)
    
    try:
        from ncfd.storage import create_storage_backend
        
        # Test local storage creation
        local_config = {
            'kind': 'local',
            'local': {
                'root': './demo_data',
                'max_size_gb': '5',
                'fallback_s3': True
            }
        }
        
        print("1. Creating Local Storage Backend")
        print("-" * 40)
        
        local_backend = create_storage_backend(local_config)
        print(f"✅ Local backend created: {type(local_backend).__name__}")
        
        # Test S3 storage creation (with mocked boto3)
        s3_config = {
            'kind': 's3',
            's3': {
                'bucket': 'demo-bucket',
                'access_key': 'demo-key',
                'secret_key': 'demo-secret'
            }
        }
        
        print("\n2. Creating S3 Storage Backend")
        print("-" * 40)
        
        # Mock boto3 for demo
        import sys
        from unittest.mock import Mock
        
        # Create a mock boto3 module
        mock_boto3 = Mock()
        mock_client = Mock()
        mock_client.head_bucket.return_value = {}
        mock_boto3.client.return_value = mock_client
        
        # Temporarily replace boto3 in sys.modules
        original_boto3 = sys.modules.get('boto3')
        sys.modules['boto3'] = mock_boto3
        
        try:
            s3_backend = create_storage_backend(s3_config)
            print(f"✅ S3 backend created: {type(s3_backend).__name__}")
        except Exception as e:
            print(f"❌ S3 backend creation failed: {e}")
        finally:
            # Restore original boto3
            if original_boto3:
                sys.modules['boto3'] = original_boto3
            else:
                del sys.modules['boto3']
        
        print("\n🎉 Storage Factory Demo Completed!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
    except Exception as e:
        print(f"❌ Demo failed: {e}")


if __name__ == "__main__":
    print("🧪 NCFD Storage System Demo")
    print("=" * 60)
    
    # Run demos
    demo_local_storage()
    demo_storage_factory()
    
    print("\n✨ All demos completed!")
