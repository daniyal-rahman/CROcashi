# Cross-Run Resolution Diagnosis

**Date**: 2025-11-27  
**Status**: ✅ Resolver Working, Issue Likely in Data Extraction

## Test Results

Ran `test_minimal_cross_run.py` which:
1. Processes one trial (creates trial entity in DB)
2. Processes one publication that references that trial by NCT ID
3. Checks if Publication-Trial relationship was created

**Result**: ✅ **TEST PASSED** - Cross-run resolution is working correctly!

## What the Logs Show

### Successful Flow

1. **Trial Processing** (Step 1):
   - Trial created with NCT ID `NCT12345678`
   - Trial entity stored in database

2. **Publication Processing** (Step 2 - Cross-Run):
   - Publication created with PMID `99999999`
   - Publication text contains NCT ID `NCT12345678`
   - Relationship extraction triggered

3. **Cross-Run Resolution** (The Key Part):
   ```
   [RELATIONSHIPS] Target entity not in pipeline cache, trying database fallback...
   [CROSS-RUN RESOLUTION] Attempting to resolve trial 'Test Trial for Cross-Run Resolution' with identifiers: {'nct_id': 'NCT12345678'}
   [CROSS-RUN RESOLUTION] Pipeline cache MISS for trial 'Test Trial for Cross-Run Resolution', trying resolver (database fallback)...
   [RESOLVER] Resolving trial: 'Test Trial for Cross-Run Resolution' with identifiers: {'nct_id': 'NCT12345678'}
   [RESOLVER] Memory cache MISS for trial 'Test Trial for Cross-Run Resolution', trying database queries...
   [RESOLVER] ✅ Level 1 SUCCESS: Exact identifier match found: d258cc29-6257-4b65-9a8b-d85fcfd12f09 (reasoning: Exact identifier match on nct_id=NCT12345678)
   [CROSS-RUN RESOLUTION] ✅ SUCCESS: Resolved trial 'Test Trial for Cross-Run Resolution' via database fallback -> d258cc29-6257-4b65-9a8b-d85fcfd12f09 (status: exact_match)
   ```

4. **Relationship Creation**:
   ```
   [RELATIONSHIPS] ✅ SUCCESS: Created publication_trial relationship between 3e92d99d-3923-47e1-994d-18d7b60bc2a0 and d258cc29-6257-4b65-9a8b-d85fcfd12f09
   ```

## Conclusion

**The hybrid resolver with database fallback is working correctly.**

The resolver:
- ✅ Detects when entities aren't in pipeline cache
- ✅ Triggers database fallback
- ✅ Finds entities from previous runs via exact identifier match
- ✅ Creates relationships successfully

## Why Real Data Might Still Show Zero Relationships

If cross-run relationships are still at zero in production, the issue is likely:

1. **NCT ID Extraction**: Publications might not be extracting NCT IDs from text
   - Check `pubmed_processor._extract_nct_ids()` 
   - Verify NCT IDs are actually in the publication text
   - Check if normalization is preventing matches

2. **Relationship Extraction**: `extract_relationships()` might not be creating relationship stubs
   - Check if `_extract_nct_ids()` is finding NCT IDs
   - Check if `_make_trial_entity_stub()` is creating proper entity stubs
   - Verify relationship extraction logic in `pubmed_processor.extract_relationships()`

3. **Data Quality**: Publications might not contain NCT IDs in searchable text
   - This was identified in previous investigation
   - Full text might not be stored or accessible
   - NCT IDs might be in fields not being searched

## Next Steps

1. **Verify NCT ID Extraction**: Run a diagnostic on actual publication data to see if NCT IDs are being extracted
2. **Check Relationship Extraction**: Verify `extract_relationships()` is being called and returning relationships
3. **Review Data Quality**: Check if publications actually contain NCT IDs in the fields being searched

## Diagnostic Logging Added

Comprehensive logging has been added to:
- `_resolve_entity_for_relationship()` - logs all cross-run resolution attempts
- `EntityResolver.resolve()` - logs all resolution strategies and results
- Relationship building section - logs relationship extraction and creation

All logs are prefixed with `[CROSS-RUN RESOLUTION]`, `[RESOLVER]`, or `[RELATIONSHIPS]` for easy filtering.


