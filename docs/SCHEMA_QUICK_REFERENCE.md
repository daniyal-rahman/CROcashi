# Study Card Schema - Quick Reference

## Core Tables Overview

```
companies → securities
    ↓
trials → studies
    ↓
signals → gates → scores
    ↓
catalysts, labels
```

## Table Details

### 1. Reference & Identity
| Table | Key Fields | Purpose |
|-------|------------|---------|
| `companies` | `company_id`, `name`, `cik` | Company master data |
| `company_aliases` | `alias_id`, `company_id`, `alias` | Alternative company names |
| `securities` | `ticker`, `exchange`, `company_id` | Stock listings |

### 2. Assets & Ownership
| Table | Key Fields | Purpose |
|-------|------------|---------|
| `assets` | `asset_id`, `names_jsonb`, `modality` | Drugs/compounds |
| `asset_ownership` | `ownership_id`, `asset_id`, `company_id` | Who owns what |

### 3. Trials & Documents
| Table | Key Fields | Purpose |
|-------|------------|---------|
| `trials` | `nct_id`, `phase`, `sponsor_company_id` | Clinical trials |
| `trial_versions` | `trial_id`, `sha256`, `raw_jsonb` | Trial change history |
| `studies` | `doc_type`, `extracted_jsonb`, `coverage_level` | Documents with Study Cards |

### 4. Signal Pipeline
| Table | Key Fields | Purpose |
|-------|------------|---------|
| `signals` | `trial_id`, `s_id`, `value`, `severity` | S1-S9 failure signals |
| `signal_evidence` | `signal_id`, `source_study_id` | Evidence for signals |
| `gates` | `trial_id`, `g_id`, `fired_bool` | G1-G4 decision gates |
| `scores` | `trial_id`, `run_id`, `p_fail` | Posterior probabilities |

### 5. Operations
| Table | Key Fields | Purpose |
|-------|------------|---------|
| `runs` | `run_id`, `flow_name`, `status` | Execution tracking |
| `run_artifacts` | `run_id`, `artifact_type` | Output files |

## Key Enums

### Exchanges
- `NASDAQ`, `NYSE`, `NYSE_AM`, `OTCQX`, `OTCQB`

### Trial Phases
- `P2`, `P2B`, `P2_3`, `P3`

### Document Types
- `PR`, `8K`, `Abstract`, `Poster`, `Paper`, `Registry`, `FDA`

### Coverage Levels
- `high`, `med`, `low`

### Signal IDs
- `S1`, `S2`, `S3`, `S4`, `S5`, `S6`, `S7`, `S8`, `S9`

### Gate IDs
- `G1`, `G2`, `G3`, `G4`

## Common Queries

### Find trials by company
```sql
SELECT t.nct_id, t.brief_title, t.phase
FROM trials t
JOIN companies c ON t.sponsor_company_id = c.company_id
WHERE c.name ILIKE '%Roche%';
```

### Find studies by coverage level
```sql
SELECT s.doc_type, s.citation, s.coverage_level
FROM studies s
WHERE s.coverage_level = 'high'
ORDER BY s.year DESC;
```

### Get signal summary for trial
```sql
SELECT s.s_id, s.severity, s.value
FROM signals s
WHERE s.trial_id = (SELECT trial_id FROM trials WHERE nct_id = 'NCT12345678')
ORDER BY s.s_id;
```

### Check gate status
```sql
SELECT g.g_id, g.fired_bool, g.rationale_text
FROM gates g
WHERE g.trial_id = (SELECT trial_id FROM trials WHERE nct_id = 'NCT12345678');
```

## Study Card JSON Structure

```json
{
  "doc": {
    "study_id": "pmid:12345",
    "doc_type": "Paper",
    "year": 2024
  },
  "trial_link": {
    "nct_id": "NCT12345678"
  },
  "design": {
    "phase": "P3",
    "randomized": true,
    "sample_size": 500
  },
  "endpoints": {
    "primary": {
      "name": "Overall Survival",
      "type": "OS"
    }
  },
  "coverage": {
    "level": "high",
    "missing_fields": []
  }
}
```

## Indexes

### Performance Indexes
- `companies.name_norm` (GIN trigram)
- `studies.extracted_jsonb` (GIN JSONB)
- `assets.names_jsonb` (GIN JSONB)
- `trials.sponsor_company_id` (B-tree)
- `signals.trial_id` (B-tree)

### Unique Constraints
- `companies.cik` (unique)
- `securities.ticker` (unique)
- `trials.nct_id` (unique)
- `signals.trial_id + s_id` (unique)
- `gates.trial_id + g_id` (unique)

## Data Types

### JSONB Fields
- `studies.extracted_jsonb` - Study Card data
- `assets.names_jsonb` - Asset identifiers
- `trial_versions.raw_jsonb` - Raw trial data
- `signals.metadata` - Signal metadata

### Array Fields
- `trials.intervention_types` - Array of strings
- `gates.supporting_s_ids` - Array of signal IDs
- `catalysts.sources` - Array of URLs

### Numeric Fields
- `scores.p_fail` - Numeric(5,4) for probabilities
- `signals.value` - Numeric(10,6) for signal values
- `lr_tables.lr_value` - Numeric(10,6) for likelihood ratios

## Relationships

### One-to-Many
- Company → Securities
- Company → Trials (as sponsor)
- Trial → Studies
- Trial → Signals
- Trial → Gates
- Trial → Scores

### Many-to-Many (via junction tables)
- Assets ↔ Companies (via asset_ownership)
- Studies ↔ Signals (via signal_evidence)

## Migration Notes

⚠️ **This is a complete schema replacement.** All previous data will be lost.

### Before Migration
1. Backup existing database
2. Export critical data
3. Ensure superuser privileges

### After Migration
1. Verify schema creation
2. Test basic connectivity
3. Begin data ingestion
