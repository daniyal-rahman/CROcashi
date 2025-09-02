# Denominator Resolver Interface Fix

This directory contains the solution for the denominator resolver divergence issue identified in the study card architecture.

## Problem

Two denominator resolvers existed with potentially divergent interfaces:
- `extract/workers/denominator_resolver.py` (deterministic)
- `extract/workers/llm/denominator_resolver.py` (LLM assist)

Risk: codepaths drift; one returns shape A, the other shape B.

## Solution

### 1. Unified Interface (`IDenominatorResolver`)

Created `interfaces/denominator_resolver.py` with:
- **`IDenominatorResolver`** abstract base class defining common interface
- **`DenominatorResult`** standardized data structure for all resolvers
- **`create_denominator_resolver()`** factory function for strategy selection

### 2. Standardized Data Schema

Both resolvers now return `DenominatorResult` with:
```python
@dataclass
class DenominatorResult:
    # Denominator values
    response_n: Optional[int] = None
    ttp_os_n: Optional[int] = None
    safety_n: Optional[int] = None
    treated_n: Optional[int] = None
    itt_n: Optional[int] = None
    per_protocol_n: Optional[int] = None
    
    # Span provenance
    response_n_span_ids: List[str] = None
    ttp_os_n_span_ids: List[str] = None
    # ... (all span ID lists)
    
    # Confidence and metadata
    confidence_scores: Dict[str, float] = None
    patterns_used: Dict[str, str] = None
```

### 3. Consistent Interface Methods

All resolvers implement:
- `process(inputs) -> WorkerResult`
- `get_method_card_denominators(inputs) -> Dict[str, Any]`
- `attach_denominators_to_factsheet(factsheet_data, inputs) -> Tuple[bool, List[str]]`
- `validate_denominator_consistency(inputs, factsheet_data) -> Dict[str, Any]`

## Usage

### Factory Pattern (Recommended)

```python
from src.ncfd.extract.workers import create_denominator_resolver

# Create deterministic resolver
resolver = create_denominator_resolver("deterministic")

# Create LLM resolver  
resolver = create_denominator_resolver("llm")

# Both have the same interface
result = resolver.process(inputs)
denominators = result.output["denominators"]  # DenominatorResult
method_card_format = denominators.get_method_card_format()
```

### Direct Import

```python
from src.ncfd.extract.workers.interfaces.denominator_resolver import IDenominatorResolver
from src.ncfd.extract.workers.denominator_resolver import DenominatorResolver
from src.ncfd.extract.workers.llm.denominator_resolver import DenominatorResolver as LLMDenominatorResolver

# Both implement IDenominatorResolver
det_resolver: IDenominatorResolver = DenominatorResolver()
llm_resolver: IDenominatorResolver = LLMDenominatorResolver()
```

## Input Format

Both resolvers accept standardized inputs:

```python
inputs = {
    "evidence_spans": List[EvidenceSpan],  # For LLM resolver
    "doc_id": Optional[int],               # For deterministic resolver (database lookup)
    "trial_context": Optional[Dict]        # Additional context
}
```

## Output Format

Both resolvers return `WorkerResult` with consistent structure:

```python
{
    "denominators": DenominatorResult,     # Standardized result object
    "processed_spans": int,                # Number of spans processed
    "extracted_denominators": int,         # Count of denominators found
    "metadata": Dict[str, Any]             # Strategy-specific metadata
}
```

## Late-Fusion Compatibility

The interface ensures late-fusion components receive consistent schema regardless of which resolver strategy is used. The factory pattern allows runtime strategy selection without changing downstream code.

## Testing

Run the interface compliance tests:

```bash
python -m pytest tests/test_denominator_resolver_interface.py -v
```

All tests verify:
- Factory creates correct resolver types
- Both resolvers implement the same interface methods
- Output schemas are consistent between strategies
- DenominatorResult methods work correctly
