# Study Card ID Conventions

This document defines the ID formats for all study card artifacts to ensure consistency and uniqueness across the system.

## ID Formats

### Document IDs (`doc_id`)

Document IDs follow the pattern: `{source}:{identifier}`

**Examples:**
- `pmid:12345678` - PubMed article
- `doi:10.1000/123456` - DOI reference
- `ctgov:NCT01234567` - ClinicalTrials.gov trial
- `pr:2024-01-15-company-announcement` - Press release
- `sec:8-K-2024-01-15` - SEC filing
- `fda:approval-2024-001` - FDA decision

**Rules:**
- Use lowercase for source prefixes
- Include full identifier (no truncation)
- Use consistent separators (`:` for standard sources, `-` for dates)

### Span IDs (`span_id`)

Span IDs follow the pattern: `{doc_id}#p{page}:{start}-{end}`

**Examples:**
- `pmid:12345678#sec:Methods:char0-150` - Methods section, characters 0-150
- `ctgov:NCT01234567#sec:Results:char200-450` - Results section, characters 200-450
- `doi:10.1000/123456#sec:Methods:char100-300` - Methods section, characters 100-300
- `pmid:12345678#sec:Methods:char0-150:p1` - Methods section, characters 0-150, page 1

**Rules:**
- Section names are case-sensitive (Methods, Results, Table, Figure, Protocol, SAP)
- Character positions are 0-based
- End position is exclusive
- Use `#sec:` separator between doc_id and section
- Use `:char` separator between section and character range
- Use `-` separator between start and end positions
- Optional page context can be added as `:p{page}` for additional precision

**Special Cases:**
- Table references: `{doc_id}#table{table_id}:{row}-{col}`
- Figure references: `{doc_id}#fig{figure_id}:{region}`
- Protocol sections: `{doc_id}#protocol:{section}:{subsection}`

### Claim IDs (`claim_id`)

Claim IDs follow the pattern: `claim_{timestamp}_{hash}`

**Examples:**
- `claim_20240115_143022_a1b2c3d4` - Claim from 2024-01-15 14:30:22
- `claim_20240115_143022_e5f6g7h8` - Another claim from same timestamp

**Rules:**
- Use `claim_` prefix
- Include timestamp in format `YYYYMMDD_HHMMSS`
- Include 8-character hash suffix for uniqueness
- Hash is computed from claim content + timestamp

### Gate IDs (`gate_id`)

Gate IDs follow the pattern: `gate_{family}_{timestamp}_{hash}`

**Examples:**
- `gate_g1_20240115_143022_a1b2c3d4` - G1 (signal) gate
- `gate_g2_20240115_143022_e5f6g7h8` - G2 (mechanism/delivery) gate
- `gate_g3_20240115_143022_i9j0k1l2` - G3 (design) gate

**Rules:**
- Use `gate_` prefix
- Include gate family (g1, g2, g3)
- Include timestamp in format `YYYYMMDD_HHMMSS`
- Include 8-character hash suffix for uniqueness

### Assessment IDs (`assessment_id`)

Assessment IDs follow the pattern: `assessment_{gate_id}_{timestamp}`

**Examples:**
- `assessment_gate_g1_20240115_143022_a1b2c3d4_20240115_150000`
- `assessment_gate_g2_20240115_143022_e5f6g7h8_20240115_150000`

**Rules:**
- Use `assessment_` prefix
- Include the gate_id being assessed
- Include assessment timestamp in format `YYYYMMDD_HHMMSS`

### Decision Record IDs (`decision_id`)

Decision record IDs follow the pattern: `decision_{trial_id}_{timestamp}`

**Examples:**
- `decision_NCT01234567_20240115_160000`
- `decision_pmid_12345678_20240115_160000`

**Rules:**
- Use `decision_` prefix
- Include the trial_id being evaluated
- Include decision timestamp in format `YYYYMMDD_HHMMSS`

## ID Generation Functions

The system provides utility functions for generating these IDs:

```python
from src.ncfd.utils.study_card_utils import (
    generate_span_id,
    generate_claim_id,
    generate_gate_id
)

# Generate span ID
span_id = generate_span_id("pmid:12345678", "Methods", 0, 150)
# Result: "pmid:12345678#sec:Methods:char0-150"

# Generate span ID with page context
span_id = generate_span_id("pmid:12345678", "Methods", 0, 150, page=1)
# Result: "pmid:12345678#sec:Methods:char0-150:p1"

# Generate claim ID
claim_id = generate_claim_id()
# Result: "claim_20240115_143022_a1b2c3d4"

# Generate gate ID
gate_id = generate_gate_id("g1")
# Result: "gate_g1_20240115_143022_a1b2c3d4"
```

## ID Validation

All IDs should be validated before use:

```python
def validate_span_id(span_id: str) -> bool:
    """Validate span ID format."""
    import re
    pattern = r'^.+?#sec:[A-Za-z]+:char\d+-\d+(:p\d+)?$'
    return bool(re.match(pattern, span_id))

def validate_doc_id(doc_id: str) -> bool:
    """Validate document ID format."""
    import re
    pattern = r'^[a-z]+:.+$'
    return bool(re.match(pattern, doc_id))
```

## ID Uniqueness Guarantees

- **Document IDs**: Unique by source + identifier combination
- **Span IDs**: Unique by doc_id + page + character range
- **Claim IDs**: Unique by timestamp + hash combination
- **Gate IDs**: Unique by family + timestamp + hash combination
- **Assessment IDs**: Unique by gate_id + assessment timestamp
- **Decision IDs**: Unique by trial_id + decision timestamp

## Migration and Versioning

When IDs need to change:

1. **Never reuse IDs** - always generate new ones
2. **Maintain backward compatibility** - old IDs should still resolve
3. **Use version prefixes** if needed: `v2_claim_...`
4. **Update all references** when changing ID formats
5. **Document changes** in version history

## Examples in Practice

```python
# Complete example of ID generation for a study
trial_id = "NCT01234567"
doc_id = f"ctgov:{trial_id}"

# Create spans
span1_id = generate_span_id(doc_id, "Methods", 0, 200)
span2_id = generate_span_id(doc_id, "Results", 200, 400)

# Create claims
claim1_id = generate_claim_id()
claim2_id = generate_claim_id()

# Create gates
gate1_id = generate_gate_id("g1")
gate2_id = generate_gate_id("g2")

# Create assessments
assessment1_id = f"assessment_{gate1_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
assessment2_id = f"assessment_{gate2_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Create decision record
decision_id = f"decision_{trial_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
```
