# Study Card System

The Study Card System is a comprehensive framework for extracting, analyzing, and evaluating clinical trial data using LLM-based workers and deterministic validation.

## Architecture Overview

The system follows a modular architecture with clear separation between LLM-based reasoning and deterministic rule-based processing:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Input Data   │───▶│  LLM Workers    │───▶│ Deterministic   │
│                 │    │                 │    │    Workers     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
                                ▼                       ▼
                       ┌─────────────────────────────────────┐
                       │         Pipeline Orchestrator       │
                       └─────────────────────────────────────┘
                                │
                                ▼
                       ┌─────────────────────────────────────┐
                       │         Decision Record             │
                       └─────────────────────────────────────┘
```

## Core Components

### 1. Data Models (`models/`)

- **DocumentCard**: Source document representation with metadata
- **EvidenceSpan**: Text spans with evidence and location information
- **Claim**: Atomic, testable claims with evidence
- **MethodCard**: Study methodology and design details
- **ResultsFactsheet**: Normalized results data
- **PocketContextCard**: Disease and intervention context
- **GateCandidate**: Initial gate proposals
- **GateSpec**: Validated gate specifications
- **GateAssessment**: Gate evaluation results
- **DecisionRecord**: Final decision documentation

### 2. LLM Workers (`workers/llm/`)

- **MethodAuditor**: Reconstructs study methodology from text spans
- **ResultsDistiller**: Extracts and normalizes results data
- **GateProposer**: Generates gate proposals based on evidence
- **FdaLens**: Provides FDA perspective analysis
- **MemoComposer**: Creates final decision memos

### 3. Deterministic Workers (`workers/deterministic/`)

- **GateValidator**: Validates gate specifications using rules
- **GateAssessor**: Evaluates gates using deterministic calculations
- **Calculators**: Mathematical computations and aggregations

### 4. Pipeline Integration (`pipeline/`)

- **StudyCardPipeline**: Main pipeline coordinator
- **Integration**: Connects to existing orchestrator.py

## Key Features

### Provenance Tracking
- Every artifact tracks its lineage and evidence spans
- Input hashes for caching and reproducibility
- Parent-child relationships between artifacts

### Validation Layers
- Schema validation for all data models
- Rule-based validation for gate specifications
- Provenance checking for evidence spans

### Separation of Concerns
- LLM workers handle reasoning and interpretation
- Deterministic workers handle calculations and validation
- Clear contracts between components

## Usage Example

```python
from src.ncfd.pipeline.study_card_pipeline import StudyCardPipeline

# Initialize pipeline
pipeline = StudyCardPipeline()

# Execute pipeline
trial_context = {
    "disease": "Heart Failure",
    "intervention": "Gene Therapy",
    "design": {"arms": 2, "total_n": 100},
    "pocket_context": PocketContextCard(...)
}

result = pipeline.execute("NCT12345", trial_context)

if result.success:
    print(f"Decision: {result.decision_record.decision}")
    print(f"Gates passed: {result.decision_record.passed_gates}")
else:
    print(f"Pipeline failed: {result.errors}")
```

## Data Flow

1. **Document Retrieval**: Find relevant documents and extract evidence spans
2. **Method Auditing**: Reconstruct study methodology from text
3. **Results Distillation**: Extract and normalize results data
4. **Claim Generation**: Create atomic claims from evidence
5. **Gate Proposal**: Generate gate candidates based on evidence
6. **Gate Validation**: Validate gate specifications using rules
7. **Gate Assessment**: Evaluate gates using deterministic logic
8. **Decision Creation**: Combine assessments into decision record
9. **FDA Analysis**: Optional FDA perspective analysis
10. **Memo Composition**: Generate final decision memo

## Integration Points

The system integrates with the existing codebase through:

- **Pipeline Directory**: Main pipeline logic in `pipeline/study_card_pipeline.py`
- **Utils Directory**: Common utilities in `utils/study_card_utils.py`
- **Test Directory**: Comprehensive test suite in `tests/test_study_cards/`

## Development Status

This is the initial implementation with:

- ✅ Complete data model structure
- ✅ Base worker infrastructure
- ✅ LLM worker framework
- ✅ Deterministic worker framework
- ✅ Pipeline orchestration
- ✅ Basic test coverage

Next steps include:
- Implementing remaining worker logic
- Adding JSON schemas for validation
- Creating normalization utilities
- Adding comprehensive error handling
- Expanding test coverage

## Testing

Run the test suite:

```bash
cd tests/
pytest test_study_cards/ -v
```

## Contributing

When adding new features:

1. Follow the existing architecture patterns
2. Separate LLM and deterministic logic
3. Add comprehensive tests
4. Update this documentation
5. Ensure provenance tracking is maintained
