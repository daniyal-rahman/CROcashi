#!/usr/bin/env python3
"""
Test full pipeline with 2 overlapping ingestions.
This tests the entire system end-to-end.
"""
import sys
from pathlib import Path
import logging
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from ingestion.clinicaltrials_gov import fetch_studies_sample
from ingestion.fda_eua import fetch_recent_euas
from src.processing.pipeline import ProcessingPipeline
from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.entities import Company, Drug
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialSponsor, TrialDrug

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_full_pipeline():
    """Test full pipeline with 2 overlapping ingestions."""
    print("=" * 80)
    print("FULL PIPELINE TEST")
    print("=" * 80)
    print(f"Started at: {datetime.now()}")
    print()
    
    results = {
        'ingestion_1': {},
        'ingestion_2': {},
        'processing_1': {},
        'processing_2': {},
        'verification': {}
    }
    
    # Test 1: Ingest clinicaltrials_gov (small batch)
    print("[1] INGESTION 1: clinicaltrials_gov")
    print("-" * 80)
    try:
        result = fetch_studies_sample(
            load_to_staging=True
        )
        results['ingestion_1'] = result
        inserted = result.get('staging_stats', {}).get('inserted', 0)
        print(f"✓ Ingested {inserted} records")
    except Exception as e:
        print(f"✗ Ingestion 1 failed: {e}")
        results['ingestion_1'] = {'error': str(e)}
        import traceback
        traceback.print_exc()
    
    # Test 2: Ingest fda_eua (small batch, overlapping with clinicaltrials)
    print("\n[2] INGESTION 2: fda_eua (overlapping)")
    print("-" * 80)
    try:
        result = fetch_recent_euas(
            limit=5,  # Small batch
            load_to_staging=True
        )
        results['ingestion_2'] = result
        inserted = result.get('staging_stats', {}).get('inserted', 0)
        print(f"✓ Ingested {inserted} records")
    except Exception as e:
        print(f"✗ Ingestion 2 failed: {e}")
        results['ingestion_2'] = {'error': str(e)}
        import traceback
        traceback.print_exc()
    
    # Check staging status
    print("\n[3] STAGING STATUS")
    print("-" * 80)
    with get_db_session() as session:
        total = session.query(StagingRawData).filter(
            StagingRawData.deleted_at.is_(None)
        ).count()
        
        by_source = session.execute(
            text("""
                SELECT source_system, COUNT(*) as count
                FROM staging_raw_data
                WHERE deleted_at IS NULL
                GROUP BY source_system
            """)
        ).fetchall()
        
        print(f"Total staging records: {total}")
        for source, count in by_source:
            print(f"  {source}: {count}")
    
    # Test 3: Process clinicaltrials_gov
    print("\n[4] PROCESSING 1: clinicaltrials_gov")
    print("-" * 80)
    try:
        pipeline = ProcessingPipeline(batch_size=50)
        result = pipeline.process_source('clinicaltrials_gov', limit=None)
        results['processing_1'] = result
        
        if 'error' in result:
            print(f"✗ Processing 1 failed: {result['error']}")
        else:
            records = result.get('records_processed', 0)
            entities = result.get('entities_created', 0) + result.get('entities_matched', 0)
            relationships = result.get('relationships_created', 0)
            print(f"✓ Processed {records} records")
            print(f"  Created/matched {entities} entities")
            print(f"  Created {relationships} relationships")
    except Exception as e:
        print(f"✗ Processing 1 failed: {e}")
        results['processing_1'] = {'error': str(e)}
        import traceback
        traceback.print_exc()
    
    # Test 4: Process fda_eua (overlapping processing)
    print("\n[5] PROCESSING 2: fda_eua (overlapping)")
    print("-" * 80)
    try:
        pipeline = ProcessingPipeline(batch_size=50)
        result = pipeline.process_source('fda_eua', limit=None)
        results['processing_2'] = result
        
        if 'error' in result:
            print(f"✗ Processing 2 failed: {result['error']}")
        else:
            records = result.get('records_processed', 0)
            entities = result.get('entities_created', 0) + result.get('entities_matched', 0)
            relationships = result.get('relationships_created', 0)
            print(f"✓ Processed {records} records")
            print(f"  Created/matched {entities} entities")
            print(f"  Created {relationships} relationships")
    except Exception as e:
        print(f"✗ Processing 2 failed: {e}")
        results['processing_2'] = {'error': str(e)}
        import traceback
        traceback.print_exc()
    
    # Test 5: Verify results
    print("\n[6] VERIFICATION")
    print("-" * 80)
    with get_db_session() as session:
        
        # Check entities
        companies = session.query(Company).filter(Company.deleted_at.is_(None)).count()
        drugs = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
        trials = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
        
        print(f"Entities created:")
        print(f"  Companies: {companies}")
        print(f"  Drugs: {drugs}")
        print(f"  Trials: {trials}")
        print(f"  Total: {companies + drugs + trials}")
        
        # Check relationships
        trial_sponsor = session.query(TrialSponsor).filter(TrialSponsor.deleted_at.is_(None)).count()
        trial_drug = session.query(TrialDrug).filter(TrialDrug.deleted_at.is_(None)).count()
        
        print(f"\nRelationships created:")
        print(f"  Trial-Sponsor: {trial_sponsor}")
        print(f"  Trial-Drug: {trial_drug}")
        print(f"  Total: {trial_sponsor + trial_drug}")
        
        # Check staging
        processed = session.query(StagingRawData).filter(
            StagingRawData.processed == True,
            StagingRawData.deleted_at.is_(None)
        ).count()
        total = session.query(StagingRawData).filter(
            StagingRawData.deleted_at.is_(None)
        ).count()
        
        print(f"\nStaging:")
        print(f"  Processed: {processed}/{total} ({processed/total*100:.1f}%)" if total > 0 else "  Processed: 0/0")
        
        results['verification'] = {
            'companies': companies,
            'drugs': drugs,
            'trials': trials,
            'trial_sponsor': trial_sponsor,
            'trial_drug': trial_drug,
            'processed': processed,
            'total': total
        }
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Completed at: {datetime.now()}")
    
    # Check for errors
    errors = []
    if 'error' in results['ingestion_1']:
        errors.append("Ingestion 1 failed")
    if 'error' in results['ingestion_2']:
        errors.append("Ingestion 2 failed")
    if 'error' in results['processing_1']:
        errors.append("Processing 1 failed")
    if 'error' in results['processing_2']:
        errors.append("Processing 2 failed")
    
    if errors:
        print(f"\n❌ Errors: {', '.join(errors)}")
        return False
    else:
        print("\n✅ All tests passed!")
        print(f"  Entities: {results['verification']['companies'] + results['verification']['drugs'] + results['verification']['trials']}")
        print(f"  Relationships: {results['verification']['trial_sponsor'] + results['verification']['trial_drug']}")
        print(f"  Processing: {results['verification']['processed']}/{results['verification']['total']} records")
        return True


if __name__ == '__main__':
    success = test_full_pipeline()
    sys.exit(0 if success else 1)

