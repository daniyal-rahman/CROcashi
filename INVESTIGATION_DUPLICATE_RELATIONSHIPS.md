# Investigation: Duplicate Relationships and Non-Drug Interventions

## Problem Statement

Processing 10 ClinicalTrials.gov records results in:
- 50% failure rate (5/10 records fail)
- Duplicate relationship constraint violations
- Non-drug interventions ("Computed Tomography", "SBRT") being treated as drugs

## Root Cause Analysis

### Issue 1: Duplicate Relationship Violations

**Error:**
```
duplicate key value violates unique constraint "trial_drugs_pkey"
Key (trial_id, drug_id)=(uuid1, uuid2) already exists
```

**Root Cause Location:** `src/processing/pipeline.py` lines 284-302

**How It Happens:**

1. Trial has 3 interventions that are the same drug with different names:
   - "Pembrolizumab"
   - "KEYTRUDA" (brand name)  
   - "pembrolizumab" (lowercase variant)

2. Entity extraction creates 3 separate ExtractedEntity objects

3. Entity resolution correctly identifies all 3 as the SAME drug → `drug_id_123`

4. **BUG:** Pipeline appends all resolved IDs without deduplication:
   ```python
   if resolved_id:
       resolved_ids.append(resolved_id)  # Line 285
   ```
   Result: `resolved_entities['drugs'] = [drug_id_123, drug_id_123, drug_id_123]`

5. Relationship extraction creates 3 relationships for the same trial-drug pair

6. Database rejects: unique constraint violation

**Why Deduplication in RelationshipBuilder Doesn't Help:**

The RelationshipBuilder's `_find_existing_relationship` only checks the database, but within a single transaction, all 3 relationships are added to the session before any are committed. SQLAlchemy batches them and the database rejects the entire batch.

### Issue 2: Non-Drug Interventions Appear as Drugs

**Error:**
```
Target entity not resolved for relationship: trial_drug - drug: Computed Tomography
Target entity not resolved for relationship: trial_drug - drug: SBRT
```

**Root Cause Location:** `src/processors/clinicaltrials_processor.py` lines 246-260 and 519-539

**How It Happens:**

1. Trial has 5 interventions in API response:
   ```
   [0] Drug: "Pembrolizumab" (type: DRUG)
   [1] Procedure: "Computed Tomography" (type: PROCEDURE)  
   [2] Drug: "Nivolumab" (type: DRUG)
   [3] Procedure: "SBRT" (type: PROCEDURE)
   [4] Drug: "Ipilimumab" (type: DRUG)
   ```

2. `_extract_interventions` correctly filters, extracting only drugs:
   ```python
   if intervention_type not in ['drug', 'biological', 'biologic']:
       continue  # Skip procedures
   ```
   Result: Extracted drugs at indices [0, 2, 4]

3. After resolution: `resolved_entities['drugs'] = [drug_id_1, drug_id_2, drug_id_3]`

4. **BUG:** `extract_relationships` loops through resolved IDs using index:
   ```python
   for i, drug_id in enumerate(resolved_entities.get('drugs', [])):
       # i = 0, 1, 2
       arm_name = interventions[i].get('arm_group_label', 'experimental')
   ```

5. `_make_drug_entity(raw_data, i)` uses the same index to look up the drug:
   ```python
   interventions = data.get('interventions', [])
   if index < len(interventions):
       drug_name = interventions[index].get('intervention_name', ...)
   ```

6. **Index Mismatch:**
   - i=0 → looks up interventions[0] = "Pembrolizumab" ✓ CORRECT
   - i=1 → looks up interventions[1] = "Computed Tomography" ✗ WRONG (this is a procedure!)
   - i=2 → looks up interventions[2] = "Nivolumab" ✗ WRONG (offset by filtered items)

7. Creates entity stub for "Computed Tomography" but it was never extracted/resolved

8. Pipeline can't find entity ID in `entity_stub_to_id` → "Target entity not resolved"

**Why This Causes Failures:**

Some trials have many procedures mixed with drugs. When the index mapping is wrong, most relationships fail to resolve, and if ANY relationship in the batch has an unresolved entity, the entire record processing may fail (depending on error handling).

## Impact Analysis

**Affected Records:**
- Any trial with duplicate drug names/aliases (common with brand/generic names)
- Any trial with non-drug interventions (very common - ~60% of trials)

**Success Rate:**
- Clean trials with unique drugs: 100% success
- Trials with duplicates OR procedures: Likely to fail
- Estimated 40-60% failure rate on real-world data

## Solution Design

### Fix 1: Deduplicate Resolved IDs

**Location:** `src/processing/pipeline.py` line 285-302

**Change:**
```python
# After resolving all entities of a type, deduplicate
resolved_ids = list(set(resolved_ids))  # or use dict to preserve order
```

**Alternative (Better):** Deduplicate while preserving relationship with extracted entities
```python
# Use dict to track unique IDs and their first occurrence
seen_ids = {}
for i, extracted_entity in enumerate(entity_list):
    resolution = resolver.resolve(extracted_entity)
    if resolved_id:
        if resolved_id not in seen_ids:
            seen_ids[resolved_id] = i  # Track first occurrence
            resolved_ids.append(resolved_id)
```

### Fix 2: Fix Index Mapping for Relationships

**Problem:** Need to map from filtered drug list back to original intervention indices

**Option A:** Store original indices with resolved entities
```python
resolved_entities['drugs'] = [(drug_id, original_index), ...]
```

**Option B (Simpler):** Don't use indices at all - extract actual drug data during resolution
```python
resolved_entities['drugs'] = [
    {'id': drug_id, 'name': 'Pembrolizumab', 'context': {...}},
    ...
]
```

**Option C (Recommended):** Store mapping in pipeline and pass to extract_relationships
```python
# In pipeline: Track which extracted entities were resolved
drug_mapping = {}  # resolved_id -> extracted_entity

# Pass to processor
relationships = processor.extract_relationships(
    raw_data, 
    resolved_entities,
    entity_mapping=drug_mapping  # NEW parameter
)

# In processor: Use actual entity data, not raw_data indices
for drug_id, drug_entity in entity_mapping['drugs'].items():
    relationships.append(RelationshipExtraction(
        relationship_type='trial_drug',
        source_entity=trial_entity,
        target_entity=drug_entity,  # Use the actual extracted entity
        attributes={'arm_name': drug_entity.context.get('arm_groups', ['experimental'])[0]}
    ))
```

### Fix 3: Add Deduplication in RelationshipBuilder

**Location:** `src/entity_resolution/relationship_builder.py`

**Change:** Before adding relationships to session, check if already in session:
```python
# In create_relationship
existing_in_session = self._check_session_for_relationship(
    model, source_entity_id, target_entity_id
)
if existing_in_session:
    self.skipped_count += 1
    return True
```

## Recommended Fix Strategy

**Phase 1: Quick Fix (Minimize Failures)**
1. Deduplicate resolved_ids in pipeline (Fix 1 - simple version)
2. Add session-level deduplication check in RelationshipBuilder (Fix 3)

**Phase 2: Proper Fix (Correct Index Mapping)**
1. Implement Option C for Fix 2 (entity mapping)
2. Refactor extract_relationships to not use raw_data indices

**Testing:**
1. Test with trials that have duplicate drug names
2. Test with trials that mix drugs and procedures
3. Test with 100 random trials to ensure >95% success rate

## Files to Modify

1. `src/processing/pipeline.py` (lines 284-302)
   - Add deduplication of resolved_ids
   - Create entity_mapping dict
   - Pass to extract_relationships

2. `src/processors/clinicaltrials_processor.py` (lines 206-271)
   - Update extract_relationships signature
   - Use entity_mapping instead of indices
   - Remove _make_drug_entity, _make_disease_entity helpers (no longer needed)

3. `src/entity_resolution/relationship_builder.py` (lines 66-125)
   - Add _check_session_for_relationship method
   - Call before adding to session

4. `src/entity_resolution/base_processor.py`
   - Update extract_relationships signature in base class

## Expected Outcome

After fixes:
- Success rate: >95% on real-world data
- Duplicates: Properly deduplicated, no constraint violations
- Procedures: Correctly filtered, no index mismatches
- Relationships: Only created for actually extracted and resolved entities

