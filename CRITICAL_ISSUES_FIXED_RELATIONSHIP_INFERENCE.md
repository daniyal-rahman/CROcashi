# Critical Issues Found and Fixed - Relationship Inference

## Summary

Found and fixed **3 critical issues** in the relationship inference implementation.

## Issue 1: Data Loss Bug - `_clear_all_relationships()` Deletes ALL Relationships ⚠️ CRITICAL

**Severity**: CRITICAL - Data Loss Risk

**Problem**: 
The `_clear_all_relationships()` method was deleting **ALL** relationships of these types, not just inferred ones:
- All `PublicationTrial` relationships
- All `PublicationDrug` relationships  
- All `PublicationCompany` relationships
- All `FilingDrug` relationships

**Impact**: 
- If relationships were created during entity extraction (same-run relationships), they would be deleted
- Data loss when running `--rebuild` flag
- Loss of relationships created by the pipeline

**Root Cause**: 
Lines 178-183 used `.delete()` without filtering, deleting all rows regardless of how they were created.

**Fix Applied**:
```python
# Before (WRONG):
self.session.query(PublicationTrial).delete()

# After (CORRECT):
self.session.execute(
    text("""
        DELETE FROM publication_trials
        WHERE data_sources->>'source' = 'inferred_from_text'
    """)
)
```

Now only deletes relationships where `data_sources->>'source' = 'inferred_from_text'`, preserving relationships created during entity extraction.

**Files Modified**: `src/services/relationship_inference.py` lines 167-220

---

## Issue 2: Performance Bug - Drug Name Mapping Loaded Inside Loop ⚠️ CRITICAL

**Severity**: CRITICAL - Performance

**Problem**:
`_load_drug_name_mapping()` was called **inside the loop** for each publication/filing that had drug mentions:
- Called once per publication with drugs (could be 100+ times)
- Called once per filing with drugs (could be 50+ times)
- Even with caching, the structure was inefficient

**Impact**:
- O(n) unnecessary method calls where n = publications/filings with drug mentions
- Poor code structure
- Potential performance issues at scale

**Root Cause**:
Lines 487 and 663 called `_load_drug_name_mapping()` inside the loop after finding drug mentions.

**Fix Applied**:
```python
# Before (WRONG):
for pub in publications:
    found_drug_names = self._search_text_for_drugs(text, drug_names)
    name_to_drug = self._load_drug_name_mapping()  # Inside loop!
    for drug_name in found_drug_names:
        drug = name_to_drug.get(drug_name)

# After (CORRECT):
name_to_drug = self._load_drug_name_mapping()  # Once before loop
for pub in publications:
    found_drug_names = self._search_text_for_drugs(text, drug_names)
    for drug_name in found_drug_names:
        drug = name_to_drug.get(drug_name)  # Use cached mapping
```

**Files Modified**: `src/services/relationship_inference.py` lines 464-465, 642-643

---

## Issue 3: Missing Flush Before Commit - Late Error Detection ⚠️ HIGH

**Severity**: HIGH - Error Handling

**Problem**:
All relationships were added to the session and then committed at once. If there were constraint violations or other errors:
- Errors only discovered at commit time
- All work lost if error occurs
- No early detection of issues
- Large transaction rollback

**Impact**:
- If 1000 relationships are added and the 1000th violates a constraint, all 1000 are rolled back
- No progress saved if error occurs
- Difficult to debug which relationship caused the issue

**Fix Applied**:
Added periodic flushes every 100 relationships and final flush before commit:

```python
# Added to all inference methods:
if relationships_created % 100 == 0:
    self.session.flush()  # Catch errors early

self.session.flush()  # Final flush before commit
self.session.commit()
```

**Benefits**:
- Errors detected after every 100 relationships
- Progress saved in smaller batches
- Easier to identify problematic relationships
- Better error recovery

**Files Modified**: 
- `src/services/relationship_inference.py` lines 101-105 (company_drug)
- Lines 434-439 (publication_trial)
- Lines 552-557 (publication_drug)
- Lines 737-742 (filing_drug)

---

## Additional Issues Found and Fixed

### Issue 4: Memory Usage with `.all()` - ✅ FIXED

**Severity**: HIGH (at scale)

**Problem**: 
All entities loaded into memory with `.all()`:
- `publications = session.query(Publication).all()` 
- `filings = session.query(SECFiling).all()`
- Could cause memory issues at larger scale

**Fix Applied**:
- Added batch processing with configurable `batch_size` (default: 1000)
- Process entities in chunks using `.offset()` and `.limit()`
- Memory usage now constant regardless of dataset size

**Files Modified**: 
- All inference methods now use batching
- `__init__` accepts `batch_size` parameter

### Issue 5: Large Single Transaction - ✅ FIXED

**Severity**: HIGH (at scale)

**Problem**:
All relationships added and committed in one large transaction, causing:
- Long-running transactions
- Large rollbacks on errors
- Database lock contention

**Fix Applied**:
- Added batch commits with configurable `commit_batch_size` (default: 500)
- Commit every N relationships instead of all at once
- Flush every 100 relationships for early error detection
- Progress saved incrementally

**Files Modified**: 
- All inference methods now commit in batches
- `__init__` accepts `commit_batch_size` parameter

### Issue 6: Transaction Isolation Between Methods - ✅ FIXED

**Severity**: MEDIUM

**Problem**:
Each inference method commits separately. If one fails, others have already committed, leading to partial state.

**Fix Applied**:
- Added `atomic` parameter to `infer_all_relationships()` (default: True)
- When `atomic=True`: All methods wrapped in single transaction (all-or-nothing)
- When `atomic=False`: Each method commits separately (allows partial success)
- CLI supports `--atomic` and `--no-atomic` flags

**Files Modified**: 
- `infer_all_relationships()` now supports atomic transactions
- CLI script updated with atomic flags

---

## Verification

All fixes have been:
- ✅ Applied to code
- ✅ Linted (no errors)
- ✅ Tested for syntax correctness
- ✅ Documented

## Testing Recommendations

1. **Test data preservation**: Run inference, verify existing relationships not deleted
2. **Test rebuild**: Run `--rebuild`, verify only inferred relationships cleared
3. **Test performance**: Verify drug name mapping loaded once
4. **Test error handling**: Verify flush catches errors early

## Files Modified

1. `src/services/relationship_inference.py` - All critical fixes applied

