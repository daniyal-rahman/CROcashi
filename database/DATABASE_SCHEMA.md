# Database Schema Documentation

## Overview

The biotech knowledge graph database contains 45+ tables organized into logical groups for comprehensive entity resolution and relationship tracking across the biotech industry.

## Table Structure

### Core Entity Tables

#### Companies (`companies`)
- Primary entity for biotech/pharma companies
- Supports ownership hierarchy (parent/subsidiary relationships)
- Tracks company status, type, and metadata
- Includes URLs, aliases, and data source tracking

#### Institutions (`institutions`)
- Academic/hospital/research institutions
- Supports institutional hierarchy
- Tracks industry partnerships

#### Drugs (`drugs`)
- Primary drug entity
- Links to `drug_chemical_identity` for definitive matching
- Supports multiple name types via `drug_names` table
- Tracks external identifiers (ChEMBL, DrugBank, PubChem, etc.)

#### Targets (`targets`)
- Biological targets (proteins, genes, pathways)
- Links to external identifiers (UniProt, gene symbols)

#### Mechanisms (`mechanisms`)
- Drug mechanisms of action
- Types: inhibitor, agonist, antagonist, modulator

#### Diseases (`diseases`)
- Disease entities with hierarchical structure
- Supports classification codes (ICD-10, MeSH, SNOMED)
- Tracks rare disease and orphan designation eligibility

### Clinical Tables

#### Clinical Trials (`clinical_trials`)
- Trial metadata and status
- Links to sponsors, drugs, and diseases via relationship tables
- Tracks phases, enrollment, dates, and results

#### Regulatory Events (`regulatory_events`)
- FDA/EMA/other regulatory actions
- Types: approval, rejection, breakthrough, orphan, fast_track, clinical_hold, withdrawal

### Publication Tables

#### Publications (`publications`)
- Scientific publications
- Links to PubMed, PMC, DOI
- Tracks clinical trial results and safety mentions

#### Patents (`patents`)
- Patent entities
- Tracks filing, publication, grant, expiration dates
- Links to drugs and companies

#### Conferences (`conferences`)
- Conference entities

#### Conference Presentations (`conference_presentations`)
- Conference abstracts and presentations
- Links to drugs, companies, and trials

#### SEC Filings (`sec_filings`)
- SEC filing documents (8-K, 10-K, 10-Q, etc.)
- Tracks mentions of programs, milestones, restructuring

### Relationship Tables

These tables connect entities with temporal tracking:

- `company_ownership_history` - Company ownership changes over time
- `company_drugs` - Company-drug relationships with development stages
- `drug_ownership_history` - Drug ownership/licensing changes
- `drug_targets` - Drug-target interactions
- `drug_mechanisms` - Drug-mechanism relationships
- `drug_indications` - Drug-disease indications with approval status
- `drug_combinations` - Drug combination entities
- `trial_sponsors` - Trial sponsor relationships (companies or institutions)
- `trial_funding` - Trial funding relationships
- `trial_drugs` - Drugs used in trials
- `trial_diseases` - Diseases studied in trials
- `publication_drugs` - Drugs mentioned in publications
- `publication_trials` - Publications linked to trials
- `publication_companies` - Company affiliations in publications
- `patent_drugs` - Drugs covered by patents
- `patent_companies` - Patent assignees/licensees
- `regulatory_drug_events` - Regulatory events linked to drugs
- `regulatory_company_events` - Regulatory events linked to companies
- `presentation_drugs` - Drugs in conference presentations
- `presentation_companies` - Companies in presentations
- `presentation_trials` - Trials presented at conferences
- `filing_companies` - Companies in SEC filings
- `filing_drugs` - Drugs mentioned in SEC filings

### Entity Resolution Tables

#### Entity Aliases (`entity_aliases`)
- Alternative names for entities
- Critical for entity resolution
- Includes confidence scores

#### Entity Matches (`entity_matches`)
- Matches across different source systems
- Tracks matching method and confidence

#### Entity Match Confidence (`entity_match_confidence`)
- Detailed match confidence tracking
- Supports manual review workflow

#### Matching Review Queue (`matching_review_queue`)
- Queue for manual matching review
- Tracks priority and assignment

#### Data Quality Metrics (`data_quality_metrics`)
- Data quality statistics over time
- Tracks match confidence distributions

### Staging Tables

#### Staging Raw Data (`staging_raw_data`)
- Raw data before entity resolution
- Stores complete source records in JSONB
- Tracks processing status and errors

## Key Design Patterns

### UUID Primary Keys
All tables use UUID primary keys for distributed system compatibility.

### Temporal Tracking
Many relationship tables include date ranges:
- `valid_from` / `valid_until` for names
- `effective_start_date` / `effective_end_date` for ownership
- `start_date` / `end_date` for relationships

### JSONB Metadata
Flexible metadata storage in `data_sources` JSONB columns:
- Tracks which sources mention each entity
- Stores source-specific metadata
- Enables full-text search via GIN indexes

### Foreign Key Constraints
- CASCADE for dependent data (e.g., drug names when drug is deleted)
- SET NULL for optional relationships (e.g., parent company)
- RESTRICT for core relationships that shouldn't be deleted

### Indexes
Comprehensive indexing strategy:
- Foreign keys are indexed
- Frequently filtered columns (status, type, dates)
- Unique identifiers (NCT ID, PMID, ticker)
- GIN indexes for JSONB and text search
- Composite indexes for common query patterns

## Example Queries

See `database/examples.py` for comprehensive query examples.

### Find all drugs for a company
```python
from database.utils import get_company_pipeline
drugs = get_company_pipeline(session, company_id)
```

### Find all trials for a drug
```python
from database.utils import get_trials_for_drug
trials = get_trials_for_drug(session, drug_id, status='active', phase=3)
```

### Find all approved drugs for a disease
```python
from database.utils import get_drugs_for_disease
drugs = get_drugs_for_disease(session, disease_id, approved_only=True)
```

## Migration Management

All schema changes are managed through Alembic migrations:

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Performance Considerations

- Use GIN indexes for JSONB queries
- Use composite indexes for common join patterns
- Consider partitioning large tables (e.g., staging_raw_data) by date
- Use connection pooling (configured in `database/config.py`)
- Monitor query performance with `EXPLAIN ANALYZE`

## Entity Resolution Workflow

1. **Staging**: Raw data stored in `staging_raw_data`
2. **Extraction**: Extract key fields to `extracted_fields`
3. **Matching**: Use `entity_aliases` and `entity_matches` for matching
4. **Confidence**: Calculate confidence scores in `entity_match_confidence`
5. **Review**: Queue low-confidence matches in `matching_review_queue`
6. **Resolution**: Create or link to resolved entities
7. **Quality**: Track metrics in `data_quality_metrics`

