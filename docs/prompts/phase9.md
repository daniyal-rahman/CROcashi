# Phase 9: Database Migration Fixes and Manual Migration Conversion

## Overview
Successfully fixed the broken Alembic migration chain and converted manually applied SQL migrations into idempotent Alembic versions. The database is now in a consistent state with `alembic upgrade head` working without errors.

## Issues Found and Fixed

### 1. Broken Migration Chain
- **Problem**: Migration files had mismatched revision IDs and down_revision references
- **Files affected**:
  - `20250122_fix_pivotal_study_card_trigger.py` - revision ID mismatch
  - `20250122_add_storage_reference_counting.py` - wrong down_revision
  - `20250123_add_p_value_generated_column.py` - wrong down_revision
  - `20250124_create_signals_gates_scores_tables.py` - wrong down_revision

### 2. Manual SQL Migrations Found
The following migrations were applied manually outside of Alembic and needed to be converted:

#### A. Storage System Migration
- **File**: `ncfd/migrations/20250123_add_storage_objects_and_references.sql`
- **Purpose**: Creates storage_objects and storage_references tables for content reference counting
- **Converted to**: `20250123_add_storage_objects_and_references.py`
- **Features**: 
  - Reference counting system
  - Storage tiering (local/s3)
  - Integration with documents and studies tables

#### B. Link Audit Fields Migration
- **File**: `ncfd/migrations/20250123_add_link_audit_fields.sql`
- **Purpose**: Adds precision validation fields to link_audit table
- **Converted to**: `20250123_add_link_audit_fields.py`
- **Features**:
  - Label, label_source, reviewed_by fields
  - Precision calculation views and functions
  - Auto-promotion validation

#### C. Company Securities Setup
- **Files**: `migrations/20250820_company_security_link_and_view.sql` and related
- **Purpose**: Links companies to securities and creates ticker views
- **Converted to**: `20250124_add_resolver_system_and_company_securities.py`
- **Features**:
  - company_securities linking table
  - v_company_tickers view
  - Adaptive schema detection

### 3. Resolver System Tables
- **Status**: Already exist in database with different schema than intended
- **Current schema**: Uses `nct_id` and `run_id` instead of `trial_id`
- **Action**: Skipped creation in migration (tables already exist)
- **Note**: These tables were created outside of Alembic and have a different purpose

## Migration Chain Fixed

### Before (Broken)
```
20250121_create_studies_table_and_guardrails (current)
├── 20250122_fix_pivotal_study_card_trigger (broken dependency)
├── 20250122_add_storage_refcounting (wrong down_revision)
├── 20250123_add_p_value_column (wrong down_revision)
└── 20250124_signals_gates_scores (wrong down_revision)
```

### After (Fixed)
```
20250121_create_studies_table_and_guardrails
├── 20250122_fix_pivotal_study_card_trigger
├── 20250122_add_storage_refcounting
├── 20250123_add_p_value_column
├── 20250123_add_storage_objects_and_references
├── 20250123_add_link_audit_fields
├── 20250124_signals_gates_scores
└── 20250124_add_resolver_system_and_company_securities (head)
```

## Key Improvements Made

### 1. Idempotent Operations
- All migrations use `IF NOT EXISTS` clauses
- Tables, indexes, and constraints are created safely
- Functions are created with `CREATE OR REPLACE`

### 2. Proper Error Handling
- Fixed column name conflicts (e.g., `reference_id` vs `referenced_id`)
- Fixed constraint references with proper quoting
- Separated index creation to avoid dependency issues

### 3. Schema Consistency
- Aligned Alembic migrations with manually applied schemas
- Preserved existing data and table structures
- Added missing columns and indexes safely

## Current Database State

### Migration Status
- **Current Version**: `20250124_add_resolver_system_and_company_securities`
- **Total Tables**: 44
- **Migration Chain**: Complete and consistent

### Tables Created/Modified
- ✅ `staging_errors` - Error logging for validation failures
- ✅ `storage_objects` - Content reference tracking
- ✅ `storage_references` - Reference counting system
- ✅ `signals` - Trial failure detection signals
- ✅ `gates` - Validation gates
- ✅ `scores` - Failure probability scores
- ✅ `company_securities` - Company-security linking
- ✅ `v_company_tickers` - Company ticker view

### Functions Created
- ✅ `increment_storage_refcount()` - Reference counting
- ✅ `decrement_storage_refcount()` - Reference cleanup
- ✅ `get_heuristic_precision()` - Precision calculation
- ✅ `can_auto_promote_heuristic()` - Auto-promotion validation

## Manual Migrations Converted

| Original SQL File | Alembic Migration | Purpose |
|-------------------|-------------------|---------|
| `20250123_add_storage_objects_and_references.sql` | `20250123_add_storage_objects_and_references.py` | Storage reference counting |
| `20250123_add_link_audit_fields.sql` | `20250123_add_link_audit_fields.py` | Link audit precision fields |
| `20250820_company_security_link_and_view.sql` | `20250124_add_resolver_system_and_company_securities.py` | Company securities linking |

## Testing and Verification

### ✅ Migration Chain
- `alembic current` - Shows correct version
- `alembic history` - Shows complete chain
- `alembic upgrade head` - Runs without errors

### ✅ Database Consistency
- All tables exist and are accessible
- Foreign key constraints are valid
- Indexes are properly created
- Functions are executable

### ✅ Idempotency
- Migrations can be run multiple times safely
- No duplicate table/column errors
- Graceful handling of existing objects

## Next Steps

### 1. Future Migrations
- All new schema changes should use Alembic
- No more manual SQL migrations
- Maintain idempotent operations

### 2. Schema Documentation
- Update models.py to reflect current schema
- Document resolver system table purposes
- Maintain migration history documentation

### 3. Testing
- Run full test suite to verify functionality
- Test migration rollback scenarios
- Verify data integrity after migrations

## Lessons Learned

1. **Migration Dependencies**: Always verify revision ID chains before committing
2. **Manual Migrations**: Convert to Alembic to maintain consistency
3. **Idempotency**: Use `IF NOT EXISTS` and `CREATE OR REPLACE` for safety
4. **Schema Drift**: Existing tables may have different schemas than expected
5. **Testing**: Always test migration chains before production deployment

## Conclusion

The database migration system is now fully functional and consistent. All manually applied migrations have been converted to idempotent Alembic versions, and the migration chain is properly structured. The system can now handle future schema changes through standard Alembic workflows.
