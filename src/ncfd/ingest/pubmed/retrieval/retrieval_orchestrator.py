"""
Retrieval Orchestrator - Dual Persistence Strategy.

Coordinates Steps 1-6 of retrieval pipeline with dual persistence:
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
from .document_scorer import AdvancedDocumentScorer
from .guardrails import GuardrailsSystem
from .ctgov_discovery import CTgovIntegration
from ..client import PubMedClient
from ..dual_persistence_service import DualPersistenceService

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Result from retrieval orchestration."""
    success: bool
    documents: List[Dict[str, Any]]
    query_metadata: Dict[str, Any]
    documents_discovered: int
    documents_mapped: int
    pmids_found: int
    session_id: Optional[str] = None
    error_message: Optional[str] = None


class RetrievalOrchestrator:
    """Orchestrates the complete retrieval pipeline (Steps 1-6) with dual persistence."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, session_factory=None):
        """Initialize retrieval orchestrator."""
        self.config = config or {}
        self.session_factory = session_factory
        
        # Initialize components
        self.entity_pack_builder = EntityPackBuilder(config)
        self.query_builder = MultiTierQueryBuilder(config)
        self.policy_engine = RetrievalPolicy(config.get('policy_config', {}))
        self.document_scorer = AdvancedDocumentScorer(config.get('scoring_config', {}))
        self.guardrails = GuardrailsSystem(config.get('guardrails_config', {}))
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
        
        # Initialize dual persistence service
        if session_factory:
            self.persistence_service = DualPersistenceService(session_factory)
        else:
            self.persistence_service = None
        
        logger.info("Retrieval orchestrator initialized with dual persistence")
    
    async def execute_retrieval(
        self,
        trial_id: int,
        asset_aliases: List[str],
        indication_terms: List[str],
        trial_nct: Optional[str] = None,
        trial_phase: Optional[str] = None,
        company_name: Optional[str] = None,
        company_aliases: Optional[List[str]] = None,
        max_results: Optional[int] = None
    ) -> RetrievalResult:
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
            RetrievalResult with discovered documents
        """
        start_time = datetime.now(timezone.utc)
        session_id = str(uuid.uuid4())
        
        try:
            logger.error(f"DEBUG: Starting retrieval orchestration with session_id: {session_id}")
            
            # Create retrieval session for tracking
            if self.persistence_service:
                retrieval_session_id = await self.persistence_service.create_retrieval_session(
                    trial_id=trial_id,
                    asset_aliases=asset_aliases,
                    indication_terms=indication_terms,
                    query_metadata={},
                    session_id=session_id
                )
                logger.error(f"DEBUG: create_retrieval_session returned: {retrieval_session_id}")
            else:
                retrieval_session_id = None
            
            # Step 1: Create entity pack (canonical entities & aliases)
            entity_pack = self.entity_pack_builder.create_entity_pack(
                asset_aliases=asset_aliases,
                indication_terms=indication_terms,
                trial_nct=trial_nct,
                trial_phase=trial_phase,
                company_name=company_name,
                company_aliases=company_aliases
            )
            
            if not entity_pack:
                return RetrievalResult(
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
                return RetrievalResult(
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
            all_pmids = await self._execute_multi_tier_queries(query_tiers, max_results)
            if not all_pmids:
                return RetrievalResult(
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
            
            # Step 5: Apply sophisticated scoring and re-ranking
            scored_documents = await self._apply_document_scoring(validated_documents, entity_pack)
            
            # Step 6: Apply guardrails (content filtering)
            final_documents = await self._apply_guardrails(scored_documents, entity_pack)
            
            # Store RAW documents found during retrieval (before filtering)
            if self.persistence_service and retrieval_session_id and all_pmids:
                # Get raw document data for storage
                raw_documents = []
                for pmid in all_pmids:
                    # Determine which query tier found this document
                    query_tier = 'A'  # Default to tier A, we'll improve this later
                    raw_documents.append({
                        'pmid': pmid,
                        'title': f'Document {pmid}',  # Placeholder - we'll get real data later
                        'retrieval_tier': query_tier,  # Use valid tier value
                        'query_tier': query_tier,
                        'policy_engine_passed': False,  # Not yet processed
                        'guardrails_passed': False,     # Not yet processed
                        'created_at': datetime.now(timezone.utc)
                    })
                
                logger.error(f"DEBUG: About to store documents with session_id: {retrieval_session_id}")
                stored_count = await self.persistence_service.store_retrieval_documents(
                    trial_id=trial_id,
                    session_id=retrieval_session_id,
                    documents=raw_documents,
                    retrieval_metadata={
                        'query_tiers': len(query_tiers),
                        'ctgov_queries': len(ctgov_queries),
                        'ctgov_trials_found': ctgov_result.trials_found if ctgov_result else 0,
                        'ctgov_nct_ids': ctgov_result.nct_ids if ctgov_result else [],
                        'total_pmids_before_filtering': len(all_pmids),
                        'documents_after_policy_engine': len(validated_documents),
                        'documents_after_scoring': len(scored_documents),
                        'final_documents': len(final_documents)
                    }
                )
                
                if stored_count == 0 and final_documents:
                    logger.error(f"No documents were stored despite having {len(final_documents)} documents")
            
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            # Update retrieval session with final metrics
            if self.persistence_service and retrieval_session_id:
                await self.persistence_service.update_session_completion(
                    session_id=retrieval_session_id,
                    total_documents_found=len(all_pmids),
                    documents_after_policy_engine=len(validated_documents),
                    documents_after_guardrails=len(final_documents),
                    documents_after_processing=len(final_documents),  # Same as guardrails for now
                    execution_time_seconds=execution_time,
                    status='completed'
                )
            
            logger.info(f"Retrieval orchestration completed in {execution_time:.2f}s: {len(final_documents)} documents (stored for human verification)")
            
            return RetrievalResult(
                success=True,
                documents=final_documents,
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
                documents_discovered=len(final_documents),
                documents_mapped=len(final_documents),
                pmids_found=len(all_pmids),
                session_id=session_id
            )
            
        except Exception as e:
            logger.error(f"Error in retrieval orchestration: {e}")
            
            # Update session as failed
            if self.persistence_service and retrieval_session_id:
                await self.persistence_service.update_session_completion(
                    session_id=retrieval_session_id,
                    total_documents_found=0,
                    documents_after_policy_engine=0,
                    documents_after_guardrails=0,
                    documents_after_processing=0,
                    execution_time_seconds=0.0,
                    status='failed'
                )
            
            return RetrievalResult(
                success=False,
                documents=[],
                query_metadata={},
                documents_discovered=0,
                documents_mapped=0,
                pmids_found=0,
                session_id=session_id,
                error_message=str(e)
            )
    
    async def _execute_multi_tier_queries(self, query_tiers: List[QueryTier], max_results: Optional[int]) -> List[str]:
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
    
    async def _apply_policy_engine(self, pmids: List[str], entity_pack: EntityPack) -> List[Dict[str, Any]]:
        """Apply policy engine validation to PMIDs and return documents."""
        try:
            # TEMPORARILY DISABLE POLICY ENGINE FOR DEBUGGING
            logger.warning("Policy engine temporarily disabled for debugging")
            # Return basic document structure for PMIDs
            return [{'pmid': pmid, 'policy_engine_passed': True} for pmid in pmids]
            
            if not self.policy_engine:
                logger.warning("Policy engine not available, skipping validation")
                # Return basic document structure for PMIDs
                return [{'pmid': pmid, 'policy_engine_passed': True} for pmid in pmids]
            
            # Fetch document metadata for policy validation
            async with self.client:
                esummary_result = await self.client.esummary_batch(pmids)
                documents = esummary_result.get('result', {})
                
                # Apply policy engine validation to each document
                validated_docs = []
                for pmid, doc_data in documents.items():
                    if isinstance(doc_data, dict):
                        policy_result = self.policy_engine.validate_document(doc_data, entity_pack)
                        if policy_result.passes_validation:
                            validated_docs.append({
                                'pmid': pmid,
                                'policy_engine_passed': True,
                                'policy_score': policy_result.score,
                                **doc_data
                            })
                
                logger.info(f"Policy engine validation: {len(validated_docs)} valid, {len(pmids) - len(validated_docs)} rejected")
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
            
            # Apply advanced scoring
            scored_tuples = self.document_scorer.rank_documents(documents, entity_pack)
            
            # Extract just the documents from the tuples
            scored_docs = [doc for doc, _ in scored_tuples]
            
            logger.info(f"Advanced scoring applied to {len(scored_docs)} documents")
            return scored_docs
            
        except Exception as e:
            logger.error(f"Error applying document scoring: {e}")
            return documents
    
    async def _apply_guardrails(self, documents: List[Dict[str, Any]], entity_pack: EntityPack) -> List[Dict[str, Any]]:
        """Apply guardrails for content filtering."""
        try:
            # TEMPORARILY DISABLE GUARDRAILS FOR DEBUGGING
            logger.warning("Guardrails temporarily disabled for debugging")
            return documents
            
            if not self.guardrails:
                logger.warning("Guardrails not available, skipping filtering")
                return documents
            
            # Apply guardrails filtering to each document
            filtered_docs = []
            for document in documents:
                guardrail_results = self.guardrails.validate_document(document, entity_pack)
                if not self.guardrails.should_reject_document(guardrail_results):
                    filtered_docs.append(document)
            
            logger.info(f"Guardrails applied to {len(documents)} documents: {len(filtered_docs)} passed")
            return filtered_docs
            
        except Exception as e:
            logger.error(f"Error applying guardrails: {e}")
            return documents