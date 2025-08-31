# Ingest & BaseSpan Test Suite for PMC2978916

## Overview

This test suite validates the **correctness of span inventory (the ground truth backbone)** for the Study Card system. It focuses specifically on the ingest and BaseSpan functionality using PMC2978916 as the canonical test case.

## 🎯 **Test Objectives**

### **Primary Goal**
Ensure that the span inventory backbone produces **100% accurate, reproducible, and immutable** text spans that serve as the foundation for all downstream processing.

### **Key Requirements**
- **Sentence segmentation**: De-hyphenation, whitespace normalization, stable span_ids
- **Table mining**: Numeric cells + headers extracted with row/col preserved
- **DerivedSpan alignment**: Fuzzy align quotes (≥0.85) snap to offsets or become DerivedSpans
- **Immutability**: Re-ingest → identical span_id + hashes
- **Gold span coverage**: 100% of gold spans present with exact (char_start, char_end, section)

## 📋 **Test Categories**

### **1. Sentence Segmentation** (`test_1_sentence_segmentation`)
- **Goal**: Verify sentence-level text processing
- **Tests**:
  - Basic sentence segmentation with configurable length limits
  - De-hyphenation of broken words
  - Whitespace normalization
  - Span ID stability and uniqueness
  - Character offset consistency
- **Pass Criteria**: All spans generated, no broken hyphens, normalized whitespace, unique span IDs

### **2. Table Mining** (`test_2_table_mining`)
- **Goal**: Verify table structure extraction
- **Tests**:
  - Table span identification and metadata
  - Numeric cell extraction
  - Header extraction
  - Row/column preservation
- **Pass Criteria**: Table spans have proper metadata, numeric values extracted, headers identified

### **3. DerivedSpan Alignment** (`test_3_derivedspan_alignment`)
- **Goal**: Verify fuzzy text alignment functionality
- **Tests**:
  - High similarity alignment (≥0.85) to existing spans
  - Medium similarity handling (DerivedSpan creation or rejection)
  - Low similarity rejection (<0.85)
- **Pass Criteria**: High similarity aligns correctly, low similarity rejected, similarity scores accurate

### **4. Immutability** (`test_4_immutability`)
- **Goal**: Verify reproducible span generation
- **Tests**:
  - Identical input produces identical output
  - Same span IDs across runs
  - Same character offsets across runs
  - Same text content across runs
  - Hash consistency (if implemented)
- **Pass Criteria**: 100% reproducibility across multiple runs

### **5. Gold Span Coverage** (`test_5_gold_span_coverage`)
- **Goal**: Verify 100% coverage of gold standard spans
- **Tests**:
  - All gold span texts present in ingested output
  - Character offset accuracy (within 10 characters)
  - Section consistency
  - Span ID format validation
- **Pass Criteria**: 100% gold span coverage, accurate offsets, correct sections

### **6. Span Budget Adherence** (`test_6_span_budget_adherence`)
- **Goal**: Verify budget constraints are respected
- **Tests**:
  - Methods section budget enforcement
  - Results section budget enforcement
  - Total span budget enforcement
- **Pass Criteria**: All budgets respected, no overflows

### **7. Reproducibility Across Seeds** (`test_7_reproducibility_across_seeds`)
- **Goal**: Verify deterministic behavior across different seeds
- **Tests**:
  - Span count consistency across seeds
  - Span ID consistency across seeds
  - Text content consistency across seeds
- **Pass Criteria**: Identical output across all seeds

### **8. Policy Matrix Testing** (`test_8_policy_matrix_testing`)
- **Goal**: Verify different policy configurations work correctly
- **Tests**:
  - Strict KM inference policy
  - Allow inferred KM policy
  - Policy-specific behavior validation
- **Pass Criteria**: Both policies produce valid results

## 🧪 **Gold Pack Data**

### **PMC2978916 Paper**
- **Title**: "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
- **Paper ID**: `pmc:PMC2978916`

### **Gold BaseSpans**
4 carefully curated spans covering Methods and Results sections with exact character offsets:

```yaml
# Methods section (char_start: 0, char_end: 200)
"Patients with platinum-resistant ovarian cancer were treated with pegylated liposomal doxorubicin (PLD) 50 mg/m2 on day 1 (and repeated every 4 weeks) in combination with escalating doses of atrasentan once daily. The starting dose was 2.5 mg and escalated in cohorts of three patients from 5 to 10 mg."

# Results section - patient population (char_start: 200, char_end: 400)
"Twenty-six patients (mean age = 60 years, range = 42–74 years) were treated at the three dose levels..."

# Results section - outcomes (char_start: 400, char_end: 500)
"Three objective responses were observed and another six patients had stable disease..."

# Results section - response rates (char_start: 500, char_end: 600)
"The ORR was 15.8% (95% CI: 3.4-39.6). CA125 response was 21.1% (95% CI: 8.4-40.3)."
```

### **Gold MethodCard**
Complete truth data including:
- Endpoints (primary: feasibility_and_toxicity)
- Ascertainment: RECIST
- Survival method: KM
- Design archetype: single_arm_phase2_gehan
- Interim looks: 1
- Analysis denominators: response_n=19, ttp_os_n=22

### **Gold ResultsFactsheet**
Exact metric values with units and denominators:
- median_ttp: 14 weeks (n=22)
- median_os: 13.1 months (n=22)
- orr_recist: 15.8% (n=19)
- ca125_response: 21.1% (n=19)

## ⚙️ **Configuration**

### **Span Budget**
```yaml
span_budget:
  methods: 12
  results: 12
  tables: 5
  topup_per_field: 3
```

### **Retrieval Configuration**
```yaml
retrieval:
  mode: "bm25_dense_union"
  seeds: [42, 123, 456]  # Fixed seeds for reproducibility
```

### **Processing Configuration**
```yaml
processing:
  min_sentence_length: 10
  max_sentence_length: 500
  dehyphenate: true
  normalize_whitespace: true
  extract_tables: true
  preserve_table_structure: true
  extract_numeric_cells: true
```

## 🚀 **Quick Start**

### **1. Run All Tests**
```bash
python test_ingest_basespan.py
```

### **2. Run Individual Tests**
```bash
# Using pytest
python -m pytest test_ingest_basespan.py::TestIngestBaseSpan::test_1_sentence_segmentation -v

# Using the test runner
python test_ingest_basespan.py
```

### **3. Run with Configuration**
```bash
# The test suite automatically loads test_ingest_basespan_config.yaml
python test_ingest_basespan.py
```

## 📊 **Expected Results**

### **Success Criteria**
- **100% gold span coverage**: All 4 gold spans present with correct sections
- **Character offset accuracy**: Within 10 characters of gold standard
- **Section consistency**: Methods/Results sections correctly identified
- **Span ID format**: Follows `doc_id#p{page}:{start}-{end}` pattern
- **Budget adherence**: No section exceeds configured limits
- **Reproducibility**: Identical output across all seeds

### **Performance Targets**
- **Execution time**: < 5 minutes
- **Memory usage**: < 512 MB
- **CPU usage**: < 80%
- **Span generation**: 4-8 spans (depending on segmentation)

## 🔍 **Troubleshooting**

### **Common Issues**

#### **1. Missing Gold Spans**
- **Symptom**: Test fails with "Missing gold spans" error
- **Cause**: Text processing not capturing expected content
- **Solution**: Check sentence segmentation configuration and text preprocessing

#### **2. Character Offset Mismatches**
- **Symptom**: Test fails with "Char start/end offset mismatch" error
- **Cause**: Text normalization changing character positions
- **Solution**: Verify text preprocessing doesn't modify character positions

#### **3. Budget Exceeded**
- **Symptom**: Test fails with "Span budget exceeded" error
- **Cause**: Configuration not properly limiting span generation
- **Solution**: Check span_budget configuration and enforcement logic

#### **4. Reproducibility Failures**
- **Symptom**: Test fails with "Span IDs vary across seeds" error
- **Cause**: Non-deterministic processing in span generation
- **Solution**: Ensure all random operations use fixed seeds

### **Debug Mode**
Enable detailed logging by modifying the configuration:
```yaml
logging:
  level: "DEBUG"
  performance:
    log_execution_time: true
    log_memory_usage: true
    log_span_counts: true
```

## 📈 **Integration with Main Test Suite**

This test suite is designed to integrate with the main comprehensive test suite:

### **Dependencies**
- `BaseSpanIngestWorker`: Core span generation
- `FuzzyAligner`: Text alignment functionality
- `BaseSpan`, `DerivedSpan`: Data models

### **Integration Points**
- **Input**: Raw text from PMC2978916
- **Output**: Validated spans for downstream processing
- **Validation**: Gold standard comparison
- **Reporting**: Detailed test results and performance metrics

## 🎯 **Next Steps**

After passing this test suite:

1. **Integration Testing**: Verify spans work with downstream components
2. **Performance Testing**: Measure span generation speed and memory usage
3. **Edge Case Testing**: Test with malformed text, very long documents, etc.
4. **Scale Testing**: Test with larger documents and higher span budgets

## 📚 **References**

- **PMC2978916**: The canonical test paper
- **Study Card Overhaul**: Overall system architecture
- **BaseSpan System**: Technical implementation details
- **Validation Rules**: Quality and consistency requirements

---

**Note**: This test suite is the foundation for all downstream processing. If these tests fail, the entire system cannot be trusted to produce accurate results.
