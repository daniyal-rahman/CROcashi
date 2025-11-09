# Verification Commands - Entity Resolution System

Quick commands to verify the system is working after the critical fixes.

---

## 1. Database Verification

Check that database is set up correctly:

```bash
cd /Users/danirahman/Repos/CROcashi
source .venv/bin/activate

# Check database connection and structure
python3 -c "
from database.config import engine
from sqlalchemy import inspect, text

with engine.connect() as conn:
    # Test connection
    conn.execute(text('SELECT 1'))
    print('✓ Database connected')
    
    # Check extensions
    result = conn.execute(text(\"SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp', 'pg_trgm')\"))
    extensions = [row[0] for row in result]
    print(f'✓ Extensions: {extensions}')

# Check table count
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f'✓ Tables: {len(tables)}')

# Check key tables exist
key_tables = ['companies', 'drugs', 'clinical_trials', 'trial_sponsors', 
              'trial_drugs', 'trial_diseases', 'entity_aliases', 'source_processing_log']
missing = [t for t in key_tables if t not in tables]
if missing:
    print(f'✗ Missing tables: {missing}')
else:
    print(f'✓ All key tables exist')
"
```

---

## 2. Run Integration Test

Full end-to-end test:

```bash
cd /Users/danirahman/Repos/CROcashi
source .venv/bin/activate

python test_integration.py
```

**What to look for:**
- `Relationships created: 3` (or more) ← **KEY METRIC**
- `✅ INTEGRATION TEST PASSED`
- No critical errors

---

## 3. Check Relationships in Database

Verify relationships were actually created:

```bash
cd /Users/danirahman/Repos/CROcashi
source .venv/bin/activate

python3 -c "
from database.config import get_db_session
from database.models import (
    ClinicalTrial, Company, Drug, Disease,
    TrialSponsor, TrialDrug, TrialDisease
)

with get_db_session() as session:
    trials = session.query(ClinicalTrial).count()
    companies = session.query(Company).count()
    drugs = session.query(Drug).count()
    diseases = session.query(Disease).count()
    
    trial_sponsors = session.query(TrialSponsor).count()
    trial_drugs = session.query(TrialDrug).count()
    trial_diseases = session.query(TrialDisease).count()
    
    print(f'Entities:')
    print(f'  Trials: {trials}')
    print(f'  Companies: {companies}')
    print(f'  Drugs: {drugs}')
    print(f'  Diseases: {diseases}')
    print(f'')
    print(f'Relationships (KEY METRICS):')
    print(f'  Trial-Sponsor: {trial_sponsors}')
    print(f'  Trial-Drug: {trial_drugs}')
    print(f'  Trial-Disease: {trial_diseases}')
    print(f'  TOTAL: {trial_sponsors + trial_drugs + trial_diseases}')
    
    if trial_sponsors > 0 or trial_drugs > 0 or trial_diseases > 0:
        print(f'')
        print(f'✅ RELATIONSHIPS ARE BEING CREATED')
    else:
        print(f'')
        print(f'✗ NO RELATIONSHIPS FOUND')
"
```

---

## 4. Test Context Extraction

Verify context-aware matching works:

```bash
cd /Users/danirahman/Repos/CROcashi
source .venv/bin/activate

python3 -c "
from database.config import get_db_session
from database.models import Company, Drug, CompanyDrug
from src.entity_resolution.entity_resolver import EntityResolver
from uuid import uuid4

with get_db_session() as session:
    # Create test entities
    company = Company(
        company_id=uuid4(),
        name='TestCo',
        data_sources={'test': {}}
    )
    session.add(company)
    session.flush()
    
    drug = Drug(
        drug_id=uuid4(),
        primary_name='TestDrug',
        data_sources={'test': {}}
    )
    session.add(drug)
    session.flush()
    
    # Link them
    link = CompanyDrug(
        company_id=company.company_id,
        drug_id=drug.drug_id,
        relationship_type='originator',
        data_sources={'test': {}}
    )
    session.add(link)
    session.commit()
    
    # Test context extraction
    resolver = EntityResolver(session)
    
    drug_context = resolver._get_entity_context(Drug, drug.drug_id)
    company_context = resolver._get_entity_context(Company, company.company_id)
    
    print(f'Drug context: {drug_context}')
    print(f'Company context: {company_context}')
    
    # Verify
    if company.company_id in drug_context['company_ids']:
        print(f'✅ Drug context includes linked company')
    else:
        print(f'✗ Drug context missing company')
    
    if drug.drug_id in company_context['drug_ids']:
        print(f'✅ Company context includes linked drug')
    else:
        print(f'✗ Company context missing drug')
    
    # Cleanup
    session.delete(link)
    session.delete(drug)
    session.delete(company)
    session.commit()
"
```

---

## 5. Process a Single Record

Test the pipeline with a single clinical trial:

```bash
cd /Users/danirahman/Repos/CROcashi
source .venv/bin/activate

python3 -c "
from uuid import uuid4
from database.config import get_db_session
from database.models import StagingRawData
from src.processing.pipeline import ProcessingPipeline

# Create test data
test_data = {
    'nct_id': 'NCT00000001',
    'title': 'Verification Test Trial',
    'phase': 'Phase 1',
    'overall_status': 'Recruiting',
    'start_date': '2024-01-01',
    'sponsor': {
        'lead_sponsor': {
            'agency': 'Verification Pharma',
            'agency_class': 'industry'
        }
    },
    'interventions': [{
        'intervention_type': 'drug',
        'intervention_name': 'Verification Drug',
    }],
    'conditions': ['Verification Disease']
}

with get_db_session() as session:
    # Delete old test data
    session.query(StagingRawData).filter(
        StagingRawData.source_record_id == 'NCT00000001'
    ).delete()
    session.commit()
    
    # Create staging record
    staging = StagingRawData(
        staging_id=uuid4(),
        source_system='clinicaltrials_gov',
        source_record_id='NCT00000001',
        raw_data=test_data,
        processed=False
    )
    session.add(staging)
    session.commit()
    print('✓ Created staging record')

# Process it
pipeline = ProcessingPipeline(batch_size=10)
stats = pipeline.process_source('clinicaltrials_gov', limit=1)

print(f'')
print(f'Processing Results:')
print(f'  Records processed: {stats.get(\"records_processed\", 0)}')
print(f'  Entities created: {stats.get(\"entities_created\", 0)}')
print(f'  Relationships created: {stats.get(\"relationships_created\", 0)}')
print(f'')

if stats.get('relationships_created', 0) > 0:
    print(f'✅ SUCCESS: Relationships were created')
else:
    print(f'✗ FAILED: No relationships created')
"
```

---

## 6. Check Processing Logs

View audit logs:

```bash
cd /Users/danirahman/Repos/CROcashi
source .venv/bin/activate

python3 -c "
from database.config import get_db_session
from database.models import SourceProcessingLog

with get_db_session() as session:
    logs = session.query(SourceProcessingLog).order_by(
        SourceProcessingLog.created_at.desc()
    ).limit(5).all()
    
    print('Recent Processing Logs:')
    print('=' * 70)
    
    for log in logs:
        print(f'')
        print(f'Record: {log.source_identifier}')
        print(f'Source: {log.source_name}')
        print(f'Status: {log.processing_status}')
        print(f'Entities extracted: {log.entities_extracted}')
        print(f'Entities created: {log.entities_created}')
        print(f'Entities matched: {log.entities_matched}')
        print(f'Relationships created: {log.relationships_created}')
        if log.errors:
            print(f'Errors: {log.errors}')
        print('-' * 70)
"
```

---

## 7. Test Entity Stub Key Generation

Verify the fix for relationship wiring:

```bash
cd /Users/danirahman/Repos/CROcashi
source .venv/bin/activate

python3 -c "
from src.entity_resolution.types import EntityType, ExtractedEntity
from src.processing.pipeline import ProcessingPipeline

# Create test entities
entity1 = ExtractedEntity(
    entity_type=EntityType.DRUG,
    name='Test Drug',
    identifiers={'nct_id': 'NCT12345'},
    context={},
    source_name='test',
    source_identifier='test-001'
)

entity2 = ExtractedEntity(
    entity_type=EntityType.DRUG,
    name='Test Drug',  # Same name
    identifiers={'nct_id': 'NCT12345'},  # Same ID
    context={},
    source_name='test',
    source_identifier='test-002'
)

entity3 = ExtractedEntity(
    entity_type=EntityType.DRUG,
    name='Different Drug',
    identifiers={'nct_id': 'NCT67890'},
    context={},
    source_name='test',
    source_identifier='test-003'
)

# Generate keys
key1 = ProcessingPipeline._make_entity_stub_key(entity1)
key2 = ProcessingPipeline._make_entity_stub_key(entity2)
key3 = ProcessingPipeline._make_entity_stub_key(entity3)

print(f'Entity 1 key: {key1}')
print(f'Entity 2 key: {key2}')
print(f'Entity 3 key: {key3}')
print(f'')

if key1 == key2:
    print(f'✅ Same entities produce same key')
else:
    print(f'✗ FAILED: Same entities have different keys')

if key1 != key3:
    print(f'✅ Different entities produce different keys')
else:
    print(f'✗ FAILED: Different entities have same key')
"
```

---

## 8. Quick Health Check (All-in-One)

Run all critical checks:

```bash
cd /Users/danirahman/Repos/CROcashi
source .venv/bin/activate

python3 -c "
from database.config import engine, get_db_session
from database.models import *
from sqlalchemy import inspect, text

print('=' * 70)
print('ENTITY RESOLUTION SYSTEM - HEALTH CHECK')
print('=' * 70)

# 1. Database connection
try:
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    print('\n✅ Database: Connected')
except Exception as e:
    print(f'\n✗ Database: FAILED - {e}')
    exit(1)

# 2. Table count
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f'✅ Database: {len(tables)} tables')

# 3. Extensions
with engine.connect() as conn:
    result = conn.execute(text(\"SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp', 'pg_trgm')\"))
    extensions = [row[0] for row in result]
    if 'uuid-ossp' in extensions and 'pg_trgm' in extensions:
        print(f'✅ Extensions: uuid-ossp, pg_trgm')
    else:
        print(f'✗ Extensions: Missing {[e for e in [\"uuid-ossp\", \"pg_trgm\"] if e not in extensions]}')

# 4. Entity counts
with get_db_session() as session:
    trials = session.query(ClinicalTrial).count()
    companies = session.query(Company).count()
    drugs = session.query(Drug).count()
    
    print(f'\n📊 Entities:')
    print(f'  Trials: {trials}')
    print(f'  Companies: {companies}')
    print(f'  Drugs: {drugs}')

# 5. Relationship counts (THE KEY METRIC)
with get_db_session() as session:
    trial_sponsors = session.query(TrialSponsor).count()
    trial_drugs = session.query(TrialDrug).count()
    trial_diseases = session.query(TrialDisease).count()
    total_rels = trial_sponsors + trial_drugs + trial_diseases
    
    print(f'\n🔗 Relationships:')
    print(f'  Trial-Sponsor: {trial_sponsors}')
    print(f'  Trial-Drug: {trial_drugs}')
    print(f'  Trial-Disease: {trial_diseases}')
    print(f'  TOTAL: {total_rels}')
    
    if total_rels > 0:
        print(f'\n✅ CRITICAL FIX VERIFIED: Relationships are being created')
    else:
        print(f'\n⚠️  No relationships found (may need to run integration test first)')

# 6. Processing logs
with get_db_session() as session:
    logs = session.query(SourceProcessingLog).count()
    print(f'\n📝 Processing Logs: {logs} entries')

print(f'\n' + '=' * 70)
print('HEALTH CHECK COMPLETE')
print('=' * 70)
"
```

---

## Expected Output (Healthy System)

After running the integration test, the health check should show:

```
======================================================================
ENTITY RESOLUTION SYSTEM - HEALTH CHECK
======================================================================

✅ Database: Connected
✅ Database: 49 tables
✅ Extensions: uuid-ossp, pg_trgm

📊 Entities:
  Trials: 1
  Companies: 1
  Drugs: 1

🔗 Relationships:
  Trial-Sponsor: 1
  Trial-Drug: 1
  Trial-Disease: 1
  TOTAL: 3

✅ CRITICAL FIX VERIFIED: Relationships are being created

📝 Processing Logs: 1 entries

======================================================================
HEALTH CHECK COMPLETE
======================================================================
```

---

## Troubleshooting

### If relationships count is 0:

1. Run the integration test first:
   ```bash
   python test_integration.py
   ```

2. Check processing logs for errors:
   ```bash
   python3 -m src.tools.monitor_processing
   ```

3. Check if entities were created but relationships failed:
   ```bash
   # Run the health check - if entities > 0 but relationships = 0,
   # the relationship creation is still broken
   ```

### If integration test fails:

1. Check database connection (`.env` file)
2. Ensure migrations are up to date: `alembic upgrade head`
3. Check for constraint violations in logs
4. Verify `clinicaltrials_gov_sample.json` exists in `data/raw/clinicaltrials_gov/`

---

## Success Criteria

The system is working if:

✅ Database connected  
✅ 49 tables exist  
✅ Extensions installed  
✅ Entities created (trials, companies, drugs)  
✅ **Relationships created > 0** ← **KEY METRIC**  
✅ Processing logs exist  
✅ Integration test passes  

---

**Last Updated:** November 7, 2025  
**Status:** All commands verified working

