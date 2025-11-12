#!/usr/bin/env python3
"""
Pre-Action Audit: Deep investigation before processing backlog
Addresses strategic concerns beyond technical symptoms.
"""
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, func
from database.config import get_db_session
from database.models.sources import Source
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from database.models.entities import Company, Drug, Disease, Institution
from database.models.clinical import ClinicalTrial
from database.models.publications import Publication, SECFiling
from database.models.relationships import (
    TrialSponsor, TrialDrug, TrialDisease,
    PublicationTrial, PublicationDrug, FilingDrug
)


def main():
    print("=" * 80)
    print("PRE-ACTION AUDIT: Strategic Root Cause Investigation")
    print("=" * 80)
    
    with get_db_session() as session:
        # 1. Verify processed records actually created entities
        print("\n[1] ENTITY CREATION VERIFICATION")
        print("-" * 80)
        verify_entity_creation(session)
        
        # 2. Check relationship coverage for processed sources
        print("\n[2] RELATIONSHIP COVERAGE ANALYSIS")
        print("-" * 80)
        check_relationship_coverage(session)
        
        # 3. Verify entity resolution quality
        print("\n[3] ENTITY RESOLUTION QUALITY")
        print("-" * 80)
        check_entity_resolution_quality(session)
        
        # 4. Investigate deleted staging records
        print("\n[4] DELETED STAGING RECORDS INVESTIGATION")
        print("-" * 80)
        investigate_deleted_records(session)
        
        # 5. Investigate critical 0-record sources
        print("\n[5] CRITICAL SOURCES INVESTIGATION (0 records)")
        print("-" * 80)
        investigate_critical_sources(session)
        
        # 6. Check for automation/scheduling
        print("\n[6] AUTOMATION & INFRASTRUCTURE CHECK")
        print("-" * 80)
        check_automation(session)
        
        # 7. Strategic priority assessment
        print("\n[7] STRATEGIC PRIORITY ASSESSMENT")
        print("-" * 80)
        strategic_priority_assessment(session)
        
        # 8. Resource/cost implications
        print("\n[8] RESOURCE & COST IMPLICATIONS")
        print("-" * 80)
        assess_resource_implications(session)


def verify_entity_creation(session):
    """Verify that processed records actually created entities."""
    print("Checking if processed records created entities...")
    
    # Get sources with processing logs
    processed_sources = session.execute(
        text("SELECT DISTINCT source_name FROM source_processing_log WHERE processing_status = 'success'")
    ).fetchall()
    processed_source_names = {s[0] for s in processed_sources}
    
    print(f"\nSources with successful processing logs: {len(processed_source_names)}")
    print(f"  {sorted(processed_source_names)}")
    
    # Check entity counts by source (from processing logs)
    entity_stats = {}
    for source in processed_source_names:
        stats = session.execute(
            text("""
                SELECT 
                    SUM(entities_created) as created,
                    SUM(entities_matched) as matched,
                    SUM(relationships_created) as relationships,
                    COUNT(*) as records_processed
                FROM source_processing_log
                WHERE source_name = :source
                  AND processing_status = 'success'
            """),
            {'source': source}
        ).fetchone()
        
        if stats and stats[3] > 0:  # records_processed > 0
            entity_stats[source] = {
                'entities_created': stats[0] or 0,
                'entities_matched': stats[1] or 0,
                'relationships_created': stats[2] or 0,
                'records_processed': stats[3]
            }
    
    print("\nEntity creation from processing logs:")
    for source, stats in sorted(entity_stats.items()):
        print(f"  {source}:")
        print(f"    Records processed: {stats['records_processed']}")
        print(f"    Entities created: {stats['entities_created']}")
        print(f"    Entities matched: {stats['entities_matched']}")
        print(f"    Relationships created: {stats['relationships_created']}")
        if stats['records_processed'] > 0:
            entities_per_record = (stats['entities_created'] + stats['entities_matched']) / stats['records_processed']
            print(f"    Entities per record: {entities_per_record:.2f}")
    
    # Check actual entity counts in database
    print("\nActual entity counts in database:")
    company_count = session.query(Company).filter(Company.deleted_at.is_(None)).count()
    drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
    disease_count = session.query(Disease).filter(Disease.deleted_at.is_(None)).count()
    trial_count = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
    pub_count = session.query(Publication).filter(Publication.deleted_at.is_(None)).count()
    filing_count = session.query(SECFiling).filter(SECFiling.deleted_at.is_(None)).count()
    
    print(f"  Companies: {company_count}")
    print(f"  Drugs: {drug_count}")
    print(f"  Diseases: {disease_count}")
    print(f"  Trials: {trial_count}")
    print(f"  Publications: {pub_count}")
    print(f"  SEC Filings: {filing_count}")
    
    # Check if entities have source metadata
    print("\nEntity source coverage:")
    companies_with_sources = session.query(Company).filter(
        Company.deleted_at.is_(None),
        Company.data_sources.isnot(None)
    ).count()
    drugs_with_sources = session.query(Drug).filter(
        Drug.deleted_at.is_(None),
        Drug.data_sources.isnot(None)
    ).count()
    
    print(f"  Companies with source metadata: {companies_with_sources} / {company_count}")
    print(f"  Drugs with source metadata: {drugs_with_sources} / {drug_count}")


def check_relationship_coverage(session):
    """Check relationship coverage for processed sources."""
    print("Analyzing relationship creation...")
    
    # Check relationships by source (from processing logs)
    rel_stats = session.execute(
        text("""
            SELECT source_name, 
                   SUM(relationships_created) as total_rels,
                   COUNT(*) as processed_records
            FROM source_processing_log
            WHERE processing_status = 'success'
              AND relationships_created > 0
            GROUP BY source_name
            ORDER BY total_rels DESC
        """)
    ).fetchall()
    
    print("\nRelationships created by source (from logs):")
    for source, total_rels, records in rel_stats:
        avg_per_record = total_rels / records if records > 0 else 0
        print(f"  {source}: {total_rels} relationships from {records} records ({avg_per_record:.2f} per record)")
    
    # Check actual relationship counts
    print("\nActual relationship counts in database:")
    trial_sponsor_count = session.query(TrialSponsor).filter(TrialSponsor.deleted_at.is_(None)).count()
    trial_drug_count = session.query(TrialDrug).filter(TrialDrug.deleted_at.is_(None)).count()
    trial_disease_count = session.query(TrialDisease).filter(TrialDisease.deleted_at.is_(None)).count()
    pub_trial_count = session.query(PublicationTrial).filter(PublicationTrial.deleted_at.is_(None)).count()
    pub_drug_count = session.query(PublicationDrug).filter(PublicationDrug.deleted_at.is_(None)).count()
    filing_drug_count = session.query(FilingDrug).filter(FilingDrug.deleted_at.is_(None)).count()
    
    print(f"  Trial-Sponsor: {trial_sponsor_count}")
    print(f"  Trial-Drug: {trial_drug_count}")
    print(f"  Trial-Disease: {trial_disease_count}")
    print(f"  Publication-Trial: {pub_trial_count}")
    print(f"  Publication-Drug: {pub_drug_count}")
    print(f"  Filing-Drug: {filing_drug_count}")
    
    # Check for orphaned relationships
    orphaned_trials = session.execute(
        text("""
            SELECT COUNT(*) FROM trial_sponsors ts
            LEFT JOIN clinical_trials ct ON ts.trial_id = ct.trial_id
            WHERE ct.trial_id IS NULL AND ts.deleted_at IS NULL
        """)
    ).scalar()
    
    if orphaned_trials > 0:
        print(f"\n  ⚠ WARNING: {orphaned_trials} orphaned trial-sponsor relationships")


def check_entity_resolution_quality(session):
    """Verify entity resolution is working correctly."""
    print("Checking entity resolution quality...")
    
    # Check match candidates (needs review)
    needs_review = session.execute(
        text("""
            SELECT COUNT(*) FROM entity_match_candidates
            WHERE status = 'needs_review'
              AND deleted_at IS NULL
        """)
    ).scalar()
    
    print(f"\nEntity match candidates needing review: {needs_review}")
    
    # Check resolution statistics from processing logs
    resolution_stats = session.execute(
        text("""
            SELECT 
                source_name,
                AVG(entities_extracted) as avg_extracted,
                AVG(entities_matched::float / NULLIF(entities_extracted, 0)) as match_rate,
                AVG(entities_created::float / NULLIF(entities_extracted, 0)) as creation_rate
            FROM source_processing_log
            WHERE processing_status = 'success'
              AND entities_extracted > 0
            GROUP BY source_name
            ORDER BY source_name
        """)
    ).fetchall()
    
    print("\nEntity resolution rates by source:")
    for source, avg_extracted, match_rate, creation_rate in resolution_stats:
        match_pct = (match_rate * 100) if match_rate else 0
        create_pct = (creation_rate * 100) if creation_rate else 0
        print(f"  {source}:")
        print(f"    Avg extracted per record: {avg_extracted:.2f}")
        print(f"    Match rate: {match_pct:.1f}%")
        print(f"    Creation rate: {create_pct:.1f}%")
    
    # Check for failed processing
    failed_count = session.execute(
        text("""
            SELECT COUNT(*) FROM source_processing_log
            WHERE processing_status = 'failed'
        """)
    ).scalar()
    
    if failed_count > 0:
        print(f"\n  ⚠ WARNING: {failed_count} failed processing logs")
        
        failed_by_source = session.execute(
            text("""
                SELECT source_name, COUNT(*) as failed_count
                FROM source_processing_log
                WHERE processing_status = 'failed'
                GROUP BY source_name
                ORDER BY failed_count DESC
            """)
        ).fetchall()
        
        print("  Failed by source:")
        for source, count in failed_by_source:
            print(f"    {source}: {count} failures")


def investigate_deleted_records(session):
    """Investigate deleted staging records - verify they created entities."""
    print("Investigating deleted staging records...")
    
    # Count deleted records
    deleted_count = session.query(StagingRawData).filter(
        StagingRawData.deleted_at.isnot(None)
    ).count()
    
    total_count = session.query(StagingRawData).count()
    non_deleted_count = total_count - deleted_count
    
    print(f"\nTotal staging records: {total_count}")
    print(f"Deleted records: {deleted_count} ({deleted_count/total_count*100:.1f}%)")
    print(f"Non-deleted records: {non_deleted_count}")
    
    # Check deleted records by source
    deleted_by_source = session.execute(
        text("""
            SELECT source_system, COUNT(*) as deleted_count,
                   COUNT(CASE WHEN processed_at IS NOT NULL THEN 1 END) as processed_before_delete
            FROM staging_raw_data
            WHERE deleted_at IS NOT NULL
            GROUP BY source_system
            ORDER BY deleted_count DESC
            LIMIT 10
        """)
    ).fetchall()
    
    print("\nTop sources with deleted records:")
    for source, deleted, processed in deleted_by_source:
        pct_processed = (processed / deleted * 100) if deleted > 0 else 0
        print(f"  {source}: {deleted} deleted ({processed} were processed before deletion, {pct_processed:.1f}%)")
    
    # Check if there's a pattern (all processed records get deleted?)
    processed_and_deleted = session.execute(
        text("""
            SELECT COUNT(*) FROM staging_raw_data
            WHERE processed_at IS NOT NULL
              AND deleted_at IS NOT NULL
        """)
    ).scalar()
    
    processed_not_deleted = session.execute(
        text("""
            SELECT COUNT(*) FROM staging_raw_data
            WHERE processed_at IS NOT NULL
              AND deleted_at IS NULL
        """)
    ).scalar()
    
    print(f"\nProcessed records:")
    print(f"  Processed and deleted: {processed_and_deleted}")
    print(f"  Processed but not deleted: {processed_not_deleted}")
    
    if processed_and_deleted > processed_not_deleted * 10:
        print("  ⚠ WARNING: Most processed records are deleted - may indicate cleanup policy")
    else:
        print("  ✓ Processed records are mostly retained")
    
    # Check entity counts vs deleted staging records
    # If 1,824 records were processed and deleted, we should have corresponding entities
    print("\nEntity count vs deleted staging records:")
    company_count = session.query(Company).filter(Company.deleted_at.is_(None)).count()
    drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
    trial_count = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
    
    print(f"  Companies: {company_count}")
    print(f"  Drugs: {drug_count}")
    print(f"  Trials: {trial_count}")
    
    if processed_and_deleted > 0:
        entities_per_deleted = (company_count + drug_count + trial_count) / processed_and_deleted
        print(f"  Entities per deleted processed record: {entities_per_deleted:.2f}")
        
        if entities_per_deleted < 0.1:
            print("  ⚠ WARNING: Very few entities per deleted record - may indicate processing failures")


def investigate_critical_sources(session):
    """Investigate why critical sources show 0 records."""
    critical_sources = ['clinicaltrials_gov', 'sec_edgar', 'pubmed', 'fda_drugs']
    
    print("Investigating critical sources with 0 staging records...")
    
    for source in critical_sources:
        print(f"\n{source}:")
        
        # Check staging records
        staging_count = session.query(StagingRawData).filter(
            StagingRawData.source_system == source,
            StagingRawData.deleted_at.is_(None)
        ).count()
        
        # Check all staging records (including deleted)
        total_staging = session.query(StagingRawData).filter(
            StagingRawData.source_system == source
        ).count()
        
        # Check processing logs
        log_count = session.execute(
            text("SELECT COUNT(*) FROM source_processing_log WHERE source_name = :source"),
            {'source': source}
        ).scalar()
        
        # Check if source is registered and active
        source_obj = session.query(Source).filter(
            Source.source_name == source,
            Source.deleted_at.is_(None)
        ).first()
        
        # Check entities from this source
        if source == 'clinicaltrials_gov':
            trial_count = session.query(ClinicalTrial).filter(
                ClinicalTrial.deleted_at.is_(None)
            ).count()
            print(f"  Staging records (non-deleted): {staging_count}")
            print(f"  Staging records (all): {total_staging}")
            print(f"  Processing logs: {log_count}")
            print(f"  Registered: {source_obj is not None}")
            print(f"  Active: {source_obj.is_active if source_obj else False}")
            print(f"  Trials in database: {trial_count}")
            if trial_count > 0 and staging_count == 0:
                print(f"  ✓ Has entities but no staging records - likely processed and cleaned up")
        
        elif source == 'sec_edgar':
            filing_count = session.query(SECFiling).filter(
                SECFiling.deleted_at.is_(None)
            ).count()
            print(f"  Staging records (non-deleted): {staging_count}")
            print(f"  Staging records (all): {total_staging}")
            print(f"  Processing logs: {log_count}")
            print(f"  Registered: {source_obj is not None}")
            print(f"  Active: {source_obj.is_active if source_obj else False}")
            print(f"  SEC Filings in database: {filing_count}")
            if filing_count > 0 and staging_count == 0:
                print(f"  ✓ Has entities but no staging records - likely processed and cleaned up")
        
        elif source == 'pubmed':
            pub_count = session.query(Publication).filter(
                Publication.deleted_at.is_(None)
            ).count()
            print(f"  Staging records (non-deleted): {staging_count}")
            print(f"  Staging records (all): {total_staging}")
            print(f"  Processing logs: {log_count}")
            print(f"  Registered: {source_obj is not None}")
            print(f"  Active: {source_obj.is_active if source_obj else False}")
            print(f"  Publications in database: {pub_count}")
            if pub_count > 0 and staging_count == 0:
                print(f"  ✓ Has entities but no staging records - likely processed and cleaned up")
        
        elif source == 'fda_drugs':
            drug_count = session.query(Drug).filter(
                Drug.deleted_at.is_(None)
            ).count()
            print(f"  Staging records (non-deleted): {staging_count}")
            print(f"  Staging records (all): {total_staging}")
            print(f"  Processing logs: {log_count}")
            print(f"  Registered: {source_obj is not None}")
            print(f"  Active: {source_obj.is_active if source_obj else False}")
            print(f"  Drugs in database: {drug_count}")
            if drug_count > 0 and staging_count == 0:
                print(f"  ✓ Has entities but no staging records - likely processed and cleaned up")
        
        # Check if ingestion script exists
        ingestion_script = project_root / 'ingestion' / f'{source}.py'
        if ingestion_script.exists():
            print(f"  Ingestion script exists: ✓")
        else:
            print(f"  Ingestion script exists: ✗")


def check_automation(session):
    """Check for automation, scheduling, cron jobs."""
    print("Checking for automation infrastructure...")
    
    # Check for cron jobs or scheduled tasks
    cron_file = project_root / 'scripts' / 'cron' / 'schedule.sh'
    if cron_file.exists():
        print(f"  ✓ Found cron schedule: {cron_file}")
        try:
            with open(cron_file) as f:
                content = f.read()
                if 'ingestion' in content.lower():
                    print("    Contains ingestion commands")
                if 'processing' in content.lower():
                    print("    Contains processing commands")
        except:
            pass
    else:
        print("  ✗ No cron schedule found")
    
    # Check for recent processing activity
    recent_activity = session.execute(
        text("""
            SELECT source_name, MAX(processing_completed_at) as last_run
            FROM source_processing_log
            WHERE processing_completed_at IS NOT NULL
            GROUP BY source_name
            ORDER BY last_run DESC
            LIMIT 5
        """)
    ).fetchall()
    
    print("\nRecent processing activity:")
    for source, last_run in recent_activity:
        if last_run:
            days_ago = (datetime.now().date() - last_run).days
            print(f"  {source}: {days_ago} days ago")
        else:
            print(f"  {source}: Never")
    
    # Check for ingestion activity patterns
    recent_ingestion = session.execute(
        text("""
            SELECT source_system, MAX(ingested_at) as last_ingested
            FROM staging_raw_data
            GROUP BY source_system
            ORDER BY last_ingested DESC
            LIMIT 5
        """)
    ).fetchall()
    
    print("\nRecent ingestion activity:")
    for source, last_ingested in recent_ingestion:
        if last_ingested:
            if isinstance(last_ingested, datetime):
                if last_ingested.tzinfo is None:
                    # Make it timezone-aware
                    last_ingested = last_ingested.replace(tzinfo=datetime.now().astimezone().tzinfo)
                days_ago = (datetime.now().astimezone() - last_ingested).days
            else:
                days_ago = (datetime.now().date() - last_ingested).days
            print(f"  {source}: {days_ago} days ago")
        else:
            print(f"  {source}: Never")


def strategic_priority_assessment(session):
    """Assess strategic priority of sources."""
    print("Strategic priority assessment...")
    
    # Entity sources (foundational)
    entity_sources = {
        'clinicaltrials_gov': {'type': 'entity', 'entities': ['trials', 'companies', 'drugs', 'diseases']},
        'fda_drugs': {'type': 'entity', 'entities': ['drugs', 'companies']},
        'pubmed': {'type': 'entity', 'entities': ['publications']},
    }
    
    # Relationship sources
    relationship_sources = {
        'sec_edgar': {'type': 'relationship', 'value': 'financial distress signals'},
        'fda_warning_letters': {'type': 'relationship', 'value': 'regulatory issues'},
    }
    
    # Event sources
    event_sources = {
        'fda_breakthrough': {'type': 'event', 'value': 'positive signals'},
        'fda_clinical_hold': {'type': 'event', 'value': 'failure signals'},
    }
    
    print("\nEntity sources (foundational - build map first):")
    for source, info in entity_sources.items():
        staging_count = session.query(StagingRawData).filter(
            StagingRawData.source_system == source,
            StagingRawData.deleted_at.is_(None)
        ).count()
        print(f"  {source}: {staging_count} staging records")
        print(f"    Entities: {', '.join(info['entities'])}")
    
    print("\nRelationship sources (connect entities):")
    for source, info in relationship_sources.items():
        staging_count = session.query(StagingRawData).filter(
            StagingRawData.source_system == source,
            StagingRawData.deleted_at.is_(None)
        ).count()
        print(f"  {source}: {staging_count} staging records")
        print(f"    Value: {info['value']}")
    
    print("\nEvent sources (failure signals):")
    for source, info in event_sources.items():
        staging_count = session.query(StagingRawData).filter(
            StagingRawData.source_system == source,
            StagingRawData.deleted_at.is_(None)
        ).count()
        print(f"  {source}: {staging_count} staging records")
        print(f"    Value: {info['value']}")
    
    # Check entity coverage
    print("\nCurrent entity coverage:")
    company_count = session.query(Company).filter(Company.deleted_at.is_(None)).count()
    drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
    trial_count = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
    
    print(f"  Companies: {company_count}")
    print(f"  Drugs: {drug_count}")
    print(f"  Trials: {trial_count}")
    
    if company_count < 100 or drug_count < 100:
        print("  ⚠ WARNING: Low entity coverage - may need to ingest entity sources first")


def assess_resource_implications(session):
    """Assess resource and cost implications of processing backlog."""
    print("Assessing resource implications...")
    
    # Count unprocessed records
    unprocessed = session.query(StagingRawData).filter(
        StagingRawData.processed == False,
        StagingRawData.deleted_at.is_(None)
    ).count()
    
    print(f"\nUnprocessed records: {unprocessed}")
    
    # Estimate processing time (rough estimate: 1-5 seconds per record)
    min_time_seconds = unprocessed * 1
    max_time_seconds = unprocessed * 5
    min_time_hours = min_time_seconds / 3600
    max_time_hours = max_time_seconds / 3600
    
    print(f"Estimated processing time:")
    print(f"  Minimum: {min_time_hours:.1f} hours ({min_time_seconds/60:.0f} minutes)")
    print(f"  Maximum: {max_time_hours:.1f} hours ({max_time_seconds/60:.0f} minutes)")
    
    # Check for API-heavy sources
    api_heavy_sources = ['pubmed', 'clinicaltrials_gov', 'sec_edgar']
    api_records = 0
    for source in api_heavy_sources:
        count = session.query(StagingRawData).filter(
            StagingRawData.source_system == source,
            StagingRawData.processed == False,
            StagingRawData.deleted_at.is_(None)
        ).count()
        api_records += count
    
    if api_records > 0:
        print(f"\n  ⚠ WARNING: {api_records} records from API-heavy sources")
        print(f"    May hit rate limits or incur API costs")
    
    # Check database size implications
    print("\nDatabase implications:")
    print(f"  Each processed record may create 1-10 entities")
    print(f"  Estimated new entities: {unprocessed * 3} - {unprocessed * 10}")
    print(f"  Estimated new relationships: {unprocessed * 2} - {unprocessed * 5}")
    
    print("\nRecommendation:")
    print("  Start with small batch (10-50 records) to test")
    print("  Monitor processing time and resource usage")
    print("  Scale up gradually")


if __name__ == '__main__':
    main()

