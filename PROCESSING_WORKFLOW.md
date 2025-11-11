# Processing Workflow

This document describes the two-phase processing workflow for building the biotech knowledge graph.

## Overview

The system uses a **two-phase approach**:

1. **Phase 1: Entity Extraction and Resolution**
   - Extract entities from source data
   - Resolve and deduplicate entities
   - Store entities in database

2. **Phase 2: Relationship Inference**
   - Infer relationships between resolved entities
   - Create relationship records in database
   - Can be run independently to iterate on relationship logic

## Phase 1: Entity Extraction

### Process Sources

Extract entities from data sources:

```bash
# Process a specific source
python -m src.processing.pipeline process_source <source_name> --limit 100

# Process all active sources
python scripts/process_all_active_sources.py
```

### What Happens

- Raw data is fetched from sources (PubMed, ClinicalTrials.gov, SEC Edgar, etc.)
- Entities are extracted (companies, drugs, trials, publications, etc.)
- Entities are resolved (deduplicated, merged)
- Entities are stored in database
- **Same-run relationships** are created (e.g., trial → sponsor, trial → drug)

### Current Sources

- ClinicalTrials.gov (trials, sponsors, drugs, diseases)
- PubMed (publications)
- OpenFDA (drugs, indications)
- SEC Edgar (filings, companies)
- And more...

## Phase 2: Relationship Inference

### Run Relationship Inference

After entities are extracted, infer cross-source relationships:

```bash
# Rebuild all relationships from scratch
python scripts/infer_relationships.py --rebuild

# Only infer specific relationship types
python scripts/infer_relationships.py --types publication_trial publication_drug

# Verbose logging
python scripts/infer_relationships.py --rebuild --verbose
```

### What Gets Inferred

The inference engine creates relationships that weren't created during extraction:

1. **Publication-Trial Relationships**
   - Extracts NCT IDs from publication text (title, abstract)
   - Matches to trials in database
   - Creates `PublicationTrial` relationships

2. **Publication-Drug Relationships**
   - Searches publication text for drug mentions
   - Matches to drugs in database
   - Creates `PublicationDrug` relationships

3. **Publication-Company Relationships**
   - Extracts company names from affiliations/funding (if available)
   - Creates `PublicationCompany` relationships
   - *Note: Limited by available data*

4. **Filing-Drug Relationships**
   - Searches SEC filing text for drug mentions
   - Matches to drugs in database
   - Creates `FilingDrug` relationships

5. **Company-Drug Relationships** (from trials)
   - Infers from trial sponsorships
   - If Company X sponsors Trial Y that tests Drug Z, creates CompanyDrug relationship
   - Already implemented and runs automatically

### When to Run Inference

- **After processing new sources**: Run inference to create relationships for new entities
- **After updating inference logic**: Rerun inference without reprocessing sources
- **Periodically**: Rebuild all relationships to ensure consistency

## Complete Workflow Example

```bash
# 1. Process sources (extract entities)
python -m src.processing.pipeline process_source pubmed --limit 100
python -m src.processing.pipeline process_source clinicaltrials_gov --limit 100

# 2. Run relationship inference
python scripts/infer_relationships.py --rebuild

# 3. Verify results
python count_relationships.py
python test_relationship_inference.py
```

## Relationship Types

### Same-Run Relationships (Created During Extraction)

These are created automatically during Phase 1:

- `TrialSponsor` - Trial → Company/Institution
- `TrialDrug` - Trial → Drug
- `TrialDisease` - Trial → Disease
- `CompanyDrug` - Company → Drug (from direct extraction)
- `RegulatoryDrugEvent` - Regulatory Event → Drug
- `RegulatoryCompanyEvent` - Regulatory Event → Company
- `FilingCompany` - SEC Filing → Company

### Cross-Run Relationships (Created During Inference)

These require Phase 2 inference:

- `PublicationTrial` - Publication → Trial (via NCT ID)
- `PublicationDrug` - Publication → Drug (via text search)
- `PublicationCompany` - Publication → Company (via affiliations)
- `FilingDrug` - SEC Filing → Drug (via text search)
- `CompanyDrug` - Additional relationships inferred from trials

## Benefits of Two-Phase Approach

1. **Simpler**: No complex cross-run entity resolution needed
2. **More Reliable**: All entities exist before relationship inference
3. **More Powerful**: Can use sophisticated inference logic across all entities
4. **Easier to Iterate**: Rerun inference without reprocessing sources
5. **Better for Biotech Map**: Relationships become queryable layer on top of entities
6. **Scalable**: Can switch to incremental inference later when needed

## Performance

At current scale (~100 publications, ~200 trials, ~800 drugs):
- Full rebuild takes **seconds**, not minutes
- Can run inference frequently without performance concerns
- When scale grows (>10k relationships), can switch to incremental updates

## Troubleshooting

### No Relationships Created

1. Check entity counts: `python count_relationships.py`
2. Verify entities exist: Check database for publications, trials, drugs
3. Check text availability: Publications need title/abstract, filings need full_text
4. Run with verbose logging: `python scripts/infer_relationships.py --rebuild --verbose`

### Relationships Not Matching

1. Check normalization: Drug names are normalized for matching
2. Check text quality: Abstract/full_text may be empty
3. Check NCT ID format: Must match pattern `NCT\d{8}`

### Performance Issues

1. Drug name cache: First run loads all drug names (one-time cost)
2. Full rebuild: Clears all relationships before rebuilding
3. Consider incremental updates: Only process new/updated entities

## Future Enhancements

- Incremental inference (only process new entities)
- More sophisticated text matching (fuzzy matching, NLP)
- Additional relationship types (patent relationships, etc.)
- Relationship confidence scoring
- Relationship validation and quality checks

