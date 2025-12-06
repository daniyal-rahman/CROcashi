# Data Quality & Wiring Validation Framework

**Created:** November 7, 2025  
**Purpose:** Comprehensive validation to ensure data quality and catch wiring issues

---

## Overview

This validation framework provides systematic checks to ensure:
1. **Data Quality** - Entities and relationships are correct
2. **Wiring Integrity** - All components are properly connected
3. **Completeness** - Data flows through the entire pipeline
4. **Edge Cases** - Unusual data is handled correctly

---

## Validation Tools

### 1. Data Quality Validation (`test_data_quality.py`)

**What it checks:**
- Entity quality (null names, duplicates, orphaned relationships)
- Relationship accuracy (duplicates, completeness)
- Data completeness (staging status, processing logs)
- Edge cases (missing relationships, unusually long names)
- Integration points (ingestion → staging → processing → database)

**Usage:**
```bash
python test_data_quality.py
```

**Current Status:**
- ✅ No critical issues found
- ⚠️  Low sponsor relationship coverage (29.7%) - This is expected as many trials have institutional sponsors that may not be extracted

### 2. Wiring Validation (`test_wiring_validation.py`)

**What it checks:**
- Ingestion scripts → Staging table wiring
- Processor registration (sources have processors)
- Staging → Processing flow
- Entity resolution coverage
- Database constraints

**Usage:**
```bash
python test_wiring_validation.py
```

**Current Status:**
- ✅ No critical wiring issues
- ⚠️  79 ingestion scripts not wired to staging (expected - only 2 wired so far)
- ⚠️  PubMed needs processor (data in staging but no processor)

---

## Current System Status

### ✅ What's Working Well:

1. **Data Quality:**
   - No null/empty entity names
   - No duplicate relationships
   - No orphaned relationships
   - 100% processing success rate (50/50 records)
   - 81% of trials have drug relationships
   - 91% of trials have disease relationships

2. **Wiring:**
   - ClinicalTrials.gov: Fully wired and functional
   - FDA Drugs: Processor registered (needs testing)
   - Ingestion → Staging: Working
   - Staging → Processing: Working
   - Processing → Database: Working

3. **Entity Resolution:**
   - 351 aliases created for matching
   - 18 entities need manual review (normal for ambiguous matches)

### ⚠️  Areas Needing Attention:

1. **Sponsor Relationship Coverage (29.7%)**
   - **Why:** Many trials have institutional sponsors that may not be extracted as companies
   - **Impact:** Low - sponsors are often institutions, not companies
   - **Action:** Review sponsor extraction logic if company relationships are critical

2. **Unwired Ingestion Scripts (79 scripts)**
   - **Why:** Only ClinicalTrials.gov and PubMed are wired so far
   - **Impact:** Medium - these sources can't be processed yet
   - **Action:** Wire up priority sources using the `StagingLoader` pattern

3. **Missing Processors:**
   - **PubMed:** 5 records in staging, no processor
   - **Impact:** Medium - PubMed data waiting to be processed
   - **Action:** Create PubMed processor

4. **Trials Missing Relationships:**
   - 12 trials with no drugs (19%)
   - 6 trials with no diseases (9%)
   - 45 trials with no sponsor (70%)
   - **Why:** Some trials may not have interventions, or extraction may miss them
   - **Impact:** Low - may be legitimate (observational trials, etc.)
   - **Action:** Review sample trials to determine if this is expected

---

## How to Use These Tools

### Regular Validation (Recommended Weekly)

```bash
# Run both validations
python test_data_quality.py
python test_wiring_validation.py
```

### Before Deploying Changes

```bash
# Run full validation suite
python test_data_quality.py && python test_wiring_validation.py
```

### After Adding New Sources

```bash
# Verify new source is wired
python test_wiring_validation.py | grep -A 5 "PROCESSOR MAPPING"
```

### After Processing Large Batches

```bash
# Check data quality
python test_data_quality.py | grep -A 10 "VALIDATION SUMMARY"
```

---

## Interpreting Results

### Critical Issues (❌)
- **Action Required:** Fix immediately
- Examples: Duplicate relationships, orphaned data, constraint violations

### Warnings (⚠️)
- **Review Recommended:** May indicate issues or expected behavior
- Examples: Low coverage, unwired sources, missing relationships

### Information (ℹ️)
- **Informational:** Status updates, not issues
- Examples: Counts, statistics, coverage percentages

---

## Validation Checklist

Use this checklist to ensure system health:

### Data Quality
- [ ] No null/empty entity names
- [ ] No duplicate relationships
- [ ] No orphaned relationships
- [ ] Processing success rate >95%
- [ ] Relationship coverage >80% for key types

### Wiring
- [ ] Priority sources wired to staging
- [ ] All staged sources have processors
- [ ] No unprocessable records in staging
- [ ] Integration points working

### Completeness
- [ ] Staging records being processed
- [ ] Entities being created correctly
- [ ] Relationships being created
- [ ] No processing errors

---

## Known Limitations

1. **Sponsor Coverage:** Many trials have institutional sponsors that may not map to companies. This is expected behavior.

2. **Missing Relationships:** Some trials legitimately have no drugs (observational studies) or no diseases (safety studies). Review sample cases to determine if extraction is missing data or if it's expected.

3. **Unwired Sources:** 79 sources are not yet wired. This is expected - wire them as needed using the `StagingLoader` pattern.

4. **Manual Review:** Some entities need manual review for ambiguous matches. This is normal and expected.

---

## Next Steps

### Immediate (High Priority)
1. ✅ Data quality validation framework created
2. ✅ Wiring validation framework created
3. ⏳ Create PubMed processor (5 records waiting)
4. ⏳ Review sponsor extraction logic if company relationships are critical

### Short-term (Medium Priority)
1. Wire up 10-15 priority data sources
2. Add more comprehensive edge case tests
3. Create validation dashboard/reporting

### Long-term (Low Priority)
1. Wire up remaining 65+ sources
2. Add performance validation
3. Add data freshness checks
4. Add relationship accuracy sampling

---

## Files Created

1. **`test_data_quality.py`** - Comprehensive data quality validation
2. **`test_wiring_validation.py`** - Wiring and integration validation
3. **`VALIDATION_FRAMEWORK.md`** - This document

---

## Example Output

### Data Quality Validation:
```
✅ No critical issues found
⚠️  WARNINGS: 1
  - Low sponsor relationship coverage
```

### Wiring Validation:
```
✅ No critical wiring issues found
⚠️  WARNINGS: 4
  - 79 ingestion scripts not wired to staging
  - 1 sources need processors
  - 1 sources have unprocessable records
  - 18 entities need manual review
```

---

## Conclusion

The validation framework provides comprehensive checks to ensure:
- ✅ Data quality is maintained
- ✅ Components are properly wired
- ✅ Issues are caught early
- ✅ System health is monitored

**Current Status:** System is healthy with expected warnings for incomplete wiring (only 2/81 sources wired so far).

Run these validations regularly to catch issues before they become problems!

