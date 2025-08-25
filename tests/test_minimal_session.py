#!/usr/bin/env python3
"""
Minimal session test to isolate database connection issues.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.db.session import get_session, reset_engine
from ncfd.db.models import Trial

def test_minimal_session():
    """Test minimal session operations."""
    print("🔄 Resetting engine first...")
    reset_engine()
    
    print("🔍 Testing minimal session...")
    
    try:
        # Test 1: Simple session creation
        print("   - Creating session...")
        with get_session() as session:
            print("   - Session created successfully")
            
            # Test 2: Simple count query
            print("   - Running count query...")
            count = session.query(Trial).count()
            print(f"   - Count query successful: {count} trials")
            
            # Test 3: Simple select query
            print("   - Running select query...")
            trials = session.query(Trial).limit(3).all()
            print(f"   - Select query successful: {len(trials)} trials retrieved")
            
            for trial in trials:
                title = trial.brief_title or trial.official_title or 'No title'
                print(f"     - {trial.nct_id}: {title[:30]}...")
        
        print("✅ All session operations completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Session test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_minimal_session()
    sys.exit(0 if success else 1)
