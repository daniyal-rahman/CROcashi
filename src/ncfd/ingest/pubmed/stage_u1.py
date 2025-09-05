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
from datetime import datetime, UTC
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .client import PubMedClient
from .mapper import PubMedMapper
from .db_service import PubMedDBService
from ...extract.abstract_features import AbstractFeatureExtractor
from ...score.simple_rs_scorer import SimpleRSScorer

logger = logging.getLogger(__name__)


@dataclass
class StageU1Result:
    """Result from Stage U1 execution."""
    trial_id: str
    success: bool
    documents_processed: int
    abstracts_fetched: int
    entities_extracted: int
    documents_scored: int
    documents_selected: int
    documents_dropped: int
    execution_time: float
    error_message: Optional[str] = None
    processed_documents: Optional[List[Dict[str, Any]]] = None
    rs_scores: Optional[List[Dict[str, Any]]] = None
    # Database persistence results
    rs_scores_stored: int = 0
    rs_scores_failed: int = 0
    candidates_stored: int = 0
    candidates_failed: int = 0
    trial_state_updated: bool = False


class StageU1Processor:
    """Processes Stage U1: Abstract Processing."""
    
    def __init__(
        self,
        client: PubMedClient,
        mapper: PubMedMapper,
        feature_extractor: AbstractFeatureExtractor,
        rs_scorer: SimpleRSScorer,
        config: Optional[Dict] = None
    ):
        """
        Initialize Stage U1 processor.
        
        Args:
            client: PubMed client instance
            mapper: Response mapper instance
            feature_extractor: Feature extraction instance
            rs_scorer: R/S scoring instance
            config: Configuration dictionary
        """
        self.client = client
        self.mapper = mapper
        self.feature_extractor = feature_extractor
        self.rs_scorer = rs_scorer
        self.config = config or {}
        
        # Initialize database service
        self.db_service = PubMedDBService()
        
        # Stage U1 settings
        self.batch_size = self.config.get('batch_size', 10)
        self.enable_entity_extraction = self.config.get('enable_entity_extraction', True)
        self.enable_rs_scoring = self.config.get('enable_rs_scoring', True)
        self.min_r_score = self.config.get('min_r_score', 0.35)  # R1 threshold
        self.min_s_score = self.config.get('min_s_score', 0.20)  # S1 threshold
        self.max_abstracts_initial = self.config.get('max_abstracts_initial', 50)  # Max abstracts to process initially
        self.enable_database_persistence = self.config.get('enable_database_persistence', True)
    
    async def execute_stage_u1(
        self,
        trial_id: str,
        u0_documents: List[Dict[str, Any]],
        trial_asset: str,
        trial_indication: str,
        trial_nct: Optional[str] = None
    ) -> StageU1Result:
        """
        Execute Stage U1: Abstract Processing.
        
        Args:
            trial_id: Unique trial identifier
            u0_documents: Documents from Stage U0
            trial_asset: Asset name for scoring
            trial_indication: Indication for scoring
            trial_nct: Optional NCT ID for scoring
            
        Returns:
            StageU1Result with execution details
        """
        start_time = datetime.now(UTC)
        
        try:
            logger.info(f"Starting Stage U1 for trial {trial_id} with {len(u0_documents)} documents")
            
            if not u0_documents:
                logger.warning(f"No documents to process for trial {trial_id}")
                return StageU1Result(
                    trial_id=trial_id,
                    success=True,
                    documents_processed=0,
                    abstracts_fetched=0,
                    entities_extracted=0,
                    documents_scored=0,
                    documents_selected=0,
                    documents_dropped=0,
                    execution_time=(datetime.now(UTC) - start_time).total_seconds()
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
                    execution_time=(datetime.now(UTC) - start_time).total_seconds()
                )
            
            logger.info(f"Fetched abstracts for {len(abstracts_fetched)} documents")
            
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
                    documents_for_scoring, trial_asset, trial_indication, trial_nct
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
            trial_state_updated = False
            
            if self.enable_database_persistence:
                try:
                    # Convert trial_id to int for database operations
                    trial_id_int = self._convert_trial_id_to_int(trial_id)
                    
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
            
            execution_time = (datetime.now(UTC) - start_time).total_seconds()
            
            logger.info(f"Stage U1 completed for {trial_id}: "
                       f"{len(documents_scored)} scored, {len(selected_docs)} selected, "
                       f"{len(dropped_docs)} dropped in {execution_time:.2f}s")
            
            return StageU1Result(
                trial_id=trial_id,
                success=True,
                documents_processed=len(u0_documents),
                abstracts_fetched=len(abstracts_fetched),
                entities_extracted=total_entities,
                documents_scored=len(documents_scored),
                documents_selected=len(selected_docs),
                documents_dropped=len(dropped_docs),
                execution_time=execution_time,
                processed_documents=final_documents,
                rs_scores=rs_scores,
                rs_scores_stored=rs_scores_stored,
                rs_scores_failed=rs_scores_failed,
                candidates_stored=candidates_stored,
                candidates_failed=candidates_failed,
                trial_state_updated=trial_state_updated
            )
            
        except Exception as e:
            execution_time = (datetime.now(UTC) - start_time).total_seconds()
            error_msg = f"Stage U1 failed for trial {trial_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            return StageU1Result(
                trial_id=trial_id,
                success=False,
                documents_processed=0,
                abstracts_fetched=0,
                entities_extracted=0,
                documents_scored=0,
                documents_selected=0,
                documents_dropped=0,
                execution_time=execution_time,
                error_message=error_msg
            )
    
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
        trial_id: str, 
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
                'decided_at': datetime.now(UTC).isoformat(),
                'created_at': datetime.now(UTC).isoformat()
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
            
            # Tightened selection criteria:
            # 1. R ≥ R1 (0.35) AND S ≥ S1 (0.20) - standard selection
            # 2. R ≥ R3 (0.75) - very high relevance can compensate for lower shortability
            # 3. Still within max_abstracts_initial limit for initial processing
            
            # Standard selection criteria
            if r_score >= self.min_r_score and s_score >= self.min_s_score:
                return True
            
            # High relevance compensation (R3 threshold)
            if r_score >= 0.75:  # R3 threshold
                return True
            
            # Initial processing limit
            if seen_so_far < self.max_abstracts_initial:
                return True
            
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
                    'stage_completed_at': datetime.now(UTC).isoformat(),
                    'selection_status': doc.get('selection_status', 'unknown'),
                    'selection_reason': doc.get('selection_reason', 'unknown')
                }
                
                updated_docs.append(doc)
                
            except Exception as e:
                logger.warning(f"Failed to update stage information: {e}")
                updated_docs.append(doc)
        
        return updated_docs
    
    def _convert_trial_id_to_int(self, trial_id: str) -> Optional[int]:
        """
        Attempt to convert a trial_id string to an integer.
        This is necessary because the database expects integers for trial_id.
        """
        try:
            return int(trial_id)
        except ValueError:
            logger.warning(f"Could not convert trial_id '{trial_id}' to integer.")
            return None
    
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
                'notes': f"R/S scoring completed: {doc.get('rs_score', {}).get('R_tier', 'N/A')}{doc.get('rs_score', {}).get('S_tier', 'N/A')}" if doc.get('rs_score') else None
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
