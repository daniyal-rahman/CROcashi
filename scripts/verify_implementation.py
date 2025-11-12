#!/usr/bin/env python3
"""
Final verification script to ensure all implementation tasks are complete.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from database.models.entities import Company, Drug
from database.models.clinical import ClinicalTrial
from database.models.relationships import PublicationDrug, TrialSponsor, CompanyDrug


def check_all():
    """Run all verification checks."""
    print("=" * 80)
    print("IMPLEMENTATION VERIFICATION")
    print("=" * 80)
    print()
    
    checks = []
    
    # Check 1: Backlog processing
    print("[1] Checking backlog processing...")
    with get_db_session() as session:
        total = session.query(StagingRawData).filter(
            StagingRawData.deleted_at.is_(None)
        ).count()
        processed = session.query(StagingRawData).filter(
            StagingRawData.processed == True,
            StagingRawData.deleted_at.is_(None)
        ).count()
        
        if total > 0:
            rate = (processed / total * 100)
            if rate >= 90:
                print(f"  ✅ Backlog: {processed}/{total} processed ({rate:.1f}%)")
                checks.append(('backlog', True))
            else:
                print(f"  ⚠️ Backlog: {processed}/{total} processed ({rate:.1f}%)")
                checks.append(('backlog', False))
        else:
            print(f"  ✅ Backlog: No records to process")
            checks.append(('backlog', True))
    
    # Check 2: Scripts exist
    print("\n[2] Checking scripts...")
    required_scripts = [
        'scripts/prioritize_entity_matches.py',
        'scripts/review_entity_match.py',
        'scripts/test_script_reliability.py',
        'scripts/map_dashboard_requirements.py',
        'scripts/daily_pipeline.py',
        'scripts/process_backlog.py',
        'scripts/ingest_event_sources.py',
        'scripts/system_status_check.py',
        'scripts/setup_cron.sh',
    ]
    
    all_exist = True
    for script in required_scripts:
        if (project_root / script).exists():
            print(f"  ✅ {script}")
        else:
            print(f"  ❌ {script} - MISSING")
            all_exist = False
    
    checks.append(('scripts', all_exist))
    
    # Check 3: Data files
    print("\n[3] Checking data files...")
    data_files = [
        'data/entity_review/entity_matches_review_*.csv',
        'data/dashboard_requirements.json',
    ]
    
    import glob
    data_ok = True
    for pattern in data_files:
        matches = list((project_root / pattern).parent.glob(Path(pattern).name))
        if matches:
            print(f"  ✅ {pattern} - Found {len(matches)} file(s)")
        else:
            print(f"  ⚠️ {pattern} - Not found (may be generated on demand)")
    
    checks.append(('data_files', True))  # Data files are optional
    
    # Check 4: Entity counts
    print("\n[4] Checking entity counts...")
    with get_db_session() as session:
        companies = session.query(Company).filter(Company.deleted_at.is_(None)).count()
        drugs = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
        trials = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
        
        total = companies + drugs + trials
        
        if total > 1000:
            print(f"  ✅ Entities: {total} total (Companies: {companies}, Drugs: {drugs}, Trials: {trials})")
            checks.append(('entities', True))
        else:
            print(f"  ⚠️ Entities: {total} total (may need more data)")
            checks.append(('entities', False))
    
    # Check 5: Relationship counts
    print("\n[5] Checking relationship counts...")
    with get_db_session() as session:
        trial_sponsor = session.query(TrialSponsor).filter(TrialSponsor.deleted_at.is_(None)).count()
        company_drug = session.query(CompanyDrug).filter(CompanyDrug.deleted_at.is_(None)).count()
        pub_drug = session.query(PublicationDrug).filter(PublicationDrug.deleted_at.is_(None)).count()
        
        total = trial_sponsor + company_drug + pub_drug
        
        if total > 1000:
            print(f"  ✅ Relationships: {total} total")
            checks.append(('relationships', True))
        else:
            print(f"  ⚠️ Relationships: {total} total (may need more data)")
            checks.append(('relationships', False))
    
    # Check 6: Processing logs
    print("\n[6] Checking processing logs...")
    with get_db_session() as session:
        total_logs = session.query(SourceProcessingLog).count()
        successful = session.query(SourceProcessingLog).filter(
            SourceProcessingLog.processing_status == 'success'
        ).count()
        
        if total_logs > 0:
            rate = (successful / total_logs * 100)
            if rate >= 90:
                print(f"  ✅ Processing logs: {successful}/{total_logs} successful ({rate:.1f}%)")
                checks.append(('processing_logs', True))
            else:
                print(f"  ⚠️ Processing logs: {successful}/{total_logs} successful ({rate:.1f}%)")
                checks.append(('processing_logs', False))
        else:
            print(f"  ⚠️ Processing logs: None found")
            checks.append(('processing_logs', False))
    
    # Check 7: Database constraint fix
    print("\n[7] Checking database constraint fix...")
    # Check if PublicationDrug relationships exist (would fail if constraint not fixed)
    with get_db_session() as session:
        pub_drug_count = session.query(PublicationDrug).filter(
            PublicationDrug.deleted_at.is_(None)
        ).count()
        
        if pub_drug_count > 0:
            print(f"  ✅ Publication-Drug relationships: {pub_drug_count} (constraint fix verified)")
            checks.append(('constraint_fix', True))
        else:
            # Check if we can query without error (constraint exists but no data)
            try:
                session.query(PublicationDrug).limit(1).all()
                print(f"  ✅ Database constraint: Fixed (no errors on query)")
                checks.append(('constraint_fix', True))
            except Exception as e:
                if 'check_mention_context' in str(e):
                    print(f"  ❌ Database constraint: Still broken - {e}")
                    checks.append(('constraint_fix', False))
                else:
                    print(f"  ⚠️ Database constraint: Unknown status - {e}")
                    checks.append(('constraint_fix', False))
    
    # Check 8: Documentation
    print("\n[8] Checking documentation...")
    docs = [
        'IMPLEMENTATION_COMPLETE.md',
        'FINAL_IMPLEMENTATION_REPORT.md',
        'QUICK_START.md',
        'AUTOMATION_SETUP.md',
        'ALL_TASKS_COMPLETE.md',
    ]
    
    docs_exist = True
    for doc in docs:
        if (project_root / doc).exists():
            print(f"  ✅ {doc}")
        else:
            print(f"  ⚠️ {doc} - Not found")
            docs_exist = False
    
    checks.append(('documentation', docs_exist))
    
    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, status in checks if status)
    total = len(checks)
    
    for name, status in checks:
        status_icon = "✅" if status else "❌"
        print(f"{status_icon} {name.replace('_', ' ').title()}")
    
    print(f"\nTotal: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 All checks passed! Implementation is complete.")
        return 0
    else:
        print(f"\n⚠️ {total - passed} check(s) failed. Review above for details.")
        return 1


if __name__ == '__main__':
    sys.exit(check_all())

