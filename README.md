# CROcashi - Clinical Research Organization Cash Investment

**Near-Certain Failure Detector** for US-listed biotech pivotal trials.

A comprehensive clinical trial failure detection system that uses advanced signal detection, pattern recognition, and Bayesian scoring to identify high-risk trials before they fail. This system provides investment-grade analysis for biotech trading decisions.

## 🎯 **What This System Does**

CROcashi analyzes clinical trial data to predict trial failures with high confidence, enabling:
- **Risk Assessment**: Identify high-risk biotech investments before failure
- **Trading Decisions**: Make informed decisions based on trial success probability
- **Portfolio Management**: Diversify biotech holdings based on risk profiles
- **Early Warning**: Detect trial problems before they become public knowledge

## 🏗️ **System Architecture**

### **Core Components**
- **Signal Detection**: 9 primitive failure signals (S1-S9) for trial analysis
- **Gate Analysis**: 4 failure pattern gates (G1-G4) for risk assessment
- **Bayesian Scoring**: Mathematical probability calculation for failure risk
- **Machine Learning**: LLM-based resolution for ambiguous cases
- **Data Pipeline**: Automated ingestion and processing of trial data

### **Technology Stack**
- **Backend**: Python 3.11+ with modern type hints
- **Database**: PostgreSQL with Alembic migrations
- **ORM**: SQLAlchemy with async support
- **Workflow**: Prefect for orchestration
- **AI/ML**: OpenAI/LLM integration
- **Deployment**: Docker containerization

## 🚀 **Quick Start**

### **1. Prerequisites**
- Python 3.11 or higher
- PostgreSQL 15+
- Docker (optional, for containerized setup)
- Git

### **2. Clone and Setup**
```bash
# Clone the repository
git clone <repository-url>
cd CROcashi

# Create virtual environment and install dependencies
make setup

# Activate virtual environment
source .venv/bin/activate
```

### **3. Configure Environment**
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
# Required: DATABASE_URL, OPENAI_API_KEY
# Optional: Other service configurations
```

### **4. Database Setup**
```bash
# Start PostgreSQL (adjust for your setup)
docker run -d --name postgres \
  -e POSTGRES_PASSWORD=ncfd \
  -e POSTGRES_USER=ncfd \
  -e POSTGRES_DB=ncfd \
  -p 5432:5432 postgres:15

# Run database migrations
export DATABASE_URL="postgresql://ncfd:ncfd@localhost:5432/ncfd"
alembic upgrade head
```

### **5. Verify Installation**
```bash
# Run the main validation script
python scripts/validate_phase6_pipeline.py

# Expected: 100% validation success rate ✅
```

## 🧪 **Testing & Validation**

### **Run Complete Test Suite**
```bash
# Run all tests
make test

# Run with coverage
pytest --cov=src/ncfd tests/
```

### **Individual Component Tests**
```bash
# Test signal detection
python scripts/demo_signals_and_gates.py

# Test scoring system
python scripts/demo_scoring_system.py

# Test testing framework
python scripts/demo_testing_validation.py

# Test complete pipeline
python scripts/demo_pipeline_integration.py
```

### **Integration Tests**
```bash
# Test document ingestion
python scripts/test_document_ingest.py

# Test pipeline integration
python scripts/demo_pipeline_integration.py

# Test storage system
python scripts/demo_storage_system.py
```

## 🔧 **Development Commands**

### **Code Quality**
```bash
# Check for issues
make lint

# Auto-fix formatting
make fmt

# Type checking
mypy src/
```

### **Database Operations**
```bash
# Run migrations
make db_migrate

# Reset database
make db_reset

# Check migration status
alembic current
```

### **Environment Management**
```bash
# Install dependencies
make install

# Update dependencies
make update

# Clean environment
make clean
```

## 📁 **Repository Structure**

```
CROcashi/
├── src/ncfd/                    # Main application code
│   ├── signals/                 # Signal detection (S1-S9)
│   ├── gates/                   # Gate analysis (G1-G4)
│   ├── scoring/                 # Bayesian scoring system
│   ├── mapping/                 # Company resolution & linking
│   ├── extract/                 # Document processing & extraction
│   ├── ingest/                  # Data ingestion & validation
│   ├── pipeline/                # Workflow orchestration
│   ├── storage/                 # File storage management
│   ├── catalyst/                # Catalyst window inference
│   └── db/                      # Database models & sessions
├── alembic/                     # Database migrations
├── tests/                       # Test suite
├── scripts/                     # Validation & demo scripts
├── config/                      # Configuration files
├── monitoring/                  # Prometheus & Grafana configs
├── nginx/                       # Web server configuration
├── docs/                        # Documentation
│   ├── CODE_REVIEWER_GUIDE.md  # External reviewer guide
│   └── [other documentation]
└── [configuration files]
```

## 📊 **System Capabilities**

### **Signal Detection (S1-S9)**
- **S1**: Endpoint change detection
- **S2**: Sample size modifications
- **S3**: Analysis plan changes
- **S4**: Sponsor pattern analysis
- **S5**: Historical failure correlation
- **S6**: Regulatory submission delays
- **S7**: Publication pattern analysis
- **S8**: Financial distress indicators
- **S9**: Management turnover signals

### **Gate Analysis (G1-G4)**
- **G1**: High-risk signal combination
- **G2**: Sponsor reliability assessment
- **G3**: Trial design quality evaluation
- **G4**: Market sentiment integration

### **Scoring System**
- **Bayesian probability** calculation
- **Confidence intervals** for risk assessment
- **Historical calibration** for accuracy
- **Real-time updates** as new data arrives

## 🔒 **Security & Configuration**

### **Environment Variables**
```bash
# Required
DATABASE_URL=postgresql://user:pass@host:port/db
OPENAI_API_KEY=your_openai_api_key

# Optional
LOG_LEVEL=INFO
STORAGE_BACKEND=local  # or s3
S3_BUCKET=your_bucket_name
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
```

### **API Security**
- API keys stored in environment variables
- Rate limiting on external API calls
- Input validation and sanitization
- Secure credential management

## 📈 **Performance & Scalability**

### **Optimizations**
- **Database indexing** on frequently queried columns
- **Connection pooling** for database efficiency
- **Async processing** for I/O operations
- **Caching strategies** for repeated calculations
- **Batch processing** for large datasets

### **Monitoring**
- **Prometheus metrics** for system health
- **Grafana dashboards** for visualization
- **Log aggregation** for debugging
- **Performance profiling** for optimization

## 🚀 **Deployment**

### **Docker Deployment**
```bash
# Production deployment
docker-compose -f docker-compose.prod.yml up -d

# Development deployment
docker-compose up -d
```

### **Manual Deployment**
```bash
# Install dependencies
pip install -e .

# Run migrations
alembic upgrade head

# Start services
python -m ncfd.api.main
```

## 📚 **Documentation**

### **For Users**
- **README.md** (this file) - Setup and usage
- **CODE_REVIEWER_GUIDE.md** - External review guide

### **For Developers**
- **API Documentation** - Endpoint specifications
- **Database Schema** - Table structures and relationships
- **Migration History** - Database change tracking
- **Test Coverage** - Code quality metrics

### **For Operations**
- **Deployment Guides** - Production setup instructions
- **Monitoring Setup** - Metrics and alerting configuration
- **Troubleshooting** - Common issues and solutions

## 🤝 **Contributing**

### **Development Workflow**
1. **Fork** the repository
2. **Create** a feature branch
3. **Implement** your changes
4. **Test** thoroughly
5. **Submit** a pull request

### **Code Standards**
- **Type hints** required for all functions
- **Docstrings** for public APIs
- **Tests** for new functionality
- **Linting** must pass
- **Formatting** must be consistent

### **Testing Requirements**
- **Unit tests** for all new code
- **Integration tests** for complex features
- **Performance tests** for critical paths
- **Coverage** should not decrease

## 🐛 **Troubleshooting**

### **Common Issues**
- **Database connection**: Check DATABASE_URL and PostgreSQL status
- **Import errors**: Ensure virtual environment is activated
- **Migration issues**: Verify alembic chain with `alembic history`
- **Test failures**: Check dependencies and environment setup

### **Getting Help**
1. **Check logs** in the `logs/` directory
2. **Review error messages** for specific details
3. **Consult documentation** in the `docs/` directory
4. **Run validation scripts** to isolate issues
5. **Contact the team** with specific error details

## 📄 **License**

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 **Acknowledgments**

- **Clinical trial data** from ClinicalTrials.gov
- **Financial data** from SEC filings and market sources
- **Machine learning** powered by OpenAI
- **Open source** community for tools and libraries

---

## 🎯 **Next Steps**

1. **Review the CODE_REVIEWER_GUIDE.md** for detailed analysis
2. **Run the validation scripts** to verify functionality
3. **Explore the test suite** to understand capabilities
4. **Check the documentation** for specific use cases
5. **Contact the team** for questions or support

**Ready to detect trial failures with near-certainty?** 🚀