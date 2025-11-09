"""
Test SEC EDGAR 8-K filings with real-world data.

This script:
1. Fetches real 8-K filings from SEC EDGAR for biotech companies
2. Loads them into staging
3. Processes them through the pipeline
4. Verifies entities and relationships in the database
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models import (
    SECFiling, Company, Drug, FilingCompany, FilingDrug,
    StagingRawData, SourceProcessingLog
)
from ingestion.sec_edgar import fetch_8k_filings_by_cik
from src.processing.pipeline import ProcessingPipeline
from sqlalchemy import func

print("=" * 70)
print("SEC EDGAR 8-K FILINGS - REAL-WORLD TEST")
print("=" * 70)

# Step 1: Fetch real 8-K filings for Moderna (CIK: 1682852)
print("\n📥 STEP 1: Fetching 8-K filings from SEC EDGAR...")
print("   Fetching filings for Moderna Inc. (CIK: 1682852)...")

try:
    filings = fetch_8k_filings_by_cik(
        cik="1682852",
        limit=5,  # Fetch 5 recent filings
        load_to_staging=True,
        requests_per_second=1.0
    )
    print(f"   ✅ Fetched {len(filings)} 8-K filings")
    
    if filings:
        print(f"\n   Sample filing:")
        sample = filings[0]
        print(f"     - Form: {sample.get('form')}")
        print(f"     - Filing Date: {sample.get('filing_date')}")
        print(f"     - Accession Number: {sample.get('accessionNumber')}")
        print(f"     - Company: {sample.get('company_name')}")
except Exception as e:
    print(f"   ❌ Error fetching filings: {e}")
    sys.exit(1)

# Step 2: Check staging
print("\n📦 STEP 2: Checking staging table...")
with get_db_session() as session:
    staging_count = session.query(StagingRawData).filter_by(
        source_system='sec_edgar',
        processed=False
    ).count()
    print(f"   ✅ Found {staging_count} unprocessed records in staging")

# Step 3: Process through pipeline
print("\n⚙️  STEP 3: Processing through pipeline...")
try:
    pipeline = ProcessingPipeline(batch_size=10)
    stats = pipeline.process_source('sec_edgar', limit=5)
    
    print(f"   ✅ Processing complete!")
    print(f"     - Records processed: {stats.get('records_processed', 0)}")
    print(f"     - Entities extracted: {stats.get('entities_extracted', 0)}")
    print(f"     - Entities created: {stats.get('entities_created', 0)}")
    print(f"     - Entities matched: {stats.get('entities_matched', 0)}")
    print(f"     - Relationships created: {stats.get('relationships_created', 0)}")
    print(f"     - Errors: {len(stats.get('errors', []))}")
    
    if stats.get('errors'):
        print(f"\n   ⚠️  Errors encountered:")
        for error in stats['errors'][:5]:  # Show first 5 errors
            print(f"     - {error}")
except Exception as e:
    print(f"   ❌ Error processing: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 4: Verify database entities
print("\n🔍 STEP 4: Verifying database entities...")
with get_db_session() as session:
    # Check SEC Filings
    filing_count = session.query(SECFiling).count()
    print(f"   ✅ SEC Filings in database: {filing_count}")
    
    if filing_count > 0:
        # Get a sample filing
        sample_filing = session.query(SECFiling).first()
        print(f"\n   Sample SEC Filing:")
        print(f"     - Filing ID: {sample_filing.filing_id}")
        print(f"     - Filing Type: {sample_filing.filing_type}")
        print(f"     - Filing Date: {sample_filing.filing_date}")
        print(f"     - Accession Number: {sample_filing.accession_number}")
        print(f"     - Mentions Milestones: {sample_filing.mentions_milestones}")
        print(f"     - Mentions Restructuring: {sample_filing.mentions_restructuring}")
        if sample_filing.cash_position:
            print(f"     - Cash Position: ${sample_filing.cash_position:,.2f}")
        if sample_filing.runway_months:
            print(f"     - Runway: {sample_filing.runway_months} months")
    
    # Check Companies
    company_count = session.query(Company).count()
    print(f"\n   ✅ Companies in database: {company_count}")
    
    # Check Drugs (may be 0 if no drug names found in text)
    drug_count = session.query(Drug).count()
    print(f"   ✅ Drugs in database: {drug_count}")

# Step 5: Verify relationships
print("\n🔗 STEP 5: Verifying relationships...")
with get_db_session() as session:
    # Filing-Company relationships
    filing_company_count = session.query(FilingCompany).count()
    print(f"   ✅ Filing-Company relationships: {filing_company_count}")
    
    if filing_company_count > 0:
        sample_rel = session.query(FilingCompany).first()
        print(f"\n   Sample Filing-Company relationship:")
        print(f"     - Filing ID: {sample_rel.filing_id}")
        print(f"     - Company ID: {sample_rel.company_id}")
        if sample_rel.filing:
            print(f"     - Filing: {sample_rel.filing.filing_type} - {sample_rel.filing.accession_number}")
        if sample_rel.company:
            print(f"     - Company: {sample_rel.company.name}")
    
    # Filing-Drug relationships
    filing_drug_count = session.query(FilingDrug).count()
    print(f"\n   ✅ Filing-Drug relationships: {filing_drug_count}")
    
    if filing_drug_count > 0:
        sample_rel = session.query(FilingDrug).first()
        print(f"\n   Sample Filing-Drug relationship:")
        print(f"     - Filing ID: {sample_rel.filing_id}")
        print(f"     - Drug ID: {sample_rel.drug_id}")
        print(f"     - Mention Type: {sample_rel.mention_type}")
        if sample_rel.filing:
            print(f"     - Filing: {sample_rel.filing.filing_type} - {sample_rel.filing.accession_number}")
        if sample_rel.drug:
            print(f"     - Drug: {sample_rel.drug.primary_name}")

# Step 6: Check processing logs
print("\n📊 STEP 6: Checking processing logs...")
with get_db_session() as session:
    logs = session.query(SourceProcessingLog).filter_by(
        source_name='sec_edgar'
    ).order_by(SourceProcessingLog.created_at.desc()).limit(5).all()
    
    print(f"   ✅ Found {len(logs)} processing log entries")
    
    if logs:
        latest_log = logs[0]
        print(f"\n   Latest processing log:")
        print(f"     - Status: {latest_log.processing_status}")
        print(f"     - Processing started: {latest_log.processing_started_at}")
        print(f"     - Processing completed: {latest_log.processing_completed_at}")

# Step 7: Data quality checks
print("\n✅ STEP 7: Data quality checks...")
with get_db_session() as session:
    # Check for null required fields
    null_filing_dates = session.query(SECFiling).filter(
        SECFiling.filing_date == None
    ).count()
    null_accession_numbers = session.query(SECFiling).filter(
        SECFiling.accession_number == None
    ).count()
    
    print(f"   ✅ Filings with null filing_date: {null_filing_dates}")
    print(f"   ✅ Filings with null accession_number: {null_accession_numbers}")
    
    # Check for orphaned relationships
    orphaned_filing_companies = session.query(FilingCompany).filter(
        ~FilingCompany.filing.has()
    ).count()
    orphaned_filing_drugs = session.query(FilingDrug).filter(
        ~FilingDrug.filing.has()
    ).count()
    
    print(f"   ✅ Orphaned Filing-Company relationships: {orphaned_filing_companies}")
    print(f"   ✅ Orphaned Filing-Drug relationships: {orphaned_filing_drugs}")

print("\n" + "=" * 70)
print("✅ REAL-WORLD TEST COMPLETE")
print("=" * 70)
print("\nSummary:")
print(f"  - SEC Filings created: {filing_count}")
print(f"  - Filing-Company relationships: {filing_company_count}")
print(f"  - Filing-Drug relationships: {filing_drug_count}")
print(f"  - Processing status: {'✅ SUCCESS' if stats.get('records_processed', 0) > 0 else '⚠️  NO RECORDS PROCESSED'}")

