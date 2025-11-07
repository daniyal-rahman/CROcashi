# Entity Resolution System - Quick Start Guide

## Overview

This entity resolution system automatically matches entities (companies, drugs, diseases, clinical trials, etc.) across 100+ data sources using a sophisticated 6-level hierarchical matching strategy with confidence scoring.

## Quick Start

### 1. Setup Database

```bash
# Run migrations to create tables
alembic upgrade head

# Initialize database with extensions
python database/init_db.py
```

### 2. Process Data

```python
from src.processing.pipeline import ProcessingPipeline

# Create pipeline
pipeline = ProcessingPipeline(batch_size=100)

# Process a source
stats = pipeline.process_source('clinicaltrials_gov', limit=1000)

print(f"Processed: {stats['records_processed']}")
print(f"Auto-matched: {stats['entities_matched']}")
print(f"New entities: {stats['entities_created']}")
print(f"Needs review: {stats['needs_review']}")
```

### 3. Review Ambiguous Matches

```bash
# Interactive review CLI
python -m src.tools.review_matches --entity-type drug --limit 20

# Show review queue stats
python -m src.tools.review_matches --stats
```

### 4. Monitor Processing

```bash
# Show dashboard
python -m src.tools.monitor_processing --days 7

# Filter by source
python -m src.tools.monitor_processing --source clinicaltrials_gov
```

## Architecture

### Hierarchical Matching (6 Levels)

1. **Level 1**: Exact Identifier (NCT ID, PMID, etc.) → Confidence: 1.0
2. **Level 2**: Exact Name Match (normalized) → Confidence: 0.95
3. **Level 3**: Alias Lookup → Confidence: 0.90
4. **Level 4**: Fuzzy Match + Context → Confidence: 0.70-0.89
5. **Level 5**: Fuzzy Match Alone → Confidence: 0.60-0.79
6. **Level 6**: No Match → Create New Entity

### Confidence Scoring

```python
base_score = trigram_similarity(name1, name2)  # PostgreSQL pg_trgm

# Context boosting
if same_company:     +0.10
if same_disease:     +0.05
if same_mechanism:   +0.05
if same_target:      +0.05
if same_time_period: +0.05  # Within 6 months

final_score = min(1.0, base_score + context_boost)
```

**Decision Thresholds**:
- ≥ 0.90: Auto-match (high confidence)
- 0.75-0.89: Auto-match + flag for review
- 0.60-0.74: Manual review required
- < 0.60: Likely no match

## Adding a New Source Processor

### Step 1: Create Processor Class

```python
from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import EntityType, ExtractedEntity

class MySourceProcessor(BaseProcessor):
    SOURCE_NAME = "my_source"
    
    def get_source_identifier(self, raw_data):
        return raw_data['id']
    
    def extract_entities(self, raw_data):
        entities = {
            'companies': [],
            'drugs': [],
            # ... other entity types
        }
        
        # Extract company
        if 'company_name' in raw_data:
            company = ExtractedEntity(
                entity_type=EntityType.COMPANY,
                name=raw_data['company_name'],
                identifiers={'ticker': raw_data.get('ticker')},
                context={},
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data)
            )
            entities['companies'].append(company)
        
        return entities
    
    def extract_relationships(self, raw_data, resolved_entities):
        # Build relationships after entities are resolved
        relationships = []
        # ... create RelationshipExtraction objects
        return relationships
```

### Step 2: Register Processor

```python
# In src/processing/pipeline.py
PROCESSOR_MAP = {
    'clinicaltrials_gov': ClinicalTrialsProcessor,
    'fda_drugs': FDADrugsProcessor,
    'my_source': MySourceProcessor,  # Add here
}
```

### Step 3: Test

```python
# Create test data in staging
from database.models import StagingRawData

staging = StagingRawData(
    source_system='my_source',
    source_record_id='12345',
    raw_data={'company_name': 'Acme Corp', 'ticker': 'ACME'},
    processed=False
)
session.add(staging)
session.commit()

# Process
pipeline = ProcessingPipeline()
stats = pipeline.process_source('my_source', limit=1)
```

## Configuration

### Matching Rules

Configure matching strategies per entity type in the database:

```sql
INSERT INTO entity_matching_rules (
    rule_id,
    entity_type,
    matching_strategy,
    priority,
    config,
    active
) VALUES (
    gen_random_uuid(),
    'drug',
    'fuzzy_context',
    4,  -- Try after exact_identifier, exact_name, alias
    '{"threshold": 0.75, "use_context": true}'::jsonb,
    true
);
```

### Confidence Thresholds

Edit `src/entity_resolution/confidence_scorer.py`:

```python
class ConfidenceScorer:
    HIGH_CONFIDENCE_THRESHOLD = 0.90  # Auto-match
    MEDIUM_CONFIDENCE_THRESHOLD = 0.75  # Auto-match + flag
    LOW_CONFIDENCE_THRESHOLD = 0.60  # Needs review
```

## Common Tasks

### Check Processing Status

```python
from database.config import get_db_session
from database.models import SourceProcessingLog

with get_db_session() as session:
    logs = session.query(SourceProcessingLog).filter(
        SourceProcessingLog.source_name == 'clinicaltrials_gov',
        SourceProcessingLog.processing_status == 'failed'
    ).all()
    
    for log in logs:
        print(f"{log.source_identifier}: {log.errors}")
```

### Create Manual Alias

```python
from database.models import EntityAlias
from uuid import uuid4

alias = EntityAlias(
    alias_id=uuid4(),
    entity_type='company',
    entity_id=company_id,  # Canonical entity UUID
    alias_text='Former Company Name',
    alias_type='former_name',
    source='manual',
    confidence_score=1.0
)
session.add(alias)
session.commit()
```

### Query Entity with All Aliases

```python
from database.models import Company, EntityAlias

company = session.query(Company).filter(
    Company.name == 'Moderna'
).first()

# Get all aliases
aliases = session.query(EntityAlias).filter(
    EntityAlias.entity_type == 'company',
    EntityAlias.entity_id == company.company_id
).all()

print(f"Primary: {company.name}")
for alias in aliases:
    print(f"Alias ({alias.alias_type}): {alias.alias_text}")
```

### Force Re-processing

```python
# Mark records as unprocessed
from database.models import StagingRawData

session.query(StagingRawData).filter(
    StagingRawData.source_system == 'clinicaltrials_gov',
    StagingRawData.source_record_id == 'NCT12345678'
).update({'processed': False})

session.commit()

# Delete old processing log
from database.models import SourceProcessingLog

session.query(SourceProcessingLog).filter(
    SourceProcessingLog.source_name == 'clinicaltrials_gov',
    SourceProcessingLog.source_identifier == 'NCT12345678'
).delete()

session.commit()

# Reprocess
pipeline.process_source('clinicaltrials_gov')
```

## Troubleshooting

### Low Auto-Match Rate (<70%)

**Possible causes**:
1. Source data quality issues (misspellings, inconsistent naming)
2. Thresholds too conservative
3. Missing aliases for common variations

**Solutions**:
- Review sample of "no match" cases
- Lower fuzzy match threshold (carefully)
- Add common aliases manually or via batch script

### High False Positive Rate

**Symptoms**: Incorrect matches in production data

**Solutions**:
- Raise confidence thresholds
- Add negative examples to training
- Improve context extraction for boosting

### Slow Processing

**Benchmarks**:
- Target: 500+ records/minute
- Acceptable: 200+ records/minute

**If slower**:
1. Check database indexes (especially trigram indexes)
2. Reduce batch size if memory constrained
3. Check for slow queries in logs
4. Consider connection pooling configuration

### Review Queue Backup

**If queue > 1000 items**:
1. Increase review team capacity
2. Lower confidence threshold to auto-match more
3. Batch resolve obvious cases programmatically

## Performance Tips

### Database Indexes

Essential indexes (auto-created by migrations):
```sql
-- Trigram indexes for fuzzy matching
CREATE INDEX idx_companies_name_trgm ON companies USING gin (name gin_trgm_ops);
CREATE INDEX idx_drugs_primary_name_trgm ON drugs USING gin (primary_name gin_trgm_ops);

-- JSONB indexes for context queries
CREATE INDEX idx_entity_match_candidates_context ON entity_match_candidates USING gin (extracted_context);

-- Composite indexes for common queries
CREATE INDEX idx_processing_log_source_status ON source_processing_log (source_name, processing_status);
```

### Query Optimization

```python
# Bad: Load all candidates then filter in Python
all_candidates = session.query(EntityMatchCandidate).all()
pending = [c for c in all_candidates if c.status == 'needs_review']

# Good: Filter in database
pending = session.query(EntityMatchCandidate).filter(
    EntityMatchCandidate.status == 'needs_review'
).limit(100).all()
```

### Batch Operations

```python
# Bad: Insert relationships one by one
for rel in relationships:
    session.add(rel)
    session.commit()  # Commit each time

# Good: Batch commit
for rel in relationships:
    session.add(rel)
session.commit()  # Commit once
```

## API Reference

### EntityResolver

```python
from src.entity_resolution.entity_resolver import EntityResolver

resolver = EntityResolver(session)

# Resolve an entity
result = resolver.resolve(extracted_entity)

# Check result
if result.status == ResolutionStatus.EXACT_MATCH:
    print(f"Matched to: {result.entity_id}")
elif result.status == ResolutionStatus.NEEDS_REVIEW:
    print(f"Ambiguous: {len(result.candidates)} candidates")
    for candidate in result.candidates:
        print(f"  - {candidate.entity_name}: {candidate.confidence_score}")
```

### ConfidenceScorer

```python
from src.entity_resolution.confidence_scorer import ConfidenceScorer

scorer = ConfidenceScorer(session)

# Calculate similarity
similarity = scorer.calculate_trigram_similarity("Moderna", "moderna")
print(f"Similarity: {similarity}")  # 1.0

# Calculate with context
score, reasons = scorer.calculate_score(
    "Drug A",
    "Drug B",
    context1={'company_ids': [company_1]},
    context2={'company_ids': [company_1]}
)
print(f"Score: {score}")  # Base + context boost
print(f"Reasons: {reasons}")
```

### RelationshipBuilder

```python
from src.entity_resolution.relationship_builder import RelationshipBuilder

builder = RelationshipBuilder(session)

# Create relationship
builder.create_relationship(
    relationship=relationship_extraction,
    source_entity_id=drug_id,
    target_entity_id=target_id,
    source_name='clinicaltrials_gov'
)

# Get stats
stats = builder.get_stats()
print(f"Created: {stats['created']}")
print(f"Updated: {stats['updated']}")
```

## Resources

- **Full Implementation Report**: `ENTITY_RESOLUTION_IMPLEMENTATION_REPORT.md`
- **Database Schema**: `database/DATABASE_SCHEMA.md`
- **API Documentation**: Auto-generated from docstrings
- **Examples**: `database/examples.py`

## Support

For issues or questions:
1. Check this README
2. Review implementation report for detailed explanations
3. Check database schema documentation
4. Review code docstrings
5. Create an issue with logs and context

---

**Version**: 1.0  
**Last Updated**: November 6, 2025

