"""
Open Access (OA) stage worker for PUBMED_OA tasks.

Handles full-text retrieval from PMC, Unpaywall, and other OA sources.
"""

import asyncio
import logging
import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .client import PubMedClient
from .db_service import PubMedDBService
from .queue_service import TaskQueueService
from ...db.session import session_scope
from ...db.models import Document, DocumentText

logger = logging.getLogger(__name__)


@dataclass
class OAWorkerResult:
    """Result from OA worker execution."""
    task_id: int
    trial_id: int
    success: bool
    documents_processed: int = 0
    fulltext_retrieved: int = 0
    fulltext_stored: int = 0
    pmc_found: int = 0
    unpaywall_found: int = 0
    failed_retrievals: int = 0
    execution_time: float = 0.0
    error_message: Optional[str] = None


class OAWorker:
    """Worker for processing PUBMED_OA tasks."""
    
    def __init__(
        self,
        client: PubMedClient,
        queue_service: TaskQueueService,
        config: Optional[Dict] = None
    ):
        """
        Initialize OA worker.
        
        Args:
            client: PubMed client instance
            queue_service: Task queue service instance
            config: Configuration dictionary
        """
        self.client = client
        self.queue_service = queue_service
        self.config = config or {}
        
        # Initialize database service
        self.db_service = PubMedDBService()
        
        # OA settings
        self.batch_size = self.config.get('batch_size', 5)
        self.max_retries = self.config.get('max_retries', 3)
        self.retry_delay = self.config.get('retry_delay', 30)
        self.enable_unpaywall = self.config.get('enable_unpaywall', True)
        self.enable_pmc = self.config.get('enable_pmc', True)
        
        self.logger = logger
    
    async def process_oa_task(self, task_data: Dict[str, Any]) -> OAWorkerResult:
        """
        Process a single PUBMED_OA task.
        
        Args:
            task_data: Task data from queue
            
        Returns:
            OAWorkerResult with execution details
        """
        start_time = datetime.now(timezone.utc)
        task_id = task_data['id']
        trial_id = task_data['trial_id']
        
        try:
            self.logger.info(f"Processing OA task {task_id} for trial {trial_id}")
            
            # Get selected candidate documents for this trial
            selected_pmids = self.db_service.get_selected_candidate_pmids(
                trial_id, stage='U1_abstract'
            )
            
            if not selected_pmids:
                self.logger.warning(f"No selected candidates found for trial {trial_id}")
                return OAWorkerResult(
                    task_id=task_id,
                    trial_id=trial_id,
                    success=True,
                    execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                    error_message="No selected candidates found"
                )
            
            self.logger.info(f"Found {len(selected_pmids)} selected candidates for OA processing")
            
            # Process documents in batches
            results = await self._process_documents_batch(selected_pmids)
            
            # Update trial state and enqueue next stage if successful
            if results['success']:
                await self._update_trial_state_and_enqueue_next(trial_id, results)
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            return OAWorkerResult(
                task_id=task_id,
                trial_id=trial_id,
                success=results['success'],
                documents_processed=results['documents_processed'],
                fulltext_retrieved=results['fulltext_retrieved'],
                fulltext_stored=results['fulltext_stored'],
                pmc_found=results['pmc_found'],
                unpaywall_found=results['unpaywall_found'],
                failed_retrievals=results['failed_retrievals'],
                execution_time=execution_time,
                error_message=results.get('error_message')
            )
            
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            error_msg = f"Unexpected error processing OA task {task_id}: {e}"
            self.logger.error(error_msg)
            
            return OAWorkerResult(
                task_id=task_id,
                trial_id=trial_id,
                success=False,
                execution_time=execution_time,
                error_message=error_msg
            )
    
    async def _process_documents_batch(self, pmids: List[str]) -> Dict[str, Any]:
        """
        Process documents in batches for OA retrieval.
        
        Args:
            pmids: List of PMIDs to process
            
        Returns:
            Processing results
        """
        results = {
            'success': True,
            'documents_processed': 0,
            'fulltext_retrieved': 0,
            'fulltext_stored': 0,
            'pmc_found': 0,
            'unpaywall_found': 0,
            'failed_retrievals': 0,
            'error_message': None
        }
        
        # Process in batches
        for i in range(0, len(pmids), self.batch_size):
            batch_pmids = pmids[i:i + self.batch_size]
            self.logger.info(f"Processing OA batch {i//self.batch_size + 1}: {len(batch_pmids)} documents")
            
            batch_results = await self._process_single_batch(batch_pmids)
            
            # Aggregate results
            for key in ['documents_processed', 'fulltext_retrieved', 'fulltext_stored', 
                       'pmc_found', 'unpaywall_found', 'failed_retrievals']:
                results[key] += batch_results[key]
            
            # Add delay between batches to respect rate limits
            if i + self.batch_size < len(pmids):
                await asyncio.sleep(2)
        
        return results
    
    async def _process_single_batch(self, pmids: List[str]) -> Dict[str, Any]:
        """
        Process a single batch of documents.
        
        Args:
            pmids: List of PMIDs in this batch
            
        Returns:
            Batch processing results
        """
        results = {
            'documents_processed': 0,
            'fulltext_retrieved': 0,
            'fulltext_stored': 0,
            'pmc_found': 0,
            'unpaywall_found': 0,
            'failed_retrievals': 0
        }
        
        for pmid in pmids:
            try:
                results['documents_processed'] += 1
                
                # Try PMC first (most reliable)
                if self.enable_pmc:
                    pmc_result = await self._try_pmc_retrieval(pmid)
                    if pmc_result['success']:
                        results['pmc_found'] += 1
                        results['fulltext_retrieved'] += 1
                        if pmc_result['stored']:
                            results['fulltext_stored'] += 1
                        continue
                
                # Try Unpaywall as fallback
                if self.enable_unpaywall:
                    unpaywall_result = await self._try_unpaywall_retrieval(pmid)
                    if unpaywall_result['success']:
                        results['unpaywall_found'] += 1
                        results['fulltext_retrieved'] += 1
                        if unpaywall_result['stored']:
                            results['fulltext_stored'] += 1
                        continue
                
                # If both failed
                results['failed_retrievals'] += 1
                self.logger.warning(f"Failed to retrieve full text for PMID {pmid}")
                
            except Exception as e:
                results['failed_retrievals'] += 1
                self.logger.error(f"Error processing PMID {pmid}: {e}")
        
        return results
    
    async def _try_pmc_retrieval(self, pmid: str) -> Dict[str, Any]:
        """
        Try to retrieve full text from PMC using stored PMCID.
        
        Args:
            pmid: PMID to retrieve
            
        Returns:
            Retrieval result
        """
        try:
            # Get PMC ID from database (stored during U1 pass)
            pmcid = await self._get_stored_pmcid(pmid)
            if not pmcid:
                return {'success': False, 'stored': False}
            
            # Fetch full text from PMC using the correct method
            full_text = await self.client.get_pmc_full_text(pmcid)
            if not full_text:
                return {'success': False, 'stored': False}
            
            # Store full text
            stored = await self._store_fulltext(pmid, full_text, source='PMC')
            
            return {'success': True, 'stored': stored}
            
        except Exception as e:
            self.logger.error(f"PMC retrieval error for PMID {pmid}: {e}")
            return {'success': False, 'stored': False}
    
    async def _try_unpaywall_retrieval(self, pmid: str) -> Dict[str, Any]:
        """
        Try to retrieve full text via Unpaywall using stored DOI.
        
        Args:
            pmid: PMID to retrieve
            
        Returns:
            Retrieval result
        """
        try:
            # Get DOI from database (stored during U1 pass)
            doi = await self._get_stored_doi(pmid)
            if not doi:
                return {'success': False, 'stored': False}
            
            # Try Unpaywall API directly
            full_text = await self._fetch_unpaywall_text(doi)
            if not full_text:
                return {'success': False, 'stored': False}
            
            # Store full text
            stored = await self._store_fulltext(pmid, full_text, source='Unpaywall')
            
            return {'success': True, 'stored': stored}
            
        except Exception as e:
            self.logger.error(f"Unpaywall retrieval error for PMID {pmid}: {e}")
            return {'success': False, 'stored': False}
    
    async def _fetch_unpaywall_text(self, doi: str) -> Optional[str]:
        """
        Fetch full text from Unpaywall API.
        
        Args:
            doi: DOI to fetch
            
        Returns:
            Full text content or None if not available
        """
        try:
            # Unpaywall API endpoint
            url = f"https://api.unpaywall.org/v2/{doi}"
            params = {
                'email': self.config.get('unpaywall_email', 'ncfd@example.com')
            }
            
            # Add proper headers
            headers = {
                'User-Agent': 'NCFD/1.0 (https://github.com/your-org/ncfd)',
                'Accept': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Check if there's an OA location
                        oa_locations = data.get('oa_locations', [])
                        if not oa_locations:
                            self.logger.debug(f"No OA locations found for DOI {doi}")
                            return None
                        
                        # Try to fetch from the first available OA location
                        for location in oa_locations:
                            pdf_url = location.get('url_for_pdf')
                            if pdf_url:
                                # For now, just return the URL - in a real implementation,
                                # you'd fetch and parse the PDF content
                                self.logger.info(f"Found OA PDF for DOI {doi}: {pdf_url}")
                                return f"PDF available at: {pdf_url}"
                        
                        # If no PDF, check for other formats
                        for location in oa_locations:
                            url_for_landing_page = location.get('url_for_landing_page')
                            if url_for_landing_page:
                                self.logger.info(f"Found OA landing page for DOI {doi}: {url_for_landing_page}")
                                return f"OA available at: {url_for_landing_page}"
                        
                        return None
                    elif response.status == 422:
                        self.logger.warning(f"Unpaywall API returned 422 for DOI {doi} - invalid DOI format or not found")
                        return None
                    else:
                        self.logger.warning(f"Unpaywall API returned status {response.status} for DOI {doi}")
                        return None
                        
        except Exception as e:
            self.logger.error(f"Error fetching from Unpaywall for DOI {doi}: {e}")
            return None
    
    async def _get_stored_pmcid(self, pmid: str) -> Optional[str]:
        """
        Get stored PMCID for a PMID from the database.
        
        Args:
            pmid: PMID to look up
            
        Returns:
            PMCID if found, None otherwise
        """
        try:
            with session_scope() as session:
                from ...db.models import Document, DocumentCitation
                
                # Get document by PMID
                doc = session.query(Document).filter(Document.pmid == pmid).first()
                if not doc:
                    return None
                
                # Get citation data
                citation = session.query(DocumentCitation).filter(
                    DocumentCitation.doc_id == doc.doc_id
                ).first()
                
                return citation.pmcid if citation else None
                
        except Exception as e:
            self.logger.error(f"Error getting stored PMCID for PMID {pmid}: {e}")
            return None
    
    async def _get_stored_doi(self, pmid: str) -> Optional[str]:
        """
        Get stored DOI for a PMID from the database.
        
        Args:
            pmid: PMID to look up
            
        Returns:
            DOI if found, None otherwise
        """
        try:
            with session_scope() as session:
                from ...db.models import Document, DocumentCitation
                
                # Get document by PMID
                doc = session.query(Document).filter(Document.pmid == pmid).first()
                if not doc:
                    return None
                
                # Get citation data
                citation = session.query(DocumentCitation).filter(
                    DocumentCitation.doc_id == doc.doc_id
                ).first()
                
                return citation.doi if citation else None
                
        except Exception as e:
            self.logger.error(f"Error getting stored DOI for PMID {pmid}: {e}")
            return None

    async def _store_fulltext(self, pmid: str, full_text: str, source: str) -> bool:
        """
        Store full text in database.
        
        Args:
            pmid: PMID
            full_text: Full text content
            source: Source of the text (PMC, Unpaywall, etc.)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with session_scope() as session:
                # Find document by PMID
                document = session.query(Document).filter(Document.pmid == pmid).first()
                if not document:
                    self.logger.warning(f"Document with PMID {pmid} not found")
                    return False
                
                # Update document_text record
                doc_text = session.query(DocumentText).filter(
                    DocumentText.doc_id == document.doc_id
                ).first()
                
                if doc_text:
                    doc_text.fulltext_text = full_text
                    doc_text.char_count_fulltext = len(full_text)
                    doc_text.fulltext_ttl_date = None  # PMC/Unpaywall don't expire
                else:
                    # Create new document_text record
                    doc_text = DocumentText(
                        doc_id=document.doc_id,
                        fulltext_text=full_text,
                        char_count_fulltext=len(full_text),
                        fulltext_ttl_date=None,
                        abstract_text=None,
                        char_count_abstract=None
                    )
                    session.add(doc_text)
                
                # Update document status
                document.status = 'parsed'
                document.content_type = 'fulltext'
                document.parsed_at = datetime.now(timezone.utc)
                
                self.logger.debug(f"Stored full text for PMID {pmid} from {source} ({len(full_text)} chars)")
                return True
                
        except Exception as e:
            self.logger.error(f"Error storing full text for PMID {pmid}: {e}")
            return False
    
    async def _update_trial_state_and_enqueue_next(self, trial_id: int, results: Dict[str, Any]):
        """
        Update trial state and enqueue next stage (STUDYCARD).
        
        Args:
            trial_id: Trial ID
            results: OA processing results
        """
        try:
            # Update trial literature state
            metrics = self.db_service.calculate_trial_metrics(trial_id)
            self.db_service.update_trial_lit_state(trial_id, metrics)
            
            # Check if we should enqueue STUDY CARD stage
            if results['fulltext_stored'] > 0:
                # Calculate priority for study card stage
                priority = self._calculate_studycard_priority(trial_id, metrics)
                
                # Enqueue STUDY CARD task
                success = self.queue_service.enqueue_task(
                    task_type='STUDYCARD',
                    task_key=f'trial:{trial_id}:STUDYCARD',
                    priority=priority,
                    payload={
                        'trial_id': trial_id,
                        'fulltext_documents': results['fulltext_stored'],
                        'source': 'OA_worker'
                    },
                    trial_id=trial_id
                )
                
                if success:
                    self.logger.info(f"Enqueued STUDY CARD task for trial {trial_id} with priority {priority}")
                else:
                    self.logger.error(f"Failed to enqueue STUDY CARD task for trial {trial_id}")
            
        except Exception as e:
            self.logger.error(f"Error updating trial state for trial {trial_id}: {e}")
    
    def _calculate_studycard_priority(self, trial_id: int, metrics: Dict[str, Any]) -> float:
        """
        Calculate priority for STUDY CARD stage.
        
        Args:
            trial_id: Trial ID
            metrics: Trial metrics
            
        Returns:
            Priority score
        """
        # Base priority from trial metrics
        base_priority = 0.0
        
        # Best S score among R≥2 documents
        best_s_rge2 = metrics.get('best_S_Rge2', 0)
        if best_s_rge2:
            base_priority += 0.4 * best_s_rge2
        
        # Uncertainty (higher uncertainty = higher priority)
        uncertainty = metrics.get('uncertainty', 0)
        if uncertainty:
            base_priority += 0.3 * uncertainty
        
        # Number of selected documents
        n_selected = metrics.get('n_docs_selected', 0)
        if n_selected > 0:
            base_priority += 0.2 * min(n_selected / 10, 1.0)  # Cap at 10 docs
        
        # Add trial ID for deterministic ordering
        base_priority += trial_id / 1000000.0
        
        return base_priority
    
    async def run_worker(self, max_tasks: Optional[int] = None):
        """
        Run the OA worker continuously.
        
        Args:
            max_tasks: Maximum number of tasks to process (None for unlimited)
        """
        self.logger.info("Starting OA worker")
        tasks_processed = 0
        
        while True:
            try:
                # Clean up expired leases
                self.queue_service.cleanup_expired_leases()
                
                # Lease next task
                task_data = self.queue_service.lease_next(['PUBMED_OA'])
                if not task_data:
                    self.logger.debug("No PUBMED_OA tasks available, waiting...")
                    await asyncio.sleep(10)
                    continue
                
                # Process task
                result = await self.process_oa_task(task_data)
                
                if result.success:
                    self.queue_service.complete_task(task_data['id'])
                    self.logger.info(f"Completed OA task {task_data['id']} for trial {result.trial_id}")
                else:
                    self.queue_service.fail_task(task_data['id'], result.error_message or "Unknown error")
                    self.logger.error(f"Failed OA task {task_data['id']}: {result.error_message}")
                
                tasks_processed += 1
                
                # Check if we've reached max tasks
                if max_tasks and tasks_processed >= max_tasks:
                    self.logger.info(f"Reached max tasks limit ({max_tasks}), stopping worker")
                    break
                
            except KeyboardInterrupt:
                self.logger.info("Received interrupt signal, stopping worker")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in OA worker: {e}")
                await asyncio.sleep(5)
        
        self.logger.info(f"OA worker stopped after processing {tasks_processed} tasks")
