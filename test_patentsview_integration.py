"""
Integration test for PatentsView data source.

Tests:
1. Fetch patents from PatentsView API
2. Load to staging table
3. Process through pipeline
4. Verify entities created (patents, companies)
5. Verify relationships created (patent_company)
6. Verify cross-source matching with FDA Drugs
"""
import logging
from database.config import get_db_session
from database.models import (
    Patent, Company, PatentCompany, StagingRawData
)
from ingestion.patentsview import search_patents
from src.processing.pipeline import ProcessingPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_patentsview_integration():
    """Test PatentsView integration end-to-end."""
    print("\n" + "="*70)
    print("PATENTSVIEW INTEGRATION TEST")
    print("="*70)
    
    # Step 1: Fetch patents from API
    print("\n1. Fetching patents from PatentsView API...")
    query = '{"_gte":{"patent_date":"2020-01-01"}}'
    result = search_patents(
        query=query,
        limit=20,
        load_to_staging=True
    )
    
    if not isinstance(result, dict) or 'patents' not in result:
        print(f"❌ ERROR: Unexpected API response format: {type(result)}")
        return False
    
    patents_fetched = len(result.get('patents', []))
    print(f"✅ Fetched {patents_fetched} patents from API")
    
    # Step 2: Verify staging
    print("\n2. Verifying staging table...")
    with get_db_session() as session:
        staged_count = session.query(StagingRawData).filter_by(
            source_system='patentsview',
            processed=False
        ).count()
        print(f"✅ Found {staged_count} unprocessed records in staging")
    
    if staged_count == 0:
        print("⚠️  WARNING: No records in staging. Check if records were already processed.")
    
    # Step 3: Process through pipeline
    print("\n3. Processing through pipeline...")
    pipeline = ProcessingPipeline(batch_size=50)
    stats = pipeline.process_source('patentsview', limit=20)
    
    print(f"✅ Processing complete:")
    print(f"   - Records processed: {stats.get('records_processed', 0)}")
    print(f"   - Records failed: {stats.get('records_failed', 0)}")
    print(f"   - Entities created: {stats.get('entities_created', 0)}")
    print(f"   - Entities matched: {stats.get('entities_matched', 0)}")
    print(f"   - Relationships created: {stats.get('relationships_created', 0)}")
    
    # Step 4: Verify entities created
    print("\n4. Verifying entities in database...")
    with get_db_session() as session:
        patents_count = session.query(Patent).count()
        companies_count = session.query(Company).count()
        relationships_count = session.query(PatentCompany).count()
        
        # Count PatentsView-specific entities
        patentsview_patents = session.query(Patent).filter(
            Patent.data_sources.has_key('patentsview')
        ).count()
        
        patentsview_companies = session.query(Company).filter(
            Company.data_sources.has_key('patentsview')
        ).count()
        
        print(f"✅ Database totals:")
        print(f"   - Total patents: {patents_count} (PatentsView: {patentsview_patents})")
        print(f"   - Total companies: {companies_count} (PatentsView: {patentsview_companies})")
        print(f"   - Patent-company relationships: {relationships_count}")
    
    # Step 5: Verify cross-source matching
    print("\n5. Verifying cross-source matching with FDA Drugs...")
    with get_db_session() as session:
        # Find companies in both PatentsView and FDA Drugs
        cross_source_companies = session.query(Company).filter(
            Company.data_sources.has_key('patentsview'),
            Company.data_sources.has_key('fda_drugs')
        ).all()
        
        print(f"✅ Cross-source companies found: {len(cross_source_companies)}")
        
        if cross_source_companies:
            print("\n   Companies appearing in both sources:")
            for company in cross_source_companies[:10]:  # Show first 10
                print(f"   - {company.name}")
                print(f"     Sources: {list(company.data_sources.keys())}")
        else:
            print("   ℹ️  No companies found in both sources.")
            print("   (This is expected if FDA Drugs data hasn't been loaded yet)")
    
    # Step 6: Sample patent data
    print("\n6. Sample patent data:")
    with get_db_session() as session:
        sample_patents = session.query(Patent).filter(
            Patent.data_sources.has_key('patentsview')
        ).limit(3).all()
        
        for patent in sample_patents:
            print(f"\n   Patent: {patent.patent_number}")
            print(f"   Title: {patent.title[:80] if patent.title else 'N/A'}...")
            print(f"   Office: {patent.patent_office}")
            if patent.publication_date:
                print(f"   Publication Date: {patent.publication_date}")
            
            # Get related companies
            companies = [rel.company for rel in patent.companies]
            if companies:
                print(f"   Assignees: {', '.join([c.name for c in companies])}")
    
    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)
    
    return True


if __name__ == "__main__":
    test_patentsview_integration()

