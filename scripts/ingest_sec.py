#!/usr/bin/env python3
"""
SEC Data Ingestion Script for CROcashi

This script provides a simple CLI interface for ingesting SEC data:
- Company tickers and securities
- SEC filings pipeline execution
- Pipeline status checking
- Backfill operations

Usage:
    python scripts/ingest_sec.py tickers [--json PATH] [--start DATE]
    python scripts/ingest_sec.py filings
    python scripts/ingest_sec.py status
    python scripts/ingest_sec.py backfill --start DATE --end DATE
"""

import argparse
import sys
from datetime import date
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.config import get_config
from ncfd.ingest.sec import ingest_sec_company_tickers_from_file
from ncfd.pipeline.sec_pipeline import SecPipeline
from ncfd.db.session import get_engine
from sqlalchemy.orm import sessionmaker


def ingest_tickers(json_path: str, start_date: str):
    """Ingest SEC company tickers and securities."""
    print(f"🔄 Ingesting SEC company tickers from {json_path}")
    print(f"📅 Start date: {start_date}")
    
    try:
        # Create database session
        engine = get_engine()
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Parse start date
        start = date.fromisoformat(start_date)
        
        # Ingest data
        stats = ingest_sec_company_tickers_from_file(session, json_path, default_start=start)
        
        # Commit changes
        session.commit()
        session.close()
        
        print("✅ SEC tickers ingestion completed successfully!")
        print(f"📊 Stats: {stats}")
        
    except Exception as e:
        print(f"❌ Error ingesting SEC tickers: {e}")
        sys.exit(1)


def run_filings_pipeline():
    """Run SEC filings pipeline for daily monitoring."""
    print("🔄 Running SEC filings pipeline...")
    
    try:
        config = get_config()
        pipeline = SecPipeline(config)
        
        result = pipeline.run_daily_scan()
        
        print("✅ SEC filings pipeline completed successfully!")
        print(f"📊 Result: {result}")
        
    except Exception as e:
        print(f"❌ Error running SEC filings pipeline: {e}")
        sys.exit(1)


def check_pipeline_status():
    """Check SEC pipeline status."""
    print("📊 Checking SEC pipeline status...")
    
    try:
        config = get_config()
        pipeline = SecPipeline(config)
        
        status = pipeline.get_pipeline_status()
        
        print("✅ SEC pipeline status retrieved successfully!")
        print(f"📊 Status: {status}")
        
    except Exception as e:
        print(f"❌ Error checking SEC pipeline status: {e}")
        sys.exit(1)


def run_backfill(start_date: str, end_date: str):
    """Run SEC filings backfill."""
    print(f"🔄 Running SEC filings backfill from {start_date} to {end_date}")
    
    try:
        config = get_config()
        pipeline = SecPipeline(config)
        
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        
        result = pipeline.run_backfill(start, end)
        
        print("✅ SEC backfill completed successfully!")
        print(f"📊 Result: {result}")
        
    except Exception as e:
        print(f"❌ Error running SEC backfill: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="SEC Data Ingestion Script for CROcashi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest company tickers
  python scripts/ingest_sec.py tickers --json data/sec/company_tickers_exchange.json --start 1990-01-01
  
  # Run filings pipeline
  python scripts/ingest_sec.py filings
  
  # Check pipeline status
  python scripts/ingest_sec.py status
  
  # Run backfill
  python scripts/ingest_sec.py backfill --start 2023-01-01 --end 2023-12-31
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Tickers command
    tickers_parser = subparsers.add_parser('tickers', help='Ingest SEC company tickers and securities')
    tickers_parser.add_argument('--json', default='data/sec/company_tickers_exchange.json',
                               help='Path to SEC company tickers JSON file')
    tickers_parser.add_argument('--start', default='1990-01-01',
                               help='Start date for active listings (YYYY-MM-DD)')
    
    # Filings command
    subparsers.add_parser('filings', help='Run SEC filings pipeline for daily monitoring')
    
    # Status command
    subparsers.add_parser('status', help='Check SEC pipeline status')
    
    # Backfill command
    backfill_parser = subparsers.add_parser('backfill', help='Run SEC filings backfill')
    backfill_parser.add_argument('--start', required=True, help='Start date for backfill (YYYY-MM-DD)')
    backfill_parser.add_argument('--end', required=True, help='End date for backfill (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Execute command
    if args.command == 'tickers':
        ingest_tickers(args.json, args.start)
    elif args.command == 'filings':
        run_filings_pipeline()
    elif args.command == 'status':
        check_pipeline_status()
    elif args.command == 'backfill':
        run_backfill(args.start, args.end)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
