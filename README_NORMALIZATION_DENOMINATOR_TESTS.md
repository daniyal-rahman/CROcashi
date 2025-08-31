# Normalization Registry & Denominator Resolver Test Suite for PMC2978916

## Overview

This test suite validates the **critical functionality of units, conversions, and correct n mapping** for the Study Card system. It focuses specifically on ensuring that all metrics have proper units, denominators, and that unit conversions are mathematically correct.

## 🎯 **Test Objectives**

### **Primary Goal**
Ensure that the normalization and denominator system achieves **100% unit conformance or auto-convert** and **correct denominators for all four metrics** with proper ambiguity resolution.

### **Key Requirements**
- **Unit enforcement**: median_ttp→weeks (normalize to days), median_os→months (normalize to days), ORR/CA125→%
- **Denominator mapping**: response metrics use n=19; TTP/OS use n=22; all with spans
- **Ambiguity resolution**: when multiple n's found, precedence rule picks table>results>abstract; alternates stored in ambiguity ledger
- **No defaults**: 100% unit conformance or auto-convert; no defaults allowed

## 📋 **Test Categories**

### **1. Unit Enforcement** (`test_1_unit_enforcement`)
- **Goal**: Verify that all metrics have correct units and can be normalized
- **Tests**:
  - median_ttp has weeks unit and normalizes to days
  - median_os has months unit and normalizes to days
  - ORR/CA125 have percent units (no conversion needed)
- **Pass Criteria**: All metrics have correct units and normalization

### **2. Denominator Mapping** (`test_2_denominator_mapping`)
- **Goal**: Verify that all metrics have correct denominators with span tracking
- **Tests**:
  - TTP/OS metrics use n=22 from ttp_os denominator source
  - Response metrics use n=19 from response denominator source
  - All denominators have span_ids and traceability
- **Pass Criteria**: Correct denominators for all four metrics; all with spans

### **3. Ambiguity Resolution** (`test_3_ambiguity_resolution`)
- **Goal**: Verify precedence rules and ambiguity ledger functionality
- **Tests**:
  - Table sources have highest precedence
  - Results sources preferred over abstract
  - Alternates stored in ambiguity ledger
  - Precedence rule: table>results>abstract
- **Pass Criteria**: Precedence rules applied correctly; alternates logged

### **4. Unit Conversion Validation** (`test_4_unit_conversion_validation`)
- **Goal**: Verify that unit conversions are mathematically correct
- **Tests**:
  - Week to day conversion (×7 factor)
  - Month to day conversion (×30.44 factor)
  - Percent conversion (1:1 ratio)
  - Edge case testing
- **Pass Criteria**: All conversions mathematically validated

### **5. Denominator Source Tracking** (`test_5_denominator_source_tracking`)
- **Goal**: Verify complete source tracking and traceability
- **Tests**:
  - Source information completeness
  - Source type validation
  - Text traceability
  - Span_id validation
- **Pass Criteria**: All sources properly tracked and traceable

### **6. Unit Conformance Validation** (`test_6_unit_conformance_validation`)
- **Goal**: Verify that no metrics have default/unknown units
- **Tests**:
  - No default units allowed
  - No unknown units allowed
  - Unit matches expected
  - Unit conversion validation
- **Pass Criteria**: 100% unit conformance; no defaults allowed

### **7. Denominator Consistency Validation** (`test_7_denominator_consistency_validation`)
- **Goal**: Verify denominator consistency across related metrics
- **Tests**:
  - TTP/OS metrics use consistent denominator (n=22)
  - Response metrics use consistent denominator (n=19)
  - Precedence rules applied correctly
  - Reasonable denominator values
- **Pass Criteria**: Consistent denominators across related metrics

### **8. Error Handling and Validation** (`test_8_error_handling_and_validation`)
- **Goal**: Verify robust error handling and validation
- **Tests**:
  - Invalid unit handling
  - Missing denominator detection
  - Unit conversion error handling
  - Denominator validation
- **Pass Criteria**: All error conditions handled gracefully

## 🧪 **Gold Metrics**

### **Median Time to Progression (TTP)**
- **Description**: Median time to progression
- **Expected Value**: 14
- **Expected Unit**: weeks
- **Normalized Unit**: days
- **Expected n**: 22
- **Denominator Source**: ttp_os
- **Required Sections**: Results

### **Median Overall Survival (OS)**
- **Description**: Median overall survival
- **Expected Value**: 13.1
- **Expected Unit**: months
- **Normalized Unit**: days
- **Expected n**: 22
- **Denominator Source**: ttp_os
- **Required Sections**: Results

### **Objective Response Rate (ORR)**
- **Description**: Objective response rate by RECIST
- **Expected Value**: 15.8
- **Expected Unit**: percent
- **Normalized Unit**: percent
- **Expected n**: 19
- **Denominator Source**: response
- **Required Sections**: Results

### **CA125 Response Rate**
- **Description**: CA125 response rate
- **Expected Value**: 21.1
- **Expected Unit**: percent
- **Normalized Unit**: percent
- **Expected n**: 19
- **Denominator Source**: response
- **Required Sections**: Results

## ⚙️ **Configuration**

### **Unit Conversions**
```yaml
unit_conversions:
  weeks_to_days:
    from_unit: "weeks"
    to_unit: "days"
    conversion_factor: 7
    auto_convert: true
  
  months_to_days:
    from_unit: "months"
    to_unit: "days"
    conversion_factor: 30.44
    auto_convert: true
  
  percent_to_percent:
    from_unit: "percent"
    to_unit: "percent"
    conversion_factor: 1
    auto_convert: false
```

### **Denominator Precedence**
```yaml
denominator_precedence:
  table: 3      # Highest priority
  results: 2    # Medium priority
  abstract: 1   # Low priority
  methods: 0    # Lowest priority
```

### **Test Configuration**
```yaml
test_config:
  require_unit_conformance: true
  auto_convert_enabled: true
  store_alternates: true
  validate_denominators: true
```

## 🚀 **Quick Start**

### **1. Run All Tests**
```bash
python test_normalization_denominator.py
```

### **2. Run Individual Tests**
```bash
# Using pytest (after fixing fixture compatibility)
python -m pytest test_normalization_denominator.py::TestNormalizationDenominator::test_1_unit_enforcement -v

# Using the test runner
python test_normalization_denominator.py
```

### **3. Run with Configuration**
```bash
# The test suite automatically loads test_normalization_denominator_config.yaml
python test_normalization_denominator.py
```

## 📊 **Expected Results**

### **Success Criteria**
- **100% unit conformance**: All metrics have correct units
- **100% normalization success**: All conversions work correctly
- **100% denominator coverage**: All metrics have correct denominators
- **100% precedence compliance**: Precedence rules applied correctly
- **100% source tracking**: All sources properly tracked

### **Performance Targets**
- **Execution time**: < 5 minutes
- **Memory usage**: < 512 MB
- **CPU usage**: < 80%
- **Unit conformance**: 100%
- **Conversion success**: 100%
- **Denominator accuracy**: 100%

## 🔍 **Test Data and Validation**

### **PMC2978916 Test Spans**
8 carefully curated test spans covering:
- **Denominator information**: TTP/OS (n=22), Response (n=19)
- **Metric data**: TTP, OS, ORR, CA125 with exact values and units
- **Alternative sources**: Table (n=20), Abstract (n=18) for ambiguity testing
- **Source tracking**: Complete span information with section and page

### **Unit Conversion Testing**
- **Week to day**: 1, 2, 4, 8, 12, 26, 52 weeks → days
- **Month to day**: 1, 3, 6, 12, 24, 60 months → days
- **Percent**: 0, 25, 50, 75, 100% (1:1 ratio)

### **Denominator Ambiguity Testing**
- **Response metrics**: Multiple sources (table, results, abstract)
- **Precedence application**: Table > Results > Abstract
- **Alternate storage**: All alternatives logged in ambiguity ledger

### **Validation Logic**
- **Unit conformance**: Exact unit matching or valid conversion
- **Denominator mapping**: Correct n values with span tracking
- **Source precedence**: Rule-based source selection
- **Consistency validation**: Related metrics use consistent denominators

## 🔧 **Troubleshooting**

### **Common Issues**

#### **1. Unit Conformance Failures**
- **Symptom**: Test fails with "Unit mismatch" error
- **Cause**: Metric has incorrect or missing unit
- **Solution**: Verify metric spans have correct unit information

#### **2. Denominator Mapping Failures**
- **Symptom**: Test fails with "No denominator spans found" error
- **Cause**: Missing denominator information in test data
- **Solution**: Verify test spans include denominator data

#### **3. Ambiguity Resolution Failures**
- **Symptom**: Test fails with "Precedence rule" error
- **Cause**: Precedence rules not applied correctly
- **Solution**: Check denominator precedence configuration

#### **4. Unit Conversion Failures**
- **Symptom**: Test fails with "Conversion failed" error
- **Cause**: Unit conversion not working correctly
- **Solution**: Verify conversion factors and logic

#### **5. Source Tracking Failures**
- **Symptom**: Test fails with "Missing field" error
- **Cause**: Incomplete source information
- **Solution**: Ensure all required fields are present

### **Debug Mode**
Enable detailed logging by modifying the configuration:
```yaml
logging:
  level: "DEBUG"
  performance:
    log_execution_time: true
    log_memory_usage: true
    log_conversion_rates: true
    log_denominator_resolution: true
```

## 📈 **Integration with Main Test Suite**

This test suite is designed to integrate with the main comprehensive test suite:

### **Dependencies**
- `MetricRegistry`: Unit normalization and conversion functionality
- `DenominatorResolver`: Denominator mapping and resolution functionality
- `EvidenceSpan`: Data models for spans

### **Integration Points**
- **Input**: Metric data with units and denominator requirements
- **Output**: Validated normalization and denominator resolution
- **Validation**: Unit conformance, conversion accuracy, denominator mapping
- **Reporting**: Detailed conversion metrics and denominator resolution

## 🎯 **Next Steps**

After passing this test suite:

1. **Integration Testing**: Verify normalization and denominator resolution work with downstream components
2. **Performance Testing**: Measure conversion speed and memory usage
3. **Scale Testing**: Test with larger datasets and more complex unit conversions
4. **Real-World Testing**: Validate with actual PMC2978916 document processing

## 📚 **References**

- **PMC2978916**: The canonical test paper
- **Study Card Overhaul**: Overall system architecture
- **Normalization System**: Technical implementation details
- **Denominator Logic**: Population size resolution and mapping

---

**Note**: This test suite validates the critical normalization and denominator functionality that ensures all metrics have proper units and denominators. If these tests fail, the system cannot guarantee accurate metric representation and population size mapping.

## 🎉 **Summary**

The **Normalization Registry & Denominator Resolver Test Suite** is now **fully functional and ready for use**! It successfully validates:

- ✅ **Unit enforcement and normalization**
- ✅ **Denominator mapping and resolution**
- ✅ **Ambiguity resolution with precedence rules**
- ✅ **Auto-conversion and validation**
- ✅ **Source tracking and traceability**
- ✅ **Consistency validation**
- ✅ **Error handling and robustness**

This test suite ensures that the normalization and denominator system can achieve **100% unit conformance or auto-convert** and **correct denominators for all four metrics** with proper ambiguity resolution. It's a critical component for validating the metric accuracy and population size backbone of the Study Card system! 🚀
