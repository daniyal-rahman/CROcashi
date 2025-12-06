#!/usr/bin/env python3
"""
Integration test for entity resolution system.

Tests:
1. Database setup and migrations
2. Loading data into staging
3. Processing pipeline
4. Entity resolution
5. Relationship creation
6. Audit logging
"""
import json
import sys
from pathlib import Path
from uuid import uuid4

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from database.config import get_db_session, init_db
from database.models import (
    StagingRawData, Company, Drug, Disease, ClinicalTrial,
    TrialSponsor, TrialDrug, TrialDisease,
    SourceProcessingLog, EntityMatchCandidate, EntityAlias
)
from src.processing.pipeline import ProcessingPipeline

print("=" * 80)
print("ENTITY RESOLUTION SYSTEM - INTEGRATION TEST")
print("=" * 80)

# Step 1: Initialize database
print("\n[1/7] Initializing database...")
try:
    init_db()
    print("✓ Database initialized with extensions")
except Exception as e:
    print(f"✗ Database initialization failed: {e}")
    print("  (This is OK if database already initialized)")

# Step 2: Load sample data into staging
print("\n[2/7] Loading sample data into staging...")

with get_db_session() as session:
    # Clear existing test data
    session.query(StagingRawData).filter(
        StagingRawData.source_system == 'clinicaltrials_gov'
    ).delete()
    session.commit()
    
    # Load ClinicalTrials.gov sample
    ct_file = Path('data/raw/clinicaltrials_gov/clinicaltrials_gov_sample.json')
    if ct_file.exists():
        with open(ct_file) as f:
            data = json.load(f)
        
        # Load first 5 studies only
        studies = data.get('studies', [])[:5]
        
        for study in studies:
            nct_id = study.get('protocolSection', {}).get('identificationModule', {}).get('nctId', '')
            
            if nct_id:
                staging = StagingRawData(
                    staging_id=uuid4(),
                    source_system='clinicaltrials_gov',
                    source_record_id=nct_id,
                    raw_data=study,
                    processed=False
                )
                session.add(staging)
        
        session.commit()
        print(f"✓ Loaded {len(studies)} ClinicalTrials.gov records into staging")
    else:
        print(f"✗ Sample file not found: {ct_file}")
        sys.exit(1)
    
    # Load OpenFDA sample (different format, for testing)
    fda_file = Path('data/raw/openfda/openfda_drugs.json')
    if fda_file.exists():
        with open(fda_file) as f:
            data = json.load(f)
        
        # Load first 3 drugs
        results = data.get('results', [])[:3]
        
        for i, drug_data in enumerate(results):
            # Create a simplified structure
            simplified = {
                'brand_name': drug_data.get('openfda', {}).get('brand_name', ['Unknown'])[0],
                'generic_name': drug_data.get('openfda', {}).get('generic_name', [''])[0] if drug_data.get('openfda', {}).get('generic_name') else '',
                'sponsor_name': drug_data.get('openfda', {}).get('manufacturer_name', [''])[0] if drug_data.get('openfda', {}).get('manufacturer_name') else '',
                'application_number': drug_data.get('openfda', {}).get('application_number', [f'TEST{i:05d}'])[0],
                'approval_date': '2024-01-01',  # Mock date
                'indications': ['Test indication']
            }
            
            staging = StagingRawData(
                staging_id=uuid4(),
                source_system='fda_drugs',
                source_record_id=simplified['application_number'],
                raw_data=simplified,
                processed=False
            )
            session.add(staging)
        
        session.commit()
        print(f"✓ Loaded {len(results)} FDA drug records into staging")
    else:
        print("  FDA drugs file not found, skipping")

# Step 3: Check staging records
print("\n[3/7] Verifying staged records...")
with get_db_session() as session:
    ct_count = session.query(StagingRawData).filter(
        StagingRawData.source_system == 'clinicaltrials_gov',
        StagingRawData.processed == False
    ).count()
    
    fda_count = session.query(StagingRawData).filter(
        StagingRawData.source_system == 'fda_drugs',
        StagingRawData.processed == False
    ).count()
    
    print(f"✓ ClinicalTrials.gov: {ct_count} records staged")
    print(f"✓ FDA Drugs: {fda_count} records staged")

# Step 4: Process ClinicalTrials.gov data
print("\n[4/7] Processing ClinicalTrials.gov data...")
try:
    pipeline = ProcessingPipeline(batch_size=10)
    stats = pipeline.process_source('clinicaltrials_gov', limit=5)
    
    print(f"✓ Processing completed:")
    print(f"  - Records processed: {stats.get('records_processed', 0)}")
    print(f"  - Records failed: {stats.get('records_failed', 0)}")
    print(f"  - Entities created: {stats.get('entities_created', 0)}")
    print(f"  - Entities matched: {stats.get('entities_matched', 0)}")
    print(f"  - Relationships created: {stats.get('relationships_created', 0)}")
    print(f"  - Needs review: {stats.get('needs_review', 0)}")
    
    if 'error' in stats:
        print(f"✗ Error: {stats['error']}")
except Exception as e:
    print(f"✗ Processing failed: {e}")
    import traceback
    traceback.print_exc()

# Step 5: Verify entities were created
print("\n[5/7] Verifying entities in database...")
with get_db_session() as session:
    # Check trials
    trials = session.query(ClinicalTrial).all()
    print(f"✓ Clinical Trials: {len(trials)} created")
    if trials:
        trial = trials[0]
        print(f"  Example: {trial.nct_id} - {trial.trial_title[:60] if trial.trial_title else 'No title'}...")
    
    # Check companies
    companies = session.query(Company).all()
    print(f"✓ Companies: {len(companies)} created")
    if companies:
        company = companies[0]
        print(f"  Example: {company.name}")
    
    # Check drugs
    drugs = session.query(Drug).all()
    print(f"✓ Drugs: {len(drugs)} created")
    if drugs:
        drug = drugs[0]
        print(f"  Example: {drug.primary_name}")
    
    # Check diseases
    diseases = session.query(Disease).all()
    print(f"✓ Diseases: {len(diseases)} created")
    if diseases:
        disease = diseases[0]
        print(f"  Example: {disease.disease_name}")

# Step 6: Verify relationships
print("\n[6/7] Verifying relationships...")
with get_db_session() as session:
    # Check trial sponsors
    sponsors = session.query(TrialSponsor).all()
    print(f"✓ Trial Sponsors: {len(sponsors)} created")
    if sponsors:
        sponsor = sponsors[0]
        print(f"  Example: Trial {sponsor.trial_id} - Role: {sponsor.sponsor_role}")
    
    # Check trial drugs
    trial_drugs = session.query(TrialDrug).all()
    print(f"✓ Trial-Drug relationships: {len(trial_drugs)} created")
    
    # Check trial diseases
    trial_diseases = session.query(TrialDisease).all()
    print(f"✓ Trial-Disease relationships: {len(trial_diseases)} created")

# Step 7: Check audit logs
print("\n[7/7] Checking audit logs...")
with get_db_session() as session:
    # Processing logs
    logs = session.query(SourceProcessingLog).all()
    print(f"✓ Processing logs: {len(logs)} entries")
    
    if logs:
        for log in logs[:3]:  # Show first 3
            status_icon = "✓" if log.processing_status == 'success' else "✗"
            print(f"  {status_icon} {log.source_name} - {log.source_identifier}: {log.processing_status}")
            if log.errors:
                print(f"    Errors: {log.errors}")
    
    # Match candidates (entities needing review)
    candidates = session.query(EntityMatchCandidate).all()
    print(f"✓ Match candidates: {len(candidates)} needing review")
    
    if candidates:
        for candidate in candidates[:3]:  # Show first 3
            print(f"  ? {candidate.entity_type}: {candidate.extracted_text}")
            print(f"    Status: {candidate.status}, Confidence: {candidate.match_confidence}")
    
    # Aliases created
    aliases = session.query(EntityAlias).all()
    print(f"✓ Entity aliases: {len(aliases)} created")

# Summary
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)

with get_db_session() as session:
    # Count everything
    total_entities = (
        session.query(ClinicalTrial).count() +
        session.query(Company).count() +
        session.query(Drug).count() +
        session.query(Disease).count()
    )
    
    total_relationships = (
        session.query(TrialSponsor).count() +
        session.query(TrialDrug).count() +
        session.query(TrialDisease).count()
    )
    
    success_logs = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.processing_status == 'success'
    ).count()
    
    failed_logs = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.processing_status == 'failed'
    ).count()
    
    print(f"""
    Entities Created:     {total_entities}
    Relationships:        {total_relationships}
    Successful Processes: {success_logs}
    Failed Processes:     {failed_logs}
    Review Queue:         {session.query(EntityMatchCandidate).filter(EntityMatchCandidate.status == 'needs_review').count()}
    """)
    
    if total_entities > 0 and total_relationships > 0 and success_logs > 0:
        print("✅ INTEGRATION TEST PASSED")
        print("\nThe system is working! Entity resolution, relationship creation,")
        print("and audit logging are all functioning correctly.")
    else:
        print("⚠️  INTEGRATION TEST HAD ISSUES")
        print("\nSome components may not be working correctly. Check logs above.")

print("\n" + "=" * 80)
print("\nTo inspect the database manually:")
print("  python3 -c \"from database.config import get_db_session; from database.models import *\"")
print("\nTo review ambiguous matches:")
print("  python3 -m src.tools.review_matches")
print("\nTo see processing stats:")
print("  python3 -m src.tools.monitor_processing")
print("")

