# Data Ingestion Status

## Current Data Coverage

**Date Range:**
- Events: 2025-11-07 to 2025-11-08 (only 2 days!)
- Trials: No registration dates captured

**Volume:**
- ~262 events
- ~269 trials
- ~108 companies

## Issue Identified

The initial ingestion only fetched:
- 200 ClinicalTrials.gov studies with keyword search (no date filter)
- 100 PubMed articles (no date filter)
- Result: Very limited date range (mostly recent test data)

## Updated Ingestion (1 Year)

The `scripts/volume_ingestion.py` script has been updated to:

1. **ClinicalTrials.gov**: Fetch up to 1000 studies from last 365 days
   - Uses date filter: `AREA[LastUpdatePostDate]RANGE[{cutoff_date},MAX]`
   - Uses diverse queries to get variety
   - Fetches in batches

2. **PubMed**: Fetch up to 500 articles from last 365 days
   - Uses date filter: `{cutoff_date}:{today}[PDAT]`
   - Filters by publication date

## To Ingest 1 Year of Data

Run:
```bash
python scripts/volume_ingestion.py
```

This will:
1. Fetch 1000 ClinicalTrials.gov studies from last year
2. Fetch 500 PubMed articles from last year
3. Process all through the pipeline
4. Backfill events from trial status history

**Expected Results:**
- Much broader date range (full year)
- More diverse trials and companies
- Better risk score calculations
- More meaningful failure analysis

## Notes

- The ClinicalTrials.gov API doesn't support simple pagination, so we use diverse queries
- Some trials may be duplicates (handled by `skip_duplicates=True`)
- Processing may take 10-30 minutes depending on data volume
- Events will be created for all trial status changes during processing

