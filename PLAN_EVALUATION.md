# Plan Evaluation: Deferred Relationship Inference

## Executive Summary

The plan is **well-aligned** with the repository structure, but needs adjustments to leverage existing infrastructure and avoid duplication.

## Existing Infrastructure Found

### ✅ Already Exists

1. **`src/services/relationship_inference.py`** - RelationshipInferenceService class
   - Currently implements: `infer_company_drug_relationships()`
   - Has `infer_all_relationships()` method (currently only calls company_drug)
   - **Action**: Extend this existing service rather than creating new file

2. **Pipeline Integration** - `src/processing/pipeline.py` lines 221-232
   - Already calls `RelationshipInferenceService` after processing
   - Runs `infer_all_relationships()` automatically
   - **Action**: Extend existing integration point

3. **Normalization Methods** - `src/entity_resolution/base_processor.py`
   - `normalize_drug_name_static()` - exists and used
   - `normalize_company_name_static()` - exists and used
   - **Action**: Reuse these in inference engine

4. **Database Models** - All relationship models exist:
   - `PublicationTrial`, `PublicationDrug`, `PublicationCompany`
   - `FilingDrug`, `CompanyDrug`
   - All have proper foreign keys and constraints
   - **Action**: Use existing models

5. **Drug Name Loading Pattern** - `src/processors/pubmed_processor.py` lines 298-339
   - `_get_all_drug_names()` method already implemented
   - Loads from database with normalization
   - **Action**: Extract to shared utility or reuse pattern

## Plan Adjustments Needed

### 1. File Location Change

**Plan Says**: Create `src/processing/relationship_inference.py`  
**Reality**: Service already exists at `src/services/relationship_inference.py`

**Recommendation**: 
- Extend existing `src/services/relationship_inference.py`
- Add new methods to `RelationshipInferenceService` class
- Keep service pattern (services/ directory) rather than processing/ directory

### 2. Integration Point

**Plan Says**: Create new CLI script  
**Reality**: Pipeline already calls inference service automatically

**Recommendation**:
- Keep automatic inference in pipeline (for same-run relationships)
- Add standalone CLI script for full rebuild (as planned)
- Both approaches can coexist

### 3. Method Naming Consistency

**Plan Says**: Methods like `infer_publication_trial_relationships()`  
**Reality**: Existing method is `infer_company_drug_relationships()`

**Recommendation**: 
- Follow existing naming pattern
- Keep consistency: `infer_<relationship_type>_relationships()`

### 4. Reuse Existing Patterns

**Plan Says**: Implement text extraction from scratch  
**Reality**: `PubMedProcessor._extract_nct_ids()` and `_extract_drugs()` already exist

**Recommendation**:
- Extract shared utilities to `src/services/relationship_inference.py` or base class
- Reuse existing text extraction patterns
- Avoid code duplication

## Detailed File-by-File Evaluation

### ✅ Files to Extend (Not Create)

1. **`src/services/relationship_inference.py`** (EXISTS)
   - **Current**: 134 lines, implements company-drug inference
   - **Add**: 
     - `infer_publication_trial_relationships()`
     - `infer_publication_drug_relationships()`
     - `infer_publication_company_relationships()`
     - `infer_filing_drug_relationships()`
   - **Update**: `infer_all_relationships()` to call new methods
   - **Add**: Helper methods for text extraction (can reuse from processors)

2. **`scripts/infer_relationships.py`** (NEW - as planned)
   - Create standalone CLI script
   - Can call `RelationshipInferenceService.rebuild_all()` method
   - Add command-line options as planned

### ✅ Files to Review (May Need Updates)

1. **`src/processing/pipeline.py`** (EXISTS)
   - Lines 221-232: Already calls inference service
   - **Action**: No changes needed for basic functionality
   - **Optional**: Add flag to skip automatic inference when running full rebuild

2. **`src/processors/pubmed_processor.py`** (EXISTS)
   - Has `_extract_nct_ids()` method (lines 378-405)
   - Has `_extract_drugs()` method (lines 240-296)
   - Has `_get_all_drug_names()` method (lines 298-339)
   - **Action**: Extract shared utilities to inference service to avoid duplication

### ✅ Database Models (All Exist)

1. **`database/models/publications.py`**
   - `Publication` model: Has `title`, `abstract`, `pmid` fields ✅
   - No `trial_nct_ids` field - need to extract from text ✅

2. **`database/models/clinical.py`**
   - `ClinicalTrial` model: Has `nct_id` field (unique, indexed) ✅

3. **`database/models/publications.py`**
   - `SECFiling` model: Has `full_text` field ✅

4. **`database/models/relationships.py`**
   - All relationship models exist with proper structure ✅

## Implementation Adjustments

### Adjustment 1: Extend Existing Service

**Instead of**:
```python
# src/processing/relationship_inference.py (NEW)
class RelationshipInferenceEngine:
    ...
```

**Do**:
```python
# src/services/relationship_inference.py (EXTEND EXISTING)
class RelationshipInferenceService:
    # Existing: infer_company_drug_relationships()
    
    # Add new methods:
    def infer_publication_trial_relationships(self) -> Dict[str, Any]:
        ...
    
    def infer_publication_drug_relationships(self) -> Dict[str, Any]:
        ...
    
    def rebuild_all(self, clear_existing=True) -> Dict[str, Any]:
        """Rebuild all relationships from scratch"""
        if clear_existing:
            self._clear_all_relationships()
        
        results = {}
        results['company_drug'] = self.infer_company_drug_relationships()
        results['publication_trial'] = self.infer_publication_trial_relationships()
        results['publication_drug'] = self.infer_publication_drug_relationships()
        # ... etc
        
        return results
```

### Adjustment 2: Extract Shared Utilities

**Create helper methods in RelationshipInferenceService**:
```python
def _extract_nct_ids_from_text(self, text: str) -> List[str]:
    """Extract NCT IDs from text (reuse pattern from PubMedProcessor)"""
    import re
    nct_pattern = re.compile(r'NCT\d{8}', re.IGNORECASE)
    return list(set(nct_pattern.findall(text)))

def _load_all_drug_names(self) -> Set[str]:
    """Load all drug names from database (reuse pattern from PubMedProcessor)"""
    from database.models import Drug
    from src.entity_resolution.base_processor import BaseProcessor
    
    drug_names = set()
    drugs = self.session.query(Drug).filter(Drug.deleted_at.is_(None)).all()
    
    for drug in drugs:
        if drug.primary_name:
            normalized = BaseProcessor.normalize_drug_name_static(drug.primary_name)
            drug_names.add(normalized)
        # ... add generic_name and aliases
    
    return drug_names
```

### Adjustment 3: Update CLI Script

**`scripts/infer_relationships.py`** should import from services:
```python
from src.services.relationship_inference import RelationshipInferenceService
from database.config import get_db_session

def main():
    with get_db_session() as session:
        service = RelationshipInferenceService(session)
        results = service.rebuild_all(clear_existing=args.rebuild)
        # Print results
```

## Potential Issues & Solutions

### Issue 1: Text Storage in Database

**Problem**: Publications have `title` and `abstract` fields, but may not have full text stored.

**Solution**: 
- Check if `abstract` field is populated
- If not, may need to reprocess publications to extract text
- For SEC filings, `full_text` field exists but may be empty

**Action**: Add logging to show how many publications/filings have searchable text

### Issue 2: Drug Name Matching

**Problem**: Drug names in text may not match normalized database names exactly.

**Solution**:
- Use fuzzy matching for drug names (existing EntityResolver has this)
- Or use word boundary matching (already implemented in PubMedProcessor)
- May need to refine matching logic based on results

**Action**: Start with exact matching, add fuzzy matching if needed

### Issue 3: Company Name Matching in Publications

**Problem**: Publications may not have structured company data.

**Solution**:
- Limited by what's stored in publication `context` field
- May need to extract from author affiliations if stored
- This relationship type may have limited results initially

**Action**: Implement basic version, can enhance later with NLP

## Updated File List

### Files to Modify (Not Create)

1. **`src/services/relationship_inference.py`** (EXTEND)
   - Add new inference methods
   - Add helper utilities
   - Add `rebuild_all()` method
   - Add `_clear_all_relationships()` method

### Files to Create (As Planned)

1. **`scripts/infer_relationships.py`** (NEW)
   - CLI script for running inference
   - Import from `src.services.relationship_inference`

2. **`test_relationship_inference.py`** (NEW - optional)
   - Tests for new inference methods

### Files to Review (No Changes Needed Initially)

1. **`src/processing/pipeline.py`** - Already integrated
2. **`src/processors/pubmed_processor.py`** - Can reuse patterns
3. Database models - All exist and correct

## Recommendations

### ✅ Proceed with Plan (With Adjustments)

1. **Extend existing service** instead of creating new one
2. **Reuse existing patterns** from processors
3. **Keep automatic inference** in pipeline for same-run relationships
4. **Add standalone CLI** for full rebuilds
5. **Start with full rebuild** (Option 2A) as planned

### ⚠️ Considerations

1. **Text availability**: Verify publications/filings have searchable text
2. **Matching quality**: May need to refine drug/company name matching
3. **Performance**: Full rebuild is fine now, but monitor as data grows
4. **Incremental updates**: Can add later when needed (Option 2B)

## Conclusion

The plan is **sound and well-aligned** with the repository structure. Main adjustments:
- Extend existing `RelationshipInferenceService` instead of creating new class
- Reuse existing text extraction patterns
- Keep existing pipeline integration
- Add standalone CLI for full rebuilds

**Estimated Implementation Time**: 3-4 hours (as planned)
**Risk Level**: Low (building on existing, tested infrastructure)


