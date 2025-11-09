"""
Test the complete end-to-end flow:
1. Fetch data from source → 2. Load to staging → 3. Process → 4. Verify entities created
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def test_clinicaltrials_end_to_end():
    """Test ClinicalTrials.gov end-to-end flow"""
    print("\n" + "="*80)
    print("END-TO-END TEST: ClinicalTrials.gov")
    print("="*80)
    
    from ingestion.clinicaltrials_gov import fetch_studies_sample
    from src.processing.pipeline import ProcessingPipeline
    from database.config import get_db_session
    from database.models.clinical import ClinicalTrial
    from database.models.entities import Company, Institution, Drug, Disease
    
    print("\n1. Fetching data from ClinicalTrials.gov...")
    result = fetch_studies_sample(
        query_term="pfizer breast cancer",
        page_size=3,
        save_dir=None,
        load_to_staging=True
    )
    
    studies = result.get('studies', [])
    print(f"   ✓ Fetched {len(studies)} studies and loaded to staging")
    
    print("\n2. Running processing pipeline...")
    pipeline = ProcessingPipeline(batch_size=10)
    stats = pipeline.process_source('clinicaltrials_gov', limit=3)
    
    print(f"\n   Pipeline Results:")
    print(f"   - Processed: {stats['records_processed']}")
    print(f"   - Failed: {stats['records_failed']}")
    print(f"   - Entities created: {stats['entities_created']}")
    print(f"   - Entities matched: {stats['entities_matched']}")
    print(f"   - Relationships: {stats['relationships_created']}")
    
    print("\n3. Verifying data in database...")
    with get_db_session() as session:
        trials = session.query(ClinicalTrial).count()
        companies = session.query(Company).count()
        institutions = session.query(Institution).count()
        drugs = session.query(Drug).count()
        diseases = session.query(Disease).count()
        
        print(f"   Database totals:")
        print(f"   - Trials: {trials}")
        print(f"   - Companies: {companies}")
        print(f"   - Institutions: {institutions}")
        print(f"   - Drugs: {drugs}")
        print(f"   - Diseases: {diseases}")
        
        # Get a sample trial
        if trials > 0:
            trial = session.query(ClinicalTrial).first()
            print(f"\n   Sample trial:")
            print(f"   - NCT ID: {trial.nct_id}")
            print(f"   - Title: {trial.trial_title[:60]}...")
            print(f"   - Phase: {trial.phase}")
            print(f"   - Status: {trial.status}")
    
    if stats['records_processed'] > 0 and trials > 0:
        print("\n✅ END-TO-END TEST PASSED!")
        print("   Data flowed successfully: Ingestion → Staging → Processing → Database")
        return True
    else:
        print("\n❌ END-TO-END TEST FAILED")
        print(f"   Records processed: {stats['records_processed']}, Trials in DB: {trials}")
        return False


def test_pubmed_end_to_end():
    """Test PubMed end-to-end flow"""
    print("\n" + "="*80)
    print("END-TO-END TEST: PubMed")
    print("="*80)
    
    from ingestion.pubmed import fetch_sample
    from database.config import get_db_session
    from database.models.staging import StagingRawData
    
    print("\n1. Fetching data from PubMed...")
    result = fetch_sample(
        term="cancer drug trial",
        retmax=5,
        save_dir=None,
        load_to_staging=True
    )
    
    pmids = result.get('search', {}).get('esearchresult', {}).get('idlist', [])
    print(f"   ✓ Fetched {len(pmids)} publications and loaded to staging")
    
    print("\n2. Checking staging table...")
    with get_db_session() as session:
        pubmed_records = session.query(StagingRawData).filter_by(
            source_system='pubmed'
        ).count()
        
        print(f"   - PubMed records in staging: {pubmed_records}")
        
        if pubmed_records > 0:
            sample = session.query(StagingRawData).filter_by(
                source_system='pubmed'
            ).first()
            print(f"   - Sample PMID: {sample.source_record_id}")
            print(f"   - Processed: {sample.processed}")
    
    if pubmed_records > 0:
        print("\n✅ PUBMED STAGING TEST PASSED!")
        print("   Note: PubMed processor not yet implemented, so data stays in staging")
        return True
    else:
        print("\n❌ PUBMED STAGING TEST FAILED")
        return False


def main():
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*25 + "END-TO-END FLOW TEST" + " "*34 + "║")
    print("╚" + "="*78 + "╝")
    
    results = {
        "ClinicalTrials.gov": test_clinicaltrials_end_to_end(),
        "PubMed": test_pubmed_end_to_end(),
    }
    
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All end-to-end tests passed!")
        print("\nWhat works:")
        print("  ✓ ClinicalTrials.gov: Ingestion → Staging → Processing → Database")
        print("  ✓ PubMed: Ingestion → Staging (processor pending)")
        print("\nWhat's left:")
        print("  - Create PubMed processor")
        print("  - Wire up ~75 more data sources")
        print("  - Add more comprehensive testing")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

