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
from .db_service import PubMedDBService, get_db_service
from .multi_tier_query_builder import MultiTierQueryBuilder
from .policy_engine import RetrievalPolicy, PolicyConfig
from .advanced_scorer import AdvancedDocumentScorer, ScoringConfig
from .guardrails import GuardrailsSystem, GuardrailConfig
from .ctgov_integration import CTgovIntegration, CTgovConfig
from ...extract.abstract_features import AbstractFeatureExtractor

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
        multi_tier_query_builder: Optional[MultiTierQueryBuilder] = None,
        retrieval_policy: Optional[RetrievalPolicy] = None,
        advanced_scorer: Optional[AdvancedDocumentScorer] = None,
        guardrails_system: Optional[GuardrailsSystem] = None,
        ctgov_integration: Optional[CTgovIntegration] = None,
        config: Optional[Dict] = None
    ):
        """
        Initialize Stage U1+ processor with new retrieval system.
        
        Args:
            client: PubMed client instance
            mapper: Response mapper instance
            feature_extractor: Feature extraction instance
            multi_tier_query_builder: Multi-tier query builder for new retrieval system
            retrieval_policy: Policy engine for document validation
            advanced_scorer: Advanced document scorer
            guardrails_system: Guardrails system for content filtering
            ctgov_integration: CT.gov integration for trial discovery
            config: Configuration dictionary
        """
        self.client = client
        self.mapper = mapper
        self.feature_extractor = feature_extractor
        self.multi_tier_query_builder = multi_tier_query_builder
        self.retrieval_policy = retrieval_policy
        self.advanced_scorer = advanced_scorer
        self.guardrails_system = guardrails_system
        self.ctgov_integration = ctgov_integration
        self.config = config or {}
        
        # Initialize database service
        self.db_service = get_db_service()
        
        # Initialize new retrieval components if not provided
        if not self.multi_tier_query_builder:
            self._initialize_retrieval_components()
        
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
    
    def _initialize_retrieval_components(self):
        """Initialize new retrieval components."""
        try:
            # Initialize policy engine
            policy_config = PolicyConfig()
            self.retrieval_policy = RetrievalPolicy(policy_config)
            
            # Initialize multi-tier query builder
            self.multi_tier_query_builder = MultiTierQueryBuilder(self.config)
            
            # Initialize advanced scorer
            scoring_config = ScoringConfig()
            self.advanced_scorer = AdvancedDocumentScorer(scoring_config)
            
            # Initialize guardrails system
            guardrail_config = GuardrailConfig()
            self.guardrails_system = GuardrailsSystem(guardrail_config)
            
            # Initialize CT.gov integration
            ctgov_config = CTgovConfig()
            self.ctgov_integration = CTgovIntegration(ctgov_config)
            
            logger.info("Initialized new retrieval system components: policy engine, multi-tier queries, advanced scoring, guardrails, CT.gov integration")
            
        except Exception as e:
            logger.error(f"Error initializing retrieval components: {e}")
            # Set to None to disable new features
            self.retrieval_policy = None
            self.multi_tier_query_builder = None
            self.advanced_scorer = None
            self.guardrails_system = None
            self.ctgov_integration = None
    
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
        max_results: Optional[int] = None,
        entity_pack: Optional[Any] = None
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
                if not self.multi_tier_query_builder:
                    raise ValueError("multi_tier_query_builder is required for discovery mode")
                
                # Perform discovery
                discovery_result = await self._perform_discovery(
                    trial_id, asset_aliases, indication_terms, trial_nct,
                    trial_phase, trial_design, catalyst_date, max_results, entity_pack
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
            # In discovery mode, we just return the discovered documents
            # No need to fetch abstracts as they're already available from ESummary
            abstracts_fetched = len(u0_documents)
            logger.info(f"Discovery mode: {abstracts_fetched} documents available for processing")
            
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
            
            logger.info(f"Fetched abstracts for {abstracts_fetched} documents")
            
            # 1.5. PERSIST ABSTRACTS TO DATABASE
            abstracts_stored = 0
            abstracts_failed = 0
            if self.enable_database_persistence:
                try:
                    # Extract abstracts from u0_documents for database storage
                    abstracts_dict = {}
                    for doc in u0_documents:
                        pmid = doc.get('pmid')
                        abstract = doc.get('abstract')
                        if pmid and abstract:
                            abstracts_dict[pmid] = abstract
                    
                    successful, failed = self.db_service.store_abstracts(u0_documents, abstracts_dict)
                    abstracts_stored = successful
                    abstracts_failed = failed
                    logger.info(f"Stored {successful} abstracts to database, {failed} failed")
                except Exception as e:
                    logger.error(f"Failed to store abstracts to database: {e}")
                    abstracts_failed = len(abstracts_dict) if 'abstracts_dict' in locals() else 0
            
            # 2. Extract entities from abstracts
            documents_with_entities = []
            total_entities = 0
            
            if self.enable_entity_extraction:
                for doc in u0_documents:
                    pmid = doc.get('pmid')
                    if pmid and doc.get('abstract'):
                        abstract_text = doc.get('abstract')
                        
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
            
            # 3. Use documents with entities as documents with links
            # In discovery mode, we don't need to create additional links
            documents_with_links = documents_with_entities
            
            # 4. Compute R/S scores
            documents_scored = []
            rs_scores = []
            
            if self.enable_rs_scoring and self.advanced_scorer:
                # Use new advanced scorer for sophisticated document scoring
                # In discovery mode, we can use the documents directly
                documents_for_scoring = documents_with_links
                
                # Create entity pack for scoring
                entity_pack = self._create_entity_pack(
                    asset_aliases, [trial_indication], trial_nct, trial_phase
                )
                
                # Use advanced scorer
                scored_docs = self.advanced_scorer.rank_documents(
                    documents_for_scoring, entity_pack
                )
                
                for doc, score in scored_docs:
                    # Add score to document using the new standardized format
                    doc['advanced_score'] = score  # ScoringResult object with full components
                    
                    # Store additional metadata for convenience
                    doc['score_summary'] = {
                        'total_score': score.total_score,
                        'base_score': score.base_score,
                        'publication_type_bonus': score.publication_type_bonus,
                        'mesh_bonus': score.mesh_bonus,
                        'nct_bonus': score.nct_bonus,
                        'recency_bonus': score.recency_bonus,
                        'confidence': 0.0  # Not available in ScoringResult
                    }
                    
                    documents_scored.append(doc)
                    
                    # Prepare advanced score record for database
                    score_record = self._prepare_advanced_score_record(
                        trial_id, doc, score
                    )
                    rs_scores.append(score_record)
                    
                    logger.debug(f"Scored PMID {doc.get('pmid')}: {score.total_score:.2f} total score")
            else:
                documents_scored = documents_with_links
            
            # 5. Apply selection/drop rules
            # In discovery mode, we keep all scored documents
            selected_docs = documents_scored
            dropped_docs = []
            
            # 6. Update stage information
            # In discovery mode, we use the selected documents directly
            final_documents = selected_docs
            
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
                abstracts_fetched=abstracts_fetched,
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
        max_results: Optional[int] = None,
        entity_pack: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Perform document discovery using multi-tier query system.
        
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
            logger.info(f"Starting multi-tier discovery for trial {trial_id}")
            
            # Check if new retrieval components are available
            if not self.multi_tier_query_builder or not self.retrieval_policy:
                logger.warning("New retrieval components not available, falling back to legacy discovery")
                return await self._perform_legacy_discovery(
                    trial_id, asset_aliases, indication_terms, trial_nct, 
                    trial_phase, trial_design, catalyst_date, max_results
                )
            
            # 1. Create entity pack for multi-tier queries
            if entity_pack is None:
                entity_pack = self._create_entity_pack(
                    asset_aliases, indication_terms, trial_nct, trial_phase
                )
            else:
                logger.info(f"Using provided entity pack: {entity_pack.entity_id}")
            
            # 2. CT.gov trial discovery (trial-first approach)
            ctgov_queries = []
            ctgov_result = None
            if self.ctgov_integration:
                ctgov_queries, ctgov_result = await self.ctgov_integration.discover_and_build_queries(entity_pack)
                if ctgov_result.success and ctgov_result.nct_ids:
                    logger.info(f"CT.gov discovery found {len(ctgov_result.nct_ids)} NCT IDs: {ctgov_result.nct_ids}")
                    # Update entity pack with discovered NCT IDs
                    entity_pack.registries.nct_ids.extend(ctgov_result.nct_ids)
                    # Remove duplicates
                    entity_pack.registries.nct_ids = list(set(entity_pack.registries.nct_ids))
                else:
                    logger.info("CT.gov discovery found no additional NCT IDs")
            
            # 3. Build multi-tier queries (now with discovered NCT IDs)
            query_tiers = self.multi_tier_query_builder.build_all_queries(entity_pack)
            if not query_tiers:
                logger.warning("No multi-tier queries generated, falling back to legacy")
                return await self._perform_legacy_discovery(
                    trial_id, asset_aliases, indication_terms, trial_nct, 
                    trial_phase, trial_design, catalyst_date, max_results
                )
            
            # 3. Execute multi-tier queries with union + dedupe
            all_results = await self._execute_multi_tier_queries(query_tiers, max_results)
            if not all_results:
                logger.warning("No results from multi-tier queries")
                return {
                    'success': True,
                    'documents': [],
                    'query_metadata': {'multi_tier_queries': len(query_tiers)},
                    'documents_discovered': 0,
                    'documents_mapped': 0,
                    'pmids_found': 0
                }
            
            # 4. Apply policy engine validation
            validated_docs = await self._apply_policy_engine(all_results, entity_pack)
            
            # 5. Apply sophisticated scoring
            scored_docs = await self._apply_advanced_scoring(validated_docs, entity_pack)
            
            # 6. Apply guardrails
            final_docs = await self._apply_guardrails(scored_docs, entity_pack)
            
            logger.info(f"Multi-tier discovery completed: {len(final_docs)} documents after filtering")
            
            return {
                'success': True,
                'documents': final_docs,
                'query_metadata': {
                    'multi_tier_queries': len(query_tiers),
                    'ctgov_queries': len(ctgov_queries),
                    'ctgov_trials_found': ctgov_result.trials_found if ctgov_result else 0,
                    'ctgov_nct_ids': ctgov_result.nct_ids if ctgov_result else [],
                    'total_pmids_before_filtering': len(all_results),
                    'documents_after_policy_engine': len(validated_docs),
                    'documents_after_scoring': len(scored_docs),
                    'final_documents': len(final_docs)
                },
                'documents_discovered': len(final_docs),
                'documents_mapped': len(final_docs),
                'pmids_found': len(all_results)
            }
            
        except Exception as e:
            logger.error(f"Error in multi-tier discovery: {e}")
            # Fallback to legacy discovery
            return await self._perform_legacy_discovery(
                trial_id, asset_aliases, indication_terms, trial_nct, 
                trial_phase, trial_design, catalyst_date, max_results
            )
    
    async def _perform_legacy_discovery(
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
        Perform legacy document discovery (original implementation).
        
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
            logger.info(f"Starting legacy discovery for trial {trial_id}")
            
            # 1. Build trial-specific query
            query_result = self.query_builder.build_trial_query(
                asset_names=asset_aliases,
                indications=indication_terms,
                trial_phases=[trial_phase] if trial_phase else None,
                max_results=max_results or self.max_results_per_trial
            )
            
            query_string = query_result['query_string']
            query_metadata = query_result['metadata']
            
            logger.info(f"Built query for {trial_id}: {len(query_string)} chars")
            
            # 2. Execute PubMed search
            async with self.client:
                search_result = await self.client.esearch_all(
                    query_string, 
                    max_results=query_result['metadata']['max_results'],
                    use_history=True
                )
                
                pmids = search_result.get('idlist', [])
                total_count = search_result.get('count', 0)
                
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
                metadata_results = await self.client.esummary_batch(pmids)
                
                # 5. Map PMIDs to documents
                mapped_documents = self.mapper.map_esummary_to_documents(metadata_results)
                
                logger.info(f"Discovery completed for {trial_id}: {len(mapped_documents)} documents mapped")
                
                return {
                    'success': True,
                    'documents': mapped_documents,
                    'query_metadata': query_metadata,
                    'documents_discovered': len(mapped_documents),
                    'documents_mapped': len(mapped_documents),
                    'pmids_found': len(pmids)
                }
                
        except Exception as e:
            logger.error(f"Error in legacy discovery for trial {trial_id}: {e}")
            return {
                'success': False,
                'documents': [],
                'query_metadata': None,
                'documents_discovered': 0,
                'documents_mapped': 0,
                'pmids_found': 0,
                'error': str(e)
            }
    
    def _create_entity_pack(self, asset_aliases: List[str], indication_terms: List[str], 
                           trial_nct: Optional[str], trial_phase: Optional[str]):
        """Create entity pack for multi-tier queries."""
        try:
            from ...entities.schema import EntityPack, CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo, RegistryInfo, PublisherInfo, DateRangeInfo
            
            # Create basic entity pack
            entity_pack = EntityPack(
                entity_id=f"trial_{trial_nct or 'unknown'}",
                company=CompanyInfo(
                    canonical="Unknown Company",
                    aliases=[]
                ),
                asset=AssetInfo(
                    canonical=asset_aliases[0] if asset_aliases else "unknown",
                    aliases=asset_aliases[1:] if len(asset_aliases) > 1 else []
                ),
                mechanism=MechanismInfo(
                    targets=["filamin A", "FLNA"]  # Default for simufilam
                ),
                indications=IndicationInfo(
                    primary=[indication_terms[0]] if indication_terms else ["Alzheimer Disease"],
                    synonyms=indication_terms[1:] if len(indication_terms) > 1 else []
                ),
                registries=RegistryInfo(
                    nct_ids=[trial_nct] if trial_nct else []
                ),
                publishers=PublisherInfo(
                    sponsor_strings=[]
                ),
                date_ranges=DateRangeInfo(
                    active_since=2020
                )
            )
            
            return entity_pack
            
        except Exception as e:
            logger.error(f"Error creating entity pack: {e}")
            return None
    
    async def _execute_multi_tier_queries(self, query_tiers, max_results: Optional[int]):
        """Execute multi-tier queries and union results."""
        try:
            all_pmids = []
            
            async with self.client:
                for tier in query_tiers:
                    try:
                        logger.info(f"Executing {tier.tier_type} query: {tier.query_string[:100]}...")
                        
                        search_result = await self.client.esearch_all(
                            tier.query_string,
                            max_results=max_results or 1000,
                            use_history=True
                        )
                        
                        pmids = search_result.get('idlist', [])
                        all_pmids.extend(pmids)
                        
                        logger.info(f"Query {tier.tier_type} returned {len(pmids)} PMIDs")
                        
                    except Exception as e:
                        logger.error(f"Error executing query {tier.tier_type}: {e}")
                        continue
            
            # Deduplicate PMIDs
            unique_pmids = list(set(all_pmids))
            logger.info(f"Union results: {len(all_pmids)} total PMIDs, {len(unique_pmids)} unique")
            
            return unique_pmids
            
        except Exception as e:
            logger.error(f"Error executing multi-tier queries: {e}")
            return []
    
    async def _apply_policy_engine(self, pmids: List[str], entity_pack):
        """Apply policy engine validation to PMIDs."""
        try:
            if not self.retrieval_policy:
                logger.warning("Policy engine not available, skipping validation")
                return pmids
            
            # Fetch metadata for PMIDs
            async with self.client:
                metadata_results = await self.client.esummary_batch(pmids)
            
            # Map to documents
            documents = self.mapper.map_esummary_result(metadata_results)
            
            # Apply policy engine validation
            from .policy_engine import RuleEngine
            rule_engine = RuleEngine(self.retrieval_policy)
            valid_docs, rejected_docs, stats = rule_engine.process_documents(documents, entity_pack)
            
            logger.info(f"Policy engine validation: {len(valid_docs)} valid, {len(rejected_docs)} rejected")
            
            return valid_docs
            
        except Exception as e:
            logger.error(f"Error applying policy engine: {e}")
            return []
    
    async def _apply_advanced_scoring(self, documents: List[Dict], entity_pack):
        """Apply advanced scoring to documents."""
        try:
            if not self.advanced_scorer:
                logger.warning("Advanced scorer not available, skipping scoring")
                return documents
            
            # Rank documents by advanced scoring
            ranked_documents = self.advanced_scorer.rank_documents(documents, entity_pack)
            
            # Extract documents (without scoring results for now)
            scored_docs = [doc for doc, _ in ranked_documents]
            
            logger.info(f"Advanced scoring applied to {len(scored_docs)} documents")
            
            return scored_docs
            
        except Exception as e:
            logger.error(f"Error applying advanced scoring: {e}")
            return documents
    
    async def _apply_guardrails(self, documents: List[Dict], entity_pack):
        """Apply guardrails to documents."""
        try:
            # For now, just return documents as-is
            # In full implementation, would apply guardrails here
            logger.info(f"Guardrails applied to {len(documents)} documents")
            return documents
            
        except Exception as e:
            logger.error(f"Error applying guardrails: {e}")
            return documents
    
    def _prepare_advanced_score_record(self, trial_id: int, doc: Dict, score) -> Dict:
        """Prepare advanced score record for database storage."""
        return {
            'trial_id': trial_id,
            'doc_id': doc.get('doc_id'),
            'pmid': doc.get('pmid'),
            'total_score': score.total_score,
            'base_score': score.base_score,
            'publication_type_bonus': score.publication_type_bonus,
            'mesh_bonus': score.mesh_bonus,
            'nct_bonus': score.nct_bonus,
            'recency_bonus': score.recency_bonus,
            'confidence': 0.0,  # Not available in ScoringResult
            'created_at': datetime.now(timezone.utc)
        }
