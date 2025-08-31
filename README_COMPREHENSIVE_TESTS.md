# Comprehensive Test Suite for Study Card System

This directory contains a comprehensive test suite for the Study Card system, designed to test all components from BaseSpan ingest through DecisionRecord creation using the PMC2978916 paper as test data.

## 🎯 Overview

The test suite covers **18 test categories** that comprehensively validate the entire dual-path pipeline system:

1. **BaseSpan Ingest** - Sentence segmentation and span creation
2. **Span Indexing** - Search and retrieval functionality
3. **Fuzzy Alignment** - Quote matching and alignment
4. **Span Triage** - Intelligent span selection with budget constraints
5. **Denominator Resolution** - Population size extraction and validation
6. **Method Auditor** - Study design and methodology extraction
7. **Results Distiller** - Clinical outcomes and metrics extraction
8. **Claimizer** - Fact extraction and classification
9. **Counter-Evidence Miner** - Contradictory evidence identification
10. **Gate Lifecycle** - Complete gate propose → validate → assess workflow
11. **Late Fusion Orchestrator** - Dual-path integration and fusion
12. **Global Validators** - Schema and business rule validation
13. **DecisionRecord Creation** - Final artifact generation
14. **End-to-End Pipeline** - Complete workflow testing
15. **Performance & Resources** - Memory and execution time monitoring
16. **Error Handling** - Graceful failure and recovery testing
17. **Idempotency** - Consistent results across multiple runs
18. **Configuration Ablation** - Different pipeline configurations

## 📋 Test Data

The test suite uses the **PMC2978916 paper** as the primary test case:
- **Title**: "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
- **Design**: Single-arm Phase 2 Gehan design
- **Population**: 26 patients (19 evaluable for response, 22 for TTP/OS)
- **Key Metrics**: Median TTP (14 weeks), Median OS (13.1 months), ORR (15.8%)

### Gold Standard Data

The test suite includes hand-curated gold standard data for:
- `MethodCard` with complete study design information
- `ResultsFactsheet` with clinical outcomes and metrics
- `Claim[]` with extracted facts and their provenance
- Span IDs and character offsets for all extracted data

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Install test dependencies
pip install -r requirements_test.txt

# Or install core dependencies only
pip install pytest psutil pyyaml
```

### 2. Run Basic Tests

```bash
# Run the comprehensive test suite
python test_comprehensive_system.py

# Or use the test runner
python run_comprehensive_tests.py
```

### 3. Run with pytest

```bash
# Run with pytest (recommended for development)
python -m pytest test_comprehensive_system.py -v

# Run with coverage
python -m pytest test_comprehensive_system.py --cov=src/ncfd --cov-report=html
```

## 📁 File Structure

```
├── test_comprehensive_system.py    # Main test suite (18 test categories)
├── run_comprehensive_tests.py      # Test runner with reporting
├── test_config.yaml               # Test configuration
├── requirements_test.txt           # Test dependencies
├── README_COMPREHENSIVE_TESTS.md  # This file
└── test_results/                  # Generated test results
    ├── test_report.html           # HTML test report
    ├── test_results.json          # JSON test results
    └── coverage/                  # Code coverage reports
```

## ⚙️ Configuration

The test suite is configured via `test_config.yaml`:

```yaml
# Test Configuration
test_config:
  max_execution_time: 10.0      # seconds
  max_memory_usage: 1024        # MB
  span_budgets:
    methods: 12
    results: 12
    tables: 5
  
# Validation Rules
validation:
  require_span_ids: true
  enforce_unit_conversion: true
  enforce_section_rules: true
```

## 🧪 Test Categories

### Core Functionality Tests

#### 1. BaseSpan Ingest (`test_1_basespan_ingest`)
- Tests sentence segmentation
- Validates span ID generation
- Checks de-hyphenation and normalization

#### 2. Span Indexing (`test_2_span_indexing`)
- Tests index building and search
- Validates retrieval accuracy
- Checks section-based filtering

#### 3. Fuzzy Alignment (`test_3_fuzzy_alignment`)
- Tests quote alignment with similarity thresholds
- Validates span mapping accuracy
- Checks rejection of low-similarity matches

#### 4. Span Triage (`test_4_span_triage`)
- Tests intelligent span selection
- Validates budget adherence
- Checks required field coverage

#### 5. Denominator Resolution (`test_5_denominator_resolution`)
- Tests population size extraction
- Validates metric-family association
- Checks ambiguity resolution

### LLM Worker Tests

#### 6. Method Auditor (`test_6_method_auditor`)
- Tests study design extraction
- Validates methodology classification
- Checks required field completion

#### 7. Results Distiller (`test_7_results_distiller`)
- Tests clinical outcomes extraction
- Validates metric normalization
- Checks unit conversion

#### 8. Claimizer (`test_8_claimizer`)
- Tests fact extraction and classification
- Validates claim typing
- Checks provenance tracking

#### 9. Counter-Evidence Miner (`test_9_counter_evidence_miner`)
- Tests contradictory evidence identification
- Validates quality scoring
- Checks applicability assessment

### Deterministic Worker Tests

#### 10. Gate Lifecycle (`test_10_gate_lifecycle`)
- Tests complete gate workflow
- Validates gate proposal, validation, and assessment
- Checks computation accuracy

### Integration Tests

#### 11. Late Fusion Orchestrator (`test_11_late_fusion_orchestrator`)
- Tests dual-path integration
- Validates configuration ablation
- Checks fusion consistency

#### 12. Global Validators (`test_12_global_validators`)
- Tests schema validation
- Validates business rules
- Checks constraint enforcement

#### 13. DecisionRecord Creation (`test_13_decision_record_creation`)
- Tests final artifact generation
- Validates memo composition
- Checks citation completeness

### End-to-End Tests

#### 14. End-to-End Pipeline (`test_14_end_to_end_pipeline`)
- Tests complete workflow
- Validates artifact generation
- Checks execution statistics

### Quality Assurance Tests

#### 15. Performance & Resources (`test_15_performance_and_resources`)
- Tests execution time limits
- Validates memory usage
- Checks resource constraints

#### 16. Error Handling (`test_16_error_handling`)
- Tests graceful failure
- Validates error messages
- Checks recovery mechanisms

#### 17. Idempotency (`test_17_idempotency`)
- Tests consistent results
- Validates deterministic behavior
- Checks reproducibility

#### 18. Configuration Ablation (`test_18_configuration_ablation`)
- Tests different pipeline modes
- Validates configuration options
- Checks feature isolation

## 📊 Test Results

The test suite generates comprehensive reports:

### HTML Report
- Interactive test results
- Performance metrics
- Error details and stack traces
- Coverage information

### JSON Report
- Machine-readable results
- Structured test data
- Performance measurements
- Configuration details

### Coverage Report
- Code coverage analysis
- Missing line identification
- Branch coverage statistics

## 🔧 Customization

### Adding New Tests

1. **Create test method** in `TestComprehensiveSystem` class:
```python
def test_19_new_feature(self):
    """Test new feature functionality."""
    # Test implementation
    pass
```

2. **Add to test runner** in `run_comprehensive_tests.py`:
```python
# Add to test execution flow
new_feature_results = self.run_new_feature_tests()
self.test_results["tests"]["new_feature_tests"] = new_feature_results
```

### Modifying Test Data

1. **Update `TestData` class** in `test_comprehensive_system.py`
2. **Modify gold standard data** for new papers
3. **Adjust test spans** for different document types

### Configuration Changes

1. **Modify `test_config.yaml`** for different test parameters
2. **Add environment variables** for dynamic configuration
3. **Update validation rules** for new requirements

## 🚨 Troubleshooting

### Common Issues

#### Import Errors
```bash
# Ensure src directory is in Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

#### Missing Dependencies
```bash
# Install missing packages
pip install -r requirements_test.txt

# Or install specific packages
pip install psutil pyyaml pytest
```

#### Test Failures
```bash
# Run with verbose output
python -m pytest test_comprehensive_system.py -v -s

# Run specific test
python -m pytest test_comprehensive_system.py::TestComprehensiveSystem::test_1_basespan_ingest -v
```

#### Performance Issues
```bash
# Check system resources
top
free -h

# Run with reduced scope
python run_comprehensive_tests.py --quick
```

### Debug Mode

```bash
# Run with debug output
python -m pytest test_comprehensive_system.py -v -s --pdb

# Run specific test with debug
python -m pytest test_comprehensive_system.py::TestComprehensiveSystem::test_1_basespan_ingest -v -s --pdb
```

## 📈 Performance Benchmarks

The test suite includes performance monitoring:

- **Execution Time**: Per-test and total timing
- **Memory Usage**: RSS and VMS memory tracking
- **CPU Usage**: Process CPU utilization
- **Resource Limits**: Threshold monitoring and alerts

### Performance Thresholds

```yaml
test_config:
  max_execution_time: 10.0      # seconds per test
  max_memory_usage: 1024        # MB total
  warning_threshold: 0.8         # 80% of limits
  error_threshold: 0.95          # 95% of limits
```

## 🔄 Continuous Integration

The test suite is designed for CI/CD pipelines:

### GitHub Actions Example
```yaml
- name: Run Comprehensive Tests
  run: |
    python run_comprehensive_tests.py --config test_config.yaml
    python -m pytest test_comprehensive_system.py --cov=src/ncfd --cov-report=xml
```

### Jenkins Example
```groovy
stage('Test') {
    steps {
        sh 'python run_comprehensive_tests.py'
        sh 'python -m pytest test_comprehensive_system.py --cov=src/ncfd --cov-report=html'
    }
    post {
        always {
            publishHTML([
                allowMissing: false,
                alwaysLinkToLastBuild: true,
                keepAll: true,
                reportDir: 'test_results/coverage',
                reportFiles: 'index.html',
                reportName: 'Coverage Report'
            ])
        }
    }
}
```

## 📚 Additional Resources

- **Study Card Overhaul Document**: `docs/Study_card_overhall.md`
- **Implementation Summary**: `IMPLEMENTATION_SUMMARY.md`
- **BaseSpan System**: `docs/BASESPAN_SYSTEM.md`
- **Code Conventions**: `docs/conventions.md`

## 🤝 Contributing

When adding new tests:

1. **Follow naming convention**: `test_XX_descriptive_name`
2. **Include docstrings**: Describe what the test validates
3. **Add assertions**: Test specific functionality
4. **Update documentation**: Modify this README if needed
5. **Run full suite**: Ensure all tests pass

## 📞 Support

For issues with the test suite:

1. **Check troubleshooting section** above
2. **Review test logs** in `test_results/` directory
3. **Run with verbose output** for detailed error information
4. **Check system requirements** and dependencies

---

**Last Updated**: December 2024  
**Version**: 1.0.0  
**Test Coverage**: 18 test categories, 100+ individual assertions
