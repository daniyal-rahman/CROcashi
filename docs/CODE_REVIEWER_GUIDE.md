# Code Reviewer Guide - CROcashi Repository

## 🎯 **Purpose of This Document**

This guide is designed for **external code reviewers** who haven't worked with this repository before. It provides a structured approach to:
1. **Understand the repository architecture** and purpose
2. **Quickly identify potential issues** and areas of concern
3. **Verify end-to-end functionality** through systematic testing
4. **Navigate the codebase** efficiently during review

---

## 📋 **Repository Overview**

### **What This Repository Does**
**CROcashi** (Clinical Research Organization Cash Investment) is a **Near-Certain Failure Detector** for US-listed biotech pivotal trials. It uses:
- **Signal Detection**: 9 primitive failure signals (S1-S9)
- **Gate Analysis**: 4 failure pattern gates (G1-G4)
- **Bayesian Scoring**: Failure probability calculation
- **Machine Learning**: LLM-based resolution for ambiguous cases

### **Key Business Value**
- **Predict trial failures** before they happen
- **Identify high-risk biotech investments** for trading decisions
- **Automate clinical trial analysis** using AI/ML
- **Provide confidence scores** for investment decisions

---

## 🏗️ **Repository Architecture**

### **Core Structure**
```
CROcashi/
├── src/ncfd/           # Main application code
│   ├── signals/        # Signal detection (S1-S9)
│   ├── gates/          # Gate analysis (G1-G4)
│   ├── scoring/        # Bayesian scoring system
│   ├── mapping/        # Company resolution & linking
│   ├── extract/        # Document processing & extraction
│   ├── ingest/         # Data ingestion & validation
│   ├── pipeline/       # Workflow orchestration
│   └── db/            # Database models & migrations
├── alembic/            # Database migrations
├── tests/              # Test suite
├── scripts/            # Validation & demo scripts
└── docs/               # Documentation
```

### **Key Technologies**
- **Python 3.11+** with modern type hints
- **PostgreSQL** with Alembic migrations
- **SQLAlchemy** ORM with async support
- **Prefect** for workflow orchestration
- **OpenAI/LLM** for intelligent resolution
- **Docker** for deployment

---

## 🔍 **Critical Review Areas**

### **1. Database Migration System**
**Location**: `alembic/versions/`
**What to Check**:
- [ ] All migrations are **idempotent** (use `IF NOT EXISTS`)
- [ ] Migration chain is **linear** (no branching issues)
- [ ] **Foreign key constraints** are properly defined
- [ ] **Indexes** are created for performance
- [ ] **Data types** are consistent across migrations

**Red Flags**:
- Migrations that drop/recreate tables without data preservation
- Missing foreign key constraints
- Inconsistent data types (e.g., mixing TEXT and BIGINT)

### **2. Signal Detection Logic**
**Location**: `src/ncfd/signals/`
**What to Check**:
- [ ] **Signal definitions** are mathematically sound
- [ ] **Thresholds** are reasonable and documented
- [ ] **Edge cases** are handled (null values, missing data)
- [ ] **Performance** considerations for large datasets

**Red Flags**:
- Hard-coded magic numbers without explanation
- Missing null checks or error handling
- O(n²) algorithms that could cause performance issues

### **3. Scoring System**
**Location**: `src/ncfd/scoring/`
**What to Check**:
- [ ] **Bayesian calculations** are mathematically correct
- [ ] **Prior probabilities** are well-justified
- [ ] **Confidence intervals** are properly calculated
- [ ] **Calibration** methods are sound

**Red Flags**:
- Division by zero possibilities
- Incorrect probability calculations
- Missing confidence intervals

### **4. Machine Learning Integration**
**Location**: `src/ncfd/mapping/llm_decider.py`
**What to Check**:
- [ ] **API key security** (not hardcoded)
- [ ] **Rate limiting** and error handling
- [ ] **Prompt engineering** is clear and safe
- [ ] **Fallback mechanisms** when LLM fails

**Red Flags**:
- Hardcoded API keys or credentials
- No rate limiting or retry logic
- Prompts that could cause security issues

---

## 🧪 **End-to-End Testing Guide**

### **Phase 1: Environment Setup**
```bash
# 1. Clone and setup
git clone <repository>
cd CROcashi
make setup
source .venv/bin/activate

# 2. Configure environment
cp .env.example .env
# Edit .env with your database credentials

# 3. Install dependencies
make install
```

### **Phase 2: Database Setup**
```bash
# 1. Start PostgreSQL (adjust for your setup)
docker run -d --name postgres -e POSTGRES_PASSWORD=ncfd -e POSTGRES_USER=ncfd -e POSTGRES_DB=ncfd -p 5432:5432 postgres:15

# 2. Run migrations
export DATABASE_URL="postgresql://ncfd:ncfd@localhost:5432/ncfd"
alembic upgrade head

# 3. Verify migration status
alembic current
alembic history --verbose
```

### **Phase 3: Core Functionality Tests**
```bash
# 1. Run the main validation script
python scripts/validate_phase6_pipeline.py

# 2. Run individual component tests
python scripts/demo_signals_and_gates.py
python scripts/demo_scoring_system.py
python scripts/demo_testing_validation.py

# 3. Run the test suite
make test
```

### **Phase 4: Integration Tests**
```bash
# 1. Test document ingestion
python scripts/test_document_ingest.py

# 2. Test pipeline integration
python scripts/demo_pipeline_integration.py

# 3. Test storage system
python scripts/demo_storage_system.py
```

---

## 🚨 **Common Issues & Red Flags**

### **Database Issues**
- **Migration conflicts**: Multiple heads in alembic
- **Constraint violations**: Missing foreign keys or check constraints
- **Performance**: Missing indexes on frequently queried columns
- **Data integrity**: Inconsistent data types or missing validations

### **Code Quality Issues**
- **Type hints**: Missing or incorrect type annotations
- **Error handling**: Unhandled exceptions or missing error messages
- **Documentation**: Missing docstrings or unclear function purposes
- **Testing**: Low test coverage or missing edge case tests

### **Security Issues**
- **Credentials**: Hardcoded passwords or API keys
- **Input validation**: Missing sanitization of user inputs
- **Access control**: No authentication or authorization checks
- **Data exposure**: Sensitive data in logs or error messages

### **Performance Issues**
- **N+1 queries**: Database queries in loops
- **Memory leaks**: Large objects not properly garbage collected
- **Inefficient algorithms**: O(n²) operations on large datasets
- **Resource limits**: No timeouts or connection pooling

---

## 📊 **Validation Checklist**

### **Pre-Review Setup**
- [ ] Repository clones successfully
- [ ] Dependencies install without errors
- [ ] Database connects and migrations run
- [ ] Environment variables are properly configured

### **Code Quality**
- [ ] All tests pass (`make test`)
- [ ] Linting passes (`make lint`)
- [ ] Code formatting is consistent (`make fmt`)
- [ ] Type checking passes (`mypy src/`)

### **Functionality**
- [ ] Main validation script runs successfully
- [ ] Individual component demos work
- [ ] Database operations complete without errors
- [ ] API endpoints respond correctly (if applicable)

### **Documentation**
- [ ] README provides clear setup instructions
- [ ] Code has adequate docstrings
- [ ] Complex logic is explained with comments
- [ ] API documentation is current (if applicable)

---

## 🔧 **Troubleshooting Common Problems**

### **Database Connection Issues**
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Test connection
psql $DATABASE_URL -c "SELECT 1;"

# Check migration status
alembic current
```

### **Import Errors**
```bash
# Ensure you're in the right directory
pwd  # Should be /path/to/CROcashi

# Check Python path
python -c "import sys; print(sys.path)"

# Verify virtual environment is activated
which python  # Should point to .venv/bin/python
```

### **Test Failures**
```bash
# Run tests with verbose output
pytest -v tests/

# Run specific test file
pytest tests/test_signals_primitives.py -v

# Check test coverage
pytest --cov=src/ncfd tests/
```

---

## 📝 **Review Notes Template**

Use this template to document your findings:

```markdown
## Code Review Summary
**Reviewer**: [Your Name]
**Date**: [Date]
**Repository**: CROcashi

### ✅ **What Works Well**
- [List positive aspects]

### ⚠️ **Areas of Concern**
- [List issues found]

### 🚨 **Critical Issues**
- [List blocking issues]

### 📋 **Recommendations**
- [List suggested improvements]

### 🧪 **Testing Results**
- [Document what you tested and results]

### 📊 **Overall Assessment**
- [Pass/Fail/Needs Work with justification]
```

---

## 🎯 **Quick Assessment Questions**

Answer these questions to quickly assess the repository health:

1. **Does the repository build and run?** (Setup, dependencies, database)
2. **Are the tests passing?** (Unit tests, integration tests)
3. **Is the code well-structured?** (Architecture, separation of concerns)
4. **Are there security concerns?** (Credentials, input validation)
5. **Is the documentation adequate?** (README, code comments, API docs)
6. **Are there performance issues?** (Database queries, algorithms)
7. **Is error handling robust?** (Exception handling, fallbacks)
8. **Are migrations safe?** (Idempotent, data preservation)

---

## 📞 **Getting Help**

If you encounter issues during review:

1. **Check the logs** in the `logs/` directory
2. **Review error messages** carefully for clues
3. **Check the documentation** in `docs/` directory
4. **Look at test examples** for usage patterns
5. **Contact the development team** with specific error details

---

**Remember**: The goal is to ensure this system can reliably detect clinical trial failures for investment decisions. Any issues that could affect accuracy, reliability, or performance are critical to identify and address.
