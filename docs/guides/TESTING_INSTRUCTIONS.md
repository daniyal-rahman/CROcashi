# Testing the Entity Resolution System

## Prerequisites

### 1. Set up Python environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Set up PostgreSQL database

```bash
# Create database
createdb biotech_kg

# Or if you need credentials:
createdb -U postgres -W biotech_kg
```

### 3. Configure environment variables

Create a `.env` file:

```bash
cat > .env <<EOF
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/biotech_kg
# Or use individual vars:
# DB_USER=postgres
# DB_PASS=postgres
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=biotech_kg
EOF
```

## Running the Integration Test

### Option 1: Full Integration Test (Recommended)

This test loads real data and verifies the entire pipeline:

```bash
# Activate virtual environment
source venv/bin/activate

# Run the test
python3 test_integration.py
```

**What it does**:
1. Initializes database with extensions (uuid-ossp, pg_trgm)
2. Loads 5 ClinicalTrials.gov records into staging
3. Runs processing pipeline
4. Verifies entities were created (trials, companies, drugs, diseases)
5. Verifies relationships were created
6. Checks audit logs

**Expected output**:
```
================================================================================
ENTITY RESOLUTION SYSTEM - INTEGRATION TEST
================================================================================

[1/7] Initializing database...
✓ Database initialized with extensions

[2/7] Loading sample data into staging...
✓ Loaded 5 ClinicalTrials.gov records into staging

[3/7] Verifying staged records...
✓ ClinicalTrials.gov: 5 records staged

[4/7] Processing ClinicalTrials.gov data...
✓ Processing completed:
  - Records processed: 5
  - Entities created: 15-25
  - Relationships created: 10-20

[5/7] Verifying entities in database...
✓ Clinical Trials: 5 created
✓ Companies: 5-10 created
✓ Drugs: 5-15 created
✓ Diseases: 5-10 created

[6/7] Verifying relationships...
✓ Trial Sponsors: 5-10 created
✓ Trial-Drug relationships: 5-15 created
✓ Trial-Disease relationships: 5-10 created

[7/7] Checking audit logs...
✓ Processing logs: 5 entries
✓ Match candidates: 0-5 needing review
✓ Entity aliases: 10-25 created

================================================================================
TEST SUMMARY
================================================================================

    Entities Created:     25-50
    Relationships:        20-40
    Successful Processes: 5
    Failed Processes:     0
    Review Queue:         0-5

✅ INTEGRATION TEST PASSED

The system is working! Entity resolution, relationship creation,
and audit logging are all functioning correctly.
```

### Option 2: Manual Step-by-Step Testing

If you want to test each component individually:

#### Step 1: Test Database Connection

```python
from database.config import get_db_session, init_db

# Initialize database
init_db()

# Test connection
with get_db_session() as session:
    result = session.execute("SELECT version()")
    print(result.scalar())
```

#### Step 2: Load Sample Data

```python
import json
from pathlib import Path
from uuid import uuid4
from database.config import get_db_session
from database.models import StagingRawData

with get_db_session() as session:
    # Load ClinicalTrials.gov sample
    with open('data/raw/clinicaltrials_gov/clinicaltrials_gov_sample.json') as f:
        data = json.load(f)
    
    # Load first study
    study = data['studies'][0]
    nct_id = study['protocolSection']['identificationModule']['nctId']
    
    staging = StagingRawData(
        staging_id=uuid4(),
        source_system='clinicaltrials_gov',
        source_record_id=nct_id,
        raw_data=study,
        processed=False
    )
    session.add(staging)
    session.commit()
    
    print(f"✓ Loaded trial {nct_id}")
```

#### Step 3: Test Entity Extraction

```python
from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
from database.config import get_db_session

with get_db_session() as session:
    processor = ClinicalTrialsProcessor(session)
    
    # Get staged record
    staging = session.query(StagingRawData).first()
    
    # Extract entities
    entities = processor.extract_entities(staging.raw_data)
    
    print(f"Extracted entities:")
    for entity_type, entity_list in entities.items():
        print(f"  {entity_type}: {len(entity_list)}")
        for entity in entity_list[:3]:  # Show first 3
            print(f"    - {entity.name}")
```

#### Step 4: Test Entity Resolution

```python
from src.entity_resolution.entity_resolver import EntityResolver
from database.config import get_db_session

with get_db_session() as session:
    resolver = EntityResolver(session)
    
    # Test resolving a company name
    from src.entity_resolution.types import EntityType, ExtractedEntity
    
    test_entity = ExtractedEntity(
        entity_type=EntityType.COMPANY,
        name="Pfizer Inc",
        identifiers={},
        context={},
        source_name='test',
        source_identifier='test001'
    )
    
    result = resolver.resolve(test_entity)
    
    print(f"Resolution result:")
    print(f"  Status: {result.status}")
    print(f"  Confidence: {result.confidence_score}")
    print(f"  Method: {result.match_method}")
    print(f"  Reasoning: {result.reasoning}")
```

#### Step 5: Test Full Pipeline

```python
from src.processing.pipeline import ProcessingPipeline

pipeline = ProcessingPipeline(batch_size=10)
stats = pipeline.process_source('clinicaltrials_gov', limit=1)

print(f"Processing stats:")
for key, value in stats.items():
    print(f"  {key}: {value}")
```

#### Step 6: Inspect Database

```python
from database.config import get_db_session
from database.models import *

with get_db_session() as session:
    # Count entities
    print(f"Trials: {session.query(ClinicalTrial).count()}")
    print(f"Companies: {session.query(Company).count()}")
    print(f"Drugs: {session.query(Drug).count()}")
    print(f"Diseases: {session.query(Disease).count()}")
    
    # Show first trial
    trial = session.query(ClinicalTrial).first()
    if trial:
        print(f"\nFirst trial: {trial.nct_id}")
        print(f"  Title: {trial.trial_title[:100]}...")
        print(f"  Phase: {trial.phase}")
        print(f"  Status: {trial.status}")
    
    # Show relationships
    print(f"\nRelationships:")
    print(f"  Trial Sponsors: {session.query(TrialSponsor).count()}")
    print(f"  Trial Drugs: {session.query(TrialDrug).count()}")
    print(f"  Trial Diseases: {session.query(TrialDisease).count()}")
```

## Using the CLI Tools

### Review Ambiguous Matches

```bash
# Show review queue stats
python3 -m src.tools.review_matches --stats

# Review drug matches
python3 -m src.tools.review_matches --entity-type drug --limit 10

# Review all pending matches
python3 -m src.tools.review_matches
```

### Monitor Processing

```bash
# Show dashboard for last 7 days
python3 -m src.tools.monitor_processing

# Filter by source
python3 -m src.tools.monitor_processing --source clinicaltrials_gov

# Show last 30 days
python3 -m src.tools.monitor_processing --days 30
```

## Troubleshooting

### Database Connection Error

```
psycopg2.OperationalError: could not connect to server
```

**Solution**: Check PostgreSQL is running:
```bash
# macOS
brew services start postgresql

# Or manually
pg_ctl -D /usr/local/var/postgres start

# Verify connection
psql -U postgres -d biotech_kg -c "SELECT 1"
```

### pg_trgm Extension Missing

```
ProgrammingError: extension "pg_trgm" does not exist
```

**Solution**: Install extension as superuser:
```sql
psql -U postgres -d biotech_kg -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

### Import Errors

```
ModuleNotFoundError: No module named 'src'
```

**Solution**: Make sure you're running from the project root:
```bash
cd /Users/danirahman/Repos/CROcashi
python3 test_integration.py
```

### Alembic Migration Errors

```
alembic.util.exc.CommandError: Target database is not up to date
```

**Solution**: Run migrations:
```bash
# Check current version
alembic current

# Upgrade to latest
alembic upgrade head

# If issues, show migration history
alembic history --verbose
```

## Expected Test Results

### Successful Run

When everything is working, you should see:
- ✅ All 7 test steps complete
- ✅ Entities created in database
- ✅ Relationships established
- ✅ Audit logs populated
- ✅ No failed processing logs

### Partial Success

If some tests fail but system is mostly working:
- ⚠️ Some entities may need manual review
- ⚠️ Some relationships might be missing (if entities didn't resolve)
- ⚠️ Review queue may have items (this is expected for ambiguous matches)

### What to Check

1. **Entity Counts**: Should be reasonable (5-50 entities from 5 trials)
2. **Relationship Counts**: Should be 50-80% of entity count
3. **Processing Logs**: Should all be 'success' status
4. **Review Queue**: Should be <20% of entities

## Next Steps After Testing

1. **If tests pass**: System is ready for larger data loads
2. **If issues found**: Check logs in `source_processing_log` table
3. **Tune matching**: Adjust thresholds in `src/entity_resolution/confidence_scorer.py`
4. **Add aliases**: Manually add common aliases for better matching

## Performance Testing

To test performance with larger datasets:

```python
from src.processing.pipeline import ProcessingPipeline
import time

pipeline = ProcessingPipeline(batch_size=100)

start = time.time()
stats = pipeline.process_source('clinicaltrials_gov', limit=1000)
duration = time.time() - start

records_per_minute = (stats['records_processed'] / duration) * 60
print(f"Processing speed: {records_per_minute:.0f} records/minute")
print(f"Target: 500+ records/minute")
```

## Questions?

See:
- `ENTITY_RESOLUTION_README.md` - Quick start guide
- `ENTITY_RESOLUTION_IMPLEMENTATION_REPORT.md` - Full documentation
- `database/DATABASE_SCHEMA.md` - Database schema details

