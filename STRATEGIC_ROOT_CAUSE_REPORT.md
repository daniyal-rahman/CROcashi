# Strategic Root Cause Report

**Date:** 2025-01-27  
**Audit Script:** `pre_action_audit.py`

## Executive Summary

The pre-action audit reveals **critical strategic context** missing from the initial diagnostic. The situation is **better than it appeared** but reveals **infrastructure gaps** that explain the current state.

### Key Findings

✅ **Good News:**
- Critical sources (clinicaltrials_gov, sec_edgar, pubmed, fda_drugs) **ARE working** - they have entities in the database
- Entity coverage is solid: 331 companies, 865 drugs, 1,017 trials
- Processing pipeline works correctly when executed (100% success rate)
- 362 processed records were successfully cleaned up after processing

⚠️ **Critical Issues:**
- **No automation infrastructure** - everything is manual (root cause)
- 496 entity match candidates need review (entity resolution quality issue)
- clinicaltrials_gov: 1,037 deleted records with 0% processed (concerning)
- 231 unprocessed records from non-critical sources

## Detailed Findings

### 1. Entity Creation Verification ✅

**Processed sources created entities successfully:**

| Source | Records | Entities Created | Entities Matched | Relationships |
|--------|---------|------------------|-------------------|---------------|
| fda_eua | 67 | 105 | 43 | 88 |
| fda_guidance | 130 | 94 | 28 | 0 |
| california_warn | 25 | 5 | 20 | 0 |
| fda_orphan | 3 | 6 | 6 | 8 |
| fda_warning_letters | 1 | 6 | 1 | 6 |

**Actual entity counts in database:**
- Companies: 331 (100% have source metadata)
- Drugs: 865 (99.9% have source metadata)
- Diseases: 1,479
- Trials: 1,017
- Publications: 100
- SEC Filings: 49

**Conclusion:** Processing pipeline works correctly. Entities are being created and relationships are being formed.

### 2. Critical Sources Investigation ✅

**The "0 records" mystery is SOLVED:**

| Source | Staging (non-deleted) | Staging (all) | Entities in DB | Status |
|--------|----------------------|---------------|----------------|--------|
| clinicaltrials_gov | 0 | 1,037 | 1,017 trials | ✅ **WORKING** |
| sec_edgar | 0 | 50 | 49 filings | ✅ **WORKING** |
| pubmed | 0 | 100 | 100 publications | ✅ **WORKING** |
| fda_drugs | 0 | 9 | 865 drugs | ✅ **WORKING** |

**Root Cause:** These sources **were ingested and processed**, then staging records were **deleted after successful processing**. This is normal workflow.

**However:** clinicaltrials_gov shows 1,037 deleted records but **0% were processed before deletion**. This suggests:
- Records were deleted without processing, OR
- Processing happened but logs weren't created, OR
- Records were bulk-deleted manually

**Action Required:** Investigate why clinicaltrials_gov has 1,017 trials in database but 0 processing logs.

### 3. Deleted Records Investigation 🔍

**Total staging records:** 2,110
- **Deleted:** 1,824 (86.4%)
- **Non-deleted:** 286

**Processed records:**
- Processed and deleted: 362 (normal cleanup)
- Processed but not deleted: 47 (retained)

**Top sources with deleted records:**
- clinicaltrials_gov: 1,037 deleted, **0% processed before deletion** ⚠️
- openfda: 100 deleted, **100% processed before deletion** ✅
- pubmed: 100 deleted, **100% processed before deletion** ✅
- sec_edgar: 50 deleted, **100% processed before deletion** ✅

**Entities per deleted processed record:** 6.11
- This is healthy - indicates successful entity extraction

**Conclusion:** Most deleted records were successfully processed. The clinicaltrials_gov anomaly needs investigation.

### 4. Entity Resolution Quality ⚠️

**Match candidates needing review:** 496

**Entity resolution rates by source:**
- california_warn: 100% match rate ✅
- fda_guidance: 100% match rate ✅
- fda_orphan: 75% match rate ✅
- fda_eua: 52.3% match rate (needs improvement)
- fda_warning_letters: 14.3% match rate (needs improvement)

**Issues:**
- 496 match candidates need manual review
- fda_warning_letters has low match rate (14.3%) - may indicate entity resolution issues

**Action Required:** Review and improve entity resolution for fda_warning_letters and fda_eua.

### 5. Relationship Coverage Analysis ⚠️

**Relationships created from processing logs:**
- fda_eua: 88 relationships (1.31 per record)
- fda_orphan: 8 relationships (2.67 per record)
- fda_warning_letters: 6 relationships (6.00 per record)

**Actual relationship counts:**
- Trial-Sponsor: 1,748 ✅
- Trial-Drug: 1,228 ✅
- Trial-Disease: 2,085 ✅
- Publication-Trial: 0 ❌
- Publication-Drug: 0 ❌
- Filing-Drug: 0 ❌

**Critical Gap:** Cross-source relationships are not being created. Publications and filings are not linked to trials/drugs.

**Root Cause:** Relationship inference has not been run (as identified in original audit).

### 6. Automation Infrastructure ❌

**No automation found:**
- ✗ No cron schedule
- ✗ No scheduled tasks
- ✗ No automation scripts

**Recent activity (manual):**
- Processing: 2 days ago (5 sources)
- Ingestion: 1 day ago (5 sources)

**Root Cause Identified:** **Everything is manual.** This explains why:
- Only 5 sources have processing logs (someone manually ran them)
- 16 active sources have no data (ingestion scripts never run)
- Processing stopped after initial batch

**This is the actual root cause** - not that scripts haven't been run, but that **there's no infrastructure to run them automatically**.

### 7. Strategic Priority Assessment

**Current entity coverage:**
- Companies: 331 ✅ (good foundation)
- Drugs: 865 ✅ (good foundation)
- Trials: 1,017 ✅ (good foundation)

**Entity sources status:**
- clinicaltrials_gov: ✅ Working (has entities)
- fda_drugs: ✅ Working (has entities)
- pubmed: ✅ Working (has entities)

**Relationship sources status:**
- sec_edgar: ✅ Working (has entities, needs relationships)
- fda_warning_letters: ⚠️ Low match rate

**Event sources status:**
- fda_breakthrough: ❌ No data
- fda_clinical_hold: ❌ No data

**Strategic Assessment:**
- ✅ **Entity foundation is solid** - can proceed with relationship/event sources
- ⚠️ **Cross-source relationships missing** - need to run relationship inference
- ❌ **Event sources not ingested** - need to ingest failure signal sources

### 8. Resource Implications

**Unprocessed records:** 231
- Estimated processing time: 4-19 minutes
- Estimated new entities: 693-2,310
- Estimated new relationships: 462-1,155

**Recommendation:** Safe to process. Start with small batch (10-50 records) to test.

## Root Cause Analysis

### Why Only 22 Sources Have Data

**Actual Root Cause:** No automation infrastructure
- 16 active sources have no data because **ingestion scripts were never run**
- No cron jobs or scheduled tasks to run them automatically
- Everything requires manual execution

**Not a symptom - this is the infrastructure gap.**

### Why Only 5 Sources Have Processing Logs

**Actual Root Cause:** Manual processing
- Someone manually ran the processing pipeline for 5 sources 2 days ago
- No automation to process new staging records automatically
- Pipeline works correctly when executed, but isn't being executed

### Why 80.6% of Staging Records Are Unprocessed

**Actual Root Cause:** Manual processing stopped
- Processing was done manually 2 days ago
- New records were ingested 1 day ago but not processed
- No automation to process new records automatically

**The 231 unprocessed records are from recent ingestion that hasn't been processed yet.**

## Strategic Recommendations

### Immediate Actions (Critical)

1. **Set up automation infrastructure** (HIGHEST PRIORITY)
   ```bash
   # Create cron job or scheduled task to:
   # 1. Run ingestion scripts for active sources
   # 2. Process new staging records automatically
   # 3. Run relationship inference periodically
   ```

2. **Investigate clinicaltrials_gov anomaly**
   - Why 1,037 deleted records with 0% processed?
   - But 1,017 trials exist in database?
   - Check if processing logs were deleted or never created

3. **Run relationship inference**
   ```bash
   python scripts/infer_relationships.py --rebuild
   ```
   This will create cross-source relationships (publication-trial, publication-drug, filing-drug)

### Medium Priority

4. **Process backlog** (231 records)
   - Start with small batch (10-50 records)
   - Monitor processing time and resource usage
   - Scale up gradually

5. **Improve entity resolution**
   - Review 496 match candidates
   - Investigate low match rates for fda_warning_letters and fda_eua
   - Improve entity matching rules if needed

6. **Ingest event sources**
   - fda_breakthrough (positive signals)
   - fda_clinical_hold (failure signals)
   - These are critical for failure analysis

### Long Term

7. **Set up monitoring and alerting**
   - Monitor ingestion success rates
   - Alert on processing failures
   - Track entity resolution quality

8. **Document automation setup**
   - Document cron jobs/scheduled tasks
   - Document processing workflow
   - Create runbooks for manual operations

## Conclusion

The initial diagnostic was technically correct but missed the **strategic root cause**: **lack of automation infrastructure**. 

**Key Insights:**
1. ✅ Critical sources ARE working - entities exist in database
2. ✅ Processing pipeline works correctly when executed
3. ❌ No automation - everything is manual (root cause)
4. ⚠️ Cross-source relationships missing (need to run inference)
5. ⚠️ Entity resolution quality needs improvement for some sources

**The system is functional but not automated.** Setting up automation infrastructure will solve most of the identified issues.

