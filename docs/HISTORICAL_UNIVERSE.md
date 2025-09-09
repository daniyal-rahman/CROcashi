# Historical Universe Backtest System

This document describes the historical universe backtest system for evaluating trial failure prediction models.

## Overview

The system builds a survivorship-safe historical universe of pivotal trials with ground-truth labels (primary outcome success/failure), implements time-based splits, and runs backtests with T-14 freeze logic.

## Architecture

### Phase 1: Universe Building (`universe_build.py`)
- Searches CT.gov for pivotal Phase 2/3 trials
- Maps sponsors to public companies via CIK/ticker resolution
- Filters by indication and completion date range
- Outputs: `trials.jsonl`, `summary.json`

### Phase 2: Document Harvesting (`harvest_docs.py`)
- Harvests SEC 8-K filings, press releases, conference abstracts
- Links documents to trials with timestamps
- Prioritizes SEC filings > PRs > abstracts > CT.gov Results
- Outputs: `documents.jsonl`, `documents_summary.json`

### Phase 3: Label Building (`build_labels.py`)
- Classifies trial outcomes from document text
- Uses phrase matching for "met/did not meet primary endpoint"
- Handles co-primary endpoints and conflicting signals
- Outputs: `labels.jsonl`, `labels_summary.json`

### Phase 4: Public Status (`public_status.py`)
- Detects if companies were public at event date
- Uses 8-K filing proximity and SEC submissions data
- Handles defunct/renamed companies safely
- Outputs: `public_status.csv`, `public_status_summary.json`

### Phase 5: Time Splits (`make_splits.py`)
- Creates train/val/test splits by event date
- Train: 2018-2020, Val: 2021, Test: 2022-2023
- Validates for leakage and temporal ordering
- Outputs: `train_ids.jsonl`, `val_ids.jsonl`, `test_ids.jsonl`

### Phase 6: T-14 Snapshots (`make_snapshots.py`)
- Builds freeze snapshots at T-14 days before event
- Analyzes coverage for Study Card building
- Tracks missing fields and scoreability
- Outputs: `snapshots/{trial_id}.json`, `coverage.jsonl`

### Phase 7: Backtest (`run_backtest_universe.py`)
- Runs existing S1-S9 signals and G1-G4 gates
- Computes p_fail using Bayesian scoring
- Evaluates Precision@K and hit rates
- Outputs: `ranked.jsonl`, `metrics.json`, `miss_audit.csv`

## Usage

### Quick Start

```bash
# Run complete pipeline for Alzheimer's trials
python scripts/universe_pipeline.py --indication "Alzheimer" --start-date "2018-01-01" --end-date "2023-12-31"
```

### Individual Phases

```bash
# Build universe only
python scripts/universe_pipeline.py --indication "Alzheimer" --phase universe

# Run specific phase
python scripts/universe_pipeline.py --indication "Alzheimer" --phase backtest
```

### Manual Execution

```bash
# Step 1: Build universe
python scripts/universe_build.py --indication "Alzheimer" --output-dir backtest/universe

# Step 2: Harvest documents
python scripts/harvest_docs.py --trials-file backtest/universe/trials.jsonl --output-dir backtest/universe

# Step 3: Build labels
python scripts/build_labels.py --trials-file backtest/universe/trials.jsonl --documents-file backtest/universe/documents.jsonl --output-dir backtest/universe

# Step 4: Public status
python scripts/public_status.py --trials-file backtest/universe/trials.jsonl --labels-file backtest/universe/labels.jsonl --output-dir backtest/universe

# Step 5: Time splits
python scripts/make_splits.py --labels-file backtest/universe/labels.jsonl --output-dir backtest/splits

# Step 6: T-14 snapshots
python scripts/make_snapshots.py --trials-file backtest/universe/trials.jsonl --documents-file backtest/universe/documents.jsonl --labels-file backtest/universe/labels.jsonl --output-dir backtest/snapshots

# Step 7: Run backtest
python scripts/run_backtest_universe.py --snapshots-dir backtest/snapshots/snapshots --coverage-file backtest/snapshots/coverage.jsonl --labels-file backtest/universe/labels.jsonl --splits-file backtest/splits/all_splits.json --output-dir backtest/results
```

## Configuration

Edit `config/universe_config.yaml` to customize:

- CT.gov search parameters
- Document harvesting sources
- Label classification phrases
- Time split ranges
- Coverage requirements
- Backtest metrics

## Data Formats

### Trials (`trials.jsonl`)
```json
{
  "trial_id": "TRIAL_NCT04388254",
  "nct_id": "NCT04388254",
  "title": "Study of Simufilam in Alzheimer's Disease",
  "phase": "PHASE3",
  "indication": "Alzheimer Disease",
  "primary_endpoint_text": "Change from baseline in ADAS-Cog11",
  "est_primary_completion_date": "2023-12-31",
  "sponsor": "Cassava Sciences Inc",
  "cik": "0001234567",
  "ticker": "SAVA"
}
```

### Documents (`documents.jsonl`)
```json
{
  "doc_id": "SEC_1234567_20231201_001",
  "trial_id": "TRIAL_NCT04388254",
  "source": "sec_8k",
  "published_at": "2023-12-01T10:30:00Z",
  "url": "https://www.sec.gov/Archives/edgar/data/1234567/000123456723000001/0001234567-23-000001.txt",
  "text": "Company announced that the Phase 3 trial did not meet the primary endpoint...",
  "linkage_confidence": 0.9
}
```

### Labels (`labels.jsonl`)
```json
{
  "trial_id": "TRIAL_NCT04388254",
  "event_date": "2023-12-01",
  "primary_outcome_success_bool": false,
  "label_source": "8k",
  "label_source_url": "https://www.sec.gov/Archives/edgar/data/1234567/000123456723000001/0001234567-23-000001.txt",
  "evidence_span": "did not meet the primary endpoint",
  "confidence": 0.9
}
```

### Coverage (`coverage.jsonl`)
```json
{
  "trial_id": "TRIAL_NCT04388254",
  "has_primary_endpoint": true,
  "has_n_total": true,
  "has_itt_status": false,
  "has_effect_size": true,
  "has_p_value": true,
  "scoreable": false,
  "missing_fields": ["itt_status"],
  "coverage_score": 0.8
}
```

## Key Features

### Survivorship-Safe Design
- Uses `public_status_at_event` instead of current ticker lists
- Handles defunct/renamed companies via SEC filings
- Manual overrides for edge cases

### Temporal Integrity
- T-14 freeze prevents look-ahead bias
- Time-based splits prevent leakage
- Document timestamps ensure proper ordering

### Coverage Tracking
- Monitors required fields for Study Card building
- Tracks scoreability per trial
- Identifies missing information sources

### Comprehensive Evaluation
- Precision@K for top predictions
- Hit rates at various thresholds
- Miss audit for unflagged failures
- Coverage analysis

## Limitations

### Current Implementation
- PR harvesting is placeholder (needs PR wire APIs)
- Abstract harvesting is placeholder (needs conference APIs)
- Stock price integration deferred
- Manual company mapping for edge cases

### Data Quality
- Relies on CT.gov data quality
- SEC filing completeness varies
- Label accuracy depends on document parsing

## Future Enhancements

### Data Sources
- Integrate PR wire APIs (BusinessWire, PR Newswire)
- Add conference abstract databases
- Include academic paper sources
- Expand SEC filing types

### Company Resolution
- Improve fuzzy matching algorithms
- Add subsidiary/merger tracking
- Integrate with company databases
- Handle international companies

### Evaluation
- Add stock price integration
- Implement calibration plots
- Add more sophisticated metrics
- Include economic impact analysis

## Troubleshooting

### Common Issues

1. **No trials found**: Check indication spelling and date ranges
2. **Low coverage**: Verify document harvesting is working
3. **Missing labels**: Check document text quality and parsing
4. **Import errors**: Ensure src/ is in Python path

### Debugging

Enable debug logging:
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
python scripts/universe_pipeline.py --indication "Alzheimer" 2>&1 | tee debug.log
```

Check intermediate files:
```bash
# Verify trials were found
wc -l backtest/universe/trials.jsonl

# Check document harvesting
wc -l backtest/universe/documents.jsonl

# Verify labels were built
wc -l backtest/universe/labels.jsonl
```

## Contributing

When adding new features:

1. Follow the phase-based architecture
2. Add comprehensive logging
3. Include data validation
4. Update configuration files
5. Add tests for new functionality
6. Update this documentation
