# Duplicate Relationships Issue - RESOLVED ✅

**Date:** November 7, 2025  
**Status:** FIXED - 100% success rate achieved

---

## Problem Summary

ClinicalTrials.gov processing had a 50% failure rate due to:
1. **Duplicate resolved IDs** - Same drug extracted multiple times resolved to same UUID
2. **Index mapping bug** - Relationship extraction used wrong indices after filtering procedures

---

## Root Causes

### Issue 1: Duplicate Resolved Entity IDs

When a trial listed the same drug multiple times (e.g., "Pembrolizumab", "KEYTRUDA", "pembrolizumab"):
- All extracted as separate ExtractedEntity objects
- All resolved to the same database UUID
- Pipeline appended same UUID multiple times: `[uuid1, uuid1, uuid1]`
- Created 3 duplicate trial-drug relationships
- Database rejected with unique constraint violation

### Issue 2: Index Mapping Mismatch

When extraction filtered out procedures but relationship building used raw indices:
- Raw interventions: `[Drug, Procedure, Drug, Procedure, Drug]`
- After filtering: `[Drug, Drug, Drug]` at indices `[0, 1, 2]`
- Relationship extraction looped `i=0,1,2` and looked up `interventions[i]`
- `i=1` looked up `interventions[1]` = Procedure ❌ (should be second drug)
- Entity stubs didn't match, relationships failed

---

## Solution Implemented

### Fix 1: Deduplicate Resolved IDs in Pipeline

**File:** `src/processing/pipeline.py` lines 227-291

Added deduplication while tracking first extracted entity for each unique ID:

```python
seen_ids = set()  # Track IDs we've already added
id_to_entity = {}  # Map resolved IDs to first extracted entity

for extracted_entity in entity_list:
    resolved_id = resolve(extracted_entity)
    
    if resolved_id and resolved_id not in seen_ids:
        resolved_ids.append(resolved_id)
        seen_ids.add(resolved_id)
        id_to_entity[resolved_id] = extracted_entity  # Store for relationships
```

### Fix 2: Pass Entity Mapping to Relationship Extraction

**Files:**
- `src/entity_resolution/base_processor.py` - Updated signature
- `src/processing/pipeline.py` line 311 - Pass `id_to_entity`
- `src/processors/clinicaltrials_processor.py` - Refactored method
- `src/processors/fda_drugs_processor.py` - Updated signature

Changed relationship extraction to use actual extracted entities instead of raw data indices:

```python
def extract_relationships(
    raw_data, 
    resolved_entities, 
    id_to_entity  # NEW: Mapping of resolved IDs to entities
):
    # Use actual extracted entities, not indices
    for drug_id in resolved_entities.get('drugs', []):
        drug_entity = id_to_entity.get(drug_id)
        if drug_entity:
            relationships.append(
                create_relationship(trial_entity, drug_entity)
            )
```

**Benefits:**
- No index mapping needed
- Uses the actual extracted entity with correct name/context
- Automatically handles filtered items (procedures)

### Fix 3: Session-Level Deduplication

**File:** `src/entity_resolution/relationship_builder.py` lines 108-112, 163-187

Added check for relationships already in session (not yet committed):

```python
def _check_session_for_relationship(model, source_id, target_id):
    """Check if relationship exists in current session"""
    for obj in self.session.new:
        if isinstance(obj, model):
            if (obj.source_id == source_id and obj.target_id == target_id):
                return True
    return False
```

This prevents duplicate constraint violations when multiple identical relationships are created in same transaction.

---

## Test Results

### Before Fixes:
- Success rate: 50% (5/10 records)
- Duplicate relationship errors
- Index out of range errors
- Procedures treated as drugs

### After Fixes:
- **Success rate: 100% (50/50 records)**
- No duplicate relationship errors
- No index mapping errors
- Procedures properly filtered

### Comprehensive Test:

```
Fetching 50 trials from real-world data...
Processing 50 trials...

RESULTS:
Success: 50/50 (100.0%)
Failed: 0/50
Entities created: 128
Relationships: 128

✅ PASSED: >95% success rate achieved!
```

---

## Files Modified

1. **`src/processing/pipeline.py`**
   - Added `seen_ids` set for deduplication
   - Added `id_to_entity` mapping
   - Pass `id_to_entity` to `extract_relationships`

2. **`src/entity_resolution/base_processor.py`**
   - Updated `extract_relationships` signature with `id_to_entity` parameter

3. **`src/processors/clinicaltrials_processor.py`**
   - Refactored `extract_relationships` to use entity mapping
   - Added `_create_sponsor_relationship_from_entity` method
   - No longer uses raw data indices

4. **`src/processors/fda_drugs_processor.py`**
   - Updated `extract_relationships` signature to match base class

5. **`src/entity_resolution/relationship_builder.py`**
   - Added `_check_session_for_relationship` method
   - Check session before creating relationships

---

## Impact

**ClinicalTrials.gov Processing:**
- ✅ 50% → 100% success rate
- ✅ Handles duplicate drug names (brand/generic)
- ✅ Handles procedures mixed with drugs
- ✅ Proper relationship deduplication
- ✅ Correct entity-relationship mapping

**Overall System:**
- ✅ Now fully functional for ClinicalTrials.gov ingestion
- ✅ Framework in place for other processors
- ✅ Robust handling of real-world data

---

## Next Steps

The ClinicalTrials.gov processor is now 100% functional. Remaining work:

1. Create processors for other sources (PubMed, FDA, SEC)
2. Wire up remaining 75+ data sources
3. Add more comprehensive testing for edge cases
4. Performance optimization for large-scale ingestion

---

## Verification Commands

Test the fixes yourself:

```bash
# Test with 50 real-world trials
python -c "
from ingestion.clinicaltrials_gov import fetch_studies_sample
from src.processing.pipeline import ProcessingPipeline
from database.config import get_db_session
from database.models.staging import StagingRawData

# Clean slate
with get_db_session() as session:
    session.query(StagingRawData).filter_by(source_system='clinicaltrials_gov').delete()
    session.commit()

# Fetch and process
fetch_studies_sample(query_term='phase 3', page_size=50, load_to_staging=True)
pipeline = ProcessingPipeline()
stats = pipeline.process_source('clinicaltrials_gov', limit=50)

print(f'Success: {stats[\"records_processed\"]}/50')
print(f'Failed: {stats[\"records_failed\"]}/50')
"
```

Expected result: 50/50 success (100%)

---

**Status:** ✅ RESOLVED - All duplicate relationship issues fixed, 100% success rate achieved

