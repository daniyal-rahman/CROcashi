# Single Trial Test Guide

This guide implements the **single-trial test topology** for isolating just the Cassava trial while keeping all real downstream processing intact. This allows you to test the complete pipeline with real database writes and worker processing without the overhead of full CT.gov/SEC ingestion.

## Overview

The single trial test:

1. **Injects** a single trial (Cassava Sciences NCT04994483) into the database
2. **Enqueues** a PUBMED_U1 task to start the pipeline
3. **Runs workers** locally to process the task queue
4. **Monitors** progress through real database writes
5. **Verifies** results with SQL queries

All downstream work is **real**: PubMed API calls, document processing, R/S scoring, OA retrieval, and study card generation.

## Prerequisites

### 1. Database Setup

Create a separate test database (recommended):

```bash
# Create test database
createdb lit_test

# Set environment variable
export DATABASE_URL=postgresql://user:pass@localhost:5432/lit_test

# Run all migrations
alembic upgrade head
```

### 2. API Keys

Set up your API keys:

```bash
export PUBMED_API_KEY=your_key_here        # Optional but recommended
export OPENAI_API_KEY=your_key_here        # Required for study cards
export ANTHROPIC_API_KEY=your_key_here     # Optional fallback
```

### 3. Dependencies

Ensure all Python dependencies are installed:

```bash
pip install -r requirements.txt
```

## Quick Start

### Option 1: Automatic Test Runner

```bash
# Run the complete test with monitoring
python scripts/run_single_trial_test.py

# Or just inject the trial and start workers manually
python scripts/run_single_trial_test.py --inject-only
```

### Option 2: Manual Step-by-Step

#### Step 1: Inject the Trial

```python
# In Python shell or script
import yaml
from src.ncfd.pipeline.orchestrator import UnifiedPipelineOrchestrator

# Load config
with open('config/single_trial_test.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Initialize orchestrator and inject trial
orchestrator = UnifiedPipelineOrchestrator(config)
trial_id = orchestrator.inject_ctgov_trial_for_test(
    nct_id="NCT04994483",
    company_name="Cassava Sciences",
    asset_aliases=["simufilam", "PTI-125"],
    indication_terms=["Alzheimer's disease"]
)
print(f"Injected trial: {trial_id}")
```

#### Step 2: Start Workers

In separate terminal windows:

```bash
# Terminal 1: U1+ Worker (Discovery + Abstract Processing)
python workers/pubmed_u1_worker.py --env test

# Terminal 2: OA Worker (Full Text Retrieval)
python workers/pubmed_oa_worker.py --env test

# Terminal 3: Study Card Worker (Study Card Generation)
python workers/studycard_worker.py --env test
```

#### Step 3: Monitor Progress

```bash
# Check overall progress
python scripts/verify_single_trial_test.py

# Check just the summary
python scripts/verify_single_trial_test.py --summary-only

# Monitor task queue
psql $DATABASE_URL -c "SELECT task_type, status, COUNT(*) FROM tasks GROUP BY 1,2 ORDER BY 1,2;"
```

## What Happens During the Test

### 1. Trial Injection
- Creates `Cassava Sciences` company record
- Creates trial record with NCT04994483
- Wires trial to company
- Enqueues `PUBMED_U1` task

### 2. U1+ Processing (Discovery + Abstracts)
- Builds PubMed search query for "simufilam" + "Alzheimer's disease"
- Executes ESearch to find relevant PMIDs
- Fetches abstract text via EFetch
- Extracts entities (NCTs, phases, numbers)
- Computes R/S scores for relevance and shortability
- Stores documents, abstracts, scores in database
- Enqueues `PUBMED_OA` task for selected documents

### 3. OA Processing (Full Text)
- Attempts to retrieve full text for high-scoring documents
- Uses PMC and Unpaywall APIs
- Stores full text in `document_text.fulltext_text`
- Enqueues `STUDYCARD` task when complete

### 4. Study Card Generation
- Processes full text documents with LLM
- Generates method cards, results cards
- Stores structured data
- Updates trial literature state

## Verification Queries

The verification script runs these key queries:

### Trial Setup
```sql
-- Your single trial is present and wired
SELECT t.trial_id, t.nct_id, t.sponsor_company_id, c.name
FROM trials t
LEFT JOIN companies c ON c.company_id = t.sponsor_company_id
WHERE t.nct_id = 'NCT04994483';
```

### Task Queue Progress
```sql
-- Queue shows tasks moving through states
SELECT status, task_type, count(*) FROM tasks GROUP BY 1,2 ORDER BY 2,1;
```

### Document Processing
```sql
-- After U1 worker runs, you should see abstracts + scores
SELECT count(*) FROM document_text dt
JOIN documents d ON d.id = dt.doc_id
JOIN trial_doc_candidates c ON c.pmid = d.pmid
WHERE c.trial_id = <trial_id> AND dt.abstract_text IS NOT NULL;

SELECT * FROM doc_rs_scores WHERE trial_id = <trial_id> ORDER BY R_score DESC LIMIT 10;
```

### Full Text Processing
```sql
-- After OA worker runs
SELECT count(*) FROM document_text dt
JOIN documents d ON d.id = dt.doc_id
JOIN trial_doc_candidates c ON c.pmid = d.pmid
WHERE c.trial_id = <trial_id> AND dt.fulltext_text IS NOT NULL;
```

### Trial State
```sql
-- Trial literature state updated
SELECT * FROM trial_lit_state WHERE trial_id = <trial_id>;
```

## Expected Results

A successful test should show:

1. **Trial Creation**: 1 company, 1 trial, properly wired
2. **Task Progression**: PUBMED_U1 → PUBMED_OA → STUDYCARD tasks moving from `queued` → `leased` → `done`
3. **Document Discovery**: 50-150 documents found via PubMed search
4. **Abstract Processing**: Abstracts fetched, entities extracted, R/S scores computed
5. **Full Text Retrieval**: Some subset of documents with full text (depends on OA availability)
6. **Study Card Generation**: Structured cards generated from full text

## Configuration

The test uses `config/single_trial_test.yaml` with these key settings:

- **Execution Order**: Only runs `ctgov` pipeline (for injection)
- **Seed Trials**: Cassava Sciences trial configuration
- **Rate Limits**: Conservative API rate limiting
- **Processing Limits**: max_results=150 for faster testing
- **Worker Settings**: Appropriate timeouts and batch sizes

## Troubleshooting

### No Tasks Processing
- Check workers are running and connecting to correct database
- Verify `DATABASE_URL` environment variable
- Check task queue: `SELECT * FROM tasks ORDER BY created_at DESC;`

### API Rate Limiting
- Ensure `PUBMED_API_KEY` is set for higher rate limits
- Check worker logs for rate limit errors
- Adjust `rate_limit_requests_per_minute` in config

### Study Card Generation Fails
- Verify LLM API keys are set (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)
- Check that full text documents were retrieved in OA stage
- Review study card worker logs

### Database Connection Issues
- Verify database exists and migrations are current
- Check database URL format and credentials
- Ensure test database is separate from production

## Advanced Usage

### Custom Trial Injection

```python
# Inject a different trial
trial_id = orchestrator.inject_ctgov_trial_for_test(
    nct_id="NCT05515666",
    company_name="Example Pharma",
    asset_aliases=["drug-x", "compound-123"],
    indication_terms=["diabetes", "type 2 diabetes"],
    extra_trial_fields={
        "phase": "P2",
        "status": "ACTIVE",
        "brief_title": "Study of Drug-X in Type 2 Diabetes"
    }
)
```

### Custom Worker Configuration

```bash
# Run with debug logging
python workers/pubmed_u1_worker.py --env test --config config/debug.yaml

# Process limited tasks for testing
python workers/pubmed_u1_worker.py --env test --max-tasks 1

# Custom worker ID
python workers/pubmed_u1_worker.py --env test --worker-id my_test_worker
```

### Monitoring with SQL

```sql
-- Real-time task monitoring
SELECT 
    task_type, 
    status, 
    COUNT(*) as count,
    MIN(created_at) as first_created,
    MAX(updated_at) as last_updated
FROM tasks 
GROUP BY task_type, status 
ORDER BY task_type, status;

-- Document processing pipeline
SELECT 
    'Documents' as stage,
    COUNT(*) as count
FROM documents d
JOIN trial_doc_candidates c ON c.pmid = d.pmid
WHERE c.trial_id = <trial_id>

UNION ALL

SELECT 
    'Abstracts' as stage,
    COUNT(*) as count
FROM document_text dt
JOIN documents d ON d.id = dt.doc_id
JOIN trial_doc_candidates c ON c.pmid = d.pmid
WHERE c.trial_id = <trial_id> AND dt.abstract_text IS NOT NULL

UNION ALL

SELECT 
    'Full Text' as stage,
    COUNT(*) as count
FROM document_text dt
JOIN documents d ON d.id = dt.doc_id
JOIN trial_doc_candidates c ON c.pmid = d.pmid
WHERE c.trial_id = <trial_id> AND dt.fulltext_text IS NOT NULL;
```

This single trial test gives you complete confidence that your pipeline works end-to-end with real data while maintaining the speed and isolation needed for development and testing.
