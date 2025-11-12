#!/usr/bin/env python3
"""
Large ingestion test with multiple sources and larger batches.
This tests the system at scale.
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
from ingestion.fda_guidance import search_guidance
from ingestion.fda_orphan import fetch_orphan_designations
from ingestion.nih_reporter import search_projects
from src.processing.pipeline import ProcessingPipeline
from database.config import get_db_session
from database.models.staging import StagingRawData
from database.models.entities import Company, Drug
from database.models.clinical import ClinicalTrial
from database.models.relationships import TrialSponsor, TrialDrug, TrialDisease

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def large_ingestion_test():
    """Run large ingestion test with multiple sources."""
    print("=" * 80)
    print("LARGE INGESTION TEST")
    print("=" * 80)
    print(f"Started at: {datetime.now()}")
    print()
    
    results = {}
    
    # Define ingestion tasks with larger batches
    ingestion_tasks = [
        {
            'name': 'clinicaltrials_gov',
            'func': fetch_studies_sample,
            'params': {'page_size': 200, 'load_to_staging': True},
            'expected': 200
        },
        {
            'name': 'fda_eua',
            'func': fetch_recent_euas,
            'params': {'limit': 50, 'load_to_staging': True},
            'expected': 50
        },
        {
            'name': 'fda_guidance',
            'func': search_guidance,
            'params': {'load_to_staging': True},
            'expected': 50
        },
        {
            'name': 'fda_orphan',
            'func': fetch_orphan_designations,
            'params': {'limit': 50, 'load_to_staging': True},
            'expected': 50
        },
        {
            'name': 'nih_reporter',
            'func': search_projects,
            'params': {'query': 'biotech', 'limit': 100, 'load_to_staging': True},
            'expected': 100
        },
    ]
    
    # Step 1: Ingest all sources
    print("[1] INGESTION PHASE")
    print("-" * 80)
    
    total_ingested = 0
    for task in ingestion_tasks:
        print(f"\nIngesting {task['name']}...")
        try:
            result = task['func'](**task['params'])
            results[f"{task['name']}_ingestion"] = result
            
            inserted = result.get('staging_stats', {}).get('inserted', 0)
            skipped = result.get('staging_stats', {}).get('skipped', 0)
            total_ingested += inserted
            
            print(f"  ✓ Inserted: {inserted}, Skipped: {skipped}")
            
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results[f"{task['name']}_ingestion"] = {'error': str(e)}
            import traceback
            traceback.print_exc()
    
    print(f"\nTotal ingested: {total_ingested} records")
    
    # Step 2: Check staging status
    print("\n[2] STAGING STATUS")
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
                ORDER BY count DESC
            """)
        ).fetchall()
        
        print(f"Total staging records: {total}")
        for source, count in by_source:
            print(f"  {source}: {count}")
    
    # Step 3: Process all sources
    print("\n[3] PROCESSING PHASE")
    print("-" * 80)
    
    pipeline = ProcessingPipeline(batch_size=100)  # Larger batch size
    total_processed = 0
    total_entities = 0
    total_relationships = 0
    
    sources_to_process = [task['name'] for task in ingestion_tasks]
    
    for source in sources_to_process:
        if source not in pipeline.PROCESSOR_MAP:
            print(f"\n{source}: No processor found, skipping")
            continue
        
        print(f"\nProcessing {source}...")
        try:
            result = pipeline.process_source(source, limit=None)
            results[f"{source}_processing"] = result
            
            if 'error' in result:
                print(f"  ✗ Error: {result['error']}")
            else:
                records = result.get('records_processed', 0)
                entities = result.get('entities_created', 0) + result.get('entities_matched', 0)
                relationships = result.get('relationships_created', 0)
                
                total_processed += records
                total_entities += entities
                total_relationships += relationships
                
                print(f"  ✓ Processed: {records} records")
                print(f"  ✓ Entities: {entities} created/matched")
                print(f"  ✓ Relationships: {relationships} created")
                
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results[f"{source}_processing"] = {'error': str(e)}
            import traceback
            traceback.print_exc()
    
    # Step 4: Final verification
    print("\n[4] FINAL VERIFICATION")
    print("-" * 80)
    with get_db_session() as session:
        # Entities
        companies = session.query(Company).filter(Company.deleted_at.is_(None)).count()
        drugs = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
        trials = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
        
        print(f"Entities:")
        print(f"  Companies: {companies}")
        print(f"  Drugs: {drugs}")
        print(f"  Trials: {trials}")
        print(f"  Total: {companies + drugs + trials}")
        
        # Relationships
        trial_sponsor = session.query(TrialSponsor).filter(TrialSponsor.deleted_at.is_(None)).count()
        trial_drug = session.query(TrialDrug).filter(TrialDrug.deleted_at.is_(None)).count()
        trial_disease = session.query(TrialDisease).filter(TrialDisease.deleted_at.is_(None)).count()
        
        print(f"\nRelationships:")
        print(f"  Trial-Sponsor: {trial_sponsor}")
        print(f"  Trial-Drug: {trial_drug}")
        print(f"  Trial-Disease: {trial_disease}")
        print(f"  Total: {trial_sponsor + trial_drug + trial_disease}")
        
        # Staging
        processed = session.query(StagingRawData).filter(
            StagingRawData.processed == True,
            StagingRawData.deleted_at.is_(None)
        ).count()
        total_staging = session.query(StagingRawData).filter(
            StagingRawData.deleted_at.is_(None)
        ).count()
        
        print(f"\nStaging:")
        print(f"  Processed: {processed}/{total_staging} ({processed/total_staging*100:.1f}%)" if total_staging > 0 else "  Processed: 0/0")
        
        results['verification'] = {
            'companies': companies,
            'drugs': drugs,
            'trials': trials,
            'trial_sponsor': trial_sponsor,
            'trial_drug': trial_drug,
            'trial_disease': trial_disease,
            'processed': processed,
            'total_staging': total_staging
        }
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Completed at: {datetime.now()}")
    print(f"\nIngestion:")
    print(f"  Total ingested: {total_ingested} records")
    print(f"\nProcessing:")
    print(f"  Records processed: {total_processed}")
    print(f"  Entities created/matched: {total_entities}")
    print(f"  Relationships created: {total_relationships}")
    print(f"\nFinal State:")
    print(f"  Total entities: {results['verification']['companies'] + results['verification']['drugs'] + results['verification']['trials']}")
    print(f"  Total relationships: {results['verification']['trial_sponsor'] + results['verification']['trial_drug'] + results['verification']['trial_disease']}")
    print(f"  Processing rate: {results['verification']['processed']}/{results['verification']['total_staging']} ({results['verification']['processed']/results['verification']['total_staging']*100:.1f}%)" if results['verification']['total_staging'] > 0 else "  Processing rate: 0/0")
    
    # Check for errors
    errors = [k for k, v in results.items() if isinstance(v, dict) and 'error' in v]
    if errors:
        print(f"\n⚠️ Errors in: {', '.join(errors)}")
        return False
    else:
        print("\n✅ All tests passed!")
        return True


if __name__ == '__main__':
    success = large_ingestion_test()
    sys.exit(0 if success else 1)

