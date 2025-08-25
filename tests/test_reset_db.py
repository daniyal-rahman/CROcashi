#!/usr/bin/env python3
"""
Test script that resets the database engine and tests connectivity.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.db.session import reset_engine, get_session
from ncfd.db.models import Trial

def test_engine_reset():
    """Test resetting the engine and reconnecting."""
    print("🔄 Resetting database engine...")
    
    try:
        # Reset the engine
        reset_engine()
        print("✅ Engine reset successful")
        
        # Test new connection
        print("🔍 Testing new database connection...")
        with get_session() as session:
            trial_count = session.query(Trial).count()
            print(f"✅ Database connection successful: {trial_count} trials found")
            
        return True
        
    except Exception as e:
        print(f"❌ Engine reset or connection test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_engine_reset()
    sys.exit(0 if success else 1)
