# Resolver Schema Migration Guide

This guide outlines the migration from the complex resolver system to a simplified three-tier matching approach.

## Overview

**Old System**: 7+ resolver tables with complex probabilistic scoring and run tracking
**New System**: 4 core tables with clear separation of concerns

## Migration Steps

### 1. Run Alembic Migration

```bash
# Apply the new schema
alembic upgrade head
```

This creates:
- `academic_blacklist` - Precise academic institution patterns
- `sponsor_resolutions` - Simplified resolution results
- `manual_review_queue` - Streamlined human review
- `llm_discoveries` - Track LLM learning
- `ticker` field added to `companies` table

### 2. Populate Academic Blacklist

```bash
# Populate with precise academic patterns
python scripts/populate_academic_blacklist.py
```

This replaces the overly broad academic keyword detection with specific regex patterns.

### 3. Migrate Existing Data

```bash
# Migrate existing resolver data
python scripts/migrate_resolver_data.py
```

This migrates:
- `resolver_decisions` → `sponsor_resolutions`
- `review_queue` → `manual_review_queue`
- LLM decisions → `llm_discoveries`

### 4. Verify Migration

```bash
# Check data counts
python -c "
from sqlalchemy import create_engine, text
engine = create_engine('postgresql://ncfd:ncfd@localhost:5433/ncfd')
with engine.connect() as conn:
    tables = ['sponsor_resolutions', 'manual_review_queue', 'llm_discoveries', 'academic_blacklist']
    for table in tables:
        result = conn.execute(text(f'SELECT COUNT(*) FROM {table}'))
        count = result.fetchone()[0]
        print(f'{table}: {count} records')
"
```

### 5. Clean Up Old Tables (Optional)

```bash
# Remove old resolver tables
python scripts/cleanup_old_resolver_tables.py
```

**⚠️ Warning**: Only run this after verifying the new system works correctly!

## New Schema Benefits

### Simplified Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `sponsor_resolutions` | Store all resolution results | `nct_id`, `company_id`, `match_method`, `confidence` |
| `manual_review_queue` | Human review cases | `nct_id`, `sponsor_text`, `status` |
| `llm_discoveries` | Track LLM learning | `nct_id`, `discovered_company_id`, `discovered_aliases` |
| `academic_blacklist` | Precise academic patterns | `pattern`, `reason`, `enabled` |

### Three-Tier Matching Flow

```
Sponsor Text → Exact Match → Fuzzy Match → LLM Match → Manual Review
     ↓              ↓            ↓           ↓           ↓
   Found?        Found?       Found?      Found?    Human Review
     ↓              ↓            ↓           ↓           ↓
   Accept        Accept       Accept    Accept +    Manual
                              Learn     Learn      Decision
```

### Key Improvements

1. **Precise Academic Detection**: Regex patterns instead of broad keywords
2. **Learning System**: LLM discoveries feed back into better matching
3. **Simplified State**: No complex run tracking or probabilistic scoring
4. **Clear Separation**: Each table has a single, clear purpose
5. **Performance**: Better indexes and simpler queries

## Rollback Plan

If issues arise, you can rollback:

```bash
# Rollback alembic migration
alembic downgrade -1

# This will remove the new tables and restore the old schema
```

## Testing the New System

1. **Test Academic Detection**:
   ```python
   # Should NOT match legitimate pharma companies
   assert not is_academic("Pfizer Inc.")
   assert not is_academic("Merck & Co.")
   
   # Should match academic institutions
   assert is_academic("Harvard University")
   assert is_academic("Mayo Clinic")
   ```

2. **Test Three-Tier Matching**:
   ```python
   # Test exact match
   result = resolve_sponsor("Pfizer Inc.")
   assert result['match_method'] == 'exact'
   
   # Test fuzzy match
   result = resolve_sponsor("Pfizer Inc")  # Missing period
   assert result['match_method'] == 'fuzzy'
   
   # Test LLM match
   result = resolve_sponsor("Some obscure subsidiary name")
   assert result['match_method'] == 'llm'
   ```

3. **Test Manual Review Queue**:
   ```python
   # Cases that fail all three tiers should go to review
   result = resolve_sponsor("Completely unknown company")
   assert result['match_method'] == 'manual'
   ```

## Next Steps

After migration:

1. Update application code to use new tables
2. Implement alias learning from LLM discoveries
3. Add monitoring for system improvement over time
4. Consider adding more sophisticated fuzzy matching algorithms
