"""
PubMed literature processing pipeline.

Implements the three-stage pipeline (U0, U1, OA) for processing clinical trial literature.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import re

from .client import PubMedClient, PubMedBatchProcessor
from .query_builder import PubMedQueryBuilder
from .mapper import PubMedMapper

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for PubMed pipeline."""
    max_concurrent_requests: int = 5
    batch_size: int = 100
    rate_limit_per_sec: int = 8
    max_retries: int = 3
    timeout_seconds: int = 30
    enable_circuit_breaker: bool = True
    circuit_breaker_threshold: int = 5
    enable_fulltext_fetch: bool = True
    fulltext_ttl_days: int = 30
    enable_pmcid_linking: bool = True
    enable_oa_detection: bool = True


@dataclass
class PipelineResult:
    """Result from pipeline execution."""
    stage: str
    success: bool
    documents_processed: int
    documents_failed: int
    error_message: Optional[str] = None
    execution_time: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class PubMedPipeline:
    """End-to-end PubMed literature processing pipeline."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize PubMed pipeline.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Validate configuration before proceeding
        self._validate_config()
        
        # Initialize components
        client_config = self.config.get('client_config', {})
        self.client = PubMedClient(
            api_key=client_config.get('api_key'),
            rate_limit_per_sec=client_config.get('rate_limit_requests_per_minute', 8) // 60,  # Convert per minute to per second
            batch_size=client_config.get('batch_size', 100),
            max_retries=client_config.get('max_retries', 3),
            timeout_seconds=client_config.get('timeout_seconds', 30),
            circuit_breaker_threshold=client_config.get('circuit_breaker_threshold', 5),
            email=client_config.get('email', 'ncfd@example.com'),
            tool=client_config.get('tool', 'NCFD')
        )
        self.mapper = PubMedMapper(self.config.get('mapper_config', {}))
        self.query_builder = PubMedQueryBuilder(self.config.get('query_config', {}))
        self.batch_processor = PubMedBatchProcessor(self.client, self.config.get('max_concurrent_requests', 5))
        
        # Pipeline configuration
        self.asset_names = self.config.get('asset_names', [])
        self.indications = self.config.get('indications', [])
        self.max_results = self.config.get('max_results', 100)
        self.enable_stages = self.config.get('enable_stages', ['U0', 'U1', 'OA'])
        
        # Pipeline state
        self.stage_results: List[PipelineResult] = []
        self.current_stage: Optional[str] = None
        
        logger.info(f"PubMed Pipeline initialized with {len(self.asset_names)} assets, {len(self.indications)} indications")
    
    def _validate_config(self) -> None:
        """
        Validate pipeline configuration.
        
        Raises:
            ValueError: If configuration is invalid
        """
        errors = []
        warnings = []
        
        # Required fields
        required_fields = ['asset_names', 'indications']
        for field in required_fields:
            if not self.config.get(field):
                errors.append(f"Missing required field: {field}")
        
        # Validate asset_names
        asset_names = self.config.get('asset_names', [])
        if not isinstance(asset_names, list):
            errors.append("asset_names must be a list")
        elif len(asset_names) == 0:
            errors.append("asset_names cannot be empty")
        elif len(asset_names) > 10:
            warnings.append("More than 10 asset names may impact search performance")
        
        # Validate indications
        indications = self.config.get('indications', [])
        if not isinstance(indications, list):
            errors.append("indications must be a list")
        elif len(indications) == 0:
            errors.append("indications cannot be empty")
        elif len(indications) > 20:
            warnings.append("More than 20 indications may impact search performance")
        
        # Validate max_results
        max_results = self.config.get('max_results', 100)
        if not isinstance(max_results, int):
            errors.append("max_results must be an integer")
        elif max_results <= 0:
            errors.append("max_results must be positive")
        elif max_results > 10000:
            warnings.append("max_results > 10000 may cause performance issues")
        
        # Validate enable_stages
        enable_stages = self.config.get('enable_stages', ['U0', 'U1', 'OA'])
        valid_stages = ['U0', 'U1', 'OA']
        if not isinstance(enable_stages, list):
            errors.append("enable_stages must be a list")
        else:
            for stage in enable_stages:
                if stage not in valid_stages:
                    errors.append(f"Invalid stage: {stage}. Valid stages: {valid_stages}")
        
        # Validate retry configuration
        retry_config = self.config.get('retry_config', {})
        if retry_config:
            max_retries = retry_config.get('max_retries', 3)
            if not isinstance(max_retries, int) or max_retries < 0:
                errors.append("retry_config.max_retries must be a non-negative integer")
            
            retry_delay = retry_config.get('retry_delay', 1.0)
            if not isinstance(retry_delay, (int, float)) or retry_delay < 0:
                errors.append("retry_config.retry_delay must be a non-negative number")
        
        # Validate client configuration
        client_config = self.config.get('client_config', {})
        if client_config:
            rate_limit = client_config.get('rate_limit_requests_per_minute')
            if rate_limit is not None and (not isinstance(rate_limit, int) or rate_limit <= 0):
                errors.append("client_config.rate_limit_requests_per_minute must be a positive integer")
            
            timeout = client_config.get('timeout_seconds')
            if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
                errors.append("client_config.timeout_seconds must be a positive number")
        
        # Report warnings
        for warning in warnings:
            logger.warning(f"Configuration warning: {warning}")
        
        # Raise errors if any
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info("Configuration validation passed")
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """
        Update pipeline configuration with validation.
        
        Args:
            new_config: New configuration to merge
        """
        # Merge configurations
        merged_config = {**self.config, **new_config}
        
        # Validate merged configuration
        original_config = self.config
        self.config = merged_config
        
        try:
            self._validate_config()
            logger.info("Configuration updated successfully")
        except ValueError as e:
            # Revert on validation failure
            self.config = original_config
            raise ValueError(f"Configuration update failed: {e}")
    
    def get_config_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current configuration.
        
        Returns:
            Configuration summary
        """
        return {
            'asset_names': self.asset_names,
            'indications': self.indications,
            'max_results': self.max_results,
            'enable_stages': self.enable_stages,
            'retry_config': self.config.get('retry_config', {}),
            'client_config': self.config.get('client_config', {}),
            'validation_status': 'valid'
        }
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.client.__aenter__()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.__aexit__(exc_type, exc_val, exc_tb)
    
    async def execute_pipeline(
        self,
        asset_names: List[str],
        indications: List[str],
        trial_phases: Optional[List[str]] = None,
        date_range: Optional[Tuple[str, str]] = None,
        max_results: int = 1000,
        enable_stages: Optional[List[str]] = None
    ) -> List[PipelineResult]:
        """
        Execute the complete PubMed literature processing pipeline.
        
        Args:
            asset_names: List of drug/compound names
            indications: List of disease/indication terms
            trial_phases: List of trial phases to include
            date_range: Tuple of (start_date, end_date) in YYYY/MM/DD format
            max_results: Maximum number of results to process
            enable_stages: List of stages to enable (U0, U1, OA)
            
        Returns:
            List of pipeline results for each stage
        """
        if enable_stages is None:
            enable_stages = ['U0', 'U1', 'OA']
        
        logger.info(f"Starting PubMed pipeline for {len(asset_names)} assets, {len(indications)} indications")
        
        # Stage U0: Metadata-only search and discovery
        if 'U0' in enable_stages:
            u0_result = await self._execute_stage_u0(
                asset_names, indications, trial_phases, date_range, max_results
            )
            self.stage_results.append(u0_result)
            
            if not u0_result.success:
                logger.error(f"Stage U0 failed: {u0_result.error_message}")
                return self.stage_results
        
        # Stage U1: Abstract evaluation and scoring
        if 'U1' in enable_stages and self.stage_results[-1].success:
            u1_result = await self._execute_stage_u1()
            self.stage_results.append(u1_result)
            
            if not u1_result.success:
                logger.error(f"Stage U1 failed: {u1_result.error_message}")
                return self.stage_results
        
        # Stage OA: Full text retrieval and analysis
        if 'OA' in enable_stages and self.stage_results[-1].success:
            oa_result = await self._execute_stage_oa()
            self.stage_results.append(oa_result)
        
        logger.info("PubMed pipeline completed")
        return self.stage_results
    
    async def _execute_stage_u0(
        self,
        asset_names: List[str],
        indications: List[str],
        trial_phases: Optional[List[str]] = None,
        date_range: Optional[Tuple[str, str]] = None,
        max_results: int = 1000
    ) -> PipelineResult:
        """
        Execute Stage U0: Metadata discovery and initial filtering.
        
        This stage performs the initial PubMed search to discover relevant
        documents and extract basic metadata.
        """
        start_time = datetime.now()
        self.current_stage = 'U0'
        
        # Retry configuration
        max_retries = self.config.get('max_retries', 3)
        retry_delay = self.config.get('retry_delay', 1.0)
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Starting Stage U0: Metadata discovery (attempt {attempt + 1}/{max_retries})")
                
                # Build search query
                query = self.query_builder.build_trial_query(
                    asset_names=self.asset_names,
                    indications=self.indications
                )
                
                # Execute search with retry logic
                pmids = await self._execute_search_with_retry(query, max_retries=2)
                
                if not pmids:
                    logger.warning("No PMIDs found in search")
                    return PipelineResult(
                        stage='U0',
                        success=True,
                        documents_processed=0,
                        documents_failed=0,
                        metadata={'search_query': query, 'pmids_found': 0}
                    )
                
                # Map PMIDs to documents
                mapping_stats = await self._map_pmids_with_retry(pmids, max_retries=2)
                valid_docs = mapping_stats.get('valid_documents', [])
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                logger.info(f"Stage U0 completed: {len(pmids)} PMIDs found, {len(valid_docs)} valid documents")
                
                return PipelineResult(
                    stage='U0',
                    success=True,
                    documents_processed=len(valid_docs),
                    documents_failed=len(pmids) - len(valid_docs),
                    execution_time=execution_time,
                    metadata={
                        'search_query': query,
                        'pmids_found': len(pmids),
                        'mapping_stats': mapping_stats,
                        'valid_documents': valid_docs
                    }
                )
                
            except Exception as e:
                execution_time = (datetime.now() - start_time).total_seconds()
                error_msg = f"Stage U0 failed (attempt {attempt + 1}/{max_retries}): {str(e)}"
                logger.error(error_msg, exc_info=True)
                
                # If this is the last attempt, return error
                if attempt == max_retries - 1:
                    return PipelineResult(
                        stage='U0',
                        success=False,
                        documents_processed=0,
                        documents_failed=0,
                        error_message=error_msg,
                        execution_time=execution_time
                    )
                
                # Otherwise, wait and retry
                logger.info(f"Retrying Stage U0 in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
    
    async def _execute_search_with_retry(self, query: str, max_retries: int = 3) -> List[str]:
        """
        Execute PubMed search with retry logic.
        
        Args:
            query: Search query string
            max_retries: Maximum number of retry attempts
            
        Returns:
            List of PMIDs found
            
        Raises:
            Exception: If all retry attempts fail
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Executing search (attempt {attempt + 1}/{max_retries})")
                search_result = await self.client.esearch(query, max_results=self.max_results)
                pmids = search_result.get('idlist', [])
                logger.info(f"Search successful: {len(pmids)} PMIDs found")
                return pmids
            except Exception as e:
                logger.warning(f"Search attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"All search retry attempts failed for query: {query}")
                    raise
                await asyncio.sleep(1.0)  # Simple retry delay
    
    async def _map_pmids_with_retry(self, pmids: List[str], max_retries: int = 3) -> Dict[str, Any]:
        """
        Map PMIDs to documents with retry logic.
        
        Args:
            pmids: List of PMIDs to map
            max_retries: Maximum number of retry attempts
            
        Returns:
            Mapping statistics and valid documents
            
        Raises:
            Exception: If all retry attempts fail
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Mapping PMIDs (attempt {attempt + 1}/{max_retries})")
                metadata_results = await self.batch_processor.process_pmids_in_batches(
                    pmids, 'esummary'
                )
                mapped_documents = self.mapper.map_esummary_result(metadata_results)
                logger.info(f"Mapping successful: {len(mapped_documents)} valid documents")
                return {
                    'valid_documents': mapped_documents,
                    'total_pmids': len(pmids),
                    'mapped_count': len(mapped_documents),
                    'failed_count': len(pmids) - len(mapped_documents)
                }
            except Exception as e:
                logger.warning(f"Mapping attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"All mapping retry attempts failed for {len(pmids)} PMIDs")
                    raise
                await asyncio.sleep(1.0)  # Simple retry delay
    
    async def _execute_stage_u1(self) -> PipelineResult:
        """
        Execute Stage U1: Abstract evaluation and scoring.
        
        This stage processes the abstracts from Stage U0 to extract entities,
        perform initial scoring, and identify candidates for full text retrieval.
        """
        start_time = datetime.now()
        self.current_stage = 'U1'
        
        try:
            logger.info("Starting Stage U1: Abstract evaluation")
            
            # Get documents from previous stage
            u0_result = next((r for r in self.stage_results if r.stage == 'U0'), None)
            if not u0_result or not u0_result.success:
                raise Exception("Stage U0 must complete successfully before U1")
            
            documents = u0_result.metadata.get('valid_documents', [])
            if not documents:
                logger.warning("No documents available for Stage U1")
                return PipelineResult(
                    stage='U1',
                    success=True,
                    documents_processed=0,
                    documents_failed=0,
                    metadata={'documents_processed': 0}
                )
            
            # Import the proper U1 stage processor
            from .stage_u1 import StageU1Processor, StageU1Result
            from ...extract.abstract_features import AbstractFeatureExtractor
            from ...score.simple_rs_scorer import SimpleRSScorer
            
            # Initialize U1 processor with proper components
            feature_extractor = AbstractFeatureExtractor()
            rs_scorer = SimpleRSScorer()
            
            u1_processor = StageU1Processor(
                client=self.client,
                mapper=self.mapper,
                feature_extractor=feature_extractor,
                rs_scorer=rs_scorer,
                config={
                    'batch_size': self.config.get('batch_size', 10),
                    'enable_entity_extraction': True,
                    'enable_rs_scoring': True,
                    'min_r_score': 0.35,
                    'min_s_score': 0.20,
                    'max_abstracts_initial': 50
                }
            )
            
            # Execute U1 stage with proper abstract fetching
            u1_result = await u1_processor.execute_stage_u1(
                trial_id="test_trial",  # Use a default trial ID for testing
                u0_documents=documents,
                trial_asset=documents[0].get('title', 'Unknown')[:50] if documents else 'Unknown',
                trial_indication="Clinical Trial",
                trial_nct=None
            )
            
            if not u1_result.success:
                raise Exception(f"Stage U1 processor failed: {u1_result.error_message}")
            
            # Extract processed documents from U1 result
            processed_docs = u1_result.processed_documents or documents
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Stage U1 completed: {len(processed_docs)} processed, {u1_result.documents_selected} selected")
            
            return PipelineResult(
                stage='U1',
                success=True,
                documents_processed=len(processed_docs),
                documents_failed=u1_result.documents_dropped,
                execution_time=execution_time,
                metadata={
                    'documents_processed': len(processed_docs),
                    'fulltext_candidates': u1_result.documents_selected,
                    'processed_documents': processed_docs,
                    'fulltext_candidate_pmids': [doc.get('pmid') for doc in processed_docs],
                    'abstracts_fetched': u1_result.abstracts_fetched,
                    'entities_extracted': u1_result.entities_extracted,
                    'documents_scored': u1_result.documents_scored
                }
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"Stage U1 failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            return PipelineResult(
                stage='U1',
                success=False,
                documents_processed=0,
                documents_failed=0,
                error_message=error_msg,
                execution_time=execution_time
            )
    
    async def _execute_stage_oa(self) -> PipelineResult:
        """
        Execute Stage OA: Full text retrieval and analysis.
        
        This stage retrieves full text content for selected documents and
        performs comprehensive analysis including PMC linking and OA detection.
        """
        start_time = datetime.now()
        self.current_stage = 'OA'
        
        try:
            logger.info("Starting Stage OA: Full text retrieval")
            
            # Get fulltext candidates from previous stage
            u1_result = next((r for r in self.stage_results if r.stage == 'U1'), None)
            if not u1_result or not u1_result.success:
                raise Exception("Stage U1 must complete successfully before OA")
            
            fulltext_candidate_pmids = u1_result.metadata.get('fulltext_candidate_pmids', [])
            if not fulltext_candidate_pmids:
                logger.warning("No fulltext candidates available for Stage OA")
                return PipelineResult(
                    stage='OA',
                    success=True,
                    documents_processed=0,
                    documents_failed=0,
                    metadata={'documents_processed': 0}
                )
            
            # 1. Convert PMIDs to PMCIDs
            pmcid_mapping = {}
            if self.config.enable_pmcid_linking:
                pmcid_mapping = await self.client.elink_pmid_to_pmcid(fulltext_candidate_pmids)
                logger.info(f"Linked {len([p for p in pmcid_mapping.values() if p])} PMIDs to PMCIDs")
            
            # 2. Check PMC open access status
            pmcids = [pmcid for pmcid in pmcid_mapping.values() if pmcid]
            oa_status = {}
            if self.config.enable_oa_detection and pmcids:
                oa_status = await self.client.check_pmc_oa_status(pmcids)
                logger.info(f"Checked OA status for {len(oa_status)} PMCIDs")
            
            # 3. Fetch full text content for open access articles
            fulltext_docs = []
            failed_docs = 0
            
            for pmid in fulltext_candidate_pmids:
                try:
                    pmcid = pmcid_mapping.get(pmid)
                    if pmcid and oa_status.get(pmcid, {}).get('full_text_available', False):
                        # Fetch full text
                        fulltext_content = await self.client.get_pmc_full_text(pmcid)
                        if fulltext_content:
                            # Update document with full text
                            doc = self._find_document_by_pmid(pmid)
                            if doc:
                                doc['text']['fulltext_text'] = fulltext_content
                                doc['text']['char_count_fulltext'] = len(fulltext_content)
                                doc['text']['fulltext_ttl_date'] = (
                                    datetime.now(datetime.UTC) + timedelta(days=self.config.fulltext_ttl_days)
                                ).isoformat()
                                doc['content_type'] = 'fulltext'
                                fulltext_docs.append(doc)
                        
                        # Rate limiting
                        await asyncio.sleep(1.0 / self.config.rate_limit_per_sec)
                    
                except Exception as e:
                    failed_docs += 1
                    logger.warning(f"Failed to process PMID {pmid} for fulltext: {e}")
                    continue
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Stage OA completed: {len(fulltext_docs)} fulltext documents, {failed_docs} failed")
            
            return PipelineResult(
                stage='OA',
                success=True,
                documents_processed=len(fulltext_docs),
                documents_failed=failed_docs,
                execution_time=execution_time,
                metadata={
                    'documents_processed': len(fulltext_docs),
                    'pmcids_linked': len([p for p in pmcid_mapping.values() if p]),
                    'oa_articles_found': len([s for s in oa_status.values() if s.get('is_oa', False)]),
                    'fulltext_documents': fulltext_docs
                }
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"Stage OA failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            return PipelineResult(
                stage='OA',
                success=False,
                documents_processed=0,
                documents_failed=0,
                error_message=error_msg,
                execution_time=execution_time
            )
    
    def _extract_nct_ids(self, doc: Dict[str, Any]) -> List[str]:
        """Extract NCT IDs from document text."""
        nct_ids = []
        
        # Check title and abstract
        text_fields = [
            doc.get('title', ''),
            doc.get('text', {}).get('abstract_text', '')
        ]
        
        for text in text_fields:
            if text:
                # Look for NCT pattern
                matches = re.findall(r'NCT\d{8}', text, re.IGNORECASE)
                nct_ids.extend(matches)
        
        return list(set(nct_ids))  # Remove duplicates
    
    def _extract_sponsor_text(self, doc: Dict[str, Any]) -> Optional[str]:
        """Extract sponsor information from document."""
        # Check affiliations first
        if 'pubmed_meta' in doc:
            affiliations = doc['pubmed_meta'].get('affiliations_jsonb', [])
            for affil in affiliations:
                if isinstance(affil, dict):
                    institution = affil.get('institution', '')
                    if institution and any(keyword in institution.lower() for keyword in ['pharma', 'biotech', 'inc', 'ltd', 'corp']):
                        return institution
        
        # Check abstract for sponsor mentions
        abstract = doc.get('text', {}).get('abstract_text', '')
        if abstract:
            # Look for common sponsor patterns
            sponsor_patterns = [
                r'sponsored by ([^,\.]+)',
                r'funded by ([^,\.]+)',
                r'support from ([^,\.]+)'
            ]
            
            for pattern in sponsor_patterns:
                match = re.search(pattern, abstract, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        
        return None
    
    def _extract_clinical_entities(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Extract clinical entities from document text."""
        entities = {}
        
        abstract = doc.get('text', {}).get('abstract_text', '')
        if not abstract:
            return entities
        
        # Extract trial phase
        phase_patterns = [
            (r'phase\s*([IViv12]+)', 'phase'),
            (r'phase\s*([IViv12]+)\s*trial', 'phase'),
            (r'([IViv12]+)\s*phase', 'phase')
        ]
        
        for pattern, entity_type in phase_patterns:
            match = re.search(pattern, abstract, re.IGNORECASE)
            if match:
                entities[entity_type] = match.group(1).upper()
                break
        
        # Extract sample size
        sample_match = re.search(r'(\d+)\s*patients?', abstract, re.IGNORECASE)
        if sample_match:
            entities['sample_size'] = int(sample_match.group(1))
        
        # Extract endpoints
        endpoint_patterns = [
            r'primary\s+endpoint[s]?\s*:?\s*([^\.]+)',
            r'primary\s+outcome[s]?\s*:?\s*([^\.]+)',
            r'endpoint[s]?\s*:?\s*([^\.]+)'
        ]
        
        for pattern in endpoint_patterns:
            match = re.search(pattern, abstract, re.IGNORECASE)
            if match:
                entities['endpoints'] = match.group(1).strip()
                break
        
        return entities
    
    def _should_fetch_fulltext(self, doc: Dict[str, Any]) -> bool:
        """Determine if document should have full text fetched."""
        # Check if already has full text
        if doc.get('content_type') == 'fulltext':
            return False
        
        # Check initial scoring (placeholder logic)
        rs_score = doc.get('rs_score')
        if rs_score and hasattr(rs_score, 'R_score') and hasattr(rs_score, 'S_score'):
            r_score = rs_score.R_score
            s_score = rs_score.S_score
        else:
            r_score = 0
            s_score = 0
        
        # Fetch full text if both scores are above threshold
        return r_score > 0.3 and s_score > 0.3
    
    def _find_document_by_pmid(self, pmid: str) -> Optional[Dict[str, Any]]:
        """Find document by PMID from previous stage results."""
        for result in self.stage_results:
            if result.success and result.metadata:
                documents = result.metadata.get('valid_documents', [])
                for doc in documents:
                    if doc.get('pmid') == pmid:
                        return doc
        return None
    
    def get_pipeline_summary(self) -> Dict[str, Any]:
        """Get summary of pipeline execution."""
        if not self.stage_results:
            return {'status': 'not_started'}
        
        successful_stages = [r for r in self.stage_results if r.success]
        failed_stages = [r for r in self.stage_results if not r.success]
        
        total_docs_processed = sum(r.documents_processed for r in successful_stages)
        total_docs_failed = sum(r.documents_failed for r in self.stage_results)
        total_execution_time = sum(r.execution_time or 0 for r in self.stage_results)
        
        return {
            'status': 'completed' if not failed_stages else 'partial_failure',
            'stages_completed': len(successful_stages),
            'stages_failed': len(failed_stages),
            'total_documents_processed': total_docs_processed,
            'total_documents_failed': total_docs_failed,
            'total_execution_time': total_execution_time,
            'stage_results': [
                {
                    'stage': r.stage,
                    'success': r.success,
                    'documents_processed': r.documents_processed,
                    'documents_failed': r.documents_failed,
                    'execution_time': r.execution_time,
                    'error_message': r.error_message
                }
                for r in self.stage_results
            ]
        }
    
    async def run_daily_ingestion(
        self, 
        force_full_scan: bool = False,
        trial_configs: Optional[List[Dict[str, Any]]] = None,
        pipeline_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run daily ingestion for PubMed pipeline.
        
        This method provides a synchronous interface for the orchestrator
        while maintaining the async nature of the underlying pipeline.
        
        Args:
            force_full_scan: Force full scan for all trials
            trial_configs: List of trial configurations to process
            pipeline_config: Pipeline configuration to use
            
        Returns:
            Dictionary with ingestion results
        """
        try:
            # Update pipeline configuration if provided
            if pipeline_config:
                self.update_config(pipeline_config)
            
            # Default trial configuration if none provided
            if trial_configs is None:
                trial_configs = [
                    {
                        'trial_id': 'default_trial',
                        'asset_names': ['drug', 'compound', 'therapy'],
                        'indications': ['disease', 'condition'],
                        'max_results': 100
                    }
                ]
            
            total_documents_processed = 0
            total_documents_failed = 0
            successful_trials = 0
            failed_trials = 0
            errors = []
            warnings = []
            
            # Process each trial configuration
            for trial_config in trial_configs:
                try:
                    trial_id = trial_config['trial_id']
                    asset_names = trial_config['asset_names']
                    indications = trial_config['indications']
                    max_results = trial_config.get('max_results', 100)
                    
                    logger.info(f"Processing trial {trial_id} with {len(asset_names)} assets, {len(indications)} indications")
                    
                    # Execute pipeline for this trial
                    results = await self.execute_pipeline(
                        asset_names=asset_names,
                        indications=indications,
                        max_results=max_results,
                        enable_stages=['U0', 'U1']  # Skip OA for daily ingestion
                    )
                    
                    # Aggregate results
                    for result in results:
                        if result.success:
                            total_documents_processed += result.documents_processed
                            total_documents_failed += result.documents_failed
                        else:
                            errors.append(f"Stage {result.stage} failed for trial {trial_id}: {result.error_message}")
                    
                    successful_trials += 1
                    
                except Exception as e:
                    failed_trials += 1
                    error_msg = f"Failed to process trial {trial_config.get('trial_id', 'unknown')}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)
                    continue
            
            # Prepare result for orchestrator
            return {
                'success': len(errors) == 0,
                'documents_processed': total_documents_processed,
                'documents_failed': total_documents_failed,
                'successful_trials': successful_trials,
                'failed_trials': failed_trials,
                'errors': errors,
                'warnings': warnings,
                'pipeline_summary': self.get_pipeline_summary()
            }
            
        except Exception as e:
            error_msg = f"PubMed daily ingestion failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'documents_processed': 0,
                'documents_failed': 0,
                'successful_trials': 0,
                'failed_trials': 1,
                'errors': [error_msg],
                'warnings': [],
                'pipeline_summary': {'status': 'failed', 'error': error_msg}
            }
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status for orchestrator."""
        return {
            'status': 'ready' if self.stage_results else 'not_started',
            'stages_completed': len([r for r in self.stage_results if r.success]),
            'stages_failed': len([r for r in self.stage_results if not r.success]),
            'total_documents_processed': sum(r.documents_processed for r in self.stage_results if r.success),
            'last_execution': self.stage_results[-1].execution_time if self.stage_results else None
        }
    
    def _should_retry_stage(self, stage_result: PipelineResult, max_failures: int = 3) -> bool:
        """
        Determine if a stage should be retried based on failure patterns.
        
        Args:
            stage_result: Result from the failed stage
            max_failures: Maximum number of failures before giving up
            
        Returns:
            True if stage should be retried, False otherwise
        """
        # Count consecutive failures for this stage
        stage_failures = sum(1 for r in self.stage_results 
                           if r.stage == stage_result.stage and not r.success)
        
        # Don't retry if we've exceeded max failures
        if stage_failures >= max_failures:
            logger.warning(f"Stage {stage_result.stage} has failed {stage_failures} times, not retrying")
            return False
        
        # Don't retry if error is unrecoverable
        unrecoverable_errors = [
            'invalid_query', 'authentication_failed', 'rate_limit_exceeded'
        ]
        
        error_message = stage_result.error_message.lower()
        if any(error in error_message for error in unrecoverable_errors):
            logger.info(f"Stage {stage_result.stage} failed with unrecoverable error: {stage_result.error_message}")
            return False
        
        return True
    
    def _get_recovery_strategy(self, stage_result: PipelineResult) -> Dict[str, Any]:
        """
        Get recovery strategy for a failed stage.
        
        Args:
            stage_result: Result from the failed stage
            
        Returns:
            Recovery strategy configuration
        """
        base_strategy = {
            'retry_count': 0,
            'max_retries': 3,
            'retry_delay': 1.0,
            'backoff_multiplier': 2.0,
            'graceful_degradation': True
        }
        
        # Customize strategy based on stage and error type
        if stage_result.stage == 'U0':
            # U0 failures are critical - be more aggressive with retries
            base_strategy['max_retries'] = 5
            base_strategy['retry_delay'] = 0.5
        elif stage_result.stage == 'U1':
            # U1 failures can be more lenient
            base_strategy['max_retries'] = 3
            base_strategy['retry_delay'] = 2.0
        elif stage_result.stage == 'OA':
            # OA failures are least critical
            base_strategy['max_retries'] = 2
            base_strategy['graceful_degradation'] = True
        
        return base_strategy
