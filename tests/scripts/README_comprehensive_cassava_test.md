# Comprehensive Cassava Pipeline Test

This test suite uses real-world Cassava Sciences trial data to comprehensively test multiple pipeline components in an integrated manner.

## Overview

The test leverages the Cassava Sciences Phase 2 trial (NCT04388254) and Phase 3 trial (NCT05515666) to validate:

- **Database Layer**: All major tables and relationships
- **CT.gov Pipeline**: Trial data extraction and company matching
- **PubMed Pipeline**: Literature processing with simufilam entity pack
- **Study Card Pipeline**: LLM-first architecture with evidence extraction
- **Orchestrator**: Pipeline coordination and error handling
- **Data Integrity**: End-to-end validation

## Real-World Data Used

### Cassava Trials
- **NCT04388254**: Phase 2, Completed, ADAS-Cog11 endpoint
- **NCT05515666**: Phase 3, Recruiting, ADAS-Cog11 endpoint

### Company Data
- **Cassava Sciences, Inc.** (NASDAQ: SAVA)
- **Simufilam** (PTI-125) - filamin A inhibitor
- **Indication**: Alzheimer's disease

## Test Phases

### Phase 1: Database Setup
- Clears test database completely
- Creates all tables
- Seeds real company and asset data

### Phase 2: CT.gov Trial Seeding
- Seeds real Cassava trial data
- Tests company matching
- Validates trial data integrity

### Phase 3: PubMed Literature Processing
- Uses simufilam entity pack
- Tests document retrieval and scoring
- Validates document-trial linking

### Phase 4: Study Card Generation
- Tests LLM workers (method auditor, results distiller, gate proposer)
- Validates evidence extraction and provenance tracking
- Tests gate analysis and decision making

### Phase 5: Orchestrator Integration
- Tests pipeline coordination
- Validates error handling and recovery
- Tests state management

### Phase 6: Validation and Reporting
- Validates data integrity
- Generates comprehensive reports
- Provides detailed metrics

## Usage

### Quick Start
```bash
# Run the comprehensive test
make test-cassava

# Or run with fresh database
make test-cassava-clean

# Or run directly
python tests/scripts/run_comprehensive_cassava_test.py
```

### Prerequisites
- PostgreSQL database (`ncfd`)
- OpenAI API key for LLM workers
- Python environment with all dependencies

### Configuration
The test uses `config/comprehensive_cassava_test.yaml` for configuration. Key settings:

- **Database**: Uses test database (`ncfd_test`)
- **LLM**: Uses GPT-4o-mini for all workers
- **PubMed**: Uses simufilam entity pack
- **Study Cards**: LLM-first architecture with validation

## Test Output

### Console Output
- Real-time progress updates
- Phase-by-phase status
- Entity counts and validation results
- Error and warning summaries

### Log Files
- **Main Log**: `logs/comprehensive_cassava_test.log`
- **Results**: `tests/logs/comprehensive_cassava_test_results.json`

### Results Structure
```json
{
  "test_info": {
    "start_time": "2024-01-01T00:00:00Z",
    "duration_seconds": 120.5
  },
  "database_setup": { "status": "success" },
  "ctgov_seeding": { "status": "success", "trials_seeded": 2 },
  "pubmed_processing": { "status": "success", "documents_created": 150 },
  "study_card_generation": { "status": "success", "trials_processed": 2 },
  "orchestrator_testing": { "status": "success" },
  "validation_results": { "status": "success" }
}
```

## Expected Results

### Entity Counts
- **Companies**: 1 (Cassava Sciences)
- **Trials**: 2 (NCT04388254, NCT05515666)
- **Documents**: 50-200 (PubMed literature)
- **Studies**: 2+ (trial studies)

### Pipeline Components
- **CT.gov**: Trial seeding and company matching
- **PubMed**: Document retrieval and scoring
- **Study Cards**: Evidence extraction and gate analysis
- **Orchestrator**: Pipeline coordination

### Data Integrity
- All trials have company associations
- Some trials have document links
- Evidence spans have proper provenance
- Gate assessments are generated

## Troubleshooting

### Common Issues
1. **Database Connection**: Ensure test database is running
2. **API Keys**: Verify OpenAI API key is set
3. **Dependencies**: Ensure all Python packages are installed
4. **Permissions**: Check database user permissions

### Debug Mode
```bash
# Run with debug logging
LOG_LEVEL=DEBUG python tests/scripts/run_comprehensive_cassava_test.py
```

### Clean Run
```bash
# Reset database and run fresh
make db-reset
make test-cassava-clean
```

## Benefits

1. **Real Data**: Uses actual Cassava trial data
2. **Comprehensive**: Tests most pipeline components
3. **Isolated**: Uses test database, no production impact
4. **Reproducible**: Consistent test data and configuration
5. **Detailed**: Provides comprehensive logging and validation

## Integration with CI/CD

The test can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions step
- name: Run Comprehensive Cassava Test
  run: |
    make test-cassava
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    PSQL_DSN: postgresql://ncfd:ncfd@localhost:5432/ncfd_test
```

## Contributing

When modifying the test:

1. **Update Real Data**: Keep trial data current and accurate
2. **Maintain Coverage**: Ensure all pipeline components are tested
3. **Validate Results**: Check that expected outcomes are reasonable
4. **Document Changes**: Update this README for any modifications
5. **Test Thoroughly**: Run the test multiple times to ensure stability
