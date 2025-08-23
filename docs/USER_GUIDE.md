# CROcashi User Guide

## 📖 **Overview**

CROcashi is a comprehensive clinical trial monitoring system that automatically ingests and processes data from ClinicalTrials.gov and SEC filings to provide real-time insights into clinical development activities.

This guide covers:
- System setup and configuration
- Daily operations and monitoring
- Data quality management
- Troubleshooting and maintenance
- Advanced features and customization

---

## 🚀 **Quick Start**

### **1. System Requirements**
- Python 3.8+
- PostgreSQL 12+
- 8GB+ RAM
- 100GB+ disk space
- Internet access for API calls

### **2. Installation**
```bash
# Clone repository
git clone <repository-url>
cd CROcashi

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp env.example .env
# Edit .env with your configuration

# Install in development mode
pip install -e .
```

### **3. Initial Setup**
```bash
# Set up database
export DATABASE_URL="postgresql://user:password@localhost:5432/crocashi"
alembic upgrade head

# Verify installation
python scripts/run_tests.py --category quick
```

---

## ⚙️ **Configuration**

### **Environment Variables**
Create a `.env` file with the following variables:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/crocashi

# API Keys (if required)
CLINICALTRIALS_API_KEY=your_api_key
SEC_EDGAR_EMAIL=your_email@domain.com

# Monitoring
ENABLE_MONITORING=true
ALERT_EMAIL=alerts@yourdomain.com

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/crocashi.log
```

### **Configuration Files**

#### **CT.gov Configuration** (`config/ctgov_config.yaml`)
```yaml
api:
  base_url: "https://clinicaltrials.gov/api/v2"
  timeout: 30
  max_retries: 3

rate_limiting:
  requests_per_second: 2
  burst_limit: 10

change_detection:
  enabled: true
  hash_fields: ["brief_title", "detailed_description", "enrollment_count"]
  min_change_threshold: 0.1
```

#### **SEC Configuration** (`config/sec_config.yaml`)
```yaml
api:
  base_url: "https://www.sec.gov/Archives/edgar/data"
  timeout: 30
  max_retries: 3

rate_limiting:
  requests_per_second: 0.5  # 2 requests per minute
  burst_limit: 5

parsing:
  max_document_size_mb: 50
  extract_sections: true
  section_strategies: ["html_outline", "regex", "manual"]
```

#### **Pipeline Configuration** (`config/pipeline_config.yaml`)
```yaml
orchestration:
  max_concurrent_pipelines: 2
  dependency_timeout_minutes: 30
  retry_failed_pipelines: true
  max_retries: 3

pipelines:
  ctgov:
    enabled: true
    schedule: "0 2 * * *"  # Daily at 2 AM
    priority: "high"
  
  sec:
    enabled: true
    schedule: "0 3 * * *"  # Daily at 3 AM
    priority: "medium"

monitoring:
  enable_monitoring: true
  track_execution_history: true
  alert_thresholds:
    error_rate_above: 0.1
    quality_score_below: 0.6
```

---

## 🏃‍♂️ **Daily Operations**

### **1. Manual Pipeline Execution**

#### **Run Daily Ingestion**
```bash
# Run complete daily ingestion
python -c "
from src.ncfd.pipeline.unified_orchestrator import UnifiedPipelineOrchestrator
from src.ncfd.config import load_config

config = load_config()
orchestrator = UnifiedPipelineOrchestrator(config)
results = orchestrator.run_daily_ingestion()
print('Daily ingestion completed:', results)
"
```

#### **Run Individual Pipelines**
```bash
# CT.gov pipeline only
python -c "
from src.ncfd.pipeline.ctgov_pipeline import CTGovPipeline
from src.ncfd.config import load_config

config = load_config()
pipeline = CTGovPipeline(config)
result = pipeline.execute()
print('CT.gov pipeline result:', result)
"

# SEC pipeline only
python -c "
from src.ncfd.pipeline.sec_pipeline import SecPipeline
from src.ncfd.config import load_config

config = load_config()
pipeline = SecPipeline(config)
result = pipeline.execute()
print('SEC pipeline result:', result)
"
```

### **2. Monitoring and Status**

#### **Check Pipeline Status**
```bash
# Get execution status
python -c "
from src.ncfd.pipeline.unified_orchestrator import UnifiedPipelineOrchestrator
from src.ncfd.config import load_config

config = load_config()
orchestrator = UnifiedPipelineOrchestrator(config)
status = orchestrator.get_execution_status()
print('Pipeline status:', status)
"
```

#### **Check Pipeline Health**
```bash
# Get health metrics
python -c "
from src.ncfd.pipeline.unified_orchestrator import UnifiedPipelineOrchestrator
from src.ncfd.config import load_config

config = load_config()
orchestrator = UnifiedPipelineOrchestrator(config)
health = orchestrator.get_pipeline_health('ctgov')
print('CT.gov health:', health)
"
```

### **3. Data Quality Monitoring**

#### **Run Quality Validation**
```bash
# Validate recent data
python -c "
from src.ncfd.quality.data_quality import DataQualityFramework
from src.ncfd.config import load_config

config = load_config()
framework = DataQualityFramework(config)
report = framework.generate_quality_report()
print('Quality report:', report)
"
```

#### **Check Quality Trends**
```bash
# Get quality trends
python -c "
from src.ncfd.quality.data_quality import DataQualityFramework
from src.ncfd.config import load_config

config = load_config()
framework = DataQualityFramework(config)
trends = framework.get_quality_trends(days=30)
print('Quality trends:', trends)
"
```

---

## 📊 **Monitoring and Alerting**

### **1. Pipeline Monitor**

#### **Start Monitoring**
```bash
# Start the monitoring system
python -c "
from src.ncfd.monitoring.pipeline_monitor import PipelineMonitor
from src.ncfd.config import load_config

config = load_config()
monitor = PipelineMonitor(config)
monitor.start_monitoring()
print('Monitoring started')
"
```

#### **Get Monitoring Status**
```bash
# Check monitoring status
python -c "
from src.ncfd.monitoring.pipeline_monitor import PipelineMonitor
from src.ncfd.config import load_config

config = load_config()
monitor = PipelineMonitor(config)
status = monitor.get_monitoring_status()
print('Monitoring status:', status)
"
```

#### **Generate Monitoring Report**
```bash
# Generate comprehensive report
python -c "
from src.ncfd.monitoring.pipeline_monitor import PipelineMonitor
from src.ncfd.config import load_config

config = load_config()
monitor = PipelineMonitor(config)
report = monitor.generate_monitoring_report()
print('Monitoring report:', report)
"
```

### **2. Alert Management**

#### **View Active Alerts**
```bash
# Check active alerts
python -c "
from src.ncfd.monitoring.pipeline_monitor import PipelineMonitor
from src.ncfd.config import load_config

config = load_config()
monitor = PipelineMonitor(config)
print('Active alerts:', len(monitor.active_alerts))
for alert in monitor.active_alerts:
    print(f'- {alert.title} ({alert.severity.value})')
"
```

#### **Acknowledge Alerts**
```bash
# Acknowledge an alert
python -c "
from src.ncfd.monitoring.pipeline_monitor import PipelineMonitor
from src.ncfd.config import load_config

config = load_config()
monitor = PipelineMonitor(config)
# Replace 'alert_id' with actual alert ID
monitor.acknowledge_alert('alert_id', 'your_username')
print('Alert acknowledged')
"
```

---

## 🔧 **Maintenance and Troubleshooting**

### **1. Common Issues**

#### **Pipeline Failures**
```bash
# Check pipeline execution history
python -c "
from src.ncfd.pipeline.unified_orchestrator import UnifiedPipelineOrchestrator
from src.ncfd.config import load_config

config = load_config()
orchestrator = UnifiedPipelineOrchestrator(config)
history = orchestrator.execution_history
print('Recent executions:', history)
"
```

#### **Data Quality Issues**
```bash
# Investigate quality problems
python -c "
from src.ncfd.quality.data_quality import DataQualityFramework
from src.ncfd.config import load_config

config = load_config()
framework = DataQualityFramework(config)
# Get recent validation results
recent_results = framework.quality_history[-5:] if framework.quality_history else []
print('Recent quality results:', recent_results)
"
```

### **2. Performance Optimization**

#### **Check System Resources**
```bash
# Monitor system performance
python -c "
from src.ncfd.monitoring.pipeline_monitor import PipelineMonitor
from src.ncfd.config import load_config

config = load_config()
monitor = PipelineMonitor(config)
monitor.update_system_metrics()
summary = monitor.get_system_performance_summary(hours=24)
print('System performance:', summary)
"
```

#### **Optimize Pipeline Settings**
```yaml
# In pipeline_config.yaml
orchestration:
  max_concurrent_pipelines: 1  # Reduce for resource-constrained systems
  dependency_timeout_minutes: 60  # Increase for slower systems

pipelines:
  ctgov:
    batch_size: 100  # Reduce batch size for memory issues
    max_workers: 2   # Reduce worker count for CPU issues
```

### **3. Data Recovery**

#### **Backfill Data**
```bash
# Run backfill for specific period
python -c "
from src.ncfd.pipeline.unified_orchestrator import UnifiedPipelineOrchestrator
from src/ncfd.config import load_config

config = load_config()
orchestrator = UnifiedPipelineOrchestrator(config)
result = orchestrator.run_backfill(
    pipeline_name='ctgov',
    start_date='2024-01-01',
    end_date='2024-01-31'
)
print('Backfill result:', result)
"
```

#### **Clear Execution History**
```bash
# Clear old execution history
python -c "
from src.ncfd.pipeline.unified_orchestrator import UnifiedPipelineOrchestrator
from src.ncfd.config import load_config

config = load_config()
orchestrator = UnifiedPipelineOrchestrator(config)
orchestrator.clear_execution_history(keep_last=100)
print('Execution history cleared')
"
```

---

## 🧪 **Testing and Validation**

### **1. Run Tests**

#### **Quick Tests**
```bash
# Run quick smoke tests
python scripts/run_tests.py --category quick
```

#### **Full Test Suite**
```bash
# Run all tests
python scripts/run_tests.py --category all
```

#### **Specific Test Categories**
```bash
# Test data quality framework
python scripts/run_tests.py --category data_quality

# Test monitoring system
python scripts/run_tests.py --category monitoring

# Test ingestion systems
python scripts/run_tests.py --category ingestion
```

#### **Coverage Analysis**
```bash
# Run tests with coverage
python scripts/run_tests.py --coverage
```

### **2. Test Individual Components**

#### **Test CT.gov Client**
```bash
# Test CT.gov client functionality
python -c "
from tests.test_ctgov_client import TestCTGovClient
import pytest

# Run specific test
test_client = TestCTGovClient()
test_client.test_client_initialization()
print('CT.gov client test passed')
"
```

#### **Test Data Quality Framework**
```bash
# Test data quality framework
python -c "
from tests.test_data_quality import TestDataQualityFramework
import pytest

# Run specific test
test_framework = TestDataQualityFramework()
test_framework.test_framework_initialization()
print('Data quality framework test passed')
"
```

---

## 📈 **Advanced Features**

### **1. Custom Validation Rules**

#### **Add Custom Rule**
```python
from src.ncfd.quality.data_quality import DataQualityFramework, ValidationRule, ValidationSeverity

# Create custom validation rule
custom_rule = ValidationRule(
    rule_id="custom_trial_rule",
    name="Custom Trial Validation",
    description="Custom validation for trial data",
    severity=ValidationSeverity.HIGH,
    category="trial",
    parameters={"threshold": 0.8}
)

# Add to framework
framework = DataQualityFramework(config)
framework.add_validation_rule(custom_rule)
```

#### **Custom Validation Logic**
```python
# Implement custom validation logic
def validate_custom_trial_data(trial_data, rule):
    """Custom trial validation logic."""
    # Your custom validation logic here
    if trial_data.get("enrollment_count", 0) < 100:
        return ValidationResult(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            status=ValidationStatus.FAIL,
            severity=rule.severity,
            message="Enrollment count too low"
        )
    return ValidationResult(
        rule_id=rule.rule_id,
        rule_name=rule.name,
        status=ValidationStatus.PASS,
        severity=rule.severity,
        message="Validation passed"
    )
```

### **2. Custom Alert Channels**

#### **Add Custom Alert Channel**
```python
from src.ncfd.monitoring.pipeline_monitor import PipelineMonitor

class CustomPipelineMonitor(PipelineMonitor):
    def _send_custom_alert(self, alert):
        """Send alert through custom channel."""
        # Your custom alert logic here
        print(f"Custom alert: {alert.title}")
        
        # Example: Send to webhook
        import requests
        requests.post("https://your-webhook.com/alerts", json={
            "title": alert.title,
            "message": alert.message,
            "severity": alert.severity.value
        })

# Use custom monitor
monitor = CustomPipelineMonitor(config)
monitor.alert_channels.append("custom")
```

### **3. Custom Pipeline Logic**

#### **Extend Pipeline Class**
```python
from src.ncfd.pipeline.ctgov_pipeline import CTGovPipeline

class CustomCTGovPipeline(CTGovPipeline):
    def pre_process_data(self, trial_data):
        """Custom pre-processing logic."""
        # Your custom logic here
        if trial_data.get("phase") == "PHASE3":
            trial_data["priority"] = "high"
        return trial_data
    
    def post_process_data(self, trial_data):
        """Custom post-processing logic."""
        # Your custom logic here
        trial_data["processed_at"] = datetime.utcnow().isoformat()
        return trial_data

# Use custom pipeline
pipeline = CustomCTGovPipeline(config)
```

---

## 📚 **Reference**

### **Configuration Options**

#### **Environment Variables**
| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |
| `ENABLE_MONITORING` | Enable monitoring system | true |
| `ALERT_EMAIL` | Email for alerts | None |

#### **Pipeline Settings**
| Setting | Description | Default |
|---------|-------------|---------|
| `max_concurrent_pipelines` | Maximum concurrent pipeline executions | 2 |
| `dependency_timeout_minutes` | Timeout for pipeline dependencies | 30 |
| `retry_failed_pipelines` | Automatically retry failed pipelines | true |
| `max_retries` | Maximum retry attempts | 3 |

### **API Endpoints**

#### **CT.gov API**
- **Base URL**: `https://clinicaltrials.gov/api/v2`
- **Rate Limit**: 2 requests/second
- **Authentication**: API key (optional)
- **Documentation**: [ClinicalTrials.gov API](https://clinicaltrials.gov/api/gui/home)

#### **SEC EDGAR**
- **Base URL**: `https://www.sec.gov/Archives/edgar/data`
- **Rate Limit**: 2 requests/minute
- **Authentication**: User-Agent header required
- **Documentation**: [SEC EDGAR](https://www.sec.gov/edgar/searchedgar/accessing-edgar-data)

### **Data Models**

#### **Trial Data Structure**
```python
{
    "nct_id": "NCT12345678",
    "brief_title": "Trial Title",
    "sponsor_name": "Sponsor Name",
    "phase": "PHASE2",
    "status": "RECRUITING",
    "enrollment_count": 100,
    "study_type": "INTERVENTIONAL",
    "arms": [...],
    "interventions": [...],
    "outcome_measures": [...]
}
```

#### **SEC Filing Structure**
```python
{
    "cik": "0001234567",
    "accession_number": "0001234567-24-000001",
    "form_type": "8-K",
    "filing_date": "2024-01-15",
    "document_path": "filing.txt",
    "content": "...",
    "sections": [...]
}
```

---

## 🆘 **Support and Troubleshooting**

### **Getting Help**

1. **Check Logs**: Review log files for error details
2. **Run Tests**: Use test suite to identify issues
3. **Check Status**: Verify pipeline and monitoring status
4. **Review Configuration**: Ensure all settings are correct

### **Common Error Codes**

| Error | Description | Solution |
|-------|-------------|----------|
| `DATABASE_URL not set` | Database connection missing | Set `DATABASE_URL` environment variable |
| `API rate limit exceeded` | Too many API requests | Check rate limiting configuration |
| `Pipeline dependency failed` | Required pipeline failed | Check dependency pipeline status |
| `Data validation failed` | Data quality issues | Review validation rules and data |

### **Performance Tuning**

1. **Reduce concurrency** for resource-constrained systems
2. **Increase timeouts** for slower networks
3. **Optimize batch sizes** for memory usage
4. **Enable caching** for repeated API calls

---

**Last Updated**: 2025-01-22
**Version**: 1.0.0
**Support**: Check repository issues or documentation
