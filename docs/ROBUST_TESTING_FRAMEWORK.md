# Robust Literature Pipeline Testing Framework

This document describes the comprehensive testing framework implemented to address the issues flagged in the code review. The framework ensures the literature pipeline is robust, production-ready, and catches the types of issues that were previously missed.

## Overview

The robust testing framework implements all 10 testing requirements specified in the code review instructions:

1. **Scope & isolation** - Ephemeral DB schema, frozen time, deterministic seeds
2. **Configuration consistency guardrails** - Unified config, constructor call tracking
3. **Stage A/B/C correctness & scoping** - Comprehensive stage validation
4. **PubMed query builder sanity** - Query structure and pattern validation
5. **Priority queue uniqueness & idempotency** - Duplicate prevention and rerun safety
6. **Budget accounting accuracy** - Cost tracking and budget enforcement
7. **LLM periodic eval + early stopping** - Controlled evaluation scenarios
8. **Trial data integrity** - Data validation and format checking
9. **Result/statistics consistency** - Pipeline vs database consistency
10. **Log hygiene** - Reduced noise, surfaced signals

## Test Files

### 1. `tests/test_literature_pipeline_robust.py`
**Comprehensive end-to-end test suite** that implements all 10 testing requirements.

**Key Features:**
- Ephemeral database schema with `TRUNCATE ... CASCADE` for all literature tables
- Component constructor spying to detect multiple instantiations
- Configuration consistency verification across all components
- Stage-by-stage correctness validation with cross-trial contamination checks
- Budget accounting accuracy verification
- Result consistency validation between pipeline and database
- Idempotency testing (run pipeline twice, verify no duplicates)

**Usage:**
```bash
python tests/test_literature_pipeline_robust.py
```

### 2. `tests/test_pubmed_query_builder.py`
**Focused PubMed query builder testing** to catch malformed query issues.

**Key Features:**
- Regex pattern validation: `^\("NCT\d{8}"\[si\]\)(?:\s+OR\s+\(.+\))?$`
- Quote balance verification (no doubled quotes)
- NCT term format validation (`[si]` not `[tiab]`)
- Drug synonym structure validation
- Edge case testing (empty NCT, invalid format, long names)

**Usage:**
```bash
python tests/test_pubmed_query_builder.py
```

### 3. `tests/test_llm_evaluation_controlled.py`
**Controlled LLM evaluation testing** to ensure the LLM path is actually exercised.

**Key Features:**
- **High-posterior stop**: Two high-utility abstracts → P(short) ≥ θ_high → `promoted`
- **Low-posterior park**: Two low-utility abstracts → P(short) ≤ θ_low → `parked`
- **Plateau stop**: Several abstracts with |ΔP| < ε → `stopped`
- LLM path exercise verification with `eval_every_docs=2`
- Budget breach scenario testing
- Multi-trial scoping validation

**Usage:**
```bash
python tests/test_llm_evaluation_controlled.py
```

### 4. `scripts/run_robust_tests.py`
**Test runner script** that executes all robust tests in sequence.

**Usage:**
```bash
python scripts/run_robust_tests.py
```

## Configuration Fixes

### Budget Monitor Configuration Key Mapping
Fixed the configuration key mismatch between the orchestrator and budget monitor:

**Before (causing config drift):**
```python
# Orchestrator used:
'daily_limit': 50.0
'trial_limit': 5.0

# Budget monitor expected:
'daily_cost_limit': 100.0  # Different key, different value
'trial_cost_limit': 10.0   # Different key, different value
```

**After (consistent config):**
```python
# Orchestrator config:
'daily_limit': 50.0
'trial_limit': 5.0

# Budget monitor gets mapped:
'daily_cost_limit': 50.0   # Mapped from daily_limit
'trial_cost_limit': 5.0    # Mapped from trial_limit
```

## Test Scenarios

### Minimal Test Matrix (as specified in instructions)

1. **Happy path, 2 high-U1 abstracts** → LLM runs once → `promoted`, **no** OA pull
2. **Low utility path, 2 low-U1** → LLM runs once → `parked`, **no** OA pull, TTL set
3. **LLM follow-up path** → LLM requests OA for 1 doc → **exactly 1** full-text fetch + cost
4. **Idempotency** → Run twice → no duplicate candidates, costs unchanged
5. **Budget breach** → Configure `trial_limit` = $0.001 → assert hard stop + error state
6. **Multi-trial scoping** → Seed two trials → ensure Stage B for trial A never touches trial B's U0 rows

## Running the Tests

### Individual Test Execution
```bash
# Run comprehensive robust test suite
python tests/test_literature_pipeline_robust.py

# Run PubMed query builder tests
python tests/test_pubmed_query_builder.py

# Run LLM evaluation controlled tests
python tests/test_llm_evaluation_controlled.py
```

### Complete Test Suite
```bash
# Run all robust tests in sequence
python scripts/run_robust_tests.py
```

### Demo with Verbose Output
```bash
# Run demo with detailed verification (verbose mode)
python scripts/demo_literature_pipeline_e2e.py --verbose

# Run demo with minimal output (default)
python scripts/demo_literature_pipeline_e2e.py
```

## What the Tests Catch

### 1. Configuration Drift
- **Before**: BudgetMonitor logged `$100/$2500` while unified config said `$50/$1000`
- **After**: Test fails if any component reports different config values
- **Verification**: Constructor call counting, config snapshot comparison

### 2. Malformed PubMed Queries
- **Before**: `""NCT05111574"[si]"[tiab]` (doubled quotes, wrong tags)
- **After**: Test fails if query doesn't match regex pattern
- **Verification**: Regex validation, quote balance checking

### 3. LLM Path Not Exercised
- **Before**: Stage B evaluated 0 docs even with `eval_every_docs=2`
- **After**: Test fails if LLM evaluation count doesn't match expected pattern
- **Verification**: Controlled test scenarios, evaluation count validation

### 4. Stats vs Budget Mismatch
- **Before**: "Total Cost: $0.0000" vs budget summary showing `$0.0020`
- **After**: Test fails if pipeline cost ≠ sum of cost records
- **Verification**: Execution-scoped cost equality checking

### 5. Legacy Data Pollution
- **Before**: `document_utilities: 1404` while run persisted 1
- **After**: Test fails if old rows exist after cleanup
- **Verification**: Ephemeral schema, `TRUNCATE ... CASCADE`

### 6. Trial Title Issues
- **Before**: "No title..." placeholder text
- **After**: Test fails if trial has null or placeholder title
- **Verification**: Trial data integrity assertions

## Test Environment Requirements

### Database Setup
- Clean database with literature pipeline tables
- No legacy data that could mask test failures
- Proper trial data with non-null titles and valid phases

### Dependencies
- `freezegun` for time freezing (optional, for deterministic testing)
- `pytest` for test framework
- All Phase 1-6 components properly installed

### Environment Variables
- Database connection details
- API keys for external services (mocked in tests)

## Expected Test Output

### Successful Test Run
```
🚀 Starting Robust Literature Pipeline Test Suite
🔧 Setting up isolated test environment...
✅ Test environment setup complete
🧪 Creating test trial: NCT05111574
🔍 Setting up component constructor spies...
🔧 Initializing Literature Orchestrator...
🔍 Verifying configuration consistency...
✅ Configuration consistency verified
🔍 Verifying trial data integrity...
✅ Trial data integrity verified: NCT05111574, 'Test Clinical Trial for Robust Testing', PHASE2
🚀 Running literature pipeline...
🔍 Verifying Stage A correctness...
✅ Stage A verified: 15 U0 documents for trial 1
🔍 Verifying Stage B correctness...
✅ Stage B verified: 8 abstracts evaluated, 3 selected
🔍 Verifying Stage C correctness...
✅ Stage C verified: 0 full-text documents
🔍 Verifying LLM evaluation behavior...
✅ LLM evaluation verified: status=promoted, posterior=0.85, count=1
🔍 Verifying budget accounting...
✅ Budget accounting verified
🔍 Verifying result consistency...
✅ Result consistency verified
🔄 Testing idempotency...
✅ Idempotency test passed
🎯 Final verification...
🎉 ROBUST TEST SUITE COMPLETED SUCCESSFULLY!
✅ All 6 components constructed exactly once
✅ Configuration consistency maintained
✅ All pipeline stages verified
✅ Budget accounting accurate
✅ LLM evaluation behavior verified
✅ Trial data integrity maintained
✅ Results consistent across pipeline and database
```

### Failed Test Run
```
❌ Robust test suite failed: Component BudgetMonitor constructed 2 times (expected 1)
```

## Integration with CI/CD

### Automated Testing
The robust test suite can be integrated into CI/CD pipelines to catch issues before deployment:

```yaml
# Example GitHub Actions workflow
- name: Run Robust Tests
  run: |
    python scripts/run_robust_tests.py
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

### Pre-commit Hooks
Consider adding pre-commit hooks to run critical tests before code commits:

```bash
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: robust-tests
      name: Robust Literature Pipeline Tests
      entry: python scripts/run_robust_tests.py
      language: system
      pass_filenames: false
```

## Troubleshooting

### Common Test Failures

1. **Configuration Drift**
   - Check component constructor calls
   - Verify unified config propagation
   - Ensure no hardcoded config values

2. **Database State Issues**
   - Verify clean test environment setup
   - Check for legacy data contamination
   - Ensure proper table cleanup

3. **LLM Path Not Exercised**
   - Verify `eval_every_docs` configuration
   - Check document evaluation counts
   - Ensure controlled test scenarios are working

4. **Budget Accounting Mismatches**
   - Verify cost record creation
   - Check execution ID scoping
   - Ensure budget monitor configuration consistency

### Debug Mode
Enable debug logging to see detailed test execution:

```bash
export LOG_LEVEL=DEBUG
python tests/test_literature_pipeline_robust.py
```

## Future Enhancements

### Additional Test Scenarios
- **Performance testing** with large document sets
- **Concurrent trial processing** validation
- **Error recovery** and resilience testing
- **Memory usage** and resource leak detection

### Test Data Generation
- **Synthetic trial data** for consistent testing
- **Varied document types** and content
- **Edge case scenarios** and boundary conditions

### Monitoring Integration
- **Real-time test metrics** collection
- **Performance regression** detection
- **Test coverage** reporting and analysis

## Conclusion

The robust testing framework provides comprehensive validation of the literature pipeline, ensuring that:

- All components are properly integrated and configured
- Pipeline stages work correctly with proper scoping
- Budget monitoring is accurate and consistent
- LLM evaluation paths are actually exercised
- Data integrity is maintained across all operations
- The system is idempotent and safe to rerun

By implementing these tests, the literature pipeline can be confidently deployed to production with the assurance that it will work correctly and catch issues early in the development cycle.
