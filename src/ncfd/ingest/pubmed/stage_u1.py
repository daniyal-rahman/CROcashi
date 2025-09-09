"""
Stage U1: Abstract Processing.

EFetch abstracts → write document_text.abstract_text.
Extract quick entities (NCT, phase/design, HR/ORR/p/CI/N).
Emit coarse document_links (nct_in_text / asset_in_text).
Compute R and S per (trial, doc) → doc_rs_scores.
Select/Drop docs based on R/S tier rules; advance candidates.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .client import PubMedClient
from .mapper import PubMedMapper
from .db_service import PubMedDBService
from .trial_query_builder import TrialQueryBuilder
from ...extract.abstract_features import AbstractFeatureExtractor
from ...score.simple_rs_scorer import SimpleRSScorer

logger = logging.getLogger(__name__)


@dataclass
class StageU1Result:
    """Result from Stage U1+ execution."""
    trial_id: int
    success: bool
    # Discovery metrics (U1+ mode)
    documents_discovered: int = 0
    documents_mapped: int = 0
    pmids_found: int = 0
    # Processing metrics
    documents_processed: int = 0
    abstracts_fetched: int = 0
    entities_extracted: int = 0
    documents_scored: int = 0
    documents_selected: int = 0
    documents_dropped: int = 0
    execution_time: float = 0.0
    error_message: Optional[str] = None
    processed_documents: Optional[List[Dict[str, Any]]] = None
    rs_scores: Optional[List[Dict[str, Any]]] = None
    # Database persistence results
    documents_stored: int = 0
    documents_failed: int = 0
    abstracts_stored: int = 0
    abstracts_failed: int = 0
    rs_scores_stored: int = 0
    rs_scores_failed: int = 0
    candidates_stored: int = 0
    candidates_failed: int = 0
    links_stored: int = 0
    links_failed: int = 0
    trial_state_updated: bool = False
    # Query audit
    query_metadata: Optional[Dict[str, Any]] = None


class StageU1Processor:
    """Processes Stage U1+: Unified Discovery and Abstract Processing."""
    
    def __init__(
        self,
        client: PubMedClient,
        mapper: PubMedMapper,
        feature_extractor: AbstractFeatureExtractor,
        rs_scorer: SimpleRSScorer,
        query_builder: Optional[TrialQueryBuilder] = None,
        config: Optional[Dict] = None
    ):
        """
        Initialize Stage U1+ processor.
        
        Args:
            client: PubMed client instance
            mapper: Response mapper instance
            feature_extractor: Feature extraction instance
            rs_scorer: R/S scoring instance
            query_builder: Trial query builder instance (required for discovery mode)
            config: Configuration dictionary
        """
        self.client = client
        self.mapper = mapper
        self.feature_extractor = feature_extractor
        self.rs_scorer = rs_scorer
        self.query_builder = query_builder
        self.config = config or {}
        
        # Initialize database service
        self.db_service = PubMedDBService()
        
        # Stage U1+ settings
        self.batch_size = self.config.get('batch_size', 10)
        self.enable_entity_extraction = self.config.get('enable_entity_extraction', True)
        self.enable_rs_scoring = self.config.get('enable_rs_scoring', True)
        self.min_r_score = self.config.get('min_r_score', 0.35)  # R1 threshold
        self.min_s_score = self.config.get('min_s_score', 0.20)  # S1 threshold
        self.max_abstracts_initial = self.config.get('max_abstracts_initial', 50)  # Max abstracts to process initially
        self.enable_database_persistence = self.config.get('enable_database_persistence', True)
        
        # Discovery settings (U1+ mode)
        self.max_results_per_trial = self.config.get('max_results_per_trial', 100)
        self.enable_prefiltering = self.config.get('enable_prefiltering', True)
        self.prefilter_sample_size = self.config.get('prefilter_sample_size', 200)
    
    async def execute_stage_u1(
        self,
        trial_id: int,
        trial_asset: str,
        trial_indication: str,
        trial_nct: Optional[str] = None,
        u0_documents: Optional[List[Dict[str, Any]]] = None,
        asset_aliases: Optional[List[str]] = None,
        indication_terms: Optional[List[str]] = None,
        trial_phase: Optional[str] = None,
        trial_design: Optional[str] = None,
        catalyst_date: Optional[datetime] = None,
        max_results: Optional[int] = None
    ) -> StageU1Result:
        """
        Execute Stage U1+: Unified Discovery and Abstract Processing.
        
        Supports two modes:
        1. Discovery+Process mode: If u0_documents is None, performs discovery then processing
        2. Process-only mode: If u0_documents is provided, skips discovery and processes existing documents
        
        Args:
            trial_id: Unique trial identifier (integer)
            trial_asset: Asset name for scoring
            trial_indication: Indication for scoring
            trial_nct: Optional NCT ID for scoring
            u0_documents: Documents from previous stage (None for discovery mode)
            asset_aliases: List of asset names/aliases (required for discovery mode)
            indication_terms: List of disease/indication terms (required for discovery mode)
            trial_phase: Optional trial phase for filtering (discovery mode)
            trial_design: Optional trial design for filtering (discovery mode)
            catalyst_date: Optional catalyst date for recency bias (discovery mode)
            max_results: Maximum results to process (discovery mode)
            
        Returns:
            StageU1Result with execution details
        """
        start_time = datetime.now(timezone.utc)
        
        try:
            # Determine execution mode
            discovery_mode = u0_documents is None
            
            if discovery_mode:
                logger.info(f"Starting Stage U1+ (Discovery+Process) for trial {trial_id}")
                
                # Validate required parameters for discovery mode
                if not asset_aliases or not indication_terms:
                    raise ValueError("asset_aliases and indication_terms are required for discovery mode")
                if not self.query_builder:
                    raise ValueError("query_builder is required for discovery mode")
                
                # Perform discovery
                discovery_result = await self._perform_discovery(
                    trial_id, asset_aliases, indication_terms, trial_nct,
                    trial_phase, trial_design, catalyst_date, max_results
                )
                
                if not discovery_result['success']:
                    return StageU1Result(
                        trial_id=trial_id,
                        success=False,
                        execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                        error_message=discovery_result['error_message']
                    )
                
                u0_documents = discovery_result['documents']
                query_metadata = discovery_result['query_metadata']
                documents_discovered = discovery_result['documents_discovered']
                documents_mapped = discovery_result['documents_mapped']
                pmids_found = discovery_result['pmids_found']
                
                logger.info(f"Discovery completed: {documents_discovered} discovered, {documents_mapped} mapped")
            else:
                logger.info(f"Starting Stage U1+ (Process-only) for trial {trial_id} with {len(u0_documents)} documents")
                query_metadata = None
                documents_discovered = 0
                documents_mapped = len(u0_documents)
                pmids_found = len(u0_documents)
            
            if not u0_documents:
                logger.warning(f"No documents to process for trial {trial_id}")
                return StageU1Result(
                    trial_id=trial_id,
                    success=True,
                    documents_discovered=documents_discovered,
                    documents_mapped=documents_mapped,
                    pmids_found=pmids_found,
                    documents_processed=0,
                    abstracts_fetched=0,
                    entities_extracted=0,
                    documents_scored=0,
                    documents_selected=0,
                    documents_dropped=0,
                    execution_time=(datetime.now(timezone.utc) - start_time).total_seconds(),
                    query_metadata=query_metadata
                )
            
            # 1. Fetch abstracts for documents using XML method for reliability
            abstracts_fetched = await self._fetch_abstracts_xml_batch(u0_documents)
            
            if not abstracts_fetched:
                logger.warning(f"No abstracts fetched for trial {trial_id}")
                return StageU1Result(
                    trial_id=trial_id,
                    success=True,
                    documents_processed=len(u0_documents),
                    abstracts_fetched=0,
                    entities_extracted=0,
                    documents_scored=0,
                    documents_selected=0,
                    documents_dropped=0,
                    execution_time=(datetime.now(timezone.utc) - start_time).total_seconds()
                )
            
            logger.info(f"Fetched abstracts for {len(abstracts_fetched)} documents")
            
            # 1.5. PERSIST ABSTRACTS TO DATABASE
            abstracts_stored = 0
            abstracts_failed = 0
            if self.enable_database_persistence:
                try:
                    successful, failed = self.db_service.store_abstracts(u0_documents, abstracts_fetched)
                    abstracts_stored = successful
                    abstracts_failed = failed
                    logger.info(f"Stored {successful} abstracts to database, {failed} failed")
                except Exception as e:
                    logger.error(f"Failed to store abstracts to database: {e}")
                    abstracts_failed = len(abstracts_fetched)
            
            # 2. Extract entities from abstracts
            documents_with_entities = []
            total_entities = 0
            
            if self.enable_entity_extraction:
                for doc in u0_documents:
                    pmid = doc.get('pmid')
                    if pmid and pmid in abstracts_fetched:
                        abstract_text = abstracts_fetched[pmid]
                        
                        # Extract entities
                        entities = self.feature_extractor.extract_all_features(abstract_text)
                        doc['extracted_entities'] = entities
                        doc['abstract_text'] = abstract_text
                        
                        total_entities += len(entities)
                        documents_with_entities.append(doc)
                        
                        logger.debug(f"Extracted {len(entities)} entities from PMID {pmid}")
                    else:
                        documents_with_entities.append(doc)
            else:
                documents_with_entities = u0_documents
            
            # 3. Create document links
            documents_with_links = self._create_document_links(
                documents_with_entities, trial_asset, trial_nct
            )
            
            # 4. Compute R/S scores
            documents_scored = []
            rs_scores = []
            
            if self.enable_rs_scoring:
                # Ensure ESummary metadata is available for scoring
                documents_for_scoring = self._prepare_documents_for_scoring(documents_with_links)
                
                scored_docs = self.rs_scorer.score_batch(
                    documents_for_scoring, trial_asset, trial_indication, trial_nct, asset_aliases
                )
                
                for doc, score in scored_docs:
                    # Add score to document using the new standardized format
                    doc['rs_score'] = score  # RSScore object with full components
                    
                    # Store additional metadata for convenience
                    doc['rs_summary'] = {
                        'R_score': score.R_score,
                        'S_score': score.S_score,
                        'R_tier': score.R_tier,
                        'S_tier': score.S_tier,
                        'confidence': score.confidence
                    }
                    
                    documents_scored.append(doc)
                    
                    # Prepare R/S score record for database
                    rs_record = self._prepare_rs_score_record(
                        trial_id, doc, score
                    )
                    rs_scores.append(rs_record)
                    
                    logger.debug(f"Scored PMID {doc.get('pmid')}: R{score.R_tier} S{score.S_tier}")
            else:
                documents_scored = documents_with_links
            
            # 5. Apply selection/drop rules
            selected_docs, dropped_docs = self._apply_selection_rules(documents_scored)
            
            # 6. Update stage information
            final_documents = self._update_stage_information(
                selected_docs, 'U1_abstract'
            )
            
            # 7. PERSIST DATA TO DATABASE (NEW!)
            rs_scores_stored = 0
            rs_scores_failed = 0
            candidates_stored = 0
            candidates_failed = 0
            links_stored = 0
            links_failed = 0
            trial_state_updated = False
            
            if self.enable_database_persistence:
                try:
                    # trial_id is already an integer, no conversion needed
                    trial_id_int = trial_id
                    
                    # Store document links
                    if documents_with_links:
                        successful, failed = self.db_service.store_document_links(trial_id_int, documents_with_links)
                        links_stored = successful
                        links_failed = failed
                        logger.info(f"Stored {successful} document links, {failed} failed")
                    
                    if trial_id_int is not None:
                        # Store R/S scores
                        if rs_scores:
                            successful, failed = self.db_service.store_rs_scores(trial_id_int, rs_scores)
                            rs_scores_stored = successful
                            rs_scores_failed = failed
                            logger.info(f"Stored {successful} R/S scores, {failed} failed")
                        
                        # Store trial-document candidates
                        candidates_data = self._prepare_candidates_data(
                            trial_id_int, final_documents, selected_docs, dropped_docs
                        )
                        if candidates_data:
                            successful, failed = self.db_service.store_trial_doc_candidates(
                                trial_id_int, candidates_data
                            )
                            candidates_stored = successful
                            candidates_failed = failed
                            logger.info(f"Stored {successful} trial-doc candidates, {failed} failed")
                        
                        # Update trial literature state
                        trial_metrics = self.db_service.calculate_trial_metrics(trial_id_int)
                        if trial_metrics:
                            trial_state_updated = self.db_service.update_trial_lit_state(
                                trial_id_int, trial_metrics
                            )
                            if trial_state_updated:
                                logger.info(f"Updated trial literature state for trial {trial_id}")
                        
                    else:
                        logger.warning(f"Could not convert trial_id '{trial_id}' to int for database operations")
                        
                except Exception as e:
                    logger.error(f"Failed to persist data to database: {e}")
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            logger.info(f"Stage U1 completed for {trial_id}: "
                       f"{len(documents_scored)} scored, {len(selected_docs)} selected, "
                       f"{len(dropped_docs)} dropped in {execution_time:.2f}s")
            
            return StageU1Result(
                trial_id=trial_id,
                success=True,
                documents_discovered=documents_discovered,
                documents_mapped=documents_mapped,
                pmids_found=pmids_found,
                documents_processed=len(u0_documents),
                abstracts_fetched=len(abstracts_fetched),
                entities_extracted=total_entities,
                documents_scored=len(documents_scored),
                documents_selected=len(selected_docs),
                documents_dropped=len(dropped_docs),
                execution_time=execution_time,
                processed_documents=final_documents,
                rs_scores=rs_scores,
                documents_stored=0,  # Will be updated when we add discovery persistence
                documents_failed=0,
                abstracts_stored=abstracts_stored,
                abstracts_failed=abstracts_failed,
                rs_scores_stored=rs_scores_stored,
                rs_scores_failed=rs_scores_failed,
                candidates_stored=candidates_stored,
                candidates_failed=candidates_failed,
                links_stored=links_stored,
                links_failed=links_failed,
                trial_state_updated=trial_state_updated,
                query_metadata=query_metadata
            )
            
        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            error_msg = f"Stage U1 failed for trial {trial_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            return StageU1Result(
                trial_id=trial_id,
                success=False,
                documents_discovered=0,
                documents_mapped=0,
                pmids_found=0,
                documents_processed=0,
                abstracts_fetched=0,
                entities_extracted=0,
                documents_scored=0,
                documents_selected=0,
                documents_dropped=0,
                execution_time=execution_time,
                error_message=error_msg
            )
    
    async def _perform_discovery(
        self,
        trial_id: int,
        asset_aliases: List[str],
        indication_terms: List[str],
        trial_nct: Optional[str] = None,
        trial_phase: Optional[str] = None,
        trial_design: Optional[str] = None,
        catalyst_date: Optional[datetime] = None,
        max_results: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Perform document discovery (U0 functionality integrated into U1+).
        
        Args:
            trial_id: Trial ID
            asset_aliases: List of asset names/aliases
            indication_terms: List of disease/indication terms
            trial_nct: Optional NCT ID for exact matching
            trial_phase: Optional trial phase for filtering
            trial_design: Optional trial design for filtering
            catalyst_date: Optional catalyst date for recency bias
            max_results: Maximum results to process
            
        Returns:
            Dictionary with discovery results
        """
        try:
            logger.info(f"Starting discovery for trial {trial_id}")
            
            # 1. Build trial-specific query
            query_result = self.query_builder.build_trial_query(
                trial_id=str(trial_id),
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
            
            # 2. Execute PubMed search
            async with self.client:
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
                    return {
                        'success': True,
                        'documents': [],
                        'query_metadata': query_metadata,
                        'documents_discovered': 0,
                        'documents_mapped': 0,
                        'pmids_found': 0
                    }
                
                logger.info(f"Found {len(pmids)} PMIDs for trial {trial_id} (total: {total_count})")
                
                # 3. Pre-filter PMIDs if enabled
                if self.enable_prefiltering:
                    pmids = await self._prefilter_pmids_full(pmids, trial_id)
                    logger.info(f"After pre-filtering: {len(pmids)} PMIDs")
                
                # 4. Fetch metadata for PMIDs
                metadata_results = await self._fetch_metadata_batch(pmids)
                
                if not metadata_results:
                    logger.warning(f"No metadata retrieved for trial {trial_id}")
                    return {
                        'success': True,
                        'documents': [],
                        'query_metadata': query_metadata,
                        'documents_discovered': len(pmids),
                        'documents_mapped': 0,
                        'pmids_found': len(pmids)
                    }
                
                # 5. Map to our document format
                mapped_documents = self.mapper.map_esummary_result(metadata_results)
                
                # 6. Add trial-specific metadata
                enriched_documents = self._enrich_documents_for_trial(
                    mapped_documents, trial_id, query_metadata
                )
                
                # 7. Persist documents and candidates to database
                documents_stored = 0
                documents_failed = 0
                candidates_stored = 0
                candidates_failed = 0
                
                if self.enable_database_persistence:
                    # Store document metadata
                    successful, failed = self.db_service.upsert_documents_metadata(trial_id, enriched_documents)
                    documents_stored = successful
                    documents_failed = failed
                    
                    # Store trial-document candidates
                    candidates = self._prepare_trial_candidates(
                        enriched_documents, trial_id, 'U1_abstract'
                    )
                    if candidates:
                        successful, failed = self.db_service.store_trial_doc_candidates_discovery(
                            trial_id, candidates
                        )
                        candidates_stored = successful
                        candidates_failed = failed
                
                logger.info(f"Discovery completed for {trial_id}: "
                           f"{len(enriched_documents)} documents mapped, "
                           f"{documents_stored} stored, {documents_failed} failed")
                
                return {
                    'success': True,
                    'documents': enriched_documents,
                    'query_metadata': query_metadata,
                    'documents_discovered': len(pmids),
                    'documents_mapped': len(enriched_documents),
                    'pmids_found': len(pmids),
                    'documents_stored': documents_stored,
                    'documents_failed': documents_failed,
                    'candidates_stored': candidates_stored,
                    'candidates_failed': candidates_failed
                }
                
        except Exception as e:
            error_msg = f"Discovery failed for trial {trial_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'error_message': error_msg,
                'documents': [],
                'query_metadata': None,
                'documents_discovered': 0,
                'documents_mapped': 0,
                'pmids_found': 0
            }
    
    async def _prefilter_pmids_full(
        self, 
        pmids: List[str], 
        trial_id: int
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
        trial_id: int,
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
                doc['stage'] = 'U1_abstract'
                doc['stage_metadata'] = {
                    'stage': 'U1_discovery',
                    'stage_description': 'Discovery completed in U1+',
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
        trial_id: int,
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
                    'selected': False,  # Will be determined by selection phase
                    'dropped_reason': None,
                    'notes': f'Discovered in Stage U1+ at {datetime.now(timezone.utc).isoformat()}',
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                
                candidates.append(candidate)
                
            except Exception as e:
                logger.warning(f"Failed to prepare candidate: {e}")
                continue
        
        return candidates
    
    async def _fetch_abstracts_xml_batch(
        self, 
        documents: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        Fetch abstracts for documents using XML method for reliability.
        
        Args:
            documents: List of documents to fetch abstracts for
            
        Returns:
            Dictionary mapping PMID to abstract text
        """
        if not documents:
            return {}
        
        # Extract PMIDs
        pmids = [doc.get('pmid') for doc in documents if doc.get('pmid')]
        
        if not pmids:
            return {}
        
        all_abstracts = {}
        
        # Process in batches using client as context manager
        async with self.client:
            for i in range(0, len(pmids), self.batch_size):
                batch = pmids[i:i + self.batch_size]
                
                try:
                    # Use XML method for reliable abstract extraction
                    batch_abstracts = await self.client.efetch_abstracts_xml(batch)
                    all_abstracts.update(batch_abstracts)
                    
                    logger.debug(f"Fetched XML abstracts for batch {i//self.batch_size + 1}: "
                               f"{len(batch)} PMIDs")
                    
                    # Rate limiting between batches
                    if i + self.batch_size < len(pmids):
                        await asyncio.sleep(0.1)  # Small delay between batches
                        
                except Exception as e:
                    logger.warning(f"Failed to fetch XML abstracts for batch {i//self.batch_size + 1}: {e}")
                    continue
        
        return all_abstracts
    
    def _prepare_documents_for_scoring(
        self, 
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Prepare documents for R/S scoring by ensuring all required metadata is available.
        
        Args:
            documents: List of documents with links
            
        Returns:
            Documents prepared for scoring
        """
        prepared_docs = []
        
        for doc in documents:
            try:
                # Ensure ESummary metadata is available for scoring
                if 'pubmed_meta' in doc and 'esummary_jsonb' in doc['pubmed_meta']:
                    esummary_data = doc['pubmed_meta']['esummary_jsonb']
                    
                    # Add publication types and date for R/S scoring
                    doc['pub_types'] = esummary_data.get('pubtype', [])
                    doc['pub_date'] = esummary_data.get('pubdate')
                    doc['journal'] = esummary_data.get('fulljournalname')
                    
                    # Add human vs animal indicator (for S scoring)
                    doc['is_human_study'] = self._is_human_study(esummary_data)
                    
                    # Add phase information if available
                    doc['trial_phase'] = self._extract_trial_phase(esummary_data)
                
                prepared_docs.append(doc)
                
            except Exception as e:
                logger.warning(f"Failed to prepare document for scoring: {e}")
                prepared_docs.append(doc)
        
        return prepared_docs
    
    def _is_human_study(self, esummary_data: Dict[str, Any]) -> bool:
        """Determine if study involves human subjects."""
        try:
            # Check publication types
            pub_types = esummary_data.get('pubtype', [])
            human_indicators = [
                'Clinical Trial', 'Randomized Controlled Trial',
                'Controlled Clinical Trial', 'Clinical Study',
                'Case Report'
            ]
            
            for pub_type in pub_types:
                if any(indicator in pub_type for indicator in human_indicators):
                    return True
            
            # Check title for human indicators
            title = esummary_data.get('title', '').lower()
            human_keywords = ['patient', 'human', 'clinical', 'trial', 'study']
            
            if any(keyword in title for keyword in human_keywords):
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Failed to determine human study status: {e}")
            return False  # Conservative default
    
    def _extract_trial_phase(self, esummary_data: Dict[str, Any]) -> Optional[str]:
        """Extract trial phase from publication data."""
        try:
            # Check publication types for phase information
            pub_types = esummary_data.get('pubtype', [])
            
            for pub_type in pub_types:
                if 'Phase I' in pub_type:
                    return 'PHASE1'
                elif 'Phase II' in pub_type:
                    return 'PHASE2'
                elif 'Phase III' in pub_type:
                    return 'PHASE3'
                elif 'Phase IV' in pub_type:
                    return 'PHASE4'
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to extract trial phase: {e}")
            return None
    
    def _create_document_links(
        self, 
        documents: List[Dict[str, Any]], 
        trial_asset: str,
        trial_nct: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Create document links based on extracted entities.
        
        Args:
            documents: List of documents with extracted entities
            trial_asset: Asset name for linking
            trial_nct: NCT ID for linking
            
        Returns:
            Documents with added link information
        """
        documents_with_links = []
        
        for doc in documents:
            try:
                links = []
                
                # Check for NCT in text (case-insensitive and normalized)
                if trial_nct and 'extracted_entities' in doc:
                    nct_entities = [e for e in doc['extracted_entities'] 
                                  if e.ent_type == 'nct_id' and 
                                  e.value_norm.upper() == trial_nct.upper()]
                    if nct_entities:
                        links.append({
                            'link_type': 'nct_in_text',
                            'nct_id': trial_nct,
                            'confidence': max(e.confidence for e in nct_entities),
                            'source': 'entity_extraction'
                        })
                
                # Check for asset in text
                if 'extracted_entities' in doc:
                    asset_entities = [e for e in doc['extracted_entities'] 
                                   if e.ent_type == 'asset_name']
                    
                    # Simple asset matching (could be enhanced)
                    abstract_text = doc.get('abstract_text', '').lower()
                    asset_lower = trial_asset.lower()
                    
                    if asset_lower in abstract_text:
                        # Find the best matching asset entity
                        best_asset_entity = None
                        best_confidence = 0.0
                        
                        for entity in asset_entities:
                            if entity.confidence > best_confidence:
                                best_asset_entity = entity
                                best_confidence = entity.confidence
                        
                        links.append({
                            'link_type': 'asset_in_text',
                            'asset_name': trial_asset,
                            'confidence': best_confidence if best_asset_entity else 0.7,
                            'source': 'text_matching'
                        })
                
                # Add links to document
                doc['document_links'] = links
                documents_with_links.append(doc)
                
            except Exception as e:
                logger.warning(f"Failed to create links for document: {e}")
                doc['document_links'] = []
                documents_with_links.append(doc)
        
        return documents_with_links
    
    def _prepare_rs_score_record(
        self, 
        trial_id: int, 
        doc: Dict[str, Any], 
        score: Any
    ) -> Dict[str, Any]:
        """
        Prepare R/S score record for database insertion.
        
        Args:
            trial_id: Trial ID
            doc: Document data
            score: R/S score object
            
        Returns:
            R/S score record
        """
        try:
            return {
                'trial_id': trial_id,
                'doc_id': None,  # Will be looked up by PMID in database service
                'pmid': doc.get('pmid'),  # Include PMID for document lookup
                'R_score': score.R_score,
                'R_tier': score.R_tier,
                'S_score': score.S_score,
                'S_tier': score.S_tier,
                'R_components_jsonb': score.R_components,
                'S_components_jsonb': score.S_components,
                'decided_at': datetime.now(timezone.utc).isoformat(),
                'created_at': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.warning(f"Failed to prepare R/S score record: {e}")
            return {}
    
    def _apply_selection_rules(
        self, 
        documents: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Apply selection/drop rules based on R/S scores.
        
        Args:
            documents: List of scored documents
            
        Returns:
            Tuple of (selected_documents, dropped_documents)
        """
        selected = []
        dropped = []
        seen_so_far = 0
        
        for doc in documents:
            try:
                if 'rs_score' not in doc:
                    # No score available, include conservatively
                    selected.append(doc)
                    continue
                
                score = doc['rs_score']
                
                # Apply tightened selection rules
                if self._should_select_document(score, seen_so_far):
                    selected.append(doc)
                    doc['selection_status'] = 'selected'
                    doc['selection_reason'] = f'R{score.R_tier} S{score.S_tier} meets criteria'
                    seen_so_far += 1
                else:
                    dropped.append(doc)
                    doc['selection_status'] = 'dropped'
                    doc['selection_reason'] = f'R{score.R_tier} S{score.S_tier} below thresholds'
                
            except Exception as e:
                logger.warning(f"Failed to apply selection rules: {e}")
                # Include conservatively if we can't determine
                selected.append(doc)
        
        return selected, dropped
    
    def _should_select_document(self, score: Any, seen_so_far: int) -> bool:
        """
        Determine if document should be selected based on R/S scores.
        
        Args:
            score: R/S score object
            seen_so_far: Number of documents already selected
            
        Returns:
            True if document should be selected
        """
        try:
            r_score = score.R_score
            s_score = score.S_score
            
            # Updated selection criteria for basic science papers:
            # 1. R ≥ R1 (0.35) - select any medium, medium-high, or high relevance papers
            # 2. R ≥ R2 (0.55) - select medium-high and high relevance papers  
            # 3. R ≥ R3 (0.75) - select high relevance papers
            # 4. Still within max_abstracts_initial limit for initial processing
            
            # Select any medium or higher relevance papers (R1, R2, R3) regardless of shortability
            if r_score >= self.min_r_score:  # R1 threshold (0.35)
                return True
            
            # Only select high-quality papers - no fallback for low relevance papers
            return False
            
        except Exception as e:
            logger.warning(f"Failed to determine selection: {e}")
            return False  # Conservative: don't select if uncertain
    
    def _update_stage_information(
        self, 
        documents: List[Dict[str, Any]], 
        stage: str
    ) -> List[Dict[str, Any]]:
        """
        Update stage information for documents.
        
        Args:
            documents: List of documents
            stage: Current stage
            
        Returns:
            Updated documents
        """
        updated_docs = []
        
        for doc in documents:
            try:
                # Update stage information
                doc['stage'] = stage
                doc['stage_metadata'] = {
                    'stage': stage,
                    'stage_description': 'Abstract processing completed',
                    'stage_completed_at': datetime.now(timezone.utc).isoformat(),
                    'selection_status': doc.get('selection_status', 'unknown'),
                    'selection_reason': doc.get('selection_reason', 'unknown')
                }
                
                updated_docs.append(doc)
                
            except Exception as e:
                logger.warning(f"Failed to update stage information: {e}")
                updated_docs.append(doc)
        
        return updated_docs
    
    
    def _prepare_candidates_data(
        self,
        trial_id_int: int,
        final_documents: List[Dict[str, Any]],
        selected_docs: List[Dict[str, Any]],
        dropped_docs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Prepare data for storing trial-document candidates in the database.
        
        Args:
            trial_id_int: Trial ID as integer
            final_documents: All documents processed
            selected_docs: Documents that were selected
            dropped_docs: Documents that were dropped
            
        Returns:
            List of candidate records for database insertion
        """
        candidates_data = []
        
        # Create a set of selected document PMIDs for fast lookup
        selected_pmids = {doc.get('pmid') for doc in selected_docs if doc.get('pmid')}
        
        for doc in final_documents:
            pmid = doc.get('pmid')
            if not pmid:
                continue
                
            # Determine if the document was selected or dropped
            is_selected = pmid in selected_pmids
            
            # Get selection reason
            selection_reason = doc.get('selection_reason', 'unknown')
            
            # Prepare candidate record matching the database schema
            candidate_record = {
                'trial_id': trial_id_int,
                'doc_id': None,  # Will be looked up by PMID in database service
                'pmid': pmid,  # Include PMID for document lookup
                'stage': 'U1_abstract',
                'selected': is_selected,
                'dropped_reason': None if is_selected else selection_reason,
                'notes': f"R/S scoring completed: R{doc.get('rs_score').R_tier if doc.get('rs_score') else 'N/A'}S{doc.get('rs_score').S_tier if doc.get('rs_score') else 'N/A'}" if doc.get('rs_score') else None
            }
            candidates_data.append(candidate_record)
        
        return candidates_data
    
    def get_stage_u1_stats(self, result: StageU1Result) -> Dict[str, Any]:
        """
        Get statistics about Stage U1 execution.
        
        Args:
            result: Stage U1 result
            
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
            'documents_processed': result.documents_processed,
            'abstracts_fetched': result.abstracts_fetched,
            'entities_extracted': result.entities_extracted,
            'documents_scored': result.documents_scored,
            'documents_selected': result.documents_selected,
            'documents_dropped': result.documents_dropped,
            'selection_rate': (
                result.documents_selected / result.documents_scored 
                if result.documents_scored > 0 else 0
            ),
            'entity_extraction_rate': (
                result.entities_extracted / result.abstracts_fetched 
                if result.abstracts_fetched > 0 else 0
            ),
            'rs_scores_stored': result.rs_scores_stored,
            'rs_scores_failed': result.rs_scores_failed,
            'candidates_stored': result.candidates_stored,
            'candidates_failed': result.candidates_failed,
            'trial_state_updated': result.trial_state_updated
        }
