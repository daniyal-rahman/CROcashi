# Quick Start Guide

**Date:** 2025-01-27  
**Status:** Implementation Complete

## What's Been Implemented

All Week 1 tasks from the verified action plan are complete:

1. ✅ Entity resolution review tools
2. ✅ Script reliability testing
3. ✅ Dashboard requirements mapping
4. ✅ Daily pipeline automation
5. ✅ Backlog processing script

## Quick Commands

### Review Entity Matches
```bash
# View prioritized candidates
open data/entity_review/entity_matches_review_*.csv

# Review a specific candidate
python scripts/review_entity_match.py show <candidate_id>

# Approve a match
python scripts/review_entity_match.py approve <candidate_id> [entity_id]

# Reject a match
python scripts/review_entity_match.py reject <candidate_id>
```

### Test Scripts
```bash
# Test script reliability
python scripts/test_script_reliability.py

# Test backlog processing (10 records)
python scripts/process_backlog.py --test
```

### Process Backlog
```bash
# Process all backlog
python scripts/process_backlog.py

# Process with limits
python scripts/process_backlog.py --limit-per-source 50
python scripts/process_backlog.py --max-total 100
```

### Set Up Automation
```bash
# Add cron job (runs daily at 2 AM)
./scripts/setup_cron.sh

# Or manually add to crontab
crontab -e
# Add: 0 2 * * * cd /path/to/CROcashi && python3 scripts/daily_pipeline.py >> logs/cron.log 2>&1
```

### Run Daily Pipeline Manually
```bash
python scripts/daily_pipeline.py
```

## Dashboard Requirements

View requirements:
```bash
cat data/dashboard_requirements.json | jq
```

Key gaps identified:
- **Priority 1:** filing_drugs relationship missing
- **Need data:** clinicaltrials_gov, sec_edgar, fda_clinical_hold

## Known Issues

### Database Constraint Error
- **Issue:** `publication_drugs` check constraint violation
- **Error:** `mention_context` value 'title_abstract' not allowed
- **Fix:** Update database constraint or fix mention_context values

### Function Name Mapping
- **Issue:** sec_edgar and pubmed use different function names
- **Status:** Scripts handle this, but may need updates

## Next Steps

1. **Review entity matches** (CSV file ready)
2. **Fix database constraint** (publication_drugs)
3. **Set up cron job** (automation)
4. **Process backlog** (215 remaining records)
5. **Ingest event sources** (fda_clinical_hold, fda_breakthrough)

## Files Reference

- **Entity Review:** `data/entity_review/entity_matches_review_*.csv`
- **Dashboard Requirements:** `data/dashboard_requirements.json`
- **Logs:** `logs/pipeline_*.log`
- **Scripts:** `scripts/*.py`

