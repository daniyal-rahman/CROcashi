"""
Retrieval Processor - Simplified Persistence Strategy.

Processes Steps 1-6 of retrieval pipeline with simplified persistence:
1. Entity pack creation (canonical entities & aliases)
2. Retrieval policy application (must/should/cannot)
3. Multi-tier PubMed queries (A, B, C, D)
4. CT.gov trial discovery
5. Re-ranking & filtering with sophisticated scoring
6. Guardrails application

Stores ALL documents found during retrieval for human verification.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .entity_pack_builder import EntityPackBuilder, EntityPack
from .query_builder import MultiTierQueryBuilder, QueryTier
from .policy_engine import RetrievalPolicy
from .document_scorer import AdvancedDocumentScorer, ScoringOutput
# Guardrails moved to pre-LLM stage
from .ctgov_discovery import CTgovIntegration
from ..client import PubMedClient
from ..db_service import PubMedDBService

logger = logging.getLogger(__name__)


@dataclass
class RetrievalOutput:
    """Result from retrieval processing."""
    success: bool
    documents: List[Dict[str, Any]]
    query_metadata: Dict[str, Any]
    documents_discovered: int
    documents_mapped: int
    pmids_found: int
    session_id: Optional[str] = None
    error_message: Optional[str] = None


class RetrievalProcessor:
    """Processes the complete retrieval pipeline (Steps 1-6) with simplified persistence."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, session_factory=None):
        """Initialize retrieval processor."""
        self.config = config or {}
        self.session_factory = session_factory
        
        # Initialize components
        self.entity_pack_builder = EntityPackBuilder(config)
        self.query_builder = MultiTierQueryBuilder(config)
        self.policy_engine = RetrievalPolicy(config.get('policy_config', {}))
        self.document_scorer = AdvancedDocumentScorer(config.get('scoring_config', {}))
        # Guardrails removed from retrieval stage - moved to pre-LLM stage
        self.guardrails = None
        self.ctgov_integration = CTgovIntegration(config.get('ctgov_config', {}))
        # Initialize PubMed client with individual parameters
        client_config = config.get('client_config', {})
        self.client = PubMedClient(
            api_key=client_config.get('api_key'),
            rate_limit_per_sec=client_config.get('rate_limit_requests_per_minute', 60) // 60,  # Convert per minute to per second
            batch_size=client_config.get('batch_size', 20),
            max_retries=client_config.get('max_retries', 3),
            timeout_seconds=client_config.get('timeout_seconds', 30),
            backoff_base=client_config.get('backoff_base', 2.0),
            circuit_breaker_threshold=client_config.get('circuit_breaker_threshold', 5),
            email=client_config.get('email', 'ncfd@example.com'),
            tool=client_config.get('tool', 'NCFD')
        )
        
        # Initialize database service
        self.db_service = PubMedDBService()
        
        logger.info("Retrieval processor initialized")
    
    async def execute_retrieval(
        self,
        trial_id: int,
        asset_aliases: List[str],
        indication_terms: List[str],
        trial_nct: Optional[str] = None,
        trial_phase: Optional[str] = None,
        company_name: Optional[str] = None,
        company_aliases: Optional[List[str]] = None,
        max_results: Optional[int] = None,
        entity_pack: Optional[Any] = None
    ) -> RetrievalOutput:
        """
        Execute complete retrieval pipeline (Steps 1-6) with dual persistence.
        
        Args:
            trial_id: Trial ID for persistence
            asset_aliases: List of asset names/aliases
            indication_terms: List of disease/indication terms
            trial_nct: Optional NCT ID for exact matching
            trial_phase: Optional trial phase for filtering
            company_name: Optional company name
            company_aliases: Optional company aliases
            max_results: Maximum results to process
            
        Returns:
            RetrievalOutput with discovered documents
        """
        start_time = datetime.now(timezone.utc)
        session_id = str(uuid.uuid4())
        
        try:
            logger.debug(f"Starting retrieval processing with session_id: {session_id}")
            logger.debug(f"RetrievalProcessor inputs - asset_aliases: {asset_aliases}, indication_terms: {indication_terms}")
            
            # Store session metadata for tracking
            retrieval_session_id = session_id
            
            # Step 1: Use provided entity pack or create one
            if entity_pack is None:
                # Create entity pack using the existing builder (fallback)
                entity_pack = self.entity_pack_builder.create_entity_pack(
                    asset_aliases=asset_aliases,
                    indication_terms=indication_terms,
                    trial_nct=trial_nct,
                    trial_phase=trial_phase,
                    company_name=company_name,
                    company_aliases=company_aliases
                )
                logger.info(f"Created entity pack using EntityPackBuilder for trial {trial_id}")
            else:
                logger.info(f"Using provided entity pack for trial {trial_id}")
            
            # Log entity pack snapshot for debugging
            logger.info(f"Entity pack snapshot (session_id={session_id}):")
            logger.info(f"  Asset terms: {entity_pack.get_all_asset_terms()}")
            logger.info(f"  Indication terms: {entity_pack.get_all_indication_terms()}")
            logger.info(f"  Company terms: {entity_pack.get_all_company_terms()}")
            logger.info(f"  NCT IDs: {entity_pack.registries.nct_ids}")
            logger.info(f"  Mechanism targets: {entity_pack.mechanism.targets}")
            logger.info(f"  Asset canonical: {entity_pack.asset.canonical if entity_pack.asset is not None else 'None'}")
            
            if not entity_pack:
                return RetrievalOutput(
                    success=False,
                    documents=[],
                    query_metadata={},
                    documents_discovered=0,
                    documents_mapped=0,
                    pmids_found=0,
                    session_id=session_id,
                    error_message="Failed to create entity pack"
                )
            
            # Step 2: CT.gov trial discovery (trial-first approach)
            ctgov_queries = []
            ctgov_result = None
            if self.ctgov_integration:
                ctgov_queries, ctgov_result = await self.ctgov_integration.discover_and_build_queries(entity_pack)
                if ctgov_result.success and ctgov_result.nct_ids:
                    logger.info(f"CT.gov discovery found {len(ctgov_result.nct_ids)} NCT IDs: {ctgov_result.nct_ids}")
                    # Update entity pack with discovered NCT IDs
                    entity_pack = self.entity_pack_builder.update_entity_pack_with_nct_ids(
                        entity_pack, ctgov_result.nct_ids
                    )
                else:
                    logger.info("CT.gov discovery found no additional NCT IDs")
            
            # Step 3: Build multi-tier queries (A, B, C, D)
            query_tiers = self.query_builder.build_all_queries(entity_pack)
            if not query_tiers:
                return RetrievalOutput(
                    success=False,
                    documents=[],
                    query_metadata={},
                    documents_discovered=0,
                    documents_mapped=0,
                    pmids_found=0,
                    session_id=session_id,
                    error_message="No multi-tier queries generated"
                )
            
            # Step 3: Execute multi-tier queries with union + dedupe
            all_pmids, tier_results = await self._execute_multi_tier_queries(query_tiers, max_results)
            if not all_pmids:
                return RetrievalOutput(
                    success=True,
                    documents=[],
                    query_metadata={'multi_tier_queries': len(query_tiers)},
                    documents_discovered=0,
                    documents_mapped=0,
                    pmids_found=0,
                    session_id=session_id
                )
            
            # Step 4: Apply policy engine validation (must/should/cannot)
            validated_documents = await self._apply_policy_engine(all_pmids, entity_pack)
            
            # Step 6: Guardrails removed - moved to pre-LLM stage
            final_documents = validated_documents
            
            # Store RAW documents found during retrieval (before filtering)
            if all_pmids:
                # Fetch metadata and PMCID information in one call
                async with self.client:
                    metadata_result = await self.client.esummary_batch(all_pmids)
                    # Enhanced XML fetch that includes PMCID detection
                    xml_result = await self.client.efetch_abstracts_xml(all_pmids)
                
                # Store documents directly using db_service
                raw_documents = []
                for pmid in all_pmids:
                    # Determine which query tier found this document
                    query_tier = 'Unknown'
                    for tier_type, tier_pmids in tier_results.items():
                        if pmid in tier_pmids:
                            query_tier = tier_type
                            break
                    
                    # Extract title from metadata
                    title = 'No title available'
                    if pmid in metadata_result:
                        metadata = metadata_result[pmid]
                        title = metadata.get('Title', metadata.get('title', 'No title available'))
                        if title and len(title) > 200:
                            title = title[:200] + '...'
                    
                    # Extract PMCID and full text status from XML result
                    pmcid = None
                    has_free_full_text = False
                    
                    if pmid in xml_result:
                        xml_info = xml_result[pmid]
                        pmcid = xml_info.get('pmcid')
                        has_free_full_text = xml_info.get('has_free_full_text', False)
                        
                        # Log PMCID detection results
                        if pmcid:
                            logger.info(f"PMCID detected for PMID {pmid}: {pmcid}")
                    
                    raw_documents.append({
                        'pmid': pmid,
                        'title': title,
                        'pmcid': pmcid,
                        'has_free_full_text': has_free_full_text,
                        'retrieval_tier': query_tier,
                        'query_tier': query_tier,
                        'policy_engine_passed': False,
                        'guardrails_passed': True,  # Guardrails moved to pre-LLM stage
                        'created_at': datetime.now(timezone.utc)
                    })
                
                # Apply scoring to documents with titles
                scored_tuples = await self._apply_document_scoring(raw_documents, entity_pack)
                
                # Extract documents and scores for storage and preview
                scored_documents = [doc for doc, _ in scored_tuples]
                scoring_results = {doc['pmid']: score for doc, score in scored_tuples}
                
                # Store documents using simplified approach
                stored_count, failed_count = self.db_service.store_documents_metadata(scored_documents)
                logger.info(f"store_documents_metadata: stored={stored_count}, failed={failed_count}, session={retrieval_session_id}")
                
                # Initialize linked_count for logging
                linked_count = 0
                
                # Link documents to trial
                if stored_count > 0:
                    # Create trial-document candidates for discovery stage
                    doc_candidates = []
                    for doc_data in scored_documents:
                        doc_candidates.append({
                            'pmid': doc_data['pmid'],
                            'stage': 'U1_discovery',
                            'retrieval_tier': doc_data['retrieval_tier'],
                            'query_tier': doc_data['query_tier']
                        })
                    
                    linked_count, link_failed = self.db_service.store_trial_doc_candidates_discovery(
                        trial_id=trial_id,
                        candidates=doc_candidates
                    )
                    logger.info(f"store_trial_doc_candidates_discovery: linked={linked_count}, failed={link_failed}")
                
                # Log top-N preview for sanity check
                logger.info("Top-N preview (first 5 ranked hits):")
                for i, (doc, score_result) in enumerate(scored_tuples[:5]):
                    # Better title extraction with fallbacks
                    title_preview = (doc.get('title') or 
                                   doc.get('metadata', {}).get('title') or 
                                   doc.get('summary', {}).get('title') or 
                                   'No title')[:120]
                    
                    # Better tier extraction with fallbacks
                    tier_hit = (doc.get('retrieval_tier') or 
                              doc.get('tier_type') or 
                              doc.get('query_tier') or 
                              'Unknown')
                    
                    # Use the actual scoring result
                    score = score_result.total_score
                    
                    pmid = doc.get('pmid', doc.get('id', 'Unknown'))
                    logger.info(f"  {i+1}) {pmid} \"{title_preview}...\" [hit:{tier_hit}, score:{score:.2f}]")
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            # Log final counts from database with debug info
            final_counts = self.db_service.get_document_counts_by_stage(trial_id)
            logger.info(f"DEBUG: get_document_counts_by_stage returned: {final_counts}")
            logger.info(f"final_counts: retrieval_docs_in_db={final_counts.get('total', 0)}, processed_docs_in_db={final_counts.get('processed', 0)}")
            
            # Also log actual stored counts for comparison
            logger.info(f"DEBUG: Documents stored this session: {stored_count}, candidates linked: {linked_count}")
            
            # Log rate limiting & retries summary
            rate_limit_info = self.client.get_rate_limit_info()
            logger.info(f"Rate limiting & retries summary:")
            logger.info(f"  esearch_calls={rate_limit_info['esearch_calls']}, efetch_calls={rate_limit_info['efetch_calls']}, retries={rate_limit_info['consecutive_failures']}, total_api_time={execution_time:.1f}s")
            
            logger.info(f"Retrieval processing completed in {execution_time:.2f}s: {len(scored_documents)} documents (stored for human verification)")
            
            return RetrievalOutput(
                success=True,
                documents=scored_documents,
                query_metadata={
                    'multi_tier_queries': len(query_tiers),
                    'ctgov_queries': len(ctgov_queries),
                    'ctgov_trials_found': ctgov_result.trials_found if ctgov_result else 0,
                    'ctgov_nct_ids': ctgov_result.nct_ids if ctgov_result else [],
                    'total_pmids_before_filtering': len(all_pmids),
                    'documents_after_policy_engine': len(validated_documents),
                    'documents_after_scoring': len(scored_documents),
                    'final_documents': len(final_documents),
                    'execution_time': execution_time
                },
                documents_discovered=len(scored_documents),
                documents_mapped=len(scored_documents),
                pmids_found=len(all_pmids),
                session_id=session_id
            )
            
        except Exception as e:
            logger.error(f"Error in retrieval processing: {e}")
            
            # Log failure - no session tracking needed in simplified approach
            logger.error(f"Retrieval processing failed for session {retrieval_session_id}")
            
            return RetrievalOutput(
                success=False,
                documents=[],
                query_metadata={},
                documents_discovered=0,
                documents_mapped=0,
                pmids_found=0,
                session_id=session_id,
                error_message=str(e)
            )
    
    async def _execute_multi_tier_queries(self, query_tiers: List[QueryTier], max_results: Optional[int]) -> Tuple[List[str], Dict[str, List[str]]]:
        """Execute multi-tier queries and union results."""
        try:
            all_pmids = []
            tier_results = {}
            
            async with self.client:
                for tier in query_tiers:
                    try:
                        # Log full query text and parameters
                        logger.info(f"Tier {tier.tier_type} query (full text):")
                        logger.info(f"  term=\"{tier.query_string}\"")
                        logger.info(f"  params={{retmax:{max_results or 1000}, datetype:\"pdat\", usehistory:true}}")
                        
                        search_result = await self.client.esearch_all(
                            tier.query_string,
                            max_results=max_results or 1000,
                            use_history=True
                        )
                        
                        pmids = search_result.get('idlist', [])
                        all_pmids.extend(pmids)
                        tier_results[tier.tier_type] = pmids
                        
                        # Calculate new vs union counts
                        previous_union = set()
                        for prev_tier, prev_pmids in tier_results.items():
                            if prev_tier != tier.tier_type:
                                previous_union.update(prev_pmids)
                        
                        new_pmids = set(pmids) - previous_union
                        union_unique = len(set(all_pmids))
                        
                        logger.info(f"  results={{returned:{len(pmids)}, new_vs_union:{len(new_pmids)}, union_unique:{union_unique}}}")
                        
                    except Exception as e:
                        logger.error(f"Error executing query {tier.tier_type}: {e}")
                        continue
            
            # Deduplicate PMIDs
            unique_pmids = list(set(all_pmids))
            logger.info(f"Union results: {len(all_pmids)} total PMIDs, {len(unique_pmids)} unique")
            
            return unique_pmids, tier_results
            
        except Exception as e:
            logger.error(f"Error executing multi-tier queries: {e}")
            return [], {}
    
    async def _apply_policy_engine(self, pmids: List[str], entity_pack: EntityPack) -> List[Dict[str, Any]]:
        """Apply policy engine validation to PMIDs and return documents."""
        try:
            # Log policy/guardrail status
            logger.info("Policy/guardrail status:")
            logger.info(f"  policy_engine = {'enabled' if self.policy_engine else 'disabled'}")
            logger.info(f"  guardrails = disabled (moved to pre-LLM stage)")
            logger.info(f"  filters = {{require_indication_signal: false, require_field_coverage: false}}")
            
            # Apply policy engine validation
            if not self.policy_engine:
                logger.warning("Policy engine not available, skipping validation")
                return [{'pmid': pmid, 'policy_engine_passed': True} for pmid in pmids]
            
            # Apply policy engine validation to each PMID
            validated_docs = []
            for pmid in pmids:
                try:
                    validation_result = self.policy_engine.validate_document({'pmid': pmid}, entity_pack)
                    # Check if validation passed using the correct attribute
                    if hasattr(validation_result, 'passes_validation') and validation_result.passes_validation:
                        validated_docs.append({'pmid': pmid, 'policy_engine_passed': True})
                    else:
                        # Document failed validation - mark as failed
                        logger.debug(f"Document {pmid} failed policy validation: {getattr(validation_result, 'validation_errors', 'Unknown error')}")
                        validated_docs.append({'pmid': pmid, 'policy_engine_passed': False})
                except Exception as e:
                    # If validation fails due to error, mark as failed
                    logger.error(f"Error validating document {pmid}: {e}")
                    validated_docs.append({'pmid': pmid, 'policy_engine_passed': False})
            
            logger.info(f"Policy engine applied to {len(pmids)} documents: {len(validated_docs)} passed")
            return validated_docs
                
        except Exception as e:
            logger.error(f"Error applying policy engine: {e}")
            return [{'pmid': pmid, 'policy_engine_passed': False} for pmid in pmids]
    
    async def _apply_document_scoring(self, documents: List[Dict[str, Any]], entity_pack: EntityPack) -> List[Dict[str, Any]]:
        """Apply document scoring and re-ranking."""
        try:
            if not self.document_scorer:
                logger.warning("Document scorer not available, skipping scoring")
                return documents
            
            logger.info(f"DEBUG: Starting scoring for {len(documents)} documents")
            
            # Apply advanced scoring
            scored_tuples = self.document_scorer.rank_documents(documents, entity_pack)
            
            # Debug logging for first few documents
            for i, (doc, score) in enumerate(scored_tuples[:3]):
                logger.info(f"DEBUG: Doc {i+1} final score: {score}, pmid: {doc.get('pmid', 'Unknown')}")
            
            logger.info(f"Advanced scoring applied to {len(scored_tuples)} documents")
            return scored_tuples
            
        except Exception as e:
            logger.error(f"Error applying document scoring: {e}")
            # Return tuples with zero scores for error case
            return [(doc, ScoringOutput(total_score=0.0, base_score=0.0, policy_score=0.0, publication_type_bonus=0.0, mesh_bonus=0.0, nct_bonus=0.0, recency_bonus=0.0)) for doc in documents]
    
    # Guardrails method removed - moved to pre-LLM stage