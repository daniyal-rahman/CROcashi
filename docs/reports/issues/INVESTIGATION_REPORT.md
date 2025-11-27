# Investigation Report: LLM-Generated Codebase Analysis

**Date:** November 7, 2025  
**Task:** Deep investigation of LLM-generated biotech knowledge graph codebase

---

## Executive Summary

The codebase investigation revealed **critical architectural flaws** that rendered the system non-functional, despite passing superficial inspection. The code looked professional and well-structured on the surface, but key components were completely disconnected.

### What I Found:

✅ **What Was Working:**
- Database schema (45+ tables, proper constraints)
- SQLAlchemy models (well-designed)
- Entity resolution logic (sophisticated matching)
- Ingestion API calls (proper HTTP clients, rate limiting)

❌ **Critical Issues Found:**
1. **ALL 80+ ingestion scripts were NOT connected to the database** - they only wrote JSON files
2. **No wiring between ingestion layer and processing pipeline** - complete architectural gap
3. **Multiple bugs in entity creation logic** - incomplete implementations
4. **Database constraint mismatches** - pipeline used values not allowed by DB schema

---

## Detailed Findings

### Issue #1: Complete Disconnect Between Ingestion and Database

**Problem:** Every single ingestion script (80+ files) only wrote data to JSON files on disk. None of them inserted data into the staging table required by the processing pipeline.

**Example - Before Fix:**
```python
# ingestion/clinicaltrials_gov.py
def fetch_studies_sample(query_term, page_size, save_dir):
    data = client.get(API_BASE, params=params)
    
    # Only writes to file - no database insert!
    if save_dir is not None:
        write_text(output, resp.text)
    
    return data
```

**Why This Happened:**
- LLM generated ingestion scripts independently
- LLM generated pipeline independently
- Never tested them together end-to-end
- Classic "looks good in isolation" syndrome

**Impact:** Zero data could flow through the system. The entire pipeline was useless.

---

### Issue #2: Incomplete Entity Creation Logic

**Problem:** The `_build_entity_data()` method in the pipeline only handled 3 entity types (Company, Drug, Disease), but processors extracted 7 types (Company, Institution, Drug, Disease, Target, Trial, Publication).

**Error:**
```
psycopg2.errors.NotNullViolation: null value in column "name" of relation "institutions"
```

**Root Cause:** When the pipeline tried to create an Institution entity, the `_build_entity_data()` method returned an empty dict because it had no case for Institutions.

**Fix Applied:**
- Added Institution, Target, and Publication cases to `_build_entity_data()`
- Properly mapped all required fields

---

### Issue #3: Database Constraint Mismatches

**Problem:** The Institution table had a CHECK constraint requiring specific values:
```sql
CHECK (institution_type IN ('university', 'hospital', 'research_institute', 
                            'government', 'cooperative_group'))
```

But ClinicalTrials.gov API returns different values: `'other'`, `'nih'`, `'other_gov'`, etc.

**Fix Applied:**
- Added mapping logic in pipeline:
```python
institution_type_map = {
    'other': 'research_institute',
    'nih': 'government',
    'other_gov': 'government',
    'fed': 'government',
    'network': 'cooperative_group'
}
```

---

### Issue #4: Relationship Extraction Bugs

**Problem:** Index out of range errors when creating trial-drug relationships because code assumed parallel arrays but they weren't guaranteed to be same length.

**Fix Applied:**
- Added bounds checking before array access
- Graceful fallback to defaults

---

## Solution Implemented

### 1. Created Staging Loader Utility

**File:** `ingestion/utils/staging_loader.py`

A reusable component that all ingestion scripts can use to insert data into the staging table:

```python
class StagingLoader:
    """Loads raw data into the staging table for processing."""
    
    def load_records(self, records, id_extractor, skip_duplicates=True):
        # Insert records with proper transaction handling
        # Deduplicate using source-specific ID extractor
        # Return stats (inserted, skipped, errors)
```

**Features:**
- Transaction management
- Deduplication
- Batch processing
- Comprehensive stats
- Reusable ID extractors for common sources

### 2. Wired Up Main Data Sources

Updated ingestion scripts to use the staging loader:

**ClinicalTrials.gov:**
```python
def fetch_studies_sample(..., load_to_staging=True):
    data = client.get(API_BASE, params=params)
    
    # NEW: Load to staging for processing
    if load_to_staging and isinstance(data, dict) and 'studies' in data:
        loader = StagingLoader('clinicaltrials_gov')
        stats = loader.load_records(
            data['studies'],
            id_extractor=clinicaltrials_id_extractor,
            skip_duplicates=True
        )
    
    return data
```

**Status:**
- ✅ ClinicalTrials.gov - Fully wired and tested
- ✅ PubMed - Wired to staging (processor pending)
- ⏳ FDA Drugs - Needs different approach (file-based)
- ⏳ 75+ other sources - Need wiring

### 3. Fixed Pipeline Bugs

- Completed `_build_entity_data()` for all entity types
- Added institution type mapping
- Fixed relationship extraction bounds checking
- Improved error handling

---

## Verification

### End-to-End Test Results

Created comprehensive test suite (`test_end_to_end.py`) that verifies:

```
✅ PASS: ClinicalTrials.gov
   - Fetched 3 studies from API
   - Loaded to staging table
   - Processed through pipeline
   - Created entities: 9
   - Database totals:
     * Trials: 4
     * Companies: 2
     * Institutions: 2
     * Drugs: 1
     * Diseases: 7

✅ PASS: PubMed
   - Fetched 5 publications
   - Loaded to staging table
   - Ready for processor implementation
```

**Data Flow Verified:**
```
API Call → Staging Table → Pipeline Processing → Entity Resolution → Database Entities
```

---

## Architecture Overview (Fixed)

### Before (Broken):
```
Ingestion Scripts → JSON Files on Disk
                                        ❌ GAP - No connection!
                    Staging Table → Pipeline → Database
```

### After (Working):
```
Ingestion Scripts → Staging Table → Pipeline → Entity Resolution → Database
                ↓                                                  ↓
            JSON Files (optional)                      Resolved Entities
```

---

## Remaining Work

### Immediate Priorities:

1. **Create PubMed Processor**
   - Extract publication entities
   - Extract author relationships
   - Handle author affiliations → companies/institutions

2. **Create FDA Drugs Processor**
   - Handle file-based ingestion (ZIP files)
   - Parse structured drug data
   - Extract approval history

3. **Create SEC Edgar Processor**
   - Handle 10-K/10-Q filings
   - Extract company events
   - Parse financial signals

4. **Wire Up Priority Sources (Next 10-15)**
   - WHO ICTRP
   - EMA Clinical Trials
   - bioRxiv/medRxiv
   - Patents (USPTO)
   - WARN notices (layoff signals)

### Long-term:

- Wire up remaining ~65 sources
- Add relationship processors for each source
- Implement review interface for entity matching
- Add comprehensive test coverage
- Performance optimization for large-scale ingestion

---

## Key Lessons

### Why This Happened:

1. **No Integration Testing:** Each component was generated independently and never tested together
2. **No Real Data Testing:** Tests used mock data that didn't expose issues
3. **Assumed Completion:** LLM assumed glue code existed when it didn't
4. **Copy-Paste Pattern:** All 80+ ingestion scripts followed same broken pattern

### What Would Have Caught This Earlier:

1. A single end-to-end test with real API data
2. Checking if staging table was actually populated
3. Running the pipeline on actual ingested data
4. Integration tests before unit tests

### Green Flags That Were Misleading:

- ✓ Code formatted properly
- ✓ Type hints present
- ✓ Docstrings comprehensive
- ✓ Error handling in place
- ✓ Logging statements correct
- ✓ Database schema valid

**But none of that mattered because the components weren't connected!**

---

## Testing Strategy Going Forward

### 1. Always Test Integration First:
```python
# This would have caught the issue immediately:
def test_basic_integration():
    # Fetch from API
    result = fetch_studies_sample(page_size=1, load_to_staging=True)
    
    # Check staging table
    assert staging_table_count() > 0  # Would fail!
    
    # Process
    pipeline.process_source('clinicaltrials_gov', limit=1)
    
    # Verify entities
    assert entities_created() > 0  # Would fail!
```

### 2. Use Real Data, Not Mocks:
- Mock data hides schema mismatches
- Mock data hides missing fields
- Mock data hides constraint violations
- Real API calls expose issues

### 3. Test the Wiring, Not Just the Components:
```python
# BAD (what LLM probably "tested"):
def test_ingestion():
    result = fetch_studies()
    assert len(result) > 0  # ✓ Passes but meaningless!

# GOOD (what actually matters):
def test_ingestion_to_staging():
    fetch_studies(load_to_staging=True)
    records = get_staging_records()
    assert len(records) > 0  # ✓ Tests the wiring!
```

---

## Current System Status

### ✅ Working:
- ClinicalTrials.gov: End-to-end data flow verified
- PubMed: Ingestion to staging working
- Pipeline: Entity creation and resolution
- Database: All tables functional

### ⏳ In Progress:
- Relationship creation (partially working)
- Entity matching (basic implementation)

### 📋 TODO:
- 75+ data sources need wiring
- PubMed, FDA, SEC processors needed
- Comprehensive test suite
- Performance testing

---

## Conclusion

The codebase suffered from the **"looks good but doesn't work" syndrome** typical of LLM-generated systems that aren't integration tested. The individual components were well-written, but the critical connections between them were missing.

**Impact of Fixes:**
- ✅ ClinicalTrials.gov now fully functional end-to-end
- ✅ Framework in place to wire up remaining sources quickly
- ✅ Test harness established to prevent regressions

**Next Steps:**
1. Wire up 10-15 priority sources using the StagingLoader pattern
2. Create processors for PubMed, FDA, SEC
3. Test relationship creation thoroughly
4. Add comprehensive integration tests

The system is now **actually functional** rather than just **apparently functional**.

---

**Files Created/Modified:**
- Created: `ingestion/utils/staging_loader.py` - Staging loader utility
- Modified: `ingestion/clinicaltrials_gov.py` - Added staging integration
- Modified: `ingestion/pubmed.py` - Added staging integration  
- Modified: `src/processing/pipeline.py` - Fixed entity creation bugs
- Modified: `src/processors/clinicaltrials_processor.py` - Fixed relationship bugs
- Created: `test_end_to_end.py` - End-to-end integration tests
- Created: `test_actual_functionality.py` - Comprehensive functionality tests
- Created: `INVESTIGATION_REPORT.md` - This document

