# Phase 4 Quick Reference Guide

**Literature Review Pipeline - Ready to Use**

## 🚀 **Quick Start**

### **1. Basic Usage**
```python
from ncfd.ingest.document_ingest import DocumentIngester
from ncfd.db.session import get_db_session

# Initialize
db_session = get_db_session()
ingester = DocumentIngester(db_session)

# Run full pipeline
results = ingester.run_full_pipeline(
    company_domains=['biotech-company.com'],
    max_docs=50
)
```

### **2. Individual Jobs**
```python
# Discovery only
sources = ingester.run_discovery_job(['company.com'])

# Fetch documents
fetched = ingester.run_fetch_job(sources, max_docs=100)

# Parse content
parsed = ingester.run_parse_job(fetched)

# Link entities
linked = ingester.run_link_job(parsed)
```

## 🔍 **Asset Extraction**

### **Extract Asset Codes**
```python
from ncfd.extract.asset_extractor import extract_asset_codes

text = "Compound AB-123 showed efficacy in Phase 2."
matches = extract_asset_codes(text)

for match in matches:
    print(f"Found: {match.value_text} at position {match.char_start}-{match.char_end}")
```

### **Extract Drug Names**
```python
from ncfd.extract.asset_extractor import extract_all_entities

# Extract all entity types
entities = extract_all_entities(text, page_no=1)
```

### **Normalize Drug Names**
```python
from ncfd.extract.asset_extractor import norm_drug_name

normalized = norm_drug_name("α-Tocopherol®")  # Returns: "alpha-tocopherol"
```

## 📚 **INN Dictionary**

### **Initialize Dictionary Manager**
```python
from ncfd.extract.inn_dictionary import INNDictionaryManager

inn_manager = INNDictionaryManager(db_session)

# Load dictionaries
inn_manager.load_chembl_dictionary("path/to/chembl.json")
inn_manager.load_who_inn_dictionary("path/to/who_inn.json")

# Build alias map
alias_map = inn_manager.build_alias_norm_map()
```

### **Discover Assets**
```python
# Find assets in text
discoveries = inn_manager.discover_assets("Patient received aspirin and metformin.")

for discovery in discoveries:
    print(f"Found: {discovery.value_text} ({discovery.alias_type})")
    print(f"Confidence: {discovery.confidence}")
```

## 🌐 **Document Discovery**

### **Company PR/IR Discovery**
```python
# Discover from company domains
domains = ['biotech-company.com', 'pharma-company.org']
sources = ingester.discover_company_pr_ir(domains)

for source in sources:
    print(f"Found: {source['title']} at {source['url']}")
    print(f"Type: {source['source_type']}")
```

### **Conference Abstract Discovery**
```python
# Discover conference sources
sources = ingester.discover_conference_abstracts()

# Sources include:
# - AACR: Cancer Research Proceedings
# - ASCO: Journal of Clinical Oncology
# - ESMO: Annals of Oncology
```

## 🔗 **Entity Linking**

### **Linking Heuristics**
The system automatically applies these heuristics:

1. **HP-1 (NCT near asset)**: Links assets within 250 characters of NCT IDs
2. **HP-2 (Exact intervention match)**: Direct name matching
3. **HP-3 (Company PR bias)**: Boosts confidence for company-hosted documents
4. **HP-4 (Abstract specificity)**: Conference abstract confidence scoring

### **Manual Linking**
```python
# Create document links manually
from ncfd.db.models import DocumentLink

link = DocumentLink(
    doc_id=doc.doc_id,
    asset_id=asset.asset_id,
    link_type='manual_link',
    confidence=0.95
)
db_session.add(link)
db_session.commit()
```

## 📊 **Monitoring & Results**

### **Pipeline Results**
```python
results = ingester.run_full_pipeline()

print(f"Discovery: {results['discovery']['total_sources']} sources")
print(f"Fetch: {results['fetch']['total_fetched']} documents")
print(f"Parse: {results['parse']['total_parsed']} parsed")
print(f"Link: {results['link']['total_linked']} linked")
```

### **Job Tracking**
```python
# Each job logs its progress
# Check logs for detailed information about each stage

# Example log output:
# INFO: Starting discovery job
# INFO: Discovered 7 conference sources
# INFO: Discovery job completed: 7 sources found
```

## ⚙️ **Configuration**

### **Environment Variables**
```bash
# Storage configuration
STORAGE_BACKEND=s3
S3_BUCKET=documents
S3_ACCESS_KEY=your_key
S3_SECRET_KEY=your_secret

# Rate limiting
MAX_REQUESTS_PER_MINUTE=60
REQUEST_TIMEOUT=30
```

### **Company Domains**
```python
# Configure company domains for PR/IR discovery
COMPANY_DOMAINS = [
    'biotech-company.com',
    'pharma-company.org',
    'therapeutics-inc.com'
]
```

## 🧪 **Testing**

### **Run Test Suite**
```bash
# Test asset extraction
python -m pytest tests/test_asset_extractor.py -v

# Test document ingestion
python -m pytest tests/test_document_ingest.py -v

# Test full Phase 4 pipeline
python scripts/test_phase4_pipeline.py
```

### **Test Individual Components**
```python
# Test asset extraction
from ncfd.extract.asset_extractor import extract_asset_codes
matches = extract_asset_codes("Test compound AB-123")
assert len(matches) > 0

# Test drug normalization
from ncfd.extract.asset_extractor import norm_drug_name
result = norm_drug_name("α-Tocopherol®")
assert result == "alpha-tocopherol"
```

## 🚨 **Troubleshooting**

### **Common Issues**

1. **Import Errors**
   ```python
   # Ensure src is in Python path
   import sys
   sys.path.insert(0, 'src')
   ```

2. **Database Connection**
   ```python
   # Check database connection
   from ncfd.db.session import get_db_session
   session = get_db_session()
   ```

3. **Storage Backend**
   ```python
   # Verify storage configuration
   ingester = DocumentIngester(db_session, storage_config={
       'backend': 's3',
       'bucket': 'your-bucket'
   })
   ```

### **Debug Mode**
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Run with verbose logging
ingester.run_full_pipeline()
```

## 📈 **Performance Tips**

### **Batch Processing**
```python
# Process in smaller batches for better memory management
results = ingester.run_full_pipeline(max_docs=50)

# For large datasets, process incrementally
sources = ingester.run_discovery_job()
for batch in chunks(sources, 100):
    fetched = ingester.run_fetch_job(batch)
    parsed = ingester.run_parse_job(fetched)
    linked = ingester.run_link_job(parsed)
```

### **Rate Limiting**
```python
# Configure rate limiting for external requests
ingester = DocumentIngester(
    db_session,
    storage_config={'rate_limit': 60}  # 60 requests per minute
)
```

## 🎯 **Next Steps**

Phase 4 is complete! You can now:

1. **Ingest documents** from company and conference sources
2. **Extract assets** using regex patterns and dictionary lookups
3. **Link entities** with confidence-scored heuristics
4. **Process at scale** with the orchestrated pipeline

**Ready for Phase 5**: Study Card extraction with LangExtract
