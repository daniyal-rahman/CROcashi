#!/usr/bin/env python3
"""
Simple database test to isolate transaction issues.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.db.session import get_session
from ncfd.db.models import Trial, TrialVersion, Company

def test_simple_db_operations():
    """Test basic database operations."""
    print("🔍 Testing simple database operations...")
    
    try:
        with get_session() as session:
            print("✅ Session created successfully")
            
            # Test 1: Count trials
            trial_count = session.query(Trial).count()
            print(f"📊 Trial count: {trial_count}")
            
            # Test 2: Count versions
            version_count = session.query(TrialVersion).count()
            print(f"📊 Version count: {version_count}")
            
            # Test 3: Count companies
            company_count = session.query(Company).count()
            print(f"📊 Company count: {company_count}")
            
            # Test 4: Get a few recent trials
            recent_trials = session.query(Trial).order_by(Trial.last_seen_at.desc()).limit(3).all()
            print(f"📊 Recent trials: {len(recent_trials)}")
            
            for trial in recent_trials:
                title = trial.brief_title or trial.official_title or 'No title'
                print(f"   - {trial.nct_id}: {title[:50]}...")
                print(f"     Phase: {trial.phase}, Status: {trial.status}")
            
            print("✅ All database operations completed successfully")
            
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = test_simple_db_operations()
    sys.exit(0 if success else 1)
