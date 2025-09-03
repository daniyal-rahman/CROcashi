# LLM-First, Provenance-Second Architecture

## Overview

This document describes the new LLM-first, provenance-second architecture implemented in the study card system. This architecture addresses the limitations of the previous span-limited approach by allowing LLMs to read raw paper text while maintaining auditability through deterministic provenance backtracing.

## Architecture Principles

### 1. LLM-First Extraction
- **LLM reads raw paper text** (not pre-triaged spans)
- **Extracts results with verbatim quotes** (≤30 words)
- **No span attachment** at this stage
- **Free-form reading** to avoid missing information due to span triage

### 2. Provenance-Second Backtracing
- **Deterministic span finding** for LLM-extracted values
- **BM25 + fuzzy matching** to locate exact text spans
- **Numeric overlap validation** to ensure accuracy
- **Multi-span provenance** support (e.g., TTP numeric + Methods KM span)

### 3. Trust Scoring and Fusion
- **Deduplication** by metric/timepoint/slice
- **Trust scoring** based on source, provenance, and confidence
- **Metadata preservation** (verbatim quotes, evidence kind, etc.)
- **Deterministic preference** in ties

## Architecture Components

### Phase A: LLM Results Drafter
**File:** `src/ncfd/extract/workers/llm/llm_results_drafter.py`

**Purpose:** Read raw paper text and extract results with verbatim quotes.

**Inputs:**
- `raw_doc_text`: Full document text
- `doc_id`: Document identifier
- `trial_context`: Trial context information

**Outputs:**
- `LLMResultsDraft`: Draft results with verbatim quotes and evidence metadata

**Key Features:**
- Section-based text chunking
- Regex fallback for metric extraction
- Confidence scoring based on quote quality
- Evidence kind classification (text/table)

### Phase B: Provenance Backtracer
**File:** `src/ncfd/extract/workers/provenance_backtracer.py`

**Purpose:** Find exact spans that justify LLM-extracted values.

**Inputs:**
- `llm_extraction_draft`: LLM draft with verbatim quotes
- `raw_doc_text`: Full document text
- `evidence_spans`: Pre-existing spans (optional)

**Outputs:**
- `LLMExtractionDraft`: Same draft with attached spans

**Key Features:**
- BM25 candidate retrieval
- Fuzzy text alignment
- Numeric overlap validation
- OCR noise handling
- Section bonus scoring

### Phase C: Results Finalizer
**File:** `src/ncfd/extract/workers/results_finalizer.py`

**Purpose:** Merge deterministic and LLM results into canonical format.

**Inputs:**
- `deterministic_results`: ResultsFactsheet from deterministic path
- `llm_results_draft`: LLMResultsDraft with resolved spans
- `denominators`: Denominator information

**Outputs:**
- `ResultsFactsheet`: Canonical results with metadata

**Key Features:**
- Deduplication by metric/timepoint/slice
- Trust scoring and source preference
- Denominator resolution from quotes
- Metadata preservation

## Data Models

### LLMResultsDraft
```python
@dataclass
class LLMResultsDraft(BaseModel):
    doc_id: str
    results: List[Dict[str, Any]]
    verbatim_quotes: List[str]
    evidence_kinds: List[EvidenceKind]
    section_hints: List[str]
    confidence_llm: List[float]
    evidence_status: List[EvidenceStatus]
    span_ids: List[str]  # To be filled by backtracer
    provenance_status: List[str]  # To be filled by backtracer
```

### Final ResultsFactsheet Row
```python
{
    "metric": "orr_recist",
    "value": 15.8,
    "units": "percent",
    "n": 19,
    "span_ids": ["pmc:...Results:char600-650", "pmc:...table:r1c1"],
    "source": "llm",
    "provenance_score": 0.92,
    "trust_score": 0.88,
    "metadata": {
        "verbatim_quote": "Overall response rate was 15.8% (3/19 patients)",
        "evidence_kind": "text",
        "section_hint": "Results",
        "confidence_llm": 0.86
    }
}
```

## Configuration

### Pipeline Configuration
```yaml
# LLM Path Configuration
llm_path:
  mode: "raw_first"         # vs "span_limited"
  require_quotes: true
  backtrace:
    bm25_topk: 20
    dense_topk: 10
    fuzzy_threshold: 0.86
    numeric_strict: true
    section_bonus: 0.1
    allow_table_only: true

# Fusion Configuration
fusion:
  prefer_deterministic_if_tie: true
  min_provenance_score: 0.75
  hard_fail_if_missing_spans: true
```

## Orchestration Flow

### Updated Late Fusion Orchestrator
**File:** `src/ncfd/extract/orchestrate/late_fusion_orchestrator.py`

**New Flow:**
1. **Deterministic Path**: Process pre-triaged spans (unchanged)
2. **LLM Path**: 
   - LLMResultsDrafter → Draft results with quotes
   - ProvenanceBacktracer → Find spans for draft results
   - ResultsFinalizer → Merge with deterministic results
3. **Late Fusion**: Combine and validate final results

## Example: PMC2978916

### LLM Drafter Output
```python
# ORR result
{
    'metric': 'orr_recist',
    'value': 15.8,
    'units': 'percent',
    'verbatim_quote': 'Overall response rate was 15.8% (3/19 patients)',
    'evidence_kind': 'text',
    'section_hint': 'Results',
    'confidence_llm': 0.86
}

# TTP result
{
    'metric': 'median_ttp',
    'value': 14.0,
    'units': 'weeks',
    'verbatim_quote': 'Median time to progression was 14 weeks',
    'evidence_kind': 'text',
    'section_hint': 'Results',
    'confidence_llm': 0.82
}
```

### Provenance Backtracer Output
```python
# ORR with resolved spans
{
    'span_ids': ['PMC2978916#sec:Results:char600-650'],
    'provenance_status': 'resolved'
}

# TTP with multi-span provenance
{
    'span_ids': [
        'PMC2978916#sec:Results:char700-750',  # Numeric result
        'PMC2978916#sec:Methods:char300-400'   # KM method
    ],
    'provenance_status': 'resolved'
}
```

### Final ResultsFactsheet
```python
{
    'metric': 'orr_recist',
    'value': 15.8,
    'units': 'percent',
    'n': 19,  # Extracted from quote
    'span_ids': ['PMC2978916#sec:Results:char600-650'],
    'source': 'llm',
    'provenance_score': 0.92,
    'trust_score': 0.88,
    'metadata': {
        'verbatim_quote': 'Overall response rate was 15.8% (3/19 patients)',
        'evidence_kind': 'text',
        'section_hint': 'Results',
        'confidence_llm': 0.86
    }
}
```

## Benefits

### 1. Improved Coverage
- **LLM reads full paper** instead of being limited by span triage
- **Captures information** that might be missed by deterministic patterns
- **Handles complex language** and paraphrasing

### 2. Maintained Auditability
- **Every result has spans** that justify the extraction
- **Deterministic provenance** through fuzzy matching
- **Numeric validation** ensures accuracy

### 3. Flexible Architecture
- **Backward compatible** with existing deterministic path
- **Configurable trust scoring** and fusion preferences
- **Metadata preservation** for debugging and analysis

### 4. Quality Assurance
- **Verbatim quotes** enable human verification
- **Confidence scoring** based on multiple factors
- **Denominator extraction** from quotes
- **Multi-span provenance** for complex results

## Testing

### Test Suite
**File:** `tests/test_llm_first_architecture.py`

**Key Tests:**
- LLM Results Drafter extraction
- Provenance Backtracer span finding
- Results Finalizer merging
- PMC2978916 example validation
- Denominator extraction
- Trust scoring
- Numeric sanity checks

### Running Tests
```bash
pytest tests/test_llm_first_architecture.py -v
```

## Migration Guide

### For Existing Code
1. **Update imports** to use new workers
2. **Add raw_doc_text** to pipeline inputs
3. **Update configuration** with new LLM path settings
4. **Handle new metadata** in results processing

### For New Implementations
1. **Use LLMResultsDrafter** instead of ResultsDistiller for LLM path
2. **Always include raw_doc_text** in pipeline inputs
3. **Configure backtracing parameters** based on document quality
4. **Handle provenance status** in downstream processing

## Future Enhancements

### Planned Improvements
1. **True LLM API integration** (currently uses regex fallback)
2. **Dense retrieval** for better candidate selection
3. **Table-specific backtracing** for structured data
4. **Multi-language support** for international studies
5. **Advanced trust scoring** with domain-specific rules

### Configuration Tuning
1. **Per-document backtracing parameters** based on OCR quality
2. **Metric-specific confidence thresholds**
3. **Domain-specific trust scoring** for different study types
4. **Adaptive fuzzy matching** based on document characteristics
