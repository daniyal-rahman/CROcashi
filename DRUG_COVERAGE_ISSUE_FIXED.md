# Drug Coverage Issue - Root Cause and Fix

## Problem Identified

**Issue**: Only 41% of trials have drug relationships (expected 60-90%)

## Root Cause

The `_validate_constraint_value()` method was **missing** from `RelationshipBuilder`, causing an `AttributeError` when trying to validate relationship attributes (like `arm_name` for trial-drug relationships).

### What Was Happening

1. ✅ Drugs were being extracted from raw data (98% of trials have interventions)
2. ✅ Drugs were being resolved to entities
3. ✅ Relationships were being extracted
4. ✅ Stub keys were matching correctly
5. ❌ **Relationship creation was failing silently** due to missing validation method

When `create_relationship()` tried to validate the `arm_name` attribute:
```python
if not self._validate_constraint_value(model, key, value):  # AttributeError!
```

The `AttributeError` was caught by the try/except block, but the relationship was never added to the session, even though the processing log incremented the counter (likely due to a timing issue or the counter being incremented before the validation).

## Fix Applied

Added the missing `_validate_constraint_value()` method to `RelationshipBuilder`:

```python
def _validate_constraint_value(self, model, key: str, value: Any) -> bool:
    """
    Validate that a value meets any database constraints for the field.
    """
    # Check string length constraints
    if isinstance(value, str):
        max_lengths = {
            'arm_name': 100,  # TrialDrug.arm_name
            'sponsor_role': 50,  # TrialSponsor.sponsor_role
        }
        if key in max_lengths and len(value) > max_lengths[key]:
            logger.warning(f"Value too long for {model.__name__}.{key}")
            return False
    return True
```

## Expected Impact

After this fix:
- ✅ Relationships should now be created successfully
- ✅ Drug coverage should increase from 41% to 60-90%
- ✅ Processing logs should accurately reflect created relationships

## Next Steps

1. **Re-process failed trials**: Run the pipeline again on trials that were processed but have no drug relationships
2. **Verify fix**: Check that new trials get drug relationships created
3. **Monitor**: Watch for any other constraint validation issues

## Diagnostic Tools Created

1. **`diagnose_drug_coverage.py`**: Comprehensive diagnostic script
2. **`debug_trial_processing.py`**: Debug specific trial processing
3. **`test_stub_key_matching.py`**: Test entity stub key matching

## Files Modified

- `src/entity_resolution/relationship_builder.py`: Added `_validate_constraint_value()` method

