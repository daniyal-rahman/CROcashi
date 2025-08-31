# BaseSpan System Implementation

## Overview

The BaseSpan system provides a foundation for **auditable, high-recall document processing** by implementing sentence-level and table-cell text spans with stable location anchors. This system enables both deterministic and LLM-assisted extraction paths while maintaining full provenance tracking.

## Architecture

### Core Components

1. **BaseSpan Ingest Worker** - Generates sentence-level and table-cell spans from document text
2. **Span Indexer** - Builds BM25 and dense indices for efficient retrieval
3. **Fuzzy Aligner** - Aligns quotes to spans or creates derived spans
4. **Span Triage Worker** - Implements budgeted selection for LLM processing

### Data Flow

```
Document Text → BaseSpan Ingest → BaseSpans → Indexing → Retrieval → Span Triage → LLM Processing
     ↓
Table Data → Table Cell Spans → Fuzzy Alignment → Derived Spans
```

## Database Schema

### BaseSpan Table

```sql
CREATE TABLE base_spans (
    span_id SERIAL PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES documents(doc_id),
    section TEXT NOT NULL,
    page INTEGER,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    text TEXT NOT NULL,
    is_table_cell BOOLEAN NOT NULL DEFAULT FALSE,
    table_id INTEGER,
    row INTEGER,
    col INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### DerivedSpan Table

```sql
CREATE TABLE derived_spans (
    derived_id SERIAL PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES documents(doc_id),
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    parent_span_ids INTEGER[] NOT NULL,
    text TEXT NOT NULL,
    similarity_score NUMERIC(3,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Configuration

The system is configured via `src/ncfd/extract/config/span_config.yaml`:

```yaml
# Span Generation Settings
span_generation:
  min_sentence_length: 50
  max_sentence_length: 400
  min_table_cell_length: 10
  max_table_cell_length: 200
  preserve_hyphens: false
  normalize_whitespace: true
  include_paragraph_spans: false

# Indexing Settings
indexing:
  bm25:
    k1: 1.2
    b: 0.75
    max_features: 10000
  dense:
    dimension: 768
    model_name: "sentence-transformers/all-MiniLM-L6-v2"

# Fuzzy Alignment Settings
fuzzy_alignment:
  similarity_threshold: 0.85
  use_levenshtein: true
  use_sequence_matcher: true
  use_token_set: true

# Span Triage Settings
span_triage:
  budgets:
    methods: 12
    results: 12
    tables: 5
  topup:
    per_field: 3
    max_attempts: 1
```

## Usage Examples

### 1. Ingest BaseSpans

```python
from ncfd.extract.workers import BaseSpanIngestWorker

# Create worker
ingest_worker = BaseSpanIngestWorker()

# Process document
result = ingest_worker.process({
    "doc_id": 123
})

if result.success:
    print(f"Generated {result.output['spans_generated']} spans")
    print(f"Text spans: {result.output['text_spans']}")
    print(f"Table spans: {result.output['table_spans']}")
```

### 2. Build Indices

```python
from ncfd.extract.workers import SpanIndexer

# Create indexer
indexer = SpanIndexer()

# Build indices for document
result = indexer.process({
    "doc_id": 123
})

# Search spans
search_results = indexer.search(
    query="overall response rate",
    section="Results",
    top_k=5
)
```

### 3. Fuzzy Alignment

```python
from ncfd.extract.workers import FuzzyAligner

# Create aligner
aligner = FuzzyAligner()

# Align quotes
result = aligner.process({
    "doc_id": 123,
    "quotes": [
        "The ORR was 15.8%",
        "Median PFS was 14 weeks"
    ]
})

for alignment in result.output['alignments']:
    if alignment['aligned']:
        print(f"Quote aligned to span {alignment['span_id']}")
        print(f"Similarity: {alignment['similarity_score']}")
```

### 4. Span Triage

```python
from ncfd.extract.workers import SpanTriageWorker

# Create triage worker
triage_worker = SpanTriageWorker()

# Perform triage
result = triage_worker.process({
    "doc_id": 123,
    "required_fields": [
        "endpoints", "survival_method", "design_archetype"
    ]
})

# Get selected spans
selected_spans = result.output['selected_spans']
must_hit_spans = result.output['must_hit_spans']
```

## Key Features

### 1. **Auditable Spans**
- Every fact is anchored to specific document locations
- Character-level position tracking (char_start, char_end)
- Page and section metadata preserved

### 2. **Dual Retrieval**
- **BM25**: Traditional keyword-based retrieval
- **Dense**: Semantic similarity using sentence transformers
- **Union**: Combines both approaches for maximum recall

### 3. **Fuzzy Alignment**
- Handles OCR errors and minor text variations
- Creates derived spans when exact matches aren't found
- Configurable similarity thresholds

### 4. **Budgeted Triage**
- Prevents LLM token explosion
- Reserves slots for critical fields
- Top-up mechanism for must-fill fields

### 5. **Section-Aware Processing**
- Methods, Results, Abstract, Discussion classification
- Table cell extraction with row/column metadata
- Section-specific budgets and constraints

### 6. **Metric Registry & Normalization**
- Oncology-specific metrics (median_ttp, median_os, orr_recist, ca125_response)
- Unit validation with hard-fail for mismatches
- Automatic normalization (weeks/months → days)
- Text extraction using regex patterns
- ResultsFactsheet validation against registry

### 7. **Denominator Resolution**
- Pattern-based extraction for analysis denominators
- Section-aware patterns (Methods > Results > Tables precedence)
- Ambiguity resolution using confidence and section ranking
- MethodCard integration for analysis_denominators
- Factsheet validation for n consistency

### 8. **Enhanced Span Triage**
- Must-fill field tracking with automatic top-up
- Field-specific queries for endpoints, survival, design
- Top-up mechanism (+3 spans for empty required fields)
- Section inference for automatic field classification

### 9. **LLM Fact Selection**
- Fact candidate generation from spans
- LLM classification (methods_detail, operational, limitation, safety, misc)
- Relevance scoring with numeric and type boosts
- Span validation to ensure auditability
- Claim export for downstream processing

### 10. **Span-Limited Normalization**
- Span-limited processing to prevent hallucinations
- Registry validation against metric definitions
- Unit normalization with automatic conversion
- Span reference validation for auditability
- ResultsFactsheet validation with detailed error reporting

### 11. **Enhanced ResultsDistiller**
- Quality metrics calculation and assessment
- Consistency validation across results
- Duplicate detection and merging
- Span reference validation
- Export capabilities for downstream processing

### 12. **GateProposer for Clinical Decisions**
- Evidence-based Go/No-Go decisions
- Configurable gate criteria with importance weighting
- Automatic threshold evaluation and scoring
- Evidence collection and reasoning
- Actionable recommendations for development

### 13. **FdaLens Regulatory Compliance**
- FDA regulatory requirement assessment
- Compliance status evaluation by category
- Evidence gap identification and recommendations
- FDA guidance reference integration
- Regulatory submission readiness assessment

### 14. **MemoComposer for Executive Summaries**
- Automated clinical memo generation
- Executive summary with key findings
- Section-based content organization
- Risk assessment and recommendations
- Professional memo formatting and export

## Integration with LLM Workers

The BaseSpan system integrates seamlessly with existing LLM workers:

```python
# Get triaged spans for LLM processing
triage_result = triage_worker.process({
    "doc_id": doc_id,
    "required_fields": required_fields
})

# Extract spans for specific sections
methods_spans = triage_result.output['selected_spans'].get('methods', [])
results_spans = triage_result.output['selected_spans'].get('results', [])

# Pass to LLM workers with span context
llm_input = {
    "doc_id": doc_id,
    "methods_spans": methods_spans,
    "results_spans": results_spans,
    "span_limited": True  # LLM only sees triaged spans
}
```

## Performance Considerations

### 1. **Indexing**
- BM25: Fast, lightweight, good for exact matches
- Dense: Slower but better semantic understanding
- Hybrid approach balances speed and quality

### 2. **Memory Usage**
- Configurable batch sizes for large documents
- FAISS indices for efficient similarity search
- Optional persistence to disk

### 3. **Scalability**
- Document-level indexing (not global)
- Configurable worker pools
- Timeout and memory limits

## Testing

Run the test suites to verify system functionality:

### Phase 1 Testing
```bash
python test_basespan_system.py
```

This will test:
- Configuration loading
- Worker instantiation
- Database connectivity
- Span generation logic
- Fuzzy matching algorithms

### Phase 2 Testing
```bash
python test_phase2_components.py
```

This will test:
- Metric registry and normalization
- Denominator resolver patterns
- Enhanced span triage with must-fill fields
- LLM selector for FactsBin
- Span-limited LLM normalizer
- Component integration

### Phase 3 Testing
```bash
python test_phase3_components.py
```

This will test:
- Enhanced ResultsDistiller with span validation
- GateProposer for clinical trial decisions
- FdaLens for regulatory compliance
- MemoComposer for executive summaries
- All components with span-limited processing
- End-to-end workflow integration

## Migration Path

### Phase 1: BaseSpan Foundation ✅
- [x] Database models (BaseSpan, DerivedSpan)
- [x] Span ingest worker
- [x] Basic indexing
- [x] Configuration system

### Phase 2: Advanced Features ✅
- [x] Metric registry and normalization
- [x] Denominator resolver
- [x] Enhanced span triage (must-fill + top-up)
- [x] LLM selector for FactsBin
- [x] Span-limited LLM normalizer

### Phase 3: LLM Integration ✅
- [x] LLM selector for FactsBin
- [x] LLM-assist normalizer
- [x] Enhanced ResultsDistiller with span validation
- [x] GateProposer for clinical trial decisions
- [x] FdaLens for regulatory compliance
- [x] MemoComposer for executive summaries

### Phase 4: Production Ready
- [ ] Global validators
- [ ] Provenance enforcement
- [ ] Performance optimization

## Troubleshooting

### Common Issues

1. **Import Errors**
   - Ensure all dependencies are installed
   - Check Python path includes `src/`

2. **Database Errors**
   - Verify database connection
   - Run database migrations for new tables

3. **Memory Issues**
   - Reduce batch sizes in configuration
   - Use document-level instead of global indexing

4. **Performance Issues**
   - Adjust similarity thresholds
   - Tune BM25 parameters
   - Consider using only BM25 for large-scale deployment

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Workers will log detailed execution information
```

## Contributing

When extending the BaseSpan system:

1. **Follow the worker pattern** - Inherit from `BaseWorker`
2. **Use typed configuration** - Extend the config dataclasses
3. **Maintain provenance** - Always track span references
4. **Add tests** - Include unit tests for new functionality
5. **Update documentation** - Document new features and APIs

## References

- [Original Specification](../original_spec.md)
- [Study Card Architecture](../Study_card_overhall.md)
- [Database Models](../../src/ncfd/db/models.py)
- [Worker Base Class](../../src/ncfd/extract/workers/base_worker.py)
