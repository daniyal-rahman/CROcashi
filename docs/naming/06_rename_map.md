# NCFD Rename Plan

## Overview

This document outlines the minimal rename plan for the NCFD codebase to address naming conflicts and ensure consistency with established naming conventions.

## Summary

- **Total Changes**: 6 items
- **Database Changes**: 4 items (2 tables, 2 columns)
- **Code Changes**: 2 items (2 classes)
- **Impact Level**: Low (minimal breaking changes)

## Detailed Changes

### Database Changes

#### Table Consolidation
| Current Location | Table Name | New Location | Rationale |
|------------------|------------|--------------|-----------|
| `study_card_models.py:14` | `StudyCard` | `models.py` | Consolidate all database models in single file |
| `study_card_models.py:59` | `Factsheet` | `models.py` | Consolidate all database models in single file |

#### Column Renaming
| Table | Column | New Name | Rationale |
|-------|--------|----------|-----------|
| `StudyCard` | `doc_id` | `document_id` | Use consistent foreign key naming pattern |
| `Factsheet` | `doc_id` | `document_id` | Use consistent foreign key naming pattern |

### Code Changes

#### Class Renaming
| Current Name | New Name | Rationale |
|--------------|----------|-----------|
| `StudyCard` | `StudyCardModel` | Distinguish from main StudyCard class |
| `Factsheet` | `FactsheetModel` | Distinguish from main Factsheet class |

## Impact Analysis

### Database Impact

#### Foreign Key Dependencies
- **StudyCard.doc_id** → **documents.doc_id**
  - **Impact**: Low - only affects study card generation
  - **Migration**: Simple column rename with data preservation
  - **Testing**: Study card pipeline tests need updates

- **Factsheet.doc_id** → **documents.doc_id**
  - **Impact**: Low - only affects factsheet generation
  - **Migration**: Simple column rename with data preservation
  - **Testing**: Factsheet generation tests need updates

#### Index Dependencies
- **No indexes** depend on the renamed columns
- **No constraints** depend on the renamed columns
- **Migration complexity**: Low

### Code Impact

#### Caller Analysis
- **StudyCard class**: Used in study card pipeline
  - **Files affected**: `pipeline/study_card_pipeline.py`
  - **Impact**: Low - simple class name change
  - **Testing**: Study card tests need updates

- **Factsheet class**: Used in results processing
  - **Files affected**: `extract/generators/results_factsheet_generator.py`
  - **Impact**: Low - simple class name change
  - **Testing**: Factsheet tests need updates

#### Import Dependencies
- **No external imports** of these classes
- **Internal imports** in study card pipeline
- **Migration complexity**: Low

## Migration Strategy

### Phase 1: Database Migration
1. **Create Alembic migration** for table consolidation
2. **Rename columns** in existing tables
3. **Update foreign key references**
4. **Run migration** in test environment
5. **Validate data integrity**

### Phase 2: Code Migration
1. **Update class names** in model files
2. **Update imports** in dependent files
3. **Update tests** for renamed classes
4. **Run full test suite**
5. **Deploy to staging**

### Phase 3: Validation
1. **Run integration tests**
2. **Validate study card generation**
3. **Validate factsheet generation**
4. **Check data consistency**
5. **Deploy to production**

## Risk Assessment

### Low Risk Items
- **Column renames**: Simple database operations
- **Class renames**: Simple code changes
- **No external dependencies**: Internal-only changes

### Mitigation Strategies
- **Backup database** before migration
- **Run tests** in staging environment
- **Gradual rollout** with monitoring
- **Rollback plan** ready if issues arise

## Testing Requirements

### Database Tests
- **Migration tests**: Verify table consolidation
- **Data integrity tests**: Verify foreign key relationships
- **Performance tests**: Verify query performance

### Code Tests
- **Unit tests**: Update for renamed classes
- **Integration tests**: Verify study card pipeline
- **End-to-end tests**: Verify full workflow

## Timeline

### Week 1: Preparation
- Create Alembic migration
- Update test cases
- Prepare staging environment

### Week 2: Migration
- Run database migration
- Update code references
- Run full test suite

### Week 3: Validation
- Integration testing
- Performance validation
- Production deployment

## Success Criteria

- [ ] All tests pass after migration
- [ ] Study card generation works correctly
- [ ] Factsheet generation works correctly
- [ ] Database integrity maintained
- [ ] Performance not degraded
- [ ] No breaking changes for external users

## Rollback Plan

If issues arise during migration:

1. **Database rollback**: Restore from backup
2. **Code rollback**: Revert to previous version
3. **Test rollback**: Run previous test suite
4. **Investigate issues**: Identify root cause
5. **Plan remediation**: Address issues before retry

## Conclusion

This rename plan addresses the minimal naming conflicts in the NCFD codebase with low risk and minimal impact. The changes improve consistency and maintainability while preserving all existing functionality.
