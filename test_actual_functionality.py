"""
Test to verify the entire pipeline actually works.
This will expose any fundamental issues in the LLM-generated code.
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_ingestion():
    """Test 1: Can we actually fetch data from ClinicalTrials.gov?"""
    print("\n" + "="*80)
    print("TEST 1: Ingestion - Can we fetch data from ClinicalTrials.gov?")
    print("="*80)
    
    try:
        from ingestion.clinicaltrials_gov import fetch_studies_sample
        
        # Try to fetch actual data
        result = fetch_studies_sample(
            query_term="cancer",
            page_size=5,
            save_dir=None  # Don't save yet
        )
        
        if not result:
            print("❌ FAIL: No data returned")
            return False
        
        if 'studies' not in result:
            print(f"❌ FAIL: Response missing 'studies' key. Keys: {list(result.keys())}")
            return False
        
        studies = result.get('studies', [])
        if not studies:
            print("❌ FAIL: No studies in response")
            return False
        
        print(f"✅ PASS: Fetched {len(studies)} studies")
        print(f"   Sample study keys: {list(studies[0].keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_staging_insert():
    """Test 2: Can we insert data into the staging table?"""
    print("\n" + "="*80)
    print("TEST 2: Staging - Can we insert data into staging table?")
    print("="*80)
    
    try:
        from database.config import get_db_session
        from database.models.staging import StagingRawData
        from uuid import uuid4
        
        # Fetch real data
        from ingestion.clinicaltrials_gov import fetch_studies_sample
        result = fetch_studies_sample(query_term="cancer", page_size=2, save_dir=None)
        
        if not result or 'studies' not in result:
            print("❌ FAIL: Could not fetch data for testing")
            return False
        
        studies = result['studies']
        
        with get_db_session() as session:
            # Try to insert first study
            study = studies[0]
            
            # Extract NCT ID
            nct_id = None
            if 'protocolSection' in study:
                nct_id = study['protocolSection'].get('identificationModule', {}).get('nctId')
            else:
                nct_id = study.get('nct_id', study.get('NCTId'))
            
            if not nct_id:
                print(f"❌ FAIL: Could not extract NCT ID. Study keys: {list(study.keys())}")
                return False
            
            # Check if already exists
            existing = session.query(StagingRawData).filter_by(
                source_system='clinicaltrials_gov',
                source_record_id=nct_id
            ).first()
            
            if existing:
                print(f"⚠️  Record {nct_id} already exists in staging")
                staging_record = existing
            else:
                staging_record = StagingRawData(
                    staging_id=uuid4(),
                    source_system='clinicaltrials_gov',
                    source_record_id=nct_id,
                    raw_data=study,
                    processed=False
                )
                session.add(staging_record)
                session.commit()
            
            print(f"✅ PASS: Inserted/found staging record for {nct_id}")
            
            # Return the NCT ID for next test
            return nct_id
            
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_processor():
    """Test 3: Can the processor extract entities from the data?"""
    print("\n" + "="*80)
    print("TEST 3: Processor - Can we extract entities?")
    print("="*80)
    
    try:
        from database.config import get_db_session
        from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
        from ingestion.clinicaltrials_gov import fetch_studies_sample
        
        # Fetch real data
        result = fetch_studies_sample(query_term="breast cancer", page_size=1, save_dir=None)
        if not result or 'studies' not in result:
            print("❌ FAIL: Could not fetch data")
            return False
        
        study = result['studies'][0]
        
        with get_db_session() as session:
            processor = ClinicalTrialsProcessor(session)
            
            # Test extraction
            entities = processor.extract_entities(study)
            
            print(f"   Extracted entities:")
            for entity_type, entity_list in entities.items():
                print(f"   - {entity_type}: {len(entity_list)}")
                if entity_list:
                    print(f"     Example: {entity_list[0].name}")
            
            # Validate
            is_valid = processor.validate_extraction(entities)
            
            if not is_valid:
                print("❌ FAIL: Validation failed")
                print(f"   Errors: {processor.get_errors()}")
                return False
            
            print("✅ PASS: Entity extraction and validation successful")
            return True
            
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_entity_resolution():
    """Test 4: Can we resolve entities (match or create)?"""
    print("\n" + "="*80)
    print("TEST 4: Entity Resolution - Can we resolve entities?")
    print("="*80)
    
    try:
        from database.config import get_db_session
        from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
        from src.entity_resolution.entity_resolver import EntityResolver
        from ingestion.clinicaltrials_gov import fetch_studies_sample
        
        # Fetch real data
        result = fetch_studies_sample(query_term="pfizer", page_size=1, save_dir=None)
        if not result or 'studies' not in result:
            print("❌ FAIL: Could not fetch data")
            return False
        
        study = result['studies'][0]
        
        with get_db_session() as session:
            processor = ClinicalTrialsProcessor(session)
            resolver = EntityResolver(session)
            
            # Extract entities
            entities = processor.extract_entities(study)
            
            # Try to resolve first company
            if entities['companies']:
                company = entities['companies'][0]
                print(f"   Resolving company: {company.name}")
                
                resolution = resolver.resolve(company)
                
                print(f"   Resolution status: {resolution.status}")
                print(f"   Confidence: {resolution.confidence_score}")
                if resolution.candidates:
                    print(f"   Candidates: {len(resolution.candidates)}")
                
                print("✅ PASS: Entity resolution works")
                return True
            else:
                print("⚠️  No companies found in this trial")
                return True
                
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_pipeline():
    """Test 5: Does the full pipeline work end-to-end?"""
    print("\n" + "="*80)
    print("TEST 5: Full Pipeline - End-to-end processing")
    print("="*80)
    
    try:
        from database.config import get_db_session
        from database.models.staging import StagingRawData
        from database.models.entities import Company, Drug, Disease
        from database.models.clinical import ClinicalTrial
        from src.processing.pipeline import ProcessingPipeline
        from ingestion.clinicaltrials_gov import fetch_studies_sample
        from uuid import uuid4
        
        # Fetch and stage data
        result = fetch_studies_sample(query_term="breast cancer drug", page_size=1, save_dir=None)
        if not result or 'studies' not in result:
            print("❌ FAIL: Could not fetch data")
            return False
        
        study = result['studies'][0]
        
        # Extract NCT ID
        nct_id = None
        if 'protocolSection' in study:
            nct_id = study['protocolSection'].get('identificationModule', {}).get('nctId')
        else:
            nct_id = study.get('nct_id', study.get('NCTId'))
        
        print(f"   Processing trial: {nct_id}")
        
        with get_db_session() as session:
            # Delete if exists (for clean test)
            session.query(StagingRawData).filter_by(
                source_system='clinicaltrials_gov',
                source_record_id=nct_id
            ).delete()
            session.commit()
            
            # Insert fresh
            staging_record = StagingRawData(
                staging_id=uuid4(),
                source_system='clinicaltrials_gov',
                source_record_id=nct_id,
                raw_data=study,
                processed=False
            )
            session.add(staging_record)
            session.commit()
        
        # Run pipeline
        pipeline = ProcessingPipeline(batch_size=10)
        stats = pipeline.process_source('clinicaltrials_gov', limit=1)
        
        print(f"\n   Pipeline Stats:")
        print(f"   - Records processed: {stats['records_processed']}")
        print(f"   - Records failed: {stats['records_failed']}")
        print(f"   - Entities created: {stats['entities_created']}")
        print(f"   - Entities matched: {stats['entities_matched']}")
        print(f"   - Relationships created: {stats['relationships_created']}")
        print(f"   - Needs review: {stats['needs_review']}")
        
        if stats['records_failed'] > 0:
            print("❌ FAIL: Pipeline processing failed")
            return False
        
        # Verify data was actually created
        with get_db_session() as session:
            trial = session.query(ClinicalTrial).filter_by(nct_id=nct_id).first()
            
            if not trial:
                print(f"❌ FAIL: Trial {nct_id} not created in database")
                return False
            
            print(f"   ✓ Trial created: {trial.trial_title[:50]}...")
            
            # Check for related entities
            companies = session.query(Company).count()
            drugs = session.query(Drug).count()
            diseases = session.query(Disease).count()
            
            print(f"   Database counts:")
            print(f"   - Companies: {companies}")
            print(f"   - Drugs: {drugs}")
            print(f"   - Diseases: {diseases}")
        
        print("✅ PASS: Full pipeline works end-to-end!")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_missing_wiring():
    """Test 6: Check for missing wiring between ingestion and pipeline"""
    print("\n" + "="*80)
    print("TEST 6: Wiring Check - Are ingestion scripts connected to staging?")
    print("="*80)
    
    print("   Checking ingestion scripts...")
    
    from pathlib import Path
    import ast
    
    ingestion_dir = Path("ingestion")
    issues = []
    
    # Check if any ingestion scripts write to staging
    for script in ingestion_dir.glob("*.py"):
        if script.name.startswith("_") or script.name == "test_helper.py":
            continue
        
        try:
            content = script.read_text()
            tree = ast.parse(content)
            
            # Check for database imports
            has_db_import = "from database" in content or "import database" in content
            has_staging_import = "StagingRawData" in content
            
            if not has_db_import and not has_staging_import:
                issues.append(f"   ⚠️  {script.name}: No database imports (writes to files only)")
        
        except Exception as e:
            issues.append(f"   ❌ {script.name}: Error analyzing - {e}")
    
    if issues:
        print("\n   ISSUES FOUND:")
        for issue in issues:
            print(issue)
        print("\n   ❌ FAIL: Ingestion scripts are not wired to database")
        print("   They only write JSON files, not to staging tables!")
        return False
    else:
        print("   ✅ PASS: Ingestion scripts appear to be wired correctly")
        return True


def main():
    """Run all tests"""
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*20 + "COMPREHENSIVE FUNCTIONALITY TEST" + " "*26 + "║")
    print("╚" + "="*78 + "╝")
    
    results = {
        "Ingestion": test_ingestion(),
        "Staging Insert": test_staging_insert(),
        "Processor": test_processor(),
        "Entity Resolution": test_entity_resolution(),
        "Full Pipeline": test_full_pipeline(),
        "Wiring Check": test_missing_wiring(),
    }
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! The system is functional.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. There are real issues to fix.")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

