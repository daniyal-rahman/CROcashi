# PubMed End-to-End Test

This directory contains a comprehensive end-to-end test for the PubMed ingestion pipeline that validates the complete workflow from PubMed API search to database storage.

## Overview

The PubMed E2E test (`test_pubmed_e2e.py`) is designed to:

1. **Validate PubMed API connectivity** - Ensure the system can connect to PubMed APIs
2. **Test the complete pipeline** - Execute all three stages (U0, U1, OA) of the PubMed pipeline
3. **Verify database operations** - Test document creation, storage, and relationships
4. **Validate data integrity** - Ensure extracted data meets quality standards
5. **Test error handling** - Verify the system handles edge cases gracefully

## Test Architecture

### Pipeline Stages Tested

- **Stage U0 (Metadata Discovery)**: PubMed search, metadata retrieval, initial mapping
- **Stage U1 (Abstract Evaluation)**: Entity extraction, scoring, candidate identification
- **Stage OA (Full Text Analysis)**: PMC linking, open access detection, full text retrieval

### Test Components

- **API Connectivity**: PubMed ESearch, ESummary, EFetch, ELink APIs
- **Query Building**: Clinical trial query construction and validation
- **Data Processing**: Document mapping, entity extraction, scoring
- **Database Operations**: Document storage, text pages, citations, relationships
- **Error Handling**: Invalid queries, empty inputs, rate limiting

## Prerequisites

### Required Dependencies

```bash
# Core dependencies (should already be installed)
pip install aiohttp sqlalchemy psycopg2-binary

# For development/testing
pip install pytest pytest-asyncio
```

### Environment Setup

1. **Database**: The test uses in-memory SQLite by default (no setup required)
2. **PubMed API**: No API key required, but rate limits apply
3. **Configuration**: Uses default test configuration or custom config file

## Usage

### Basic Test Execution

```bash
# Run with default settings (NCT04368728 - Moderna COVID-19 trial)
python test_pubmed_e2e.py

# Run with verbose logging
python test_pubmed_e2e.py --verbose

# Run with custom trial ID
python test_pubmed_e2e.py --trial-id NCT04535194

# Run with custom assets and indications
python test_pubmed_e2e.py --assets "Keytruda" "Pembrolizumab" --indications "cancer" "melanoma"
```

### Configuration File

Create a custom configuration file:

```json
{
  "test_trial_id": "NCT04535194",
  "test_assets": ["Keytruda", "Pembrolizumab"],
  "test_indications": ["cancer", "melanoma"],
  "max_results": 100,
  "email": "your-email@example.com"
}
```

Run with custom config:

```bash
python test_pubmed_e2e.py --config config/my_test_config.json
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--config` | Path to configuration file | None |
| `--trial-id` | Clinical trial ID to test | NCT04368728 |
| `--assets` | Space-separated asset names | mRNA-1273, Moderna |
| `--indications` | Space-separated indications | COVID-19, SARS-CoV-2 |
| `--verbose` | Enable verbose logging | False |

## Test Scenarios

### 1. Real Clinical Trial Test

**Default Test**: NCT04368728 (Moderna mRNA-1273 COVID-19 vaccine trial)

- **Asset**: mRNA-1273, Moderna, Spikevax
- **Indication**: COVID-19, SARS-CoV-2
- **Expected Results**: Multiple publications, abstracts, sponsor information

### 2. Multiple Asset Test

Tests the system's ability to handle multiple drug/compound names:

```bash
python test_pubmed_e2e.py --assets "Keytruda" "Pembrolizumab" "Opdivo" --indications "cancer"
```

### 3. Error Handling Test

Automatically tests:
- Invalid PubMed queries
- Empty asset lists
- Large result sets
- Rate limiting scenarios

### 4. Database Integration Test

Tests:
- Document creation and retrieval
- Text page storage
- Citation linking
- Relationship integrity

## Output and Results

### Console Output

The test provides real-time progress updates:

```
🚀 Starting PubMed E2E Test
🔍 Testing PubMed API connectivity...
✅ API connectivity test passed - found 3 results for NCT04368728
🔍 Testing query building...
✅ Query building test passed - generated query: (mRNA-1273[Title/Abstract] OR Moderna[Title/Abstract])...
🔍 Testing individual pipeline stages...
Testing Stage U0...
✅ Stage U0 passed - processed 15 documents
...
```

### Test Report

A comprehensive JSON report is generated:

```json
{
  "start_time": "2024-01-15T10:30:00",
  "end_time": "2024-01-15T10:35:30",
  "duration_seconds": 330.5,
  "pipeline_results": [...],
  "database_validation": {...},
  "data_integrity": {...},
  "test_summary": {
    "total_tests": 8,
    "successful_tests": 8,
    "success_rate": 100.0
  }
}
```

### Report File

Reports are saved as: `pubmed_e2e_test_report_YYYYMMDD_HHMMSS.json`

## Interpreting Results

### Success Indicators

- **API Connectivity**: ✅ Found results for trial ID
- **Pipeline Stages**: All 3 stages complete successfully
- **Data Quality**: Documents have abstracts, NCT IDs, sponsor info
- **Database**: All CRUD operations succeed
- **Error Handling**: Edge cases handled gracefully

### Common Issues and Solutions

#### 1. API Rate Limiting

```
⚠️ Health check failed, but continuing with test
```

**Solution**: Reduce `rate_limit_per_sec` in config or add API key

#### 2. No Results Found

```
❌ No PMIDs found in search results
```

**Solution**: Check trial ID validity, adjust search terms

#### 3. Database Errors

```
❌ Document not found after creation
```

**Solution**: Check database connection, table creation

#### 4. Pipeline Stage Failures

```
❌ Stage U1 failed: Stage U0 must complete successfully before U1
```

**Solution**: Ensure proper stage dependencies, check data flow

## Performance Considerations

### Rate Limiting

- **Without API Key**: 3 requests/second
- **With API Key**: 10 requests/second
- **Test Default**: 3 requests/second (conservative)

### Test Duration

- **Typical Test**: 2-5 minutes
- **Large Result Sets**: 5-15 minutes
- **Full Text Fetching**: 10-30 minutes (disabled by default)

### Resource Usage

- **Memory**: Minimal (in-memory SQLite)
- **Network**: PubMed API calls only
- **CPU**: Low (async processing)

## Customization

### Adding New Test Scenarios

Extend the `PubMedE2ETest` class:

```python
async def _test_custom_scenario(self):
    """Test custom functionality."""
    logger.info("🔍 Testing custom scenario...")
    # Your test logic here
    pass
```

### Modifying Validation Rules

Update the `_validate_data_integrity` method:

```python
# Add custom validation
if doc.get('custom_field'):
    validation_results['documents_with_custom_field'] += 1
```

### Custom Test Data

Modify the test configuration:

```json
{
  "test_assets": ["YourDrug", "YourCompany"],
  "test_indications": ["YourDisease"],
  "validation": {
    "min_documents": 10,
    "custom_validation": true
  }
}
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
- name: Run PubMed E2E Test
  run: |
    python scripts/test_pubmed_e2e.py --config config/pubmed_e2e_test_config.json
  env:
    DATABASE_URL: ${{ secrets.TEST_DATABASE_URL }}
```

### Exit Codes

- **0**: All tests passed
- **1**: Test failures detected
- **130**: Test interrupted (Ctrl+C)

## Troubleshooting

### Common Problems

1. **Import Errors**: Ensure `src/` is in Python path
2. **Database Errors**: Check SQLAlchemy version compatibility
3. **Async Issues**: Ensure Python 3.7+ and proper async setup
4. **Rate Limiting**: Reduce concurrent requests, add delays

### Debug Mode

Enable verbose logging for detailed debugging:

```bash
python test_pubmed_e2e.py --verbose
```

### Manual Testing

Test individual components:

```python
# Test just the client
async with PubMedClient() as client:
    result = await client.esearch("cancer", max_results=5)
    print(result)

# Test just the pipeline
async with PubMedPipeline() as pipeline:
    result = await pipeline._execute_stage_u0(["test"], ["test"])
    print(result)
```

## Contributing

### Adding New Tests

1. Extend the `PubMedE2ETest` class
2. Add test method with `_test_` prefix
3. Update the main test runner
4. Add validation logic

### Reporting Issues

Include:
- Test configuration
- Error messages
- System information
- Expected vs actual behavior

## References

- [PubMed E-utilities Documentation](https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/)
- [NCFD PubMed Pipeline Documentation](../docs/)
- [Database Schema](../src/ncfd/db/models.py)
- [Pipeline Implementation](../src/ncfd/ingest/pubmed/pipeline.py)
