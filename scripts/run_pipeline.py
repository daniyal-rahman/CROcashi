#!/usr/bin/env python3
"""
CROcashi Pipeline CLI Runner

Simple command-line interface to run the CROcashi pipeline
with different filtering and configuration options.
"""

import argparse
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from ncfd.pipeline.orchestrator import (
    CROcashiOrchestrator, 
    CompanyFilter, 
    PipelineConfig,
    run_investment_filtered_pipeline,
    run_company_specific_pipeline
)
from ncfd.db.session import get_db_session


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run the CROcashi pipeline for literature review and asset extraction"
    )
    
    # Pipeline mode selection
    parser.add_argument(
        '--mode',
        choices=['investment-filtered', 'company-specific', 'custom'],
        default='investment-filtered',
        help='Pipeline execution mode'
    )
    
    # Company filtering options
    parser.add_argument(
        '--min-market-cap',
        type=float,
        default=100_000_000,
        help='Minimum market cap in USD (default: 100M)'
    )
    
    parser.add_argument(
        '--max-market-cap',
        type=float,
        help='Maximum market cap in USD (no limit if not specified)'
    )
    
    parser.add_argument(
        '--exchanges',
        nargs='+',
        default=['NASDAQ', 'NYSE', 'NYSE American'],
        help='Stock exchanges to include (default: NASDAQ, NYSE, NYSE American)'
    )
    
    parser.add_argument(
        '--exclude-countries',
        nargs='+',
        default=['CN', 'HK'],
        help='Countries to exclude (default: CN, HK)'
    )
    
    parser.add_argument(
        '--min-trials',
        type=int,
        default=1,
        help='Minimum number of trials per company (default: 1)'
    )
    
    parser.add_argument(
        '--include-private',
        action='store_true',
        help='Include private companies (default: false)'
    )
    
    # Company-specific mode options
    parser.add_argument(
        '--company-ids',
        nargs='+',
        type=int,
        help='Specific company IDs to process (for company-specific mode)'
    )
    
    # Pipeline configuration
    parser.add_argument(
        '--max-docs-per-company',
        type=int,
        default=100,
        help='Maximum documents per company (default: 100)'
    )
    
    parser.add_argument(
        '--max-total-docs',
        type=int,
        default=1000,
        help='Maximum total documents to process (default: 1000)'
    )
    
    parser.add_argument(
        '--rate-limit-delay',
        type=float,
        default=1.0,
        help='Delay between requests in seconds (default: 1.0)'
    )
    
    # Execution options
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run analysis only, without making changes'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Get database session
        logger.info("Connecting to database...")
        db_session = get_db_session()
        
        if args.mode == 'investment-filtered':
            logger.info("Running investment-filtered pipeline...")
            
            # Use convenience function
            result = run_investment_filtered_pipeline(
                db_session=db_session,
                min_market_cap=args.min_market_cap,
                exchanges=args.exchanges,
                max_documents=args.max_total_docs
            )
            
        elif args.mode == 'company-specific':
            if not args.company_ids:
                logger.error("Company-specific mode requires --company-ids")
                sys.exit(1)
            
            logger.info(f"Running company-specific pipeline for companies: {args.company_ids}")
            
            # Use convenience function
            result = run_company_specific_pipeline(
                db_session=db_session,
                company_ids=args.company_ids,
                max_documents_per_company=args.max_docs_per_company
            )
            
        elif args.mode == 'custom':
            logger.info("Running custom pipeline...")
            
            # Create custom company filter
            company_filter = CompanyFilter(
                min_market_cap=args.min_market_cap,
                max_market_cap=args.max_market_cap,
                exchanges=args.exchanges,
                exclude_countries=args.exclude_countries,
                min_trial_count=args.min_trials,
                include_private=args.include_private
            )
            
            # Create custom pipeline config
            config = PipelineConfig(
                max_documents_per_company=args.max_docs_per_company,
                max_total_documents=args.max_total_docs,
                rate_limit_delay=args.rate_limit_delay
            )
            
            # Create orchestrator and run
            orchestrator = CROcashiOrchestrator(db_session, config)
            result = orchestrator.run_complete_pipeline(
                company_filter=company_filter,
                dry_run=args.dry_run
            )
        
        # Display results
        print("\n" + "="*60)
        print("PIPELINE EXECUTION RESULTS")
        print("="*60)
        print(f"Execution ID: {result.execution_id}")
        print(f"Status: {'DRY RUN' if args.dry_run else 'COMPLETED'}")
        print(f"Duration: {result.end_time - result.start_time}")
        print()
        print("COMPANIES & TRIALS:")
        print(f"  Companies processed: {result.companies_processed}")
        print(f"  Trials filtered: {result.trials_filtered}")
        print()
        print("DOCUMENTS:")
        print(f"  Discovered: {result.documents_discovered}")
        print(f"  Fetched: {result.documents_fetched}")
        print(f"  Parsed: {result.documents_parsed}")
        print(f"  Linked: {result.documents_linked}")
        print()
        print("ASSETS & LINKS:")
        print(f"  Assets extracted: {result.assets_extracted}")
        print(f"  Links created: {result.links_created}")
        print()
        
        if result.errors:
            print("ERRORS:")
            for error in result.errors:
                print(f"  - {error}")
            print()
        
        if result.warnings:
            print("WARNINGS:")
            for warning in result.warnings:
                print(f"  - {warning}")
            print()
        
        print("="*60)
        
        if args.dry_run:
            print("DRY RUN COMPLETED - No changes were made to the database")
        else:
            print("PIPELINE EXECUTION COMPLETED SUCCESSFULLY!")
        
        return 0
        
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
