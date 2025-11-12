#!/usr/bin/env python3
"""
Diagnostic script to investigate:
1. Why only 22 sources have data (not 30)
2. Why only 5 sources have processing logs
3. Why 80.6% of staging records are unprocessed
"""
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from database.config import get_db_session
from database.models.sources import Source
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from src.processing.pipeline import ProcessingPipeline


def main():
    print("=" * 80)
    print("PROCESSING ISSUES DIAGNOSTIC")
    print("=" * 80)
    
    with get_db_session() as session:
        # 1. Check source registration vs staging data
        print("\n[1] SOURCE REGISTRATION vs STAGING DATA")
        print("-" * 80)
        
        # Get all registered sources
        registered_sources = session.query(Source).filter(
            Source.deleted_at.is_(None)
        ).all()
        
        active_sources = [s for s in registered_sources if s.is_active]
        print(f"Total registered sources: {len(registered_sources)}")
        print(f"Active sources: {len(active_sources)}")
        
        # Get sources with staging data
        staging_sources = session.query(StagingRawData.source_system).distinct().all()
        staging_source_names = {s[0] for s in staging_sources}
        print(f"Sources with staging data: {len(staging_source_names)}")
        
        # Get sources with processing logs
        processing_sources = session.execute(
            text("SELECT DISTINCT source_name FROM source_processing_log")
        ).fetchall()
        processing_source_names = {s[0] for s in processing_sources}
        print(f"Sources with processing logs: {len(processing_source_names)}")
        
        # Find active sources without staging data
        active_names = {s.source_name for s in active_sources}
        active_without_staging = active_names - staging_source_names
        print(f"\nActive sources WITHOUT staging data ({len(active_without_staging)}):")
        for source in sorted(active_without_staging):
            print(f"  - {source}")
        
        # Find sources with staging data but no processing logs
        staging_without_processing = staging_source_names - processing_source_names
        print(f"\nSources with staging data but NO processing logs ({len(staging_without_processing)}):")
        for source in sorted(staging_without_processing):
            # Count staging records
            count = session.query(StagingRawData).filter(
                StagingRawData.source_system == source,
                StagingRawData.deleted_at.is_(None)
            ).count()
            print(f"  - {source}: {count} staging records")
        
        # 2. Check PROCESSOR_MAP coverage
        print("\n[2] PROCESSOR MAP COVERAGE")
        print("-" * 80)
        
        processor_map = ProcessingPipeline.PROCESSOR_MAP
        print(f"Processors available: {len(processor_map)}")
        print(f"Sources in PROCESSOR_MAP: {sorted(processor_map.keys())}")
        
        # Check which sources with staging data have processors
        staging_with_processor = staging_source_names & set(processor_map.keys())
        staging_without_processor = staging_source_names - set(processor_map.keys())
        
        print(f"\nSources with staging data AND processor: {len(staging_with_processor)}")
        for source in sorted(staging_with_processor):
            count = session.query(StagingRawData).filter(
                StagingRawData.source_system == source,
                StagingRawData.deleted_at.is_(None)
            ).count()
            processed = session.query(StagingRawData).filter(
                StagingRawData.source_system == source,
                StagingRawData.processed == True,
                StagingRawData.deleted_at.is_(None)
            ).count()
            pct = (processed/count*100) if count > 0 else 0
            print(f"  - {source}: {count} total, {processed} processed ({pct:.1f}%)")
        
        print(f"\nSources with staging data but NO processor: {len(staging_without_processor)}")
        for source in sorted(staging_without_processor):
            count = session.query(StagingRawData).filter(
                StagingRawData.source_system == source,
                StagingRawData.deleted_at.is_(None)
            ).count()
            print(f"  - {source}: {count} staging records (CANNOT BE PROCESSED)")
        
        # 3. Check unprocessed records breakdown
        print("\n[3] UNPROCESSED RECORDS BREAKDOWN")
        print("-" * 80)
        
        total_staging = session.query(StagingRawData).filter(
            StagingRawData.deleted_at.is_(None)
        ).count()
        
        processed_staging = session.query(StagingRawData).filter(
            StagingRawData.processed == True,
            StagingRawData.deleted_at.is_(None)
        ).count()
        
        unprocessed_staging = total_staging - processed_staging
        
        print(f"Total staging records: {total_staging}")
        print(f"Processed: {processed_staging} ({processed_staging/total_staging*100:.1f}%)")
        print(f"Unprocessed: {unprocessed_staging} ({unprocessed_staging/total_staging*100:.1f}%)")
        
        # Breakdown by source
        staging_by_source = session.execute(
            text("""
                SELECT source_system, 
                       COUNT(*) as total,
                       COUNT(CASE WHEN processed = true THEN 1 END) as processed,
                       COUNT(CASE WHEN processed = false THEN 1 END) as unprocessed
                FROM staging_raw_data
                WHERE deleted_at IS NULL
                GROUP BY source_system
                ORDER BY unprocessed DESC
            """)
        ).fetchall()
        
        print("\nBreakdown by source:")
        for source, total, processed, unprocessed in staging_by_source:
            has_processor = source in processor_map
            processor_status = "✓" if has_processor else "✗ NO PROCESSOR"
            print(f"  {source}:")
            print(f"    Total: {total}, Processed: {processed}, Unprocessed: {unprocessed}")
            print(f"    Processor: {processor_status}")
        
        # 4. Check processing logs by source
        print("\n[4] PROCESSING LOGS BY SOURCE")
        print("-" * 80)
        
        log_stats = session.execute(
            text("""
                SELECT source_name,
                       COUNT(*) as total_logs,
                       COUNT(CASE WHEN processing_status = 'success' THEN 1 END) as successful,
                       COUNT(CASE WHEN processing_status = 'failed' THEN 1 END) as failed,
                       COUNT(CASE WHEN processing_status = 'processing' THEN 1 END) as processing
                FROM source_processing_log
                GROUP BY source_name
                ORDER BY total_logs DESC
            """)
        ).fetchall()
        
        print(f"Total sources with processing logs: {len(log_stats)}")
        for source, total, successful, failed, processing in log_stats:
            print(f"  {source}:")
            print(f"    Total logs: {total}")
            print(f"    Successful: {successful}, Failed: {failed}, Processing: {processing}")
        
        # 5. Summary and root causes
        print("\n[5] ROOT CAUSE ANALYSIS")
        print("-" * 80)
        
        print("\nWhy only 22 sources have data (not 30):")
        print(f"  - {len(active_sources)} sources are marked as 'active'")
        print(f"  - {len(active_without_staging)} active sources have never been ingested")
        print(f"  - Only {len(staging_source_names)} sources actually have staging data")
        print(f"  → {len(active_without_staging)} active sources need ingestion scripts to be run")
        
        print("\nWhy only 5 sources have processing logs:")
        print(f"  - {len(processing_source_names)} sources have processing logs")
        print(f"  - {len(staging_with_processor)} sources have staging data AND processors")
        print(f"  - {len(staging_without_processor)} sources have staging data but NO processors")
        print(f"  → Processing pipeline has only been run for {len(processing_source_names)} sources")
        print(f"  → {len(staging_without_processor)} sources cannot be processed (no processor)")
        
        print("\nWhy 80.6% of staging records are unprocessed:")
        print(f"  - {unprocessed_staging} out of {total_staging} records are unprocessed")
        
        # Count unprocessable records (sources without processors)
        unprocessable_count = 0
        for source in staging_without_processor:
            count = session.query(StagingRawData).filter(
                StagingRawData.source_system == source,
                StagingRawData.deleted_at.is_(None)
            ).count()
            unprocessable_count += count
        
        processable_unprocessed = unprocessed_staging - unprocessable_count
        
        print(f"  - {unprocessable_count} records are from sources without processors (CANNOT BE PROCESSED)")
        print(f"  - {processable_unprocessed} records are from sources with processors (CAN BE PROCESSED)")
        print(f"  → Need to run processing pipeline for sources with processors")
        print(f"  → Need to implement processors for {len(staging_without_processor)} sources")


if __name__ == '__main__':
    main()

