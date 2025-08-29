# Abstract Features Extraction Specification

## Overview
This document specifies the regex patterns and heuristics for extracting quantitative features and risk signals from PubMed abstracts.

## Feature Categories

### 1. Clinical Trial Identifiers
**Purpose**: Link abstracts to specific trials

**Patterns**:
- **NCT ID**: `NCT\d{8}`
- **Trial registration**: `trial\s+registration\s+number`
- **Study ID**: `study\s+ID[:\s]+([A-Z0-9-]+)`

**Examples**:
- "NCT02366143" → NCT ID
- "Trial registration number: NCT02366143" → Formal registration
- "Study ID: KEYNOTE-024" → Sponsor study ID

### 2. Phase Information
**Purpose**: Determine trial phase for relevance scoring

**Patterns**:
- **Phase 1**: `phase\s*1|P1|phase\s*I`
- **Phase 2**: `phase\s*2|P2|phase\s*II|phase\s*2b|P2B`
- **Phase 3**: `phase\s*3|P3|phase\s*III`
- **Phase 4**: `phase\s*4|P4|phase\s*IV`

**Examples**:
- "Phase 3 randomized trial" → P3
- "P2B dose-finding study" → P2B
- "Phase II/III study" → P2/3

### 3. Sample Size Information
**Purpose**: Assess trial power and statistical robustness

**Patterns**:
- **Total sample**: `(?:total\s+)?(?:n\s*=|sample\s+size\s*=|enrolled\s+)(\d+(?:,\d+)*)`
- **Per arm**: `(\d+(?:,\d+)*)\s+patients?\s+(?:per\s+arm|in\s+each\s+group)`
- **Randomized**: `(\d+(?:,\d+)*)\s+patients?\s+randomized`

**Examples**:
- "n=305 patients" → 305
- "Sample size: 1,234" → 1234
- "150 patients per arm" → 150 per arm

### 4. Primary Endpoint Results
**Purpose**: Extract primary outcome data for shortability assessment

**Patterns**:
- **Hazard Ratio**: `(?:HR|hazard\s+ratio)\s*[=:]\s*([0-9.]+)(?:\s*\(([0-9.]+)\s*-\s*([0-9.]+)\))?`
- **Odds Ratio**: `(?:OR|odds\s+ratio)\s*[=:]\s*([0-9.]+)(?:\s*\(([0-9.]+)\s*-\s*([0-9.]+)\))?`
- **Risk Ratio**: `(?:RR|risk\s+ratio)\s*[=:]\s*([0-9.]+)(?:\s*\(([0-9.]+)\s*-\s*([0-9.]+)\))?`
- **Response Rate**: `(?:ORR|overall\s+response\s+rate)\s*[=:]\s*([0-9.]+)%?`

**Examples**:
- "HR=1.15 (95% CI: 1.02-1.30)" → HR=1.15, CI: 1.02-1.30
- "ORR was 45.2%" → ORR=45.2%
- "Risk ratio 0.85 (0.72-1.01)" → RR=0.85, CI: 0.72-1.01

### 5. Statistical Significance
**Purpose**: Assess statistical robustness of results

**Patterns**:
- **P-values**: `p\s*[<≤=]\s*([0-9.]+)|p\s*=\s*([0-9.]+)`
- **Confidence intervals**: `(?:95%?\s+)?CI[:\s]+([0-9.]+)\s*-\s*([0-9.]+)`
- **Significance**: `(?:statistically\s+)?(?:significant|non-significant|ns)`

**Examples**:
- "p < 0.001" → p < 0.001
- "95% CI: 0.65-0.89" → CI: 0.65-0.89
- "statistically significant" → significant

### 6. Risk Signal Phrases
**Purpose**: Identify language indicating potential shortability

**Patterns**:
- **Primary endpoint failure**: `(?:did\s+not\s+meet|failed\s+to\s+meet|missed)\s+(?:primary|primary\s+endpoint)`
- **Futility**: `futility|futile|stopped\s+early\s+for\s+futility`
- **Non-inferiority miss**: `(?:did\s+not\s+demonstrate|failed\s+to\s+demonstrate)\s+non-inferiority`
- **Subgroup analysis**: `subgroup\s+analysis|post-hoc|post\s+hoc`
- **Interim analysis**: `interim\s+analysis|stopped\s+early|early\s+stopping`

**Examples**:
- "Did not meet primary endpoint" → Primary failure
- "Stopped early for futility" → Futility
- "Post-hoc subgroup analysis" → Subgroup analysis

### 7. Safety Signals
**Purpose**: Identify adverse event patterns

**Patterns**:
- **Discontinuations**: `(?:treatment\s+)?discontinuation|withdrawn|stopped\s+treatment`
- **Serious adverse events**: `(?:serious\s+)?adverse\s+events?|SAEs?|grade\s+[3-5]`
- **Deaths**: `deaths?|mortality|fatal`

**Examples**:
- "Treatment discontinuation rate 15%" → Discontinuations
- "Grade 3-4 adverse events" → High-grade AEs
- "No treatment-related deaths" → Safety mention

## Extraction Strategy

### 1. Pattern Matching
- **Regex compilation**: Pre-compile patterns for performance
- **Case sensitivity**: Use case-insensitive matching where appropriate
- **Context windows**: Extract surrounding text for validation

### 2. Validation Rules
- **Number ranges**: Validate that extracted numbers are reasonable
- **Unit consistency**: Ensure extracted values have appropriate units
- **Context validation**: Check that extracted values make sense in context

### 3. Confidence Scoring
- **High confidence**: Exact pattern matches with clear context
- **Medium confidence**: Pattern matches with some ambiguity
- **Low confidence**: Weak pattern matches or unclear context

## Implementation Notes

### Performance Considerations
- **Batch processing**: Process multiple abstracts together
- **Pattern caching**: Cache compiled regex patterns
- **Early termination**: Stop extraction if key signals found

### Quality Assurance
- **False positive filtering**: Remove obviously incorrect extractions
- **Context validation**: Ensure extracted values are clinically relevant
- **Manual review**: Flag uncertain extractions for human review

### Configuration
```yaml
extraction:
  patterns:
    enabled: true
    confidence_threshold: 0.7
    max_context_chars: 100
  validation:
    check_ranges: true
    validate_units: true
    require_context: true
  output:
    include_confidence: true
    include_context: true
    include_span: true
```

## Output Format

### Entity Structure
```json
{
  "ent_type": "effect_size",
  "value_text": "HR=1.15",
  "value_norm": 1.15,
  "confidence": 0.95,
  "char_start": 245,
  "char_end": 252,
  "context": "The hazard ratio was HR=1.15 (95% CI: 1.02-1.30)",
  "detector": "regex"
}
```

### Confidence Levels
- **0.9-1.0**: High confidence, clear pattern match
- **0.7-0.9**: Medium confidence, good pattern match
- **0.5-0.7**: Low confidence, weak pattern match
- **<0.5**: Very low confidence, uncertain extraction
