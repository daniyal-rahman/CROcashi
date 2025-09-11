# Cassava CT.gov + PubMed Ingestion Test

This test demonstrates the complete workflow of:
1. Querying CT.gov for Cassava Sciences trials
2. Storing trial data in the test database
3. Using the orchestrator to ingest PubMed literature for these trials
4. Showing comprehensive results
5. Cleaning up the database

## Files

- `cassava_ctgov_pubmed_test.py` - Main test implementation
- `run_cassava_test.py` - Simple runner script
- `README_cassava_test.md` - This documentation

## Prerequisites

1. **Environment Setup**: Ensure you have the required environment variables set:
   ```bash
   export PSQL_DSN="postgresql://user:pass@localhost:5432/test_db"
   export OPENAI_API_KEY="your-openai-key"
   export PUBMED_API_KEY="your-pubmed-key"  # Optional but recommended
   export PUBMED_EMAIL="your-email@example.com"
   ```

2. **Database**: The test uses the PostgreSQL test database. Make sure it's running and accessible.

3. **Dependencies**: All required Python packages should be installed.

## Usage

### Option 1: Direct execution
```bash
cd /Users/danirahman/Repos/CROcashi
python tests/scripts/cassava_ctgov_pubmed_test.py
```

### Option 2: Using the runner script
```bash
cd /Users/danirahman/Repos/CROcashi
python tests/scripts/run_cassava_test.py
```

## What the Test Does

### 1. CT.gov Data Ingestion
- Queries CT.gov API for all trials matching Cassava/Simufilam keywords
- Extracts relevant trial metadata (NCT ID, title, phase, status, etc.)
- Stores trials in the test database with proper company relationships

### 2. PubMed Literature Ingestion
- Uses the orchestrator's PubMed pipeline to find relevant literature
- Searches for documents related to each trial's assets and indications
- Processes abstracts and extracts entities
- Links documents to trials through the database

### 3. Results Analysis
- Shows comprehensive statistics about trials and documents found
- Displays detailed information about each trial
- Lists PubMed documents linked to each trial
- Saves results to JSON file for further analysis

### 4. Database Cleanup
- Clears all test data after completion
- Ensures clean state for subsequent runs

## Expected Output

The test will show:
- Number of Cassava trials found in CT.gov
- Success/failure of PubMed ingestion
- Number of documents processed
- Detailed trial information including:
  - NCT ID and title
  - Sponsor and phase
  - Status and indication
  - Linked PubMed documents
- Any errors or warnings encountered

## Results Storage

Results are saved to `tests/logs/cassava_test_results.json` containing:
- Raw CT.gov trial data
- Database trial records
- PubMed ingestion results
- Test metadata and timestamps

## Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Check that PostgreSQL is running
   - Verify PSQL_DSN environment variable
   - Ensure database exists and is accessible

2. **PubMed API Rate Limiting**
   - The test respects rate limits (60 requests/minute)
   - If you hit limits, wait and retry
   - Consider getting a PubMed API key for higher limits

3. **Missing Dependencies**
   - Install required packages: `pip install -r requirements.txt`
   - Ensure all NCFD modules are importable

4. **Environment Variables**
   - Check that all required environment variables are set
   - Use `env.example` as a reference

### Debug Mode

To see more detailed logging:
```bash
export LOG_LEVEL=DEBUG
python tests/scripts/cassava_ctgov_pubmed_test.py
```

## Customization

You can modify the test to:
- Query different companies or drugs by changing `CASSAVA_QUERY`
- Adjust PubMed search parameters in the configuration
- Change the number of documents retrieved per trial
- Add additional data processing or analysis steps

## Notes

- The test automatically cleans up after itself
- It uses the test database, not production data
- All operations are logged for debugging
- The test is designed to be idempotent (can be run multiple times)
