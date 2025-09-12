# Development Guide

## Overview

This guide provides developers with the information needed to understand, contribute to, and maintain the CROcashi system.

## Architecture Overview

### Core System Purpose
CROcashi is a **Near-Certain Failure Detector** for US-listed biotech pivotal trials that uses:
- **Signal Detection**: 9 primitive failure signals (S1-S9)
- **Gate Analysis**: 4 failure pattern gates (G1-G4)
- **Bayesian Scoring**: Failure probability calculation
- **Machine Learning**: LLM-based resolution for ambiguous cases

### Key Architecture Principles
1. **Precision-first approach** - few, very high-confidence red flags
2. **Evidence-constrained synthesis** to prevent hallucination
3. **Provenance tracking** for all data transformations
4. **Modular design** with clear separation of concerns

## Repository Structure

```
CROcashi/
├── src/ncfd/           # Main application code
│   ├── signals/        # Signal detection (S1-S9)
│   ├── gates/          # Gate analysis (G1-G4)
│   ├── scoring/        # Bayesian scoring system
│   ├── synthesis/      # Evidence-constrained synthesis
│   ├── extract/        # Document processing & extraction
│   ├── ingest/         # Data ingestion & validation
│   ├── pipeline/       # Workflow orchestration
│   ├── db/            # Database models & migrations
│   └── backtest/      # Evaluation framework
├── alembic/            # Database migrations
├── tests/              # Test suite
├── scripts/            # Validation & demo scripts
├── config/             # Configuration files
└── docs/               # Documentation
```

## Development Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 12+
- Git

### Installation
Or there are make cmds that should do most of this `make setup`
```bash
# Clone repository
git clone <repository-url>
cd CROcashi

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Option 1: Manual setup
pip install -e .

# Option 2: Automated setup (recommended)
python scripts/setup_dev.py

# Set up database
export DATABASE_URL="postgresql://user:pass@localhost/crocashi"
alembic upgrade head
```

### Environment Variables
```bash
# Required
export DATABASE_URL="postgresql://user:pass@localhost/crocashi"
export OPENAI_API_KEY="your-openai-api-key"

# Optional
export LOG_LEVEL="INFO"
export ENVIRONMENT="development"
```

### Import Patterns
After installing the package with `pip install -e .`, use consistent import patterns:

```python
# ✅ Correct: Import from ncfd package
from ncfd.backtest.outcomes import BacktestOutcomes
from ncfd.catalyst.backtest import BacktestRunner
from ncfd.config import get_config

# ❌ Incorrect: Don't use sys.path manipulation
# sys.path.insert(0, 'src')  # Don't do this
# from backtest.outcomes import BacktestOutcomes  # Don't do this
```

**Important**: The package must be installed in development mode (`pip install -e .`) for imports to work correctly. This ensures all scripts and tests can import from the `ncfd` package without manual path manipulation.

## Key Components

### Signal Detection System

#### Primitive Signals (S1-S9)
- **S1**: Endpoint changes post-registration
- **S2**: Underpowered trials
- **S3**: Subgroup-only wins without multiplicity control
- **S4**: ITT vs PP contradictions
- **S5**: Effect size analysis and class priors
- **S6**: Multiple interim looks
- **S7**: Single-arm trials vs RCT standard
- **S8**: P-value cusping
- **S9**: OS/PFS contradictions

#### Implementation Location
```python
# Signal definitions
src/ncfd/signals/signals.py

# Signal evaluation
src/ncfd/signals/evaluator.py

# Signal configuration
config/section_constraints.yaml
```

### Gate Analysis System

#### Failure Pattern Gates (G1-G4)
- **G1 (Alpha-Meltdown)**: S1 + S2 combination
- **G2 (Analysis-Gaming)**: S3 + S4 combination
- **G3 (Plausibility)**: S5 + (S6 | S7) combination
- **G4 (P-hacking)**: S8 + (S1 | S3) combination

#### Implementation Location
```python
# Gate definitions
src/ncfd/gates/gates.py

# Gate evaluation
src/ncfd/gates/evaluator.py

# Gate configuration
config/gate_lrs.yaml
```

### Study Card Architecture

The system uses an LLM-first, provenance-second architecture:

1. **LLM Results Drafter**: Reads raw paper text and extracts results
2. **Provenance Backtracer**: Finds exact spans that justify LLM-extracted values
3. **Results Finalizer**: Merges deterministic and LLM results

#### Implementation Location
```python
# LLM extraction
src/ncfd/extract/workers/llm/llm_results_drafter.py

# Provenance tracking
src/ncfd/extract/workers/provenance_backtracer.py

# Results finalization
src/ncfd/extract/workers/results_finalizer.py
```

### BaseSpan System

Provides auditable, high-recall document processing with sentence-level and table-cell text spans.

#### Implementation Location
```python
# Span generation
src/ncfd/extract/workers/base_span_ingest_worker.py

# Span indexing
src/ncfd/extract/workers/span_indexer.py

# Span triage
src/ncfd/extract/workers/span_triage_worker.py
```

## Database Schema

### Key Tables
- **trials**: Clinical trial information with versioning
- **studies**: Document storage with Study Card JSON
- **signals**: Signal detection results
- **gates**: Gate evaluation results
- **scores**: Bayesian scoring results
- **companies**: Company information and aliases
- **assets**: Asset information and ownership

### Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## Testing

### Running Tests
```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_signals.py

# Run with coverage
python -m pytest tests/ --cov=src/ncfd

# Run specific test
python -m pytest tests/test_signals.py::test_s1_endpoint_changes
```

### Test Structure
- **Unit Tests**: Test individual functions and classes
- **Integration Tests**: Test component interactions
- **End-to-End Tests**: Test complete workflows

### Writing Tests
```python
import pytest
from ncfd.signals.evaluator import SignalEvaluator

def test_s1_endpoint_changes():
    """Test S1 signal detection for endpoint changes."""
    evaluator = SignalEvaluator()
    trial = create_test_trial()
    
    result = evaluator.evaluate_s1(trial)
    
    assert result.fired == True
    assert result.confidence > 0.8
```

## Configuration

### Configuration Files
- `config/core_system_config.yaml` - Core system configuration
- `config/backtest.yaml` - Backtest settings
- `config/ctgov_config.yaml` - CT.gov ingestion
- `config/sec_config.yaml` - SEC filing processing
- `config/gate_lrs.yaml` - Gate likelihood ratios

### Configuration Structure
```yaml
# Example configuration
database:
  url: ${DATABASE_URL}
  pool_size: 10

signals:
  s1:
    enabled: true
    threshold: 0.8
  s2:
    enabled: true
    power_threshold: 0.8

gates:
  g1:
    enabled: true
    likelihood_ratio: 2.5
```

## Code Style

### Python Style Guide
- Follow PEP 8
- Use type hints for all function parameters and return values
- Use docstrings for all public functions and classes
- Keep functions small and focused

### Naming Conventions
- **Classes**: PascalCase (e.g., `SignalEvaluator`)
- **Functions**: snake_case (e.g., `evaluate_signal`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `DEFAULT_THRESHOLD`)
- **Files**: snake_case (e.g., `signal_evaluator.py`)

### Code Organization
```python
# Standard module structure
"""
Module docstring.
"""

from typing import List, Optional
import logging

from .base import BaseEvaluator
from ..models import Trial, SignalResult

logger = logging.getLogger(__name__)

class SignalEvaluator(BaseEvaluator):
    """Signal evaluation class."""
    
    def __init__(self, config: dict):
        """Initialize evaluator."""
        super().__init__(config)
    
    def evaluate(self, trial: Trial) -> SignalResult:
        """Evaluate signals for trial."""
        # Implementation
        pass
```

## Common Patterns

### Database Operations
```python
from sqlalchemy.orm import Session
from ncfd.db.models import Trial, Signal

def get_trial_signals(session: Session, trial_id: str) -> List[Signal]:
    """Get all signals for a trial."""
    return session.query(Signal).filter(Signal.trial_id == trial_id).all()
```

### Configuration Loading
```python
from ncfd.config import load_config

def load_signal_config() -> dict:
    """Load signal configuration."""
    config = load_config()
    return config.get('signals', {})
```

### Logging
```python
import logging

logger = logging.getLogger(__name__)

def process_trial(trial_id: str):
    """Process a trial."""
    logger.info(f"Processing trial {trial_id}")
    try:
        # Processing logic
        logger.debug("Processing completed successfully")
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise
```

## Debugging

### Common Issues

#### Import Errors
```bash
# Check Python path
python -c "import sys; print(sys.path)"

# Install in development mode
pip install -e .
```

#### Database Issues
```bash
# Check database connection
python -c "from ncfd.db import get_session; print('DB OK')"

# Run migrations
alembic upgrade head
```

#### Configuration Issues
```bash
# Check configuration loading
python -c "from ncfd.config import load_config; print(load_config())"
```

### Debug Mode
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable debug logging for specific modules
logging.getLogger('ncfd.signals').setLevel(logging.DEBUG)
```

## Performance Considerations

### Database Optimization
- Use proper indexes for frequently queried fields
- Use batch operations for bulk data processing
- Use connection pooling for database connections

### Memory Management
- Use generators for large data processing
- Clear unused objects from memory
- Monitor memory usage with profiling tools

### Caching
- Cache frequently accessed data
- Use Redis for distributed caching
- Implement cache invalidation strategies

## Security

### Input Validation
- Validate all user inputs
- Use parameterized queries for database operations
- Sanitize data before processing

### Error Handling
- Don't expose sensitive information in error messages
- Log errors for debugging but don't expose internals
- Use proper exception handling

### Access Control
- Implement proper authentication and authorization
- Use environment variables for sensitive configuration
- Validate API keys and tokens

## Contributing

### Development Workflow
1. Create feature branch from main
2. Implement changes with tests
3. Run full test suite
4. Update documentation
5. Submit pull request

### Pull Request Checklist
- [ ] All tests pass
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] Configuration changes documented
- [ ] Migration scripts included if needed

### Code Review Guidelines
- Review for correctness and completeness
- Check for security issues
- Verify performance implications
- Ensure proper error handling
- Validate configuration changes

## Resources

### Documentation
- [User Guide](USER_GUIDE.md)
- [Architecture Overview](LLM_FIRST_ARCHITECTURE.md)
- [Production Status](PRODUCTION_STATUS.md)

### External Resources
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Pytest Documentation](https://docs.pytest.org/)

---

**Last Updated**: January 2025
