"""
End-to-end integration test for OpenFDA data source.

Tests:
1. Fetching data from OpenFDA API
2. Loading to staging table
3. Processing through pipeline
4. Verifying entities and relationships created
5. Cross-source matching verification
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_openfda_end_to_end():
    """Test OpenFDA integration end-to-end."""
    print("\n" + "="*80)
    print("END-TO-END TEST: OpenFDA")
    print("="*80)
    
    try:
        from ingestion.openfda import search_drugs
        from src.processing.pipeline import ProcessingPipeline
        from database.config import get_db_session
        from database.models import Drug, Company, Disease, CompanyDrug, DrugIndication, StagingRawData
        
        # Step 1: Fetch data from OpenFDA
        print("\n1. Fetching data from OpenFDA...")
        result = search_drugs(
            query="cancer OR oncology OR immunotherapy",
            limit=20,
            save_dir=None,
            load_to_staging=True
        )
        
        if not isinstance(result, dict):
            print(f"❌ ERROR: Unexpected API response format: {type(result)}")
            return False
        
        patents_fetched = len(result.get('results', []))
        print(f"✅ Fetched {patents_fetched} drug labels from API")
        
        # Step 2: Verify staging
        print("\n2. Verifying staging table...")
        with get_db_session() as session:
            staged_count = session.query(StagingRawData).filter_by(
                source_system='openfda',
                processed=False
            ).count()
            print(f"✅ Found {staged_count} unprocessed records in staging")
        
        if staged_count == 0:
            print("⚠️  WARNING: No records in staging. Check if records were already processed.")
        
        # Step 3: Process through pipeline
        print("\n3. Processing through pipeline...")
        pipeline = ProcessingPipeline(batch_size=50)
        stats = pipeline.process_source('openfda', limit=20)
        
        print(f"✅ Processing complete:")
        print(f"   - Records processed: {stats.get('records_processed', 0)}")
        print(f"   - Records failed: {stats.get('records_failed', 0)}")
        print(f"   - Entities created: {stats.get('entities_created', 0)}")
        print(f"   - Entities matched: {stats.get('entities_matched', 0)}")
        print(f"   - Relationships: {stats.get('relationships_created', 0)}")
        
        # Step 4: Verify data in database
        print("\n4. Verifying data in database...")
        with get_db_session() as session:
            drugs = session.query(Drug).filter(
                Drug.data_sources.has_key('openfda')
            ).count()
            companies = session.query(Company).filter(
                Company.data_sources.has_key('openfda')
            ).count()
            diseases = session.query(Disease).filter(
                Disease.data_sources.has_key('openfda')
            ).count()
            company_drugs = session.query(CompanyDrug).count()
            drug_indications = session.query(DrugIndication).count()
            
            print(f"   Database totals:")
            print(f"   - Drugs (from OpenFDA): {drugs}")
            print(f"   - Companies (from OpenFDA): {companies}")
            print(f"   - Diseases (from OpenFDA): {diseases}")
            print(f"   - Company-Drug Relationships: {company_drugs}")
            print(f"   - Drug-Indication Relationships: {drug_indications}")
            
            # Cross-source matching verification
            print("\n5. Cross-source matching verification...")
            
            # Drugs appearing in both OpenFDA and FDA Drugs
            drugs_in_both = session.query(Drug).filter(
                Drug.data_sources.has_key('openfda'),
                Drug.data_sources.has_key('fda_drugs')
            ).count()
            print(f"   - Drugs appearing in both OpenFDA and FDA Drugs: {drugs_in_both}")
            
            # Companies appearing in both OpenFDA and PatentsView
            companies_in_both = session.query(Company).filter(
                Company.data_sources.has_key('openfda'),
                Company.data_sources.has_key('patentsview')
            ).count()
            print(f"   - Companies appearing in both OpenFDA and PatentsView: {companies_in_both}")
            
            # Companies appearing in both OpenFDA and FDA Drugs
            companies_fda = session.query(Company).filter(
                Company.data_sources.has_key('openfda'),
                Company.data_sources.has_key('fda_drugs')
            ).count()
            print(f"   - Companies appearing in both OpenFDA and FDA Drugs: {companies_fda}")
        
        # Step 6: Final validation
        if stats['records_processed'] > 0 and drugs > 0 and company_drugs > 0:
            print("\n✅ END-TO-END TEST PASSED!")
            print("   Data flowed successfully: Ingestion → Staging → Processing → Database")
            return True
        else:
            print("\n❌ END-TO-END TEST FAILED")
            print(f"   Records processed: {stats['records_processed']}, Drugs in DB: {drugs}, Company-Drug Rels: {company_drugs}")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_openfda_end_to_end()
    sys.exit(0 if success else 1)

