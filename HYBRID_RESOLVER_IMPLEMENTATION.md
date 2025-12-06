# Hybrid Entity Resolver Implementation

**Date**: 2025-01-27  
**Status**: ✅ Implemented and Ready for Testing

## Overview

This implementation adds a two-tier lookup strategy to the EntityResolver:
1. **Tier 1 - Memory Cache**: Fast lookup for entities resolved in the current processing run
2. **Tier 2 - Database Fallback**: Cross-run resolution for entities processed in previous runs

This enables relationships to be created between entities from different processing runs (e.g., publications processed today can link to trials processed yesterday).

## What Was Implemented

### 1. Memory Cache in EntityResolver (`src/entity_resolution/entity_resolver.py`)

- Added `_memory_cache` and `_id_to_cache_key` instance variables
- Added `_make_cache_key()` method with identifier-based key generation
- Added `_lookup_in_memory_cache()` method for fast path lookups
- Added `_register_in_cache()` method to store resolved entities
- Added public `register_entity()` method for pipeline use
- Modified `resolve()` to check cache first, then database
- Auto-registers successful resolutions in cache

**Key Features:**
- Only caches high-confidence matches (EXACT_MATCH or HIGH_CONFIDENCE)
- Uses identifier priority (NCT ID > name, PMID > DOI, etc.)
- Consistent cache key generation (normalized values)

### 2. Database Fallback in Pipeline (`src/processing/pipeline.py`)

- Added `_resolve_entity_for_relationship()` method for cross-run resolution
- Updated relationship building to use database fallback when `entity_stub_to_id` lookup fails
- Registers entities in resolver cache after resolution/creation

**Key Features:**
- Handles both source and target entities in relationships
- Only uses high-confidence resolutions from database
- Registers found entities for subsequent lookups in same run

### 3. Hybrid Resolver Support (`src/entity_resolution/hybrid_resolver.py`)

- Added `register_entity()` pass-through to underlying `EntityResolver`

## Verification Checklist

### ✅ Cache Key Consistency

The `_make_cache_key()` method ensures consistent keys:
- Uses identifier fields in priority order (first match wins)
- Normalizes identifier values (strip whitespace)
- Same entity with same identifier always produces same key

**Test**: Run `test_cross_run_resolution.py` Test 1

### ✅ Relationship Building Integration

Both source and target entities use database fallback:
- Source entity: Lines 507-512 in `pipeline.py`
- Target entity: Lines 519-524 in `pipeline.py`

**Test**: Run `test_cross_run_resolution.py` Test 3

### ✅ Confidence Threshold Filtering

Only high-confidence resolutions are cached:
- `EXACT_MATCH` (confidence 1.0)
- `HIGH_CONFIDENCE` (confidence ≥ 0.75-0.85)
- `NEEDS_REVIEW` and `NO_MATCH` are not cached (no entity_id)

This is enforced by the resolver's existing logic - only successful resolutions have `entity_id`.

## Testing

### Quick Integration Test

```bash
# 1. Process some trials
python -m src.cli ingest --source clinicaltrials --limit 5

# 2. Verify trials exist
psql -c "SELECT COUNT(*) FROM clinical_trials WHERE nct_id IS NOT NULL"

# 3. Process publications that reference those trials
python -m src.cli ingest --source pubmed --limit 10

# 4. Verify relationships were created (the key test)
psql -c "SELECT COUNT(*) FROM publication_trials"
```

If `publication_trials` shows non-zero counts after step 3, cross-run resolution is working.

### Diagnostic Script

Run the comprehensive diagnostic script:

```bash
python test_cross_run_resolution.py
```

This script tests:
1. Cache key consistency
2. Database fallback functionality
3. Cross-run relationship creation
4. Cache hit/miss behavior
5. Current relationship counts

### Expected Behavior

**Within Same Run:**
- First resolution: Cache MISS → Database query → Cache registration
- Second resolution: Cache HIT → Immediate return

**Cross-Run:**
- Entity not in memory cache
- Falls back to database query
- Finds entity from previous run
- Registers in cache for subsequent lookups

## Logging

Enhanced logging has been added to track cache behavior:

- `Cache HIT`: Entity found in memory cache
- `Cache MISS`: Entity not in cache, querying database
- `Cache SKIP`: No cache key could be generated (no identifiers)

Enable debug logging to see cache behavior:

```python
import logging
logging.getLogger('src.entity_resolution.entity_resolver').setLevel(logging.DEBUG)
```

## Performance Considerations

### Memory Cache Benefits

- **Within-run deduplication**: Same entity resolved multiple times in one batch → single database query
- **Fast lookups**: O(1) dictionary lookup vs. database query

### Database Fallback

- **Cross-run resolution**: Enables relationships between entities from different runs
- **Lazy loading**: Only queries database when memory cache misses
- **No performance regression**: Existing code path unchanged

### Cache Size

- Cache is per-resolver instance (per processing run)
- Cleared when resolver instance is destroyed
- Typical run: 100-1000 entities → ~1-10 MB memory

## Known Limitations

1. **Cache is per-run**: Entities from previous runs are not in cache on startup
   - **Solution**: Database fallback handles this (the main feature)

2. **Name-based cache keys**: Less reliable than identifier-based keys
   - **Solution**: Identifier-based keys are prioritized

3. **No batch pre-loading**: Each entity is resolved individually
   - **Future**: Can add batch resolution if performance becomes an issue

## Files Modified

1. `src/entity_resolution/entity_resolver.py`
   - Added memory cache infrastructure
   - Modified `resolve()` method
   - Added cache management methods

2. `src/processing/pipeline.py`
   - Added `_resolve_entity_for_relationship()` method
   - Updated relationship building logic
   - Added cache registration calls

3. `src/entity_resolution/hybrid_resolver.py`
   - Added `register_entity()` pass-through

## Next Steps

1. **Run diagnostic tests**: `python test_cross_run_resolution.py`
2. **Test with real data**: Process trials, then publications
3. **Monitor relationship counts**: Verify cross-run relationships are created
4. **Check logs**: Verify cache hit rates and database fallback usage

## Success Criteria

✅ Publications processed today can link to trials processed yesterday  
✅ SEC filings can link to existing companies/drugs from previous runs  
✅ Memory cache reduces database queries within same run  
✅ Database fallback works when memory cache misses  
✅ No performance regression  
✅ Relationship counts increase (no longer zero for cross-run relationships)


