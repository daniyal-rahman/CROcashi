# Retrieval & Span Triage Test Suite for PMC2978916

## Overview

This test suite validates the **critical functionality of must-hit recall within strict span budgets** for the Study Card system. It focuses specifically on ensuring that all required content is captured while respecting budget constraints and maintaining high recall rates.

## 🎯 **Test Objectives**

### **Primary Goal**
Ensure that the retrieval and triage system achieves **≥95% recall on must-hits within budget** and **100% after single top-up**, while strictly enforcing budget constraints.

### **Key Requirements**
- **Must-hit coverage**: Triage returns at least one span for each required content type
- **Section boosting**: Methods queries don't pull Discussion; Results/Table preferred for numerics over Abstract
- **Top-up logic**: If a must-fill is missing, exactly one targeted top-up (+3 spans) runs; no loops
- **Budget enforcement**: All budgets respected; reserved slots filled when content exists

## 📋 **Test Categories**

### **1. Must-Hit Coverage** (`test_1_must_hit_coverage`)
- **Goal**: Verify that all required content types are covered
- **Tests**:
  - Statistics/Kaplan-Meier content coverage
  - RECIST criteria and assessment cadence coverage
  - Gehan two-stage design information coverage
  - Response breakdown (paragraph or table) coverage
  - Survival medians (paragraph or table) coverage
- **Pass Criteria**: 100% coverage of all must-hit content types

### **2. Section Boosting** (`test_2_section_boosting`)
- **Goal**: Verify section-aware query targeting and boosting
- **Tests**:
  - Methods queries exclude Discussion content
  - Results queries prioritize Results over Abstract
  - Numeric content prefers Results over Abstract
  - Section priority enforcement
- **Pass Criteria**: Section boosting working correctly, no cross-section contamination

### **3. Top-Up Logic** (`test_3_top_up_logic`)
- **Goal**: Verify intelligent top-up retrieval for missing content
- **Tests**:
  - Initial retrieval identifies missing content
  - Top-up adds exactly +3 spans per missing field
  - No infinite loops or multiple top-up attempts
  - Top-up significantly reduces missing content
- **Pass Criteria**: Single top-up run, +3 spans per field, no loops

### **4. Budget Enforcement** (`test_4_budget_enforcement`)
- **Goal**: Verify strict budget constraint enforcement
- **Tests**:
  - Section budget limits respected
  - Total budget limits enforced
  - Reserved slots properly utilized
  - Budget utilization rates maintained
- **Pass Criteria**: All budgets respected, no overruns, proper utilization

### **5. Recall Rate Calculation** (`test_5_recall_rate_calculation`)
- **Goal**: Verify recall rate calculation and threshold compliance
- **Tests**:
  - Individual content type recall rates
  - Overall recall rate calculation
  - 95% threshold compliance verification
  - Recall rate accuracy validation
- **Pass Criteria**: All content types meet 95% recall threshold

### **6. Content Type Prioritization** (`test_6_content_type_prioritization`)
- **Goal**: Verify that high-priority content gets retrieval preference
- **Tests**:
  - High priority content appears first in results
  - Priority-based ranking works correctly
  - Content type boosting functionality
- **Pass Criteria**: At least 60% high priority content in first half of results

### **7. Retrieval Mode Comparison** (`test_7_retrieval_mode_comparison`)
- **Goal**: Verify different retrieval modes and their performance
- **Tests**:
  - BM25-only mode performance
  - Dense-only mode performance
  - BM25 ∪ dense union mode performance
  - Mode comparison and validation
- **Pass Criteria**: Union mode provides best coverage

### **8. Error Handling and Robustness** (`test_8_error_handling_and_robustness`)
- **Goal**: Verify system robustness and error handling
- **Tests**:
  - Malformed query handling
  - Empty span set handling
  - Budget overrun prevention
  - Graceful degradation
- **Pass Criteria**: All error conditions handled gracefully

## 🧪 **Must-Hit Content Types**

### **Statistics/Kaplan-Meier Content**
- **Description**: Statistical analysis methods and survival analysis
- **Expected Terms**: Kaplan-Meier, log-rank, survival analysis, median
- **Required Sections**: Methods, Results
- **Priority**: High

### **RECIST Criteria and Assessment Cadence**
- **Description**: Response evaluation criteria and timing
- **Expected Terms**: RECIST, response, assessment, every, weeks, cycles
- **Required Sections**: Methods, Results
- **Priority**: High

### **Gehan Two-Stage Design**
- **Description**: Study design methodology information
- **Expected Terms**: Gehan, two-stage, interim, cohorts, escalating
- **Required Sections**: Methods
- **Priority**: High

### **Response Breakdown**
- **Description**: Response rate data and analysis
- **Expected Terms**: response rate, ORR, 15.8%, 21.1%, objective responses
- **Required Sections**: Results
- **Priority**: High

### **Survival Medians**
- **Description**: Survival outcome data and statistics
- **Expected Terms**: median, 14 weeks, 13.1 months, time to progression, overall survival
- **Required Sections**: Results
- **Priority**: High

## ⚙️ **Configuration**

### **Span Budget**
```yaml
span_budget:
  methods: 12
  results: 12
  tables: 5
  abstract: 3
  discussion: 2
  topup_per_field: 3
```

### **Retrieval Configuration**
```yaml
retrieval_config:
  mode: "bm25_dense_union"
  seeds: [42, 123, 456]
  section_boosting: true
  content_type_boosting: true
```

### **Triage Configuration**
```yaml
triage_config:
  must_hit_threshold: 0.95  # 95% recall requirement
  topup_attempts: 1         # Exactly one top-up run
  topup_increment: 3        # +3 spans per top-up
  max_total_spans: 50       # Overall limit
```

## 🚀 **Quick Start**

### **1. Run All Tests**
```bash
python test_retrieval_triage.py
```

### **2. Run Individual Tests**
```bash
# Using pytest (after fixing fixture compatibility)
python -m pytest test_retrieval_triage.py::TestRetrievalTriage::test_1_must_hit_coverage -v

# Using the test runner
python test_retrieval_triage.py
```

### **3. Run with Configuration**
```bash
# The test suite automatically loads test_retrieval_triage_config.yaml
python test_retrieval_triage.py
```

## 📊 **Expected Results**

### **Success Criteria**
- **100% must-hit coverage**: All 5 content types covered with required spans
- **95% recall threshold**: Individual and overall recall rates meet threshold
- **Budget compliance**: No section or total budget overruns
- **Top-up effectiveness**: Single top-up run achieves 100% coverage
- **Section boosting**: Methods exclude Discussion, Results preferred over Abstract

### **Performance Targets**
- **Execution time**: < 5 minutes
- **Memory usage**: < 512 MB
- **CPU usage**: < 80%
- **Recall rate**: ≥95% initial, 100% after top-up
- **Budget utilization**: ≥50% for sections with content

## 🔍 **Test Data and Simulation**

### **PMC2978916 Test Spans**
8 carefully curated test spans covering:
- **Methods section**: Statistics/KM, RECIST, Gehan design
- **Results section**: Response breakdown, survival medians
- **Abstract section**: General study information
- **Discussion section**: Interpretation and conclusions

### **Simulation Methods**
The test suite includes comprehensive simulation methods:
- **Section query simulation**: Target-specific section retrieval
- **Numeric query simulation**: Numeric content prioritization
- **Content type retrieval**: Type-specific span retrieval
- **Top-up simulation**: Missing content recovery
- **Mode comparison**: BM25 vs dense vs union performance

### **Validation Logic**
- **Coverage calculation**: Must-hit content type coverage
- **Recall rate calculation**: Relevant span retrieval rates
- **Budget enforcement**: Section and total limit compliance
- **Priority validation**: Content type and section prioritization

## 🔧 **Troubleshooting**

### **Common Issues**

#### **1. Must-Hit Coverage Failures**
- **Symptom**: Test fails with "Insufficient spans for {content_type}" error
- **Cause**: Missing spans for required content types
- **Solution**: Verify test data includes all required content types

#### **2. Section Boosting Failures**
- **Symptom**: Test fails with "Methods query pulled Discussion spans" error
- **Cause**: Section boosting not working correctly
- **Solution**: Check section priority configuration and query targeting

#### **3. Top-Up Logic Failures**
- **Symptom**: Test fails with "Top-up should add {expected} spans" error
- **Cause**: Top-up increment not working correctly
- **Solution**: Verify topup_increment configuration and logic

#### **4. Budget Enforcement Failures**
- **Symptom**: Test fails with "Section exceeded budget" error
- **Cause**: Budget limits not enforced
- **Solution**: Check budget configuration and enforcement logic

#### **5. Recall Rate Failures**
- **Symptom**: Test fails with "Overall recall below threshold" error
- **Cause**: Retrieval not achieving required recall rates
- **Solution**: Verify retrieval configuration and must-hit threshold

### **Debug Mode**
Enable detailed logging by modifying the configuration:
```yaml
logging:
  level: "DEBUG"
  performance:
    log_execution_time: true
    log_memory_usage: true
    log_span_counts: true
    log_recall_rates: true
    log_budget_utilization: true
```

## 📈 **Integration with Main Test Suite**

This test suite is designed to integrate with the main comprehensive test suite:

### **Dependencies**
- `SpanTriageWorker`: Core triage functionality
- `Retriever`: Retrieval and ranking functionality
- `EvidenceSpan`: Data models for spans

### **Integration Points**
- **Input**: Must-hit content requirements and span budgets
- **Output**: Validated retrieval and triage performance
- **Validation**: Coverage, recall, and budget compliance
- **Reporting**: Detailed performance metrics and error reports

## 🎯 **Next Steps**

After passing this test suite:

1. **Integration Testing**: Verify retrieval and triage work with downstream components
2. **Performance Testing**: Measure retrieval speed and memory usage
3. **Scale Testing**: Test with larger documents and higher span budgets
4. **Real-World Testing**: Validate with actual PMC2978916 document processing

## 📚 **References**

- **PMC2978916**: The canonical test paper
- **Study Card Overhaul**: Overall system architecture
- **Retrieval System**: Technical implementation details
- **Triage Logic**: Content prioritization and budget management

---

**Note**: This test suite validates the critical retrieval and triage functionality that ensures all required content is captured within budget constraints. If these tests fail, the system cannot guarantee comprehensive content coverage.
