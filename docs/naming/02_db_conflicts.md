# DB Naming Conflicts

## Summary
- total_tables: 35
- issues_found: 4 (2 completed)

## Issues

| object | type | where | observed | expected | source |
|--------|------|-------|----------|----------|--------|
| `doc_id` | COLUMN | `study_cards` table | `doc_id` | **Keep as `doc_id`** | Codebase standard, avoid churn |
| `doc_id` | COLUMN | `factsheets` table | `doc_id` | **Keep as `doc_id`** | Codebase standard, avoid churn |
| `id` | COLUMN | `study_cards` table | `id` | **Keep as `id`** | Safer pattern, avoid widespread changes |
| `id` | COLUMN | `factsheets` table | `id` | **Keep as `id`** | Safer pattern, avoid widespread changes |
| `ondelete` behavior | CONSTRAINT | `company_aliases.company_id` | ~~`null`~~ | ✅ **COMPLETED** | CASCADE constraint added via migration |
| `Base` class | MODEL | ~~`study_card_models.py`~~ | ~~Separate `Base`~~ | ✅ **COMPLETED** | Study card models consolidated into main models.py |

## Suggested Remediations

### High Priority (Model Consolidation)

1. **Consolidate Study Card Models**
   - Move `StudyCard` and `Factsheet` classes from `src/ncfd/db/study_card_models.py` to `src/ncfd/db/models.py`
   - Use the main `Base` class instead of separate `declarative_base()`
   - **Rationale**: Maintains single source of truth for database models

### Medium Priority (Referential Integrity)

2. **Fix Company Alias Cascade Behavior**
   - Change `company_aliases.company_id` ondelete from `null` to `CASCADE`
   - **Rationale**: Aliases should be deleted when company is deleted (dependent data)

### Low Priority (Documentation)

3. **Add Missing Foreign Key Constraints**
   - Add explicit foreign key constraint for `study_cards.doc_id` → `documents.doc_id`
   - Add explicit foreign key constraint for `factsheets.doc_id` → `documents.doc_id`
   - **Rationale**: Ensures referential integrity and proper cascade behavior

### Recommended Naming Rule (Rule A - Safer)

**Primary Keys**: Use `id` for all tables (current pattern)  
**Foreign Keys**: Use `<ref_table>_id` pattern (current pattern)  
**Rationale**: Avoids widespread churn across codebase. The current pattern is consistent and well-established.

## Impact Analysis

### Database Schema Changes Required
- **Migration**: Create new migration to rename columns and add constraints
- **Downtime**: Minimal (column renames with data preservation)
- **Rollback**: Straightforward (reverse column renames)

### Code Changes Required
- **Model Updates**: Update SQLAlchemy model definitions
- **Query Updates**: Update any queries referencing old column names
- **Test Updates**: Update test fixtures and assertions
- **Documentation**: Update API documentation if applicable

### Risk Assessment
- **Low Risk**: Column renames are safe with proper migration
- **Medium Risk**: Foreign key constraint additions may fail if data is inconsistent
- **Mitigation**: Validate data integrity before applying constraints

## Implementation Plan

### Phase 1: Model Consolidation
1. Move study card models to main `models.py`
2. Update imports across codebase
3. Remove `study_card_models.py` file

### Phase 2: Schema Updates
1. Create migration to rename primary keys
2. Create migration to rename foreign keys
3. Create migration to add foreign key constraints
4. Create migration to fix cascade behavior

### Phase 3: Code Updates
1. Update all references to old column names
2. Update test fixtures and assertions
3. Update documentation

### Phase 4: Validation
1. Run comprehensive tests
2. Validate data integrity
3. Performance testing

## Notes

- **Enum Consistency**: All enums follow `PascalCase` naming consistently
- **Table Plurality**: All tables are properly pluralized
- **Column Naming**: All columns follow `snake_case` consistently
- **Timestamp Pattern**: All tables use `created_at`/`updated_at` consistently
- **Index Naming**: All indexes follow `idx_<table>_<column>` pattern consistently

The database schema demonstrates excellent naming consistency overall, with only minor issues in the study card models that need consolidation and standardization.
