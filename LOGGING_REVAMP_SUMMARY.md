# Logging System Revamp - Complete Implementation

## Overview

I have completely revamped the logging system for CROcashi/NCFD following the comprehensive guidance provided. The new system provides structured logging with comprehensive schema, canonical event taxonomy, IO tracing, context management, and specialized logging for LLM operations and decision transparency.

## What Was Implemented

### 1. Core Structured Logging System (`src/ncfd/logging/`)

#### Schema (`schema.py`)
- **LogRecord**: Comprehensive log record schema with all required fields
- **LLMLogRecord**: Specialized for LLM operations with cost tracking
- **DecisionLogRecord**: Specialized for decision-making with transparency
- **IOTraceRecord**: Specialized for IO tracing operations
- **LogLevel**: Standardized log levels (DEBUG, INFO, WARN, ERROR)
- **Outcome**: Task execution outcomes (success, fail, partial)

#### Event Taxonomy (`event_taxonomy.py`)
- **Canonical event names** for all pipeline stages:
  - Ingestion: `ctgov.fetch.*`, `pubmed.search.*`, `pubmed.efetch.*`
  - Processing: `study_card.build.*`, `nlp.extract.*`
  - Decisions: `gate.evaluate.*`, `signal.evaluate.*`
  - LLM: `llm.call.*`
  - System: `task.*`, `flow.state.*`, `run.summary`
- **Event validation** and categorization
- **Consistent naming** for dashboard creation and alerting

#### Context Management (`context.py`)
- **Context variables** for automatic inclusion in logs:
  - `run_id`, `flow_id`, `task_id`, `attempt`
  - `code_version`, `git_dirty`, `docker_image`, `py_version`, `env`
- **LogContext** manager for execution tracking
- **Automatic git info** and system info inclusion
- **Context threading** through execution flow

#### IO Tracing (`io_trace.py`)
- **Safe boundary logging** with redaction
- **Configurable sampling** (off|errors|sample:0.05|all)
- **Include/exclude patterns** for selective tracing
- **Blob storage** for full payloads (debug mode)
- **Specialized decorators**: `@llm_trace`, `@parse_trace`, `@validate_trace`
- **Hash-based correlation** for debugging

#### Structured Logger (`structured_logger.py`)
- **JSON output** with comprehensive schema
- **Specialized logging methods**:
  - `log_llm_call()` for LLM operations with cost tracking
  - `log_decision()` for decision transparency
  - `log_performance()` for metrics
  - `log_error_with_context()` for actionable errors
- **Automatic context inclusion**
- **Event validation**

### 2. Configuration Updates

#### Core System Config (`config/core_system_config.yaml`)
- **Structured logging configuration**
- **IO tracing settings**
- **LLM cost tracking**
- **Decision transparency**
- **Performance monitoring**

#### Migration Guide (`docs/LOGGING_MIGRATION_GUIDE.md`)
- **Step-by-step migration** instructions
- **Code examples** for all patterns
- **Event taxonomy reference**
- **Configuration examples**
- **Migration checklist**

### 3. Code Improvements

#### CT.gov Client (`src/ncfd/ingest/ctgov.py`)
- **Replaced print statements** with structured logging
- **Added canonical event names**
- **Included trial context** (nct_id, phase, status)
- **Performance metrics** logging

#### PubMed Client (`src/ncfd/ingest/pubmed/client.py`)
- **Comprehensive structured logging** for all operations
- **Rate limiting and error handling** with context
- **Performance tracking** with duration and counts
- **Circuit breaker monitoring**
- **Retry logic** with structured error reporting

#### Worker Updates (`workers/pubmed_u1_worker.py`)
- **Structured logging setup**
- **Context management** for execution tracking
- **Error handling** with actionable context
- **Configuration validation** logging

### 4. Legacy Support

#### Deprecated Module (`src/ncfd/logging.py`)
- **Backward compatibility** with deprecation warnings
- **Automatic migration** to new system
- **Gradual transition** support

## Key Features

### 1. Comprehensive Schema
Every log line now carries:
- **Core identification**: timestamp, level, module, event
- **Execution context**: run_id, flow_id, task_id, attempt, duration, outcome
- **Code/config versioning**: git SHA, docker image, python version, config hash
- **Data identifiers**: nct_id, trial_id, doc_id, pmid, pmcid, doi, etc.
- **Performance metrics**: processed_n, success_n, fail_n, latency_ms, cache_hit
- **Error information**: err_type, err_msg, stack, root_cause, retry_in_s
- **LLM metrics**: model, tokens, cost, temperature, truncation
- **Decision transparency**: rule_id, features, thresholds, decision, confidence, why, evidence_refs

### 2. Decision Transparency
For Signals/Gates, every log includes:
- **Inputs** (features actually used)
- **Rule ID/version**
- **Thresholds** applied
- **Decision** made
- **Confidence** score
- **Why** (one sentence explanation)
- **Evidence references** with document IDs and character ranges

### 3. LLM Cost Tracking
- **Model, provider, API mode**
- **Input/output tokens**
- **USD cost**
- **Caching status**
- **Truncation flags**
- **Latency metrics**

### 4. IO Tracing
- **Safe, cheap, and findable** boundary logging
- **Redaction** for sensitive information
- **Sampling** and pattern filtering
- **Blob storage** for full payloads (debug mode)
- **Hash-based correlation**

### 5. Error Handling
- **Actionable errors** with suggested actions
- **Full context** and stack traces
- **Root cause** identification
- **Retry information**

## Benefits

### 1. Instant Answers
Every log line answers:
- **What ran** (event, module)
- **On which data** (nct_id, pmid, etc.)
- **With which code/config** (git SHA, config hash)
- **What decisions were made** (decision, confidence, why)
- **How long/costly it was** (duration_ms, usd_cost)
- **Where it broke** (err_type, err_msg, stack)

### 2. Dashboard Ready
- **Structured JSON** logs
- **Consistent event names**
- **Easy aggregation** and alerting
- **Performance monitoring**

### 3. Audit Trail
- **Decision transparency** with evidence references
- **LLM cost tracking**
- **Reproducibility** with git info and config hashes
- **Error context** with suggested actions

### 4. Development Efficiency
- **IO tracing** for debugging
- **Context management** for execution tracking
- **Specialized logging methods** for common patterns
- **Migration guide** for easy adoption

## Usage Examples

### Basic Structured Logging
```python
from ncfd.logging import get_logger, EventTaxonomy

logger = get_logger(__name__)
logger.info(
    EventTaxonomy.CTGOV_FETCH_START,
    "Starting CT.gov fetch",
    nct_id="NCT05515666",
    query="cassava therapeutics"
)
```

### LLM Call Logging
```python
logger.log_llm_call(
    EventTaxonomy.LLM_CALL_DONE,
    model="gpt-4",
    input_tokens=1250,
    output_tokens=320,
    usd_cost=0.024,
    duration_ms=2100
)
```

### Decision Transparency
```python
logger.log_decision(
    EventTaxonomy.GATE_EVALUATE_DONE,
    decision="fail",
    confidence=0.86,
    why="Dropout>20% and ≥4 amendments in pivotal phase.",
    features={"arm_dropout_pct": 27.3, "amendments_n": 5},
    evidence_refs=[["doc_812", "PMID:38900123", [14235, 14512]]]
)
```

### IO Tracing
```python
from ncfd.logging import llm_trace

@llm_trace(name="llm.synthesize.study_card", capture_args=("prompt", "settings"))
def synthesize_study_card(prompt, settings):
    # LLM call with automatic IO tracing
    return result
```

### Context Management
```python
from ncfd.logging import LogContext

with LogContext(run_id="r_123", task_id="trial_001"):
    # All logs automatically include context
    logger.info(EventTaxonomy.TASK_STARTED, "Starting task")
```

## Configuration

### Environment Variables
```bash
# IO tracing
export IO_TRACE=errors  # off|errors|sample:0.05|all
export TRACE_INCLUDE="ncfd.llm.,ncfd.ingest.,ncfd.extract."
export IO_TRACE_BLOBS=on
export IO_TRACE_BLOB_DIR="/tmp/ncfd_io_blobs"
```

### YAML Configuration
```yaml
logging:
  level: INFO
  json_format: true
  enable_structured_logging: true
  enforce_event_taxonomy: true
  io_trace_mode: "errors"
  enable_llm_cost_tracking: true
  enable_decision_logging: true
```

## Migration Status

✅ **Completed**:
- Core structured logging system
- Event taxonomy definition
- IO tracing implementation
- Context management
- Configuration updates
- Code improvements (CT.gov, PubMed client, workers)
- Migration guide and examples
- Legacy support with deprecation warnings

🔄 **Next Steps**:
- Migrate remaining modules to use new logging system
- Update test files to use structured logging
- Add monitoring dashboards based on structured logs
- Implement log aggregation and alerting

## Files Created/Modified

### New Files
- `src/ncfd/logging/__init__.py`
- `src/ncfd/logging/schema.py`
- `src/ncfd/logging/event_taxonomy.py`
- `src/ncfd/logging/context.py`
- `src/ncfd/logging/io_trace.py`
- `src/ncfd/logging/structured_logger.py`
- `src/ncfd/logging/examples.py`
- `docs/LOGGING_MIGRATION_GUIDE.md`

### Modified Files
- `src/ncfd/logging.py` (deprecated with warnings)
- `src/ncfd/ingest/ctgov.py` (improved logging)
- `src/ncfd/ingest/pubmed/client.py` (comprehensive structured logging)
- `workers/pubmed_u1_worker.py` (structured logging setup)
- `config/core_system_config.yaml` (logging configuration)

The logging system is now ready for production use and provides comprehensive observability for the entire NCFD pipeline.
