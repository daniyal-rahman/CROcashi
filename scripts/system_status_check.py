#!/usr/bin/env python3
"""
Comprehensive system status check.
Shows current state of ingestion, processing, and relationships.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, func
from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from database.models.entities import Company, Drug, Disease, Institution
from database.models.clinical import ClinicalTrial
from database.models.publications import Publication, SECFiling
from database.models.relationships import (
    TrialSponsor, TrialDrug, TrialDisease,
    PublicationTrial, PublicationDrug, FilingDrug,
    CompanyDrug
)


def main():
    print("=" * 80)
    print("SYSTEM STATUS CHECK")
    print("=" * 80)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    with get_db_session() as session:
        # 1. Staging status
        print("[1] STAGING STATUS")
        print("-" * 80)
        check_staging_status(session)
        
        # 2. Processing status
        print("\n[2] PROCESSING STATUS")
        print("-" * 80)
        check_processing_status(session)
        
        # 3. Entity counts
        print("\n[3] ENTITY COUNTS")
        print("-" * 80)
        check_entity_counts(session)
        
        # 4. Relationship counts
        print("\n[4] RELATIONSHIP COUNTS")
        print("-" * 80)
        check_relationship_counts(session)
        
        # 5. Source health
        print("\n[5] SOURCE HEALTH")
        print("-" * 80)
        check_source_health(session)
        
        # 6. Recent activity
        print("\n[6] RECENT ACTIVITY")
        print("-" * 80)
        check_recent_activity(session)
        
        # 7. Overall assessment
        print("\n[7] OVERALL ASSESSMENT")
        print("-" * 80)
        overall_assessment(session)


def check_staging_status(session):
    """Check staging table status."""
    total = session.query(StagingRawData).filter(
        StagingRawData.deleted_at.is_(None)
    ).count()
    
    processed = session.query(StagingRawData).filter(
        StagingRawData.processed == True,
        StagingRawData.deleted_at.is_(None)
    ).count()
    
    unprocessed = total - processed
    
    print(f"Total staging records: {total}")
    print(f"Processed: {processed} ({processed/total*100:.1f}%)" if total > 0 else "Processed: 0")
    print(f"Unprocessed: {unprocessed} ({unprocessed/total*100:.1f}%)" if total > 0 else "Unprocessed: 0")
    
    # By source
    by_source = session.execute(
        text("""
            SELECT source_system,
                   COUNT(*) as total,
                   COUNT(CASE WHEN processed = true THEN 1 END) as processed
            FROM staging_raw_data
            WHERE deleted_at IS NULL
            GROUP BY source_system
            ORDER BY total DESC
            LIMIT 10
        """)
    ).fetchall()
    
    if by_source:
        print(f"\nTop sources by staging records:")
        for source, total_count, processed_count in by_source:
            pct = (processed_count / total_count * 100) if total_count > 0 else 0
            print(f"  {source}: {total_count} total, {processed_count} processed ({pct:.1f}%)")


def check_processing_status(session):
    """Check processing logs status."""
    total_logs = session.query(SourceProcessingLog).count()
    
    successful = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.processing_status == 'success'
    ).count()
    
    failed = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.processing_status == 'failed'
    ).count()
    
    processing = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.processing_status == 'processing'
    ).count()
    
    print(f"Total processing logs: {total_logs}")
    print(f"Successful: {successful} ({successful/total_logs*100:.1f}%)" if total_logs > 0 else "Successful: 0")
    print(f"Failed: {failed}")
    print(f"Processing: {processing}")
    
    # By source
    by_source = session.execute(
        text("""
            SELECT source_name,
                   COUNT(*) as total,
                   COUNT(CASE WHEN processing_status = 'success' THEN 1 END) as successful
            FROM source_processing_log
            GROUP BY source_name
            ORDER BY total DESC
            LIMIT 10
        """)
    ).fetchall()
    
    if by_source:
        print(f"\nTop sources by processing logs:")
        for source, total_count, successful_count in by_source:
            pct = (successful_count / total_count * 100) if total_count > 0 else 0
            print(f"  {source}: {total_count} logs, {successful_count} successful ({pct:.1f}%)")


def check_entity_counts(session):
    """Check entity counts."""
    companies = session.query(Company).filter(Company.deleted_at.is_(None)).count()
    drugs = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
    diseases = session.query(Disease).filter(Disease.deleted_at.is_(None)).count()
    trials = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
    pubs = session.query(Publication).filter(Publication.deleted_at.is_(None)).count()
    filings = session.query(SECFiling).filter(SECFiling.deleted_at.is_(None)).count()
    
    print(f"Companies: {companies}")
    print(f"Drugs: {drugs}")
    print(f"Diseases: {diseases}")
    print(f"Trials: {trials}")
    print(f"Publications: {pubs}")
    print(f"SEC Filings: {filings}")
    print(f"Total: {companies + drugs + diseases + trials + pubs + filings}")


def check_relationship_counts(session):
    """Check relationship counts."""
    trial_sponsor = session.query(TrialSponsor).filter(TrialSponsor.deleted_at.is_(None)).count()
    trial_drug = session.query(TrialDrug).filter(TrialDrug.deleted_at.is_(None)).count()
    trial_disease = session.query(TrialDisease).filter(TrialDisease.deleted_at.is_(None)).count()
    pub_trial = session.query(PublicationTrial).filter(PublicationTrial.deleted_at.is_(None)).count()
    pub_drug = session.query(PublicationDrug).filter(PublicationDrug.deleted_at.is_(None)).count()
    filing_drug = session.query(FilingDrug).filter(FilingDrug.deleted_at.is_(None)).count()
    company_drug = session.query(CompanyDrug).filter(CompanyDrug.deleted_at.is_(None)).count()
    
    print(f"Trial-Sponsor: {trial_sponsor}")
    print(f"Trial-Drug: {trial_drug}")
    print(f"Trial-Disease: {trial_disease}")
    print(f"Publication-Trial: {pub_trial} {'⚠️' if pub_trial == 0 else '✅'}")
    print(f"Publication-Drug: {pub_drug} {'⚠️' if pub_drug == 0 else '✅'}")
    print(f"Filing-Drug: {filing_drug} {'⚠️' if filing_drug == 0 else '✅'}")
    print(f"Company-Drug: {company_drug}")
    print(f"Total: {trial_sponsor + trial_drug + trial_disease + pub_trial + pub_drug + filing_drug + company_drug}")


def check_source_health(session):
    """Check source health."""
    # Sources with data
    sources_with_data = session.execute(
        text("""
            SELECT DISTINCT source_system
            FROM staging_raw_data
            WHERE deleted_at IS NULL
        """)
    ).fetchall()
    
    # Sources with processing logs
    sources_with_logs = session.execute(
        text("""
            SELECT DISTINCT source_name
            FROM source_processing_log
        """)
    ).fetchall()
    
    print(f"Sources with staging data: {len(sources_with_data)}")
    print(f"Sources with processing logs: {len(sources_with_logs)}")
    
    if sources_with_data:
        print(f"\nSources with data:")
        for (source,) in sources_with_data[:10]:
            count = session.query(StagingRawData).filter(
                StagingRawData.source_system == source,
                StagingRawData.deleted_at.is_(None)
            ).count()
            print(f"  {source}: {count} records")


def check_recent_activity(session):
    """Check recent activity."""
    # Recent processing
    recent_processing = session.execute(
        text("""
            SELECT source_name, MAX(processing_completed_at) as last_run
            FROM source_processing_log
            WHERE processing_completed_at IS NOT NULL
            GROUP BY source_name
            ORDER BY last_run DESC
            LIMIT 5
        """)
    ).fetchall()
    
    print(f"Recent processing activity:")
    for source, last_run in recent_processing:
        if last_run:
            days_ago = (datetime.now().date() - last_run).days
            print(f"  {source}: {days_ago} days ago")
    
    # Recent ingestion
    recent_ingestion = session.execute(
        text("""
            SELECT source_system, MAX(ingested_at) as last_ingested
            FROM staging_raw_data
            GROUP BY source_system
            ORDER BY last_ingested DESC
            LIMIT 5
        """)
    ).fetchall()
    
    print(f"\nRecent ingestion activity:")
    for source, last_ingested in recent_ingestion:
        if last_ingested:
            if isinstance(last_ingested, datetime):
                days_ago = (datetime.now() - last_ingested.replace(tzinfo=None)).days
            else:
                days_ago = (datetime.now().date() - last_ingested).days
            print(f"  {source}: {days_ago} days ago")


def overall_assessment(session):
    """Overall system assessment."""
    # Get key metrics
    total_staging = session.query(StagingRawData).filter(
        StagingRawData.deleted_at.is_(None)
    ).count()
    
    processed_staging = session.query(StagingRawData).filter(
        StagingRawData.processed == True,
        StagingRawData.deleted_at.is_(None)
    ).count()
    
    processing_rate = (processed_staging / total_staging * 100) if total_staging > 0 else 0
    
    total_entities = (
        session.query(Company).filter(Company.deleted_at.is_(None)).count() +
        session.query(Drug).filter(Drug.deleted_at.is_(None)).count() +
        session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
    )
    
    total_relationships = (
        session.query(TrialSponsor).filter(TrialSponsor.deleted_at.is_(None)).count() +
        session.query(TrialDrug).filter(TrialDrug.deleted_at.is_(None)).count() +
        session.query(TrialDisease).filter(TrialDisease.deleted_at.is_(None)).count()
    )
    
    print(f"Processing Rate: {processing_rate:.1f}%")
    print(f"Total Entities: {total_entities}")
    print(f"Total Relationships: {total_relationships}")
    
    # Status indicators
    if processing_rate >= 90:
        print(f"\n✅ Processing: Excellent ({processing_rate:.1f}%)")
    elif processing_rate >= 70:
        print(f"\n✅ Processing: Good ({processing_rate:.1f}%)")
    elif processing_rate >= 50:
        print(f"\n⚠️ Processing: Fair ({processing_rate:.1f}%)")
    else:
        print(f"\n❌ Processing: Poor ({processing_rate:.1f}%)")
    
    if total_entities > 1000:
        print(f"✅ Entities: Good coverage ({total_entities})")
    elif total_entities > 500:
        print(f"⚠️ Entities: Moderate coverage ({total_entities})")
    else:
        print(f"❌ Entities: Low coverage ({total_entities})")
    
    if total_relationships > 1000:
        print(f"✅ Relationships: Good coverage ({total_relationships})")
    elif total_relationships > 500:
        print(f"⚠️ Relationships: Moderate coverage ({total_relationships})")
    else:
        print(f"❌ Relationships: Low coverage ({total_relationships})")


if __name__ == '__main__':
    main()

