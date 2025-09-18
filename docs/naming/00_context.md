# NCFD Repository Context Documentation

## Overview

The **NCFD (Near-Certain Failure Detector)** repository is a comprehensive system for analyzing US-listed biotech pivotal clinical trials to identify high-risk investments. The system combines signal detection, gate analysis, Bayesian scoring, and LLM-powered document processing to provide investment decision support.

## System Architecture

### Core Components

The system is organized into several key modules:

#### 1. Database Layer (`src/ncfd/db/`)
- **Models**: SQLAlchemy ORM models defining the complete schema
  - `models.py`: Main database models (1079 lines) - Core entities including companies, trials, assets, documents, signals, gates, scores
  - `study_card_models.py`: Study card specific models (81 lines) - StudyCard and Factsheet models
- **Migrations**: Alembic migrations for schema evolution
  - 52 migration files in `alembic/versions/`
  - Latest: `117fe225c48e_simplify_resolver_schema.py` (simplified resolver tables)
- **Session Management**: Database connection and session handling

#### 2. Data Ingestion (`src/ncfd/ingest/`)
- **CT.gov**: Clinical trial registry ingestion and change detection
- **SEC**: SEC filing processing and entity extraction
- **PubMed**: Literature retrieval and processing system
- **USPTO**: Patent data ingestion and processing
- **Text Processing**: Span indexing and document processing

#### 3. Document Processing (`src/ncfd/extract/`)
- **Retrieval**: Enhanced document retrieval with policy engines
- **Generators**: LLM-powered document analysis (study cards, results factsheets)
- **Models**: Structured data models for extracted information
- **Risk Assessment**: Pattern scoring and risk evaluation
- **Runtime Text**: Real-time text generation and caching

#### 4. Pipeline Orchestration (`src/ncfd/pipeline/`)
- **Orchestrator**: Unified pipeline coordination (1519 lines)
  - Coordinates CT.gov, SEC, PubMed, and study card pipelines
  - Manages dependencies and parallel execution
  - Handles error recovery and state management
- **Individual Pipelines**: Specialized pipelines for each data source
- **Asset Resolution**: Company and asset matching logic
- **Early Stopping**: Intelligent processing termination
- **Literature Queue**: Priority-based trial processing

#### 5. LLM Integration (`src/ncfd/llm/`)
- **Factory**: Provider factory with fallback support (225 lines)
- **Providers**: OpenAI and other LLM provider implementations
- **Concurrency**: Rate limiting and request management
- **Configuration**: Model selection and worker-specific overrides

#### 6. Logging System (`src/ncfd/logging/`)
- **Structured Logger**: JSON-based logging with context (374 lines)
- **Event Taxonomy**: Standardized event naming
- **IO Tracing**: Request/response tracking
- **Context Management**: Automatic context inclusion

#### 7. Entity Management (`src/ncfd/entities/`)
- **Schema**: In-memory entity pack definitions (183 lines)
  - CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo
  - EntityPack with must-link/should-link/cannot-link term generation
- **Mapping**: Entity resolution and normalization

#### 8. Synthesis (`src/ncfd/synthesis/`)
- **Evidence-Constrained Synthesis**: Structured evidence analysis
- **Independent LLM Analysis**: Multi-model validation

## Database Schema

### Core Tables

#### Company & Security Management
- `companies`: Core company entities with CIK, LEI, incorporation details
- `company_aliases`: Fuzzy matching aliases for company resolution
- `securities`: Stock tickers and exchange information

#### Trial Management
- `trials`: Clinical trial registry with NCT ID, phase, status, endpoints
- `trial_versions`: Historical trial data with change tracking
- `studies`: Document-trial associations with extraction results

#### Asset & Patent Management
- `assets`: Drug/asset entities with ownership and mechanism information
- `patents`: Patent records with family relationships
- `patent_assignments`: Patent ownership transfers

#### Document Processing
- `documents`: Raw document metadata and processing status
- `document_text`: Abstracts and full text content
- `document_tables`: Extracted table data
- `document_citations`: DOI/PMID/PMCID references
- `document_entities`: LangExtract entity extraction results
- `document_links`: Linking between documents and normalized entities
- `spans`: Text spans with location information

#### Signal Detection & Scoring
- `signals`: Primitive failure signals (S1-S9) with severity
- `signal_evidence`: Evidence supporting signal detection
- `gates`: Composite failure pattern gates (G1-G4)
- `scores`: Bayesian posterior probabilities per run

#### Literature System
- `trial_doc_candidates`: Trial-document relationships by processing stage
- `pubmed_meta`: PubMed-specific metadata
- `pmc_meta`: PMC-specific metadata
- `trial_lit_state`: Trial-level literature state and metrics

#### Processing & Operations
- `runs`: Execution lineage tracking
- `run_artifacts`: Output tracking per run
- `processing_queue`: Task queue for pipeline operations
- `ctgov_ingest_state`: CT.gov ingestion state tracking

#### Resolution & Review
- `sponsor_resolutions`: Simplified sponsor resolution results
- `manual_review_queue`: Manual review queue management
- `academic_blacklist`: Academic institution patterns
- `llm_discoveries`: LLM learning and discoveries

### Enums
- `exchange_enum`: NASDAQ, NYSE, NYSE_AM, OTCQX, OTCQB
- `phase_enum`: P2, P2B, P2_3, P3
- `doc_type_enum`: PR, 8K, Abstract, Poster, Paper, Registry, FDA
- `trial_status_enum`: Recruiting, Active, Completed, Terminated, etc.
- `signal_id_enum`: S1-S9 primitive signals
- `gate_id_enum`: G1-G4 composite gates

## Configuration System

### Core Configuration (`config/core_system_config.yaml`)
- **Logging**: Structured logging with JSON output, context tracking, IO tracing
- **Database**: Connection pooling, batch operations, performance optimization
- **Storage**: S3/local filesystem with fallback support
- **Ingestion**: Rate limiting and API configurations
- **Entity Mapping**: Exchange whitelist, name matching thresholds
- **Linking Heuristics**: Confidence thresholds and auto-promotion settings
- **Signals**: P-value thresholds, power requirements, effect size analysis
- **Gates**: Co-dependency definitions and likelihood ratios
- **Scoring**: Prior failure rates, likelihood ratios, stop rules

### Entity Packs (`config/entity_packs/`)
- YAML-based entity definitions for literature retrieval
- Company aliases, asset names, mechanism targets, indications
- Registry IDs, publisher strings, date ranges

## Signal Detection System

### Primitive Signals (S1-S9)
1. **S1**: Endpoint changes post-registration
2. **S2**: Underpowered trials
3. **S3**: Subgroup-only wins without multiplicity control
4. **S4**: ITT vs PP contradictions
5. **S5**: Effect size analysis and class priors
6. **S6**: Multiple interim looks
7. **S7**: Single-arm trials vs RCT standard
8. **S8**: P-value cusping
9. **S9**: OS/PFS contradictions

### Composite Gates (G1-G4)
1. **G1 (Alpha-Meltdown)**: S1 + S2 combination
2. **G2 (Analysis-Gaming)**: S3 + S4 combination
3. **G3 (Plausibility)**: S5 + (S6 | S7) combination
4. **G4 (P-hacking)**: S8 + (S1 | S3) combination

## Testing Framework

### Test Structure
- **conftest.py**: Test environment setup with database isolation
- **Scripts**: Comprehensive integration tests
  - `comprehensive_cassava_pipeline_test.py`: Full pipeline test with real Cassava trial data
  - Tests CT.gov ingestion, PubMed processing, study card generation
- **Utils**: Test environment management and data loading

### Test Database
- Uses separate testing PostgreSQL database
- Automatic cleanup and isolation between tests
- Real-world trial data for comprehensive testing

## API Layer

### Current Status
- **main.py**: Empty API implementation (placeholder)
- No REST API endpoints currently implemented
- Focus on pipeline orchestration rather than API exposure

## Key Technologies

### Backend
- **Python 3.11+** with modern type hints
- **PostgreSQL** with Alembic migrations
- **SQLAlchemy** ORM with async support
- **Docker** for deployment

### LLM Integration
- **OpenAI** GPT models for document analysis
- **Provider Factory** with fallback support
- **Concurrency Management** for rate limiting
- **Cost Tracking** and token monitoring

### Data Processing
- **LangExtract** for entity extraction
- **BM25** indexing for document retrieval
- **DuckDB** for analytical queries
- **S3/Local** storage for document persistence

## Production Readiness

### ✅ Fully Implemented
- Core infrastructure and database schema
- Signal detection and gate analysis
- Bayesian scoring system
- Study card architecture with LLM integration
- Comprehensive testing framework
- Structured logging and monitoring

### ⚠️ Needs Attention
- API layer implementation
- Monitoring and alerting systems
- Configuration calibration
- Error handling and retry logic
- Patent system implementation

## File Naming Conventions

### Database Models
- **snake_case** for table names: `companies`, `trial_versions`, `signal_evidence`
- **PascalCase** for model classes: `Company`, `TrialVersion`, `SignalEvidence`
- **snake_case** for column names: `company_id`, `trial_id`, `created_at`

### Configuration Files
- **snake_case** for file names: `core_system_config.yaml`, `ctgov_config.yaml`
- **SCREAMING_SNAKE_CASE** for environment variables: `DATABASE_URL`, `S3_BUCKET`

### Code Modules
- **snake_case** for module names: `orchestrator.py`, `structured_logger.py`
- **PascalCase** for class names: `PipelineOrchestrator`, `StructuredLogger`
- **snake_case** for function names: `run_full_pipeline`, `create_provider`

### Test Files
- **snake_case** for test files: `comprehensive_cassava_pipeline_test.py`
- **test_** prefix for test modules: `test_signals.py`, `test_gates.py`

## Migration History

The database schema has evolved through 52 Alembic migrations, with key milestones:
- Baseline extensions and core tables
- Company and securities management
- Trial versioning and change tracking
- Document processing and entity extraction
- Signal detection and gate analysis
- Literature system and PubMed integration
- Simplified resolver schema (latest)

## Development Workflow

### Environment Setup
1. PostgreSQL database with test/prod separation
2. Environment variables via `.env` files
3. Docker for consistent development environment
4. Alembic for database migrations

### Testing Approach
1. Comprehensive integration tests with real data
2. Database isolation and cleanup
3. Pipeline orchestration testing
4. LLM integration validation

### Configuration Management
1. YAML-based configuration files
2. Environment-specific profiles (local/staging/prod)
3. Entity packs for literature retrieval
4. Signal and gate parameter tuning

This documentation provides the foundational context for understanding the NCFD repository structure, architecture, and implementation details.
