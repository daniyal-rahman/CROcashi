# Study Card System ID Conventions

This document defines the standardized ID formats and provenance tracking for the Study Card System.

## Document IDs (doc_id)

### Format: `{source}:{accession}`

- **PubMed Central**: `pmc:PMC2978916`
- **PubMed**: `pmid:21076619`
- **ClinicalTrials.gov**: `ctgov:NCT01234567`
- **FDA**: `fda:NDA123456`
- **Press Release**: `pr:company_2024_01_15`
- **SEC Filing**: `sec:8-K_2024_01_15`

### Rules
- Use lowercase for source prefixes
- Preserve exact accession format from source
- No spaces or special characters in doc_id

## Span IDs (span_id)

### Format: `{doc_id}#<locator>`

### Section-based Locators (Preferred)
- **Methods**: `sec:Methods:char234-471`
- **Results**: `sec:Results:char120-356`
- **Statistics**: `sec:Statistics:char89-234`
- **Assessment**: `sec:Assessment:char567-789`

### Page-based Locators (Fallback)
- **Page + Char**: `p1:char234-471`
- **Page + Line**: `p1:line15-23`

### Table Locators
- **Row-based**: `table:3:rRECIST_total`
- **Cell-based**: `table:3:r2c3`
- **Header-keyed**: `table:3:cell:response_rate`

### Rules
- Use `sec:` prefix when structured sections are available
- Fall back to `p{page}:` when only page numbers available
- For tables, use descriptive row names when possible
- Char ranges should be non-overlapping and precise

## Claim IDs (claim_id)

### Format: ULID (Universally Unique Lexicographically Sortable Identifier)

- **Example**: `01H9X8P7Q6R5S4T3U2V1W0X9Y8Z7A6B5C4D3E2F1G0`
- **Properties**: 
  - 26 characters
  - Time-sortable
  - URL-safe
  - Monotonic sort order

### Usage
- Every extracted claim gets a unique claim_id
- Used for cross-referencing in gates and assessments
- Immutable once assigned

## Card IDs

### Format: ULID (same as claim_id)

- **DocumentCard**: `01H9X8P7Q6R5S4T3U2V1W0X9Y8Z7A6B5C4D3E2F1G0`
- **MethodCard**: `01H9X8P7Q6R5S4T3U2V1W0X9Y8Z7A6B5C4D3E2F1G1`
- **ResultsFactsheet**: `01H9X8P7Q6R5S4T3U2V1W0X9Y8Z7A6B5C4D3E2F1G2`

### Rules
- Each card type gets its own ULID namespace
- IDs are globally unique across all card types
- Used for lineage tracking and cross-references

## Gate IDs (gate_id)

### Format: `gate:{family}:{sequence}`

- **G1 (Signal)**: `gate:G1:01`
- **G2 (Mechanism)**: `gate:G2:01`
- **G3 (Design)**: `gate:G3:01`
- **Sub-gates**: `gate:G1:01a`, `gate:G1:01b`

### Rules
- Family codes: G1, G2, G3
- Sequence numbers: 01, 02, 03...
- Sub-gates use letters: a, b, c...

## Assessment IDs (assessment_id)

### Format: `assess:{gate_id}:{timestamp}`

- **Example**: `assess:gate:G1:01:20240115T143022Z`
- **Format**: `assess:{gate_id}:{YYYYMMDDTHHMMSSZ}`

### Rules
- Include gate_id for traceability
- Use ISO 8601 timestamp format
- UTC timezone

## Decision IDs (decision_id)

### Format: `decision:{trial_id}:{version}`

- **Example**: `decision:ovarian_cancer_atrasentan:v1`
- **Format**: `decision:{trial_identifier}:v{version_number}`

### Rules
- Trial identifier should be descriptive
- Version numbers: v1, v2, v3...
- Include trial context for clarity

## Input Hash (input_hash)

### Format: SHA256 hash of ordered inputs

### Input Order
1. Document hashes (sorted by doc_id)
2. Prompt version
3. Worker configuration hash
4. Input parameters (sorted by key)

### Example
```python
import hashlib
import json

def compute_input_hash(docs, prompt_version, config, params):
    # Sort inputs for deterministic hashing
    doc_hashes = sorted([(d.doc_id, d.hash) for d in docs])
    sorted_params = sorted(params.items())
    
    # Create ordered input string
    input_str = json.dumps({
        'docs': doc_hashes,
        'prompt_version': prompt_version,
        'config': config,
        'params': sorted_params
    }, sort_keys=True)
    
    # Return SHA256 hash
    return hashlib.sha256(input_str.encode()).hexdigest()
```

### Rules
- Must be deterministic (same inputs = same hash)
- Include all inputs that affect output
- Use for lineage tracking and caching

## Provenance Anchors

### Format: List of span_ids

### Usage
- Every artifact must have ≥1 provenance anchor
- Anchors point to source text spans
- Used for audit trail and verification

### Example
```json
{
  "provenance_anchors": [
    "pmc:PMC2978916#sec:Methods:char234-471",
    "pmc:PMC2978916#sec:Results:char120-356"
  ]
}
```

## Validation Rules

### Hard Requirements
1. **No generic IDs**: Every ID must be specific and traceable
2. **Span resolution**: Every span_id must resolve to a valid document
3. **Non-overlapping**: Char ranges within a document must not overlap
4. **Consistent format**: All IDs of the same type must follow the same format
5. **Input hash presence**: Every artifact must have a non-null input_hash

### Quality Checks
1. **Anchor validation**: Verify all span_ids resolve to existing spans
2. **Format validation**: Ensure IDs match expected patterns
3. **Uniqueness**: Check for duplicate IDs within the same namespace
4. **Completeness**: Verify all required ID fields are present

## Implementation Notes

### ID Generation
- Use ULID library for time-sortable IDs
- Generate IDs at creation time, not at serialization
- Store IDs as strings in JSON for compatibility

### Span Resolution
- Implement span lookup by doc_id + locator
- Cache resolved spans for performance
- Validate span existence before creating references

### Lineage Tracking
- Store input_hash on every artifact
- Link parent-child relationships via IDs
- Enable replay of processing pipeline
