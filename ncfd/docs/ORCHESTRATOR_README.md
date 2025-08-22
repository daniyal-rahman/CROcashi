# CROcashi Orchestrator

**Complete Pipeline Orchestration for Literature Review and Asset Extraction**

## 🎯 **Overview**

The CROcashi Orchestrator is the central coordination system that:

1. **Filters CT.gov trials** for public companies meeting investment criteria
2. **Runs literature review pipeline** on filtered companies only
3. **Extracts and links assets** from company documents
4. **Prepares data** for LLM analysis and red flag detection
5. **Generates company dossiers** for investment decision making

**Key Benefit**: Your original CT.gov data remains intact while the orchestrator creates filtered subsets for investment analysis.

## 🚀 **Quick Start**

### **Basic Usage**

```python
from ncfd.pipeline.orchestrator import CROcashiOrchestrator
from ncfd.db.session import get_db_session

# Initialize
db_session = get_db_session()
orchestrator = CROcashiOrchestrator(db_session)

# Run complete pipeline with default filters
result = orchestrator.run_complete_pipeline()

print(f"Processed {result.companies_processed} companies")
print(f"Extracted {result.assets_extracted} assets")
```

### **CLI Usage**

```bash
# Run with default investment filters ($100M+ market cap, US exchanges)
python scripts/run_pipeline.py

# Conservative filter ($1B+ market cap only)
python scripts/run_pipeline.py --min-market-cap 1000000000

# Aggressive filter (include $50M+ companies)
python scripts/run_pipeline.py --min-market-cap 50000000

# Specific companies only
python scripts/run_pipeline.py --mode company-specific --company-ids 123 456 789

# Dry run (analysis only)
python scripts/run_pipeline.py --dry-run
```

## 🔧 **Configuration**

### **Company Filtering Options**

```python
from ncfd.pipeline.orchestrator import CompanyFilter

# Conservative filter
conservative_filter = CompanyFilter(
    min_market_cap=1_000_000_000,  # $1B minimum
    exchanges=['NASDAQ', 'NYSE'],   # Major exchanges only
    exclude_countries=['CN', 'HK'], # Exclude China/Hong Kong
    min_trial_count=2,              # At least 2 trials
    include_private=False           # Public companies only
)

# Aggressive filter
aggressive_filter = CompanyFilter(
    min_market_cap=50_000_000,     # $50M minimum
    exchanges=['NASDAQ', 'NYSE', 'NYSE American', 'OTCQX'],
    exclude_countries=['CN', 'HK'],
    min_trial_count=1,
    include_private=False
)
```

### **Pipeline Configuration**

```python
from ncfd.pipeline.orchestrator import PipelineConfig

config = PipelineConfig(
    max_documents_per_company=100,    # Max docs per company
    max_total_documents=1000,         # Total document limit
    rate_limit_delay=1.0,             # 1 second between requests
    enable_storage=True,               # Enable document storage
    enable_parallel_processing=False  # Sequential processing
)
```

## 📊 **Pipeline Workflow**

### **Step 1: Company Filtering**
The orchestrator automatically filters companies based on:

- **Market Cap**: Configurable minimum/maximum thresholds
- **Exchange**: NASDAQ, NYSE, NYSE American, OTCQX
- **Country**: Excludes China/Hong Kong by default
- **Trial Count**: Minimum number of clinical trials
- **Public Status**: Public companies only (configurable)

### **Step 2: Literature Review Pipeline**
For each filtered company:

1. **Discovery**: Find PR/IR documents and conference abstracts
2. **Fetch**: Download document content
3. **Parse**: Extract text, tables, and metadata
4. **Link**: Create document-entity relationships

### **Step 3: Asset Extraction**
- **Asset Codes**: AB-123, XYZ-456 patterns
- **Drug Names**: INN and generic names
- **NCT IDs**: Clinical trial identifiers
- **Citations**: DOIs and PMIDs

### **Step 4: Data Preparation (Future)**
- **LLM Analysis**: Prepare data for red flag detection
- **Risk Assessment**: Compile risk factors
- **Competitive Analysis**: Market positioning

### **Step 5: Dossier Generation (Future)**
- **Company Overview**: Business summary
- **Trial Summary**: Clinical trial status
- **Asset Pipeline**: Drug development pipeline
- **Investment Recommendation**: Risk/reward assessment

## 🎛️ **Use Cases**

### **Investment Research**
```python
# Focus on large-cap biotech companies
filter = CompanyFilter(
    min_market_cap=5_000_000_000,  # $5B minimum
    exchanges=['NASDAQ', 'NYSE'],
    min_trial_count=3
)

result = orchestrator.run_complete_pipeline(company_filter=filter)
```

### **Small Cap Discovery**
```python
# Find promising small-cap companies
filter = CompanyFilter(
    min_market_cap=100_000_000,    # $100M minimum
    max_market_cap=1_000_000_000,  # $1B maximum
    exchanges=['NASDAQ', 'NYSE American'],
    min_trial_count=1
)

result = orchestrator.run_complete_pipeline(company_filter=filter)
```

### **Specific Company Analysis**
```python
# Analyze specific companies
company_ids = [123, 456, 789]
result = run_company_specific_pipeline(db_session, company_ids)
```

### **Research Mode**
```python
# Include academic and private companies
filter = CompanyFilter(
    min_market_cap=0,
    exchanges=[],
    exclude_countries=[],
    include_private=True
)

result = orchestrator.run_complete_pipeline(company_filter=filter)
```

## 📈 **Monitoring and Results**

### **Pipeline Status**
```python
# Get current pipeline status
status = orchestrator.get_pipeline_status()
print(f"Current company: {status['current_company']}")
print(f"Documents processed: {status['stats']['documents_parsed']}")
```

### **Execution Results**
```python
result = orchestrator.run_complete_pipeline()

print(f"Execution ID: {result.execution_id}")
print(f"Duration: {result.end_time - result.start_time}")
print(f"Companies: {result.companies_processed}")
print(f"Documents: {result.documents_linked}")
print(f"Assets: {result.assets_extracted}")
```

### **Error Handling**
```python
try:
    result = orchestrator.run_complete_pipeline()
except Exception as e:
    print(f"Pipeline failed: {e}")
    # Check result.errors and result.warnings for details
```

## 🔌 **Future Implementation Hooks**

The orchestrator includes hooks for future features:

### **LLM Analysis Hook**
```python
def _prepare_llm_analysis_data(self):
    # TODO: Implement LLM data preparation
    # - Aggregate company trial data
    # - Prepare document summaries
    # - Create analysis prompts
    # - Set up LLM service integration
    pass
```

### **Dossier Generation Hook**
```python
def _generate_company_dossiers(self):
    # TODO: Implement dossier generation
    # - Compile company trial summaries
    # - Aggregate literature findings
    # - Generate risk assessments
    # - Create investment recommendations
    pass
```

## ⚙️ **Configuration File**

The orchestrator can use a YAML configuration file:

```yaml
# config/pipeline_config.yaml
default_company_filter:
  min_market_cap: 100_000_000
  exchanges: [NASDAQ, NYSE, NYSE American]
  exclude_countries: [CN, HK]

pipeline_config:
  max_documents_per_company: 100
  max_total_documents: 1000
  rate_limit_delay: 1.0
```

## 🧪 **Testing**

### **Dry Run Mode**
```bash
# Test pipeline without making changes
python scripts/run_pipeline.py --dry-run --verbose
```

### **Unit Tests**
```bash
# Run orchestrator tests
python -m pytest tests/test_orchestrator.py -v
```

## 🚨 **Troubleshooting**

### **Common Issues**

1. **No Companies Found**
   - Check market cap thresholds
   - Verify exchange filters
   - Ensure companies have trials

2. **Document Discovery Fails**
   - Check company domain configuration
   - Verify network connectivity
   - Review rate limiting settings

3. **Asset Extraction Issues**
   - Check document parsing status
   - Verify asset extraction patterns
   - Review confidence thresholds

### **Debug Mode**
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Run with verbose logging
orchestrator.run_complete_pipeline()
```

## 📚 **API Reference**

### **CROcashiOrchestrator**

- `run_complete_pipeline(company_filter, dry_run)` - Run complete pipeline
- `get_pipeline_status()` - Get current status
- `reset_pipeline_stats()` - Reset statistics

### **CompanyFilter**

- `min_market_cap` - Minimum market cap
- `exchanges` - Stock exchanges to include
- `exclude_countries` - Countries to exclude
- `min_trial_count` - Minimum trials per company

### **PipelineConfig**

- `max_documents_per_company` - Document limit per company
- `max_total_documents` - Total document limit
- `rate_limit_delay` - Request delay in seconds

## 🎯 **Next Steps**

With the orchestrator in place, you can now:

1. **Filter CT.gov trials** for investment-worthy companies
2. **Run literature review** on filtered companies only
3. **Extract assets** automatically from company documents
4. **Prepare data** for future LLM analysis
5. **Generate dossiers** for investment decisions

The system maintains your original data while creating focused investment analysis pipelines.

**Ready for Phase 5**: Study Card extraction with LangExtract can now proceed with confidence that the orchestrator will filter for the right companies.
