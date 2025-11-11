# Source Inventory Report

**Generated:** 2025-11-09 11:17:57

---

## Summary

- **Total Sources Implemented:** 82
- **Active Sources:** 5
- **Inactive Sources:** 0
- **Failing Sources:** 0
- **Sources with No Data:** 1
- **Not Configured in DB:** 76

---

## Active Sources

| Source Name | Type | Last Successful Run | Records (Last Run) | Total Records | Records (30d) | Status |
|-------------|------|---------------------|-------------------|---------------|---------------|--------|
| clinicaltrials_gov | clinical | 2025-11-09 | 818 | 1,018 | 1,018 | ✅ Active |
| openfda | regulatory | 2025-11-07 | 100 | 100 | 100 | ✅ Active |
| pubmed | literature | 2025-11-07 | 100 | 100 | 100 | ✅ Active |
| sec_edgar | financial | 2025-11-07 | 50 | 50 | 50 | ✅ Active |
| fda_drugs | regulatory | Never | N/A | 9 | 9 | ✅ Active |

---

## Sources with No Data

| Source Name | Type | Last Run | Last Status | Notes |
|-------------|------|----------|-------------|-------|
| patentsview | patent | Never | Never run | No records in staging table |

---

## Sources Not Configured in Database

These sources have ingestion scripts but are not registered in the `sources` table.

| Source Name | Inferred Type | Total Records | Notes |
|-------------|---------------|---------------|-------|
| alphavantage | financial | 0 | Not registered in sources table |
| anvisa_brazil | regulatory | 0 | Not registered in sources table |
| arxiv | literature | 0 | Not registered in sources table |
| asco_abstracts | conference | 0 | Not registered in sources table |
| barda | funding | 0 | Not registered in sources table |
| biogrid | scientific | 0 | Not registered in sources table |
| biorxiv | literature | 0 | Not registered in sources table |
| biospace_layoff_tracker | employment | 0 | Not registered in sources table |
| calcbench | financial | 0 | Not registered in sources table |
| california_warn | employment | 0 | Not registered in sources table |
| cdsco_india | regulatory | 0 | Not registered in sources table |
| chembl | scientific | 0 | Not registered in sources table |
| chemrxiv | literature | 0 | Not registered in sources table |
| clingen | scientific | 0 | Not registered in sources table |
| clinvar | scientific | 0 | Not registered in sources table |
| darpa | funding | 0 | Not registered in sources table |
| disgenet | scientific | 0 | Not registered in sources table |
| dod_contracts | funding | 0 | Not registered in sources table |
| ema_epar | regulatory | 0 | Not registered in sources table |
| ema_guidelines | regulatory | 0 | Not registered in sources table |
| ema_prime | regulatory | 0 | Not registered in sources table |
| ema_trials | regulatory | 0 | Not registered in sources table |
| europe_pmc | literature | 0 | Not registered in sources table |
| fda_breakthrough | regulatory | 0 | Not registered in sources table |
| fda_clinical_hold | regulatory | 0 | Not registered in sources table |
| fda_eua | regulatory | 0 | Not registered in sources table |
| fda_expanded_access | regulatory | 0 | Not registered in sources table |
| fda_faers | regulatory | 0 | Not registered in sources table |
| fda_guidance | regulatory | 0 | Not registered in sources table |
| fda_orange_book | regulatory | 0 | Not registered in sources table |
| fda_orphan | regulatory | 0 | Not registered in sources table |
| fda_purple_book | regulatory | 0 | Not registered in sources table |
| fda_warning_letters | regulatory | 0 | Not registered in sources table |
| federal_warn | employment | 0 | Not registered in sources table |
| fierce_layoff_tracker | employment | 0 | Not registered in sources table |
| google_news | social | 0 | Not registered in sources table |
| health_canada | regulatory | 0 | Not registered in sources table |
| hsa_singapore | regulatory | 0 | Not registered in sources table |
| ich_guidelines | regulatory | 0 | Not registered in sources table |
| illinois_warn | employment | 0 | Not registered in sources table |
| massachusetts_warn | employment | 0 | Not registered in sources table |
| medrxiv | literature | 0 | Not registered in sources table |
| mfds_korea | regulatory | 0 | Not registered in sources table |
| mhra_uk | regulatory | 0 | Not registered in sources table |
| motley_fool | other | 0 | Not registered in sources table |
| new_jersey_warn | employment | 0 | Not registered in sources table |
| new_york_warn | employment | 0 | Not registered in sources table |
| nice_uk | regulatory | 0 | Not registered in sources table |
| nih_reporter | funding | 0 | Not registered in sources table |
| nsf_awards | funding | 0 | Not registered in sources table |
| omim | scientific | 0 | Not registered in sources table |
| openfigi | financial | 0 | Not registered in sources table |
| opentargets | scientific | 0 | Not registered in sources table |
| orphanet | scientific | 0 | Not registered in sources table |
| pennsylvania_warn | employment | 0 | Not registered in sources table |
| pmc | literature | 0 | Not registered in sources table |
| pubchem | scientific | 0 | Not registered in sources table |
| pubtator | literature | 0 | Not registered in sources table |
| reactome | scientific | 0 | Not registered in sources table |
| reddit_biotech | social | 0 | Not registered in sources table |
| rss_news | social | 0 | Not registered in sources table |
| sbir | funding | 0 | Not registered in sources table |
| seeking_alpha | other | 0 | Not registered in sources table |
| semantic_scholar | regulatory | 0 | Not registered in sources table |
| string_db | scientific | 0 | Not registered in sources table |
| swissmedic | regulatory | 0 | Not registered in sources table |
| texas_warn | employment | 0 | Not registered in sources table |
| tga_australia | regulatory | 0 | Not registered in sources table |
| uniprot | scientific | 0 | Not registered in sources table |
| uspto_public_pair | patent | 0 | Not registered in sources table |
| vaers | other | 0 | Not registered in sources table |
| wayback_machine | other | 0 | Not registered in sources table |
| who_ictrp | regulatory | 0 | Not registered in sources table |
| who_outbreak_news | regulatory | 0 | Not registered in sources table |
| xtalks_layoff | employment | 0 | Not registered in sources table |
| youtube_biotech | social | 0 | Not registered in sources table |

---

## Detailed Statistics

### Sources by Type

- **regulatory**: 29
- **scientific**: 12
- **employment**: 11
- **literature**: 8
- **funding**: 6
- **financial**: 4
- **social**: 4
- **other**: 4
- **patent**: 2
- **conference**: 1
- **clinical**: 1

### Top 10 Sources by Total Records

| Rank | Source Name | Total Records |
|------|-------------|---------------|
| 1 | clinicaltrials_gov | 1,018 |
| 2 | openfda | 100 |
| 3 | pubmed | 100 |
| 4 | sec_edgar | 50 |
| 5 | fda_drugs | 9 |
| 6 | alphavantage | 0 |
| 7 | anvisa_brazil | 0 |
| 8 | arxiv | 0 |
| 9 | asco_abstracts | 0 |
| 10 | barda | 0 |

### Most Active Sources (Last 30 Days)

| Rank | Source Name | Records (30d) |
|------|-------------|---------------|
| 1 | clinicaltrials_gov | 1,018 |
| 2 | openfda | 100 |
| 3 | pubmed | 100 |
| 4 | sec_edgar | 50 |
| 5 | fda_drugs | 9 |

---

# Database Schema Report

**Generated:** 2025-11-09 11:17:57

---

## Summary

- **Total Tables:** 54
- **Total Rows Across All Tables:** 22,962
- **Empty Tables:** 33
- **Small Tables (< 10 rows):** 3

---

## All Tables and Row Counts

| Table Name | Row Count | Category |
|------------|-----------|----------|
| entity_aliases | 4,675 | resolution |
| data_lineage | 3,388 | infrastructure |
| trial_diseases | 2,085 | relationship |
| trial_sponsors | 1,748 | relationship |
| diseases | 1,477 | entity |
| staging_raw_data | 1,277 | staging |
| source_processing_log | 1,269 | resolution |
| trial_drugs | 1,228 | relationship |
| events | 1,059 | infrastructure |
| clinical_trials | 1,017 | clinical |
| trial_status_history | 1,011 | clinical |
| institutions | 887 | entity |
| drugs | 854 | entity |
| entity_match_candidates | 488 | resolution |
| companies | 292 | entity |
| publications | 100 | publication |
| sec_filings | 49 | publication |
| filing_companies | 49 | relationship |
| sources | 6 | infrastructure |
| company_drugs | 2 | relationship |
| alembic_version | 1 | other |
| drug_combinations | 0 | relationship |
| entity_matches | 0 | resolution |
| entity_match_confidence | 0 | resolution |
| matching_review_queue | 0 | resolution |
| drug_chemical_identity | 0 | entity |
| drug_names | 0 | entity |
| disease_names | 0 | entity |
| conferences | 0 | publication |
| conference_presentations | 0 | publication |
| company_ownership_history | 0 | relationship |
| targets | 0 | entity |
| mechanisms | 0 | entity |
| drug_ownership_history | 0 | relationship |
| drug_targets | 0 | relationship |
| drug_mechanisms | 0 | relationship |
| trial_funding | 0 | relationship |
| regulatory_events | 0 | clinical |
| patents | 0 | publication |
| publication_trials | 0 | relationship |
| publication_companies | 0 | relationship |
| patent_drugs | 0 | relationship |
| patent_companies | 0 | relationship |
| drug_indications | 0 | relationship |
| publication_drugs | 0 | relationship |
| regulatory_drug_events | 0 | relationship |
| regulatory_company_events | 0 | relationship |
| presentation_drugs | 0 | relationship |
| presentation_companies | 0 | relationship |
| presentation_trials | 0 | relationship |
| filing_drugs | 0 | relationship |
| entity_matching_rules | 0 | resolution |
| data_quality_metrics | 0 | resolution |
| entity_merges | 0 | infrastructure |

---

## Staging vs Production Tables

### Staging Tables

| Table Name | Row Count |
|------------|-----------|
| staging_raw_data | 1,277 |

**Staging Total:** 1,277 rows
**Production Total:** 17,232 rows

---

## Entity Tables

| Table Name | Row Count | Description |
|------------|-----------|------------|
| companies | 292 | Biotech/pharma companies |
| disease_names | 0 | Disease name variations |
| diseases | 1,477 | Disease entities |
| drug_chemical_identity | 0 | Drug chemical identifiers |
| drug_names | 0 | Drug name variations |
| drugs | 854 | Drug entities |
| institutions | 887 | Academic/hospital/research institutions |
| mechanisms | 0 | Drug mechanisms of action |
| targets | 0 | Biological targets (proteins, genes) |

**Entity Tables Total:** 3,510 rows

---

## Relationship/Edge Tables

| Table Name | Row Count | Description |
|------------|-----------|------------|
| company_drugs | 2 | Company-drug associations |
| company_ownership_history | 0 | Company ownership relationships |
| drug_combinations | 0 | Drug combination therapies |
| drug_indications | 0 | Drug-disease indications |
| drug_mechanisms | 0 | Drug-mechanism relationships |
| drug_ownership_history | 0 | Drug ownership history |
| drug_targets | 0 | Drug-target relationships |
| filing_companies | 49 | SEC filing-company links |
| filing_drugs | 0 | SEC filing-drug mentions |
| patent_companies | 0 | Patent-company associations |
| patent_drugs | 0 | Patent-drug associations |
| presentation_companies | 0 | Conference presentation-company links |
| presentation_drugs | 0 | Conference presentation-drug links |
| presentation_trials | 0 | Conference presentation-trial links |
| publication_companies | 0 | Publication-company mentions |
| publication_drugs | 0 | Publication-drug mentions |
| publication_trials | 0 | Publication-trial references |
| regulatory_company_events | 0 | Regulatory events for companies |
| regulatory_drug_events | 0 | Regulatory events for drugs |
| trial_diseases | 2,085 | Trial-disease relationships |
| trial_drugs | 1,228 | Trial-drug relationships |
| trial_funding | 0 | Trial funding sources |
| trial_sponsors | 1,748 | Trial sponsor relationships |

**Relationship Tables Total:** 5,112 rows

---

## Clinical Tables

| Table Name | Row Count | Description |
|------------|-----------|------------|
| clinical_trials | 1,017 | Clinical trial records |
| regulatory_events | 0 | Regulatory events (approvals, rejections, etc.) |
| trial_status_history | 1,011 | Trial status change history |

**Clinical Tables Total:** 2,028 rows

---

## Publication Tables

| Table Name | Row Count | Description |
|------------|-----------|------------|
| conference_presentations | 0 | Conference presentations |
| conferences | 0 | Conference records |
| patents | 0 | Patent records |
| publications | 100 | Scientific publications |
| sec_filings | 49 | SEC filing records |

**Publication Tables Total:** 149 rows

---

## Empty or Suspiciously Small Tables

### Empty Tables (0 rows)

| Table Name | Category |
|------------|----------|
| company_ownership_history | relationship |
| conference_presentations | publication |
| conferences | publication |
| data_quality_metrics | resolution |
| disease_names | entity |
| drug_chemical_identity | entity |
| drug_combinations | relationship |
| drug_indications | relationship |
| drug_mechanisms | relationship |
| drug_names | entity |
| drug_ownership_history | relationship |
| drug_targets | relationship |
| entity_match_confidence | resolution |
| entity_matches | resolution |
| entity_matching_rules | resolution |
| entity_merges | infrastructure |
| filing_drugs | relationship |
| matching_review_queue | resolution |
| mechanisms | entity |
| patent_companies | relationship |
| patent_drugs | relationship |
| patents | publication |
| presentation_companies | relationship |
| presentation_drugs | relationship |
| presentation_trials | relationship |
| publication_companies | relationship |
| publication_drugs | relationship |
| publication_trials | relationship |
| regulatory_company_events | relationship |
| regulatory_drug_events | relationship |
| regulatory_events | clinical |
| targets | entity |
| trial_funding | relationship |

### Small Tables (< 10 rows)

| Table Name | Row Count | Category |
|------------|-----------|----------|
| alembic_version | 1 | other |
| company_drugs | 2 | relationship |
| sources | 6 | infrastructure |

---

## Infrastructure Tables

| Table Name | Row Count | Description |
|------------|-----------|------------|
| data_lineage | 3,388 | Data provenance tracking |
| entity_merges | 0 | Entity merge audit trail |
| events | 1,059 | Event stream records |
| sources | 6 | Data source metadata |

---

## Entity Resolution Tables

| Table Name | Row Count | Description |
|------------|-----------|------------|
| data_quality_metrics | 0 | Data quality statistics |
| entity_aliases | 4,675 | Entity alias mappings |
| entity_match_candidates | 488 | Potential matches |
| entity_match_confidence | 0 | Match confidence scores |
| entity_matches | 0 | Entity match records |
| entity_matching_rules | 0 | Matching rules configuration |
| matching_review_queue | 0 | Matches pending review |
| source_processing_log | 1,269 | Source processing audit log |

**Resolution Tables Total:** 6,432 rows

---

# Data Pipeline Flow Report

**Generated:** 2025-11-09 11:17:57

This report traces the flow of data through the pipeline for key entity types.

---

## Overall Pipeline Statistics

- **Total Records in Staging:** 1,277
- **Processed Records:** 1,268 (99.3%)
- **Unprocessed Records:** 9 (0.7%)

---

## Companies Flow

### Funnel Analysis

| Stage | Count | % of Previous | % of Initial |
|-------|-------|--------------|-------------|
| **1. Raw Records in Staging** | 1,277 | 100.0% | 100.0% |
| **2. Processed Records** | 1,268 | 99.3% | 99.3% |
| **3. Resolved Entities Created** | 292 | 17.0% | 16.9% |
| **4. Relationships Created** | 2 | 0.7% | 0.2% |

### Loss Analysis

- **Lost at Stage 2 (Not Processed):** 9 (0.7%)
  - Records in staging but not yet processed
- **Lost at Stage 3 (No Entity Created):** 976 (76.4%)
  - Records processed but no entity created (may be duplicates, validation failures, etc.)

### Breakdown by Source

| Source | Staging Records | Processed | Unprocessed | Entities Created |
|--------|----------------|------------|-------------|------------------|
| clinicaltrials_gov | 1,018 | 1,018 | 0 | 216 |
| sec_edgar | 50 | 50 | 0 | 0 |
| fda_drugs | 9 | 0 | 9 | 0 |
| openfda | 100 | 100 | 0 | 0 |
| pubmed | 100 | 100 | 0 | 0 |

---

## Drugs Flow

### Funnel Analysis

| Stage | Count | % of Previous | % of Initial |
|-------|-------|--------------|-------------|
| **1. Raw Records in Staging** | 1,227 | 100.0% | 100.0% |
| **2. Processed Records** | 1,218 | 99.3% | 99.3% |
| **3. Resolved Entities Created** | 854 | 50.7% | 50.3% |
| **4. Relationships Created** | 1,228 | 143.8% | 100.1% |

### Loss Analysis

- **Lost at Stage 2 (Not Processed):** 9 (0.7%)
  - Records in staging but not yet processed
- **Lost at Stage 3 (No Entity Created):** 364 (29.7%)
  - Records processed but no entity created (may be duplicates, validation failures, etc.)

### Breakdown by Source

| Source | Staging Records | Processed | Unprocessed | Entities Created |
|--------|----------------|------------|-------------|------------------|
| clinicaltrials_gov | 1,018 | 1,018 | 0 | 617 |
| fda_drugs | 9 | 0 | 9 | 0 |
| openfda | 100 | 100 | 0 | 0 |
| pubmed | 100 | 100 | 0 | 0 |

---

## Trials Flow

### Funnel Analysis

| Stage | Count | % of Previous | % of Initial |
|-------|-------|--------------|-------------|
| **1. Raw Records in Staging** | 1,018 | 100.0% | 100.0% |
| **2. Processed Records** | 1,018 | 100.0% | 100.0% |
| **3. Resolved Entities Created** | 1,017 | 79.8% | 79.8% |
| **4. Relationships Created** | 5,061 | 497.2% | 497.2% |

### Loss Analysis

- **Lost at Stage 2 (Not Processed):** 0 (0.0%)
- **Lost at Stage 3 (No Entity Created):** 1 (0.1%)
  - Records processed but no entity created (may be duplicates, validation failures, etc.)

### Breakdown by Source

| Source | Staging Records | Processed | Unprocessed | Entities Created |
|--------|----------------|------------|-------------|------------------|
| clinicaltrials_gov | 1,018 | 1,018 | 0 | 812 |

---

## Trial Relationships Breakdown

| Relationship Type | Count | Avg per Trial |
|-------------------|-------|---------------|
| Trial Sponsors | 1,748 | 1.7 |
| Trial Drugs | 1,228 | 1.2 |
| Trial Diseases | 2,085 | 2.1 |

---

## Processing Errors Analysis

- **Staging Records with Processing Errors:** 0
- **Failed Processing Logs:** 0

✅ No processing errors found.

---

# Entity Resolution Coverage Report

**Generated:** 2025-11-09 11:17:57

This report shows entity resolution coverage metrics and identifies unresolved records.

---

## Overall Resolution Statistics

- **Total Entities:** 4,527
- **Entities with Aliases:** 4,526
- **Entities Tracked in Lineage:** 3,388
- **Match Candidates:** 488
- **In Review Queue:** 0

---

## Coverage by Entity Type

| Entity Type | Total Entities | With Aliases | In Lineage | Alias Coverage | Lineage Coverage |
|-------------|----------------|--------------|------------|----------------|------------------|
| company | 292 | 292 | 216 | 100.0% | 74.0% |
| drug | 854 | 853 | 617 | 99.9% | 72.2% |
| disease | 1,477 | 1,477 | 1,072 | 100.0% | 72.6% |
| trial | 1,017 | 1,017 | 812 | 100.0% | 79.8% |
| institution | 887 | 887 | 671 | 100.0% | 75.6% |

---

## Resolution Success Rate from Processing

### Processing Status

| Status | Count | Percentage |
|--------|-------|------------|
| Success | 1,269 | 100.0% |
| Failed | 0 | 0.0% |
| Needs Review | 0 | 0.0% |

### Entity Extraction & Resolution

| Metric | Count |
|--------|-------|
| Total Entities Extracted | 7,029 |
| Entities Matched (Existing) | 2,931 |
| Entities Created (New) | 3,682 |

- **Match Rate:** 41.7%
- **Creation Rate:** 52.4%
- **Total Resolution Rate:** 94.1%

---

## Failed Resolution Analysis

✅ No failed processing logs found.

### Match Candidates by Entity Type

| Entity Type | Count |
|-------------|-------|
| company | 1 |
| drug | 49 |
| disease | 373 |
| trial | 8 |
| institution | 57 |

---

## Examples of Unresolved Records

### Match Candidates (Needs Review)

#### Example 1: disease

- **Extracted Text:** Spinocerebellar Ataxia Type 3
- **Source:** clinicaltrials_gov
- **Source Identifier:** NCT03701399
- **Potential Matches Found:** 1
- **Status:** needs_review
- **Match Confidence:** 0.74

#### Example 2: disease

- **Extracted Text:** Spinocerebellar Ataxia Type 8
- **Source:** clinicaltrials_gov
- **Source Identifier:** NCT03701399
- **Potential Matches Found:** 1
- **Status:** needs_review
- **Match Confidence:** 0.74

#### Example 3: disease

- **Extracted Text:** Spinocerebellar Ataxia Type 10
- **Source:** clinicaltrials_gov
- **Source Identifier:** NCT03701399
- **Potential Matches Found:** 1
- **Status:** needs_review
- **Match Confidence:** 0.76

#### Example 4: disease

- **Extracted Text:** Spinocerebellar Ataxia Type 6
- **Source:** clinicaltrials_gov
- **Source Identifier:** NCT03701399
- **Potential Matches Found:** 1
- **Status:** needs_review
- **Match Confidence:** 0.74

#### Example 5: disease

- **Extracted Text:** Spinocerebellar Ataxia Type 2
- **Source:** clinicaltrials_gov
- **Source Identifier:** NCT03701399
- **Potential Matches Found:** 1
- **Status:** needs_review
- **Match Confidence:** 0.74

✅ No staging records with processing errors found.
---

## Resolution Quality Metrics

- **Total Match Candidates:** 488
  - Note: Confidence scores are stored in potential_matches JSONB field

---

## Entity Aliases Statistics

- **Total Aliases:** 4,675

### Aliases by Entity Type

| Entity Type | Alias Count | Avg per Entity |
|-------------|-------------|----------------|
| company | 292 | 1.0 |
| drug | 853 | 1.0 |
| disease | 1,477 | 1.0 |
| trial | 1,017 | 1.0 |
| institution | 887 | 1.0 |

---

# Scoring System Report

**Generated:** 2025-11-09 11:17:57

This report documents the scoring system implementation and current score distribution.

---

## Scoring System Location

### Primary Implementation

- **File:** `src/services/company_risk_service.py`
- **Class:** `CompanyRiskService`
- **Main Function:** `calculate_company_risk_score(company_id: UUID)`

### Supporting Files

- **API Routes:** `src/api/routes/company_risk.py`
- **Data Models:** `src/api/models/company_risk.py`
- **Cache Configuration:** `src/services/cache_config.py`
- **Database View:** `database/migrations/versions/f1a2b3c4d5e6_add_company_risk_metrics_view.py`

---

## Scoring Algorithm

### Score Range
- **Range:** 0-100
- **Higher score = Higher risk**

### Component Weights

| Component | Weight | Description |
|-----------|--------|-------------|
| Failure Rate | 40 points | Historical trial termination rate |
| Recent Failures | 30 points | Failures in last 12 months |
| Pipeline Stagnation | 20 points | Days since last pipeline update |
| Warning Signals | 10 points | Early warning indicators |
| **Total** | **100 points** | |

### Risk Categories

| Category | Score Range |
|----------|-------------|
| LOW | 0-25 |
| MODERATE | 25-50 |
| HIGH | 50-75 |
| CRITICAL | 75-100 |

---

## Scoring System Inputs

The scoring system uses the following data sources:

### 1. Company Metrics (from `get_company_metrics()`)

- **Source:** `CompanyRiskService.get_company_metrics()`
- **Data Sources:**
  - `companies` table - Company information
  - `clinical_trials` table - Trial records
  - `trial_sponsors` table - Company-trial relationships
  - `events` table - Pipeline events

- **Metrics Calculated:**
  - Total trials count
  - Active trials count
  - Terminated trials count
  - Success rates by phase (Phase 1, 2, 3)
  - Pipeline velocity (new programs per year)
  - Days since last pipeline update
  - Failure clustering patterns

### 2. Recent Failure Events

- **Source:** `FailureAnalysisService.get_program_events()`
- **Data Source:** `events` table
- **Event Types Tracked:**
  - `trial.status.terminated`
  - `trial.status.withdrawn`
  - `regulatory.clinical_hold`
- **Time Window:** Last 12 months

### 3. Warning Signals

- **Source:** `CompanyRiskService._get_warning_signals()`
- **Signals Detected:**
  - Layoff announcements
  - Clinical holds
  - Regulatory warnings
  - Pipeline stagnation

---

## Scoring System Outputs

The scoring system produces the following outputs:

### Primary Output: Risk Score

- **Field:** `risk_score`
- **Type:** `float`
- **Range:** 0.0 - 100.0
- **Description:** Composite risk score calculated from all components

### Secondary Outputs

1. **Risk Category** (`risk_category`)
   - Values: `LOW`, `MODERATE`, `HIGH`, `CRITICAL`
   - Derived from risk score range

2. **Component Breakdown** (`components`)
   - `failure_rate`: Score, weight, and details
   - `recent_failures`: Score, weight, and details
   - `pipeline_stagnation`: Score, weight, and details
   - `warning_signals`: Score, weight, and details

3. **Metadata**
   - `company_id`: Company UUID
   - `company_name`: Company name
   - `calculated_at`: ISO timestamp of calculation

### Storage

- **Primary Storage:** Calculated on-demand (not stored in database)
- **Caching:** Redis cache with key `risk_score:{company_id}`
- **Cache TTL:** 1 hour (configurable via `CacheTTL.RISK_SCORE`)
- **Materialized View:** `company_risk_metrics` (contains metrics, not scores)

---

## Current Score Distribution

Calculating risk scores for all companies...

- **Total Companies:** 292
- **Companies with Scores:** 292 (100.0%)
- **Companies with Errors:** 0

### Score Statistics

| Metric | Value |
|--------|-------|
| Minimum | 0.00 |
| Maximum | 26.00 |
| Average | 1.42 |
| Median | 0.00 |

### Distribution by Risk Category

| Category | Count | Percentage | Avg Score | Min Score | Max Score |
|----------|-------|------------|-----------|------------|----------|
| LOW | 289 | 99.0% | 1.16 | 0.00 | 12.00 |
| MODERATE | 3 | 1.0% | 26.00 | 26.00 | 26.00 |
| HIGH | 0 | 0.0% | N/A | N/A | N/A |
| CRITICAL | 0 | 0.0% | N/A | N/A | N/A |

### Score Distribution (Histogram)

| Score Range | Count | Percentage |
|-------------|-------|------------|
| 0-10 | 261 | 89.4% |
| 10-20 | 28 | 9.6% |
| 20-30 | 3 | 1.0% |
| 30-40 | 0 | 0.0% |
| 40-50 | 0 | 0.0% |
| 50-60 | 0 | 0.0% |
| 60-70 | 0 | 0.0% |
| 70-80 | 0 | 0.0% |
| 80-90 | 0 | 0.0% |
| 90-100 | 0 | 0.0% |

---

## Implementation Details

### Calculation Flow

1. **Check Cache:** Look for cached score in Redis
2. **Get Metrics:** Call `get_company_metrics()` to gather company data
3. **Calculate Components:**
   - Failure Rate: `terminated_count / total_trials * 40`
   - Recent Failures: Based on failures in last 12 months (0-30 points)
   - Pipeline Stagnation: Based on days since last update (0-20 points)
   - Warning Signals: Based on signal count (0-10 points)
4. **Sum Components:** Total = failure_score + recent_score + stagnation_score + warning_score
5. **Determine Category:** Map score to risk category
6. **Cache Result:** Store in Redis with 1-hour TTL
7. **Return Result:** Return dictionary with score, category, and components

### Key Functions

- `calculate_company_risk_score(company_id)` - Main scoring function
- `get_company_metrics(company_id)` - Gathers company metrics
- `_get_warning_signals(company_id)` - Detects warning signals
- `_get_risk_category(score)` - Maps score to category
- `_calculate_phase_success_rate(trials)` - Calculates phase success rates
- `_calculate_pipeline_velocity(company_id, trials)` - Calculates pipeline velocity
- `_get_days_since_last_update(company_id)` - Gets days since last update
- `_detect_failure_clustering(company_id)` - Detects failure patterns

---

---

# Dashboard/UI Report

**Generated:** 2025-11-09 11:17:57

This report documents the dashboard views, pages, and their database queries.

---

## Dashboard Structure

### Technology Stack

- **Frontend Framework:** React with TypeScript
- **Routing:** React Router v6
- **API Client:** Axios
- **Styling:** Tailwind CSS
- **Charts:** Recharts
- **Backend API:** FastAPI (Python)

### Application Entry Point

- **File:** `frontend/src/App.tsx`
- **Routes:**
  - `/` - Company Risk Dashboard (default)
  - `/company/:companyId` - Company Risk Dashboard (with company selected)

---

## Views and Pages

### 1. Company Risk Dashboard (Primary View)

- **File:** `frontend/src/pages/CompanyRiskDashboard.tsx`
- **Route:** `/` or `/company/:companyId`
- **Description:** Main dashboard showing company risk profiles and metrics

**Two Display Modes:**

1. **List View (Default):** Shows recent failed trials
   - Component: `FailedTrialsList`
   - Displays: Recent high-risk and failed trials with company risk scores

2. **Detail View:** Shows detailed company risk profile
   - Components:
     - `RiskScoreCard` - Risk score visualization
     - `MetricsCards` - Company metrics cards
     - `TimelineVisualization` - Event timeline chart

**Components Used:**

- `CompanySearchBar` - Company search with autocomplete
- `FailedTrialsList` - List of recent failures
- `RiskScoreCard` - Risk score gauge and component breakdown
- `MetricsCards` - Grid of metric cards
- `TimelineVisualization` - Event timeline chart and list

---

## Data Queries by View

### Company Risk Dashboard - Detail View

When a company is selected, the dashboard makes **3 parallel API calls:**

#### 1. Risk Profile Query

- **API Endpoint:** `GET /api/companies/{company_id}/risk-profile`
- **Backend Route:** `src/api/routes/company_risk.py::get_company_risk_profile()`
- **Service Method:** `CompanyRiskService.calculate_company_risk_score()`
- **Database Queries:**
  - `companies` table - Get company information
  - `clinical_trials` + `trial_sponsors` - Get all trials for company
  - `events` table - Get recent failure events (last 12 months)
  - Calculates: Failure rate, recent failures, pipeline stagnation, warning signals
- **Returns:** Risk score (0-100), risk category, component breakdown

#### 2. Company Metrics Query

- **API Endpoint:** `GET /api/companies/{company_id}/metrics`
- **Backend Route:** `src/api/routes/company_risk.py::get_company_metrics()`
- **Service Method:** `CompanyRiskService.get_company_metrics()`
- **Database Queries:**
  - `companies` table - Company info
  - `clinical_trials` + `trial_sponsors` - All company trials
  - `events` table - Pipeline events for last update calculation
  - Calculates:
    - Total trials, active trials, terminated count
    - Success rates by phase (Phase 1, 2, 3)
    - Pipeline velocity (new programs per year)
    - Days since last pipeline update
    - Failure clustering patterns
- **Returns:** All company metrics

#### 3. Company Timeline Query

- **API Endpoint:** `GET /api/companies/{company_id}/timeline`
- **Backend Route:** `src/api/routes/company_risk.py::get_company_timeline()`
- **Service Method:** `CompanyRiskService.get_company_timeline()`
- **Database Queries:**
  - `events` table - Events where company is in `entities_involved` array
  - `company_drugs` table - Related drugs (if include_related=True)
  - `trial_sponsors` table - Related trials (if include_related=True)
  - Uses PostgreSQL array query: `array_position(entities_involved, company_id) != NULL`
  - Filters: Optional date range, optional event types
- **Returns:** Chronological list of events

---

### Company Risk Dashboard - List View (Failed Trials)

#### Recent Failures Query

- **API Endpoint:** `GET /api/failures/recent?days=90&limit=50`
- **Backend Route:** `src/api/routes/company_risk.py::get_recent_failures()`
- **Service Method:** `FailureTracker.get_recent_failures()`
- **Database Queries:**
  - `events` table - Filter by event types:
    - `trial.status.terminated`
    - `trial.status.withdrawn`
    - `program.milestone.rejected`
    - `regulatory.rejection`
  - Filters: Last N days (default 30, UI uses 90)
  - Enriches with entity details (companies, trials, drugs, diseases)
- **Additional Queries:**
  - For each failure, loads company risk profile to show risk score
  - API: `GET /api/companies/{company_id}/risk-profile` (called per company)
- **Returns:** List of failure events with enriched entity details and risk scores

---

### Company Search

#### Company Search Query

- **Component:** `CompanySearchBar`
- **API Endpoint:** `GET /api/companies/search`
- **Backend Route:** `src/api/routes/company_risk.py::search_companies()`
- **Database Queries:**
  - `companies` table - Base query with name search (ILIKE)
  - Optional joins:
    - `trial_sponsors` + `trial_diseases` + `diseases` - For therapeutic area filter
    - Subquery for trial counts - For min_programs filter
  - For each result:
    - Calls `calculate_company_risk_score()` - Risk score calculation
    - Calls `get_company_metrics()` - Basic metrics
- **Filters Supported:**
  - `q` - Company name search (ILIKE)
  - `risk_category` - Filter by risk category
  - `therapeutic_area` - Filter by disease area
  - `min_programs` - Minimum number of trials
  - `limit` / `offset` - Pagination
- **Returns:** List of companies with risk scores and basic metrics

---

## Primary Company Risk View

The primary view is the **Company Risk Dashboard Detail View**, which displays:

### 1. Risk Score Card

- **Component:** `RiskScoreCard`
- **Data Source:** Risk Profile API response
- **Displays:**
  - Risk score gauge (0-100, semicircle visualization)
  - Risk category badge (LOW, MODERATE, HIGH, CRITICAL)
  - Component breakdown with progress bars:
    - Failure Rate (40 points max)
    - Recent Failures (30 points max)
    - Pipeline Stagnation (20 points max)
    - Warning Signals (10 points max)

### 2. Metrics Cards

- **Component:** `MetricsCards`
- **Data Source:** Company Metrics API response
- **Displays (8 cards):**
  - Total Trials
  - Active Trials
  - Terminated Count
  - Pipeline Velocity (programs/year)
  - Phase 1 Success Rate (%)
  - Phase 2 Success Rate (%)
  - Phase 3 Success Rate (%)
  - Days Since Last Update

### 3. Timeline Visualization

- **Component:** `TimelineVisualization`
- **Data Source:** Company Timeline API response
- **Displays:**
  - Line chart showing event counts over time by significance level
  - List of recent events (up to 20) with significance indicators
  - Event types and dates

---

## Database Query Patterns

### How the Dashboard Queries the Database

#### 1. Company Risk Score Calculation

**Query Pattern:** Multi-step aggregation

```sql
-- Step 1: Get company trials
SELECT t.* FROM clinical_trials t
JOIN trial_sponsors ts ON t.trial_id = ts.trial_id
WHERE ts.entity_id = :company_id
  AND ts.entity_type = 'company'
  AND ts.deleted_at IS NULL
  AND t.deleted_at IS NULL

-- Step 2: Get recent failure events
SELECT * FROM events
WHERE array_position(entities_involved, :company_id) IS NOT NULL
  AND event_type IN ('trial.status.terminated', 'trial.status.withdrawn', 'regulatory.clinical_hold')
  AND event_date >= :twelve_months_ago
  AND deleted_at IS NULL

-- Step 3: Get warning signals (from events)
SELECT * FROM events
WHERE array_position(entities_involved, :company_id) IS NOT NULL
  AND event_type IN ('corporate.layoff', 'regulatory.warning_letter', ...)
  AND deleted_at IS NULL
```

**Calculation:**
- Failure Rate: `terminated_count / total_trials * 40`
- Recent Failures: Based on count in last 12 months (0-30 points)
- Pipeline Stagnation: Based on days since last event (0-20 points)
- Warning Signals: Based on signal count (0-10 points)

#### 2. Company Metrics Query

**Query Pattern:** JOIN with aggregations

```sql
SELECT
  COUNT(DISTINCT t.trial_id) as total_trials,
  COUNT(DISTINCT CASE WHEN t.status IN ('ACTIVE', 'RECRUITING') THEN t.trial_id END) as active_trials,
  COUNT(DISTINCT CASE WHEN t.status IN ('TERMINATED', 'WITHDRAWN') THEN t.trial_id END) as terminated_count,
  -- Phase success rates calculated in Python
  MAX(t.registration_date) as last_trial_registration_date,
  MAX(e.event_date) as last_pipeline_update_date
FROM companies c
LEFT JOIN trial_sponsors ts ON c.company_id = ts.entity_id
LEFT JOIN clinical_trials t ON ts.trial_id = t.trial_id
LEFT JOIN events e ON e.entities_involved @> ARRAY[c.company_id]::uuid[]
WHERE c.company_id = :company_id
  AND c.deleted_at IS NULL
GROUP BY c.company_id
```

#### 3. Timeline Query

**Query Pattern:** Array containment query

```sql
-- Primary query
SELECT * FROM events
WHERE array_position(entities_involved, :company_id) IS NOT NULL
  AND deleted_at IS NULL
ORDER BY event_date DESC

-- If include_related=True, also query related entities
SELECT drug_id FROM company_drugs WHERE company_id = :company_id
SELECT trial_id FROM trial_sponsors WHERE entity_id = :company_id
-- Then query events for those related entities
```

#### 4. Recent Failures Query

**Query Pattern:** Event filtering with entity enrichment

```sql
SELECT * FROM events
WHERE event_type IN ('trial.status.terminated', 'trial.status.withdrawn', ...)
  AND event_date >= :start_date
  AND deleted_at IS NULL
ORDER BY event_date DESC
LIMIT :limit

-- Then enrich with entity details (companies, trials, drugs, diseases)
-- by querying entities_involved array
```

#### 5. Company Search Query

**Query Pattern:** Conditional JOINs with filters

```sql
SELECT c.* FROM companies c
WHERE c.name ILIKE '%:query%'
  AND c.deleted_at IS NULL

-- If therapeutic_area filter:
JOIN trial_sponsors ts ON c.company_id = ts.entity_id
JOIN trial_diseases td ON ts.trial_id = td.trial_id
JOIN diseases d ON td.disease_id = d.disease_id
WHERE d.disease_name ILIKE '%:therapeutic_area%'

-- If min_programs filter:
JOIN (
  SELECT entity_id, COUNT(trial_id) as trial_count
  FROM trial_sponsors
  WHERE entity_type = 'company'
  GROUP BY entity_id
) tc ON c.company_id = tc.entity_id
WHERE tc.trial_count >= :min_programs
```

---

## Query Performance Considerations

### Caching Strategy

- **Risk Scores:** Cached in Redis with 1-hour TTL
  - Cache key: `risk_score:{company_id}`
- **Company Metrics:** Cached in Redis with 30-minute TTL
  - Cache key: `company_metrics:{company_id}`
- **Timelines:** Cached in Redis with 15-minute TTL
  - Cache key: `company_timeline:{company_id}:{filters}`

### Database Indexes Used

- `companies.company_id` - Primary key
- `trial_sponsors.entity_id` - For company-trial joins
- `trial_sponsors.trial_id` - For trial lookups
- `events.entities_involved` - Array column (GIN index recommended)
- `events.event_date` - For date filtering
- `events.event_type` - For event type filtering

### Potential Performance Issues

1. **Array Queries:** `array_position(entities_involved, company_id)`
   - May be slow without GIN index on `entities_involved`
   - Consider: `CREATE INDEX idx_events_entities_gin ON events USING GIN(entities_involved);`

2. **N+1 Queries in Search:**
   - Company search calculates risk score for each company
   - Could be optimized with batch processing or materialized view

3. **Timeline with Related Entities:**
   - When `include_related=True`, queries multiple entity types
   - May benefit from denormalized event table or materialized view

---

## API Endpoints Summary

| Endpoint | Method | Purpose | Database Tables Queried |
|----------|--------|---------|------------------------|
| `/api/companies/{id}/risk-profile` | GET | Get risk score | companies, clinical_trials, trial_sponsors, events |
| `/api/companies/{id}/metrics` | GET | Get company metrics | companies, clinical_trials, trial_sponsors, events |
| `/api/companies/{id}/timeline` | GET | Get event timeline | events, company_drugs, trial_sponsors (optional) |
| `/api/companies/search` | GET | Search companies | companies, trial_sponsors, trial_diseases, diseases |
| `/api/failures/recent` | GET | Get recent failures | events, companies, clinical_trials, drugs, diseases |

---
