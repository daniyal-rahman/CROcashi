"""
Main processing pipeline that coordinates:
1. Fetch batch of unprocessed records from staging
2. Process each with appropriate source processor  
3. Resolve all entities
4. Create/update entities and relationships
5. Log results
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Type
from uuid import UUID, uuid4

from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.config import get_db_session
from database.models import (
    StagingRawData, EntityMatchCandidate, SourceProcessingLog,
    Company, Drug, Disease, Target, ClinicalTrial, Publication,
    Institution, EntityAlias, Patent, RegulatoryEvent, TrialStatusHistory, SECFiling,
    ConferencePresentation, Conference
)
from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.hybrid_resolver import HybridEntityResolver
from src.entity_resolution.relationship_builder import RelationshipBuilder
from src.entity_resolution.types import EntityType, ExtractedEntity, ResolutionStatus
from src.services.lineage_service import LineageService
from src.services.event_service import EventService
from src.services.relationship_inference import RelationshipInferenceService
from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
from src.processors.fda_drugs_processor import FDADrugsProcessor
from src.processors.patentsview_processor import PatentsViewProcessor
from src.processors.openfda_processor import OpenFDAProcessor
from src.processors.sec_filings_processor import SECFilingsProcessor
from src.processors.pubmed_processor import PubMedProcessor
from src.processors.fda_warning_letters_processor import FDAWarningLettersProcessor
from src.processors.warn_notices_processor import WARNNoticesProcessor
from src.processors.asco_abstracts_processor import ASCOAbstractsProcessor
from src.processors.fda_clinical_hold_processor import FDAClinicalHoldProcessor
from src.processors.fda_breakthrough_processor import FDABreakthroughProcessor
from src.processors.fda_orphan_processor import FDAOrphanProcessor
from src.processors.federal_warn_processor import FederalWARNProcessor
from src.processors.fda_orange_book_processor import FDAOrangeBookProcessor
from src.processors.biospace_layoff_tracker_processor import BioSpaceLayoffTrackerProcessor
from src.processors.fierce_layoff_tracker_processor import FierceLayoffTrackerProcessor
from src.processors.ema_epar_processor import EMAEPARProcessor
from src.processors.ema_prime_processor import EMAPRIMEProcessor
from src.processors.who_ictrp_processor import WHOICTRPProcessor
from src.processors.uspto_public_pair_processor import USPTOPublicPairProcessor
from src.processors.fda_purple_book_processor import FDAPurpleBookProcessor
from src.processors.ema_trials_processor import EMATrialsProcessor
from src.processors.health_canada_processor import HealthCanadaProcessor
from src.processors.mhra_uk_processor import MHRUKProcessor
from src.processors.tga_australia_processor import TGAAustraliaProcessor
from src.processors.fda_eua_processor import FDAEUAProcessor
from src.processors.fda_expanded_access_processor import FDAExpandedAccessProcessor
from src.processors.fda_faers_processor import FDAFAERSProcessor
from src.processors.who_outbreak_news_processor import WHOOutbreakNewsProcessor
from src.processors.ema_guidelines_processor import EMAGuidelinesProcessor
from src.processors.fda_guidance_processor import FDAGuidanceProcessor
from src.processors.ich_guidelines_processor import ICHGuidelinesProcessor
from src.processors.nih_reporter_processor import NIHReporterProcessor
from src.processors.nsf_awards_processor import NsfAwardsProcessor
from src.processors.vaers_processor import VAERSProcessor
from src.processors.anvisa_brazil_processor import AnvisaBrazilProcessor
from src.processors.cdsco_india_processor import CdscoIndiaProcessor
from src.processors.mfds_korea_processor import MfdsKoreaProcessor
from src.processors.hsa_singapore_processor import HsaSingaporeProcessor

logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """
    Main pipeline that coordinates staging → processing → resolution → relationship creation.
    
    Features:
    - Batch processing with configurable batch size
    - Transaction boundaries per staging record
    - Error handling with rollback
    - Idempotency (safe to re-process records)
    - Comprehensive logging
    """
    
    # Mapping of source names to processor classes
    PROCESSOR_MAP: Dict[str, Type[BaseProcessor]] = {
        'clinicaltrials_gov': ClinicalTrialsProcessor,
        'fda_drugs': FDADrugsProcessor,
        'patentsview': PatentsViewProcessor,
        'openfda': OpenFDAProcessor,
        'pubmed': PubMedProcessor,
        'sec_edgar': SECFilingsProcessor,
        'fda_warning_letters': FDAWarningLettersProcessor,
        'california_warn': WARNNoticesProcessor,
        'asco_abstracts': ASCOAbstractsProcessor,
        'fda_clinical_hold': FDAClinicalHoldProcessor,
        'fda_breakthrough': FDABreakthroughProcessor,
        'fda_orphan': FDAOrphanProcessor,
        'federal_warn': FederalWARNProcessor,
        'fda_orange_book': FDAOrangeBookProcessor,
        'biospace_layoff_tracker': BioSpaceLayoffTrackerProcessor,
        'fierce_layoff_tracker': FierceLayoffTrackerProcessor,
        'ema_epar': EMAEPARProcessor,
        'ema_prime': EMAPRIMEProcessor,
        'who_ictrp': WHOICTRPProcessor,
        'uspto_public_pair': USPTOPublicPairProcessor,
        'fda_purple_book': FDAPurpleBookProcessor,
        'ema_trials': EMATrialsProcessor,
        'health_canada': HealthCanadaProcessor,
        'mhra_uk': MHRUKProcessor,
        'tga_australia': TGAAustraliaProcessor,
        'fda_eua': FDAEUAProcessor,
        'fda_expanded_access': FDAExpandedAccessProcessor,
        'fda_faers': FDAFAERSProcessor,
        'who_outbreak_news': WHOOutbreakNewsProcessor,
        'ema_guidelines': EMAGuidelinesProcessor,
        'fda_guidance': FDAGuidanceProcessor,
        'ich_guidelines': ICHGuidelinesProcessor,
        'nih_reporter': NIHReporterProcessor,
        'nsf_awards': NsfAwardsProcessor,
        'vaers': VAERSProcessor,
        'anvisa_brazil': AnvisaBrazilProcessor,
        'cdsco_india': CdscoIndiaProcessor,
        'mfds_korea': MfdsKoreaProcessor,
        'hsa_singapore': HsaSingaporeProcessor,
        # Add more processors as they're implemented
    }
    
    def __init__(self, batch_size: int = 100, use_hybrid_resolver: bool = True):
        """
        Initialize processing pipeline.
        
        Args:
            batch_size: Number of records to process per batch
            use_hybrid_resolver: Use hybrid resolver (rule-based + LLM) if True,
                                 otherwise use rule-based only
        """
        self.batch_size = batch_size
        self.use_hybrid_resolver = use_hybrid_resolver
    
    def process_source(
        self,
        source_name: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process all unprocessed records for a specific source.
        
        Args:
            source_name: Name of the source (e.g., 'clinicaltrials_gov')
            limit: Optional limit on number of records to process
            
        Returns:
            Dict with processing statistics
        """
        logger.info(f"Starting processing for source: {source_name}")
        
        # Get processor class
        processor_class = self.PROCESSOR_MAP.get(source_name)
        if not processor_class:
            logger.error(f"No processor found for source: {source_name}")
            return {'error': f'Unknown source: {source_name}'}
        
        stats = {
            'source': source_name,
            'records_processed': 0,
            'records_failed': 0,
            'entities_created': 0,
            'entities_matched': 0,
            'relationships_created': 0,
            'needs_review': 0,
            'start_time': datetime.now()
        }
        
        # Process in batches
        processed_count = 0
        
        while True:
            if limit and processed_count >= limit:
                break
            
            batch_limit = min(self.batch_size, limit - processed_count) if limit else self.batch_size
            
            with get_db_session() as session:
                # Fetch unprocessed records
                records = self._fetch_unprocessed_records(
                    session,
                    source_name,
                    batch_limit
                )
                
                if not records:
                    break  # No more records
                
                logger.info(f"Processing batch of {len(records)} records")
                
                # Process each record
                for record in records:
                    result = self._process_single_record(
                        session,
                        record,
                        processor_class
                    )
                    
                    # Update stats
                    if result['status'] == 'success':
                        stats['records_processed'] += 1
                        stats['entities_created'] += result.get('entities_created', 0)
                        stats['entities_matched'] += result.get('entities_matched', 0)
                        stats['relationships_created'] += result.get('relationships_created', 0)
                        stats['needs_review'] += result.get('needs_review', 0)
                    else:
                        stats['records_failed'] += 1
                    
                    processed_count += 1
        
        stats['end_time'] = datetime.now()
        stats['duration_seconds'] = (stats['end_time'] - stats['start_time']).total_seconds()
        
        logger.info(f"Completed processing for {source_name}: {stats}")
        
        # Run relationship inference after processing (if enabled)
        # This infers relationships from existing data (e.g., company-drug from trials)
        try:
            with get_db_session() as session:
                inference_service = RelationshipInferenceService(session)
                inference_results = inference_service.infer_all_relationships()
                if inference_results.get('company_drug', {}).get('status') == 'success':
                    inferred_count = inference_results['company_drug'].get('relationships_inferred', 0)
                    if inferred_count > 0:
                        logger.info(f"Inferred {inferred_count} company-drug relationships from trial sponsorships")
        except Exception as e:
            logger.warning(f"Relationship inference failed (non-critical): {e}")
        
        return stats
    
    def _fetch_unprocessed_records(
        self,
        session: Session,
        source_name: str,
        limit: int
    ) -> List[StagingRawData]:
        """
        Fetch unprocessed records from staging table.
        
        Args:
            session: Database session
            source_name: Source system name
            limit: Maximum number of records
            
        Returns:
            List of staging records
        """
        query = session.query(StagingRawData).filter(
            and_(
                StagingRawData.source_system == source_name,
                StagingRawData.processed == False
            )
        ).limit(limit)
        
        return query.all()
    
    def _process_single_record(
        self,
        session: Session,
        staging_record: StagingRawData,
        processor_class: Type[BaseProcessor]
    ) -> Dict[str, Any]:
        """
        Process a single staging record with full transaction handling.
        
        Args:
            session: Database session
            staging_record: Staging record to process
            processor_class: Processor class for this source
            
        Returns:
            Dict with processing result
        """
        source_identifier = staging_record.source_record_id
        
        # Check if already processed (idempotency)
        existing_log = session.query(SourceProcessingLog).filter(
            and_(
                SourceProcessingLog.source_name == staging_record.source_system,
                SourceProcessingLog.source_identifier == source_identifier,
                SourceProcessingLog.processing_status == 'success'
            )
        ).first()
        
        if existing_log:
            logger.info(f"Record {source_identifier} already processed successfully, skipping")
            staging_record.processed = True
            return {'status': 'skipped', 'reason': 'already_processed'}
        
        # Create processing log
        log = SourceProcessingLog(
            log_id=uuid4(),
            source_name=staging_record.source_system,
            source_identifier=source_identifier,
            processing_started_at=datetime.now().date(),
            processing_status='processing'
        )
        session.add(log)
        
        try:
            # Initialize processor
            processor = processor_class(session)
            
            # Use hybrid resolver if enabled
            if self.use_hybrid_resolver:
                resolver = HybridEntityResolver(session)
            else:
                resolver = EntityResolver(session)
            
            rel_builder = RelationshipBuilder(session)
            lineage_service = LineageService(session)
            event_service = EventService(session)
            
            # Extract entities from raw data
            raw_data = staging_record.raw_data
            entities = processor.extract_entities(raw_data)
            
            # Filter out invalid entities (navigation text, etc.)
            entities = processor.filter_invalid_entities(entities)
            
            if not processor.validate_extraction(entities):
                raise ValueError("Entity extraction validation failed")
            
            log.entities_extracted = sum(len(v) for v in entities.values())
            
            # Resolve each entity
            resolved_entities = {}
            entity_stub_to_id = {}  # Maps entity stubs to resolved UUIDs
            id_to_entity = {}  # Maps resolved IDs to first extracted entity (for deduplication)
            needs_review_count = 0
            
            for entity_type, entity_list in entities.items():
                resolved_ids = []  # Collect all resolved IDs for this entity type
                seen_ids = set()  # Track IDs we've already added to avoid duplicates
                
                for i, extracted_entity in enumerate(entity_list):
                    # Resolve entity
                    resolution = resolver.resolve(extracted_entity)
                    resolved_id = None
                    
                    # Handle resolution result
                    if resolution.status == ResolutionStatus.EXACT_MATCH or \
                       resolution.status == ResolutionStatus.HIGH_CONFIDENCE:
                        # Use existing entity
                        resolved_id = resolution.entity_id
                        log.entities_matched = (log.entities_matched or 0) + 1
                        
                        # Store mapping from entity stub to resolved ID
                        stub_key = self._make_entity_stub_key(extracted_entity)
                        entity_stub_to_id[stub_key] = resolution.entity_id
                        
                        # Register in resolver cache for subsequent lookups in this run
                        resolver.register_entity(extracted_entity, resolution.entity_id)
                        
                    elif resolution.status == ResolutionStatus.NEEDS_REVIEW:
                        # Create match candidate for review
                        self._create_match_candidate(
                            session,
                            extracted_entity,
                            resolution,
                            source_identifier
                        )
                        needs_review_count += 1
                        
                    elif resolution.status == ResolutionStatus.NO_MATCH:
                        # Create new entity
                        resolved_id = self._create_new_entity(
                            session,
                            extracted_entity
                        )
                        log.entities_created = (log.entities_created or 0) + 1
                        
                        # Create lineage record for new entity
                        try:
                            source = lineage_service.get_or_create_source(
                                source_name=processor.SOURCE_NAME,
                                source_type=self._get_source_type(processor.SOURCE_NAME)
                            )
                            table_name = self._get_table_name_for_entity_type(extracted_entity.entity_type)
                            lineage_service.create_lineage_record(
                                table_name=table_name,
                                record_id=resolved_id,
                                source_id=source.source_id,
                                raw_data_snapshot=raw_data,
                                extraction_method='api',  # Could be made configurable
                                confidence_score=1.0  # New entities are high confidence
                            )
                        except (ValueError, IntegrityError) as e:
                            logger.warning(f"Failed to create lineage record: {e}")
                        
                        # Store mapping from entity stub to resolved ID
                        stub_key = self._make_entity_stub_key(extracted_entity)
                        entity_stub_to_id[stub_key] = resolved_id
                        
                        # Register in resolver cache for subsequent lookups in this run
                        resolver.register_entity(extracted_entity, resolved_id)
                        
                        # Create alias for future matching (only for entity types that support aliases)
                        # Allowed types: company, drug, disease, target, institution, trial, publication, patent
                        allowed_alias_types = {'company', 'drug', 'disease', 'target', 'institution', 'trial', 'publication', 'patent'}
                        if extracted_entity.entity_type.value in allowed_alias_types:
                            self._create_alias(
                                session,
                                extracted_entity.entity_type.value,
                                resolved_id,
                                extracted_entity.name,
                                'original_name',
                                processor.SOURCE_NAME
                            )
                    
                    # Add to list if successfully resolved AND not a duplicate
                    if resolved_id:
                        if resolved_id not in seen_ids:
                            resolved_ids.append(resolved_id)
                            seen_ids.add(resolved_id)
                            # Store first extracted entity for this ID (for relationship building)
                            id_to_entity[resolved_id] = extracted_entity
                            
                            # Handle trial status tracking for ClinicalTrials.gov only
                            if (entity_type == 'trials' and 
                                extracted_entity.entity_type == EntityType.TRIAL and
                                processor.SOURCE_NAME == 'clinicaltrials_gov'):
                                self._handle_trial_status_update(
                                    session,
                                    resolved_id,
                                    extracted_entity,
                                    processor.SOURCE_NAME,
                                    event_service=event_service
                                )
                
                # Store resolved entities in format processors expect:
                # - Singular form for certain entity types: 'trial', 'sponsor'
                #   (converted from 'trials' -> 'trial', 'companies' first -> 'sponsor')
                # - Plural form for multiples: 'drugs', 'diseases', 'collaborators'
                if resolved_ids:
                    if entity_type == 'trials' and len(resolved_ids) == 1:
                        # Store as singular 'trial'
                        resolved_entities['trial'] = resolved_ids[0]
                    elif entity_type == 'patents' and len(resolved_ids) == 1:
                        # Store as singular 'patent'
                        resolved_entities['patent'] = resolved_ids[0]
                    elif entity_type == 'filings' and len(resolved_ids) == 1:
                        # Store as singular 'filing'
                        resolved_entities['filing'] = resolved_ids[0]
                    elif entity_type == 'publications' and len(resolved_ids) == 1:
                        # Store as singular 'publication'
                        resolved_entities['publication'] = resolved_ids[0]
                    elif entity_type == 'companies' and len(resolved_ids) >= 1:
                        # For ClinicalTrials: first company is 'sponsor', rest are 'collaborators'
                        # For other sources: store as 'companies' (plural)
                        # Check if this is from ClinicalTrials processor
                        if processor.SOURCE_NAME == 'clinicaltrials_gov':
                            resolved_entities['sponsor'] = resolved_ids[0]
                            if len(resolved_ids) > 1:
                                resolved_entities['collaborators'] = resolved_ids[1:]
                        else:
                            # Store as-is for other sources (PatentsView, etc.)
                            resolved_entities[entity_type] = resolved_ids
                    elif entity_type == 'institutions' and len(resolved_ids) >= 1:
                        # For ClinicalTrials: first institution is 'sponsor' if no company sponsor
                        # Rest are 'collaborators'
                        # Check if this is from ClinicalTrials processor
                        if processor.SOURCE_NAME == 'clinicaltrials_gov':
                            # Only set as sponsor if we don't already have a company sponsor
                            if 'sponsor' not in resolved_entities:
                                resolved_entities['sponsor'] = resolved_ids[0]
                                if len(resolved_ids) > 1:
                                    # Add remaining institutions to collaborators
                                    if 'collaborators' not in resolved_entities:
                                        resolved_entities['collaborators'] = []
                                    resolved_entities['collaborators'].extend(resolved_ids[1:])
                            else:
                                # Company sponsor exists, so institutions are collaborators
                                if 'collaborators' not in resolved_entities:
                                    resolved_entities['collaborators'] = []
                                resolved_entities['collaborators'].extend(resolved_ids)
                        else:
                            # Store as-is for other sources
                            resolved_entities[entity_type] = resolved_ids
                    elif entity_type == 'regulatory_events':
                        # Store regulatory events as list
                        resolved_entities[entity_type] = resolved_ids
                    else:
                        # Store as-is (drugs, diseases, etc.)
                        resolved_entities[entity_type] = resolved_ids
            
            # Extract and create relationships
            logger.info(f"[RELATIONSHIPS] Extracting relationships for {source_identifier}...")
            relationships = processor.extract_relationships(raw_data, resolved_entities, id_to_entity)
            
            logger.info(
                f"[RELATIONSHIPS] Extracted {len(relationships)} relationships for {source_identifier}"
            )
            
            if len(relationships) == 0:
                logger.warning(
                    f"[RELATIONSHIPS] ⚠️ No relationships extracted for {source_identifier}. "
                    f"Resolved entities: {list(resolved_entities.keys())}"
                )
            
            for i, relationship in enumerate(relationships):
                logger.info(
                    f"[RELATIONSHIPS] Processing relationship {i+1}/{len(relationships)}: "
                    f"{relationship.relationship_type} "
                    f"({relationship.source_entity.entity_type.value} '{relationship.source_entity.name}' -> "
                    f"{relationship.target_entity.entity_type.value} '{relationship.target_entity.name}')"
                )
                
                # Look up source entity ID from the entity stub (Tier 1: memory cache)
                source_stub_key = self._make_entity_stub_key(relationship.source_entity)
                source_id = entity_stub_to_id.get(source_stub_key)
                
                logger.debug(
                    f"[RELATIONSHIPS] Source entity lookup: stub_key={source_stub_key}, "
                    f"pipeline_cache_hit={source_id is not None}"
                )
                
                # Tier 2: Database fallback if not in memory cache
                if not source_id:
                    logger.info(
                        f"[RELATIONSHIPS] Source entity not in pipeline cache, trying database fallback..."
                    )
                    source_id = self._resolve_entity_for_relationship(
                        resolver,
                        relationship.source_entity,
                        entity_stub_to_id
                    )
                
                # Look up target entity ID from the entity stub (Tier 1: memory cache)
                target_stub_key = self._make_entity_stub_key(relationship.target_entity)
                target_id = entity_stub_to_id.get(target_stub_key)
                
                logger.debug(
                    f"[RELATIONSHIPS] Target entity lookup: stub_key={target_stub_key}, "
                    f"pipeline_cache_hit={target_id is not None}"
                )
                
                # Tier 2: Database fallback if not in memory cache
                if not target_id:
                    logger.info(
                        f"[RELATIONSHIPS] Target entity not in pipeline cache, trying database fallback..."
                    )
                    target_id = self._resolve_entity_for_relationship(
                        resolver,
                        relationship.target_entity,
                        entity_stub_to_id
                    )
                
                logger.info(
                    f"[RELATIONSHIPS] Resolution results: "
                    f"source_id={source_id}, target_id={target_id}"
                )
                
                if source_id and target_id:
                    logger.info(
                        f"[RELATIONSHIPS] ✅ Both entities resolved, creating relationship..."
                    )
                    result = rel_builder.create_relationship(
                        relationship,
                        source_id,
                        target_id,
                        processor.SOURCE_NAME
                    )
                    if result:
                        logger.info(
                            f"[RELATIONSHIPS] ✅ SUCCESS: Created {relationship.relationship_type} "
                            f"relationship between {source_id} and {target_id}"
                        )
                    else:
                        logger.warning(
                            f"[RELATIONSHIPS] ❌ FAILED: RelationshipBuilder returned False for "
                            f"{relationship.relationship_type} between "
                            f"{relationship.source_entity.name} and {relationship.target_entity.name}"
                        )
                else:
                    # Log warning if entities not found after both tiers
                    if not source_id:
                        logger.warning(
                            f"[RELATIONSHIPS] ❌ Source entity not resolved for relationship "
                            f"(after database fallback): {relationship.relationship_type} - "
                            f"{relationship.source_entity.entity_type.value}: {relationship.source_entity.name} "
                            f"(stub_key: {source_stub_key}, identifiers: {relationship.source_entity.identifiers})"
                        )
                    if not target_id:
                        logger.warning(
                            f"[RELATIONSHIPS] ❌ Target entity not resolved for relationship "
                            f"(after database fallback): {relationship.relationship_type} - "
                            f"{relationship.target_entity.entity_type.value}: {relationship.target_entity.name} "
                            f"(stub_key: {target_stub_key}, identifiers: {relationship.target_entity.identifiers})"
                        )
            
            rel_stats = rel_builder.get_stats()
            log.relationships_created = rel_stats['created']
            
            # Convert regulatory events to unified events
            if 'regulatory_events' in resolved_entities:
                regulatory_event_ids = resolved_entities['regulatory_events']
                if isinstance(regulatory_event_ids, list):
                    for reg_event_id in regulatory_event_ids:
                        try:
                            # Get the regulatory event
                            reg_event = session.query(RegulatoryEvent).filter(
                                RegulatoryEvent.event_id == reg_event_id
                            ).first()
                            
                            if reg_event:
                                # Get entities involved (drug + company)
                                entities_involved = []
                                
                                # Get drug from relationships
                                from database.models.relationships import RegulatoryDrugEvent
                                drug_rel = session.query(RegulatoryDrugEvent).filter(
                                    RegulatoryDrugEvent.event_id == reg_event_id
                                ).first()
                                if drug_rel:
                                    entities_involved.append(drug_rel.drug_id)
                                
                                # Get company from relationships
                                from database.models.relationships import RegulatoryCompanyEvent
                                company_rel = session.query(RegulatoryCompanyEvent).filter(
                                    RegulatoryCompanyEvent.event_id == reg_event_id
                                ).first()
                                if company_rel:
                                    entities_involved.append(company_rel.company_id)
                                
                                # Add regulatory event itself
                                entities_involved.append(reg_event_id)
                                
                                # Get source ID
                                source = lineage_service.get_or_create_source(
                                    source_name=processor.SOURCE_NAME,
                                    source_type=self._get_source_type(processor.SOURCE_NAME)
                                )
                                
                                # Convert to unified event
                                event_service.convert_regulatory_event_to_event(
                                    regulatory_event_id=reg_event_id,
                                    entities_involved=entities_involved,
                                    source_id=source.source_id
                                )
                                logger.debug(f"Converted regulatory event {reg_event_id} to unified event")
                        except Exception as e:
                            logger.warning(f"Failed to convert regulatory event {reg_event_id} to event: {e}")
            
            # Mark as successfully processed
            staging_record.processed = True
            staging_record.processed_at = datetime.now()
            
            log.processing_status = 'success'
            log.processing_completed_at = datetime.now().date()
            
            session.commit()
            
            logger.info(f"Successfully processed {source_identifier}")
            
            return {
                'status': 'success',
                'entities_created': log.entities_created or 0,
                'entities_matched': log.entities_matched or 0,
                'relationships_created': log.relationships_created or 0,
                'needs_review': needs_review_count
            }
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error processing {source_identifier}: {e}", exc_info=True)
            
            # Update log with error
            log.processing_status = 'failed'
            log.processing_completed_at = datetime.now().date()
            log.errors = [str(e)]
            
            session.commit()
            
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _create_match_candidate(
        self,
        session: Session,
        extracted_entity: ExtractedEntity,
        resolution,
        source_identifier: str
    ):
        """Create a match candidate for manual review."""
        # Serialize context to ensure datetime objects are converted to strings
        serialized_context = self._serialize_for_json(extracted_entity.context)
        
        candidate = EntityMatchCandidate(
            candidate_id=uuid4(),
            entity_type=extracted_entity.entity_type.value,
            source_identifier=source_identifier,
            source_name=extracted_entity.source_name,
            extracted_text=extracted_entity.name,
            extracted_context=serialized_context,
            potential_matches=[
                {
                    'entity_id': str(c.entity_id),
                    'score': c.confidence_score,
                    'reason': '; '.join(c.match_reasons)
                }
                for c in resolution.candidates[:5]  # Top 5 candidates
            ],
            match_confidence=resolution.confidence_score,
            match_reasoning=resolution.reasoning,
            status='needs_review'
        )
        
        session.add(candidate)
    
    def _create_new_entity(
        self,
        session: Session,
        extracted_entity: ExtractedEntity
    ) -> UUID:
        """
        Create a new entity in the database.
        
        Args:
            session: Database session
            extracted_entity: Entity to create
            
        Returns:
            UUID of created entity
        """
        entity_type = extracted_entity.entity_type
        
        # Get the appropriate model
        model_map = {
            EntityType.COMPANY: Company,
            EntityType.INSTITUTION: Institution,
            EntityType.DRUG: Drug,
            EntityType.DISEASE: Disease,
            EntityType.TARGET: Target,
            EntityType.TRIAL: ClinicalTrial,
            EntityType.PUBLICATION: Publication,
            EntityType.PATENT: Patent,
            EntityType.REGULATORY_EVENT: RegulatoryEvent,
            EntityType.SEC_FILING: SECFiling,
            EntityType.CONFERENCE_PRESENTATION: ConferencePresentation,
        }
        
        model = model_map.get(entity_type)
        if not model:
            raise ValueError(f"Unknown entity type: {entity_type}")
        
        # Create entity with appropriate fields
        entity_data = self._build_entity_data(extracted_entity, model)
        
        # Handle Conference lookup for ConferencePresentation
        if model.__name__ == 'ConferencePresentation' and '_conference_name' in entity_data:
            conference_name = entity_data.pop('_conference_name')
            # Look up Conference by name (Conference is already imported at top)
            conference = session.query(Conference).filter(
                Conference.conference_name == conference_name
            ).first()
            if not conference:
                # Create Conference if it doesn't exist
                conference = Conference(
                    conference_id=uuid4(),
                    conference_name=conference_name,
                    conference_date=extracted_entity.context.get('conference_date')
                )
                session.add(conference)
                session.flush()
            entity_data['conference_id'] = conference.conference_id
        
        new_entity = model(**entity_data)
        session.add(new_entity)
        session.flush()  # Get the ID
        
        # Get the entity ID
        id_field = self._get_id_field(model)
        entity_id = getattr(new_entity, id_field)
        
        return entity_id
    
    @staticmethod
    def _normalize_trial_status(status: Optional[str]) -> Optional[str]:
        """
        Normalize and map trial status to valid database values.
        
        Valid statuses: 'recruiting', 'active', 'completed', 'terminated', 'suspended', 
        'withdrawn', 'unknown', 'enrolling_by_invitation', 'active_not_recruiting', 'not_yet_recruiting'
        
        Args:
            status: Raw status string
            
        Returns:
            Normalized status string or None if invalid
        """
        if not status:
            return None
        
        status = status.lower()
        
        # Valid statuses
        valid_statuses = {
            'recruiting', 'active', 'completed', 'terminated', 'suspended', 
            'withdrawn', 'unknown', 'enrolling_by_invitation', 
            'active_not_recruiting', 'not_yet_recruiting'
        }
        
        # Map common invalid statuses
        status_map = {
            'available': 'unknown',  # Expanded access or other
            'approved_for_marketing': 'completed',
            'no_longer_available': 'withdrawn',
            'temporarily_not_available': 'suspended',
            'withdrawn': 'withdrawn',
            'recruiting': 'recruiting',
            'active, not recruiting': 'active_not_recruiting',
            'not yet recruiting': 'not_yet_recruiting',
            'enrolling by invitation': 'enrolling_by_invitation',
        }
        
        # Apply mapping if needed
        if status in status_map:
            status = status_map[status]
        
        # If still not valid, set to None
        if status not in valid_statuses:
            status = None
        
        return status
    
    @staticmethod
    def _serialize_for_json(obj: Any) -> Any:
        """
        Recursively serialize objects for JSON storage.
        Converts datetime objects to ISO format strings.
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: ProcessingPipeline._serialize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [ProcessingPipeline._serialize_for_json(item) for item in obj]
        elif isinstance(obj, UUID):
            return str(obj)
        elif hasattr(obj, 'isoformat'):  # date objects
            return obj.isoformat()
        else:
            return obj
    
    @staticmethod
    def _build_entity_data(extracted_entity: ExtractedEntity, model) -> Dict[str, Any]:
        """Build entity data dict for model creation."""
        data = {}
        
        # Common fields
        if model.__name__ == 'Company':
            data['company_id'] = uuid4()
            data['name'] = extracted_entity.name
            data['ticker'] = extracted_entity.identifiers.get('ticker')
            data['data_sources'] = {extracted_entity.source_name: {'first_seen': datetime.now().isoformat()}}
            
        elif model.__name__ == 'Institution':
            data['institution_id'] = uuid4()
            data['name'] = extracted_entity.name
            # Map sponsor_class to valid institution_type values
            sponsor_class = extracted_entity.context.get('sponsor_class', '').lower()
            institution_type_map = {
                'other': 'research_institute',
                'nih': 'government',
                'other_gov': 'government',
                'fed': 'government',
                'network': 'cooperative_group',
                'industry': 'research_institute',  # Shouldn't happen, but handle it
            }
            data['institution_type'] = institution_type_map.get(sponsor_class, 'research_institute')
            data['country'] = extracted_entity.context.get('country')
            
        elif model.__name__ == 'Drug':
            data['drug_id'] = uuid4()
            data['primary_name'] = extracted_entity.name
            data['generic_name'] = extracted_entity.context.get('generic_name')
            data['code_name'] = extracted_entity.context.get('code_name')
            data['data_sources'] = {extracted_entity.source_name: {'first_seen': datetime.now().isoformat()}}
            
        elif model.__name__ == 'Disease':
            data['disease_id'] = uuid4()
            data['disease_name'] = extracted_entity.name
            data['data_sources'] = {extracted_entity.source_name: {'first_seen': datetime.now().isoformat()}}
            
        elif model.__name__ == 'Target':
            data['target_id'] = uuid4()
            data['gene_symbol'] = extracted_entity.name
            data['target_name'] = extracted_entity.context.get('target_name', extracted_entity.name)
            data['target_type'] = extracted_entity.context.get('target_type', 'protein')
            
        elif model.__name__ == 'ClinicalTrial':
            data['trial_id'] = uuid4()
            data['nct_id'] = extracted_entity.identifiers.get('nct_id')
            data['eudract_number'] = extracted_entity.identifiers.get('eudract_number')
            data['trial_title'] = extracted_entity.name
            data['phase'] = extracted_entity.context.get('phase')
            data['phase_numeric'] = extracted_entity.context.get('phase_numeric')
            # Map status to valid values (constraint only allows specific statuses)
            data['status'] = ProcessingPipeline._normalize_trial_status(
                extracted_entity.context.get('status')
            )
            # Normalize study_type to lowercase and map invalid values
            study_type = extracted_entity.context.get('study_type')
            if study_type:
                study_type = study_type.lower()
                # Map expanded_access to None (not allowed by constraint)
                # Constraint only allows 'interventional', 'observational', or NULL
                if study_type not in ['interventional', 'observational']:
                    study_type = None
            data['study_type'] = study_type
            # Map enrollment from context to enrollment_target
            enrollment = extracted_entity.context.get('enrollment')
            if enrollment:
                data['enrollment_target'] = enrollment
            # Map dates from context
            start_date = extracted_entity.context.get('start_date')
            if start_date:
                # Convert datetime to date if needed
                if isinstance(start_date, datetime):
                    start_date = start_date.date()
                elif isinstance(start_date, str):
                    try:
                        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
                    except (ValueError, AttributeError):
                        pass
                data['start_date'] = start_date
            completion_date = extracted_entity.context.get('completion_date')
            if completion_date:
                # Convert datetime to date if needed
                if isinstance(completion_date, datetime):
                    completion_date = completion_date.date()
                elif isinstance(completion_date, str):
                    try:
                        completion_date = datetime.fromisoformat(completion_date.replace('Z', '+00:00')).date()
                    except (ValueError, AttributeError):
                        pass
                data['completion_date'] = completion_date
            data['why_stopped'] = extracted_entity.context.get('why_stopped')
            # Handle array fields (ARRAY(Text) in database)
            for array_field in ['primary_endpoints', 'secondary_endpoints', 'study_locations']:
                array_value = extracted_entity.context.get(array_field)
                if array_value and isinstance(array_value, list):
                    # Ensure all are strings
                    data[array_field] = [str(item) for item in array_value if item]
                else:
                    data[array_field] = None
            data['data_sources'] = {extracted_entity.source_name: {'first_seen': datetime.now().isoformat()}}
            
        elif model.__name__ == 'Publication':
            data['pub_id'] = uuid4()
            # Title is required (nullable=False)
            data['title'] = extracted_entity.name or extracted_entity.context.get('title') or 'Untitled Publication'
            data['pmid'] = extracted_entity.identifiers.get('pmid')
            data['doi'] = extracted_entity.identifiers.get('doi')
            data['pmcid'] = extracted_entity.identifiers.get('pmcid')
            # Map publication_date with date conversion
            publication_date = extracted_entity.context.get('publication_date')
            if publication_date:
                # Convert datetime to date if needed
                if isinstance(publication_date, datetime):
                    publication_date = publication_date.date()
                elif isinstance(publication_date, str):
                    try:
                        publication_date = datetime.fromisoformat(publication_date.replace('Z', '+00:00')).date()
                    except (ValueError, AttributeError):
                        pass
            data['publication_date'] = publication_date
            data['journal'] = extracted_entity.context.get('journal')
            data['abstract'] = extracted_entity.context.get('abstract')
            # Normalize publication_type (has check constraint)
            publication_type = extracted_entity.context.get('publication_type')
            if publication_type:
                publication_type = publication_type.lower()
                valid_publication_types = {'clinical_trial', 'review', 'meta_analysis', 'case_report'}
                if publication_type not in valid_publication_types:
                    publication_type = None  # Set to None if invalid
            data['publication_type'] = publication_type
            data['is_clinical_trial_result'] = extracted_entity.context.get('is_clinical_trial_result', False)
            data['data_sources'] = {extracted_entity.source_name: {'first_seen': datetime.now().isoformat()}}
        
        elif model.__name__ == 'Patent':
            data['patent_id'] = uuid4()
            patent_number = extracted_entity.identifiers.get('patent_number')
            if not patent_number:
                raise ValueError("Patent number is required (nullable=False in database)")
            data['patent_number'] = patent_number
            data['patent_office'] = extracted_entity.context.get('patent_office', 'USPTO')
            data['title'] = extracted_entity.name or extracted_entity.context.get('title')
            # Map date fields with conversion
            for date_field in ['filing_date', 'publication_date', 'grant_date', 'expiration_date']:
                date_value = extracted_entity.context.get(date_field)
                if date_value:
                    # Convert datetime to date if needed
                    if isinstance(date_value, datetime):
                        date_value = date_value.date()
                    elif isinstance(date_value, str):
                        try:
                            date_value = datetime.fromisoformat(date_value.replace('Z', '+00:00')).date()
                        except (ValueError, AttributeError):
                            pass
                data[date_field] = date_value
            # Normalize patent status (has check constraint)
            patent_status = extracted_entity.context.get('status')
            if patent_status:
                patent_status = patent_status.lower()
                valid_patent_statuses = {'pending', 'granted', 'expired', 'abandoned'}
                if patent_status not in valid_patent_statuses:
                    patent_status = None  # Set to None if invalid
            data['status'] = patent_status
            # Assignees must be list of strings (ARRAY(Text) in database)
            assignees = extracted_entity.context.get('assignees', [])
            if assignees and isinstance(assignees, list):
                # Ensure all are strings
                data['assignees'] = [str(a) for a in assignees if a]
            else:
                data['assignees'] = []
            data['data_sources'] = {extracted_entity.source_name: {'first_seen': datetime.now().isoformat()}}
        
        elif model.__name__ == 'SECFiling':
            data['filing_id'] = uuid4()
            # Normalize filing_type (has check constraint)
            filing_type = extracted_entity.context.get('filing_type', '8-K')
            valid_filing_types = {'8-K', '10-K', '10-Q', 'S-1', 'DEF 14A'}
            if filing_type not in valid_filing_types:
                # Default to '8-K' if invalid
                filing_type = '8-K'
            data['filing_type'] = filing_type
            # Map filing_date with date conversion
            filing_date = extracted_entity.context.get('filing_date')
            if not filing_date:
                raise ValueError("filing_date is required (nullable=False in database)")
            # Convert datetime to date if needed
            if isinstance(filing_date, datetime):
                filing_date = filing_date.date()
            elif isinstance(filing_date, str):
                try:
                    filing_date = datetime.fromisoformat(filing_date.replace('Z', '+00:00')).date()
                except (ValueError, AttributeError):
                    pass
            data['filing_date'] = filing_date
            accession_number = extracted_entity.identifiers.get('accession_number')
            if not accession_number:
                raise ValueError("accession_number is required (nullable=False in database)")
            data['accession_number'] = accession_number
            data['filing_url'] = extracted_entity.context.get('filing_url')
            data['full_text'] = extracted_entity.context.get('full_text')
            data['mentions_milestones'] = extracted_entity.context.get('mentions_milestones', False)
            data['mentions_restructuring'] = extracted_entity.context.get('mentions_restructuring', False)
            data['cash_position'] = extracted_entity.context.get('cash_position')
            data['runway_months'] = extracted_entity.context.get('runway_months')
            # Note: SECFiling model does not have data_sources field (unlike other entities)
        
        elif model.__name__ == 'RegulatoryEvent':
            data['event_id'] = uuid4()
            # Normalize event_type (required, has check constraint)
            event_type = extracted_entity.context.get('event_type', '').lower()
            valid_event_types = {'approval', 'rejection', 'breakthrough', 'orphan', 'fast_track', 'clinical_hold', 'withdrawal'}
            if event_type not in valid_event_types:
                # Default to 'approval' if invalid (most common case)
                event_type = 'approval'
            data['event_type'] = event_type
            
            # Map event_date with date conversion (required, nullable=False)
            event_date = extracted_entity.context.get('event_date')
            if not event_date:
                # Use current date as fallback if missing (required field)
                event_date = datetime.now().date()
            else:
                # Convert datetime to date if needed
                if isinstance(event_date, datetime):
                    event_date = event_date.date()
                elif isinstance(event_date, str):
                    try:
                        event_date = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
                    except (ValueError, AttributeError):
                        event_date = datetime.now().date()  # Fallback
            data['event_date'] = event_date
            
            # Normalize regulatory_body (required, has check constraint)
            regulatory_body = extracted_entity.context.get('regulatory_body', '').strip()
            valid_regulatory_bodies = {'FDA', 'EMA', 'PMDA', 'Health_Canada'}
            if regulatory_body not in valid_regulatory_bodies:
                # Default to 'FDA' if invalid (most common case)
                regulatory_body = 'FDA'
            data['regulatory_body'] = regulatory_body
            
            data['country'] = extracted_entity.context.get('country')
            data['application_number'] = extracted_entity.identifiers.get('application_number')
            
            # Normalize approval_type (optional, has check constraint)
            approval_type = extracted_entity.context.get('approval_type')
            if approval_type:
                approval_type = approval_type.lower()
                valid_approval_types = {'full', 'accelerated', 'priority_review'}
                if approval_type not in valid_approval_types:
                    approval_type = None  # Set to None if invalid
            data['approval_type'] = approval_type
            
            data['description'] = extracted_entity.context.get('description')
            data['document_url'] = extracted_entity.context.get('document_url')
            data['data_sources'] = {extracted_entity.source_name: {'first_seen': datetime.now().isoformat()}}
        
        elif model.__name__ == 'ConferencePresentation':
            data['presentation_id'] = uuid4()
            # Conference is required (foreign key)
            # Try to get conference_id from context first (set by processor)
            conference_id = extracted_entity.context.get('conference_id')
            if not conference_id:
                # Look up Conference by name from resolved entities
                # Conference should have been processed before ConferencePresentation
                conference_name = extracted_entity.context.get('conference', '')
                if conference_name:
                    # This lookup will be done in _create_new_entity by passing session
                    # For now, we'll store conference_name and look it up in _create_new_entity
                    # Store conference_name for lookup
                    data['_conference_name'] = conference_name
                else:
                    raise ValueError("Conference name or ID required for ConferencePresentation")
            else:
                data['conference_id'] = conference_id
            data['abstract_number'] = extracted_entity.identifiers.get('abstract_number') or extracted_entity.identifiers.get('abstract_id')
            # Normalize presentation_type (has check constraint)
            presentation_type = extracted_entity.context.get('presentation_type')
            if presentation_type:
                presentation_type = presentation_type.lower()
                valid_presentation_types = {'oral', 'poster', 'late_breaking'}
                if presentation_type not in valid_presentation_types:
                    presentation_type = None
            data['presentation_type'] = presentation_type
            data['title'] = extracted_entity.name or extracted_entity.context.get('title')
            data['abstract'] = extracted_entity.context.get('abstract_text') or extracted_entity.context.get('abstract')
            # Handle authors array
            authors = extracted_entity.context.get('authors', [])
            if authors and isinstance(authors, list):
                data['authors'] = [str(a) for a in authors if a]
            else:
                data['authors'] = []
            # Map presentation_date with date conversion
            presentation_date = extracted_entity.context.get('presentation_date')
            if presentation_date:
                # Convert datetime to date if needed
                if isinstance(presentation_date, datetime):
                    presentation_date = presentation_date.date()
                elif isinstance(presentation_date, str):
                    try:
                        presentation_date = datetime.fromisoformat(presentation_date.replace('Z', '+00:00')).date()
                    except (ValueError, AttributeError):
                        pass
            data['presentation_date'] = presentation_date
            # Normalize status (has check constraint)
            status = extracted_entity.context.get('status')
            if status:
                status = status.lower()
                valid_statuses = {'accepted', 'presented', 'withdrawn'}
                if status not in valid_statuses:
                    status = None
            data['status'] = status
            data['data_sources'] = {extracted_entity.source_name: {'first_seen': datetime.now().isoformat()}}
        
        return data
    
    def _handle_trial_status_update(
        self,
        session: Session,
        trial_id: UUID,
        extracted_entity: ExtractedEntity,
        source_name: str,
        event_service: Optional[EventService] = None
    ):
        """
        Handle trial status updates and create status history entries and events.
        
        Args:
            session: Database session
            trial_id: UUID of the trial
            extracted_entity: Extracted trial entity with new status
            source_name: Source system name
            event_service: Optional EventService for creating events
        """
        # Get current trial from database
        trial = session.query(ClinicalTrial).filter(
            ClinicalTrial.trial_id == trial_id
        ).first()
        
        if not trial:
            return
        
        # Get new status from extracted entity and normalize it
        new_status = self._normalize_trial_status(extracted_entity.context.get('status'))
        if not new_status:
            # Can't update status history with None (constraint requires NOT NULL)
            # Skip status update if normalization returns None
            return
        
        # Check if status has changed
        current_status = trial.status.lower() if trial.status else None
        
        # Check if trial already has status history (to detect newly created trials)
        existing_history = session.query(TrialStatusHistory).filter(
            TrialStatusHistory.trial_id == trial_id
        ).first()
        
        # Determine status date
        status_date = datetime.now().date()
        if extracted_entity.context.get('status_verified_date'):
            try:
                status_date = extracted_entity.context['status_verified_date']
                if isinstance(status_date, str):
                    status_date = datetime.strptime(status_date, '%Y-%m-%d').date()
                elif isinstance(status_date, datetime):
                    status_date = status_date.date()
            except (ValueError, TypeError):
                pass  # Use current date as fallback
        
        # Get source ID for events
        source_id = None
        if event_service:
            try:
                from database.models.sources import Source
                source = session.query(Source).filter(
                    Source.source_name == source_name
                ).first()
                if source:
                    source_id = source.source_id
            except Exception as e:
                logger.warning(f"Could not get source ID for {source_name}: {e}")
        
        # Get entities involved (trial + sponsor companies)
        entities_involved = [trial_id]
        try:
            from database.models.relationships import TrialSponsor
            sponsors = session.query(TrialSponsor).filter(
                TrialSponsor.trial_id == trial_id,
                TrialSponsor.entity_type == 'company',
                TrialSponsor.deleted_at.is_(None)
            ).all()
            for sponsor in sponsors:
                if sponsor.entity_id not in entities_involved:
                    entities_involved.append(sponsor.entity_id)
        except Exception as e:
            logger.warning(f"Could not get sponsors for trial {trial_id}: {e}")
        
        if current_status != new_status:
            # Status has changed - create history entry
            status_history = TrialStatusHistory(
                history_id=uuid4(),
                trial_id=trial_id,
                status=new_status,
                status_date=status_date,
                source=source_name,
                notes=f"Status changed from {current_status} to {new_status}"
            )
            session.add(status_history)
            
            # Update trial status and status_verified_date
            trial.status = new_status
            trial.status_verified_date = status_date
            
            # Create event for status change
            if event_service:
                try:
                    event_service.convert_trial_status_to_event(
                        trial_id=trial_id,
                        status=new_status,
                        status_date=status_date,
                        entities_involved=entities_involved,
                        source_id=source_id
                    )
                    logger.debug(f"Created event for trial {trial.nct_id} status change: {new_status}")
                except Exception as e:
                    logger.warning(f"Failed to create event for trial status change: {e}")
            
            logger.info(
                f"Trial {trial.nct_id} status changed: {current_status} -> {new_status}"
            )
        elif not existing_history:
            # No existing history - create initial status history entry (for newly created trials)
            status_history = TrialStatusHistory(
                history_id=uuid4(),
                trial_id=trial_id,
                status=new_status,
                status_date=status_date,
                source=source_name,
                notes="Initial status recorded"
            )
            session.add(status_history)
            
            # Update status_verified_date if not already set
            if not trial.status_verified_date:
                trial.status_verified_date = status_date
            
            # Create event for initial status (trial initiated/started)
            if event_service:
                try:
                    # Map initial status to appropriate event type
                    initial_event_type = 'trial.status.initiated'
                    if new_status in ['recruiting', 'active', 'enrolling_by_invitation']:
                        initial_event_type = 'trial.status.recruiting'
                    elif new_status == 'completed':
                        initial_event_type = 'trial.status.completed'
                    
                    event_service.create_event(
                        event_type=initial_event_type,
                        event_date=status_date,
                        entities_involved=entities_involved,
                        event_data={
                            'trial_id': str(trial_id),
                            'status': new_status,
                            'nct_id': trial.nct_id
                        },
                        source_id=source_id
                    )
                    logger.debug(f"Created initial event for trial {trial.nct_id}: {initial_event_type}")
                except Exception as e:
                    logger.warning(f"Failed to create initial event for trial: {e}")
    
    @staticmethod
    def _get_source_type(source_name: str) -> str:
        """Get source type for a source name."""
        source_type_map = {
            'clinicaltrials_gov': 'clinical',
            'fda_drugs': 'regulatory',
            'sec_edgar': 'financial',
            'pubmed': 'literature',
            'patentsview': 'patent',
            'openfda': 'regulatory',
            'fda_warning_letters': 'regulatory',
            'california_warn': 'financial',
            'asco_abstracts': 'literature',
        }
        return source_type_map.get(source_name, 'other')
    
    @staticmethod
    def _get_table_name_for_entity_type(entity_type: EntityType) -> str:
        """Get table name for an entity type."""
        table_map = {
            EntityType.COMPANY: 'companies',
            EntityType.INSTITUTION: 'institutions',
            EntityType.DRUG: 'drugs',
            EntityType.DISEASE: 'diseases',
            EntityType.TARGET: 'targets',
            EntityType.TRIAL: 'clinical_trials',
            EntityType.PUBLICATION: 'publications',
            EntityType.PATENT: 'patents',
            EntityType.REGULATORY_EVENT: 'regulatory_events',
            EntityType.SEC_FILING: 'sec_filings',
            EntityType.CONFERENCE_PRESENTATION: 'conference_presentations',
        }
        return table_map.get(entity_type, 'unknown')
    
    @staticmethod
    def _get_id_field(model) -> str:
        """Get the ID field name for a model."""
        id_fields = {
            'Company': 'company_id',
            'Institution': 'institution_id',
            'Drug': 'drug_id',
            'Disease': 'disease_id',
            'Target': 'target_id',
            'ClinicalTrial': 'trial_id',
            'Publication': 'pub_id',
            'Patent': 'patent_id',
            'RegulatoryEvent': 'event_id',
            'SECFiling': 'filing_id',
        }
        return id_fields.get(model.__name__, 'id')
    
    @staticmethod
    def _make_entity_stub_key(entity: ExtractedEntity) -> tuple:
        """
        Create a hashable key from an ExtractedEntity for mapping to resolved IDs.
        
        CRITICAL: Must use the same normalization as entity extraction functions
        to ensure stub keys match extracted entities.
        
        Args:
            entity: ExtractedEntity object
            
        Returns:
            Tuple that uniquely identifies this entity
        """
        # Use entity type, name, and key identifiers to create unique key
        # Sort identifiers to ensure consistent hashing
        identifier_tuple = tuple(sorted(
            (k, v) for k, v in entity.identifiers.items() 
            if v  # Only include non-empty identifiers
        ))
        
        # CRITICAL: Use the same normalization as extraction functions
        # This ensures stub keys match extracted entity names
        from src.entity_resolution.base_processor import BaseProcessor
        
        # Normalize name based on entity type (same as extraction)
        if entity.entity_type == EntityType.DRUG:
            normalized_name = BaseProcessor.normalize_drug_name_static(entity.name)
        elif entity.entity_type == EntityType.COMPANY:
            normalized_name = BaseProcessor.normalize_company_name_static(entity.name)
        else:
            # For other types, use simple normalization
            normalized_name = entity.name.lower().strip()
        
        return (
            entity.entity_type.value,
            normalized_name,
            identifier_tuple
        )
    
    def _resolve_entity_for_relationship(
        self,
        resolver: EntityResolver,
        entity: ExtractedEntity,
        entity_stub_to_id: Dict
    ) -> Optional[UUID]:
        """
        Resolve an entity for relationship building with database fallback.
        
        This implements Tier 2 (database fallback) for cross-run entity resolution.
        When an entity is not in the current run's memory cache, this method
        queries the database to find entities from previous runs.
        
        Args:
            resolver: EntityResolver instance (has its own memory cache)
            entity: ExtractedEntity to resolve
            entity_stub_to_id: Pipeline's entity stub to ID mapping
            
        Returns:
            UUID of resolved entity, or None if not found
        """
        logger.info(
            f"[CROSS-RUN RESOLUTION] Attempting to resolve {entity.entity_type.value} "
            f"'{entity.name}' with identifiers: {entity.identifiers}"
        )
        
        # Check pipeline's memory cache first (Tier 1)
        stub_key = self._make_entity_stub_key(entity)
        logger.debug(f"[CROSS-RUN RESOLUTION] Pipeline cache key: {stub_key}")
        
        if stub_key in entity_stub_to_id:
            cached_id = entity_stub_to_id[stub_key]
            logger.info(
                f"[CROSS-RUN RESOLUTION] ✅ Pipeline cache HIT for {entity.entity_type.value} "
                f"'{entity.name}' -> {cached_id}"
            )
            return cached_id
        
        logger.info(
            f"[CROSS-RUN RESOLUTION] Pipeline cache MISS for {entity.entity_type.value} "
            f"'{entity.name}', trying resolver (database fallback)..."
        )
        
        # Tier 2: Try resolver (checks its memory cache, then database)
        # This enables cross-run resolution - finding entities processed in previous runs
        logger.debug(f"[CROSS-RUN RESOLUTION] Calling resolver.resolve() for {entity.entity_type.value} '{entity.name}'")
        resolution = resolver.resolve(entity)
        
        logger.info(
            f"[CROSS-RUN RESOLUTION] Resolver result: status={resolution.status.value}, "
            f"entity_id={resolution.entity_id}, confidence={resolution.confidence_score:.2f}, "
            f"reasoning={resolution.reasoning}"
        )
        
        # Only use high-confidence resolutions (EXACT_MATCH or HIGH_CONFIDENCE)
        # NEEDS_REVIEW and NO_MATCH don't have entity_id, so they're safely ignored
        if resolution.entity_id:
            # Register in pipeline cache for subsequent lookups in this run
            entity_stub_to_id[stub_key] = resolution.entity_id
            logger.info(
                f"[CROSS-RUN RESOLUTION] ✅ SUCCESS: Resolved {entity.entity_type.value} "
                f"'{entity.name}' via database fallback -> {resolution.entity_id} "
                f"(status: {resolution.status.value})"
            )
            logger.debug(
                f"[CROSS-RUN RESOLUTION] Registered in pipeline cache: {stub_key} -> {resolution.entity_id}"
            )
            return resolution.entity_id
        
        # Entity not found in database either
        logger.warning(
            f"[CROSS-RUN RESOLUTION] ❌ FAILED: Entity {entity.entity_type.value} "
            f"'{entity.name}' not found in database fallback. "
            f"Status: {resolution.status.value}, Reasoning: {resolution.reasoning}"
        )
        return None
    
    @staticmethod
    def _create_alias(
        session: Session,
        entity_type: str,
        entity_id: UUID,
        alias_text: str,
        alias_type: str,
        source: str
    ):
        """Create an alias entry."""
        alias = EntityAlias(
            alias_id=uuid4(),
            entity_type=entity_type,
            entity_id=entity_id,
            alias_text=alias_text,
            alias_type=alias_type,
            source=source,
            confidence_score=1.0
        )
        session.add(alias)

