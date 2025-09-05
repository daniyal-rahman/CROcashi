# Scripts Directory

This directory contains operational scripts for the CROcashi system. Test and debug scripts have been moved to `tests/scripts/`.

## Core Operational Scripts

### Analysis & Synthesis
- **`synthesize.py`** - Generate deterministic synthesis for a trial
  ```bash
  python scripts/synthesize.py --trial-id trial_001
  ```

- **`gpt5_analysis.py`** - Run GPT-5 thinking analysis on a trial
  ```bash
  python scripts/gpt5_analysis.py --trial-id trial_001
  ```

- **`run_signals_from_extraction.py`** - Run signal detection from extracted study cards
  ```bash
  python scripts/run_signals_from_extraction.py --trial-id trial_001
  ```

### Backtesting
- **`backtest.py`** - Main backtest CLI for NCFD pipeline evaluation
  ```bash
  python scripts/backtest.py --stage all --config config/backtest.yaml
  ```

### Data Ingestion
- **`ingest_ctgov_since_august.py`** - Ingest CT.gov trials since August
  ```bash
  python scripts/ingest_ctgov_since_august.py
  ```

- **`ingest_sec.py`** - Ingest SEC filing data
  ```bash
  python scripts/ingest_sec.py
  ```

- **`ingest_aliases_from_text.py`** - Ingest company aliases from text file
  ```bash
  python scripts/ingest_aliases_from_text.py --file aliases.txt
  ```

### Data Management
- **`load_company_aliases.py`** - Load company aliases into database
  ```bash
  python scripts/load_company_aliases.py
  ```

- **`seed_company_trials.py`** - Seed database with company and trial data
  ```bash
  python scripts/seed_company_trials.py
  ```

- **`wire_asset_to_trials.py`** - Link assets to trials
  ```bash
  python scripts/wire_asset_to_trials.py
  ```

- **`manual_asset_resolution.py`** - Manual asset resolution tool
  ```bash
  python scripts/manual_asset_resolution.py
  ```

### Verification & Validation
- **`verify_resolved_sponsors.py`** - Verify sponsor resolution results
  ```bash
  python scripts/verify_resolved_sponsors.py
  ```

### System Administration
- **`nuke_and_reset.sh`** - Reset database and rebuild from scratch
  ```bash
  ./scripts/nuke_and_reset.sh
  ```

## Script Categories

### Production Scripts
These scripts are used in production workflows:
- `synthesize.py`
- `gpt5_analysis.py`
- `backtest.py`
- `ingest_ctgov_since_august.py`
- `ingest_sec.py`

### Data Setup Scripts
These scripts are used for initial data setup and maintenance:
- `load_company_aliases.py`
- `seed_company_trials.py`
- `wire_asset_to_trials.py`
- `ingest_aliases_from_text.py`

### Utility Scripts
These scripts provide utility functions:
- `manual_asset_resolution.py`
- `verify_resolved_sponsors.py`
- `run_signals_from_extraction.py`

### System Administration
These scripts are for system administration:
- `nuke_and_reset.sh`

## Test Scripts

Test and debug scripts have been moved to `tests/scripts/` and include:
- Specific backtest scripts (e.g., `backtest_pubmed_cassava.py`)
- Debug scripts (e.g., `debug_cassava_trial.py`)
- Test scripts (e.g., `test_top_k_guard.py`)
- PMC2978916 test scripts
- Analysis scripts for specific trials

## Usage Guidelines

### Prerequisites
- Database must be set up and migrations run
- Environment variables configured (DATABASE_URL, OPENAI_API_KEY, etc.)
- Dependencies installed

### Common Patterns
Most scripts follow these patterns:
```bash
# Basic usage
python scripts/script_name.py --required-arg value

# With configuration
python scripts/script_name.py --config config/file.yaml

# With output file
python scripts/script_name.py --out output.json
```

### Error Handling
- Scripts include proper error handling and logging
- Check logs for detailed error information
- Use `--help` flag for usage information

## Adding New Scripts

When adding new scripts:
1. Use descriptive names
2. Include proper argument parsing
3. Add error handling and logging
4. Document usage in this README
5. Move test/debug scripts to `tests/scripts/`

## Script Dependencies

### Database
- Most scripts require database connection
- Use `get_db_session()` for database access
- Ensure migrations are up to date

### Configuration
- Scripts use YAML configuration files
- Environment variables for sensitive data
- Default configurations provided

### External APIs
- OpenAI API for GPT-5 analysis
- CT.gov API for trial data
- SEC API for filing data

---

**Last Updated**: January 2025
