# NCFD Naming Rules

## Overview

This document defines the comprehensive naming conventions for the NCFD (Near-Certain Failure Detector) codebase. These rules ensure consistency across database schema, Python code, and API interfaces.

## Database Naming Conventions

### Tables
- **Format**: `snake_case_plural`
- **Examples**: `companies`, `trial_versions`, `signal_evidence`
- **Rationale**: Plural nouns clearly indicate collections of entities

### Columns
- **Format**: `snake_case`
- **Examples**: `company_id`, `created_at`, `sponsor_text`
- **Rationale**: Consistent with Python naming conventions

### Primary Keys
- **Format**: `id` (singular)
- **Examples**: `company_id`, `trial_id`, `signal_id`
- **Rationale**: Clear, unambiguous identifier naming

### Foreign Keys
- **Format**: `<ref_table>_id`
- **Examples**: `company_id`, `trial_id`, `asset_id`
- **Rationale**: Clear relationship indication with consistent suffix

### Timestamps
- **Required Fields**: `created_at`, `updated_at`
- **Format**: `snake_case`
- **Rationale**: Standard audit trail fields

### Enums
- **Format**: `PascalCase`
- **Examples**: `ExchangeEnum`, `PhaseEnum`, `TrialStatusEnum`
- **Rationale**: Consistent with Python class naming

## Code Naming Conventions

### Classes
- **Format**: `PascalCase`
- **Examples**: `Company`, `TrialVersion`, `PipelineOrchestrator`
- **Rationale**: Standard Python class naming convention

### Functions
- **Format**: `snake_case`
- **Examples**: `process_document`, `track_trial_changes`, `resolve_sponsor`
- **Rationale**: Consistent with Python function naming

### Variables
- **Format**: `snake_case`
- **Examples**: `trial_id`, `company_name`, `processing_result`
- **Rationale**: Consistent with Python variable naming

### Constants
- **Format**: `SCREAMING_SNAKE_CASE`
- **Examples**: `ESEARCH_URL`, `MAX_RETRIES`, `DEFAULT_TIMEOUT`
- **Rationale**: Clear distinction from variables

### Enums
- **Class Format**: `PascalCase`
- **Member Format**: `SCREAMING_SNAKE_CASE`
- **Examples**: 
  ```python
  class TrialStatus(Enum):
      RECRUITING = "RECRUITING"
      COMPLETED = "COMPLETED"
      TERMINATED = "TERMINATED"
  ```

### Pydantic Models
- **Format**: `PascalCase`
- **Examples**: `StudyCard`, `DocumentCard`, `EvidenceField`
- **Rationale**: Consistent with Python class naming

## API Naming Conventions

### HTTP Paths
- **Format**: `kebab-case`
- **Examples**: `/api/trial-data`, `/api/study-cards`, `/api/signal-detection`
- **Rationale**: URL-friendly format with hyphens

### HTTP Handlers
- **Format**: `snake_case`
- **Examples**: `get_trial_data`, `create_study_card`, `detect_signals`
- **Rationale**: Consistent with Python function naming

## Rules and Constraints

### Length Limits
- **Maximum Name Length**: 64 characters
- **Rationale**: Database and identifier length limits

### Forbidden Prefixes
- **Avoid**: `tmp_`, `test_`
- **Rationale**: Prevents confusion with temporary or test code

### Abbreviations
- **configuration** → `cfg`
- **identifier** → `id`
- **Rationale**: Common, well-understood abbreviations

### Reserved Words
- **Avoid**: `type`, `class`, `index`
- **Rationale**: Python and SQL reserved words

### Foreign Key Format
- **Pattern**: `<ref_table>_id`
- **Examples**: `company_id`, `trial_id`, `asset_id`
- **Rationale**: Clear relationship indication

### Cascade Behavior
- **Default**: `CASCADE` for dependent relationships
- **Rationale**: Ensures referential integrity and prevents orphaned records

## Examples from Current Codebase

### Database Models
```python
class Company(Base):
    __tablename__ = "companies"  # snake_case_plural
    
    company_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # <table>_id
    name: Mapped[str] = mapped_column(Text, nullable=False)  # snake_case
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # timestamp
```

### Enums
```python
class TrialStatus(Enum):  # PascalCase
    RECRUITING = "RECRUITING"  # SCREAMING_SNAKE_CASE
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"
```

### Functions
```python
def process_document(doc_id: str) -> DocumentCard:  # snake_case
    """Process a document and return structured data."""
    pass
```

### Classes
```python
class PipelineOrchestrator:  # PascalCase
    """Unified orchestrator for pipeline execution."""
    
    def run_full_pipeline(self) -> OrchestrationResult:  # snake_case
        """Execute the complete pipeline."""
        pass
```

## Migration Guidelines

When applying these naming rules to existing code:

1. **Database Changes**: Use Alembic migrations to rename tables and columns
2. **Code Changes**: Update all references to renamed symbols
3. **API Changes**: Maintain backward compatibility during transitions
4. **Testing**: Ensure all tests pass after renaming

## Enforcement

These naming rules should be enforced through:
- **Linting**: Configure tools like `flake8` and `black`
- **Pre-commit Hooks**: Validate naming before commits
- **Code Reviews**: Manual verification of naming compliance
- **Documentation**: Keep this document updated with any rule changes
