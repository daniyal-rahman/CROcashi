# Logging Migration Guide

This guide explains how to migrate from the old logging system to the new comprehensive structured logging system.

## Overview

The new logging system provides:
- **Structured logging** with comprehensive schema
- **Canonical event taxonomy** for consistent event naming
- **IO tracing decorators** for boundary logging
- **Context management** for execution tracking
- **LLM-specific logging** with cost tracking
- **Decision transparency logging** for auditability

## Quick Migration

### 1. Update Imports

**Old:**
```python
import logging
logger = logging.getLogger(__name__)
```

**New:**
```python
from ncfd.logging import get_logger, EventTaxonomy
logger = get_logger(__name__)
```

### 2. Replace Basic Logging

**Old:**
```python
logger.info("Processing trial")
logger.error(f"Failed to process {trial_id}")
logger.warning("Rate limit hit")
```

**New:**
```python
logger.info(
    EventTaxonomy.CTGOV_FETCH_START,
    "Processing trial",
    nct_id=trial_id
)
logger.error(
    EventTaxonomy.CTGOV_FETCH_ERROR,
    f"Failed to process {trial_id}",
    nct_id=trial_id,
    err_type="ProcessingError"
)
logger.warn(
    EventTaxonomy.PUBMED_EFETCH_ERROR,
    "Rate limit hit",
    err_type="RateLimitError",
    retry_in_s=60
)
```

### 3. Add Context Management

**Old:**
```python
def process_trial(trial_id):
    logger.info(f"Starting trial {trial_id}")
    # ... work ...
    logger.info(f"Completed trial {trial_id}")
```

**New:**
```python
from ncfd.logging import LogContext

def process_trial(trial_id):
    with LogContext(run_id="r_123", task_id=f"trial_{trial_id}"):
        logger.info(
            EventTaxonomy.TASK_STARTED,
            f"Starting trial {trial_id}",
            nct_id=trial_id
        )
        # ... work ...
        logger.info(
            EventTaxonomy.TASK_COMPLETED,
            f"Completed trial {trial_id}",
            nct_id=trial_id
        )
```

### 4. Add IO Tracing

**Old:**
```python
def call_llm(prompt, settings):
    # ... LLM call ...
    return result
```

**New:**
```python
from ncfd.logging import llm_trace

@llm_trace(name="llm.synthesize.study_card", capture_args=("prompt", "settings"))
def call_llm(prompt, settings):
    # ... LLM call ...
    return result
```

### 5. Add Performance Logging

**Old:**
```python
start_time = time.time()
# ... work ...
duration = time.time() - start_time
logger.info(f"Operation took {duration:.2f}s")
```

**New:**
```python
start_time = time.time()
# ... work ...
duration_ms = int((time.time() - start_time) * 1000)
logger.log_performance(
    EventTaxonomy.CTGOV_FETCH_DONE,
    duration_ms=duration_ms,
    processed_n=count,
    success_n=success_count,
    fail_n=fail_count
)
```

## Event Taxonomy

Use canonical event names from `EventTaxonomy`:

### Ingestion Events
- `EventTaxonomy.CTGOV_FETCH_START/DONE/ERROR`
- `EventTaxonomy.PUBMED_SEARCH_START/DONE/ERROR`
- `EventTaxonomy.PUBMED_EFETCH_START/DONE/ERROR`
- `EventTaxonomy.PMC_FULLTEXT_FETCH_START/DONE/MISS/ERROR`

### Processing Events
- `EventTaxonomy.STUDY_CARD_BUILD_DONE/PARTIAL/ERROR`
- `EventTaxonomy.NLP_EXTRACT_ENTITIES_DONE/ERROR`
- `EventTaxonomy.EVIDENCE_LINKED_DONE/ERROR`

### Decision Events
- `EventTaxonomy.GATE_EVALUATE_DONE/ERROR`
- `EventTaxonomy.SIGNAL_EVALUATE_START/DONE/ERROR`

### LLM Events
- `EventTaxonomy.LLM_CALL_START/DONE/ERROR`

### System Events
- `EventTaxonomy.TASK_STARTED/COMPLETED/FAILED`
- `EventTaxonomy.FLOW_STATE_TRANSITION`
- `EventTaxonomy.RUN_SUMMARY`

## Specialized Logging Methods

### LLM Logging
```python
logger.log_llm_call(
    EventTaxonomy.LLM_CALL_DONE,
    model="gpt-4",
    input_tokens=1250,
    output_tokens=320,
    usd_cost=0.024,
    duration_ms=2100,
    prompt_id="study_card_generation_v2"
)
```

### Decision Logging
```python
logger.log_decision(
    EventTaxonomy.GATE_EVALUATE_DONE,
    decision="fail",
    confidence=0.86,
    why="Dropout>20% and ≥4 amendments in pivotal phase.",
    features={"arm_dropout_pct": 27.3, "amendments_n": 5},
    thresholds={"arm_dropout_pct": 20, "amendments_n": 4},
    evidence_refs=[["doc_812", "PMID:38900123", [14235, 14512]]],
    gate_id="G2_protocol_integrity",
    nct_id="NCT05515666"
)
```

### Error Logging
```python
try:
    # ... risky operation ...
except Exception as e:
    logger.log_error_with_context(
        EventTaxonomy.CTGOV_FETCH_ERROR,
        error=e,
        context={
            "nct_id": trial_id,
            "query_params": params,
            "retry_count": retry_count
        },
        suggested_action="Check trial data format and retry"
    )
```

## IO Tracing Configuration

Set environment variables for IO tracing:

```bash
# Trace mode: off|errors|sample:0.05|all
export IO_TRACE=errors

# Include/exclude patterns
export TRACE_INCLUDE="ncfd.llm.,ncfd.ingest.,ncfd.extract."
export TRACE_EXCLUDE="ncfd.ingest.ctgov.raw_xml"

# Store full payloads for debugging
export IO_TRACE_BLOBS=on
export IO_TRACE_BLOB_DIR="/tmp/ncfd_io_blobs"
```

## Configuration Updates

Update your configuration files to use the new logging settings:

```yaml
logging:
  # Basic configuration
  level: INFO
  json_format: true
  console: true
  log_file: "logs/ncfd_pipeline.log"
  
  # Structured logging
  enable_structured_logging: true
  enforce_event_taxonomy: true
  include_context: true
  
  # IO tracing
  io_trace_mode: "errors"
  io_trace_blobs: false
  io_trace_include: ["ncfd.llm.", "ncfd.ingest.", "ncfd.extract."]
  
  # LLM logging
  enable_llm_cost_tracking: true
  enable_llm_token_tracking: true
  
  # Decision transparency
  enable_decision_logging: true
  include_evidence_refs: true
```

## Migration Checklist

- [ ] Update imports to use new logging system
- [ ] Replace basic logging calls with structured logging
- [ ] Add canonical event names from EventTaxonomy
- [ ] Add context management for execution tracking
- [ ] Add IO tracing decorators to critical functions
- [ ] Add performance logging with duration and counts
- [ ] Add LLM-specific logging for cost tracking
- [ ] Add decision transparency logging for gates/signals
- [ ] Update configuration files
- [ ] Remove print statements and replace with proper logging
- [ ] Test logging output format and completeness

## Examples

See `src/ncfd/logging/examples.py` for comprehensive examples of all logging patterns.

## Benefits

The new logging system provides:

1. **Instant Answers**: Every log line answers what ran, on which data, with which code/config, what decisions were made (and why), how long/costly it was, and where it broke.

2. **Dashboard Ready**: Structured JSON logs with consistent event names make dashboard creation easy.

3. **Audit Trail**: Decision transparency with evidence references and reasoning chains.

4. **Cost Tracking**: LLM usage and costs are automatically tracked.

5. **Error Context**: Errors include full context and suggested actions.

6. **Performance Monitoring**: Duration and throughput metrics are automatically captured.

7. **Reproducibility**: Git info, system info, and configuration hashes are automatically included.

8. **IO Tracing**: Safe, cheap, and findable logging of function inputs/outputs at boundaries.
