# Problem 1 Implementation Guide

## Overview

This document explains the solution implemented for **Problem 1**: fixing the resolver cascade flow and ensuring all decisions generate training data for the probabilistic model.

## Problem Description

**Before the fix:**
- The LLM pathway was bypassing deterministic and probabilistic resolvers when enabled
- LLM decisions were not generating training data for the probabilistic model
- The resolver was inefficient and missing opportunities for deterministic/probabilistic resolution

**After the fix:**
- All three resolver functions now follow a proper cascade: Deterministic → Probabilistic → LLM
- Every trial processed generates training data regardless of the decision path
- LLM is only used when probabilistic resolution is uncertain

## What Was Changed

### 1. Modified `resolve_one()` Function

**File**: `ncfd/src/ncfd/mapping/cli.py`

**Changes Made**:
- **Before**: LLM bypassed deterministic and probabilistic when enabled
- **After**: Always tries deterministic first, then probabilistic, then LLM only if needed

**Key Logic**:
```python
# Step 1: Always try deterministic first
det = det_resolve(s, sponsor)

# Step 2: Always try probabilistic (regardless of decider)
scored = score_candidates(cands, sponsor, weights, intercept, context=ctx)
prob_decision = decide_probabilistic(scored, th["tau_accept"], th["review_low"], th["min_top2_margin"])

# Step 3: If probabilistic hits accept, use it (regardless of decider)
if prob_decision.mode == "accept":
    # Use probabilistic decision
    return

# Step 4: If probabilistic didn't accept, check if we should use LLM
use_llm = _llm_enabled(decider)
if not use_llm:
    # Use probabilistic decision (review/reject)
    return

# Step 5: LLM path (only if probabilistic didn't accept and LLM is enabled)
llm_dec = decide_with_llm(...)
```

### 2. Modified `resolve_nct()` Function

**File**: `ncfd/src/ncfd/mapping/cli.py`

**Changes Made**:
- Same cascade logic as `resolve_one()`
- Ensures all trials generate training data

### 3. Modified `resolve_batch()` Function

**File**: `ncfd/src/ncfd/mapping/cli.py`

**Changes Made**:
- Same cascade logic applied to batch processing
- Each trial in the batch follows the same flow

## How the New Cascade Works

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        RESOLVER CASCADE                        │
└─────────────────────────────────────────────────────────────────┘

Step 1: Deterministic Resolution
├── Try exact alias/company/domain matches
├── Try rule-based regex patterns  
└── If match found → ACCEPT and return

Step 2: Probabilistic Resolution (ALWAYS)
├── Extract features and score candidates
├── Apply trained model weights
└── Check against thresholds

Step 3: Decision Logic
├── If probabilistic hits ACCEPT threshold → Use probabilistic decision
├── If probabilistic doesn't accept AND LLM disabled → Use probabilistic decision
└── If probabilistic doesn't accept AND LLM enabled → Try LLM

Step 4: LLM Resolution (Only if needed)
├── Use LLM to evaluate candidates
├── Make final decision
└── Persist all data for training
```

### Threshold Logic

The probabilistic model uses these thresholds (from `config/resolver.yaml`):
- **`tau_accept`**: 0.90 - Score needed for automatic acceptance
- **`review_low`**: 0.60 - Minimum score to go to review instead of reject
- **`min_top2_margin`**: 0.05 - Minimum margin between top 2 candidates

### Decision Paths

1. **Deterministic ACCEPT** (p = 1.0)
   - Exact matches via aliases, company names, or domains
   - Bypasses probabilistic scoring
   - Still generates training data

2. **Probabilistic ACCEPT** (p ≥ 0.90)
   - High-confidence model predictions
   - Full feature vector available for training

3. **Probabilistic REVIEW** (0.60 ≤ p < 0.90)
   - Moderate confidence, needs human review
   - Full feature vector available for training

4. **LLM ACCEPT** (p = 1.0, confidence from LLM)
   - Used when probabilistic is uncertain
   - Features from probabilistic scoring + LLM decision
   - Full training data available

## Usage Examples

### 1. Auto Mode (Recommended)

```bash
# Resolve single trial with cascade
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT01234567 --persist --apply-trial

# Resolve single sponsor string
PYTHONPATH=src python -m ncfd.mapping.cli resolve-one "AstraZeneca" --persist --nct NCT01234567

# Batch processing
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --limit 25 --persist --apply-trial
```

### 2. Human Mode

```bash
# Uses cascade but marks decisions as human-reviewed
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT01234567 --persist --apply-trial --decider human

# Batch with human decider
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --limit 25 --persist --apply-trial --decider human
```

### 3. LLM Mode

```bash
# Uses cascade, LLM gets final say if probabilistic uncertain
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT01234567 --persist --apply-trial --decider llm

# Batch with LLM decider
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --limit 25 --persist --apply-trial --decider llm
```

### 4. Using Makefile Targets

```bash
# Activate environment
source .venv/bin/activate
make reup

# Single resolution
make resolve-one SPONSOR="AstraZeneca"

# Batch processing
make resolve-batch

# Review queue management
make review-list
make review-show RQ=123
make review-accept RQ=123 CID=6968 APPLY=1
```

## Training Data Flow

### What Gets Stored

**Every trial processed now generates training data:**

1. **`resolver_features`**: Feature vectors for all candidates
2. **`resolver_decisions`**: Final decision outcomes
3. **`review_queue`**: Trials needing human review

### Training Data Sources

**Before**: Only human decisions and probabilistic decisions
**After**: All decision types generate training data:

- **Human decisions**: Gold standard labels
- **LLM decisions**: AI-generated labels  
- **Deterministic decisions**: Rule-based labels
- **Probabilistic decisions**: Model-based labels

### Export for Training

The training export script now has access to much more comprehensive data:

```sql
-- This query will now return more data due to the cascade
SELECT 
    d.nct_id,
    d.company_id,
    (d.match_type LIKE '%accept%')::int AS y,
    f.features_jsonb->>'jw_primary' AS jw_primary,
    f.features_jsonb->>'token_set_ratio' AS token_set_ratio,
    -- ... other features
    d.decided_by,  -- Shows which path made the decision
    d.match_type   -- Shows the decision type
FROM resolver_decisions d 
JOIN resolver_features f USING (nct_id, company_id);
```

## Configuration

### Resolver Configuration

**File**: `config/resolver.yaml`

```yaml
model:
  intercept: -5.0
  weights:
    jw_primary: 2.8
    token_set_ratio: 2.4
    acronym_exact: 1.9
    domain_root_match: 3.6
    # ... other weights

thresholds:
  tau_accept: 0.90        # Score needed for automatic acceptance
  review_low: 0.60        # Minimum score to go to review
  min_top2_margin: 0.05   # Minimum margin between top 2
```

### Environment Variables

```bash
# In .env file
RESOLVER_DISABLE_PROB=0    # Enable probabilistic path (default)
OPENAI_API_KEY=your_key    # For LLM functionality
```

## Testing the Implementation

### 1. Verify Cascade Flow

```bash
# Test deterministic path
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT02200757 --persist

# Test probabilistic path (should go to review)
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT06467357 --persist

# Test LLM path
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT06467357 --persist --decider llm
```

### 2. Check Database Updates

```sql
-- Check counts
SELECT 'decisions' as table_name, COUNT(*) as count FROM resolver_decisions
UNION ALL 
SELECT 'features', COUNT(*) FROM resolver_features
UNION ALL 
SELECT 'queue', COUNT(*) FROM review_queue;

-- Check specific trial
SELECT nct_id, decided_by, match_type, company_id 
FROM resolver_decisions 
WHERE nct_id = 'NCT06467357';
```

### 3. Verify Training Data

```sql
-- Check feature availability
SELECT COUNT(*) AS matches 
FROM resolver_decisions d 
JOIN resolver_features f USING (nct_id, company_id);
```

## Benefits of the New Implementation

### 1. **Efficiency**
- Deterministic and probabilistic resolvers get first chance
- LLM only used when needed
- Faster resolution for clear cases

### 2. **Training Data Quality**
- Every trial generates features for model improvement
- Diverse decision sources (human, LLM, deterministic, probabilistic)
- Larger training dataset

### 3. **Consistency**
- All three functions follow the same logic
- Predictable behavior across different modes
- Clear audit trail

### 4. **Backward Compatibility**
- Existing workflows continue to work
- No breaking changes to CLI interface
- Same configuration files

## Troubleshooting

### Common Issues

1. **Probabilistic path disabled**
   - Check `.env` file for `RESOLVER_DISABLE_PROB=1`
   - Set to `0` or remove the line

2. **LLM not working**
   - Check `OPENAI_API_KEY` environment variable
   - Verify OpenAI package installation
   - Check API rate limits

3. **Database connection issues**
   - Verify database is running: `make db.health`
   - Check connection string in `.env`
   - Ensure migrations are up to date: `make migrate_up`

### Debug Mode

```bash
# Enable verbose logging
export PYTHONPATH=src
python -m ncfd.mapping.cli resolve-nct NCT01234567 --persist --decider llm
```

## Performance Considerations

### Threshold Tuning

- **Higher `tau_accept`**: More conservative, fewer automatic accepts, more LLM usage
- **Lower `tau_accept`**: More aggressive, more automatic accepts, less LLM usage
- **Balance**: Aim for 70-80% automatic resolution, 20-30% LLM review

### Batch Processing

- **Small batches** (10-25): Good for testing and development
- **Large batches** (100+): Good for production processing
- **Monitor**: Check database performance with large batches

## Future Enhancements

### Potential Improvements

1. **Adaptive thresholds**: Automatically adjust based on performance
2. **Confidence calibration**: Better probability estimates
3. **Feature engineering**: Additional features for better scoring
4. **Model ensemble**: Combine multiple models for better decisions

### Monitoring

- Track resolution success rates by path
- Monitor LLM usage and costs
- Analyze feature importance for model improvement
- Measure training data quality improvements

## Conclusion

The implementation successfully solves Problem 1 by:

✅ **Fixing the cascade flow**: Deterministic → Probabilistic → LLM  
✅ **Ensuring training data**: All decisions generate features for training  
✅ **Maintaining efficiency**: LLM only used when needed  
✅ **Preserving compatibility**: No breaking changes to existing workflows  

The resolver now provides a robust, efficient, and data-rich foundation for clinical trial sponsor resolution, with clear decision paths and comprehensive training data generation.
