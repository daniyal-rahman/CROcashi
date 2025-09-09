# Real End-to-End Pipeline

This document describes the real end-to-end pipeline implementation that runs the complete automated system from CT.gov ingestion through study card generation and evaluation.

## Overview

The real E2E pipeline (`scripts/e2e_run.py`) implements the complete automated workflow:

1. **CT.gov Incremental Ingestion** - Pulls latest trials from CT.gov head
2. **SEC Company Wiring** - Maps trial sponsors to public companies  
3. **PubMed Literature Pipeline** - Retrieves and processes literature
4. **Trial Prioritization** - Uses literature queue to rank trials
5. **Study Card Generation** - Generates real study cards using LLM workers
6. **Automated Evaluation** - Evaluates and ranks study cards with LLM resolution

## Key Features

- **Real System Components**: Uses actual pipeline workers, not mocks
- **Early Stopping**: Stops when target study cards completed or budget exhausted  
- **Java Dependency Safe**: Lazy imports avoid Java/Lucene initialization issues
- **Comprehensive Logging**: Detailed execution logs and JSON reports
- **Configurable**: Production-ready YAML configuration
- **Persistent**: All results saved to database and file snapshots

## Usage

### Basic Usage

```bash
# Run with default settings (5 trials max, 1 study card target, 15min timeout)
make e2e

# Or run directly
python scripts/e2e_run.py --config config/e2e.yaml --max-trials 5 --at-least-study-cards 1
```

### Debug Mode

```bash
# Extended timeout with debug logging
make e2e-debug

# Or run directly  
python scripts/e2e_run.py --config config/e2e.yaml --max-trials 3 --time-budget-seconds 1800 --log-level DEBUG
```

### Docker Environment

```bash
# Run inside Docker container
make e2e-docker
```

### Force Full Scan

```bash
# Ignore incremental state and scan all data
make e2e-force-full

# Or run directly
python scripts/e2e_run.py --config config/e2e.yaml --force-full-scan
```

## Configuration

The pipeline uses `config/e2e.yaml` with production-ready settings:

- **LLM Provider**: OpenAI with gpt-4o-mini models
- **Retrieval Backend**: BM25 (avoids Java dependencies)
- **Database**: PostgreSQL via `PSQL_DSN`
- **Rate Limits**: Conservative API rate limits
- **Timeouts**: Reasonable timeouts for each stage

## Stopping Conditions

The pipeline stops when **any** of these conditions are met:

1. **Study Card Target**: Generated specified number of study cards (default: 1)
2. **Trial Limit**: Processed maximum number of trials (default: 5) 
3. **Time Budget**: Exceeded time budget (default: 900 seconds / 15 minutes)

## Output

### Console Logs
- Real-time execution progress
- Stage timings and metrics
- Study card generation details
- Error/warning reporting

### Reports Directory
- `e2e_execution_report_<id>.json` - Complete execution summary
- `study_card_<id>_<nct>.json` - Individual study card snapshots
- `evaluation_results_<id>.json` - Automated evaluation results

### Log Files  
- `logs/e2e_run.log` - Detailed execution logs
- `logs/e2e_debug.log` - Debug-level logs (when using debug mode)

## Prerequisites

### Environment Variables
```bash
# Required
export PSQL_DSN="postgresql+psycopg2://user:pass@host:port/db"
export OPENAI_API_KEY="sk-..."

# Optional
export DATABASE_URL="${PSQL_DSN}"  # Alternative to PSQL_DSN
```

### Database
- PostgreSQL running (via Docker: `docker compose up -d`)
- Database schema migrated (`make db-migrate`)
- Some trial and company data ingested

### Dependencies
- Python 3.12+ environment
- All packages from `pyproject.toml` installed
- No Java/JVM required (BM25 backend avoids this)

## Architecture

### Lazy Component Loading

The pipeline uses lazy imports to avoid Java dependency issues:

```python
# Components loaded only when needed
def lazy_import_orchestrator():
    from ncfd.pipeline.orchestrator import UnifiedPipelineOrchestrator
    return UnifiedPipelineOrchestrator
```

This ensures the script starts quickly and only loads heavy components when actually used.

### Real vs Mock

Unlike previous E2E implementations, this version:

- ✅ **Uses real database queries** for trials and companies
- ✅ **Executes real PubMed pipeline** with document retrieval
- ✅ **Runs real LLM workers** for study card generation  
- ✅ **Persists results** to database tables
- ✅ **Performs real evaluation** with optional LLM resolution

### Error Handling

- **Graceful degradation**: Pipeline continues if non-critical stages fail
- **Retry logic**: Configurable retries for transient failures
- **Early exit**: Clear stop conditions prevent runaway execution
- **Comprehensive logging**: All errors captured with context

## Troubleshooting

### Java Module Errors

If you see `java.lang.module.FindException: Module jdk.incubator.vector not found`:

1. Check that `config/e2e.yaml` uses `backend: bm25` (not lucene)
2. Ensure no Java-dependent retrievers are configured
3. The lazy imports should prevent this - file a bug if it persists

### Database Connection

```bash
# Test database connectivity
make db-test

# Check if required tables exist
make db-shell
\dt trials
\dt companies  
\dt studies
```

### Missing Data

The pipeline requires some existing data:

```bash
# Ingest some initial CT.gov data
make ctgov-sync

# Ingest company data  
make sec-sync
```

### LLM Rate Limits

If hitting OpenAI rate limits:
1. Reduce `--max-trials` 
2. Lower rate limits in `config/e2e.yaml`
3. Check `OPENAI_API_KEY` has sufficient quota

## Performance

### Typical Execution Times

- **1 study card**: 2-5 minutes
- **3 study cards**: 5-10 minutes  
- **5 study cards**: 10-15 minutes

### Cost Estimates

- **1 study card**: ~$0.50-1.00 in LLM costs
- **5 study cards**: ~$2.50-5.00 in LLM costs

Costs depend on literature volume and LLM model selection.

## Development

### Adding New Stopping Conditions

Modify `E2EExecutionContext.should_stop()`:

```python
def should_stop(self) -> tuple[bool, str]:
    # Add custom condition
    if self.custom_condition_met():
        return True, "Custom condition reached"
    # ... existing conditions
```

### Customizing Pipeline Stages

Override stage methods in `RealE2EPipelineRunner`:

```python
async def _custom_prioritization(self):
    # Custom trial prioritization logic
    pass
```

### Testing Changes

```bash
# Test with minimal settings
python scripts/e2e_run.py --config config/e2e.yaml --max-trials 1 --time-budget-seconds 300

# Dry run mode (if implemented)
python scripts/e2e_run.py --config config/e2e.yaml --dry-run
```
