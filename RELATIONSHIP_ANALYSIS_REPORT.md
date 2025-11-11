# Relationship Analysis Report

## Executive Summary

**Total Relationships**: 5,943

**Status**: Many relationship types are missing (0 relationships), indicating issues with relationship extraction and creation.

## Current Relationship Counts

| Relationship Type | Count | Status |
|------------------|-------|--------|
| TrialSponsor | 1,748 | ✅ Working |
| TrialDisease | 2,085 | ✅ Working |
| TrialDrug | 1,228 | ✅ Working |
| CompanyDrug | 739 | ✅ Working |
| RegulatoryDrugEvent | 22 | ✅ Working |
| RegulatoryCompanyEvent | 71 | ✅ Working |
| FilingCompany | 49 | ✅ Working |
| DrugIndication | 1 | ⚠️ Very Low |
| **PublicationDrug** | **0** | ❌ **Missing** |
| **PublicationTrial** | **0** | ❌ **Missing** |
| **PublicationCompany** | **0** | ❌ **Missing** |
| **PatentDrug** | **0** | ❌ **Missing** |
| **PatentCompany** | **0** | ❌ **Missing** |
| **FilingDrug** | **0** | ❌ **Missing** |
| **DrugTarget** | **0** | ❌ **Missing** |
| **DrugMechanism** | **0** | ❌ **Missing** |
| CompanyOwnershipHistory | 0 | ❌ Missing |
| DrugOwnershipHistory | 0 | ❌ Missing |
| TrialFunding | 0 | ❌ Missing |
| PresentationDrug | 0 | ❌ Missing |
| PresentationCompany | 0 | ❌ Missing |
| PresentationTrial | 0 | ❌ Missing |

## Entity Counts

- Companies: 331
- Drugs: 865
- Trials: 1,017
- Publications: 100
- Patents: 0
- SEC Filings: 49

## Root Causes Identified

### 1. Publication Relationships (0 relationships, 100 publications exist)

**Problem**: Publications are being created but relationships are not.

**Root Causes**:
1. **PublicationTrial**: The `PubMedProcessor.extract_relationships()` method queries the database for trials by NCT ID and creates relationship stubs. However, these trial stubs are created from database objects, not from extracted entities. The pipeline's `entity_stub_to_id` mapping only contains entities extracted in the current processing run, so the trial stub keys don't match, causing relationship creation to fail.

2. **PublicationDrug**: Drugs are extracted from publication text (this was fixed), but:
   - The drugs might not be resolving properly
   - Or the stub key matching is failing

**Code Location**: `src/processors/pubmed_processor.py` lines 132-151 (PublicationTrial) and 153-166 (PublicationDrug)

**Fix Required**:
- For PublicationTrial: Instead of creating stubs from database objects, query the database for trial UUIDs directly and use those UUIDs in the relationship creation, bypassing the stub key matching.
- For PublicationDrug: Verify entity resolution is working for extracted drugs.

### 2. Patent Relationships (0 relationships, 0 patents exist)

**Status**: No patents in database, so no relationships expected.

**Note**: PatentsViewProcessor and USPTOPublicPairProcessor have relationship extraction code, but no patents have been ingested yet.

### 3. FilingDrug Relationships (0 relationships, 49 filings exist)

**Problem**: SEC filings exist but no drug relationships.

**Root Cause**: Need to verify:
- Is `SECFilingsProcessor._extract_drugs_text_search()` being called?
- Are drugs being found in filing text?
- Is entity resolution working for extracted drugs?

**Code Location**: `src/processors/sec_filings_processor.py`

### 4. DrugTarget and DrugMechanism (0 relationships, 865 drugs exist)

**Problem**: No target or mechanism relationships exist.

**Root Cause**: **OpenFDA processor does NOT extract drug targets or mechanisms**. It only extracts:
- Drug-indication relationships
- Company-drug relationships

**Code Location**: `src/processors/openfda_processor.py` - `extract_relationships()` method (lines 92-148) only creates `drug_indication` and `company_drug` relationships.

**Fix Required**: 
- Need a different data source that provides drug target/mechanism information
- Or add extraction logic to OpenFDA processor if that data is available in OpenFDA labels

### 5. CompanyOwnershipHistory and DrugOwnershipHistory (0 relationships)

**Problem**: No ownership history relationships.

**Root Cause**: No processor appears to extract ownership history. This might require:
- Manual data entry
- A different data source
- Inference from other relationships

## Recommendations

### High Priority

1. **Fix PublicationTrial relationships**:
   - Modify `PubMedProcessor.extract_relationships()` to query trial UUIDs directly instead of creating stubs
   - Or modify pipeline to handle database-lookup relationships differently

2. **Investigate PublicationDrug relationships**:
   - Add logging to see if drugs are being extracted
   - Verify entity resolution is working
   - Check stub key matching

3. **Investigate FilingDrug relationships**:
   - Add logging to SEC processor to see if drugs are being found
   - Verify relationship creation is being called

### Medium Priority

4. **Add DrugTarget/DrugMechanism extraction**:
   - Identify data source that provides this information
   - Implement extraction in appropriate processor
   - Or add to OpenFDA processor if data is available

5. **Add ownership history extraction**:
   - Identify data source for company/drug ownership history
   - Implement extraction logic

### Low Priority

6. **Patent relationships**: Will be created automatically once patents are ingested

## Next Steps

1. Fix PublicationTrial relationship creation (bypass stub matching for database lookups)
2. Add diagnostic logging to PublicationDrug and FilingDrug extraction
3. Identify and implement data source for DrugTarget/DrugMechanism
4. Re-run ingestion for publications to create relationships


