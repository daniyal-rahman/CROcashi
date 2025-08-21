# Problem 1 Solution Summary

## Problem Description

**Current State (Before Fix):**
- The LLM pathway was working but going straight to the LLM when `decider="llm"`
- Deterministic and probabilistic resolvers were being bypassed when LLM was enabled
- LLM decisions were not being sent to the probabilistic model for training

**Requirements:**
1. **Fix the flow**: Deterministic → Probabilistic → LLM (only if needed)
2. **Training data**: All LLM wirings should also be sent to the probabilistic model for training instead of relying only on human input

## Solution Implemented

### 1. Fixed Resolution Flow

The resolver now follows a proper cascade approach:

```
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

### 2. Key Changes Made

#### A. Modified `resolve_one()` function
- **Before**: LLM bypassed deterministic and probabilistic when enabled
- **After**: Always tries deterministic first, then probabilistic, then LLM only if needed

#### B. Modified `resolve_nct()` function  
- **Before**: Same bypass issue
- **After**: Same proper cascade flow

#### C. Modified `resolve_batch()` function
- **Before**: Same bypass issue  
- **After**: Same proper cascade flow

### 3. Training Data Flow

**Critical Improvement**: All decisions now generate training data:

```
Deterministic ACCEPT:
├── Features: Not applicable (exact match)
├── Decision: Stored in resolver_decisions
└── Training: Available for future probabilistic model training

Probabilistic ACCEPT:
├── Features: Stored in resolver_features  
├── Decision: Stored in resolver_decisions
└── Training: Full feature vector + decision available

LLM ACCEPT:
├── Features: Stored in resolver_features (from probabilistic scoring)
├── Decision: Stored in resolver_decisions  
└── Training: Full feature vector + LLM decision available
```

### 4. Benefits of the New Flow

1. **Efficiency**: Deterministic and probabilistic resolvers get first chance to resolve
2. **Training Data**: Every trial processed generates features for model improvement
3. **Fallback**: LLM only used when probabilistic model is uncertain
4. **Consistency**: All three functions now follow the same logic
5. **Audit Trail**: Clear decision path for each trial

### 5. Usage Examples

```bash
# Auto mode: Uses the cascade (det → prob → LLM if needed)
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT00032773 --persist --apply-trial

# Human mode: Uses cascade but marks decisions as human-reviewed  
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT00032773 --persist --apply-trial --decider human

# LLM mode: Uses cascade, LLM gets final say if probabilistic uncertain
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT00032773 --persist --apply-trial --decider llm
```

### 6. Training Loop Impact

**Before**: Only human decisions and probabilistic decisions were available for training
**After**: All decisions (deterministic, probabilistic, LLM) generate training data:

- `resolver_features`: Contains feature vectors for all trials
- `resolver_decisions`: Contains all decision outcomes  
- Training script can now use:
  - Human-reviewed decisions (gold standard)
  - LLM decisions (AI-generated labels)
  - Deterministic decisions (rule-based)
  - Probabilistic decisions (model-based)

This significantly expands the training dataset and should improve the probabilistic model's performance over time.

## Testing the Solution

To verify the fix works:

1. **Run a few trials** with different deciders to see the cascade in action
2. **Check database tables** to ensure features are being stored for all trials
3. **Verify training export** includes all decision types
4. **Monitor performance** to ensure deterministic and probabilistic still work efficiently

The solution maintains backward compatibility while fixing the core issue of missing training data and inefficient resolution flow.
