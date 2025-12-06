# Automation Setup Guide

**Date:** 2025-01-27  
**Status:** Ready for Setup

## Quick Setup

### Option 1: Automated Setup (Recommended)

```bash
cd /Users/danirahman/Repos/CROcashi
./scripts/setup_cron.sh
```

This will:
- Create log directory
- Add cron job for daily pipeline (runs at 2 AM)
- Show you the cron job details

### Option 2: Manual Setup

```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 2 AM):
0 2 * * * cd /Users/danirahman/Repos/CROcashi && python3 scripts/daily_pipeline.py >> logs/cron.log 2>&1
```

## What Gets Automated

### Daily (2 AM)
- **Ingestion:** Small batches from critical sources
  - clinicaltrials_gov (50 records)
  - sec_edgar (50 records)
  - pubmed (50 records)
  - fda_drugs (50 records)

- **Processing:** All new staging records
  - Processes all sources with unprocessed records
  - Creates entities and relationships
  - Logs results

### Weekly (Mondays)
- **Relationship Inference:** Cross-source relationships
  - Company-drug relationships
  - Publication-trial relationships
  - Publication-drug relationships
  - Filing-drug relationships

## Monitoring

### Check Logs
```bash
# View today's log
tail -f logs/pipeline_$(date +%Y%m%d).log

# View cron log
tail -f logs/cron.log

# View all logs
ls -lh logs/
```

### Check Status
```bash
# Run system status check
python scripts/system_status_check.py

# Check processing logs
python -c "
from database.config import get_db_session
from database.models.resolution import SourceProcessingLog
from sqlalchemy import func

with get_db_session() as session:
    recent = session.query(
        SourceProcessingLog.source_name,
        func.count(SourceProcessingLog.log_id).label('count'),
        func.max(SourceProcessingLog.processing_completed_at).label('last_run')
    ).group_by(SourceProcessingLog.source_name).order_by(func.max(SourceProcessingLog.processing_completed_at).desc()).limit(5).all()
    
    for source, count, last_run in recent:
        print(f'{source}: {count} logs, last run: {last_run}')
"
```

## Troubleshooting

### Cron Job Not Running
```bash
# Check if cron is running
ps aux | grep cron

# Check cron logs (system dependent)
# macOS: Console.app -> System Log
# Linux: /var/log/cron or journalctl -u cron

# Test cron job manually
cd /Users/danirahman/Repos/CROcashi && python3 scripts/daily_pipeline.py
```

### Pipeline Errors
```bash
# Check for errors in logs
grep -i error logs/pipeline_*.log

# Run pipeline manually to see errors
python scripts/daily_pipeline.py
```

### No New Data
- Check if ingestion scripts are working
- Verify API keys/credentials
- Check network connectivity
- Review ingestion script logs

## Customization

### Change Schedule
Edit crontab:
```bash
crontab -e
```

Examples:
- Daily at 3 AM: `0 3 * * * ...`
- Every 6 hours: `0 */6 * * * ...`
- Weekdays only: `0 2 * * 1-5 ...`

### Change Batch Sizes
Edit `scripts/daily_pipeline.py`:
```python
# Change ingestion limit
result = ingest_source(source, limit=100)  # Was 50

# Change processing batch size
pipeline = ProcessingPipeline(batch_size=100)  # Was 50
```

### Add More Sources
Edit `scripts/daily_pipeline.py`:
```python
critical_sources = [
    'clinicaltrials_gov',
    'sec_edgar',
    'pubmed',
    'fda_drugs',
    'your_new_source'  # Add here
]
```

## Verification

After setup, verify it's working:

```bash
# 1. Check cron job is scheduled
crontab -l | grep daily_pipeline

# 2. Wait for first run (or trigger manually)
python scripts/daily_pipeline.py

# 3. Check logs
ls -lh logs/

# 4. Check database for new records
python scripts/system_status_check.py
```

## Maintenance

### Weekly
- Review logs for errors
- Check processing success rates
- Verify new data is being ingested

### Monthly
- Review entity resolution candidates
- Check relationship coverage
- Update ingestion limits if needed

## Support

If automation isn't working:
1. Check logs: `logs/pipeline_*.log` and `logs/cron.log`
2. Run manually: `python scripts/daily_pipeline.py`
3. Check system status: `python scripts/system_status_check.py`
4. Review error messages in logs

