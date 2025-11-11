# LLM Issues and Short-Sighted Patterns Found

## Critical Issues

### 1. ⚠️ **WARN Processor Creates Events in extract_relationships**
**Location**: `src/processors/warn_notices_processor.py:92-134`

**Issue**: Creating Event entities directly in `extract_relationships()` breaks the separation of concerns. Other processors only return RelationshipExtraction objects here.

**Pattern in codebase**: 
- RegulatoryEvents are created as entities first, then converted to Events by the pipeline
- Events are typically created by the pipeline, not processors

**Fix Options**:
1. **Option A (Recommended)**: Create a special entity type for WARN notices that gets converted to Event by pipeline
2. **Option B**: Keep current approach but document it as intentional deviation
3. **Option C**: Move Event creation to pipeline after relationships are created

**Current Status**: Works but inconsistent with architecture

---

### 2. ⚠️ **Date Fallbacks Using Current Date**
**Locations**: 
- `src/processors/fda_warning_letters_processor.py:231`
- `src/processors/warn_notices_processor.py:104`

**Issue**: Using `datetime.now().date()` as fallback when date parsing fails. SEC processor returns `None` if date can't be parsed (which prevents entity creation).

**Pattern in codebase**: 
- `sec_filings_processor.py:222-224` returns `None` if filing_date can't be parsed
- However, `event_date` in RegulatoryEvent is `nullable=False`, so fallback might be necessary

**Fix**: 
- For RegulatoryEvent: Fallback is acceptable (required field)
- For Event: Fallback is acceptable (required field)
- But should log warning when using fallback

**Current Status**: Works but should add warning logs

---

### 3. ⚠️ **Not Using Base Processor Date Helper**
**Locations**: All three processors

**Issue**: Created custom `_parse_warning_letter_date()`, `_parse_warn_date()`, `_parse_date()` methods instead of using `BaseProcessor.extract_date_from_raw()`.

**Pattern in codebase**: 
- `base_processor.py:114-144` has `extract_date_from_raw()` method
- Other processors use this method (e.g., `patentsview_processor.py:135`)

**Fix**: Should use `self.extract_date_from_raw(raw_data, 'issue_date')` instead of custom methods

**Current Status**: Code duplication, should refactor

---

## Medium Priority Issues

### 4. ⚠️ **Missing Type Validation**
**Locations**: All processors

**Issue**: Not checking if `raw_data.get()` returns expected types before using them.

**Example**:
```python
# Current (assumes list):
drugs_mentioned = raw_data.get('drugs_mentioned', [])
if isinstance(drugs_mentioned, str):
    drugs_mentioned = [drugs_mentioned]

# Missing: What if it's a dict? Or None?
```

**Pattern in codebase**: 
- `pubmed_processor.py:191-192` checks `isinstance(title, list)` before processing
- `openfda_processor.py:330-340` has extensive type checking

**Fix**: Add type checks for all `raw_data.get()` calls

**Current Status**: May fail on unexpected data formats

---

### 5. ⚠️ **Abstract ID Extraction Fragility**
**Location**: `src/processors/asco_abstracts_processor.py:200`

**Issue**: 
```python
'abstract_number': abstract_id.split('-')[-1] if '-' in abstract_id else abstract_id
```

This assumes abstract_id format is `"ASCO-2024-12345"`. If format changes, this breaks.

**Fix**: Use regex or more robust parsing, or store full abstract_id

**Current Status**: Fragile, may break on format changes

---

### 6. ⚠️ **Hardcoded Source Type**
**Location**: `src/processors/warn_notices_processor.py:109`

**Issue**: 
```python
source_type='financial'  # WARN notices are financial signals
```

Hardcoded string instead of using pipeline's `_get_source_type()` method.

**Pattern in codebase**: Pipeline has `_get_source_type()` that maps source names to types

**Fix**: Should get source type from pipeline or use constant

**Current Status**: Works but inconsistent

---

### 7. ⚠️ **Missing Validation for Required Fields**
**Locations**: All processors

**Issue**: Not validating that required fields exist before creating entities.

**Example**: 
- `fda_warning_letters_processor.py:218` checks `if not letter_id: return None` ✅ Good
- But `warn_notices_processor.py` doesn't validate `notice_id` before creating Event

**Pattern in codebase**: 
- `sec_filings_processor.py:201-203` validates `accession_number` before proceeding
- `patentsview_processor.py:128-132` validates `patent_number` before proceeding

**Fix**: Add validation for all required identifiers

**Current Status**: May create entities with missing required fields

---

## Low Priority Issues (Code Quality)

### 8. ⚠️ **Code Duplication: Date Parsing**
**Locations**: All three processors

**Issue**: Three nearly identical date parsing methods with same logic.

**Fix**: Use `BaseProcessor.extract_date_from_raw()` or create shared utility

**Current Status**: Code duplication

---

### 9. ⚠️ **Code Duplication: Drug Name Loading**
**Locations**: 
- `src/processors/fda_warning_letters_processor.py:289-325`
- `src/processors/asco_abstracts_processor.py:362-398`

**Issue**: Identical `_get_all_drug_names()` method in two processors.

**Fix**: Move to `BaseProcessor` as shared method

**Current Status**: Code duplication

---

### 10. ⚠️ **Magic Numbers**
**Locations**: All ingestion files

**Issue**: Hardcoded values like `[:200]`, `10000`, `[:50000]` without constants.

**Pattern in codebase**: `CODE_QUALITY_ISSUES_REPORT.md` documents this as an issue

**Fix**: Extract to constants

**Current Status**: Code quality issue, not functional

---

### 11. ⚠️ **Generic Exception Handling**
**Locations**: All processors

**Issue**: Using `except Exception as e:` which is too broad.

**Pattern in codebase**: `CODE_QUALITY_ISSUES_REPORT.md` documents this

**Fix**: Catch specific exceptions

**Current Status**: Code quality issue

---

## Summary

### Must Fix (Critical)
1. ✅ Event creation pattern (document or refactor)
2. ⚠️ Add warning logs for date fallbacks
3. ⚠️ Use base processor date helper
4. ⚠️ Add type validation

### Should Fix (Medium)
5. ⚠️ Fix abstract ID extraction
6. ⚠️ Use pipeline source type method
7. ⚠️ Add required field validation

### Nice to Fix (Low)
8. ⚠️ Remove code duplication
9. ⚠️ Extract magic numbers
10. ⚠️ Specific exception handling

---

## Recommended Fix Order

1. **Add type validation** (prevents runtime errors)
2. **Add required field validation** (prevents database errors)
3. **Use base processor date helper** (reduces duplication)
4. **Add warning logs for fallbacks** (improves observability)
5. **Fix abstract ID extraction** (prevents future breakage)
6. **Refactor Event creation** (architectural consistency)
7. **Remove code duplication** (maintainability)

