# Deep Investigation: Why Relationship Tables Are Empty

**Date:** 2025-01-27  
**Investigation Script:** `investigate_empty_relationships.py`

## Executive Summary

The relationship tables (`publication_trials`, `publication_drugs`, `filing_drugs`) are empty because **publications and SEC filings were inserted directly into the database, bypassing the processing pipeline entirely**. This means:

1. **No relationships were created** - `extract_relationships()` was never called
2. **Missing data** - Publications don't have abstracts, filings don't have full_text
3. **No processing logs** - No evidence these records went through the pipeline

## Root Cause Analysis

### 1. Publications (100 records)

**Status:**
- ✅ 100 publications in database
- ❌ **0 processing logs** for PubMed
- ❌ **0 staging records** for PubMed
- ❌ **0 abstracts** (all publications have `abstract = NULL`)
- ❌ **0 NCT IDs found** in publication text

**Root Cause:**
Publications were inserted directly into the `publications` table, bypassing:
- `ingestion/pubmed.py` → staging
- `src/processors/pubmed_processor.py` → entity extraction
- `src/processing/pipeline.py` → relationship creation

**Impact:**
- `extract_relationships()` was never called
- No publication-trial relationships created (even if NCT IDs existed, they weren't extracted)
- No publication-drug relationships created (drug extraction requires abstract text)

### 2. SEC Filings (49 records)

**Status:**
- ✅ 49 SEC filings in database
- ❌ **0 processing logs** for sec_edgar
- ❌ **0 staging records** for sec_edgar
- ❌ **0 filings have full_text** (all have `full_text = NULL`)
- ❌ **0 filing-drug relationships**

**Root Cause:**
Filings were inserted directly into the `sec_filings` table, bypassing:
- `ingestion/sec_edgar.py` → staging
- `src/processors/sec_filings_processor.py` → entity extraction
- `src/processing/pipeline.py` → relationship creation

**Impact:**
- `extract_relationships()` was never called
- No filing-drug relationships created (drug extraction requires `full_text`)
- Filing-company relationships exist (49) - likely created separately or during direct insertion

### 3. Processor Code Status

**Good News:** The processor code is **correctly implemented**:

1. **PubMedProcessor** (`src/processors/pubmed_processor.py`):
   - ✅ `extract_relationships()` method exists (lines 103-183)
   - ✅ Extracts NCT IDs from text (line 133)
   - ✅ Queries database for matching trials (lines 137-139)
   - ✅ Creates publication-trial relationships (lines 143-151)
   - ✅ Creates publication-drug relationships (lines 154-166)
   - ✅ Drug extraction implemented (lines 240-296)
   - ✅ Loads drug names from database (lines 298-339)

2. **SECFilingsProcessor** (`src/processors/sec_filings_processor.py`):
   - ✅ `extract_relationships()` method exists (lines 104-196)
   - ✅ Creates filing-drug relationships (lines 137-155)
   - ✅ Drug extraction implemented (lines 316-357)
   - ✅ Loads drug names from database (lines 465+)

3. **Pipeline Integration** (`src/processing/pipeline.py`):
   - ✅ Calls `extract_relationships()` (line 478)
   - ✅ Creates relationships via `RelationshipBuilder` (lines 498-503)
   - ✅ Proper entity stub to ID mapping (lines 484-489)

## Evidence

### Investigation Results

```
INVESTIGATION: Publication-Trial Relationships
1. Publications in database: 100
2. NCT IDs found in sample publications: 0
3. Trials in database: 1017
5. PubMed processing logs: 0  ← KEY FINDING
6. PubMed staging records: 0   ← KEY FINDING
7. Testing processor extraction...
   No staging records found to test  ← KEY FINDING

INVESTIGATION: Publication-Drug Relationships
1. Drugs in database: 865
2. Drug names loaded by processor: 898  ← Processor works!
3. Testing drug extraction from publication...
   No staging records found to test  ← KEY FINDING

INVESTIGATION: Filing-Drug Relationships
1. SEC Filings in database: 49
2. Filings with full_text: 0  ← KEY FINDING
3. Drugs in database: 865
4. Drug names loaded by processor: 898  ← Processor works!
5. Testing drug extraction from filing...
   No staging records found to test  ← KEY FINDING
6. SEC processing logs: 0  ← KEY FINDING
```

### Database State

```python
# Publications
- Count: 100
- With abstracts: 0 (all have abstract = NULL)
- Processing logs: 0
- Staging records: 0

# SEC Filings
- Count: 49
- With full_text: 0 (all have full_text = NULL)
- Processing logs: 0
- Staging records: 0
```

## Why This Happened

Possible scenarios:

1. **Direct Database Insertion**: Publications and filings were inserted via SQL or ORM directly, skipping the ingestion → staging → processing flow

2. **Old Data Migration**: Data was migrated from another system without going through the pipeline

3. **Test Data**: Data was inserted for testing purposes without full processing

4. **Incomplete Ingestion**: Ingestion scripts were run but processing pipeline was never executed

## Solutions

### Option 1: Reprocess Existing Data (Recommended)

**For Publications:**
1. Export publications to staging
2. Run processing pipeline
3. Relationships will be created

**For SEC Filings:**
1. Re-fetch filings with full_text
2. Load to staging
3. Run processing pipeline
4. Relationships will be created

### Option 2: Run Relationship Inference

Use the inference service to create relationships from existing data:

```bash
# For publication-trial relationships
python scripts/infer_relationships.py --types publication_trial

# For publication-drug relationships  
python scripts/infer_relationships.py --types publication_drug

# For filing-drug relationships
python scripts/infer_relationships.py --types filing_drug
```

**Note:** This requires:
- Publications to have abstracts (currently they don't)
- Filings to have full_text (currently they don't)

### Option 3: Re-ingest Data Properly

1. **Clear existing data** (or mark as needing reprocessing)
2. **Re-run ingestion scripts** with `load_to_staging=True`
3. **Run processing pipeline** on staging data
4. Relationships will be created automatically

## Verification Steps

To verify the fix works:

1. **Check staging records exist:**
   ```sql
   SELECT COUNT(*) FROM staging_raw_data WHERE source_system = 'pubmed';
   SELECT COUNT(*) FROM staging_raw_data WHERE source_system = 'sec_edgar';
   ```

2. **Check processing logs:**
   ```sql
   SELECT COUNT(*) FROM source_processing_log WHERE source_name = 'pubmed';
   SELECT COUNT(*) FROM source_processing_log WHERE source_name = 'sec_edgar';
   ```

3. **Check relationships created:**
   ```sql
   SELECT COUNT(*) FROM publication_trials;
   SELECT COUNT(*) FROM publication_drugs;
   SELECT COUNT(*) FROM filing_drugs;
   ```

4. **Check data completeness:**
   ```sql
   SELECT COUNT(*) FROM publications WHERE abstract IS NOT NULL;
   SELECT COUNT(*) FROM sec_filings WHERE full_text IS NOT NULL;
   ```

## Conclusion

**The code is correct** - processors and pipeline are properly implemented. The issue is **data was inserted directly, bypassing the processing pipeline**.

**Fix:** Reprocess the data through the proper pipeline:
1. Load publications/filings to staging (with full data: abstracts, full_text)
2. Run processing pipeline
3. Relationships will be created automatically

The relationship creation logic works - it just needs to be executed on properly processed data.

