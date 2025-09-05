# Test Scripts Directory

This directory contains test and debug scripts that were moved from the main `scripts/` directory to keep it focused on operational scripts.

## Test Scripts

### Early Stopping Tests
- **`test_top_k_guard.py`** - Test Top-K guard mechanism for early stopping
- **`test_early_stopping_keytruda.py`** - Test early stopping with Keytruda trial
- **`test_early_stopping_cassava.py`** - Test early stopping with Cassava trial

### Asset Resolution Tests
- **`test_cassava_asset_resolution.py`** - Test asset resolution for Cassava trial
- **`test_cassava_papers.py`** - Test paper processing for Cassava trial

### Debug Scripts
- **`debug_cassava_trial.py`** - Debug script for Cassava trial analysis

### Analysis Scripts
- **`analyze_cassava_misses.py`** - Analyze missed signals in Cassava trial

### PMC2978916 Test Scripts
- **`run_pmc2978916_debug.py`** - Debug script for PMC2978916 paper
- **`run_pmc2978916_test.py`** - Test script for PMC2978916 paper
- **`run_pmc2978916_quick.py`** - Quick test for PMC2978916 paper

### Backtest Scripts
- **`backtest_pubmed_cassava.py`** - PubMed literature review backtest for Cassava trial
- **`backtest_ctgov_sec_wiring_with_llm.py`** - CT.gov + SEC wiring backtest with LLM
- **`backtest_ctgov_sec_wiring.py`** - CT.gov + SEC wiring backtest
- **`backtest_ctgov_real.py`** - Real CT.gov backtest with actual data

### Test Infrastructure
- **`run_pubmed_e2e_test.sh`** - End-to-end test script for PubMed pipeline
- **`README_pubmed_e2e_test.md`** - Documentation for PubMed end-to-end tests

## Usage

### Running Tests
```bash
# Run specific test
python tests/scripts/test_top_k_guard.py

# Run debug script
python tests/scripts/debug_cassava_trial.py

# Run backtest
python tests/scripts/backtest_pubmed_cassava.py
```

### Test Categories

#### Unit Tests
These test specific functionality:
- `test_top_k_guard.py`
- `test_early_stopping_*.py`
- `test_cassava_*.py`

#### Integration Tests
These test component interactions:
- `backtest_*.py`
- `run_pmc2978916_*.py`

#### Debug Scripts
These help debug specific issues:
- `debug_cassava_trial.py`
- `analyze_cassava_misses.py`

#### End-to-End Tests
These test complete workflows:
- `run_pubmed_e2e_test.sh`

## Test Data

### Cassava Trial (NCT04388254)
Many tests use the Cassava trial as a test case:
- Asset: simufilam (PTI-125)
- Indication: Alzheimer's disease
- Phase: 2
- Primary endpoint: ADAS-Cog11

### PMC2978916 Paper
Several tests use this specific paper:
- PubMed ID: PMC2978916
- Used for testing document processing

### Keytruda Trial
Some tests use Keytruda as a reference:
- Asset: pembrolizumab
- Indication: Various cancers
- Used for comparison testing

## Test Configuration

### Environment Setup
Tests require:
- Database connection
- OpenAI API key (for LLM tests)
- Test data files
- Proper Python path

### Common Test Patterns
```python
# Import test modules (package should be installed in development mode)
from ncfd.module import ClassName

# Run test
def test_functionality():
    # Test implementation
    pass
```

## Debugging

### Common Issues
1. **Import errors**: Ensure src path is added correctly
2. **Database errors**: Check database connection and migrations
3. **API errors**: Verify API keys and rate limits
4. **File not found**: Check test data file paths

### Debug Mode
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable debug logging for specific modules
logging.getLogger('ncfd.module').setLevel(logging.DEBUG)
```

## Test Maintenance

### Adding New Tests
1. Use descriptive names starting with `test_`
2. Include proper setup and teardown
3. Add error handling and logging
4. Document test purpose and data requirements
5. Update this README

### Test Data Management
- Keep test data files in appropriate locations
- Use realistic but anonymized data
- Document data sources and formats
- Version control test data files

### Test Execution
- Run tests individually for debugging
- Use pytest for batch execution
- Check test output and logs
- Verify test results match expectations

## Integration with Main Tests

These scripts complement the main test suite in `tests/`:
- Main tests: Unit and integration tests using pytest
- Script tests: End-to-end and manual testing scenarios
- Both use the same test data and configuration

---

**Last Updated**: January 2025
