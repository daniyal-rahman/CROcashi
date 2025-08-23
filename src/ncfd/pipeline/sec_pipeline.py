"""
SEC Filing Pipeline for automated filing monitoring and processing.

This module provides:
- Daily filing monitoring and scanning
- Automated document processing
- Integration with LangExtract for information extraction
- Event processing and company linking
- Change detection and signal evaluation
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import json

from ..ingest.sec_filings import SecFilingsClient
from ..ingest.sec_langextract import SecLangExtractor
from ..ingest.sec_types import (
    FilingMetadata, FilingDocument, EightKItem, TenKSection,
    ExtractionResult, SecIngestionResult
)

logger = logging.getLogger(__name__)


class SecPipeline:
    """
    Automated SEC filing pipeline for monitoring and processing.
    
    Features:
    - Daily filing monitoring
    - Automated document processing
    - Information extraction via LangExtract
    - Change detection and tracking
    - Integration with existing systems
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the SEC pipeline.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.client = SecFilingsClient(config)
        self.langextract = SecLangExtractor(config)
        
        # Pipeline state
        self.state_file = Path(config.get('state_file', '.state/sec_pipeline.json'))
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.pipeline_state = self._load_pipeline_state()
        
        # Company monitoring
        self.monitored_companies = config.get('monitored_companies', [])
        self.company_last_check = self.pipeline_state.get('company_last_check', {})
        
        # Processing metrics
        self.daily_stats = self.pipeline_state.get('daily_stats', {})
        self.processing_errors = []
        
        logger.info(f"SEC Pipeline initialized with {len(self.monitored_companies)} monitored companies")
    
    def run_daily_scan(self, force_full_scan: bool = False) -> SecIngestionResult:
        """
        Run daily filing scan for all monitored companies.
        
        Args:
            force_full_scan: Force full scan regardless of last check time
            
        Returns:
            Ingestion result summary
        """
        start_time = datetime.utcnow()
        logger.info("Starting daily SEC filing scan")
        
        # Determine scan parameters
        since_date = self._get_scan_since_date(force_full_scan)
        form_types = self.config.get('filtering', {}).get('form_types', ['8-K', '10-K', '10-Q'])
        
        # Initialize result tracking
        total_filings = 0
        successful_filings = 0
        failed_filings = 0
        new_filings = 0
        updated_filings = 0
        unchanged_filings = 0
        
        # Process each monitored company
        for company_cik in self.monitored_companies:
            try:
                company_result = self._process_company_filings(
                    company_cik, form_types, since_date
                )
                
                if company_result:
                    total_filings += company_result.filings_processed
                    successful_filings += company_result.filings_successful
                    failed_filings += company_result.filings_failed
                    new_filings += company_result.new_filings
                    updated_filings += company_result.updated_filings
                    unchanged_filings += company_result.unchanged_filings
                
                # Update last check time
                self.company_last_check[company_cik] = datetime.utcnow().isoformat()
                
                # Rate limiting between companies
                time.sleep(1)  # Be extra polite
                
            except Exception as e:
                error_msg = f"Error processing company {company_cik}: {e}"
                logger.error(error_msg)
                self.processing_errors.append(error_msg)
                failed_filings += 1
        
        # Calculate processing time
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Create overall result
        result = SecIngestionResult(
            success=len(self.processing_errors) == 0,
            company_cik=0,  # Overall result
            filings_processed=total_filings,
            filings_successful=successful_filings,
            filings_failed=failed_filings,
            new_filings=new_filings,
            updated_filings=updated_filings,
            unchanged_filings=unchanged_filings,
            processing_time_seconds=processing_time,
            errors=self.processing_errors
        )
        
        # Update pipeline state
        self._update_pipeline_state(result)
        
        # Log results
        logger.info(
            f"Daily scan completed: {total_filings} filings processed, "
            f"{new_filings} new, {updated_filings} updated, "
            f"{failed_filings} failed in {processing_time:.1f}s"
        )
        
        return result
    
    def _process_company_filings(
        self, 
        company_cik: int, 
        form_types: List[str], 
        since_date: date
    ) -> Optional[SecIngestionResult]:
        """
        Process filings for a specific company.
        
        Args:
            company_cik: Company CIK number
            form_types: Form types to process
            since_date: Date to scan from
            
        Returns:
            Company processing result
        """
        logger.info(f"Processing filings for company {company_cik}")
        
        try:
            # Fetch filing metadata
            filings = self.client.fetch_company_filings(
                company_cik, form_types, since_date
            )
            
            if not filings:
                logger.info(f"No new filings found for company {company_cik}")
                return SecIngestionResult(
                    success=True,
                    company_cik=company_cik,
                    filings_processed=0
                )
            
            # Process each filing
            processed_filings = 0
            successful_filings = 0
            failed_filings = 0
            new_filings = 0
            updated_filings = 0
            unchanged_filings = 0
            
            for filing_metadata in filings:
                try:
                    filing_result = self._process_filing(filing_metadata)
                    
                    if filing_result:
                        processed_filings += 1
                        successful_filings += 1
                        
                        # Determine if filing is new/updated/unchanged
                        if filing_result.new_filings > 0:
                            new_filings += 1
                        elif filing_result.updated_filings > 0:
                            updated_filings += 1
                        else:
                            unchanged_filings += 1
                    else:
                        failed_filings += 1
                        
                except Exception as e:
                    error_msg = f"Error processing filing {filing_metadata.accession}: {e}"
                    logger.error(error_msg)
                    failed_filings += 1
                
                # Rate limiting between filings
                time.sleep(0.5)  # 2 seconds between filings
            
            # Create company result
            company_result = SecIngestionResult(
                success=failed_filings == 0,
                company_cik=company_cik,
                filings_processed=processed_filings,
                filings_successful=successful_filings,
                filings_failed=failed_filings,
                new_filings=new_filings,
                updated_filings=updated_filings,
                unchanged_filings=unchanged_filings
            )
            
            return company_result
            
        except Exception as e:
            logger.error(f"Error fetching filings for company {company_cik}: {e}")
            return None
    
    def _process_filing(self, filing_metadata: FilingMetadata) -> Optional[Dict[str, Any]]:
        """
        Process a single filing document.
        
        Args:
            filing_metadata: Filing metadata
            
        Returns:
            Processing result or None if failed
        """
        try:
            # Check if filing is already processed and unchanged
            if self._is_filing_unchanged(filing_metadata):
                logger.info(f"Filing {filing_metadata.accession} unchanged, skipping")
                return {"status": "unchanged"}
            
            # Fetch and parse document
            document = self.client.fetch_filing_document(filing_metadata)
            if not document:
                logger.error(f"Failed to fetch document for {filing_metadata.accession}")
                return None
            
            # Extract information using LangExtract
            extraction_result = self._extract_information(document)
            
            # Process extracted information
            if extraction_result and extraction_result.extracted_items:
                self._process_extracted_items(extraction_result, filing_metadata)
            
            # Update filing tracking
            self._update_filing_tracking(filing_metadata, document)
            
            # Determine if filing is new or updated
            is_new = self._is_new_filing(filing_metadata)
            status = "new" if is_new else "updated"
            
            logger.info(f"Successfully processed filing {filing_metadata.accession} ({status})")
            
            return {
                "status": status,
                "extraction_result": extraction_result,
                "document": document
            }
            
        except Exception as e:
            logger.error(f"Error processing filing {filing_metadata.accession}: {e}")
            return None
    
    def _extract_information(self, document: FilingDocument) -> Optional[ExtractionResult]:
        """
        Extract information from document using LangExtract.
        
        Args:
            document: Parsed filing document
            
        Returns:
            Extraction result or None if failed
        """
        try:
            # Filter sections by confidence and relevance
            relevant_sections = self._filter_relevant_sections(document.sections)
            
            if not relevant_sections:
                logger.info(f"No relevant sections found in {document.metadata.accession}")
                return None
            
            # Extract information based on form type
            form_type = document.metadata.form_type
            filing_metadata = {
                'cik': document.metadata.cik,
                'accession': document.metadata.accession,
                'company_name': document.metadata.company_name,
                'filing_date': document.metadata.filing_date.isoformat()
            }
            
            extraction_result = self.langextract.batch_extract(
                relevant_sections, filing_metadata, form_type
            )
            
            return extraction_result
            
        except Exception as e:
            logger.error(f"Error extracting information from {document.metadata.accession}: {e}")
            return None
    
    def _filter_relevant_sections(self, sections: List[Any]) -> List[Any]:
        """Filter sections by relevance and confidence."""
        relevant_sections = []
        
        for section in sections:
            # Check confidence level
            if section.confidence in ["HIGH", "MEDIUM"]:
                relevant_sections.append(section)
            elif section.confidence == "LOW" and len(section.content) > 500:
                # Include low confidence sections if they have substantial content
                relevant_sections.append(section)
        
        return relevant_sections
    
    def _process_extracted_items(
        self, 
        extraction_result: ExtractionResult, 
        filing_metadata: FilingMetadata
    ):
        """
        Process extracted information items.
        
        Args:
            extraction_result: Result of information extraction
            filing_metadata: Filing metadata
        """
        try:
            for item in extraction_result.extracted_items:
                if hasattr(item, 'trial_events') and item.trial_events:
                    # Process trial events
                    self._process_trial_events(item, filing_metadata)
                
                if hasattr(item, 'clinical_development') and item.clinical_development:
                    # Process clinical development information
                    self._process_clinical_development(item, filing_metadata)
                
                # Flag items requiring review
                if hasattr(item, 'requires_review') and item.requires_review:
                    self._flag_for_review(item, filing_metadata)
                    
        except Exception as e:
            logger.error(f"Error processing extracted items: {e}")
    
    def _process_trial_events(self, item: EightKItem, filing_metadata: FilingMetadata):
        """Process extracted trial events."""
        logger.info(f"Processing trial events from {filing_metadata.accession}")
        
        # TODO: Integrate with trial database
        # TODO: Trigger signal evaluation
        # TODO: Update company-trial relationships
        
        pass
    
    def _process_clinical_development(self, item: TenKSection, filing_metadata: FilingMetadata):
        """Process extracted clinical development information."""
        logger.info(f"Processing clinical development from {filing_metadata.accession}")
        
        # TODO: Integrate with pipeline database
        # TODO: Update trial status and milestones
        # TODO: Trigger regulatory monitoring
        
        pass
    
    def _flag_for_review(self, item: Any, filing_metadata: FilingMetadata):
        """Flag item for human review."""
        logger.info(f"Flagging item for review from {filing_metadata.accession}")
        
        # TODO: Add to review queue
        # TODO: Send notification
        # TODO: Track review status
        
        pass
    
    def _is_filing_unchanged(self, filing_metadata: FilingMetadata) -> bool:
        """Check if filing content is unchanged."""
        # TODO: Implement content hash comparison
        # TODO: Check against stored versions
        return False
    
    def _is_new_filing(self, filing_metadata: FilingMetadata) -> bool:
        """Check if filing is new."""
        # TODO: Check against filing database
        return True
    
    def _update_filing_tracking(self, filing_metadata: FilingMetadata, document: FilingDocument):
        """Update filing tracking information."""
        # TODO: Store filing metadata
        # TODO: Update processing timestamps
        # TODO: Track extraction results
        
        pass
    
    def _get_scan_since_date(self, force_full_scan: bool) -> date:
        """Get the date to scan from."""
        if force_full_scan:
            # Use configured backfill start date
            backfill_date = self.config.get('filtering', {}).get('min_filing_date', '2000-01-01')
            return datetime.strptime(backfill_date, '%Y-%m-%d').date()
        
        # Check last scan time
        last_scan = self.pipeline_state.get('last_scan_date')
        if last_scan:
            last_scan_date = datetime.fromisoformat(last_scan).date()
            # Scan from 2 days ago to catch any missed filings
            return last_scan_date - timedelta(days=2)
        
        # Default to 7 days ago
        return datetime.utcnow().date() - timedelta(days=7)
    
    def _load_pipeline_state(self) -> Dict[str, Any]:
        """Load pipeline state from file."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load pipeline state: {e}")
        
        return {}
    
    def _update_pipeline_state(self, result: SecIngestionResult):
        """Update pipeline state with latest results."""
        try:
            # Update last scan date
            self.pipeline_state['last_scan_date'] = datetime.utcnow().isoformat()
            
            # Update company last check times
            self.pipeline_state['company_last_check'] = self.company_last_check
            
            # Update daily stats
            today = datetime.utcnow().date().isoformat()
            if today not in self.daily_stats:
                self.daily_stats[today] = {
                    'filings_processed': 0,
                    'new_filings': 0,
                    'updated_filings': 0,
                    'errors': 0
                }
            
            self.daily_stats[today]['filings_processed'] += result.filings_processed
            self.daily_stats[today]['new_filings'] += result.new_filings
            self.daily_stats[today]['updated_filings'] += result.updated_filings
            self.daily_stats[today]['errors'] += len(result.errors)
            
            self.pipeline_state['daily_stats'] = self.daily_stats
            
            # Save state
            with open(self.state_file, 'w') as f:
                json.dump(self.pipeline_state, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to update pipeline state: {e}")
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        return {
            'last_scan_date': self.pipeline_state.get('last_scan_date'),
            'monitored_companies': len(self.monitored_companies),
            'company_last_check': self.company_last_check,
            'daily_stats': self.daily_stats,
            'recent_errors': self.processing_errors[-10:] if self.processing_errors else [],
            'state_file': str(self.state_file)
        }
    
    def add_monitored_company(self, company_cik: int):
        """Add a company to monitoring list."""
        if company_cik not in self.monitored_companies:
            self.monitored_companies.append(company_cik)
            logger.info(f"Added company {company_cik} to monitoring list")
    
    def remove_monitored_company(self, company_cik: int):
        """Remove a company from monitoring list."""
        if company_cik in self.monitored_companies:
            self.monitored_companies.remove(company_cik)
            logger.info(f"Removed company {company_cik} from monitoring list")
    
    def run_backfill(
        self, 
        start_date: date, 
        end_date: date,
        company_ciks: Optional[List[int]] = None
    ) -> SecIngestionResult:
        """
        Run backfill for historical filings.
        
        Args:
            start_date: Start date for backfill
            end_date: End date for backfill
            company_ciks: Specific companies to backfill (None for all)
            
        Returns:
            Backfill result
        """
        logger.info(f"Starting backfill from {start_date} to {end_date}")
        
        # Use specified companies or all monitored companies
        companies_to_process = company_ciks or self.monitored_companies
        
        # Temporarily override scan date
        original_since_date = self._get_scan_since_date(False)
        
        try:
            # Run scan with backfill dates
            result = self.run_daily_scan(force_full_scan=True)
            
            logger.info(f"Backfill completed: {result.filings_processed} filings processed")
            return result
            
        finally:
            # Restore original scan date
            pass  # TODO: Implement proper state restoration
