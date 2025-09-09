# PubMed Pipeline Specification

## Overview
This document specifies the end-to-end PubMed literature processing pipeline with state transitions and decision points.

## Pipeline Stages

### Stage U1+: Unified Discovery and Abstract Processing
**Purpose**: Discover potentially relevant documents and extract/analyze abstract text for R/S scoring

**Inputs**:
- Trial metadata (asset, indication, phase, NCT ID)
- Asset aliases and synonyms
- Indication keywords and MeSH terms

**Process**:
1. **Query Construction**: Build PubMed ESearch query
2. **ESearch**: Execute query to get PMID list
3. **ESummary**: Fetch metadata for PMIDs
4. **Document Creation**: Insert into documents table with pubmed_meta.esummary_jsonb
5. **Candidate Linking**: Create trial_doc_candidates rows with stage='U1_discovery'
6. **EFetch**: Retrieve abstract text for PMIDs
7. **Text Storage**: Update document_text.abstract_text
8. **Entity Extraction**: Extract NCTs, assets, phases, numbers
9. **R/S Scoring**: Calculate relevance and shortability scores
10. **Linking**: Create document_links for discovered entities

**Outputs**:
- documents rows with status='discovered' → 'abstracted' → 'scored'
- pubmed_meta with esummary_jsonb for audit/reproducibility
- document_text with abstract content
- document_entities with extracted information
- document_links with trial/asset connections
- doc_rs_scores with R/S tiers
- trial_doc_candidates with stage='U1_discovery' → 'U1_abstract'

**Decision Point**:
- **Keep**: R≥1 and S≥S1 documents
- **Drop**: R0 or S0 documents (keep citation only)
- **Park**: Low-R documents for later review

**Modes**:
- **Discovery+Process**: Full pipeline from query to scoring (default)
- **Process-only**: Skip discovery, process existing documents (legacy compatibility)

### Legacy Stage U0: Metadata Discovery (Deprecated)
**Status**: Deprecated - functionality integrated into U1+

The U0 stage has been folded into U1+ to simplify orchestration and reduce complexity. 
All U0 functionality (ESearch, ESummary, document creation, candidate linking) is now 
performed as part of the U1+ discovery phase.

### Stage OA: Open Access Full Text (Optional)
**Purpose**: Fetch full text for high-priority documents

**Inputs**:
- Documents with R3S3 or R3S2 (ambiguous)
- PMC availability check

**Process**:
1. **ELink**: Convert PMID to PMC ID
2. **OA Check**: Verify open access status
3. **EFetch**: Retrieve full text content
4. **Text Storage**: Update document_text.fulltext_text
5. **Entity Update**: Extract additional entities from full text

**Outputs**:
- document_text with full text content
- Updated document_entities
- fulltext_ttl_date for non-candidates

**Decision Point**:
- **Fetch**: Only for R3S3 or R3S2 with ambiguity
- **Skip**: For all other documents

## State Transitions

### Document Status Flow
```
discovered → fetched → parsed → linked → scored → parked/promoted
    ↓           ↓        ↓        ↓        ↓
   U0         U0       U1       U1       U1
```

### Trial State Updates
After each stage, update `trial_lit_state`:
- `n_docs_seen`: Total documents processed
- `n_docs_selected`: Documents kept for analysis
- `best_S_Rge2`: Best S score among R≥2 documents
- `p_short`: Posterior probability of shortability
- `uncertainty`: Current uncertainty level

## Decision Logic

### Document Selection (U1 → U1)
```python
if R_score >= 0.35:  # R1 threshold
    if S_score >= 0.20:  # S1 threshold
        keep_document()
    else:
        park_document(reason="low_shortability")
else:
    drop_document(reason="low_relevance")
```

### Full Text Fetch (U1 → OA)
```python
if R_tier in ['R3'] and S_tier in ['S3', 'S2']:
    if has_pmc_oa():
        fetch_full_text()
    else:
        mark_no_oa()
else:
    skip_full_text()
```

### Trial Promotion
```python
if exists_R3S3() or count_R3S2_R2S3() >= 2:
    promote_trial()
elif best_S_Rge2 <= S1 and no_promising_abstracts():
    park_trial()
elif plateau_detected():
    stop_trial()
```

## Error Handling

### API Failures
- **Rate limiting**: Exponential backoff and retry
- **Service errors**: Circuit breaker pattern
- **Network issues**: Retry with increasing delays

### Data Quality Issues
- **Missing abstracts**: Log and mark for review
- **Parse failures**: Store raw content, flag errors
- **Entity conflicts**: Human review required

### Pipeline Failures
- **Stage timeout**: Mark documents as failed
- **Database errors**: Rollback and retry
- **Resource exhaustion**: Pause pipeline

## Monitoring & Metrics

### Stage Performance
- **U0 throughput**: documents discovered per minute
- **U1 processing**: abstracts processed per minute
- **OA fetch rate**: full texts retrieved per hour

### Quality Metrics
- **Abstract coverage**: % of documents with abstracts
- **Entity extraction**: precision/recall of extracted entities
- **R/S consistency**: inter-annotator agreement

### Cost Tracking
- **API calls**: requests per trial per stage
- **Storage usage**: text content size per document
- **Processing time**: CPU time per document

## Configuration

### Pipeline Settings
```yaml
pipeline:
  stages:
    u0:
      batch_size: 100
      max_retries: 3
      timeout_seconds: 30
    u1:
      batch_size: 50
      entity_extraction: true
      rs_scoring: true
    oa:
      enabled: true
      max_per_trial: 2
      ttl_days: 90
```

### Thresholds
```yaml
thresholds:
  r_tiers: {r3: 0.75, r2: 0.55, r1: 0.35}
  s_tiers: {s3: 0.70, s2: 0.45, s1: 0.20}
  promotion:
    r3s3_required: false
    r3s2_r2s3_count: 2
    plateau_epsilon: 0.03
```
