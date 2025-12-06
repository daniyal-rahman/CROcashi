#!/bin/bash
# Setup cron job for daily pipeline
# Run this script to add the daily pipeline to crontab

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_PATH="$(which python3)"

# Create log directory
mkdir -p "$PROJECT_ROOT/logs"

# Cron job runs daily at 2 AM
CRON_SCHEDULE="0 2 * * *"
CRON_COMMAND="cd $PROJECT_ROOT && $PYTHON_PATH scripts/daily_pipeline.py >> logs/cron.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "daily_pipeline.py"; then
    echo "Cron job already exists. Removing old entry..."
    crontab -l 2>/dev/null | grep -v "daily_pipeline.py" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_SCHEDULE $CRON_COMMAND") | crontab -

echo "✓ Cron job added successfully"
echo "Schedule: Daily at 2 AM"
echo "Command: $CRON_COMMAND"
echo ""
echo "To view cron jobs: crontab -l"
echo "To remove cron job: crontab -e (then delete the line)"

