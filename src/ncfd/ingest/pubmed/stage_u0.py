"""
Stage U0: Metadata Discovery.

Runs ESearch/ESummary → prepares documents + document_citations.
Seeds trial_doc_candidates (stage=U0_meta).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .client import PubMedClient
from .trial_query_builder import TrialQueryBuilder
from .mapper import PubMedMapper

logger = logging.getLogger(__name__)


@dataclass
class StageU0Result:
    """Result from Stage U0 execution."""
    trial_id: str
    success: bool
    documents_discovered: int
    documents_mapped: int
    pmids_found: int
    execution_time: float
    error_message: Optional[str] = None
    query_metadata: Optional[Dict[str, Any]] = None
    mapped_documents: Optional[List[Dict[str, Any]]] = None


class StageU0Processor:
    """Processes Stage U0: Metadata Discovery."""
    
    def __init__(
        self,
        client: PubMedClient,
        query_builder: TrialQueryBuilder,
        mapper: PubMedMapper,
        config: Optional[Dict] = None
    ):
        """
        Initialize Stage U0 processor.
        
        Args:
            client: PubMed client instance
            query_builder: Trial query builder instance
            mapper: Response mapper instance
            config: Configuration dictionary
        """
        self.client = client
        self.query_builder = query_builder
        self.mapper = mapper
        self.config = config or {}
        
        # Stage U0 settings
        self.max_results_per_trial = self.config.get('max_results_per_trial', 100)
        self.batch_size = self.config.get('batch_size', 20)
        self.enable_prefiltering = self.config.get('enable_prefiltering', True)
        self.prefilter_sample_size = self.config.get('prefilter_sample_size', 200)
    
    async def execute_stage_u0(
        self,
        trial_id: str,
        asset_aliases: List[str],
        indication_terms: List[str],
        trial_nct: Optional[str] = None,
        trial_phase: Optional[str] = None,
        trial_design: Optional[str] = None,
        catalyst_date: Optional[datetime] = None,
        max_results: Optional[int] = None
    ) -> StageU0Result:
        """
        Execute Stage U0: Metadata Discovery.
        
        Args:
            trial_id: Unique trial identifier
            asset_aliases: List of asset names/aliases
            indication_terms: List of disease/indication terms
            trial_nct: Optional NCT ID for exact matching
            trial_phase: Optional trial phase for filtering
            trial_design: Optional trial design for filtering
            catalyst_date: Optional catalyst date for recency bias
            max_results: Maximum results to process (overrides config)
            
        Returns:
            StageU0Result with execution details
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            logger.info(f"Starting Stage U0 for trial {trial_id}")
            
            # 1. Build trial-specific query
            query_result = self.query_builder.build_trial_query(
                trial_id=trial_id,
                asset_aliases=asset_aliases,
                indication_terms=indication_terms,
                trial_nct=trial_nct,
                trial_phase=trial_phase,
                trial_design=trial_design,
                catalyst_date=catalyst_date,
                max_results=max_results or self.max_results_per_trial
            )
            
            query_string = query_result['query_string']
            query_metadata = query_result['metadata']
            
            logger.info(f"Built query for {trial_id}: {len(query_string)} chars")
            
            # 2. Execute PubMed search with pagination using client as context manager
            async with self.client:
                # Use pagination to get full result set up to max_results
                search_result = await self.client.esearch_all(
                    query_string, 
                    max_results=query_result['max_results'],
                    use_history=True
                )
                
                pmids = search_result.get('idlist', [])
                total_count = search_result.get('count', 0)
                webenv = search_result.get('webenv')
                query_key = search_result.get('querykey')
                
                if not pmids:
                    logger.warning(f"No PMIDs found for trial {trial_id}")
                    return StageU0Result(
                        trial_id=trial_id,
                        success=True,
                        documents_discovered=0,
                        documents_mapped=0,
                        pmids_found=0,
                        execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                        query_metadata=query_metadata
                    )
                
                logger.info(f"Found {len(pmids)} PMIDs for trial {trial_id} (total: {total_count})")
                if webenv and query_key:
                    logger.info(f"Using WebEnv: {webenv}, QueryKey: {query_key}")
                
                # 3. Pre-filter PMIDs if enabled (now processes ALL PMIDs, not just first 50)
                if self.enable_prefiltering:
                    pmids = await self._prefilter_pmids_full(pmids, trial_id)
                    logger.info(f"After pre-filtering: {len(pmids)} PMIDs")
                
                # 4. Fetch metadata for PMIDs
                metadata_results = await self._fetch_metadata_batch(pmids)
                
                if not metadata_results:
                    logger.warning(f"No metadata retrieved for trial {trial_id}")
                    return StageU0Result(
                        trial_id=trial_id,
                        success=True,
                        documents_discovered=len(pmids),
                        documents_mapped=0,
                        pmids_found=len(pmids),
                        execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                        query_metadata=query_metadata
                    )
                
                # 5. Map to our document format
                mapped_documents = self.mapper.map_esummary_result(metadata_results)
                
                # 6. Add trial-specific metadata
                enriched_documents = self._enrich_documents_for_trial(
                    mapped_documents, trial_id, query_metadata
                )
                
                # 7. Prepare trial_doc_candidates
                candidates = self._prepare_trial_candidates(
                    enriched_documents, trial_id, 'U0_meta'
                )
                
                execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                
                logger.info(f"Stage U0 completed for {trial_id}: "
                           f"{len(enriched_documents)} documents mapped in {execution_time:.2f}s")
                
                return StageU0Result(
                    trial_id=trial_id,
                    success=True,
                    documents_discovered=len(pmids),
                    documents_mapped=len(enriched_documents),
                    pmids_found=len(pmids),
                    execution_time=execution_time,
                    query_metadata=query_metadata,
                    mapped_documents=enriched_documents
                )
            
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            error_msg = f"Stage U0 failed for trial {trial_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            return StageU0Result(
                trial_id=trial_id,
                success=False,
                documents_discovered=0,
                documents_mapped=0,
                pmids_found=0,
                execution_time=execution_time,
                error_message=error_msg
            )
    
    async def _prefilter_pmids_full(
        self, 
        pmids: List[str], 
        trial_id: str
    ) -> List[str]:
        """
        Pre-filter ALL PMIDs to remove obvious non-clinical items.
        
        Args:
            pmids: List of PMIDs to filter
            trial_id: Trial ID for logging
            
        Returns:
            Filtered list of PMIDs
        """
        if not self.enable_prefiltering or not pmids:
            return pmids
        
        try:
            logger.info(f"Pre-filtering {len(pmids)} PMIDs for trial {trial_id}")
            
            # Fetch metadata for ALL PMIDs in batches
            all_metadata = await self._fetch_metadata_batch(pmids)
            
            filtered_pmids = []
            filtered_count = 0
            
            for pmid in pmids:
                if pmid in all_metadata:
                    doc_data = all_metadata[pmid]
                    
                    # Check if document passes basic filters
                    if self._passes_prefilter(doc_data):
                        filtered_pmids.append(pmid)
                    else:
                        filtered_count += 1
                        logger.debug(f"PMID {pmid} filtered out during pre-filtering")
                else:
                    # If we can't get metadata, include it (conservative)
                    filtered_pmids.append(pmid)
                    logger.debug(f"PMID {pmid} included (no metadata available)")
            
            logger.info(f"Pre-filtering: {len(pmids)} -> {len(filtered_pmids)} PMIDs ({filtered_count} filtered out)")
            return filtered_pmids
            
        except Exception as e:
            logger.warning(f"Pre-filtering failed for trial {trial_id}: {e}")
            return pmids  # Return original list if filtering fails
    
    def _passes_prefilter(self, doc_data: Dict[str, Any]) -> bool:
        """
        Check if document passes pre-filtering criteria.
        
        Args:
            doc_data: Document metadata from ESummary
            
        Returns:
            True if document passes filters
        """
        try:
            # Check publication type
            pub_types = doc_data.get('pubtype', [])
            if not pub_types:
                return True  # Include if we can't determine type
            
            # Filter out obvious non-clinical items
            exclude_types = [
                'Editorial', 'Letter', 'Comment', 'News', 'Interview',
                'Biography', 'Historical Article', 'Portrait'
            ]
            
            for pub_type in pub_types:
                if any(exclude in pub_type for exclude in exclude_types):
                    return False
            
            # Check if it's a clinical trial or related
            clinical_types = [
                'Clinical Trial', 'Randomized Controlled Trial',
                'Controlled Clinical Trial', 'Clinical Study',
                'Case Report'  # Removed Review/Meta-Analysis to be more selective
            ]
            
            for pub_type in pub_types:
                if any(clinical in pub_type for clinical in clinical_types):
                    return True
            
            # Check title for clinical keywords
            title = doc_data.get('title', '').lower()
            clinical_keywords = [
                'trial', 'study', 'clinical', 'patient', 'treatment',
                'therapy', 'drug', 'medication', 'outcome', 'efficacy'
            ]
            
            if any(keyword in title for keyword in clinical_keywords):
                return True
            
            # Default to include if uncertain
            return True
            
        except Exception as e:
            logger.warning(f"Pre-filter check failed: {e}")
            return True  # Include if we can't determine
    
    async def _fetch_metadata_batch(self, pmids: List[str]) -> Dict[str, Any]:
        """
        Fetch metadata for PMIDs in batches.
        
        Args:
            pmids: List of PMIDs to fetch
            
        Returns:
            Metadata results dictionary
        """
        if not pmids:
            return {}
        
        all_results = {}
        
        # Process in batches
        for i in range(0, len(pmids), self.batch_size):
            batch = pmids[i:i + self.batch_size]
            
            try:
                batch_results = await self.client.esummary_batch(batch)
                all_results.update(batch_results)
                
                logger.debug(f"Fetched metadata for batch {i//self.batch_size + 1}: "
                           f"{len(batch)} PMIDs")
                
                # Rate limiting between batches
                if i + self.batch_size < len(pmids):
                    await asyncio.sleep(0.1)  # Small delay between batches
                    
            except Exception as e:
                logger.warning(f"Failed to fetch batch {i//self.batch_size + 1}: {e}")
                continue
        
        return all_results
    
    def _enrich_documents_for_trial(
        self, 
        documents: List[Dict[str, Any]], 
        trial_id: str,
        query_metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Enrich documents with trial-specific information.
        
        Args:
            documents: List of mapped documents
            trial_id: Trial ID
            query_metadata: Query metadata
            
        Returns:
            Enriched documents
        """
        enriched = []
        
        for doc in documents:
            try:
                # Add trial context
                doc['trial_context'] = {
                    'trial_id': trial_id,
                    'query_metadata': query_metadata,
                    'enriched_at': datetime.now(timezone.utc).isoformat()
                }
                
                # Add stage information
                doc['stage'] = 'U0_meta'
                doc['stage_metadata'] = {
                    'stage': 'U0_meta',
                    'stage_description': 'Metadata discovery completed',
                    'stage_completed_at': datetime.now(timezone.utc).isoformat()
                }
                
                enriched.append(doc)
                
            except Exception as e:
                logger.warning(f"Failed to enrich document: {e}")
                continue
        
        return enriched
    
    def _prepare_trial_candidates(
        self, 
        documents: List[Dict[str, Any]], 
        trial_id: str,
        stage: str
    ) -> List[Dict[str, Any]]:
        """
        Prepare trial_doc_candidates entries.
        
        Args:
            documents: List of enriched documents
            trial_id: Trial ID
            stage: Current stage
            
        Returns:
            List of candidate entries
        """
        candidates = []
        
        for doc in documents:
            try:
                candidate = {
                    'trial_id': trial_id,
                    'doc_id': None,  # Will be assigned during database insertion
                    'pmid': doc.get('pmid'),
                    'stage': stage,
                    'selected': True,  # All U0 documents are selected initially
                    'dropped_reason': None,
                    'notes': f'Discovered in Stage U0 at {datetime.now(timezone.utc).isoformat()}',
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                
                candidates.append(candidate)
                
            except Exception as e:
                logger.warning(f"Failed to prepare candidate: {e}")
                continue
        
        return candidates
    
    def get_stage_u0_stats(self, result: StageU0Result) -> Dict[str, Any]:
        """
        Get statistics about Stage U0 execution.
        
        Args:
            result: Stage U0 result
            
        Returns:
            Statistics dictionary
        """
        if not result.success:
            return {
                'trial_id': result.trial_id,
                'success': False,
                'error': result.error_message
            }
        
        return {
            'trial_id': result.trial_id,
            'success': True,
            'execution_time_seconds': result.execution_time,
            'documents_discovered': result.documents_discovered,
            'documents_mapped': result.documents_mapped,
            'pmids_found': result.pmids_found,
            'mapping_efficiency': (
                result.documents_mapped / result.documents_discovered 
                if result.documents_discovered > 0 else 0
            ),
            'query_metadata': result.query_metadata
        }
