# Study Card Architecture Implementation

## Overview

This document describes the complete implementation of the new Study Card architecture that replaces the previous database schema. The new architecture is designed for precision-first analysis of US-listed companies and pivotal Phase 2b/3 trials.

## What Was Implemented

### 1. Complete Database Schema Overhaul

The entire database schema has been replaced with a new architecture that includes:

- **Reference & Identity**: Companies, company aliases, securities
- **Assets & Ownership**: Assets, asset ownership relationships
- **Trials & Versioning**: Clinical trials with full versioning support
- **Documents & Storage**: Studies table with Study Card JSON
- **Patents**: Patent information and assignment history
- **Signals → Gates → Scores**: Complete failure detection pipeline
- **Catalyst Timing**: Trial readout windows and certainty
- **Run Lineage**: Execution tracking and artifact management

### 2. New Models (`src/ncfd/db/models.py`)

All previous models have been replaced with new ones that implement:

- **Proper enum types** for all categorical fields
- **JSONB fields** for flexible data storage (Study Cards, metadata)
- **Comprehensive indexing** including GIN indexes for JSONB fields
- **Proper foreign key relationships** with cascade delete rules
- **Timestamp fields** for audit trails

### 3. Database Migration (`alembic/versions/20250125_study_card_overhaul_new_architecture.py`)

A new baseline migration that:

- **Drops all previous tables** and recreates the schema from scratch
- **Creates all required PostgreSQL enums** for type safety
- **Sets up proper indexes** for performance
- **Establishes foreign key constraints** for data integrity

### 4. Database Rebuild Tools

#### `scripts/nuke_and_rebuild_db.py`
Python script that completely destroys and recreates the database:
- Terminates all connections to the target database
- Drops and recreates the database
- Sets up required PostgreSQL extensions (pg_trgm, btree_gin)

#### `scripts/rebuild_database.sh`
Shell script that automates the entire rebuild process:
- Runs the nuke script
- Executes the new migration
- Verifies the schema

## Key Architectural Changes

### 1. Study Card JSON Structure

The `studies.extracted_jsonb` field contains structured Study Card data with:

```json
{
  "doc": { "study_id", "doc_type", "url", "citation", "year" },
  "trial_link": { "nct_id?", "trial_id?" },
  "asset_link": { "asset_id?", "names{inn, internal_codes[]}" },
  "design": { "phase", "randomized", "blinded", "arms", "sample_size" },
  "endpoints": { "primary", "secondary[]" },
  "results": { "primary", "secondary[]", "subgroups[]", "safety" },
  "protocol": { "version_date", "changes" },
  "consistency": { "itt_vs_pp", "interims", "pvalue_shape" },
  "class_priors": { "indication", "moa", "historical_win_rate" },
  "coverage": { "level", "missing_fields", "reasons" },
  "quotes": [{ "field_ref", "text", "location" }]
}
```

### 2. Precision-First Approach

- **US-listed companies only** (NASDAQ, NYSE, NYSE_AM, OTCQX, OTCQB)
- **Pivotal Phase 2b/3 trials** focus
- **Evidence-constrained claims** with quotes and evidence spans
- **Coverage auditing** to identify data gaps

### 3. Signal Detection Pipeline

- **S1-S9 signals**: Primitive failure detection signals
- **G1-G4 gates**: Composite decision gates
- **Likelihood ratios**: Configurable calibration per gate/universe
- **Posterior probabilities**: Bayesian updating with stop rules

## How to Use

### 1. Prerequisites

- PostgreSQL database with superuser privileges
- `DATABASE_URL` environment variable set
- `psycopg2` Python package installed
- `alembic` command available

### 2. Complete Database Rebuild

```bash
# Option 1: Use the automated script
./scripts/rebuild_database.sh

# Option 2: Manual process
python scripts/nuke_and_rebuild_db.py
alembic upgrade head
python scripts/print_db_info.py
```

### 3. Verify the Schema

```bash
# Check database structure
python scripts/print_db_info.py

# Or connect directly with psql
psql $DATABASE_URL -c "\dt"
```

## Database Schema Summary

### Core Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `companies` | Company master data | company_id, name, cik, lei |
| `securities` | Stock tickers | ticker, exchange, company_id |
| `trials` | Clinical trials | nct_id, phase, sponsor_company_id |
| `studies` | Documents with Study Cards | doc_type, extracted_jsonb, coverage_level |
| `assets` | Drugs/compounds | names_jsonb, modality, target |
| `signals` | Failure detection | s_id, trial_id, value, severity |
| `gates` | Decision gates | g_id, trial_id, fired_bool |
| `scores` | Posterior probabilities | trial_id, run_id, p_fail |

### Key Relationships

- **Company** → **Securities** (one-to-many)
- **Company** → **Trials** (sponsor relationship)
- **Trial** → **Studies** (documents about the trial)
- **Trial** → **Signals** → **Gates** → **Scores** (pipeline)
- **Asset** → **Studies** (documents about the asset)

## Migration Strategy

### 1. Data Loss Warning

⚠️ **This migration will completely destroy all existing data.** There is no upgrade path from the old schema.

### 2. Backup Strategy

Before running this migration:
1. **Backup all existing data** using pg_dump
2. **Export critical data** to CSV/JSON if needed
3. **Document current state** for reference

### 3. Rollback Plan

If issues arise:
1. **Restore from backup** using pg_restore
2. **Revert to previous alembic version** if needed
3. **Fix issues** and re-run the migration

## Next Steps

### 1. Immediate Actions

- [ ] Run the database rebuild
- [ ] Verify schema creation
- [ ] Test basic connectivity

### 2. Data Ingestion

- [ ] Ingest CT.gov trials and versions
- [ ] Ingest SEC company and security data
- [ ] Run company resolution pipeline
- [ ] Ingest PR/IR and abstract documents

### 3. Study Card Generation

- [ ] Implement LangExtract prompts
- [ ] Build Study Card JSON structure
- [ ] Validate coverage levels
- [ ] Generate evidence spans

### 4. Signal Detection

- [ ] Implement S1-S9 signal detectors
- [ ] Configure G1-G4 gate logic
- [ ] Set up likelihood ratio calibration
- [ ] Test scoring pipeline

## Troubleshooting

### Common Issues

1. **Permission denied**: Ensure database user has superuser privileges
2. **Connection refused**: Check DATABASE_URL and network connectivity
3. **Extension not found**: Verify PostgreSQL installation includes pg_trgm
4. **Migration fails**: Check for syntax errors in models.py

### Debug Commands

```bash
# Check database status
python scripts/print_db_info.py

# Verify alembic state
alembic current

# Check table creation
psql $DATABASE_URL -c "\dt"

# View specific table structure
psql $DATABASE_URL -c "\d+ companies"
```

## Support

For issues or questions:

1. **Check the logs** for detailed error messages
2. **Review the schema** against the blueprint
3. **Verify dependencies** are properly installed
4. **Consult the original specification** for design decisions

---

**Note**: This implementation represents a complete architectural overhaul. All previous data and schema will be lost during the migration process.
