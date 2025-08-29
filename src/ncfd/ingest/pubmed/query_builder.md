# PubMed Query Builder Specification

## Overview
This document specifies how to build PubMed ESearch queries for each clinical trial to discover relevant literature.

## Query Construction Strategy

### Inputs per Trial
- **Asset aliases**: INN, internal codes, generic names, brand names
- **Indication keywords**: MeSH terms, indication text, disease area
- **Line-of-therapy markers**: first-line, second-line, refractory, etc.
- **NCT ID**: if available for exact matching
- **MOA/class synonyms**: mechanism of action, drug class
- **Catalyst window**: ±18 months focus around expected completion

### Query Structure
```
(asset_terms) AND (indication_terms) AND (clinical_bias)
```

### Asset Terms
- Primary: exact INN name
- Secondary: internal codes, generic names
- Tertiary: brand names, common misspellings
- Format: `"drug_name"[TIAB] OR "drug_name"[MH]`

### Indication Terms
- Primary: exact indication text
- Secondary: MeSH terms for disease area
- Tertiary: broader disease category terms
- Format: `"indication"[TIAB] OR "indication"[MH]`

### Clinical Bias
- `clinicaltrial[PTYP]` - clinical trial publications
- `randomized[TIAB]` - randomized studies
- `phase[TIAB]` - phase-specific studies
- `human[PTYP]` - human studies only

### Example Query
```
("pembrolizumab"[TIAB] OR "pembrolizumab"[MH] OR "MK-3475"[TIAB]) 
AND 
("non-small cell lung cancer"[TIAB] OR "lung neoplasms"[MH]) 
AND 
(clinicaltrial[PTYP] OR randomized[TIAB] OR "phase 3"[TIAB])
```

## Query Optimization

### Batch Size
- Group up to 10 trials per cycle
- Respect PubMed rate limits (≤8-10 req/s with API key)

### Fallback Strategies
1. **Broad asset search**: if no results, expand to drug class
2. **Indication expansion**: if no results, use broader disease terms
3. **Temporal focus**: prioritize recent publications (±18 months)

### Quality Filters
- Exclude: protocols, editorials, animal-only studies
- Include: results, reviews, meta-analyses
- Prioritize: human clinical data, P2/P3 studies

## Configuration
Query parameters are configurable via `rs_config.yaml`:
- `max_queries_per_trial`: maximum query variations to try
- `fallback_expansion`: whether to use broader search terms
- `temporal_focus_months`: window around catalyst dates
