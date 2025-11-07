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
from sqlalchemy.orm import Session

from database.config import get_db_session
from database.models import (
    StagingRawData, EntityMatchCandidate, SourceProcessingLog,
    Company, Drug, Disease, Target, ClinicalTrial, Publication,
    Institution, EntityAlias
)
from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.relationship_builder import RelationshipBuilder
from src.entity_resolution.types import EntityType, ExtractedEntity, ResolutionStatus
from src.processors.clinicaltrials_processor import ClinicalTrialsProcessor
from src.processors.fda_drugs_processor import FDADrugsProcessor

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
        # Add more processors as they're implemented
    }
    
    def __init__(self, batch_size: int = 100):
        """
        Initialize processing pipeline.
        
        Args:
            batch_size: Number of records to process per batch
        """
        self.batch_size = batch_size
    
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
            resolver = EntityResolver(session)
            rel_builder = RelationshipBuilder(session)
            
            # Extract entities from raw data
            raw_data = staging_record.raw_data
            entities = processor.extract_entities(raw_data)
            
            if not processor.validate_extraction(entities):
                raise ValueError("Entity extraction validation failed")
            
            log.entities_extracted = sum(len(v) for v in entities.values())
            
            # Resolve each entity
            resolved_entities = {}
            needs_review_count = 0
            
            for entity_type, entity_list in entities.items():
                for i, extracted_entity in enumerate(entity_list):
                    # Resolve entity
                    resolution = resolver.resolve(extracted_entity)
                    
                    # Handle resolution result
                    if resolution.status == ResolutionStatus.EXACT_MATCH or \
                       resolution.status == ResolutionStatus.HIGH_CONFIDENCE:
                        # Use existing entity
                        entity_key = f"{entity_type}_{i}"
                        resolved_entities[entity_key] = resolution.entity_id
                        log.entities_matched = (log.entities_matched or 0) + 1
                        
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
                        new_entity_id = self._create_new_entity(
                            session,
                            extracted_entity
                        )
                        entity_key = f"{entity_type}_{i}"
                        resolved_entities[entity_key] = new_entity_id
                        log.entities_created = (log.entities_created or 0) + 1
                        
                        # Create alias for future matching
                        self._create_alias(
                            session,
                            extracted_entity.entity_type.value,
                            new_entity_id,
                            extracted_entity.name,
                            'original_name',
                            processor.SOURCE_NAME
                        )
            
            # Extract and create relationships
            relationships = processor.extract_relationships(raw_data, resolved_entities)
            
            for relationship in relationships:
                # Get source and target IDs from resolved_entities
                # This is simplified - in production you'd need better key matching
                source_id = resolved_entities.get('trial_0')  # Example
                target_id = resolved_entities.get('drug_0')  # Example
                
                if source_id and target_id:
                    rel_builder.create_relationship(
                        relationship,
                        source_id,
                        target_id,
                        processor.SOURCE_NAME
                    )
            
            rel_stats = rel_builder.get_stats()
            log.relationships_created = rel_stats['created']
            
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
        candidate = EntityMatchCandidate(
            candidate_id=uuid4(),
            entity_type=extracted_entity.entity_type.value,
            source_identifier=source_identifier,
            source_name=extracted_entity.source_name,
            extracted_text=extracted_entity.name,
            extracted_context=extracted_entity.context,
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
        }
        
        model = model_map.get(entity_type)
        if not model:
            raise ValueError(f"Unknown entity type: {entity_type}")
        
        # Create entity with appropriate fields
        entity_data = self._build_entity_data(extracted_entity, model)
        
        new_entity = model(**entity_data)
        session.add(new_entity)
        session.flush()  # Get the ID
        
        # Get the entity ID
        id_field = self._get_id_field(model)
        entity_id = getattr(new_entity, id_field)
        
        return entity_id
    
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
            
        elif model.__name__ == 'ClinicalTrial':
            data['trial_id'] = uuid4()
            data['nct_id'] = extracted_entity.identifiers.get('nct_id')
            data['trial_title'] = extracted_entity.name
            data['phase'] = extracted_entity.context.get('phase')
            data['status'] = extracted_entity.context.get('status')
            data['data_sources'] = {extracted_entity.source_name: {'first_seen': datetime.now().isoformat()}}
            
        # Add more entity types as needed
        
        return data
    
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
        }
        return id_fields.get(model.__name__, 'id')
    
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

