# Comprehensive Cassava Pipeline Test V2

## Overview

This is a completely rewritten version of the Cassava pipeline test that fixes all the issues found in the original version and provides a clean, simplified architecture for testing the Cassava Sciences Phase 3 trial (NCT05515666).

## Key Improvements Over V1

### 🔧 **Fixed Issues**

1. **No More Duplicate Query Building**
   - V1 had confusing orchestrator vs individual test execution
   - V2 uses a single, clear execution path through the orchestrator
   - No more conflicting `skip_individual_pipeline_tests` configuration

2. **Simplified Configuration**
   - Single configuration source with clear hierarchy
   - No conflicting flags or confusing settings
   - Proper CT.gov filtering to Cassava trials only

3. **Better Error Handling**
   - Consistent error handling patterns throughout
   - Clear error messages and proper exception propagation
   - No more hard failures on specific error types

4. **Cleaner Logging**
   - Reduced noise from DEBUG logs
   - Focused on useful information
   - Consistent log levels and formatting

5. **Proper Transaction Management**
   - Clear database transaction boundaries
   - Proper session management
   - No more potential race conditions

### 🏗️ **Architecture Improvements**

1. **Single Execution Path**
   ```
   Database Setup → CT.gov Ingestion → PubMed Processing → Study Card Generation → Independent Analysis → Validation
   ```

2. **Proper CT.gov Integration**
   - Runs actual CT.gov ingestion with filtering
   - Only processes Cassava trials
   - Uses real data instead of seeded data

3. **Comprehensive Pipeline Testing**
   - Tests the complete pipeline end-to-end
   - Validates each phase independently
   - Provides detailed metrics and reporting

## Usage

### Prerequisites

Before running the test, ensure your PostgreSQL database has the required extensions:

```bash
# Setup database with required extensions (run once)
python scripts/setup_test_database.py
```

This will create the necessary PostgreSQL extensions (`pg_trgm`, `btree_gin`, etc.) and database schema.

### Run the Test

```bash
# Using Makefile (recommended - handles database setup automatically)
make test-cassava-v2

# Manual setup and run
python scripts/setup_test_database.py
python tests/scripts/run_cassava_test_v2.py

# Direct execution
python tests/scripts/comprehensive_cassava_pipeline_test_v2.py
```

### Expected Results

The test should:
1. ✅ Set up a clean test database
2. ✅ Ingest Cassava trials from CT.gov
3. ✅ Process PubMed literature for Cassava trials
4. ✅ Generate study cards with LLM analysis
5. ✅ Run independent LLM analysis
6. ✅ Validate results and check for expected papers

### Expected Papers

The test specifically looks for these key Cassava papers:
- **PMC10531384** (2023): "Simufilam Reverses Aberrant Receptor Interactions"
- **PMC10339288** (2023): "Simufilam suppresses overactive mTOR and restores its"
- **JPAD 2020**: "PTI-125 Reduces Biomarkers of Alzheimer's Disease in Patients"

## Configuration

The test uses a simplified configuration that:
- Forces CT.gov ingestion with Cassava filtering
- Uses comprehensive PubMed search terms
- Enables all study card generation stages
- Runs independent LLM analysis
- Provides detailed validation and reporting

## Output

The test generates:
- **Console output**: Real-time progress and final summary
- **JSON results**: Detailed results saved to `tests/logs/comprehensive_cassava_test_v2_results.json`
- **Database state**: Preserved for inspection (no cleanup)

## Key Differences from V1

| Aspect | V1 | V2 |
|--------|----|----|
| **Execution Path** | Confusing orchestrator + individual tests | Single orchestrator path |
| **CT.gov** | Seeded data only | Real CT.gov ingestion with filtering |
| **Configuration** | Conflicting flags | Single, clear configuration |
| **Error Handling** | Inconsistent patterns | Standardized error handling |
| **Logging** | Noisy DEBUG logs | Clean, focused logging |
| **Validation** | Basic checks | Comprehensive validation |
| **Reporting** | Basic summary | Detailed metrics and analysis |

## Troubleshooting

### Common Issues

1. **Database Extension Issues**
   ```
   ERROR: operator class "gin_trgm_ops" does not exist for access method "gin"
   ```
   **Solution**: Run the database setup script first:
   ```bash
   python scripts/setup_test_database.py
   ```
   
   If that fails, install PostgreSQL contrib modules:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install postgresql-contrib
   
   # macOS with Homebrew
   brew install postgresql
   ```

2. **Database Connection Issues**
   - Ensure test database is properly configured
   - Check environment variables in `env.example`
   - Verify database user has CREATE EXTENSION privileges

3. **CT.gov API Issues**
   - Verify internet connectivity
   - Check CT.gov API rate limits

4. **PubMed API Issues**
   - Ensure PubMed API key is configured
   - Check rate limiting settings

5. **LLM API Issues**
   - Verify OpenAI API key is configured
   - Check rate limits and quotas

### Debug Mode

To enable more verbose logging, modify the logging level in the test:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Future Improvements

1. **Parallel Execution**: Enable parallel processing for faster execution
2. **Incremental Testing**: Support for incremental test runs
3. **Custom Filters**: Allow custom CT.gov and PubMed filters
4. **Performance Metrics**: Add detailed performance timing
5. **Integration Tests**: Add integration with other pipeline components

## Contributing

When making changes to this test:
1. Maintain the single execution path principle
2. Keep configuration simple and clear
3. Use consistent error handling patterns
4. Add comprehensive validation checks
5. Update this README with any changes
