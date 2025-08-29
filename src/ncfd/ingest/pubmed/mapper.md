# PubMed Mapper Specification

## Overview
This document specifies how to map PubMed E-utilities API responses to our database staging tables.

## Field Mappings

### ESearch Response → documents
```
pmid → documents.pmid
query → documents.title (temporary, replaced by ESummary)
discovered_at → documents.discovered_at
source_type → 'PubMed'
status → 'discovered'
```

### ESummary Response → document_citations
```
pmid → document_citations.pmid
doi → document_citations.doi
journal → document_citations.journal
pub_date → document_citations.pub_year
article_type → document_citations.article_type
mesh_terms → document_citations.mesh_jsonb
substance_names → document_citations.substances_jsonb
```

### ESummary Response → documents
```
title → documents.title
published_at → documents.published_at
publisher → 'PubMed / NLM'
status → 'fetched'
fetched_at → documents.fetched_at
```

### EFetch Response → document_text
```
abstract → document_text.abstract_text
char_count → document_text.char_count_abstract
status → 'parsed'
parsed_at → documents.parsed_at
```

### EFetch Response → document_entities
```
nct_ids → document_entities (ent_type='nct_id')
asset_names → document_entities (ent_type='asset_name')
phases → document_entities (ent_type='phase')
endpoints → document_entities (ent_type='endpoint')
effect_sizes → document_entities (ent_type='effect_size')
p_values → document_entities (ent_type='p_value')
```

### EFetch Response → document_links
```
nct_in_text → document_links (link_type='nct_in_text')
asset_in_text → document_links (link_type='asset_in_text')
asset_in_mesh → document_links (link_type='asset_in_mesh')
```

## Data Transformation

### Date Handling
- **ESummary dates**: Convert to UTC datetime
- **Format variations**: YYYY, YYYY-MM, YYYY-MM-DD
- **Fallback**: Use discovered_at if parsing fails

### Text Normalization
- **Abstracts**: Remove HTML tags, normalize whitespace
- **Titles**: Title case, remove extra punctuation
- **MeSH terms**: Convert to lowercase, normalize separators

### Entity Extraction
- **NCT IDs**: Regex pattern `NCT\d{8}`
- **Asset names**: Match against asset_aliases table
- **Phases**: Extract P1, P2, P2B, P3, P4 patterns
- **Numbers**: Extract p-values, effect sizes, sample sizes

## Quality Checks

### Required Fields
- **pmid**: Must be valid PMID format
- **title**: Must be non-empty after normalization
- **abstract**: Must be >50 characters for U1 stage

### Validation Rules
- **PMID uniqueness**: Check for duplicates before insert
- **Text quality**: Reject abstracts that are mostly HTML/XML
- **Language**: Prefer English abstracts (detect via lang field)

### Error Handling
- **Missing abstracts**: Log and mark for manual review
- **Parse failures**: Store raw text, mark status='error'
- **Entity conflicts**: Flag for human review

## Performance Considerations

### Batch Operations
- **Insert**: Use bulk_insert_mappings for multiple documents
- **Update**: Batch status updates by stage
- **Entity extraction**: Process in chunks to avoid memory issues

### Indexing Strategy
- **Primary**: pmid, source_type, status
- **Secondary**: published_at, title (for text search)
- **Composite**: (source_type, status, published_at)

## Configuration

### Mapper Settings
```yaml
mapper:
  min_abstract_length: 50
  max_title_length: 500
  entity_extraction:
    enabled: true
    confidence_threshold: 0.8
  quality_checks:
    require_abstract: true
    require_title: true
    validate_pmid: true
```

### Entity Patterns
```yaml
patterns:
  nct_id: "NCT\\d{8}"
  phase: "(P[1-4]|P2B|P2/3)"
  p_value: "p\\s*[<≤]\\s*0\\.\\d+"
  effect_size: "(HR|OR|RR)\\s*=\\s*[0-9.]+"
```
