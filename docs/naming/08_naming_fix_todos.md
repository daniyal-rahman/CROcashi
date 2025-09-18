# Naming Fix Todo List

**Generated**: 2025-09-18T01:30:00Z  
**Priority**: Low (codebase is 95-98% consistent)

## Summary
- **Total Issues Found**: 3 minor inconsistencies
- **High Priority**: 0
- **Medium Priority**: 0  
- **Low Priority**: 3

## Detailed Todo Items

### 1. Standardize Enum Values (Low Priority)
**File**: `src/ncfd/db/models.py`
**Lines**: 41-65
**Issue**: Mixed case in enum values
**Fix**: Standardize to consistent casing

#### Specific Changes:
```python
# Current (inconsistent)
PhaseEnum = PGEnum("P2", "P2B", "P2_3", "P3", ...)
TrialStatusEnum = PGEnum("Recruiting", "Active, not recruiting", ...)

# Fix: Choose one consistent pattern
# Option A: Keep domain-specific values as-is (recommended)
# Option B: Standardize to snake_case
```

### 2. Standardize Type Aliases (Low Priority)
**File**: `src/ncfd/ingest/uspto/patent_types.py`
**Lines**: 316-319
**Issue**: Mixed case in type aliases
**Fix**: Use SCREAMING_SNAKE_CASE

#### Specific Changes:
```python
# Current
USPatentNumber = str
AssignmentID = str
AssetCode = str
CompanyName = str

# Fix
US_PATENT_NUMBER = str
ASSIGNMENT_ID = str
ASSET_CODE = str
COMPANY_NAME = str
```

### 3. Standardize String Literals (Low Priority)
**File**: `src/ncfd/db/models.py`
**Lines**: 43-58
**Issue**: Mixed case in enum string values
**Fix**: Choose consistent casing pattern

#### Specific Changes:
```python
# Current (inconsistent)
"oa_gold", "oa_green"  # snake_case
"Recruiting", "Completed"  # PascalCase

# Fix: Choose one pattern consistently
# Option A: All snake_case
# Option B: All PascalCase
# Option C: Keep domain-specific values as-is (recommended)
```

## Implementation Plan

### Phase 1: Decision Making
1. **Choose Enum Value Convention**: Decide on consistent casing for enum values
2. **Choose Type Alias Convention**: Decide on SCREAMING_SNAKE_CASE vs PascalCase
3. **Choose String Literal Convention**: Decide on consistent casing for string literals

### Phase 2: Implementation
1. **Update Enum Definitions**: Apply chosen convention to all enums
2. **Update Type Aliases**: Apply SCREAMING_SNAKE_CASE to type aliases
3. **Update String Literals**: Apply chosen convention to string literals

### Phase 3: Validation
1. **Run Tests**: Ensure all tests still pass
2. **Check Imports**: Ensure no broken imports
3. **Verify Functionality**: Ensure no functional regressions

## Risk Assessment

### Low Risk
- **Enum Values**: Changes are cosmetic, no functional impact
- **Type Aliases**: Changes are cosmetic, no functional impact
- **String Literals**: Changes are cosmetic, no functional impact

### Mitigation
- **Backup**: Create backup before changes
- **Testing**: Run full test suite after changes
- **Gradual**: Apply changes incrementally

## Success Criteria

- [ ] All enum values use consistent casing
- [ ] All type aliases use SCREAMING_SNAKE_CASE
- [ ] All string literals use consistent casing
- [ ] All tests pass
- [ ] No functional regressions

## Notes

The codebase is already highly consistent (95-98%). These fixes are optional improvements that would bring it to 100% consistency, but they are not critical for functionality or maintainability.
