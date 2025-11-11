# Code Quality Issues Report

**Date:** Generated automatically  
**Purpose:** Identify magic numbers, hardcoded values, and other code quality issues across the repository

---

## 🔴 Category 1: Magic Numbers (Hardcoded Numeric Values)

### High Priority - Should be Constants

#### Time/Duration Values
1. **`src/services/company_risk_service.py`**
   - Line 151: `ttl=1800` (30 minutes cache) - should be `CACHE_TTL_METRICS = 1800`
   - Line 198: `365.25` (days per year) - should be `DAYS_PER_YEAR = 365.25`
   - Line 228: `timedelta(days=365)` (12 months) - should be `TWELVE_MONTHS_DAYS = 365`
   - Line 244: `90` (clustering period days) - should be `FAILURE_CLUSTERING_WINDOW_DAYS = 90`
   - Line 322: `timedelta(days=365)` (duplicate) - should use constant
   - Line 348: `730` (2 years) - should be `TWO_YEARS_DAYS = 730`
   - Line 350: `365` (1 year) - should be `ONE_YEAR_DAYS = 365`
   - Line 352: `180` (6 months) - should be `SIX_MONTHS_DAYS = 180`
   - Line 411: `ttl=3600` (1 hour cache) - should be `CACHE_TTL_RISK_SCORE = 3600`
   - Line 514: `ttl=900` (15 minutes cache) - should be `CACHE_TTL_TIMELINE = 900`

2. **`src/services/pattern_matcher.py`**
   - Line 218, 225, 238: `180` (default time window) - should be `DEFAULT_TIME_WINDOW_DAYS = 180`
   - Line 232: `7` (days per week) - should be `DAYS_PER_WEEK = 7`
   - Line 234: `30` (days per month) - should be `DAYS_PER_MONTH = 30`
   - Line 236: `365` (days per year) - should be `DAYS_PER_YEAR = 365`

3. **`src/services/failure_analysis_service.py`**
   - Line 245: `timedelta(days=365)` - should use constant
   - Line 256: `0.2` (risk score multiplier) - should be `RISK_SCORE_MULTIPLIER = 0.2`
   - Line 397, 401, 405: `1000` (query limit) - should be `MAX_ENTITIES_QUERY = 1000`

4. **`src/services/failure_tracker.py`**
   - Line 41, 307: `30` (default days) - should be `DEFAULT_DAYS = 30`

#### Confidence/Score Thresholds
5. **`src/entity_resolution/entity_resolver.py`**
   - Line 309: `0.3` (similarity threshold) - should be `MIN_SIMILARITY_THRESHOLD = 0.3`
   - Line 321: `10` (LIMIT for fuzzy matches) - should be `MAX_FUZZY_CANDIDATES = 10`
   - Line 358: `0.70` (fuzzy threshold) - should be `FUZZY_MATCH_THRESHOLD = 0.70`
   - Line 428: `0.70` (higher threshold) - should be `FUZZY_ALONE_THRESHOLD = 0.70`
   - Line 188, 215: `0.95` (exact match confidence) - should use `ConfidenceScorer.HIGH_CONFIDENCE_THRESHOLD`
   - Line 229, 252, 262, 270: `0.90` (alias confidence) - should use constant

6. **`src/entity_resolution/confidence_scorer.py`**
   - ✅ **GOOD**: Already has constants defined (lines 36-45)
   - However, some hardcoded values still exist in comments (lines 6-11)

#### Batch/Processing Limits
7. **`src/processing/pipeline.py`**
   - Line 66: `100` (default batch size) - should be `DEFAULT_BATCH_SIZE = 100`

8. **`scripts/volume_ingestion.py`**
   - Line 30: `1000` (default count) - should be `DEFAULT_CLINICALTRIALS_COUNT = 1000`
   - Line 58: `100` (page size) - should be `API_PAGE_SIZE = 100`
   - Line 92: `100` (FDA drugs count) - should be `DEFAULT_FDA_DRUGS_COUNT = 100`
   - Line 105: `500` (PubMed count) - should be `DEFAULT_PUBMED_COUNT = 500`
   - Line 227, 229: Hardcoded counts in function calls

#### String Truncation Limits
9. **`src/processors/sec_filings_processor.py`**
   - Line 344: `[:500]` (context truncation) - should be `MAX_CONTEXT_LENGTH = 500`
   - Line 387: `1000` (billion multiplier) - should be `BILLION_MULTIPLIER = 1000`
   - Line 528-529: `200` (context window) - should be `CONTEXT_WINDOW_CHARS = 200`
   - Line 637: `[:500]` (sentence truncation) - should use constant
   - Line 700-703: `200` (regex match limit) - should use constant

10. **`ingestion/california_warn.py`**
    - Line 48: `[:200]` (text truncation) - should be `MAX_TEXT_PREVIEW = 200`
    - Line 114: `< 200` (text length check) - should use constant
    - Line 122: `[:1000]` (text search limit) - should be `MAX_SEARCH_TEXT = 1000`
    - Line 200: `10000` (hash modulo) - should be `HASH_MODULO = 10000`

11. **`ingestion/fda_warning_letters.py`**
    - Line 46: `[:200]` (text truncation) - should use constant
    - Line 110: `< 200` (text length check) - should use constant
    - Line 129: `< 200` (name length check) - should use constant
    - Line 164: `10000` (hash modulo) - should use constant

12. **`ingestion/utils/staging_loader.py`**
    - Line 272: `10000` (hash modulo) - should be constant

#### HTTP Status Codes
13. **`src/api/routes/company_risk.py`**
    - Lines 55, 80, 128, 159, 288: `status_code=500` - should be `HTTP_500_INTERNAL_SERVER_ERROR = 500`
    - Lines 34, 42, 54, 65, 76, 87, 101: `200`, `404`, `500` in tests - should use constants

14. **`src/api/main.py`**
    - Line 76: `port=8000` - should be `DEFAULT_PORT = 8000` or from config
    - Line 69: `status_code=500` - should use constant

#### Risk Score Weights
15. **`src/services/company_risk_service.py`**
    - ✅ **GOOD**: Already has constants (lines 35-38)
    - However, hardcoded values in calculations:
      - Line 336: `30` (recent score max) - should use `RECENT_FAILURES_WEIGHT`
      - Line 338: `20` (recent score) - should be calculated constant
      - Line 340: `10` (recent score) - should be calculated constant
      - Line 360: `2` (warning score multiplier) - should be `WARNING_SCORE_MULTIPLIER = 2`

#### Percentage Calculations
16. **Multiple files** use hardcoded `100` for percentage calculations:
    - `diagnose_all_metrics.py`: Lines 41, 71, 90, 101, 122, 138, 191, 222
    - `reprocess_missing_sponsors.py`: Line 80
    - `reprocess_and_verify.py`: Line 95
    - Should use `PERCENTAGE_MULTIPLIER = 100` constant

---

## 🟡 Category 2: Hardcoded Strings and Configuration

### Source Names
1. **`src/processing/pipeline.py`**
   - Line 112, 360, 371: `'clinicaltrials_gov'` - should be `SOURCE_CLINICALTRIALS_GOV = 'clinicaltrials_gov'`
   - Multiple hardcoded source name checks throughout

2. **`src/entity_resolution/entity_resolver.py`**
   - Line 563: `'Company'` (model name string) - should use model class
   - Line 580: `'Drug'` (model name string) - should use model class

### Status Strings
3. **`src/services/company_risk_service.py`**
   - Line 109: `['ACTIVE', 'RECRUITING', 'ENROLLING_BY_INVITATION']` - should be constants
   - Line 113: `['TERMINATED', 'WITHDRAWN', 'SUSPENDED']` - should be constants
   - Line 168: `'COMPLETED'` - should be constant
   - Line 232: `['trial.status.terminated', 'trial.status.withdrawn', 'regulatory.clinical_hold']` - should be constants

4. **`src/processing/pipeline.py`**
   - Line 1092: `'completed'` - should be constant
   - Multiple status string comparisons throughout

### Error Messages
5. **Multiple files** have hardcoded error message strings that could be constants for consistency

### API Endpoints
6. **`src/api/main.py`**
   - Line 31: `version="1.0.0"` - should be from config or `__version__`

---

## 🟠 Category 3: Exception Handling Issues

### Bare Except Clauses
1. **`validate_structure.py:138`**
   ```python
   except:
   ```
   Should catch specific exceptions

2. **`ingestion/openfigi.py:51`**
   ```python
   except:
   ```
   Should catch specific exceptions

3. **`scripts/test_simple.py:82`**
   ```python
   except:
   ```
   Should catch specific exceptions

4. **`ingestion/ema_epar.py:24`**
   ```python
   except:
   ```
   Should catch specific exceptions

### Generic Exception Catching
5. **Multiple files** use `except Exception:` which is too broad:
   - `database/migrations/versions/e8f9a0b1c2d3_add_event_stream_lineage_soft_deletes.py:287`
   - `src/processors/pubmed_processor.py:362`
   - `database/config.py:58`
   - `ingestion/omim.py:42`
   - `ingestion/motley_fool.py:34`
   - `ingestion/seeking_alpha.py:34`
   - `ingestion/vaers.py:58`
   - `scripts/run_with_report.py:48-115` (multiple instances)
   - `ingestion/fda_faers.py:50`
   - `src/processing/pipeline.py:302` (and others)

   Should catch specific exception types (ValueError, KeyError, etc.)

---

## 🔵 Category 4: Code Duplication

### Repeated Patterns
1. **Hash Modulo Pattern**
   - `ingestion/california_warn.py:200`
   - `ingestion/fda_warning_letters.py:164`
   - `ingestion/utils/staging_loader.py:272`
   - All use `hash(...) % 10000` - should be a utility function

2. **Text Truncation Pattern**
   - Multiple files truncate text to 200 or 500 characters
   - Should use utility function: `truncate_text(text, max_length)`

3. **Status String Lists**
   - Multiple files define similar status lists
   - Should be centralized constants

4. **Cache Key Generation**
   - Pattern `f"{prefix}:{id}"` repeated
   - Should use utility function

5. **Percentage Calculation**
   - Pattern `(value / total * 100)` repeated
   - Should use utility function: `calculate_percentage(value, total)`

---

## 🟣 Category 5: Other Code Quality Issues

### Missing Type Hints
1. **Some functions** lack return type hints or parameter type hints
   - Check files for functions without complete type annotations

### Long Functions
2. **`src/processing/pipeline.py`**
   - `process_source()` method is very long (100+ lines)
   - `_resolve_entities()` method is very long
   - Should be broken into smaller functions

3. **`src/services/company_risk_service.py`**
   - `calculate_company_risk_score()` is long (130+ lines)
   - Should be broken into smaller methods

### Inconsistent Patterns
4. **Model Name String Comparisons**
   - `src/processing/pipeline.py` uses `model.__name__ == 'Company'`
   - Should use `isinstance()` or model class comparison

5. **Source Name Comparisons**
   - Multiple places compare `processor.SOURCE_NAME == 'clinicaltrials_gov'`
   - Should use constants or enum

### Magic Strings in Database Queries
6. **`src/entity_resolution/entity_resolver.py`**
   - Line 98: `'exact_match'` - should be constant
   - Line 401: `'fuzzy_match'` - should be constant

### Hardcoded Defaults
7. **`src/api/routes/company_risk.py`**
   - Line 133: `Query(30, ...)` - should use constant
   - Line 134: `Query(50, ...)` - should use constant
   - Line 168: `Query(50, ...)` - should use constant

---

## 📊 Summary Statistics

- **Magic Numbers Found**: ~80+ instances
- **Hardcoded Strings**: ~30+ instances
- **Bare Except Clauses**: 4 instances
- **Generic Exception Catching**: ~15+ instances
- **Code Duplication Patterns**: 5 major patterns

---

## ✅ Recommendations

### High Priority
1. Create a `constants.py` file with all magic numbers
2. Create a `exceptions.py` file with custom exceptions
3. Replace all bare `except:` clauses
4. Replace generic `except Exception:` with specific exceptions
5. Extract common patterns into utility functions

### Medium Priority
6. Add type hints to all functions
7. Break down long functions (>100 lines)
8. Use enums for status strings
9. Centralize configuration values

### Low Priority
10. Add docstrings where missing
11. Standardize error message format
12. Add unit tests for utility functions

---

## 📝 Example Refactoring

### Before:
```python
def calculate_risk(self, company_id):
    twelve_months_ago = date.today() - timedelta(days=365)
    if days_since_update > 365:
        score = 15
```

### After:
```python
from src.constants import TimeConstants, RiskScoreConstants

def calculate_risk(self, company_id: UUID) -> float:
    twelve_months_ago = date.today() - timedelta(days=TimeConstants.ONE_YEAR_DAYS)
    if days_since_update > TimeConstants.ONE_YEAR_DAYS:
        score = RiskScoreConstants.STAGNATION_ONE_YEAR_SCORE
```

