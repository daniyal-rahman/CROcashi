# Database Triggers & Schema Fixes

## Overview

This document describes the fixes implemented for database triggers and schema issues identified in the code review.

## Issues Fixed

### 1. **Column Name Mismatch** ✅ FIXED
**Problem**: Documentation files referenced `extracted_json` instead of `extracted_jsonb`
**Solution**: Updated all documentation references to use correct column name `extracted_jsonb`

**Files Fixed**:
- `ncfd/docs/fixes_completion_report.md`
- `ncfd/docs/TODO_COMPLETION_PROOF.md`

### 2. **Safe JSONB Access** ✅ FIXED
**Problem**: Database triggers could crash on malformed JSONB data
**Solution**: Implemented robust JSONB access patterns with proper guards

**Key Improvements**:
```sql
-- Safe array access with type checking
IF jsonb_typeof(card->'results') = 'object' AND 
   jsonb_typeof(card->'results'->'primary') = 'array' THEN
  -- Safe to use jsonb_array_elements
END IF;

-- Robust integer parsing with regex fallback
BEGIN
  total_n := (card #>> '{sample_size,total_n}')::int;
EXCEPTION WHEN OTHERS THEN
  total_n := NULLIF(regexp_replace(
    COALESCE(card #>> '{sample_size,total_n}', '0'), 
    '[^0-9]', '', 'g'
  ), '')::int;
END;
```

### 3. **Staging Errors Table** ✅ IMPLEMENTED
**Problem**: No error sink for failed validations
**Solution**: Created comprehensive `staging_errors` table with proper indexing

**Table Structure**:
```sql
CREATE TABLE staging_errors(
  id BIGSERIAL PRIMARY KEY,
  trial_id BIGINT,
  study_id BIGINT,
  error_type TEXT,
  error_message TEXT,
  extracted_jsonb JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Performance indexes
CREATE INDEX ON staging_errors(created_at);
CREATE INDEX ON staging_errors(trial_id);
CREATE INDEX ON staging_errors(error_type);
```

### 4. **p_value Generated Column** ✅ IMPLEMENTED
**Problem**: No fast access to p-value data for hot lookups
**Solution**: Added computed column with index for performance

**Implementation**:
```sql
-- Generated column for p-value
ALTER TABLE studies 
ADD COLUMN p_value numeric 
GENERATED ALWAYS AS (
  (extracted_jsonb #>> '{results,primary,0,p_value}')::numeric
) STORED;

-- Partial index for non-null values
CREATE INDEX ON studies(p_value) WHERE p_value IS NOT NULL;
```

### 5. **Error Handling Strategy** ✅ IMPLEMENTED
**Problem**: Triggers would crash pipeline on validation failures
**Solution**: Changed from hard failures to warnings with error logging

**Before (Dangerous)**:
```sql
RAISE EXCEPTION 'PivotalStudyMissingFields: %', error_msg;
```

**After (Safe)**:
```sql
-- Log error to staging_errors table
INSERT INTO staging_errors (trial_id, error_type, error_message, extracted_jsonb)
VALUES (NEW.trial_id, 'pivotal_validation', error_msg, NEW.extracted_jsonb);

-- Raise warning instead of exception
RAISE WARNING '%', error_msg;

-- Allow insert to proceed for manual review
RETURN NEW;
```

## Migration Files

### `20250123_add_p_value_generated_column.sql`
- Adds `p_value` generated column to `studies` table
- Creates partial index on `p_value`
- Improves `staging_errors` table structure
- Adds proper documentation comments

## Model Updates

### `Study` Model (`ncfd/src/ncfd/db/models.py`)
```python
class Study(Base):
    # ... existing fields ...
    p_value: Mapped[Optional[float]] = mapped_column(
        Numeric, 
        computed="(extracted_jsonb #>> '{results,primary,0,p_value}')::numeric", 
        stored=True
    )
```

## Testing

### Test Script: `ncfd/scripts/test_db_triggers_and_schema.py`
Comprehensive test suite that verifies:
1. ✅ `staging_errors` table structure and indexes
2. ✅ `p_value` generated column functionality
3. ✅ Trigger function safety patterns
4. ✅ Error logging behavior
5. ✅ Malformed data handling

**Run Tests**:
```bash
cd ncfd
python scripts/test_db_triggers_and_schema.py
```

## Performance Benefits

### 1. **Faster p-value Queries**
- Generated column eliminates JSONB parsing overhead
- Partial index provides fast access to non-null values
- Enables efficient statistical analysis queries

### 2. **Robust Error Handling**
- No more pipeline crashes on malformed data
- Errors logged for manual review and debugging
- Maintains data integrity while allowing graceful degradation

### 3. **Safe JSONB Operations**
- Type checking prevents crashes on null paths
- Regex fallback handles string-to-number conversions
- Comprehensive validation without system failures

## Best Practices Implemented

### 1. **Guardrails vs. Blocking**
- Triggers provide validation warnings, not hard stops
- Application layer handles business logic decisions
- Database maintains data quality without blocking operations

### 2. **Error Sink Pattern**
- Centralized error logging for monitoring
- Structured error data for analysis
- Audit trail for validation failures

### 3. **Generated Columns**
- Computed values stored for performance
- Automatic updates when source data changes
- Indexable for fast queries

## Verification Commands

### Check Migration Status
```bash
cd ncfd
alembic current
alembic history
```

### Verify Table Structure
```sql
-- Check p_value column
\d+ studies

-- Check staging_errors table
\d+ staging_errors

-- Verify indexes
\di+ *staging_errors*
\di+ *studies*
```

### Test Trigger Function
```sql
-- Check function definition
SELECT pg_get_functiondef(oid) 
FROM pg_proc 
WHERE proname = 'enforce_pivotal_study_card';
```

## Summary

All identified database triggers and schema issues have been resolved:

- ✅ **Column naming**: `extracted_jsonb` used consistently
- ✅ **Safe JSONB access**: Robust guards and error handling
- ✅ **Error logging**: `staging_errors` table with proper indexing
- ✅ **Performance**: `p_value` generated column with index
- ✅ **Stability**: Warnings instead of crashes, graceful degradation

The system now provides robust validation while maintaining pipeline stability and performance.
