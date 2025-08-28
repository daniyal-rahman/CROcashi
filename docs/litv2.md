# Literature Ingestion Pipeline v2 (LITv2)

## Overview

LITv2 is a cost-optimized, three-stage literature ingestion system that replaces the previous "smart stop" mechanism with an intelligent pruning strategy. The system processes clinical trial literature through metadata-only discovery, abstract evaluation, and on-demand full-text retrieval.

## Architecture

### Core Components

1. **LiteratureOrchestrator** - Main coordinator managing all pipeline stages
2. **LiteraturePipeline** - Three-stage processing engine
3. **LiteratureScorer** - Utility scoring (U0/U1) for document triage
4. **DocumentQueue** - Candidate management and prioritization
5. **LLMEvaluator** - AI-driven evaluation and early stopping
6. **SmartPubMedClient** - Three-stage PubMed retrieval
7. **BudgetMonitor** - Cost tracking and budget enforcement

### Three-Stage Pipeline

```
Stage A: Metadata Discovery (Cheap)
├── Search PubMed with NCT IDs + trial metadata
├── Extract basic document information
├── Calculate U0 scores (metadata-based utility)
└── Persist candidates for Stage B

Stage B: Abstract Evaluation (Moderate)
├── Retrieve abstracts for high-U0 candidates
├── Calculate U1 scores (abstract-based utility)
├── Apply utility thresholds (θ_high, θ_low)
└── Promote/park candidates based on scores

Stage C: Full-Text Retrieval (Expensive)
├── On-demand full-text for high-utility documents
├── Triggered by LLM evaluation requests
├── Controlled by budget constraints
└── Rare, targeted retrieval only
```

## Implementation Details

### Key Files

#### Core Pipeline
- `src/ncfd/pipeline/literature_orchestrator.py` - Main orchestrator
- `src/ncfd/ingest/literature_pipeline.py` - Three-stage pipeline engine
- `src/ncfd/ingest/literature_scoring.py` - Utility scoring algorithms
- `src/ncfd/ingest/document_queue.py` - Candidate queue management

#### LLM Integration
- `src/ncfd/ingest/llm_evaluator.py` - AI evaluation engine
- `src/ncfd/ingest/llm_client.py` - OpenAI GPT-5-mini integration

#### Data Retrieval
- `src/ncfd/ingest/smart_pubmed.py` - PubMed client with three-stage logic
- `src/ncfd/ingest/budget_monitor.py` - Cost tracking and limits

#### Database Models
- `src/ncfd/db/models.py` - Core data models
- `alembic/versions/` - Database migrations

### Configuration

Centralized YAML configuration with sections:
- `scoring`: Utility thresholds and weights
- `queue`: Batch sizes and candidate limits
- `evaluation`: LLM evaluation parameters
- `pubmed`: API settings and rate limits
- `budget`: Cost limits and thresholds

### Logic Flow

1. **Initialization**
   ```
   Orchestrator → Unified Config → Component Initialization
   ```

2. **Trial Processing**
   ```
   Trial Queue → Drug Synonyms → Pipeline Execution
   ```

3. **Stage A (Metadata)**
   ```
   PubMed Search → U0 Scoring → Database Persistence
   ```

4. **Stage B (Abstracts)**
   ```
   U0 Filtering → Abstract Fetch → U1 Scoring → Promotion/Parking
   ```

5. **LLM Evaluation**
   ```
   Document Batch → AI Analysis → Stop Decision → Trial Status Update
   ```

6. **Stage C (Full-Text)**
   ```
   High-Utility Candidates → Budget Check → Full-Text Retrieval
   ```

## Database Schema

### Core Tables
- `trials` - Clinical trial information
- `documents` - Literature documents
- `document_utilities` - U0/U1 scores and metadata
- `trial_evaluations` - LLM evaluation results
- `trial_priority_queue` - Processing queue management
- `cost_records` - Budget tracking
- `literature_pipeline_executions` - Pipeline run history

### Key Relationships
- `trials` → `document_utilities` (one-to-many)
- `trials` → `trial_evaluations` (one-to-many)
- `trials` → `trial_priority_queue` (one-to-many)

## Usage

### Running the Pipeline

```python
from ncfd.pipeline.literature_orchestrator import LiteratureOrchestrator
from ncfd.db.session import get_session

# Initialize orchestrator
with get_session() as db_session:
    orchestrator = LiteratureOrchestrator(config, db_session)
    
    # Run pipeline for specific trials
    result = orchestrator.run_literature_pipeline(
        trial_ids=['NCT05111574'],
        dry_run=False
    )
```

### Configuration Example

```yaml
scoring:
  tau_abstract: 0.35      # U0 threshold for abstract evaluation
  theta_high: 0.75        # High utility threshold
  theta_low: 0.25         # Low utility threshold
  delta_min: 0.05         # Minimum improvement for promotion

evaluation:
  eval_every_docs: 2      # LLM evaluation frequency
  tier2_llm_tokens_per_eval: 1500

budget:
  daily_limit: 50.0       # Daily cost limit
  trial_limit: 5.0        # Per-trial cost limit
  costs:
    metadata_fetch: 0.001
    abstract_fetch: 0.01
    full_text_fetch: 0.25
    llm_evaluation: 0.05
```

### Testing

#### End-to-End Demo
```bash
# Run complete pipeline demonstration
source .env
python scripts/demo_literature_pipeline_e2e.py
```

#### Database Setup
```bash
# Apply migrations
source .env
alembic upgrade head

# Verify tables
psql postgresql://ncfd:ncfd@localhost:5433/ncfd -c "\dt"
```

## Key Features

### Cost Optimization
- **Stage A**: Free/cheap metadata discovery
- **Stage B**: Moderate-cost abstract evaluation
- **Stage C**: Expensive full-text only when needed

### Intelligent Pruning
- **U0 Scoring**: Metadata-based utility assessment
- **U1 Scoring**: Abstract-based detailed evaluation
- **LLM Evaluation**: AI-driven early stopping decisions

### Budget Control
- **Per-Operation Costs**: Tracked for each pipeline stage
- **Trial Limits**: Prevent runaway costs per trial
- **Period Limits**: Daily/monthly budget enforcement

### Data Persistence
- **Cross-Stage Persistence**: U0 scores available for Stage B
- **Run Isolation**: Each pipeline execution has unique run_id
- **Audit Trail**: Complete cost and decision history

## Performance Characteristics

- **Stage A**: ~1-2 seconds per trial, $0.001 per document
- **Stage B**: ~0.5-1 second per abstract, $0.01 per abstract
- **Stage C**: ~2-5 seconds per full-text, $0.25 per document
- **LLM Evaluation**: ~1-3 seconds per batch, $0.05 per evaluation

## Error Handling

- **Budget Exceeded**: Graceful degradation with logging
- **API Failures**: Retry logic with exponential backoff
- **Database Errors**: Transaction rollback and recovery
- **LLM Failures**: Fallback to mock evaluation

## Monitoring

### Logs
- Component initialization and configuration
- Stage execution progress and timing
- Cost tracking and budget status
- Error conditions and recovery

### Metrics
- Documents processed per stage
- Utility score distributions
- Cost per operation type
- Pipeline execution times

## Future Enhancements

1. **Multi-Provider Support**: Additional LLM providers beyond OpenAI
2. **Advanced Scoring**: Machine learning-based utility prediction
3. **Real-time Updates**: Live PubMed monitoring for new publications
4. **Distributed Processing**: Parallel trial processing across workers
5. **Advanced Analytics**: Trial-level literature impact assessment
