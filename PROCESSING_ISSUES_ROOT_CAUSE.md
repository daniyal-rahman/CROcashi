# Root Cause Analysis: Processing Issues

**Date:** 2025-01-27  
**Diagnostic Script:** `diagnose_processing_issues.py`

## Summary

The audit findings reveal three critical issues:
1. **Only 22 sources have data** (not 30+ as might be claimed)
2. **Only 5 sources have processing logs** (despite 22 having staging data)
3. **80.6% of staging records are unprocessed** (1,701 out of 2,110 records, or 231 out of 286 non-deleted records)

**Note on Record Counts:**
- **Total staging records (including deleted):** 2,110
- **Non-deleted staging records:** 286
- **Deleted records:** 1,824 (86.4% of all records)
- The audit counts all records, while the diagnostic only counts non-deleted records
- Most deleted records were likely processed and then cleaned up

## Root Causes

### Issue 1: Why Only 22 Sources Have Data (Not 30)

**Root Cause:** 16 active sources have never been ingested.

**Details:**
- 37 sources are marked as "active" in the database
- Only 22 sources actually have staging data
- 16 active sources have never had their ingestion scripts executed:
  - `fda_breakthrough`
  - `fda_clinical_hold`
  - `fda_expanded_access`
  - `fda_orange_book`
  - `fda_purple_book`
  - `federal_warn`
  - `fierce_layoff_tracker`
  - `ich_guidelines`
  - `mhra_uk`
  - `nsf_awards`
  - `patentsview`
  - `tga_australia`
  - `uspto_public_pair`
  - `vaers`
  - `who_ictrp`
  - `who_outbreak_news`

**Solution:**
- Run ingestion scripts for these 16 active sources
- Or deactivate sources that don't work or aren't needed

### Issue 2: Why Only 5 Sources Have Processing Logs

**Root Cause:** The processing pipeline has only been run for 5 sources, despite 22 sources having staging data and processors.

**Details:**
- 22 sources have staging data AND processors available
- Only 5 sources have processing logs (evidence of pipeline execution):
  1. `fda_guidance` (130 logs)
  2. `fda_eua` (67 logs)
  3. `california_warn` (25 logs)
  4. `fda_orphan` (3 logs)
  5. `fda_warning_letters` (1 log)

- 17 sources have staging data but NO processing logs:
  - Most have 0 staging records (likely old/deleted data)
  - `nih_reporter` has 90 staging records but has never been processed
  - `clinicaltrials_gov`, `pubmed`, `sec_edgar`, `fda_drugs` show 0 records (may have been processed and deleted, or never ingested)

**Solution:**
- Run the processing pipeline for all sources with staging data
- Start with sources that have the most unprocessed records:
  - `nih_reporter`: 90 unprocessed records
  - `fda_eua`: 75 unprocessed records (partially processed)
  - `fda_guidance`: 63 unprocessed records (partially processed)

### Issue 3: Why 80.6% of Staging Records Are Unprocessed

**Root Cause:** The processing pipeline has not been run for most sources, or was run partially and stopped.

**Details:**
- **Total staging records (all):** 2,110
- **Processed (by processed_at):** 409 (19.4%)
- **Unprocessed (all):** 1,701 (80.6%)

- **Non-deleted staging records:** 286
- **Processed (non-deleted, by flag):** 55 (19.2%)
- **Unprocessed (non-deleted):** 231 (80.8%)

**Note:** There's a discrepancy between `processed_at` (409) and `processed` flag (55). This suggests:
- Some records have `processed_at` set but `processed == False`
- Or some processed records were deleted (1,824 deleted records)
- The audit uses `processed_at` while the diagnostic uses the `processed` flag

**Breakdown by source:**
1. `nih_reporter`: 90 unprocessed (100% unprocessed) - **NEVER PROCESSED**
2. `fda_eua`: 75 unprocessed (75% unprocessed) - **PARTIALLY PROCESSED**
3. `fda_guidance`: 63 unprocessed (75% unprocessed) - **PARTIALLY PROCESSED**
4. `fda_orphan`: 3 unprocessed (75% unprocessed) - **PARTIALLY PROCESSED**
5. `california_warn`: 0 unprocessed (100% processed) - **FULLY PROCESSED**

**Key Finding:** All unprocessed records are from sources that HAVE processors. There are no records stuck because of missing processors.

**Solution:**
- Run the processing pipeline for all sources with unprocessed records
- Priority order:
  1. `nih_reporter` (90 records, never processed)
  2. `fda_eua` (75 records, partially processed)
  3. `fda_guidance` (63 records, partially processed)
  4. `fda_orphan` (3 records, partially processed)

## Recommended Actions

### Immediate (Critical)

1. **Process unprocessed staging records:**
   ```bash
   # Process nih_reporter (90 records)
   python -m src.processing.pipeline process_source nih_reporter
   
   # Process remaining fda_eua records (75 records)
   python -m src.processing.pipeline process_source fda_eua
   
   # Process remaining fda_guidance records (63 records)
   python -m src.processing.pipeline process_source fda_guidance
   
   # Process remaining fda_orphan records (3 records)
   python -m src.processing.pipeline process_source fda_orphan
   ```

2. **Ingest data for active sources without staging data:**
   - Run ingestion scripts for the 16 active sources that have no data
   - Or deactivate sources that aren't needed

### Medium Priority

3. **Verify why major sources show 0 staging records:**
   - `clinicaltrials_gov`: Should have thousands of records
   - `pubmed`: Should have hundreds of records
   - `sec_edgar`: Should have records
   - `fda_drugs`: Should have records
   
   These may have been:
   - Processed and deleted from staging (normal workflow)
   - Never ingested
   - Deleted manually

4. **Set up automated processing:**
   - Automatically process new staging records after ingestion
   - Monitor processing success rates

### Long Term

5. **Review source activation:**
   - Only mark sources as "active" if they're actually being used
   - Deactivate sources that don't work or aren't needed

6. **Document actual status:**
   - Update documentation to reflect that only 5 sources have been processed
   - Not 30+ sources as might be claimed

## Technical Notes

- All sources with staging data have processors available (39 processors total)
- No records are stuck due to missing processors
- Processing pipeline works correctly when executed (100% success rate for processed records)
- The issue is simply that the pipeline hasn't been run for most sources

## Verification

After running the processing pipeline, verify with:
```bash
python diagnose_processing_issues.py
```

Expected results:
- Processing logs should exist for all sources with staging data
- Processing rate should be close to 100% for sources that have been processed
- Unprocessed record count should decrease significantly

