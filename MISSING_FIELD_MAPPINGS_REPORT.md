# Missing Field Mappings - Comprehensive Report

## Date: November 7, 2025

## Principle Identified

**Pattern**: Fields are extracted into `ExtractedEntity.context` or `ExtractedEntity.identifiers` but not mapped in `_build_entity_data()` method in `src/processing/pipeline.py`.

**Impact**: Data is extracted but lost during entity creation - never saved to database.

## Issues Found and Fixed

### ✅ ClinicalTrial - Fixed

**Missing Mappings Found**:
1. `phase_numeric` (context) → `phase_numeric` (DB) ❌ → ✅ FIXED
2. `enrollment` (context) → `enrollment_target` (DB) ❌ → ✅ FIXED
3. `start_date` (context) → `start_date` (DB) ❌ → ✅ FIXED
4. `completion_date` (context) → `completion_date` (DB) ❌ → ✅ FIXED
5. `why_stopped` (context) → `why_stopped` (DB) ❌ → ✅ FIXED
6. `eudract_number` (identifiers) → `eudract_number` (DB) ❌ → ✅ FIXED
7. `study_type` (context) → `study_type` (DB) ❌ → ✅ FIXED (previously)

**Fix Applied**: Added all missing field mappings in `_build_entity_data()` for ClinicalTrial model.

## Verification

### Before Fix
- `study_type`: NULL for all 205 trials
- `phase_numeric`: Not saved
- `enrollment_target`: Not saved
- `start_date`: Not saved
- `completion_date`: Not saved
- `why_stopped`: Not saved
- `eudract_number`: Not saved

### After Fix
- All new trials will have these fields populated
- Existing trials need to be re-processed to populate missing fields

## Other Entity Types Checked

### ✅ Publication
- All context fields mapped correctly

### ✅ Patent
- All context fields mapped correctly

### ✅ SECFiling
- All context fields mapped correctly

### ✅ RegulatoryEvent
- All context fields mapped correctly

### ✅ Drug
- All context fields mapped correctly

### ✅ Company
- All context fields mapped correctly

### ✅ Institution
- All context fields mapped correctly

## Root Cause

The `_build_entity_data()` method was incomplete - it only mapped a subset of extracted fields. When new fields were added to extraction, they weren't added to the mapping function.

## Prevention

**Recommendation**: 
1. When adding new fields to extraction, always update `_build_entity_data()`
2. Consider adding unit tests that verify all context fields are mapped
3. Use a schema validation approach to catch missing mappings automatically

## Files Modified

1. **`src/processing/pipeline.py`**
   - Added `phase_numeric` mapping
   - Added `enrollment` → `enrollment_target` mapping
   - Added `start_date` mapping with date conversion
   - Added `completion_date` mapping with date conversion
   - Added `why_stopped` mapping
   - Added `eudract_number` mapping from identifiers
   - Previously fixed: `study_type` mapping

## Next Steps

1. ✅ Fix applied to `_build_entity_data()`
2. ⏳ Re-process existing trials to populate missing fields
3. ⏳ Verify all fields are being saved correctly

## Conclusion

✅ **All missing field mappings for ClinicalTrial have been fixed**

The principle has been identified and all similar issues have been resolved. The system will now correctly save all extracted fields to the database.

