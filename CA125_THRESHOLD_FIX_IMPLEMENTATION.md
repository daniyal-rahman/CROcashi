# CA-125 Threshold Fix Implementation

## Problem Statement

The issue was that CA-125 "50% reduction" patterns in Methods sections were being incorrectly captured as `response_rate` claims instead of being recognized as assay threshold definitions.

**Root cause**: Claimizer treated an endpoint definition as an effect size.

## Implemented Fixes

### Fix A: Schema Mapping in Claimizer

**Location**: `src/ncfd/extract/workers/llm/claimizer.py`

**Changes**:
1. Added special handling for CA-125 threshold patterns in Methods sections
2. When pattern matches `CA[- ]?125 … (50% reduction|≥50% decline)` in Methods, the system now:
   - Emits `Claim.type = methods_detail` (or `assay_threshold`)
   - Sets `endpoint = assay_threshold`
   - Stores threshold information: `{name: "CA-125", op: "≥", value: 50, units: "percent"}`
   - **Does NOT create a response_rate claim**

**Pattern Detection**:
```python
ca125_threshold_patterns = [
    (r'CA[- ]?125.*?(?:defined as|threshold|≥|>=)\s*(\d+\.?\d*)\s*%', 'ca125_threshold'),
    (r'CA[- ]?125.*?(?:50%|50\s*percent)\s*(?:reduction|decline)', 'ca125_threshold'),
]
```

**Skip Logic**: Added logic to skip creating `response_rate` claims when CA-125 threshold patterns are detected.

### Fix B: Validator Guardrail

**Location**: `src/ncfd/extract/validators/validator_utils.py`

**Changes**:
1. Enhanced `MethodCardValidator.validate()` to accept optional `spans` parameter
2. Added `_validate_ca125_thresholds()` method that:
   - Checks if any Methods spans include CA-125 AND % AND "reduction/decline"
   - Asserts that `MethodCard.assay_thresholds` contains a CA-125 threshold
   - If not, raises a critical validation error with span IDs

3. Added `auto_lift_ca125_thresholds()` method that:
   - Automatically lifts CA-125 threshold definitions from Methods spans to `assay_thresholds`
   - Extracts threshold value, units, and rationale
   - Adds proper provenance tracking
   - Prevents duplicates

**Validation Rule**:
```python
# If we found CA-125 threshold definitions in Methods, check if they're captured in assay_thresholds
if ca125_methods_spans:
    assay_thresholds = method_dict.get('assay_thresholds', [])
    ca125_thresholds = [t for t in assay_thresholds if 'ca-125' in str(t).lower() or 'ca125' in str(t).lower()]
    
    if not ca125_thresholds:
        # Auto-lift the threshold definition to assay_thresholds
        span_ids = [span.span_id for span in ca125_methods_spans if hasattr(span, 'span_id')]
        errors.append(f"CRITICAL: CA-125 threshold definition found in Methods spans {span_ids} but not captured in assay_thresholds. Auto-lift required.")
```

## Testing

Created comprehensive test suite in `tests/test_ca125_threshold_fix.py` that verifies:

1. **Correct Claim Type**: CA-125 threshold definitions create `methods_detail` claims, not `response_rate`
2. **No Duplicate Claims**: CA-125 threshold patterns don't create both threshold and response rate claims
3. **Validator Detection**: Validator correctly identifies missing CA-125 thresholds
4. **Auto-Lift Functionality**: Auto-lift correctly adds CA-125 thresholds to MethodCard
5. **Validation Pass**: Validation passes when CA-125 threshold already exists
6. **No Duplicates**: Auto-lift doesn't create duplicate thresholds

## Usage

### Manual Auto-Lift
```python
from src.ncfd.extract.validators.validator_utils import MethodCardValidator

# Auto-lift CA-125 thresholds from spans to MethodCard
lifted = MethodCardValidator.auto_lift_ca125_thresholds(method_card, spans)
if lifted:
    print("CA-125 thresholds auto-lifted successfully")
```

### Validation with Spans
```python
# Validate MethodCard with span context for CA-125 threshold checking
is_valid, errors = MethodCardValidator.validate(method_card, spans)
```

## Impact

- **Prevents Misclassification**: CA-125 threshold definitions are no longer misclassified as response rates
- **Ensures Completeness**: Validator ensures CA-125 thresholds are properly captured in MethodCard
- **Maintains Backward Compatibility**: Existing functionality remains unchanged
- **Provides Auto-Recovery**: Auto-lift functionality can recover from missed threshold definitions

## Files Modified

1. `src/ncfd/extract/workers/llm/claimizer.py` - Added CA-125 threshold pattern detection
2. `src/ncfd/extract/validators/validator_utils.py` - Added validation and auto-lift functionality
3. `tests/test_ca125_threshold_fix.py` - Comprehensive test suite (new file)

## Validation Results

All tests pass:
- ✅ Original PMC2978916 E2E test still passes
- ✅ All 6 CA-125 threshold fix tests pass
- ✅ No regressions introduced
