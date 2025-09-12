# CROcashi - Clinical Research Organization Cash Investment

## Overview

CROcashi is a **Near-Certain Failure Detector** for US-listed biotech pivotal trials. The system uses signal detection, gate analysis, and Bayesian scoring to identify high-risk clinical trials for investment decisions.

## Current Status

**Production Readiness**: **75% Complete** ✅

### ✅ **Fully Implemented**
- **Core Infrastructure**: Database schema, migrations, ORM models
- **Signal Detection**: 9 primitive failure signals (S1-S9)
- **Gate Analysis**: 4 failure pattern gates (G1-G4)
- **Scoring System**: Bayesian framework with likelihood ratios
- **Backtest System**: Comprehensive evaluation framework
- **Study Card Architecture**: LLM-first extraction with provenance tracking
- **BaseSpan System**: Auditable document processing foundation

### ⚠️ **Needs Attention**
- **Monitoring & Alerting**: Placeholder implementations need real alerting
- **Configuration**: Many placeholder values need calibration
- **Error Handling**: Retry logic and circuit breakers missing
- **API Layer**: No REST API implementation
- **Patent System**: Not implemented

## Architecture

### Core Components
```
src/ncfd/
├── signals/        # Signal detection (S1-S9)
├── gates/          # Gate analysis (G1-G4)
├── scoring/        # Bayesian scoring system
├── synthesis/      # Evidence-constrained synthesis
├── extract/        # Document processing & extraction
├── ingest/         # Data ingestion & validation
├── pipeline/       # Workflow orchestration
├── db/            # Database models & migrations
└── backtest/      # Evaluation framework
```

### Key Technologies
- **Python 3.11+** with modern type hints
- **PostgreSQL** with Alembic migrations
- **SQLAlchemy** ORM with async support
- **OpenAI/LLM** for intelligent resolution
- **Docker** for deployment

## Quick Start

### Prerequisites
- PostgreSQL database
- Python 3.11+
- OpenAI API key (for GPT-5 integration)

### Installation
```bash
# Clone repository
git clone <repository-url>
cd CROcashi

# Install dependencies
pip install -e .

# Set up database
export DATABASE_URL="postgresql://user:pass@localhost/crocashi"
alembic upgrade head

# Run tests
python -m pytest tests/
```

### Basic Usage
```bash
# Run backtest
python scripts/backtest.py --stage all --config config/backtest.yaml

# Run synthesis
python scripts/synthesize.py --trial-id trial_001

# Run GPT-5 analysis
python scripts/gpt5_analysis.py --trial-id trial_001
```

## Signal Detection System

### Primitive Signals (S1-S9)
- **S1**: Endpoint changes post-registration
- **S2**: Underpowered trials
- **S3**: Subgroup-only wins without multiplicity control
- **S4**: ITT vs PP contradictions
- **S5**: Effect size analysis and class priors
- **S6**: Multiple interim looks
- **S7**: Single-arm trials vs RCT standard
- **S8**: P-value cusping
- **S9**: OS/PFS contradictions

### Failure Pattern Gates (G1-G4)
- **G1 (Alpha-Meltdown)**: S1 + S2 combination
- **G2 (Analysis-Gaming)**: S3 + S4 combination
- **G3 (Plausibility)**: S5 + (S6 | S7) combination
- **G4 (P-hacking)**: S8 + (S1 | S3) combination

## Configuration

The system uses multiple configuration files:
- `config/core_system_config.yaml` - Core system configuration
- `config/backtest.yaml` - Backtest settings
- `config/ctgov_config.yaml` - CT.gov ingestion
- `config/sec_config.yaml` - SEC filing processing

## Testing

```bash
# Run all tests
python -m pytest tests/

# Run specific test categories
python -m pytest tests/test_signals.py
python -m pytest tests/test_gates.py
python -m pytest tests/test_backtest_outcomes.py
```

## Documentation

- [User Guide](USER_GUIDE.md) - Comprehensive usage guide
- [Architecture Overview](LLM_FIRST_ARCHITECTURE.md) - System architecture
- [Study Card System](Study_card_overhall.md) - Study card implementation
- [BaseSpan System](BASESPAN_SYSTEM.md) - Document processing foundation

## Contributing

1. Follow the existing code style and patterns
2. Add tests for new functionality
3. Update documentation for significant changes
4. Ensure all tests pass before submitting

## License

[Add license information here]
