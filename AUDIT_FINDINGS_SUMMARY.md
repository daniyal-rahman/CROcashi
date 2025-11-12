# Comprehensive Repository Audit - Findings Summary

**Date:** 2025-01-27  
**Audit Script:** `comprehensive_repo_audit.py`

## Executive Summary

The audit reveals significant discrepancies between **claimed capabilities** and **actual implementation**. While the repository has 82 ingestion scripts and 37 active sources, many critical relationship tables are empty and many active sources have no data.

## Key Findings

### ✅ What's Actually Working

1. **Source Registration**: 82 ingestion scripts registered (all of them)
2. **Core Entity Extraction**: 
   - 1,017 clinical trials
   - 331 companies
   - 865 drugs
   - 1,479 diseases
   - 100 publications
   - 49 SEC filings
3. **Trial Relationships**: Working well
   - 1,748 trial-sponsor relationships
   - 1,228 trial-drug relationships
   - 2,085 trial-disease relationships

### 🚨 Critical Issues Found

#### 1. **Empty Relationship Tables** (HIGH PRIORITY)

Despite having data, these relationship tables are completely empty:

- **`publication_trials`**: 0 relationships (100 publications, 1,017 trials available)
- **`publication_drugs`**: 0 relationships (100 publications available)
- **`filing_drugs`**: 0 relationships (49 filings available)
- **`patents`**: 0 patents (entire table empty)
- **`patent_drugs`**: 0 relationships

**Impact**: Cross-source relationship inference is not working. Publications are not linked to trials or drugs, and filings don't extract drug mentions.

#### 2. **Active Sources with No Data** (16 sources)

These sources are marked as "active" but have no staging data or processing logs:

- `patentsview`
- `nsf_awards`
- `uspto_public_pair`
- `fda_breakthrough`
- `fierce_layoff_tracker`
- `who_ictrp`
- `federal_warn`
- `fda_orange_book`
- `fda_expanded_access`
- `fda_clinical_hold`
- `who_outbreak_news`
- `mhra_uk`
- `fda_purple_book`
- `vaers`
- `ich_guidelines`
- `tga_australia`

**Impact**: Claims of "30 sources being ingested" are misleading - only 22 sources actually have data, and only 5 have processing logs.

#### 3. **Low Processing Rate**

- **2,110 staging records** total
- **409 processed** (19.4%)
- **1,701 unprocessed** (80.6%)

**Impact**: Most ingested data is sitting in staging, not processed into entities/relationships.

#### 4. **Missing Processors**

Active sources without corresponding processors:
- `clinicaltrials_gov` (but has data - processor may be in different location)
- `sec_edgar` (but has data - processor may be in different location)
- `california_warn`

**Note**: Some sources may have processors with different naming conventions.

### 📊 Relationship Coverage Analysis

| Relationship Type | Count | Coverage | Expected | Status |
|------------------|-------|----------|----------|--------|
| Trial-Sponsor | 1,748 | 171.9% | 20-50% | ✅ Good (multiple sponsors per trial) |
| Trial-Drug | 1,228 | 120.7% | 60-90% | ✅ Good (multiple drugs per trial) |
| Trial-Disease | 2,085 | 205.0% | 70-95% | ✅ Good (multiple diseases per trial) |
| Publication-Trial | 0 | 0.0% | 5-20% | ❌ **CRITICAL: Not working** |
| Publication-Drug | 0 | 0.0% | 30-50% | ❌ **CRITICAL: Not working** |
| Filing-Drug | 0 | 0.0% | 15-30% | ❌ **CRITICAL: Not working** |

### 🔍 Data Quality Issues

**Good News**: No critical data quality issues found:
- ✅ No orphaned relationships
- ✅ No null entity names
- ✅ No duplicate relationships detected
- ✅ 0 failed processing logs

### 📈 Sources Breakdown

- **Total Ingestion Scripts**: 82
- **Registered Sources**: 82 (100%)
- **Active Sources**: 37 (45%)
- **Sources with Staging Data**: 22 (27%)
- **Sources with Processing Logs**: 5 (6%)

**Reality Check**: Only **5 sources** have actually been processed through the pipeline, despite 37 being marked as "active".

## Root Cause Analysis

### Why Relationship Tables Are Empty

1. **Publication-Trial Relationships**: 
   - Relationship inference engine exists (`src/services/relationship_inference.py`)
   - But inference has not been run (`scripts/infer_relationships.py` exists but may not have been executed)
   - Cross-run relationship resolution is deferred (see `fix-cross-run-relationship-resolution.plan.md`)

2. **Publication-Drug Relationships**:
   - Same issue - inference not run
   - Drug extraction from publication text may not be implemented in processors

3. **Filing-Drug Relationships**:
   - SEC filing processor may not extract drug mentions
   - Or extraction exists but relationships not created

### Why So Many Unprocessed Records

- **80.6% of staging records unprocessed** suggests:
  - Pipeline may have been run once, then new data added
  - Or processing pipeline has issues/bugs
  - Or processing is intentionally deferred

## Recommendations

### Immediate Actions (Critical)

1. **Run Relationship Inference**
   ```bash
   python scripts/infer_relationships.py --rebuild
   ```
   This should populate `publication_trials`, `publication_drugs`, and potentially `filing_drugs`.

2. **Process Staging Data**
   ```bash
   python -m src.processing.pipeline process_all --limit 1000
   ```
   Process the 1,701 unprocessed staging records.

3. **Fix Active Sources with No Data**
   - Either deactivate sources that don't work
   - Or fix ingestion scripts to actually fetch data
   - Or remove them from "active" status

### Medium Priority

4. **Verify Processor Implementation**
   - Check if `clinicaltrials_gov` and `sec_edgar` processors exist with different names
   - Implement missing processors for active sources

5. **Document Actual Status**
   - Update documentation to reflect that only 5 sources are actively processed
   - Not 30+ sources as might be claimed

### Long Term

6. **Implement Incremental Processing**
   - Set up automated processing of new staging records
   - Monitor processing success rates

7. **Add Relationship Extraction to Processors**
   - Ensure processors extract relationships during entity extraction
   - Not just rely on deferred inference

## Conclusion

The repository has a **solid foundation** with good entity extraction and trial relationships working well. However, there are **significant gaps**:

1. **Cross-source relationships are not being created** (publication-trial, publication-drug, filing-drug)
2. **Most data is unprocessed** (80.6% in staging)
3. **Many "active" sources have no data** (16 out of 37)

The good news is these are **fixable issues** - the infrastructure exists, it just needs to be executed. The relationship inference engine exists but hasn't been run, and the processing pipeline needs to be executed on the backlog of staging data.

**Verdict**: Not "LLM-generated green flags" - the code is real and working for core functionality. But there are **deep implementation gaps** where features exist but haven't been executed, and many sources are marked "active" but don't actually have data.


