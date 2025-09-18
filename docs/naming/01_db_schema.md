# NCFD Database Schema Inventory

## Overview

This document provides a comprehensive inventory of the NCFD database schema as of migration `117fe225c48e` (simplify_resolver_schema). The schema contains **38 tables** and **13 enums** following consistent naming conventions.

## Schema Summary

- **Schema Version**: `117fe225c48e`
- **Total Tables**: 38
- **Total Enums**: 13
- **Extraction Date**: 2025-09-18T00:48:16Z

## Naming Conventions Observed

### Table Naming
- **Style**: `snake_case_plural` (100% consistent)
- **Examples**: `companies`, `trial_versions`, `signal_evidence`
- **Rationale**: Clear indication of entity collections

### Column Naming
- **Style**: `snake_case` (100% consistent)
- **Examples**: `company_id`, `created_at`, `sponsor_text`
- **Rationale**: Consistent with Python naming conventions

### Primary Key Naming
- **Style**: `<table>_id` (100% consistent)
- **Examples**: `company_id`, `trial_id`, `asset_id`
- **Rationale**: Clear, unambiguous identifier naming

### Foreign Key Naming
- **Style**: `<ref_table>_id` (100% consistent)
- **Examples**: `company_id`, `trial_id`, `asset_id`
- **Rationale**: Clear relationship indication

### Timestamp Naming
- **Style**: `created_at`/`updated_at` (100% consistent)
- **Rationale**: Standard audit trail fields

## Core Tables

### Company & Security Management

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `companies` | Core company entities | `company_id`, `name`, `cik`, `lei` | 1:N with securities, trials, assets |
| `company_aliases` | Fuzzy matching aliases | `alias_id`, `company_id`, `alias` | N:1 with companies |
| `securities` | Stock tickers and exchanges | `security_id`, `company_id`, `ticker` | N:1 with companies |

### Trial Management

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `trials` | Clinical trial registry | `trial_id`, `nct_id`, `sponsor_company_id` | 1:N with versions, studies, signals |
| `trial_versions` | Historical trial data | `trial_version_id`, `trial_id`, `sha256` | N:1 with trials |
| `studies` | Document-trial associations | `study_id`, `trial_id`, `asset_id`, `doc_id` | N:1 with trials, assets, documents |

### Asset & Patent Management

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `assets` | Drug/asset entities | `asset_id`, `names_jsonb`, `owner_company_id` | 1:N with patents, studies |
| `patents` | Patent records | `patent_id`, `asset_id`, `jurisdiction`, `number` | N:1 with assets |
| `patent_assignments` | Patent ownership transfers | `assignment_id`, `patent_id`, `assignor`, `assignee` | N:1 with patents |

### Document Processing

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `documents` | Raw document metadata | `doc_id`, `source_type`, `url_hash`, `sha256` | 1:N with text, tables, citations |
| `document_text` | Abstracts and full text | `doc_id`, `abstract_text`, `fulltext_text` | 1:1 with documents |
| `document_tables` | Extracted table data | `doc_id`, `table_idx`, `table_jsonb` | N:1 with documents |
| `document_citations` | DOI/PMID/PMCID references | `doc_id`, `doi`, `pmid`, `pmcid` | 1:1 with documents |
| `document_entities` | LangExtract entity extraction | `doc_id`, `ent_type`, `value_text` | N:1 with documents |
| `document_links` | Linking to normalized entities | `doc_id`, `trial_id`, `asset_id`, `company_id` | N:1 with documents, trials, assets, companies |
| `spans` | Text spans with location | `id`, `doc_id`, `quote`, `section` | N:1 with documents |

### Signal Detection & Scoring

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `signals` | Primitive failure signals (S1-S9) | `signal_id`, `trial_id`, `run_id`, `s_id` | N:1 with trials, runs |
| `signal_evidence` | Evidence supporting signals | `evidence_id`, `signal_id`, `source_study_id` | N:1 with signals, studies |
| `gates` | Composite failure pattern gates (G1-G4) | `gate_id`, `trial_id`, `run_id`, `g_id` | N:1 with trials, runs |
| `scores` | Bayesian posterior probabilities | `score_id`, `trial_id`, `run_id`, `p_fail` | N:1 with trials, runs |

### Literature System

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `trial_doc_candidates` | Trial-document relationships | `trial_id`, `doc_id`, `stage`, `selected` | N:1 with trials, documents |
| `pubmed_meta` | PubMed-specific metadata | `doc_id`, `pmid`, `medline_xml_sha` | 1:1 with documents |
| `pmc_meta` | PMC-specific metadata | `doc_id`, `pmcid`, `license`, `oa_route` | 1:1 with documents |
| `trial_lit_state` | Trial-level literature state | `trial_id`, `best_S_Rge2`, `n_docs_seen` | 1:1 with trials |

### Processing & Operations

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `runs` | Execution lineage tracking | `run_id`, `started_at`, `finished_at`, `status` | 1:N with artifacts, signals, gates, scores |
| `run_artifacts` | Output tracking per run | `artifact_id`, `run_id`, `artifact_type` | N:1 with runs |
| `processing_queue` | Task queue for pipeline | `id`, `task_type`, `task_key`, `status` | Independent |
| `ctgov_ingest_state` | CT.gov ingestion state | `id`, `last_ingest_date`, `ingest_status` | Independent |

### Resolution & Review

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `sponsor_resolutions` | Simplified sponsor resolution | `id`, `nct_id`, `sponsor_text`, `company_id` | N:1 with companies |
| `manual_review_queue` | Manual review queue | `id`, `nct_id`, `sponsor_text`, `status` | N:1 with companies |
| `academic_blacklist` | Academic institution patterns | `id`, `pattern`, `reason`, `enabled` | Independent |
| `llm_discoveries` | LLM learning and discoveries | `id`, `nct_id`, `sponsor_text`, `discovered_company_id` | N:1 with companies |

### Study Card System

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `study_cards` | Study card data | `id`, `doc_id`, `design_archetype`, `is_blinded` | N:1 with documents |
| `factsheets` | Results factsheet data | `id`, `doc_id`, `results`, `primary_endpoint_results` | N:1 with documents |

### Additional Tables

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `disclosures` | Trial disclosures | `disclosure_id`, `trial_id`, `source_type` | N:1 with trials |
| `catalysts` | Timing windows for trial readouts | `catalyst_id`, `trial_id`, `window_start`, `window_end` | N:1 with trials |
| `labels` | Ground truth for backtests | `label_id`, `trial_id`, `event_date`, `primary_outcome_success_bool` | N:1 with trials |
| `markets` | Market data for analysis | `mkt_id`, `ticker`, `date`, `market_cap` | Independent |

## Enums

### Core Enums

| Enum | Values | Purpose |
|------|--------|---------|
| `ExchangeEnum` | NASDAQ, NYSE, NYSE_AM, OTCQX, OTCQB | Stock exchange types |
| `PhaseEnum` | P2, P2B, P2_3, P3 | Clinical trial phases |
| `DocTypeEnum` | PR, 8K, Abstract, Poster, Paper, Registry, FDA | Document types |
| `TrialStatusEnum` | Recruiting, Active, Completed, Terminated, etc. | Trial status values |
| `SeverityEnum` | H, M, L | Severity levels |
| `SignalIDEnum` | S1, S2, S3, S4, S5, S6, S7, S8, S9 | Primitive signal identifiers |
| `GateIDEnum` | G1, G2, G3, G4 | Composite gate identifiers |

### Processing Enums

| Enum | Values | Purpose |
|------|--------|---------|
| `OAStatusEnum` | oa_gold, oa_green, accepted_ms, embargoed, unknown | Open access status |
| `CoverageLevelEnum` | high, med, low | Coverage levels |
| `CertaintyEnum` | low, med, high | Certainty levels |
| `RunStatusEnum` | success, failed, partial | Run execution status |
| `AssignmentType` | sale, license, security | Patent assignment types |
| `ArtifactType` | model, data, report, config | Run artifact types |

## Key Relationships

### Primary Relationships
- **Companies** → **Securities** (1:N)
- **Companies** → **Trials** (1:N via sponsor_company_id)
- **Companies** → **Assets** (1:N via owner_company_id)
- **Trials** → **TrialVersions** (1:N)
- **Trials** → **Studies** (1:N)
- **Trials** → **Signals** (1:N)
- **Trials** → **Gates** (1:N)
- **Trials** → **Scores** (1:N)
- **Documents** → **DocumentText** (1:1)
- **Documents** → **DocumentTables** (1:N)
- **Documents** → **DocumentCitations** (1:1)
- **Documents** → **DocumentEntities** (1:N)
- **Documents** → **DocumentLinks** (1:N)
- **Assets** → **Patents** (1:N)
- **Runs** → **RunArtifacts** (1:N)

### Cascade Behavior
- **CASCADE**: Used for dependent relationships (e.g., securities → companies)
- **SET NULL**: Used for optional relationships (e.g., studies → assets)
- **RESTRICT**: Used for critical relationships

## Indexing Strategy

### Primary Indexes
- **Primary Keys**: All tables have `id` or `<table>_id` primary keys
- **Unique Constraints**: NCT IDs, tickers, CIKs, URL hashes
- **Foreign Key Indexes**: All foreign keys are indexed for performance

### Performance Indexes
- **Text Search**: GIN indexes on JSONB columns
- **Date Ranges**: Indexes on completion dates, update dates
- **Status Fields**: Indexes on trial status, run status
- **Composite Indexes**: Multi-column indexes for common query patterns

## Data Quality Features

### Constraints
- **Check Constraints**: Valid values for enums and ranges
- **Unique Constraints**: Prevent duplicate entities
- **Foreign Key Constraints**: Maintain referential integrity
- **Not Null Constraints**: Required fields are enforced

### Audit Trail
- **Timestamps**: `created_at` and `updated_at` on all major tables
- **Version Tracking**: Trial versions with SHA256 hashes
- **Run Tracking**: Complete execution lineage
- **Change Detection**: Material change tracking

## Migration History

The schema has evolved through 52 Alembic migrations with key milestones:
- **Baseline**: Core extensions and tables
- **Company System**: Company and securities management
- **Trial System**: Trial versioning and change tracking
- **Document System**: Document processing and entity extraction
- **Signal System**: Signal detection and gate analysis
- **Literature System**: PubMed integration and literature processing
- **Resolver System**: Simplified sponsor resolution (latest)

## Summary

The NCFD database schema demonstrates excellent naming consistency and architectural design:

✅ **Naming Consistency**: 100% adherence to `snake_case` conventions  
✅ **Relationship Integrity**: Clear foreign key patterns with appropriate cascade behavior  
✅ **Performance Optimization**: Comprehensive indexing strategy  
✅ **Data Quality**: Robust constraints and audit trails  
✅ **Scalability**: Well-designed for growth and evolution  

The schema supports the system's precision-first approach to clinical trial analysis with comprehensive signal detection, gate analysis, and Bayesian scoring capabilities.
