# Deep Review - LLM-Generated Code Issues

**Date:** November 7, 2025  
**Purpose:** Find hidden issues in LLM-generated code that looks good but isn't functional

---

## Critical Issues Found

### ❌ Issue #1: FDA Drugs Processor - Stub Entity Mismatch

**File:** `src/processors/fda_drugs_processor.py`

**Problem:** `_make_drug_entity` doesn't normalize the drug name, but `_extract_drug` does. This causes stub key mismatches.

**Location:**
- Line 291-301: `_make_drug_entity` returns unnormalized name
- Line 154-187: `_extract_drug` normalizes name

**Impact:** HIGH - Relationships will fail to match because stub keys won't match

**Fix Needed:**
```python
def _make_drug_entity(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
    brand_name = raw_data.get('brand_name', raw_data.get('TradeName', ''))
    # CRITICAL: Normalize to match original extraction
    brand_name = self.normalize_drug_name(brand_name) if brand_name else ''
    return ExtractedEntity(...)
```

---

### ⚠️  Issue #2: OpenFDA - "Unknown Drug" Fallback

**File:** `src/processors/openfda_processor.py`

**Problem:** Line 342 uses "Unknown Drug" as fallback when no name found.

**Location:** Line 342
```python
primary_name = brand_name if brand_name else generic_name or "Unknown Drug"
```

**Impact:** MEDIUM - Creates entities with "Unknown Drug" name which is not useful

**Fix Needed:** Return None instead of creating entity with "Unknown Drug"

---

### ⚠️  Issue #3: OpenFDA - Placeholder Indication Parsing

**File:** `src/processors/openfda_processor.py`

**Problem:** Line 290 has comment "This is a placeholder - real implementation would use NLP"

**Location:** Lines 279-322: `_parse_indication_text`

**Current Implementation:**
- Takes first sentence of indication text
- No actual disease name extraction
- Just uses raw text as disease name

**Impact:** MEDIUM - Creates low-quality disease entities from full indication text

**Example:**
- Input: "For the treatment of moderate to severe rheumatoid arthritis in adults"
- Output: Disease name = "For the treatment of moderate to severe rheumatoid arthritis in adults" (not ideal)

**Status:** Functional but low quality - works but creates noisy data

---

### ⚠️  Issue #4: FDA Drugs - Missing Normalization in Stub Entities

**File:** `src/processors/fda_drugs_processor.py`

**Problem:** Multiple `_make_*` functions don't normalize names to match original extraction

**Locations:**
- `_make_drug_entity` (line 291) - doesn't normalize
- `_make_company_entity` (line 303) - doesn't normalize
- `_make_indication_entity` (line 326) - doesn't normalize

**Impact:** HIGH - Stub keys won't match, relationships will fail

**Fix Needed:** All `_make_*` functions must normalize names exactly like extraction functions

---

### ⚠️  Issue #5: FDA Drugs - Relationship Extraction Uses Stubs Instead of id_to_entity

**File:** `src/processors/fda_drugs_processor.py`

**Problem:** Lines 102-111, 114-126, 128-136 create relationships using `_make_*` stubs instead of using `id_to_entity` map

**Current Code:**
```python
relationships.append(RelationshipExtraction(
    relationship_type='company_drug',
    source_entity=self._make_company_entity(raw_data),  # ❌ Creates new stub
    target_entity=self._make_drug_entity(raw_data),     # ❌ Creates new stub
    ...
))
```

**Should Be:**
```python
company_entity = id_to_entity.get(company_id)
drug_entity = id_to_entity.get(drug_id)
if company_entity and drug_entity:
    relationships.append(RelationshipExtraction(
        relationship_type='company_drug',
        source_entity=company_entity,  # ✅ Use actual extracted entity
        target_entity=drug_entity,      # ✅ Use actual extracted entity
        ...
    ))
```

**Impact:** CRITICAL - Relationships will fail because stub keys won't match resolved entities

---

### ⚠️  Issue #6: PatentsView - Missing Normalization in Stub Entities

**File:** `src/processors/patentsview_processor.py`

**Problem:** `_make_company_entity` doesn't normalize company name

**Location:** Line 235-244

**Impact:** MEDIUM - May cause stub key mismatches

---

## Verification Tests

### ✅ What Actually Works:

1. **Entity Extraction:** All processors extract real data from test inputs
2. **Data Parsing:** Date parsing, name extraction work correctly
3. **Normalization:** Base processor normalization functions work
4. **Validation:** Entity validation works

### ❌ What Has Issues:

1. **Stub Entity Creation:** Not normalized, won't match original entities
2. **Relationship Extraction:** Uses stubs instead of `id_to_entity` map
3. **Fallback Values:** "Unknown Drug" creates bad entities
4. **Indication Parsing:** Placeholder implementation creates noisy data

---

## Summary

### Critical Issues (Must Fix):
1. ✅ **FIXED** - FDA Drugs: Stub entities not normalized → relationship matching fails
2. ✅ **FIXED** - FDA Drugs: Relationship extraction uses stubs instead of `id_to_entity`

### High Priority (Should Fix):
3. ✅ **FIXED** - OpenFDA: "Unknown Drug" fallback → creates bad entities
4. ✅ **FIXED** - All processors: Stub entity normalization missing

### Medium Priority (Nice to Fix):
5. ⚠️  OpenFDA: Placeholder indication parsing → noisy disease names (functional but low quality)
6. ✅ **FIXED** - PatentsView: Stub entity normalization

## Fixes Applied

### ✅ Fix #1: FDA Drugs Relationship Extraction
- Changed from using `_make_*` stubs to using `id_to_entity` map
- Now correctly uses actual extracted entities for relationship matching

### ✅ Fix #2: FDA Drugs Stub Normalization
- Added normalization to `_make_drug_entity`
- Added normalization to `_make_company_entity`
- Added normalization to `_make_indication_entity`

### ✅ Fix #3: OpenFDA "Unknown Drug" Fix
- Changed to return `None` instead of creating entity with "Unknown Drug"
- Prevents bad entities from being created

### ✅ Fix #4: PatentsView Stub Normalization
- Added normalization to `_make_company_entity`

---

## Files That Need Fixes

1. **`src/processors/fda_drugs_processor.py`**
   - Fix `_make_drug_entity` normalization
   - Fix `_make_company_entity` normalization  
   - Fix `extract_relationships` to use `id_to_entity` map
   - Fix `_make_indication_entity` normalization

2. **`src/processors/openfda_processor.py`**
   - Remove "Unknown Drug" fallback (return None instead)
   - Improve indication parsing (or document limitation)

3. **`src/processors/patentsview_processor.py`**
   - Fix `_make_company_entity` normalization

---

## Pattern Identified

**Common LLM-Generated Issue:**
- Extraction functions normalize names ✅
- Stub creation functions don't normalize ❌
- Relationship extraction uses stubs instead of `id_to_entity` ❌

This is a **systematic issue** across multiple processors - the pattern suggests LLM generated the code without understanding the stub key matching requirement.

