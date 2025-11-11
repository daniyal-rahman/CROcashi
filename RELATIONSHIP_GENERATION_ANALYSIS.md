# Relationship Generation Analysis

**Date**: Current  
**Status**: Issues Identified - Fixes in Progress

---

## Current State Analysis

### 1. Company-Drug Relationships: **2 relationships** (Expected: 200+)

**Root Cause**: No inference logic implemented.

**Current Flow**:
- Trial sponsorships create `trial_sponsors` records (1,748 rows ✅)
- Trial-drug links create `trial_drugs` records (1,228 rows ✅)
- **BUT**: No code infers `company_drugs` from `trial_sponsors` + `trial_drugs`

**Evidence**:
- `SOURCE_CONFIGURATION_AUDIT.md` line 506: "Should infer: Company → Drug relationships from TrialSponsor + TrialDrug"
- No inference code found in codebase
- Only 2 direct relationships from FDA Drugs@FDA source

**Fix Required**: Add post-processing inference function

---

### 2. Publication Relationships: **0 relationships** (Expected: 50+)

**Root Cause**: Drug extraction returns empty list.

**Current Code** (`src/processors/pubmed_processor.py`):
```python
def _extract_drugs(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
    # ... placeholder code ...
    # Placeholder: return empty list for now
    # In production, this would use a drug name dictionary or NER model
    return drugs  # Always returns []
```

**Evidence**:
- Line 272: `return drugs` (empty list)
- `extract_relationships()` has logic to create publication-drug links (lines 153-166)
- But no drugs are extracted, so no relationships created

**Fix Required**: Implement drug name extraction from publication text

---

### 3. SEC Filing-Drug Relationships: **0 relationships** (Expected: 20+)

**Current Code**: Implementation exists but may not be working.

**Code Location**: `src/processors/sec_filings_processor.py`
- `_extract_drugs_text_search()` (line 316) - searches for drug names in text
- `extract_relationships()` (line 137) - creates filing-drug relationships
- `_get_all_drug_names()` (line 465) - loads drugs from database

**Potential Issues**:
1. Drug names cache may be empty if no drugs in database yet
2. Text search may not be matching properly
3. Relationships may be created but not persisted

**Fix Required**: Debug and verify the extraction logic

---

## Implementation Plan

### Fix 1: Company-Drug Inference (HIGH PRIORITY)

**Location**: Create new file `src/services/relationship_inference.py`

**Logic**:
```sql
INSERT INTO company_drugs (company_id, drug_id, relationship_type, confidence, source)
SELECT DISTINCT 
    ts.entity_id as company_id,
    td.drug_id,
    'developer' as relationship_type,
    0.9 as confidence,
    'inferred_from_trial' as source
FROM trial_sponsors ts 
JOIN trial_drugs td ON ts.trial_id = td.trial_id
WHERE ts.entity_type = 'company'
AND NOT EXISTS (
    SELECT 1 FROM company_drugs cd 
    WHERE cd.company_id = ts.entity_id 
    AND cd.drug_id = td.drug_id
)
```

**Expected Result**: 200+ company-drug relationships

---

### Fix 2: Publication-Drug Extraction (MEDIUM PRIORITY)

**Location**: `src/processors/pubmed_processor.py` - `_extract_drugs()` method

**Approach**:
1. Load all drug names from database (similar to SEC processor)
2. Search publication title/abstract for drug mentions
3. Use word boundaries to avoid partial matches
4. Return extracted drug entities

**Expected Result**: 30+ publication-drug relationships

---

### Fix 3: SEC Filing-Drug Verification (MEDIUM PRIORITY)

**Location**: `src/processors/sec_filings_processor.py`

**Actions**:
1. Verify `_get_all_drug_names()` is working
2. Check if drug names are being found in text
3. Verify relationships are being created
4. Add logging to debug issues

**Expected Result**: 15+ filing-drug relationships

---

## Verification Queries

After each fix, run these queries:

### After Fix 1 (Company-Drug Inference):
```sql
-- Should show 200+ rows
SELECT COUNT(*) FROM company_drugs WHERE relationship_type = 'developer';

-- Sample relationships
SELECT c.name, d.drug_name, cd.relationship_type
FROM company_drugs cd
JOIN companies c ON cd.company_id = c.company_id
JOIN drugs d ON cd.drug_id = d.drug_id
LIMIT 20;
```

### After Fix 2 (Publication-Drug):
```sql
-- Should show 30+ rows
SELECT COUNT(*) FROM publication_drugs;

-- Verify quality
SELECT p.title, d.drug_name
FROM publication_drugs pd
JOIN publications p ON pd.pub_id = p.pub_id
JOIN drugs d ON pd.drug_id = d.drug_id
LIMIT 10;
```

### After Fix 3 (SEC Filing-Drug):
```sql
-- Should show 15+ rows
SELECT COUNT(*) FROM filing_drugs;

-- Check for program discontinuation events
SELECT COUNT(*) FROM events WHERE event_type = 'program.discontinued';
```

---

## Next Steps

1. ✅ Implement company-drug inference
2. ✅ Fix publication-drug extraction
3. ✅ Verify SEC filing-drug extraction
4. ✅ Add post-processing hook to pipeline
5. ✅ Run verification queries
6. ✅ Test with real data


