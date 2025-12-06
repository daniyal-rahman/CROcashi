#!/usr/bin/env python3
"""
Test script to activate 3 data sources (FDA Drugs, OpenFDA, PatentsView) 
with SMALL limits for validation.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_fda_drugs():
    """Test FDA Drugs source."""
    print("\n" + "="*80)
    print("1. FDA DRUGS")
    print("="*80)
    
    try:
        from ingestion.fda_drugs import download_all, ingest_fda_drugs
        
        # Download
        print("\n1.1 Downloading FDA files...")
        try:
            paths = download_all()
            print(f"✓ Downloaded {len(paths)} files")
        except Exception as e:
            print(f"⚠️  Download warning: {e}")
            print("  Continuing with existing files if any...")
        
        # Ingest to staging
        print("\n1.2 Ingesting to staging...")
        stats = ingest_fda_drugs(load_to_staging=True)
        if 'error' in stats:
            print(f"❌ Error: {stats['error']}")
            return False
        print(f"✓ Parsed {stats['parsed']} records")
        print(f"  - Inserted: {stats['inserted']}")
        print(f"  - Skipped: {stats['skipped']}")
        print(f"  - Errors: {stats['errors']}")
        
        # Process staging to entities/relationships
        print("\n1.3 Processing staging to entities/relationships (limit=200)...")
        from src.processing.pipeline import ProcessingPipeline
        pipeline = ProcessingPipeline()
        stats = pipeline.process_source('fda_drugs', limit=200)
        print(f"✓ Processing complete:")
        print(f"  - Records processed: {stats.get('records_processed', 0)}")
        print(f"  - Records failed: {stats.get('records_failed', 0)}")
        print(f"  - Entities created: {stats.get('entities_created', 0)}")
        print(f"  - Entities matched: {stats.get('entities_matched', 0)}")
        print(f"  - Relationships created: {stats.get('relationships_created', 0)}")
        return True
        
    except Exception as e:
        print(f"❌ Error in FDA Drugs: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_openfda():
    """Test OpenFDA source."""
    print("\n" + "="*80)
    print("2. OPENFDA")
    print("="*80)
    
    try:
        from ingestion.openfda import search_drugs
        
        # Ingest from API to staging
        print("\n2.1 Fetching from API and ingesting to staging (limit=100)...")
        data = search_drugs(limit=100, load_to_staging=True)
        results_count = len(data.get('results', []))
        print(f"✓ Fetched {results_count} records from API")
        
        # Process staging to entities/relationships
        print("\n2.2 Processing staging to entities/relationships (limit=200)...")
        from src.processing.pipeline import ProcessingPipeline
        pipeline = ProcessingPipeline()
        stats = pipeline.process_source('openfda', limit=200)
        print(f"✓ Processing complete:")
        print(f"  - Records processed: {stats.get('records_processed', 0)}")
        print(f"  - Records failed: {stats.get('records_failed', 0)}")
        print(f"  - Entities created: {stats.get('entities_created', 0)}")
        print(f"  - Entities matched: {stats.get('entities_matched', 0)}")
        print(f"  - Relationships created: {stats.get('relationships_created', 0)}")
        return True
        
    except Exception as e:
        print(f"❌ Error in OpenFDA: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_patentsview():
    """Test PatentsView source."""
    print("\n" + "="*80)
    print("3. PATENTSVIEW")
    print("="*80)
    
    try:
        from ingestion.patentsview import search_patents
        
        # Ingest from API to staging
        print("\n3.1 Fetching from API and ingesting to staging (limit=100)...")
        data = search_patents(limit=100, load_to_staging=True)
        patents_count = len(data.get('patents', []))
        print(f"✓ Fetched {patents_count} patents from API")
        
        # Process staging to entities/relationships
        print("\n3.2 Processing staging to entities/relationships (limit=200)...")
        from src.processing.pipeline import ProcessingPipeline
        pipeline = ProcessingPipeline()
        stats = pipeline.process_source('patentsview', limit=200)
        print(f"✓ Processing complete:")
        print(f"  - Records processed: {stats.get('records_processed', 0)}")
        print(f"  - Records failed: {stats.get('records_failed', 0)}")
        print(f"  - Entities created: {stats.get('entities_created', 0)}")
        print(f"  - Entities matched: {stats.get('entities_matched', 0)}")
        print(f"  - Relationships created: {stats.get('relationships_created', 0)}")
        return True
        
    except Exception as e:
        print(f"❌ Error in PatentsView: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_results():
    """Verify results with SQL queries."""
    print("\n" + "="*80)
    print("4. VERIFY RESULTS")
    print("="*80)
    
    try:
        from database.config import get_db_session
        from database.models import StagingRawData
        from database.models.relationships import CompanyDrug, DrugIndication, PatentCompany, PatentDrug
        
        with get_db_session() as session:
            # Staging counts per source
            print("\n4.1 Staging records per source:")
            for source in ['fda_drugs', 'openfda', 'patentsview']:
                total_count = session.query(StagingRawData).filter_by(
                    source_system=source
                ).count()
                unprocessed_count = session.query(StagingRawData).filter_by(
                    source_system=source,
                    processed=False
                ).count()
                processed_count = session.query(StagingRawData).filter_by(
                    source_system=source,
                    processed=True
                ).count()
                print(f"  - {source}: {total_count} total ({processed_count} processed, {unprocessed_count} unprocessed)")
            
            # Relationship counts
            print("\n4.2 Relationship counts:")
            company_drugs_count = session.query(CompanyDrug).filter(
                CompanyDrug.deleted_at.is_(None)
            ).count()
            print(f"  - company_drugs: {company_drugs_count}")
            
            drug_indications_count = session.query(DrugIndication).filter(
                DrugIndication.deleted_at.is_(None)
            ).count()
            print(f"  - drug_indications: {drug_indications_count}")
            
            patent_companies_count = session.query(PatentCompany).filter(
                PatentCompany.deleted_at.is_(None)
            ).count()
            print(f"  - patent_companies: {patent_companies_count}")
            
            patent_drugs_count = session.query(PatentDrug).filter(
                PatentDrug.deleted_at.is_(None)
            ).count()
            print(f"  - patent_drugs: {patent_drugs_count}")
            
            print("\n✓ Verification complete")
            return True
            
    except Exception as e:
        print(f"❌ Error in verification: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("TESTING 3 DATA SOURCES (SMALL LIMITS)")
    print("="*80)
    
    results = {}
    
    # Test FDA Drugs
    results['fda_drugs'] = test_fda_drugs()
    
    # Test OpenFDA
    results['openfda'] = test_openfda()
    
    # Test PatentsView
    results['patentsview'] = test_patentsview()
    
    # Verify results
    results['verification'] = verify_results()
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    for source, success in results.items():
        status = "✓ PASS" if success else "❌ FAIL"
        print(f"{status}: {source}")
    
    all_passed = all(results.values())
    print(f"\n{'✓ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
