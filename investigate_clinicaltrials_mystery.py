#!/usr/bin/env python3
"""
Investigate ClinicalTrials.gov Mystery:
- 1,037 deleted staging records
- 0% processed before deletion
- But 1,017 trials exist in database

Possible explanations:
A) Bulk manual load (bypassed staging)
B) Processing logs not created
C) Two-stage process (bulk load + later staging cleanup)
"""
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, func
from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.clinical import ClinicalTrial
from database.models.resolution import SourceProcessingLog
from datetime import datetime


def main():
    print("=" * 80)
    print("CLINICALTRIALS.GOV MYSTERY INVESTIGATION")
    print("=" * 80)
    
    with get_db_session() as session:
        # 1. Check if trials have staging_id references
        print("\n[1] CHECKING TRIAL SOURCE METADATA")
        print("-" * 80)
        check_trial_source_metadata(session)
        
        # 2. Check timestamp relationships
        print("\n[2] CHECKING TIMESTAMP RELATIONSHIPS")
        print("-" * 80)
        check_timestamps(session)
        
        # 3. Check for processing logs
        print("\n[3] CHECKING PROCESSING LOGS")
        print("-" * 80)
        check_processing_logs(session)
        
        # 4. Check deleted staging records
        print("\n[4] CHECKING DELETED STAGING RECORDS")
        print("-" * 80)
        check_deleted_staging(session)
        
        # 5. Check for orphaned staging records
        print("\n[5] CHECKING FOR ORPHANED STAGING RECORDS")
        print("-" * 80)
        check_orphaned_staging(session)
        
        # 6. Hypothesis testing
        print("\n[6] HYPOTHESIS TESTING")
        print("-" * 80)
        test_hypotheses(session)


def check_trial_source_metadata(session):
    """Check if trials have staging_id references or were bulk loaded."""
    print("Checking trial source metadata...")
    
    # Count trials from clinicaltrials_gov
    total_trials = session.query(ClinicalTrial).filter(
        ClinicalTrial.deleted_at.is_(None)
    ).count()
    
    ct_trials = session.query(ClinicalTrial).filter(
        ClinicalTrial.deleted_at.is_(None)
    ).all()
    
    # Check data_sources field
    trials_with_sources = 0
    trials_with_ct_source = 0
    staging_id_count = 0
    bulk_load_count = 0
    
    for trial in ct_trials:
        if trial.data_sources:
            trials_with_sources += 1
            if 'clinicaltrials_gov' in trial.data_sources:
                trials_with_ct_source += 1
                # Check if there's a staging_id reference
                source_info = trial.data_sources.get('clinicaltrials_gov', {})
                if 'staging_id' in source_info:
                    staging_id_count += 1
                if source_info.get('method') == 'bulk_load':
                    bulk_load_count += 1
    
    print(f"\nTotal trials: {total_trials}")
    print(f"Trials with data_sources: {trials_with_sources}")
    print(f"Trials with clinicaltrials_gov source: {trials_with_ct_source}")
    print(f"Trials with staging_id reference: {staging_id_count}")
    print(f"Trials marked as bulk_load: {bulk_load_count}")
    
    # Check created_at dates
    earliest_trial = session.query(func.min(ClinicalTrial.created_at)).filter(
        ClinicalTrial.deleted_at.is_(None)
    ).scalar()
    
    latest_trial = session.query(func.max(ClinicalTrial.created_at)).filter(
        ClinicalTrial.deleted_at.is_(None)
    ).scalar()
    
    print(f"\nTrial creation dates:")
    print(f"  Earliest: {earliest_trial}")
    print(f"  Latest: {latest_trial}")
    
    # Sample some trials to check their data_sources structure
    sample_trials = session.query(ClinicalTrial).filter(
        ClinicalTrial.deleted_at.is_(None)
    ).limit(5).all()
    
    print("\nSample trial data_sources:")
    for trial in sample_trials:
        if trial.data_sources:
            print(f"  {trial.nct_id}: {trial.data_sources}")
        else:
            print(f"  {trial.nct_id}: No data_sources")


def check_timestamps(session):
    """Check if trial creation happened before staging deletion."""
    print("Checking timestamp relationships...")
    
    # Get earliest trial creation
    earliest_trial = session.query(func.min(ClinicalTrial.created_at)).filter(
        ClinicalTrial.deleted_at.is_(None)
    ).scalar()
    
    # Get latest staging deletion
    latest_deletion = session.query(func.max(StagingRawData.deleted_at)).filter(
        StagingRawData.source_system == 'clinicaltrials_gov',
        StagingRawData.deleted_at.isnot(None)
    ).scalar()
    
    # Get earliest staging deletion
    earliest_deletion = session.query(func.min(StagingRawData.deleted_at)).filter(
        StagingRawData.source_system == 'clinicaltrials_gov',
        StagingRawData.deleted_at.isnot(None)
    ).scalar()
    
    print(f"\nTrial creation:")
    print(f"  Earliest: {earliest_trial}")
    
    print(f"\nStaging deletion:")
    if earliest_deletion:
        print(f"  Earliest: {earliest_deletion}")
    if latest_deletion:
        print(f"  Latest: {latest_deletion}")
    
    if earliest_trial and earliest_deletion:
        if earliest_trial < earliest_deletion:
            print(f"\n  ✓ Trials created BEFORE staging deletion (normal workflow)")
        else:
            print(f"\n  ⚠ Trials created AFTER staging deletion (unusual)")
    
    # Check if there's overlap
    if earliest_trial and latest_deletion:
        if earliest_trial < latest_deletion:
            print(f"  ✓ Timeline overlap exists (trials created during staging period)")
        else:
            print(f"  ⚠ No timeline overlap (trials created after all staging deleted)")


def check_processing_logs(session):
    """Check for any processing logs related to clinicaltrials_gov."""
    print("Checking processing logs...")
    
    # Count processing logs
    log_count = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.source_name == 'clinicaltrials_gov'
    ).count()
    
    print(f"\nTotal processing logs for clinicaltrials_gov: {log_count}")
    
    if log_count > 0:
        # Get log details
        logs = session.query(SourceProcessingLog).filter(
            SourceProcessingLog.source_name == 'clinicaltrials_gov'
        ).all()
        
        print(f"\nProcessing log details:")
        for log in logs[:10]:  # First 10
            print(f"  {log.source_identifier}: {log.processing_status} on {log.processing_started_at}")
        
        # Check status breakdown
        status_breakdown = session.execute(
            text("""
                SELECT processing_status, COUNT(*) as count
                FROM source_processing_log
                WHERE source_name = 'clinicaltrials_gov'
                GROUP BY processing_status
            """)
        ).fetchall()
        
        print(f"\nStatus breakdown:")
        for status, count in status_breakdown:
            print(f"  {status}: {count}")
    else:
        print("  ⚠ NO PROCESSING LOGS FOUND")
        print("  This confirms the mystery - 1,017 trials exist but no processing logs")


def check_deleted_staging(session):
    """Check details of deleted staging records."""
    print("Checking deleted staging records...")
    
    # Count deleted records
    deleted_count = session.query(StagingRawData).filter(
        StagingRawData.source_system == 'clinicaltrials_gov',
        StagingRawData.deleted_at.isnot(None)
    ).count()
    
    print(f"\nTotal deleted staging records: {deleted_count}")
    
    # Check if any were processed before deletion
    processed_before_delete = session.query(StagingRawData).filter(
        StagingRawData.source_system == 'clinicaltrials_gov',
        StagingRawData.deleted_at.isnot(None),
        StagingRawData.processed_at.isnot(None)
    ).count()
    
    print(f"Processed before deletion: {processed_before_delete}")
    print(f"Deleted without processing: {deleted_count - processed_before_delete}")
    
    # Get deletion date range
    deletion_dates = session.execute(
        text("""
            SELECT 
                DATE(deleted_at) as deletion_date,
                COUNT(*) as count
            FROM staging_raw_data
            WHERE source_system = 'clinicaltrials_gov'
              AND deleted_at IS NOT NULL
            GROUP BY DATE(deleted_at)
            ORDER BY deletion_date DESC
            LIMIT 10
        """)
    ).fetchall()
    
    print(f"\nDeletion dates (last 10):")
    for date, count in deletion_dates:
        print(f"  {date}: {count} records deleted")
    
    # Sample deleted records
    sample_deleted = session.query(StagingRawData).filter(
        StagingRawData.source_system == 'clinicaltrials_gov',
        StagingRawData.deleted_at.isnot(None)
    ).limit(5).all()
    
    print(f"\nSample deleted records:")
    for record in sample_deleted:
        print(f"  {record.source_record_id}:")
        print(f"    Ingested: {record.ingested_at}")
        print(f"    Processed: {record.processed_at}")
        print(f"    Deleted: {record.deleted_at}")


def check_orphaned_staging(session):
    """Check if deleted staging records have corresponding trials."""
    print("Checking for orphaned staging records...")
    
    # Get sample deleted staging record IDs
    deleted_records = session.query(StagingRawData).filter(
        StagingRawData.source_system == 'clinicaltrials_gov',
        StagingRawData.deleted_at.isnot(None)
    ).limit(10).all()
    
    print(f"\nChecking if deleted staging records have corresponding trials...")
    
    matched_count = 0
    unmatched_count = 0
    
    for record in deleted_records:
        # Try to find trial by NCT ID
        nct_id = record.source_record_id
        trial = session.query(ClinicalTrial).filter(
            ClinicalTrial.nct_id == nct_id,
            ClinicalTrial.deleted_at.is_(None)
        ).first()
        
        if trial:
            matched_count += 1
            print(f"  ✓ {nct_id}: Trial exists")
        else:
            unmatched_count += 1
            print(f"  ✗ {nct_id}: No trial found")
    
    print(f"\nSummary:")
    print(f"  Matched: {matched_count}")
    print(f"  Unmatched: {unmatched_count}")
    
    if matched_count > 0:
        print(f"\n  ✓ Some deleted staging records DO have corresponding trials")
        print(f"    This suggests trials were created from staging, but logs weren't created")
    else:
        print(f"\n  ⚠ No deleted staging records have corresponding trials")
        print(f"    This suggests staging records were deleted without processing")


def test_hypotheses(session):
    """Test the three hypotheses."""
    print("Testing hypotheses...")
    
    # Hypothesis A: Bulk manual load
    print("\n[Hypothesis A] Bulk manual load (bypassed staging):")
    trials_with_staging_ref = session.execute(
        text("""
            SELECT COUNT(*) 
            FROM clinical_trials 
            WHERE data_sources::text LIKE '%staging_id%'
              AND deleted_at IS NULL
        """)
    ).scalar()
    
    total_trials = session.query(ClinicalTrial).filter(
        ClinicalTrial.deleted_at.is_(None)
    ).count()
    
    staging_ref_pct = (trials_with_staging_ref / total_trials * 100) if total_trials > 0 else 0
    
    print(f"  Trials with staging_id reference: {trials_with_staging_ref} / {total_trials} ({staging_ref_pct:.1f}%)")
    
    if staging_ref_pct < 10:
        print(f"  ✓ LIKELY: Most trials don't reference staging (bulk load)")
    else:
        print(f"  ✗ UNLIKELY: Many trials reference staging")
    
    # Hypothesis B: Processing logs not created
    print("\n[Hypothesis B] Processing logs not created:")
    log_count = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.source_name == 'clinicaltrials_gov'
    ).count()
    
    print(f"  Processing logs: {log_count}")
    
    if log_count == 0:
        print(f"  ✓ LIKELY: No processing logs exist (logging may have failed)")
    else:
        print(f"  ✗ UNLIKELY: Processing logs exist")
    
    # Hypothesis C: Two-stage process
    print("\n[Hypothesis C] Two-stage process (bulk load + later staging cleanup):")
    
    # Check if trials were created in bulk (all at once)
    trial_creation_dates = session.execute(
        text("""
            SELECT DATE(created_at) as creation_date, COUNT(*) as count
            FROM clinical_trials
            WHERE deleted_at IS NULL
            GROUP BY DATE(created_at)
            ORDER BY count DESC
            LIMIT 5
        """)
    ).fetchall()
    
    print(f"  Top trial creation dates:")
    for date, count in trial_creation_dates:
        print(f"    {date}: {count} trials")
    
    if len(trial_creation_dates) > 0:
        max_count = max(c[1] for c in trial_creation_dates)
        if max_count > total_trials * 0.5:
            print(f"  ✓ LIKELY: Most trials created on single date (bulk load)")
        else:
            print(f"  ✗ UNLIKELY: Trials created over time (not bulk load)")
    
    # Final assessment
    print("\n[CONCLUSION]")
    print("-" * 80)
    
    if staging_ref_pct < 10 and log_count == 0:
        print("  MOST LIKELY: Hypothesis A + B")
        print("  - Trials were bulk loaded directly (bypassed staging)")
        print("  - Later, staging records were created but never processed")
        print("  - Staging records were cleaned up as 'old data'")
        print("  - No processing logs because bulk load bypassed processing pipeline")
    elif log_count == 0 and max_count > total_trials * 0.5:
        print("  MOST LIKELY: Hypothesis C")
        print("  - Initial bulk load created trials directly")
        print("  - Later ingestion created staging records")
        print("  - Staging records were never processed (already had trials)")
        print("  - Staging records were cleaned up")
    else:
        print("  UNCLEAR: Need more investigation")


if __name__ == '__main__':
    main()

