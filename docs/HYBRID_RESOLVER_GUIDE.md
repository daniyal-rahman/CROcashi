# Hybrid Entity Resolution System - Complete Guide

**Last Updated**: November 11, 2025  
**Status**: Built and ready for LLM activation in Week 4

## Overview

The hybrid entity resolution system combines rule-based matching with optional LLM validation to achieve high accuracy while maintaining performance. The system is currently running with LLM **disabled** to collect training data through manual review. When the RTX 5080 GPU arrives, the LLM can be activated immediately.

## Architecture

```
Entity Extraction
        ↓
Rule-Based Resolver (6-level hierarchy)
        ↓
  Confidence Check
        ↓
   ┌────────┴────────┐
   ↓                 ↓
High (≥0.90)    Medium (0.60-0.89)
Auto-match      → LLM Validator (if enabled)
   ↓                 ↓
   └──────────→ Final Decision
                     ↓
              Entity Created/Matched
```

### Rule-Based Matching (6 Levels)

1. **Exact Identifier Match** (confidence = 1.0)
   - NCT ID, PMID, DOI, CIK, etc.
   
2. **Exact Name Match** (confidence = 0.95)
   - Normalized string comparison
   
3. **Alias Lookup** (confidence = 0.90)
   - Matches against `entity_aliases` table
   - Self-improving: approved matches create new aliases
   
4. **Fuzzy Match + Context** (confidence = 0.70-0.89)
   - PostgreSQL trigram similarity
   - Context boosting (+0.10 for same company, +0.05 for same disease, etc.)
   
5. **Fuzzy Match Alone** (confidence = 0.60-0.79)
   - Trigram similarity without context
   
6. **No Match** (confidence = 0.0)
   - Create new entity

### LLM Validation (Optional)

When enabled, medium-confidence matches (0.60-0.89) are validated by a local LLM:

- **Model**: Llama 3.1 70B (quantized to Q4 or Q5)
- **Inference**: llama.cpp via llama-cpp-python
- **Latency**: ~1-3 seconds per validation
- **Cost**: $0 (local inference)

The LLM receives:
- Candidate text
- Existing entity name
- Entity type
- Context (source, relationships, etc.)
- Rule-based confidence score

And returns:
- Match decision (true/false)
- Confidence score (0.0-1.0)
- Reasoning (natural language explanation)

## Feature Flag Configuration

### Environment Variables

Add to `.env` (create from `.env.example`):

```bash
# LLM Entity Resolution (disabled by default)
USE_LLM_VALIDATION=false
LLM_MODEL_PATH=/path/to/llama-3.1-70b-finetuned.gguf
LLM_CONFIDENCE_WEIGHT=0.6

# Optional: Adjust thresholds
LLM_INVOKE_MIN_CONFIDENCE=0.60
LLM_INVOKE_MAX_CONFIDENCE=0.90
AUTO_MATCH_THRESHOLD=0.85
```

### Configuration Options

- **USE_LLM_VALIDATION**: Enable/disable LLM validation (default: `false`)
- **LLM_MODEL_PATH**: Path to GGUF model file
- **LLM_CONFIDENCE_WEIGHT**: Weight given to LLM confidence in final score (default: 0.6)
  - Final confidence = rule_conf × (1 - weight) + llm_conf × weight
- **LLM_INVOKE_MIN_CONFIDENCE**: Minimum rule confidence to invoke LLM (default: 0.60)
- **LLM_INVOKE_MAX_CONFIDENCE**: Maximum rule confidence to invoke LLM (default: 0.90)
- **AUTO_MATCH_THRESHOLD**: Minimum combined confidence to auto-match (default: 0.85)

### Check Configuration

```python
from src.config.feature_flags import FeatureFlags

FeatureFlags.print_config()
```

## Training Data Collection (Weeks 1-4)

### Manual Review Process

1. **Export current training data**:
```bash
python scripts/export_training_data.py
```

2. **Continue manual reviews**:
```bash
# Review match candidates in batches
python scripts/manual_review_candidates.py --batch-size 50

# Or use interactive review
python scripts/review_entity_match.py show <candidate_id>
python scripts/review_entity_match.py approve <candidate_id> [entity_id]
python scripts/review_entity_match.py reject <candidate_id>
```

3. **Monitor progress**:
```bash
# Analyze training data quality
python scripts/analyze_training_data.py

# Check how many reviews collected
python -c "
from database.config import get_db_session
from database.models.resolution import EntityMatchCandidate

with get_db_session() as session:
    reviewed = session.query(EntityMatchCandidate).filter(
        EntityMatchCandidate.status.in_(['reviewed', 'new_entity']),
        EntityMatchCandidate.deleted_at.is_(None)
    ).count()
    print(f'Training examples: {reviewed}')
    print(f'Target: 500-1000')
"
```

### Data Export for Fine-Tuning

Export reviewed candidates in JSONL format:

```bash
# Export all reviewed candidates
python scripts/export_training_data.py

# Output: data/llm_training/entity_matching_training.jsonl

# Split into train/val
python scripts/split_training_data.py

# Output: 
#   data/llm_training/train.jsonl (80%)
#   data/llm_training/val.jsonl (20%)

# Analyze data quality
python scripts/analyze_training_data.py
```

## Model Fine-Tuning (Week 4, when RTX 5080 arrives)

### Prerequisites

```bash
# Install fine-tuning dependencies
pip install transformers torch accelerate peft trl bitsandbytes
```

### Fine-Tuning Script

Create `scripts/finetune_llm.py`:

```python
from transformers import AutoModelForCausalLM, TrainingArguments
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
import torch

# Load base model (quantized)
model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-3.1-70B-Instruct",
    load_in_4bit=True,
    device_map="auto",
    torch_dtype=torch.float16
)

# LoRA configuration
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

# Prepare model
model = prepare_model_for_kbit_training(model)
model = get_peft_model(model, lora_config)

# Load training data
from datasets import load_dataset
dataset = load_dataset('json', data_files={
    'train': 'data/llm_training/train.jsonl',
    'validation': 'data/llm_training/val.jsonl'
})

# Training arguments
training_args = TrainingArguments(
    output_dir="models/llama-3.1-70b-biotech",
    num_train_epochs=3,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=2e-4,
    logging_steps=10,
    save_strategy="epoch",
    evaluation_strategy="epoch"
)

# Train
trainer = SFTTrainer(
    model=model,
    train_dataset=dataset['train'],
    eval_dataset=dataset['validation'],
    peft_config=lora_config,
    max_seq_length=2048,
    training_args=training_args
)

trainer.train()

# Save
trainer.save_model("models/llama-3.1-70b-biotech-finetuned")
```

### Run Fine-Tuning

```bash
python scripts/finetune_llm.py
```

Expected time: 6-12 hours on RTX 5080

## Activation Checklist (Week 4)

When RTX 5080 arrives and model is fine-tuned:

### 1. Install LLM Dependencies

```bash
pip install llama-cpp-python
```

### 2. Copy Model to Server

```bash
# Model will be in GGUF format after fine-tuning
cp models/llama-3.1-70b-biotech-finetuned.gguf /path/to/models/
```

### 3. Update Environment Variables

```bash
# In .env
USE_LLM_VALIDATION=true
LLM_MODEL_PATH=/path/to/models/llama-3.1-70b-biotech-finetuned.gguf
```

### 4. Test LLM Loading

```python
from src.entity_resolution.llm_matcher import LLMEntityMatcher

matcher = LLMEntityMatcher("/path/to/model.gguf")
print(f"LLM available: {matcher.is_available()}")
```

### 5. Run Evaluation

```bash
# Compare rule-based vs hybrid on validation set
python scripts/evaluate_hybrid_system.py
```

### 6. Start Processing with Hybrid Resolver

```python
from src.processing.pipeline import ProcessingPipeline

# Hybrid resolver enabled by default
pipeline = ProcessingPipeline(use_hybrid_resolver=True)

# Process a source
stats = pipeline.process_source('clinicaltrials_gov', limit=100)
```

### 7. Monitor Performance

Track metrics for 24-48 hours:
- Auto-match rate (target: 85-90%)
- Precision on auto-matches (target: 95%+)
- LLM invocation rate (should be 20-30% of cases)
- Average latency per entity
- Manual review queue size

### 8. Adjust Confidence Weights (if needed)

If precision is too low, increase threshold:
```bash
AUTO_MATCH_THRESHOLD=0.90  # More conservative
```

If too many reviews needed, lower threshold:
```bash
AUTO_MATCH_THRESHOLD=0.80  # More aggressive
```

Adjust LLM weight:
```bash
LLM_CONFIDENCE_WEIGHT=0.7  # Trust LLM more
LLM_CONFIDENCE_WEIGHT=0.5  # Trust rules more
```

## Usage Examples

### Basic Usage (LLM Disabled)

```python
from database.config import get_db_session
from src.entity_resolution.hybrid_resolver import HybridEntityResolver
from src.entity_resolution.types import ExtractedEntity, EntityType

with get_db_session() as session:
    resolver = HybridEntityResolver(session)
    
    entity = ExtractedEntity(
        entity_type=EntityType.DISEASE,
        name="Non-small Cell Lung Cancer",
        identifiers={},
        context={},
        metadata={'source_name': 'clinicaltrials_gov'}
    )
    
    result = resolver.resolve(entity)
    print(f"Status: {result.status}")
    print(f"Confidence: {result.confidence_score}")
    print(f"Method: {result.match_method}")
```

### Usage with Processing Pipeline

```python
from src.processing.pipeline import ProcessingPipeline

# Use hybrid resolver (default)
pipeline = ProcessingPipeline(use_hybrid_resolver=True)
stats = pipeline.process_source('fda_drugs', limit=50)

# Use rule-based only
pipeline = ProcessingPipeline(use_hybrid_resolver=False)
stats = pipeline.process_source('fda_drugs', limit=50)
```

### Evaluate System

```bash
python scripts/evaluate_hybrid_system.py
```

## Troubleshooting

### LLM Not Loading

**Issue**: `LLM not available` message

**Solutions**:
1. Check `LLM_MODEL_PATH` is correct
2. Verify model file exists and is readable
3. Check llama-cpp-python is installed: `pip install llama-cpp-python`
4. Check GPU is available: `nvidia-smi`
5. Try loading model manually to see error:
```python
from llama_cpp import Llama
model = Llama(model_path="/path/to/model.gguf", n_gpu_layers=-1)
```

### Low Precision

**Issue**: Auto-matches have <95% precision

**Solutions**:
1. Increase `AUTO_MATCH_THRESHOLD` (e.g., 0.90)
2. Review LLM prompts in `src/entity_resolution/llm_matcher.py`
3. Fine-tune with more training data
4. Adjust `LLM_CONFIDENCE_WEIGHT`

### Too Many Manual Reviews

**Issue**: >30% of entities need manual review

**Solutions**:
1. Lower `AUTO_MATCH_THRESHOLD` (e.g., 0.80)
2. Add more aliases through manual review
3. Improve entity extraction quality in processors
4. Check if LLM is actually running (USE_LLM_VALIDATION=true)

### Slow Processing

**Issue**: Processing takes too long

**Solutions**:
1. Check LLM GPU layers: should be `-1` (all layers on GPU)
2. Reduce context window: `n_ctx=2048` instead of 4096
3. Use smaller model (Llama 3.1 8B instead of 70B)
4. Disable LLM temporarily: `USE_LLM_VALIDATION=false`

## Next Steps

1. **Week 1-4**: Continue manual review to reach 500-1000 training examples
2. **Week 4**: Fine-tune Llama 70B on collected data
3. **Week 5**: Activate LLM and evaluate
4. **Week 6+**: Monitor and iterate

## Additional Resources

- **Training Data**: `data/llm_training/`
- **Evaluation Results**: `data/evaluation/`
- **Model Checkpoints**: `models/`
- **Review Results**: `MATCH_CANDIDATE_REVIEW_RESULTS.md`

## Support

For issues or questions:
1. Check logs: `grep "LLM" logs/processing.log`
2. Run diagnostics: `python scripts/evaluate_hybrid_system.py`
3. Review feature flags: `FeatureFlags.print_config()`

