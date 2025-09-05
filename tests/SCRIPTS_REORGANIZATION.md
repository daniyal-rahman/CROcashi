# Scripts Reorganization Summary

## Overview

The scripts directory has been reorganized to separate operational scripts from test and debug scripts, making it easier to find and use the right tools for different purposes.

## What Was Moved

### Test Scripts (12 files moved to `tests/scripts/`)

#### Early Stopping Tests
- `test_top_k_guard.py` - Test Top-K guard mechanism
- `test_early_stopping_keytruda.py` - Test early stopping with Keytruda trial
- `test_early_stopping_cassava.py` - Test early stopping with Cassava trial

#### Asset Resolution Tests
- `test_cassava_asset_resolution.py` - Test asset resolution for Cassava trial
- `test_cassava_papers.py` - Test paper processing for Cassava trial

#### Debug Scripts
- `debug_cassava_trial.py` - Debug script for Cassava trial analysis

#### Analysis Scripts
- `analyze_cassava_misses.py` - Analyze missed signals in Cassava trial

#### PMC2978916 Test Scripts
- `run_pmc2978916_debug.py` - Debug script for PMC2978916 paper
- `run_pmc2978916_test.py` - Test script for PMC2978916 paper
- `run_pmc2978916_quick.py` - Quick test for PMC2978916 paper

#### Backtest Scripts
- `backtest_pubmed_cassava.py` - PubMed literature review backtest for Cassava trial
- `backtest_ctgov_sec_wiring_with_llm.py` - CT.gov + SEC wiring backtest with LLM
- `backtest_ctgov_sec_wiring.py` - CT.gov + SEC wiring backtest
- `backtest_ctgov_real.py` - Real CT.gov backtest with actual data

#### Test Infrastructure
- `run_pubmed_e2e_test.sh` - End-to-end test script for PubMed pipeline
- `README_pubmed_e2e_test.md` - Documentation for PubMed end-to-end tests

## What Remains in `scripts/`

### Core Operational Scripts (13 files)

#### Analysis & Synthesis
- `synthesize.py` - Generate deterministic synthesis for a trial
- `gpt5_analysis.py` - Run GPT-5 thinking analysis on a trial
- `run_signals_from_extraction.py` - Run signal detection from extracted study cards

#### Backtesting
- `backtest.py` - Main backtest CLI for NCFD pipeline evaluation

#### Data Ingestion
- `ingest_ctgov_since_august.py` - Ingest CT.gov trials since August
- `ingest_sec.py` - Ingest SEC filing data
- `ingest_aliases_from_text.py` - Ingest company aliases from text file

#### Data Management
- `load_company_aliases.py` - Load company aliases into database
- `seed_company_trials.py` - Seed database with company and trial data
- `wire_asset_to_trials.py` - Link assets to trials
- `manual_asset_resolution.py` - Manual asset resolution tool

#### Verification & Validation
- `verify_resolved_sponsors.py` - Verify sponsor resolution results

#### System Administration
- `nuke_and_reset.sh` - Reset database and rebuild from scratch

## New Documentation

### `scripts/README.md`
- Documents all operational scripts
- Provides usage examples
- Categorizes scripts by purpose
- Includes guidelines for adding new scripts

### `tests/scripts/README.md`
- Documents all test and debug scripts
- Explains test categories and usage
- Provides debugging guidance
- Describes test data and configuration

## Benefits

### Improved Organization
- **Clear separation** between operational and test scripts
- **Easier navigation** for different use cases
- **Reduced confusion** about script purposes

### Better Documentation
- **Comprehensive READMEs** for both directories
- **Usage examples** for all scripts
- **Clear categorization** by purpose

### Enhanced Maintainability
- **Focused directories** with specific purposes
- **Clear guidelines** for adding new scripts
- **Consistent patterns** across script types

## Script Categories

### Production Scripts
Scripts used in production workflows:
- `synthesize.py`
- `gpt5_analysis.py`
- `backtest.py`
- `ingest_ctgov_since_august.py`
- `ingest_sec.py`

### Data Setup Scripts
Scripts used for initial data setup and maintenance:
- `load_company_aliases.py`
- `seed_company_trials.py`
- `wire_asset_to_trials.py`
- `ingest_aliases_from_text.py`

### Utility Scripts
Scripts that provide utility functions:
- `manual_asset_resolution.py`
- `verify_resolved_sponsors.py`
- `run_signals_from_extraction.py`

### System Administration
Scripts for system administration:
- `nuke_and_reset.sh`

## Usage Patterns

### Operational Scripts
```bash
# Run synthesis
python scripts/synthesize.py --trial-id trial_001

# Run backtest
python scripts/backtest.py --stage all --config config/backtest.yaml

# Ingest data
python scripts/ingest_ctgov_since_august.py
```

### Test Scripts
```bash
# Run specific test
python tests/scripts/test_top_k_guard.py

# Run debug script
python tests/scripts/debug_cassava_trial.py

# Run backtest
python tests/scripts/backtest_pubmed_cassava.py
```

## Future Guidelines

### Adding New Scripts
1. **Operational scripts** go in `scripts/`
2. **Test/debug scripts** go in `tests/scripts/`
3. Use descriptive names
4. Include proper argument parsing
5. Add error handling and logging
6. Document usage in appropriate README

### Script Naming
- **Operational scripts**: Descriptive names (e.g., `synthesize.py`)
- **Test scripts**: Start with `test_` (e.g., `test_top_k_guard.py`)
- **Debug scripts**: Start with `debug_` (e.g., `debug_cassava_trial.py`)

### Documentation
- Update appropriate README when adding scripts
- Include usage examples
- Document dependencies and prerequisites
- Explain script purpose and context

---

**Reorganization Date**: January 2025
**Next Review**: February 2025
