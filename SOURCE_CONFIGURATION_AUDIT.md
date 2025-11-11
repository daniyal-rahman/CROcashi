# Phase 1: Source Configuration Audit

**Generated:** 2025-11-09 11:38:39

## Executive Summary

- **Total Ingestion Scripts:** 82
- **Registered Sources:** 6
- **Unregistered Sources:** 76
- **Active Sources:** 6
- **Inactive Sources:** 0
- **Active but Never Run:** 1
- **Missing Scripts:** 0

---

## 1. Source Registration Check

### Unregistered Sources (Need Registration)

These sources have ingestion scripts but are not registered in the `sources` table.

#### 🔴 CRITICAL Priority (Failure Detection)

| Source Name | Type | Category | Priority Reason |
|-------------|------|----------|-----------------|
| `asco_abstracts` | conference | conference | Conference abstracts (trial results, early data) |
| `biospace_layoff_tracker` | employment | employment | Employment signals (layoffs, WARN notices) |
| `california_warn` | employment | employment | Employment signals (layoffs, WARN notices) |
| `ema_epar` | regulatory | regulatory | Regulatory signals (clinical holds, approvals, warnings) |
| `ema_prime` | regulatory | regulatory | Regulatory signals (clinical holds, approvals, warnings) |
| `fda_breakthrough` | regulatory | regulatory | Regulatory signals (clinical holds, approvals, warnings) |
| `fda_clinical_hold` | regulatory | regulatory | Regulatory signals (clinical holds, approvals, warnings) |
| `fda_orange_book` | regulatory | regulatory | Regulatory signals (clinical holds, approvals, warnings) |
| `fda_orphan` | regulatory | regulatory | Regulatory signals (clinical holds, approvals, warnings) |
| `fda_warning_letters` | regulatory | regulatory | Regulatory signals (clinical holds, approvals, warnings) |
| `federal_warn` | employment | employment | Employment signals (layoffs, WARN notices) |
| `fierce_layoff_tracker` | employment | employment | Employment signals (layoffs, WARN notices) |
| `uspto_public_pair` | patent | patent | Patent data (IP protection, innovation signals) |
| `who_ictrp` | regulatory | clinical | Critical for failure detection |

#### 🟠 HIGH Priority

| Source Name | Type |
|-------------|------|
| `cdsco_india` | regulatory |
| `ema_guidelines` | regulatory |
| `ema_trials` | regulatory |
| `fda_eua` | regulatory |
| `fda_expanded_access` | regulatory |
| `fda_faers` | regulatory |
| `fda_guidance` | regulatory |
| `fda_purple_book` | regulatory |
| `health_canada` | regulatory |
| `hsa_singapore` | regulatory |
| `ich_guidelines` | regulatory |
| `illinois_warn` | employment |
| `massachusetts_warn` | employment |
| `mfds_korea` | regulatory |
| `mhra_uk` | regulatory |
| `new_jersey_warn` | employment |
| `new_york_warn` | employment |
| `nice_uk` | regulatory |
| `pennsylvania_warn` | employment |
| `swissmedic` | regulatory |
| `texas_warn` | employment |
| `tga_australia` | regulatory |
| `who_outbreak_news` | regulatory |
| `xtalks_layoff` | employment |

#### 🟡 MEDIUM Priority

| Source Name | Type |
|-------------|------|
| `arxiv` | literature |
| `biorxiv` | literature |
| `chemrxiv` | literature |
| `europe_pmc` | literature |
| `medrxiv` | literature |
| `pmc` | literature |
| `pubtator` | literature |
| `semantic_scholar` | literature |

#### ⚪ LOW Priority

*30 additional sources*

---

## 2. Source Activation Verification

### ⚠️ Active Sources Never Run

These sources are marked `is_active=True` but have never been executed.

| Source Name | Type | Status | Issue |
|-------------|------|--------|-------|
| `patentsview` | patent | Active | Never run, no staging records |

### ⚠️ Sources with Metadata Issues

| Source Name | Issues |
|-------------|--------|
| `openfda` | Type mismatch: registered as 'regulatory', should be 'other' |

---

## 3. Missing Critical Sources for Failure Detection

These high-priority sources should be running to detect company failures:

### REGULATORY Sources

| Source Name | Status | Priority | Reason |
|-------------|--------|----------|--------|
| `fda_breakthrough` | ❌ Not Registered | CRITICAL | Breakthrough designations signal success |
| `fda_orphan` | ❌ Not Registered | CRITICAL | Orphan designations indicate pipeline activity |
| `fda_orange_book` | ❌ Not Registered | CRITICAL | Approved drugs = revenue potential |
| `fda_clinical_hold` | ❌ Not Registered | CRITICAL | Clinical holds = immediate failure signal |
| `fda_warning_letters` | ❌ Not Registered | CRITICAL | Warning letters = regulatory risk |
| `ema_epar` | ❌ Not Registered | CRITICAL | Regulatory approvals/rejections |
| `ema_prime` | ❌ Not Registered | CRITICAL | Regulatory approvals/rejections |

### EMPLOYMENT Sources

| Source Name | Status | Priority | Reason |
|-------------|--------|----------|--------|
| `california_warn` | ❌ Not Registered | CRITICAL | Layoffs/WARN notices = financial distress signal |
| `federal_warn` | ❌ Not Registered | CRITICAL | Layoffs/WARN notices = financial distress signal |
| `biospace_layoff_tracker` | ❌ Not Registered | CRITICAL | Layoffs/WARN notices = financial distress signal |
| `fierce_layoff_tracker` | ❌ Not Registered | CRITICAL | Layoffs/WARN notices = financial distress signal |

### PATENT Sources

| Source Name | Status | Priority | Reason |
|-------------|--------|----------|--------|
| `patentsview` | ⚠️ Active but Never Run | CRITICAL | Patent activity = innovation/IP protection |
| `uspto_public_pair` | ❌ Not Registered | CRITICAL | Patent activity = innovation/IP protection |

### CONFERENCE Sources

| Source Name | Status | Priority | Reason |
|-------------|--------|----------|--------|
| `asco_abstracts` | ❌ Not Registered | CRITICAL | Conference abstracts = early trial results |

### CLINICAL Sources

| Source Name | Status | Priority | Reason |
|-------------|--------|----------|--------|
| `who_ictrp` | ❌ Not Registered | CRITICAL | Critical for failure detection |

---

## 4. Registration Recommendations (Prioritized)

### Immediate Action Required (Week 1)

Register and activate these critical sources:

| Source Name | Type | Category | Action |
|-------------|------|----------|-------|
| `fda_breakthrough` | regulatory | regulatory | Register + Activate |
| `fda_orphan` | regulatory | regulatory | Register + Activate |
| `fda_orange_book` | regulatory | regulatory | Register + Activate |
| `fda_clinical_hold` | regulatory | regulatory | Register + Activate |
| `fda_warning_letters` | regulatory | regulatory | Register + Activate |
| `ema_epar` | regulatory | regulatory | Register + Activate |
| `ema_prime` | regulatory | regulatory | Register + Activate |
| `california_warn` | employment | employment | Register + Activate |
| `federal_warn` | employment | employment | Register + Activate |
| `biospace_layoff_tracker` | employment | employment | Register + Activate |
| `fierce_layoff_tracker` | employment | employment | Register + Activate |
| `uspto_public_pair` | patent | patent | Register + Activate |
| `asco_abstracts` | conference | conference | Register + Activate |
| `who_ictrp` | regulatory | clinical | Register + Activate |

#### SQL Template for Registration

```sql
INSERT INTO sources (source_name, source_type, is_active, update_frequency, base_url)
VALUES
  ('fda_breakthrough', 'regulatory', true, 'weekly', 'https://example.com'),
  ('fda_orphan', 'regulatory', true, 'weekly', 'https://example.com'),
  ('fda_orange_book', 'regulatory', true, 'weekly', 'https://example.com'),
  ('fda_clinical_hold', 'regulatory', true, 'weekly', 'https://example.com'),
  ('fda_warning_letters', 'regulatory', true, 'weekly', 'https://example.com'),
  ('ema_epar', 'regulatory', true, 'weekly', 'https://example.com'),
  ('ema_prime', 'regulatory', true, 'weekly', 'https://example.com'),
  ('california_warn', 'employment', true, 'weekly', 'https://example.com'),
  ('federal_warn', 'employment', true, 'weekly', 'https://example.com'),
  ('biospace_layoff_tracker', 'employment', true, 'weekly', 'https://example.com'),
```

---

## 5. Summary Statistics

### Sources by Type

| Type | Total Scripts | Registered | Unregistered |
|------|---------------|------------|--------------|
| clinical | 1 | 1 | 0 |
| conference | 1 | 0 | 1 |
| employment | 11 | 0 | 11 |
| financial | 4 | 1 | 3 |
| funding | 6 | 0 | 6 |
| literature | 9 | 1 | 8 |
| other | 6 | 0 | 5 |
| patent | 2 | 1 | 1 |
| regulatory | 26 | 2 | 25 |
| scientific | 12 | 0 | 12 |
| social | 4 | 0 | 4 |

---

**End of Report**

---

# Phase 2: Data Pipeline Integrity Check

**Generated:** 2025-11-09 11:38:39

Goal: Verify data flows from staging → entities → relationships with minimal loss

---

## 1. Staging to Entity Conversion Rates

For each active source, tracking the data flow funnel:

| Source Name | Staging Records | Processed | Entities Created | Staging→Processed | Processed→Entities | Overall Conversion | Status |
|-------------|----------------|----------|------------------|-------------------|-------------------|-------------------|--------|
| `clinicaltrials_gov` | 1018 | 1018 | 3388 | 100.0% | 332.8% | 332.8% | ✅ Good |
| `fda_drugs` | 9 | 0 | 0 | 0.0% | 0.0% | 0.0% | ❌ None |
| `sec_edgar` | 50 | 50 | 0 | 100.0% | 0.0% | 0.0% | ❌ None |
| `pubmed` | 100 | 100 | 0 | 100.0% | 0.0% | 0.0% | ❌ None |
| `patentsview` | 0 | 0 | 0 | 0.0% | 0.0% | 0.0% | ❌ None |
| `openfda` | 100 | 100 | 0 | 100.0% | 0.0% | 0.0% | ❌ None |

---

## 2. Entity Extraction Validation

### Source: clinicaltrials_gov

**Sampled 20 records for validation**

- **Processed:** 20/20
- **Unprocessed:** 0/20

**Extraction Results:**
- Entities Extracted: 120
- Entities Matched: 82
- Entities Created: 33

---

### Source: fda_drugs

**Sampled 9 records for validation**

- **Processed:** 0/9
- **Unprocessed:** 9/9

---

### Source: sec_edgar

**Sampled 20 records for validation**

- **Processed:** 20/20
- **Unprocessed:** 0/20

**Extraction Results:**
- Entities Extracted: 40
- Entities Matched: 23
- Entities Created: 17

---

### Source: pubmed

**Sampled 20 records for validation**

- **Processed:** 20/20
- **Unprocessed:** 0/20

**Extraction Results:**
- Entities Extracted: 20
- Entities Matched: 0
- Entities Created: 20

---

### Source: patentsview

*No staging records found*

## 3. Deduplication Analysis

### Overall Deduplication Statistics

| Source Name | Entities Extracted | Entities Matched | Entities Created | Deduplication Rate |
|-------------|-------------------|------------------|------------------|-------------------|
| `clinicaltrials_gov` | 6657 | 2856 | 3389 | 42.9% | ⚠️ Low |
| `fda_drugs` | 0 | 0 | 0 | 0.0% | ❌ None |
| `sec_edgar` | 100 | 56 | 44 | 56.0% | ⚠️ Low |
| `pubmed` | 100 | 0 | 100 | 0.0% | ❌ None |
| `patentsview` | 0 | 0 | 0 | 0.0% | ❌ None |
| `openfda` | 172 | 19 | 149 | 11.0% | ⚠️ Low |

### Entity Aliases Analysis

Verifying that entity aliases are being created for deduplication:

#### clinicaltrials_gov

| Entity Type | Entity Count | Alias Count | Avg Aliases/Entity |
|-------------|--------------|-------------|-------------------|
| company | 0 | 0 | 0.00 ❌ |
| drug | 617 | 617 | 1.00 ✅ |
| disease | 1072 | 1072 | 1.00 ✅ |

#### fda_drugs

| Entity Type | Entity Count | Alias Count | Avg Aliases/Entity |
|-------------|--------------|-------------|-------------------|
| company | 0 | 0 | 0.00 ❌ |
| drug | 0 | 0 | 0.00 ❌ |
| disease | 0 | 0 | 0.00 ❌ |

#### sec_edgar

| Entity Type | Entity Count | Alias Count | Avg Aliases/Entity |
|-------------|--------------|-------------|-------------------|
| company | 0 | 0 | 0.00 ❌ |
| drug | 0 | 0 | 0.00 ❌ |
| disease | 0 | 0 | 0.00 ❌ |

#### pubmed

| Entity Type | Entity Count | Alias Count | Avg Aliases/Entity |
|-------------|--------------|-------------|-------------------|
| company | 0 | 0 | 0.00 ❌ |
| drug | 0 | 0 | 0.00 ❌ |
| disease | 0 | 0 | 0.00 ❌ |

#### patentsview

| Entity Type | Entity Count | Alias Count | Avg Aliases/Entity |
|-------------|--------------|-------------|-------------------|
| company | 0 | 0 | 0.00 ❌ |
| drug | 0 | 0 | 0.00 ❌ |
| disease | 0 | 0 | 0.00 ❌ |

### High Confidence Matches Not Auto-Merged

Matches with confidence ≥ 0.8 that require manual review:

| Source Name | High Confidence Unmerged |
|-------------|-------------------------|
| `clinicaltrials_gov` | 186 ⚠️ Review Needed |
| `fda_drugs` | 0 ✅ None |
| `sec_edgar` | 0 ✅ None |
| `pubmed` | 0 ✅ None |
| `patentsview` | 0 ✅ None |
| `openfda` | 3 ⚠️ Review Needed |

---

## 4. Data Loss Funnel Summary

Overall pipeline statistics showing where records are lost:

### Overall Pipeline Funnel

1. **Staging Records:** 1,277
2. **Successfully Processed:** 1,268 (99.3%)
3. **Entities Created:** 3,388 (265.3%)

**Loss Points:**
- Staging → Processed: 9 records lost (0.7%)
- Processed → Entities: -2,120 records lost (-167.2%)

---

**End of Phase 2 Report**

---

# Phase 3: Relationship Generation Coverage

**Generated:** 2025-11-09 11:38:40

Goal: Ensure relationships are being created between resolved entities

---

## 1. Relationship Creation Rates

### Overall Relationship Coverage

| Relationship Table | Actual Count | Expected (Min) | Expected (Typical) | Coverage % | Status |
|-------------------|--------------|----------------|-------------------|------------|--------|
| `company_drugs` | 2 | 130 | 261 | 1.5% | ⚠️ Low |
| `drug_indications` | 0 | N/A | N/A | N/A | - |
| `drug_mechanisms` | 0 | 0 | 256 | 0.0% | ⚠️ Low |
| `drug_targets` | 0 | 0 | 427 | 0.0% | ⚠️ Low |
| `filing_companies` | 49 | 49 | 49 | 100.0% | ✅ Good |
| `filing_drugs` | 0 | 15 | 24 | 0.0% | ❌ Empty |
| `patent_companies` | 0 | N/A | N/A | N/A | - |
| `patent_drugs` | 0 | N/A | N/A | N/A | - |
| `publication_companies` | 0 | 20 | 40 | 0.0% | ❌ Empty |
| `publication_drugs` | 0 | 30 | 50 | 0.0% | ❌ Empty |
| `publication_trials` | 0 | 10 | 20 | 0.0% | ❌ Empty |
| `regulatory_company_events` | 0 | N/A | N/A | N/A | - |
| `regulatory_drug_events` | 0 | N/A | N/A | N/A | - |
| `trial_diseases` | 2,085 | 1017 | 1526 | 205.0% | ✅ Good |
| `trial_drugs` | 1,228 | 814 | 1017 | 150.9% | ✅ Good |
| `trial_sponsors` | 1,748 | 1017 | 1220 | 171.9% | ✅ Good |

### 🔴 Critical Empty Tables

#### filing_drugs
- **Expected:** 49 filings, many should mention drugs
- **Actual:** 0

#### publication_companies
- **Expected:** 100 publications, some should mention companies
- **Actual:** 0

#### publication_drugs
- **Expected:** 100 publications, many should mention drugs
- **Actual:** 0

#### publication_trials
- **Expected:** 100 publications, some should link to trials
- **Actual:** 0

### ⚠️ Low Coverage Tables (< 50%)

#### company_drugs
- **Actual:** 2
- **Expected (Min):** 130
- **Coverage:** 1.5%
- **Reason:** 261 companies sponsor trials, should have drug relationships

#### drug_mechanisms
- **Actual:** 0
- **Expected (Min):** 0
- **Coverage:** 0.0%
- **Reason:** Should have mechanism data (not yet ingested)

#### drug_targets
- **Actual:** 0
- **Expected (Min):** 0
- **Coverage:** 0.0%
- **Reason:** Should have data from ChEMBL/OpenTargets (not yet ingested)

---

## 2. Cross-Reference Validation

### Clinical Trial Relationships

- **Trials:** 1,017
- **Trial-Sponsor Links:** 1,748 ✅
- **Trial-Drug Links:** 1,228 ✅
- **Trial-Disease Links:** 2,085 ✅

### Publication Relationships

- **Publications:** 100
- **Publication-Drug Links:** 0 ❌
- **Publication-Company Links:** 0 ❌
- **Publication-Trial Links:** 0 ❌

### SEC Filing Relationships

- **SEC Filings:** 49
- **Filing-Company Links:** 49 ✅
- **Filing-Drug Links:** 0 ❌

---

## 3. Company-Drug Relationship Investigation

### Current State

- **Total Companies:** 292
- **Total Drugs:** 854
- **Company-Drug Relationships:** 2 ❌
- **Companies with Trials:** 261
- **Trials with Drugs:** 590
- **Companies Sponsoring Trials with Drugs:** 204

### Analysis

**Expected Minimum:** 204 company-drug relationships

**Why relationships aren't being created:**

1. **Trial-based inference not implemented:**
   - Companies sponsor trials that test drugs
   - Should infer: Company → Drug relationships from TrialSponsor + TrialDrug
   - Currently: Only direct extraction from source data (FDA Drugs@FDA)

2. **Source data limitations:**
   - FDA Drugs@FDA: Only 9 records processed
   - OpenFDA: Creates company-drug links but limited data
   - SEC filings: Extract drugs but may not create relationships

3. **Relationship extraction logic:**
   - ClinicalTrialsProcessor: Creates trial-sponsor and trial-drug, but not company-drug
   - Need: Cross-table inference to link companies to drugs via trials

### Recommendations

1. **Implement cross-table inference:**
   - Create company-drug relationships from TrialSponsor + TrialDrug
   - Query: `SELECT DISTINCT ts.entity_id, td.drug_id FROM trial_sponsors ts JOIN trial_drugs td ON ts.trial_id = td.trial_id WHERE ts.entity_type = 'company'`

2. **Enhance SEC filings processor:**
   - Ensure filing-drug relationships are created
   - Extract company-drug relationships from pipeline updates

3. **Process more FDA data:**
   - FDA Drugs@FDA has company-drug ownership data
   - Currently only 9 records processed

---

## 4. Gap Analysis Summary

### Missing Relationship Types

| Relationship Type | Priority | Reason |
|-------------------|----------|--------|
| `publication_companies` | MEDIUM | 100 publications, some should mention companies |
| `publication_trials` | MEDIUM | 100 publications, some should link to trials |
| `filing_drugs` | HIGH | 49 filings, many should mention drugs |
| `publication_drugs` | HIGH | 100 publications, many should mention drugs |

### Root Causes

1. **Missing source data:**
   - ChEMBL, OpenTargets not ingested → No drug-target relationships
   - Mechanism data not extracted → No drug-mechanism relationships

2. **Relationship extraction not implemented:**
   - Publications: Extract entities but relationships not created
   - SEC filings: Extract drugs but filing-drug links missing

3. **Cross-table inference missing:**
   - Company-drug: Should infer from trial relationships
   - Publication-entity: Should link based on text mentions

---

**End of Phase 3 Report**

---

# Phase 4: Entity Resolution Quality

**Generated:** 2025-11-09 11:38:40

Goal: Verify entity resolution is accurate and complete

---

## 1. Resolution Coverage by Source

### Overall Resolution Rates

| Source Name | Entities Extracted | Matched | Created | Match Rate | Creation Rate | Resolution Rate | Status |
|-------------|-------------------|---------|--------|------------|---------------|-----------------|--------|
| `clinicaltrials_gov` | 6,657 | 2,856 | 3,389 | 42.9% | 50.9% | 93.8% | ✅ Good |
| `openfda` | 172 | 19 | 149 | 11.0% | 86.6% | 97.7% | ✅ Good |
| `pubmed` | 100 | 0 | 100 | 0.0% | 100.0% | 100.0% | ✅ Good |
| `sec_edgar` | 100 | 56 | 44 | 56.0% | 44.0% | 100.0% | ✅ Good |

### ClinicalTrials.gov Deep Dive

- **Companies Extracted:** 0
- **Companies in Lineage:** 0
- **Company Resolution Rate:** 0.0%

- **Drugs Extracted:** 617
- **Drugs in Lineage:** 617
- **Drug Resolution Rate:** 9.3%

**Analysis:**
- 21% company resolution may be expected if many sponsors are institutions, not companies
- 61% drug resolution suggests some drug names aren't matching existing entities
- Consider: Are drug names being normalized correctly? Are aliases being created?

---

## 2. Match Candidate Review

### Overall Statistics

- **Total Match Candidates:** 488

**By Status:**
- needs_review: 488

**By Confidence Score:**
- 0.9: 1
- 0.8: 287
- 0.7: 200

- **High Confidence (≥0.8):** 189
- **Low Confidence (<0.6):** 0

### High Confidence Matches (≥0.8) - Should Be Auto-Merged?

| Source | Entity Type | Extracted Text | Confidence | Potential Matches |
|--------|------------|----------------|------------|-------------------|
| clinicaltrials_gov | disease | Traumatic Brain Injury... | 0.82 | 1 matches |
| clinicaltrials_gov | disease | Acute Lymphoblastic Leukemia... | 0.85 | 2 matches |
| clinicaltrials_gov | disease | Non-small Cell Lung Cancer... | 0.83 | 2 matches |
| clinicaltrials_gov | disease | High-grade B-cell Lymphoma (HGBCL)... | 0.84 | 1 matches |
| clinicaltrials_gov | disease | Acute Lymphoblastic Leukemia... | 0.85 | 2 matches |
| clinicaltrials_gov | disease | Squamous Cell Carcinoma... | 0.82 | 1 matches |
| clinicaltrials_gov | disease | Crohn's Disease... | 0.81 | 1 matches |
| clinicaltrials_gov | disease | Non-Small Cell Lung Cancer... | 0.83 | 2 matches |
| clinicaltrials_gov | institution | Xinhua Hospital, Shanghai Jiao Tong University Sch... | 0.80 | 1 matches |
| clinicaltrials_gov | disease | B-Non Hodgkin Lymphoma... | 0.82 | 2 matches |

**Recommendation:** If these are clearly correct matches, consider lowering auto-merge threshold to 0.8

---

## 3. Alias Quality Check

### Overall Alias Statistics

- **Total Aliases:** 4,675
- **Entities with Aliases:** 4,675
- **Average Aliases per Entity:** 1.00

- **Entities with Single Alias:** 4,675 ⚠️
- **Entities with Multiple Aliases:** 0 ✅

**⚠️ Warning:** Entities with only 1 alias may indicate:
- Alias creation not working properly
- Entities only seen from one source
- Missing canonical name alias

### Alias Types Distribution

| Alias Type | Count |
|------------|-------|
| original_name | 4,675 |

### Sample Aliases for Verification

| Entity Type | Alias Text | Alias Type | Entity ID |
|-------------|------------|------------|-----------|
| trial | Test Clinical Trial... | original_name | 79e59804... |
| company | Test Pharma... | original_name | b2b9f8f6... |
| drug | Test Drug ABC... | original_name | cb51415c... |
| disease | Cancer... | original_name | 5a641211... |
| trial | NBTXR3 and Radiation Therapy in Treating... | original_name | ea97963a... |
| company | Nanobiotix... | original_name | befe0826... |
| disease | Head and Neck Cancer... | original_name | be4f4e09... |
| trial | Study of the Disease Process of Lymphang... | original_name | 83fed1bb... |
| institution | National Heart, Lung, and Blood Institut... | original_name | 8bac3560... |
| disease | Lung Disease... | original_name | 25af4776... |
| disease | Pneumothorax... | original_name | d332f03c... |
| disease | Tuberous Sclerosis... | original_name | 18e72c9e... |
| disease | Lymphangioleiomyomatosis... | original_name | a58ec024... |
| trial | Primary Renal Lymphoma on a 48 Year Old ... | original_name | 124c9519... |
| institution | Instituto Mexicano del Seguro Social... | original_name | f9cbca1d... |

---

## 4. Sponsor Coverage Deep Dive

### Current State

- **Total Trial Sponsors:** 1,748
- **Company Sponsors:** 415
- **Institution Sponsors:** 1,333

- **Existing Company Entities:** 261
- **Missing Company Entities:** 0 ❌

- **Existing Institution Entities:** 872
- **Missing Institution Entities:** 0 ❌

- **Trials with Unresolved Sponsors:** 0

### Recommendations

1. **Investigate Missing Entities:**
   - Check if sponsor names are being extracted correctly
   - Verify entity resolution is running for sponsors
   - Check if new entities are being created when no match found

2. **Improve Institution Resolution:**
   - Ensure institutions are being extracted from trials
   - Create institution entities when not found
   - Add institution aliases for better matching

3. **Match Confidence Thresholds:**
   - Review if thresholds are too conservative
   - Consider auto-merging high-confidence matches (≥0.8)

---

## 5. Recommendations Summary

### Threshold Adjustments

1. **Auto-Merge Threshold:**
   - Current: High confidence (≥0.9) auto-merges
   - Recommendation: Lower to 0.8 for clearly correct matches
   - Impact: Reduce manual review queue, improve resolution rate

2. **Fuzzy Match Threshold:**
   - Current: 0.6-0.79 requires review
   - Recommendation: Auto-merge 0.75+ with context
   - Impact: Better handling of name variations

### Process Improvements

1. **Alias Creation:**
   - Ensure all extracted names become aliases
   - Create canonical name aliases for all entities
   - Track alias sources for better matching

2. **Entity Creation:**
   - Ensure new entities are created when no match found
   - Verify entity creation is logged in processing logs
   - Check for silent failures in entity creation

3. **Institution Handling:**
   - Improve institution extraction from trials
   - Create institution entities when missing
   - Add institution-specific matching rules

---

**End of Phase 4 Report**

---

# Phase 5: Scoring System Validation

**Generated:** 2025-11-09 11:38:40

Goal: Verify risk scores accurately reflect company risk

---

## 1. Score Component Analysis

**Sampled 20 companies with risk scores > 0**

### Component Verification Results

| Company | Risk Score | Failure Rate | Recent Failures | Stagnation | Warnings | Issues |
|---------|------------|--------------|----------------|------------|----------|--------|
| Novartis Pharmaceuticals... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| Bristol-Myers Squibb... | 26.0 | 0.0 | 20 | 0 | 6 | 0 ✅ |
| Medtronic Cardiac Ablation Sol... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| Aristea Therapeutics,... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| AstraZeneca... | 26.0 | 0.0 | 20 | 0 | 6 | 0 ✅ |
| Incyte... | 26.0 | 0.0 | 20 | 0 | 6 | 0 ✅ |
| EDAP TMS S.A.... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| Incyte Biosciences Internation... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| TikoMed AB... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| TG Therapeutics,... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| Spinal Stabilization Technolog... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| PharmaMar... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| Pfizer... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| Dermed Diagnostics,... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| Lisata Therapeutics,... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| AMS Advanced Medical Services... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| Sage Therapeutics... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| Actuate Therapeutics... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| EMD Serono Research & Developm... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |
| Forge Biologics,... | 12.0 | 0.0 | 10 | 0 | 2 | 0 ✅ |

### Analysis: Why 289/292 Companies (99%) Score 0-25 (LOW Risk)

**Reasons for LOW risk scores:**

- No failures: 28 companies
- No recent failures: 0 companies
- No pipeline stagnation: 28 companies
- No warning signals: 0 companies

**Conclusion:** Most companies have low scores because they have:
1. No or few terminated trials (low failure rate)
2. No recent failures in last 12 months
3. Recent pipeline activity (no stagnation)
4. No warning signals detected

---

## 2. Input Data Completeness

### Data Completeness Statistics

- **Total Companies:** 292
- **Companies with 0 Trials:** 31 (10.6%) ⚠️
- **Companies with 0 Events:** 230 (78.8%) ⚠️
- **Companies with < 3 Trials:** 240 (82.2%) ⚠️

### Impact on Scoring

**Companies with 0 Trials:**
- Cannot calculate failure rate (component = 0)
- Cannot detect pipeline stagnation (no trial dates)
- Risk score will be very low (0-10 points max from warnings/recent failures)

**Companies with 0 Events:**
- No warning signals detected
- No recent failures tracked
- Risk score will be low (only failure rate and stagnation contribute)

**Companies with < 3 Trials:**
- Failure rate may not be statistically significant
- Small sample size makes risk assessment unreliable

### Sample Companies with 0 Trials

| Company Name | Risk Score | Issue |
|--------------|------------|-------|
| Nanobiotix... | 0.0 | No trials to calculate failure rate |
| Rxhomeo Private Limited d.b.a. Rxhomeo,... | 0.0 | No trials to calculate failure rate |
| Atlantis Consumer Healthcare,... | 0.0 | No trials to calculate failure rate |
| Moderna,... | 0.0 | No trials to calculate failure rate |
| Lights Medical Manufacture Co.,... | 0.0 | No trials to calculate failure rate |
| Cipla USA Inc.,... | 0.0 | No trials to calculate failure rate |
| A-S Medication Solutions... | 0.0 | No trials to calculate failure rate |
| Amazon.com Services... | 0.0 | No trials to calculate failure rate |
| Village Pharma,... | 0.0 | No trials to calculate failure rate |
| Meijer Distribution,... | 0.0 | No trials to calculate failure rate |

---

## 3. Expected vs Actual Scoring

### Companies That SHOULD Be High Risk

| Company Name | Risk Score | Category | Reasons | Expected Category |
|--------------|------------|----------|---------|------------------|

---

## 4. Score Distribution Reasonableness

### Current Distribution

- **Total Companies Scored:** 292
- **Min Score:** 0.0
- **Max Score:** 26.0
- **Average Score:** 1.4
- **Median Score:** 0.0

**By Category:**
- LOW: 289 (99.0%)
- MODERATE: 3 (1.0%)

**By Score Range:**
- 0-9: 261 (89.4%)
- 10-19: 28 (9.6%)
- 20-29: 3 (1.0%)

### Analysis: Is Distribution Reasonable?

**Current State:** 89% of companies score 0-10 (essentially no risk)

**Expected Distribution:**
- Some companies should have MODERATE/HIGH risk
- Real-world biotech companies have varying risk levels
- Companies with multiple failures should score higher

### Root Cause Analysis

1. **Insufficient Input Data?**
   - 10.6% of companies have 0 trials → Cannot calculate failure rate
   - 78.8% of companies have 0 events → No warning signals
   - Impact: These companies will score 0-10 (only from stagnation if applicable)

2. **Scoring Weights Too Conservative?**
   - Current weights: Failure Rate (40), Recent Failures (30), Stagnation (20), Warnings (10)
   - A company needs:
     - 50%+ failure rate OR
     - 3+ recent failures OR
     - 2+ years stagnation
   - To score > 25 (MODERATE risk)
   - **Analysis:** Thresholds may be too high for real-world risk

3. **Missing Failure Events?**
   - Terminated trials in database: 0
   - Failure events in events table: 76
   - ✅ Event coverage appears complete

### Recommendations

1. **Adjust Scoring Thresholds:**
   - Lower MODERATE threshold to 15-20 (from 25)
   - Increase weight for single recent failure (from 10 to 15)
   - Add points for companies with 0 trials (unknown risk)

2. **Improve Event Coverage:**
   - Ensure all terminated trials have corresponding events
   - Backfill missing failure events

3. **Handle Data Sparsity:**
   - Companies with 0 trials: Assign 'UNKNOWN' risk category
   - Companies with < 3 trials: Flag as 'INSUFFICIENT_DATA'
   - Don't penalize companies for missing data

---

**End of Phase 5 Report**

---

# Phase 6: UI Data Accuracy

**Generated:** 2025-11-09 11:38:46

Goal: Ensure dashboard displays correct data from database

---

## 1. API Response Validation

### Testing API Endpoints for 5 Random Companies

| Company | Risk Profile | Metrics | Timeline | Overall |
|---------|--------------|---------|----------|---------|
| EM Cosmetics | ✅ | ✅ | ✅ | ✅ |
| Acella Pharmaceuticals, | ✅ | ✅ | ✅ | ✅ |
| Daiichi Sankyo | ✅ | ✅ | ❌ | ❌ |
| Rui Therapeutics Co., | ✅ | ✅ | ❌ | ❌ |
| Chongqing Precision Biotech Co... | ✅ | ✅ | ❌ | ❌ |

### ⚠️ API Response Issues

#### Daiichi Sankyo

**Timeline Issues:**
- Event count mismatch: API=2, DB=1
- Extra events in API: ['e19c957f-c91b-4e76-af88-a9ea75cc787b']

#### Rui Therapeutics Co.,

**Timeline Issues:**
- Event count mismatch: API=1, DB=0
- Extra events in API: ['b9c419d0-245b-4640-a001-3edddb7e7db8']

#### Chongqing Precision Biotech Co.,

**Timeline Issues:**
- Event count mismatch: API=1, DB=0
- Extra events in API: ['ecb51c13-0ee0-43a0-bf0c-4735c9eb41c1']

---

## 2. Failed Trials List Accuracy

### Database vs API Comparison

- **Database Events (last 90 days):** 76
- **API Response Count:** 50
- **Match Status:** ✅ Match

### Entity Enrichment Issues

- Event 819851b1-41d8-40ef-8ce1-10377a233589: Missing company enrichment
- Event 28a8bd2f-d29e-44d5-855c-e357ea20e728: Missing company enrichment
- Event 6ceb3abd-1f31-40cf-abc6-6321750c273c: Missing company enrichment
- Event a3111ace-5ffd-4f81-a46d-bd4f9343444a: Missing company enrichment
- Event 6a8b502b-8851-4fe4-b0f7-38f380327f09: Missing company enrichment
- Event db9ec29b-33ec-4b6a-9c7d-0334b277cf8b: Missing company enrichment

### Entity Enrichment Verification

**Expected Enrichment:**
- Company details (name, ID)
- Trial details (if applicable)
- Drug details (if applicable)
- Disease details (if applicable)

**Enrichment Coverage (sample of 5):**
- Companies enriched: 2/5
- Trials enriched: 5/5
- Drugs enriched: 0/5
- Diseases enriched: 0/5

---

## 3. Company Search Functionality

### Search Test Results

| Test | Status | Issues |
|------|--------|--------|
| Name Search | ✅ Pass | 0 |
| Risk Category Filter | ✅ Pass | 0 |
| Therapeutic Area Filter | ✅ Pass | 0 |
| Risk Score Consistency | ✅ Pass | 0 |

---

## 4. Timeline Visualization Data

### Timeline Data Validation

| Validation | Status | Issues |
|------------|--------|--------|
| Date Ranges | ✅ Pass | 0 |
| Event Significance | ✅ Pass | 0 |
| Event Ordering | ✅ Pass | 0 |

### Timeline Data Requirements

**Expected Behavior:**
- Events ordered by date (descending)
- Date ranges are reasonable (no future dates, not too old)
- Event significance levels are valid (critical, major, minor, trace)
- All events for company are included

---

**End of Phase 6 Report**

---

# Phase 7: Critical Gaps Assessment

**Generated:** 2025-11-09 11:38:47

Goal: Identify what's missing for failure detection to work

---

## 1. Failure Signal Coverage

### Expected Failure Signal Types

| Signal Type | Expected | Present | Count | Status |
|-------------|----------|---------|-------|--------|
| trial.status.terminated | Yes | Yes | 59 | ✅ Present |
| trial.status.withdrawn | Yes | Yes | 17 | ✅ Present |
| regulatory.clinical_hold | Yes | No | 0 | ❌ Missing |
| program.milestone.rejected | Yes | No | 0 | ❌ Missing |
| program.discontinued | Yes | No | 0 | ❌ Missing |
| corporate.restructuring | Yes | No | 0 | ❌ Missing |
| corporate.layoff | Yes | No | 0 | ❌ Missing |
| regulatory.rejection | Yes | No | 0 | ❌ Missing |

**Total Failure Events:** 76

### ⚠️ Missing Failure Signal Types

- `regulatory.clinical_hold` - Not found in events table
- `program.milestone.rejected` - Not found in events table
- `program.discontinued` - Not found in events table
- `corporate.restructuring` - Not found in events table
- `corporate.layoff` - Not found in events table
- `regulatory.rejection` - Not found in events table

**Impact:**
- These failure types cannot be detected or tracked
- Risk scoring will miss these failure modes
- Dashboard will not show these failure signals

---

## 2. Early Warning Signal Gaps

### Early Warning Signal Coverage

| Signal Type | Expected | Present | Count | Source Status |
|-------------|----------|---------|-------|---------------|
| Warn Notices | Yes | No | 0 | not_registered |
| Layoff Signals | Yes | No | 0 | N/A |
| Fda Warning Letters | Yes | No | 0 | not_registered |
| Clinical Holds | Yes | No | 0 | N/A |
| Fda Approvals | Yes | No | 0 | N/A |
| Fda Rejections | Yes | No | 0 | N/A |

**Overall Coverage:** 0.0%

### Detailed Analysis

**WARN Notices:** ❌ Source not registered
- WARN notices indicate mass layoffs (strong failure signal)
- No ingestion script found for WARN data
- **Priority: HIGH** - Critical early warning signal

**Layoff Signals:** ❌ No layoff events in database
- Corporate layoffs are major financial distress signals
- Should be captured as `corporate.layoff` events
- **Priority: MEDIUM** - Important but may be captured via WARN

**FDA Warning Letters:** ❌ Source not registered
- FDA warning letters indicate regulatory issues
- Strong early warning signal for compliance failures
- **Priority: HIGH** - Regulatory risk indicator

**Clinical Holds:** ❌ Not found in events
- Clinical holds are critical regulatory failure signals
- Should be captured as `regulatory.clinical_hold` events
- **Priority: CRITICAL** - Direct failure indicator

---

## 3. Regulatory Events Gap

### Regulatory Events Table Status

- **Table Exists:** ❌ No
- **Row Count:** 0

### ⚠️ Regulatory Events Table is Empty

**Expected Data Types:**

- Approvals: ❌ 0 (in events table)
- Rejections: ❌ 0 (in events table)
- Clinical Holds: ❌ 0 (in events table)
- Breakthrough Designations: ❌ 0 (in events table)
- Orphan Designations: ❌ 0 (in events table)

**Regulatory Events in Events Table:**
- Total regulatory events: 0

### Why Regulatory Events Aren't Being Captured

**No regulatory sources found**

**Root Cause Analysis:**
1. Regulatory events may be captured in `events` table instead of `regulatory_events`
2. Regulatory sources may not be running (FDA approvals, rejections, etc.)
3. Event extraction logic may not be creating regulatory events

**Impact:**
- Cannot query regulatory events separately from other events
- Regulatory event-specific fields may be missing
- Regulatory timeline analysis is limited

---

## 4. Patent/IP Intelligence Gap

### Patent Tables Status

| Table | Row Count | Expected | Status |
|-------|-----------|----------|--------|
| Patents Table | 0 | Yes | ❌ Empty |
| Patent Drugs Table | 0 | Yes | ❌ Empty |
| Patent Companies Table | 0 | Yes | ❌ Empty |

### ⚠️ Patent Tables Are Empty

**Expected Data:**
- Patent records (patent numbers, filing dates, expiration dates)
- Patent-drug relationships (which drugs are covered by patents)
- Patent-company relationships (which companies own patents)

**No patent sources found**

### Impact on Failure Detection


**Additional Impacts:**
- Cannot assess IP protection status of programs
- Cannot identify when exclusivity expires (generic competition risk)
- Cannot track competitive IP landscape
- Missing critical data for program valuation

---

## 5. Prioritized Gaps Summary

### CRITICAL Priority (Blocks Failure Detection)

1. Clinical holds not captured - direct failure indicator missing
2. No regulatory events captured - approvals/rejections/holds missing
3. Patent data missing - cannot assess IP protection and exclusivity

### HIGH Priority (Significantly Impacts Failure Detection)

1. WARN notices not being captured - mass layoff signals missing
2. FDA warning letters not being captured - regulatory risk signals missing
3. Missing failure signal types: regulatory.clinical_hold, program.milestone.rejected, program.discontinued

### MEDIUM Priority (Enhances Failure Detection)

1. Layoff events not captured (may be covered by WARN notices)
2. Additional missing failure signal types: 3 more

### Recommendations

1. **Activate Regulatory Sources:**
   - Register and activate FDA data sources (approvals, rejections, clinical holds)
   - Ensure event extraction creates regulatory events

2. **Register WARN Notice Source:**
   - Create ingestion script for WARN notices
   - Register source and activate
   - Extract as `corporate.layoff` events

3. **Activate Patent Sources:**
   - Register patent data sources (USPTO, PatentsView)
   - Extract patent-drug and patent-company relationships
   - Capture expiration dates for exclusivity analysis

4. **Complete Failure Signal Types:**
   - Ensure all failure event types are being captured
   - Add missing event types to event extraction logic

---

**End of Phase 7 Report**
