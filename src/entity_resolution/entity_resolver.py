"""
Entity resolver with hierarchical matching strategy.

Implements 6-level matching hierarchy:
1. Exact Identifier Match (confidence = 1.0)
2. Exact Name Match (confidence = 0.95)
3. Alias Lookup (confidence = 0.90)
4. Fuzzy Match with Context (confidence = 0.70-0.89)
5. Fuzzy Match Alone (confidence = 0.60-0.79)
6. No Match (create new entity)
"""
import logging
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, or_, text
from sqlalchemy.exc import ProgrammingError, OperationalError
from sqlalchemy.orm import Session

from database.models import (
    Company, Drug, Disease, Target, ClinicalTrial, Publication,
    Institution, EntityAlias, EntityMatchCandidate, Patent, RegulatoryEvent, SECFiling
)
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, MatchCandidate, MatchMethod,
    ResolutionResult, ResolutionStatus
)
from src.entity_resolution.confidence_scorer import ConfidenceScorer

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Resolves entities using hierarchical matching strategy.
    
    The resolver tries strategies in order of confidence:
    1. Exact identifier (CIK, NCT ID, PMID, etc.)
    2. Exact name match
    3. Alias lookup
    4. Fuzzy match with context
    5. Fuzzy match alone
    6. No match found
    """
    
    # Mapping of entity types to database models
    ENTITY_MODELS = {
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
    }
    
    # Identifier fields for each entity type
    IDENTIFIER_FIELDS = {
        EntityType.COMPANY: ['ticker', 'name'],  # CIK would be in identifiers dict
        EntityType.DRUG: ['chembl_id', 'drugbank_id', 'inchi_key', 'cas_number', 'unii_code'],
        EntityType.DISEASE: ['icd10_code', 'mesh_id', 'snomed_code', 'disease_ontology_id'],
        EntityType.TARGET: ['uniprot_id', 'gene_symbol', 'gene_id'],
        EntityType.TRIAL: ['nct_id', 'eudract_number'],
        EntityType.PUBLICATION: ['pmid', 'doi', 'pmcid'],
        EntityType.INSTITUTION: ['name'],  # Institutions don't have many unique identifiers
        EntityType.PATENT: ['patent_number'],
        EntityType.REGULATORY_EVENT: ['application_number'],
        EntityType.SEC_FILING: ['accession_number'],
    }
    
    def __init__(self, session: Session):
        """
        Initialize entity resolver.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.scorer = ConfidenceScorer(session)
        
        # Memory cache for current processing run
        # Maps cache key (entity_type, identifier_field, identifier_value) -> (entity_id, match_method, confidence_score, status, reasoning)
        # Only stores high-confidence resolutions (EXACT_MATCH or HIGH_CONFIDENCE)
        # Stores metadata to preserve original resolution method for audit trails
        self._memory_cache: Dict[tuple, tuple] = {}
        
        # Reverse cache: entity_id -> cache key (for deduplication)
        self._id_to_cache_key: Dict[UUID, tuple] = {}
    
    def resolve(self, entity: ExtractedEntity) -> ResolutionResult:
        """
        Resolve an extracted entity using hierarchical matching.
        
        Uses two-tier lookup:
        1. Memory cache (fast path) - entities resolved in current run
        2. Database queries (fallback) - for cross-run resolution
        
        Args:
            entity: Extracted entity to resolve
            
        Returns:
            ResolutionResult with match details
        """
        logger.info(
            f"[RESOLVER] Resolving {entity.entity_type.value}: '{entity.name}' "
            f"with identifiers: {entity.identifiers}"
        )
        
        # Tier 1: Check memory cache first (fast path)
        cached_result = self._lookup_in_memory_cache(entity)
        if cached_result:
            entity_id, match_method, confidence_score, status, reasoning = cached_result
            logger.info(
                f"[RESOLVER] ✅ Memory cache HIT for {entity.entity_type.value} "
                f"'{entity.name}' -> {entity_id} (original method: {match_method.value if match_method else 'N/A'})"
            )
            return ResolutionResult(
                status=status,
                entity_id=entity_id,
                confidence_score=confidence_score,
                match_method=match_method,
                reasoning=f"Found in memory cache from current run (originally: {reasoning})"
            )
        
        logger.info(
            f"[RESOLVER] Memory cache MISS for {entity.entity_type.value} '{entity.name}', "
            f"trying database queries..."
        )
        
        # Tier 2: Database fallback (cross-run resolution)
        # Level 1: Try exact identifier match
        logger.debug(f"[RESOLVER] Level 1: Trying exact identifier match...")
        result = self._try_exact_identifier(entity)
        if result.status == ResolutionStatus.EXACT_MATCH:
            logger.info(
                f"[RESOLVER] ✅ Level 1 SUCCESS: Exact identifier match found: {result.entity_id} "
                f"(reasoning: {result.reasoning})"
            )
            # Register in cache for future lookups in this run
            if result.entity_id:
                self._register_in_cache(entity, result)
            return result
        else:
            logger.debug(f"[RESOLVER] Level 1 FAILED: {result.reasoning}")
        
        # Level 2: Try exact name match
        logger.debug(f"[RESOLVER] Level 2: Trying exact name match...")
        result = self._try_exact_name(entity)
        if result.status == ResolutionStatus.EXACT_MATCH:
            logger.info(
                f"[RESOLVER] ✅ Level 2 SUCCESS: Exact name match found: {result.entity_id} "
                f"(reasoning: {result.reasoning})"
            )
            # Register in cache for future lookups in this run
            if result.entity_id:
                self._register_in_cache(entity, result)
            return result
        else:
            logger.debug(f"[RESOLVER] Level 2 FAILED: {result.reasoning}")
        
        # Level 3: Try alias lookup
        logger.debug(f"[RESOLVER] Level 3: Trying alias lookup...")
        result = self._try_alias_lookup(entity)
        if result.status in (ResolutionStatus.EXACT_MATCH, ResolutionStatus.HIGH_CONFIDENCE):
            logger.info(
                f"[RESOLVER] ✅ Level 3 SUCCESS: Alias match found: {result.entity_id} "
                f"(status: {result.status.value}, reasoning: {result.reasoning})"
            )
            # Register in cache for future lookups in this run
            if result.entity_id:
                self._register_in_cache(entity, result)
            return result
        elif result.status == ResolutionStatus.NEEDS_REVIEW:
            logger.info(
                f"[RESOLVER] ⚠️ Level 3 NEEDS_REVIEW: Multiple alias matches found "
                f"(reasoning: {result.reasoning})"
            )
            return result
        else:
            logger.debug(f"[RESOLVER] Level 3 FAILED: {result.reasoning}")
        
        # Level 4: Try fuzzy match with context
        logger.debug(f"[RESOLVER] Level 4: Trying fuzzy match with context...")
        result = self._try_fuzzy_context(entity)
        if result.status == ResolutionStatus.HIGH_CONFIDENCE:
            logger.info(
                f"[RESOLVER] ✅ Level 4 SUCCESS: Fuzzy context match found: {result.entity_id} "
                f"(score: {result.confidence_score:.2f}, reasoning: {result.reasoning})"
            )
            # Register in cache for future lookups in this run
            if result.entity_id:
                self._register_in_cache(entity, result)
            return result
        elif result.status == ResolutionStatus.NEEDS_REVIEW:
            logger.info(
                f"[RESOLVER] ⚠️ Level 4 NEEDS_REVIEW: Fuzzy context match "
                f"(score: {result.confidence_score:.2f}, reasoning: {result.reasoning})"
            )
            return result
        else:
            logger.debug(f"[RESOLVER] Level 4 FAILED: {result.reasoning}")
        
        # Level 5: Try fuzzy match alone
        logger.debug(f"[RESOLVER] Level 5: Trying fuzzy match alone...")
        result = self._try_fuzzy_alone(entity)
        if result.status == ResolutionStatus.NEEDS_REVIEW:
            logger.info(
                f"[RESOLVER] ⚠️ Level 5 NEEDS_REVIEW: Fuzzy match "
                f"(score: {result.confidence_score:.2f}, reasoning: {result.reasoning})"
            )
            return result
        else:
            logger.debug(f"[RESOLVER] Level 5 FAILED: {result.reasoning}")
        
        # Level 6: No match found
        logger.warning(
            f"[RESOLVER] ❌ Level 6 FAILED: No match found for {entity.entity_type.value} "
            f"'{entity.name}' after trying all strategies. Marking for new entity creation."
        )
        return ResolutionResult(
            status=ResolutionStatus.NO_MATCH,
            confidence_score=0.0,
            match_method=MatchMethod.NO_MATCH,
            reasoning="No matches found in any strategy",
            should_create_new=True
        )
    
    def _try_exact_identifier(self, entity: ExtractedEntity) -> ResolutionResult:
        """
        Level 1: Try to match by exact identifier.
        
        Confidence: 1.0 (perfect match)
        """
        model = self.ENTITY_MODELS.get(entity.entity_type)
        if not model:
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning=f"Unknown entity type: {entity.entity_type}"
            )
        
        identifier_fields = self.IDENTIFIER_FIELDS.get(entity.entity_type, [])
        
        # Try each identifier field
        for field_name in identifier_fields:
            # Check in entity.identifiers dict
            if field_name in entity.identifiers and entity.identifiers[field_name]:
                value = entity.identifiers[field_name]
                
                # Query database for this identifier
                if hasattr(model, field_name):
                    query = self.session.query(model).filter(
                        getattr(model, field_name) == value
                    )
                    result = query.first()
                    
                    if result:
                        entity_id = self._get_entity_id(result)
                        return ResolutionResult(
                            status=ResolutionStatus.EXACT_MATCH,
                            entity_id=entity_id,
                            confidence_score=1.0,
                            match_method=MatchMethod.EXACT_IDENTIFIER,
                            reasoning=f"Exact identifier match on {field_name}={value}"
                        )
        
        return ResolutionResult(
            status=ResolutionStatus.NO_MATCH,
            reasoning="No exact identifier match found"
        )
    
    def _try_exact_name(self, entity: ExtractedEntity) -> ResolutionResult:
        """
        Level 2: Try to match by exact name (case-insensitive, normalized).
        
        Confidence: 0.95
        """
        model = self.ENTITY_MODELS.get(entity.entity_type)
        if not model:
            return ResolutionResult(status=ResolutionStatus.NO_MATCH)
        
        # Normalize the name
        normalized_name = self.scorer._normalize_text(entity.name)
        
        # Get the name field for this entity type
        name_field = self._get_name_field(model)
        if not name_field:
            return ResolutionResult(status=ResolutionStatus.NO_MATCH)
        
        # Query with normalized name comparison
        # Use PostgreSQL LOWER() for case-insensitive match
        query = self.session.query(model).filter(
            text(f"LOWER(REGEXP_REPLACE({name_field}, '[^a-zA-Z0-9\\s\\-]', '', 'g')) = :normalized_name")
        ).params(normalized_name=normalized_name)
        
        result = query.first()
        
        if result:
            entity_id = self._get_entity_id(result)
            return ResolutionResult(
                status=ResolutionStatus.EXACT_MATCH,
                entity_id=entity_id,
                confidence_score=0.95,
                match_method=MatchMethod.EXACT_NAME,
                reasoning=f"Exact name match (normalized): {entity.name}"
            )
        
        return ResolutionResult(
            status=ResolutionStatus.NO_MATCH,
            reasoning="No exact name match found"
        )
    
    def _try_alias_lookup(self, entity: ExtractedEntity) -> ResolutionResult:
        """
        Level 3: Try to match via alias lookup.
        
        Confidence: 0.90
        """
        # Query entity_aliases table
        query = self.session.query(EntityAlias).filter(
            and_(
                EntityAlias.entity_type == entity.entity_type.value,
                EntityAlias.alias_text.ilike(entity.name)
            )
        )
        
        aliases = query.all()
        
        if len(aliases) == 0:
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning="No alias match found"
            )
        elif len(aliases) == 1:
            # Single alias match
            alias = aliases[0]
            return ResolutionResult(
                status=ResolutionStatus.HIGH_CONFIDENCE,
                entity_id=alias.entity_id,
                confidence_score=0.90,
                match_method=MatchMethod.ALIAS,
                reasoning=f"Single alias match: {alias.alias_text} ({alias.alias_type})"
            )
        else:
            # Multiple aliases found - needs review
            candidates = [
                MatchCandidate(
                    entity_id=alias.entity_id,
                    entity_name=alias.alias_text,
                    confidence_score=float(alias.confidence_score or 0.90),
                    match_reasons=[f"Alias type: {alias.alias_type}"]
                )
                for alias in aliases
            ]
            
            return ResolutionResult(
                status=ResolutionStatus.NEEDS_REVIEW,
                confidence_score=0.90,
                match_method=MatchMethod.ALIAS,
                candidates=candidates,
                reasoning=f"Multiple alias matches found ({len(aliases)}), needs review"
            )
    
    def _try_fuzzy_context(self, entity: ExtractedEntity) -> ResolutionResult:
        """
        Level 4: Try fuzzy matching with context boosting.
        
        Confidence: 0.70-0.89 (depending on context)
        Thresholds:
            - >= 0.85: Auto-match
            - 0.70-0.84: Needs review
        """
        model = self.ENTITY_MODELS.get(entity.entity_type)
        if not model:
            return ResolutionResult(status=ResolutionStatus.NO_MATCH)
        
        name_field = self._get_name_field(model)
        if not name_field:
            return ResolutionResult(status=ResolutionStatus.NO_MATCH)
        
        # Use PostgreSQL similarity search with case-insensitive matching
        # Normalize the search name first
        try:
            normalized_search = self.scorer._normalize_text(entity.name)
            # Ensure it's a valid string and handle encoding issues
            if not isinstance(normalized_search, str):
                normalized_search = str(normalized_search)
            # Remove or replace problematic characters
            normalized_search = normalized_search.encode('utf-8', errors='ignore').decode('utf-8')
        except Exception as e:
            logger.warning(f"Error normalizing text '{entity.name}': {e}, skipping fuzzy match")
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning=f"Text normalization failed: {str(e)}"
            )
        
        # Minimum base similarity to consider fuzzy matches
        # This is tuned based on precision/recall analysis - see entity_resolution docs
        # Values below this threshold are too dissimilar to be meaningful matches
        similarity_threshold = 0.3
        
        # Get ID field name for explicit selection
        id_field = self._get_id_field_name(model)
        
        # Use explicit column selection instead of SELECT * to avoid indexing issues
        try:
            query_text = text(f"""
                SELECT {id_field}, {name_field}, similarity(LOWER({name_field}), :search_name) as sim_score
                FROM {model.__tablename__}
                WHERE similarity(LOWER({name_field}), :search_name) > :threshold
                ORDER BY sim_score DESC
                LIMIT 10
            """)
            
            results = self.session.execute(
                query_text,
                {"search_name": normalized_search, "threshold": similarity_threshold}
            ).fetchall()
        except (ProgrammingError, OperationalError) as e:
            logger.warning(f"Error executing fuzzy match query for '{entity.name}': {e}, skipping")
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning=f"Fuzzy match query failed: {str(e)}"
            )
        
        if not results:
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning="No fuzzy matches above threshold"
            )
        
        # Score each candidate with context
        candidates = []
        for row in results:
            # Explicit column order: [id_field, name_field, sim_score]
            entity_id = UUID(str(row[0]))  # First column is ID
            entity_name = str(row[1])  # Second column is name
            sim_score = float(row[2])  # Third column is similarity score
            
            # Calculate score with context (using stage normalization for diseases)
            candidate_context = self._get_entity_context(model, entity_id)
            if entity.entity_type == EntityType.DISEASE:
                score, reasons = self.scorer.calculate_score_with_stage_normalization(
                    entity.name,
                    entity_name,
                    entity.entity_type.value,
                    entity.context,
                    candidate_context
                )
            else:
                score, reasons = self.scorer.calculate_score(
                    entity.name,
                    entity_name,
                    entity.context,
                    candidate_context
                )
            
            if score >= 0.70:  # Only include if above fuzzy threshold
                candidates.append(
                    MatchCandidate(
                        entity_id=entity_id,
                        entity_name=entity_name,
                        confidence_score=score,
                        match_reasons=reasons
                    )
                )
        
        if not candidates:
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning="No candidates above confidence threshold"
            )
        
        # Sort by score
        candidates.sort(key=lambda x: x.confidence_score, reverse=True)
        best_candidate = candidates[0]
        
        # Best match threshold: if best match is significantly better than second, auto-approve
        BEST_MATCH_THRESHOLD = 0.15  # 15% confidence difference
        has_clear_best_match = False
        if len(candidates) > 1:
            second_best_score = candidates[1].confidence_score
            score_diff = best_candidate.confidence_score - second_best_score
            if score_diff >= BEST_MATCH_THRESHOLD:
                has_clear_best_match = True
        
        # Decide based on best score
        if best_candidate.confidence_score >= 0.85:
            return ResolutionResult(
                status=ResolutionStatus.HIGH_CONFIDENCE,
                entity_id=best_candidate.entity_id,
                confidence_score=best_candidate.confidence_score,
                match_method=MatchMethod.FUZZY_CONTEXT,
                candidates=candidates[:5],  # Include top 5 for reference
                reasoning="; ".join(best_candidate.match_reasons)
            )
        elif best_candidate.confidence_score >= 0.75 and has_clear_best_match:
            # Medium confidence but clear best match - auto-approve
            return ResolutionResult(
                status=ResolutionStatus.HIGH_CONFIDENCE,
                entity_id=best_candidate.entity_id,
                confidence_score=best_candidate.confidence_score,
                match_method=MatchMethod.FUZZY_CONTEXT,
                candidates=candidates[:5],
                reasoning=f"Clear best match (score diff: {score_diff:.2f}); " + "; ".join(best_candidate.match_reasons)
            )
        else:
            return ResolutionResult(
                status=ResolutionStatus.NEEDS_REVIEW,
                confidence_score=best_candidate.confidence_score,
                match_method=MatchMethod.FUZZY_CONTEXT,
                candidates=candidates[:5],
                reasoning="; ".join(best_candidate.match_reasons)
            )
    
    def _try_fuzzy_alone(self, entity: ExtractedEntity) -> ResolutionResult:
        """
        Level 5: Try fuzzy matching without context.
        
        Confidence: 0.60-0.79
        All matches at this level need review.
        """
        model = self.ENTITY_MODELS.get(entity.entity_type)
        if not model:
            return ResolutionResult(status=ResolutionStatus.NO_MATCH)
        
        name_field = self._get_name_field(model)
        if not name_field:
            return ResolutionResult(status=ResolutionStatus.NO_MATCH)
        
        # Use PostgreSQL similarity search with case-insensitive matching
        # Normalize the search name first
        try:
            normalized_search = self.scorer._normalize_text(entity.name)
            # Ensure it's a valid string and handle encoding issues
            if not isinstance(normalized_search, str):
                normalized_search = str(normalized_search)
            # Remove or replace problematic characters
            normalized_search = normalized_search.encode('utf-8', errors='ignore').decode('utf-8')
        except Exception as e:
            logger.warning(f"Error normalizing text '{entity.name}': {e}, skipping fuzzy match")
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning=f"Text normalization failed: {str(e)}"
            )
        
        similarity_threshold = 0.70  # Higher threshold for fuzzy alone
        
        # Get ID field name for explicit selection
        id_field = self._get_id_field_name(model)
        
        # Use explicit column selection instead of SELECT * to avoid indexing issues
        try:
            query_text = text(f"""
                SELECT {id_field}, {name_field}, similarity(LOWER({name_field}), :search_name) as sim_score
                FROM {model.__tablename__}
                WHERE similarity(LOWER({name_field}), :search_name) > :threshold
                ORDER BY sim_score DESC
                LIMIT 5
            """)
            
            results = self.session.execute(
                query_text,
                {"search_name": normalized_search, "threshold": similarity_threshold}
            ).fetchall()
        except Exception as e:
            logger.warning(f"Error executing fuzzy match query for '{entity.name}': {e}, skipping")
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning=f"Fuzzy match query failed: {str(e)}"
            )
        
        if not results:
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning="No fuzzy matches above threshold (without context)"
            )
        
        # Convert to candidates
        # Explicit column order: [id_field, name_field, sim_score]
        candidates = []
        for row in results:
            entity_id = UUID(str(row[0]))  # First column is ID
            entity_name = str(row[1])  # Second column is name
            sim_score = float(row[2])  # Third column is similarity score
            
            candidates.append(
                MatchCandidate(
                    entity_id=entity_id,
                    entity_name=entity_name,
                    confidence_score=sim_score,
                    match_reasons=[f"Trigram similarity: {sim_score:.2f} (no context)"]
                )
            )
        
        best_candidate = candidates[0]
        
        return ResolutionResult(
            status=ResolutionStatus.NEEDS_REVIEW,
            confidence_score=best_candidate.confidence_score,
            match_method=MatchMethod.FUZZY_ALONE,
            candidates=candidates,
            reasoning=f"High similarity ({best_candidate.confidence_score:.2f}) but no context to boost confidence"
        )
    
    @staticmethod
    def _get_entity_id(entity_obj) -> UUID:
        """Get the entity ID from a model object."""
        id_fields = [
            'company_id', 'institution_id', 'drug_id', 'disease_id',
            'target_id', 'trial_id', 'pub_id', 'patent_id', 'filing_id'
        ]
        
        for field in id_fields:
            if hasattr(entity_obj, field):
                return getattr(entity_obj, field)
        
        raise ValueError(f"Could not find ID field for entity: {entity_obj}")
    
    @staticmethod
    def _get_name_field(model) -> Optional[str]:
        """Get the primary name field for an entity model."""
        name_fields = {
            'Company': 'name',
            'Institution': 'name',
            'Drug': 'primary_name',
            'Disease': 'disease_name',
            'Target': 'target_name',
            'ClinicalTrial': 'trial_title',
            'Publication': 'title',
            'Patent': 'title',
            'RegulatoryEvent': 'description',  # Or could use application_number for matching
            'SECFiling': 'accession_number',  # Use accession_number as primary identifier
        }
        return name_fields.get(model.__name__)
    
    # Removed _get_name_field_index - now using explicit column selection
    
    def _get_entity_context(self, model, entity_id: UUID) -> Dict:
        """
        Get context information for an entity to boost matching.
        
        Queries relationship tables to find associated entities that can
        help boost matching confidence.
        
        Args:
            model: Entity model class (Company, Drug, etc.)
            entity_id: UUID of the entity
            
        Returns:
            Dict with context keys: company_ids, disease_ids, target_ids, 
            mechanism_ids, drug_ids, trial_ids, date
        """
        from database.models import (
            CompanyDrug, DrugIndication, DrugTarget, DrugMechanism,
            TrialSponsor, TrialDrug, TrialDisease,
            Company, Drug, Disease, ClinicalTrial
        )
        
        context = {
            'company_ids': [],
            'disease_ids': [],
            'target_ids': [],
            'mechanism_ids': [],
            'drug_ids': [],
            'trial_ids': [],
            'date': None
        }
        
        try:
            model_name = model.__name__
            
            # Get entity to extract creation date
            entity = self.session.query(model).filter(
                getattr(model, self._get_id_field_name(model)) == entity_id
            ).first()
            
            if entity and hasattr(entity, 'created_at'):
                context['date'] = entity.created_at
            
            # Company context
            if model_name == 'Company':
                # Get drugs associated with this company
                drug_rels = self.session.query(CompanyDrug.drug_id).filter(
                    CompanyDrug.company_id == entity_id
                ).limit(20).all()
                context['drug_ids'] = [rel.drug_id for rel in drug_rels]
                
                # Get trials sponsored by this company
                trial_rels = self.session.query(TrialSponsor.trial_id).filter(
                    and_(
                        TrialSponsor.entity_id == entity_id,
                        TrialSponsor.entity_type == 'company'
                    )
                ).limit(20).all()
                context['trial_ids'] = [rel.trial_id for rel in trial_rels]
            
            # Drug context
            elif model_name == 'Drug':
                # Get companies associated with this drug
                company_rels = self.session.query(CompanyDrug.company_id).filter(
                    CompanyDrug.drug_id == entity_id
                ).limit(10).all()
                context['company_ids'] = [rel.company_id for rel in company_rels]
                
                # Get diseases/indications for this drug
                disease_rels = self.session.query(DrugIndication.disease_id).filter(
                    DrugIndication.drug_id == entity_id
                ).limit(10).all()
                context['disease_ids'] = [rel.disease_id for rel in disease_rels]
                
                # Get targets for this drug
                target_rels = self.session.query(DrugTarget.target_id).filter(
                    DrugTarget.drug_id == entity_id
                ).limit(10).all()
                context['target_ids'] = [rel.target_id for rel in target_rels]
                
                # Get mechanisms for this drug
                mechanism_rels = self.session.query(DrugMechanism.mechanism_id).filter(
                    DrugMechanism.drug_id == entity_id
                ).limit(10).all()
                context['mechanism_ids'] = [rel.mechanism_id for rel in mechanism_rels]
                
                # Get trials testing this drug
                trial_rels = self.session.query(TrialDrug.trial_id).filter(
                    TrialDrug.drug_id == entity_id
                ).limit(20).all()
                context['trial_ids'] = [rel.trial_id for rel in trial_rels]
            
            # Disease context
            elif model_name == 'Disease':
                # Get drugs indicated for this disease
                drug_rels = self.session.query(DrugIndication.drug_id).filter(
                    DrugIndication.disease_id == entity_id
                ).limit(20).all()
                context['drug_ids'] = [rel.drug_id for rel in drug_rels]
                
                # Get trials studying this disease
                trial_rels = self.session.query(TrialDisease.trial_id).filter(
                    TrialDisease.disease_id == entity_id
                ).limit(20).all()
                context['trial_ids'] = [rel.trial_id for rel in trial_rels]
            
            # Clinical Trial context
            elif model_name == 'ClinicalTrial':
                # Get sponsors for this trial
                sponsor_rels = self.session.query(
                    TrialSponsor.entity_id,
                    TrialSponsor.entity_type
                ).filter(
                    TrialSponsor.trial_id == entity_id
                ).limit(10).all()
                
                for rel in sponsor_rels:
                    if rel.entity_type == 'company':
                        context['company_ids'].append(rel.entity_id)
                
                # Get drugs tested in this trial
                drug_rels = self.session.query(TrialDrug.drug_id).filter(
                    TrialDrug.trial_id == entity_id
                ).limit(10).all()
                context['drug_ids'] = [rel.drug_id for rel in drug_rels]
                
                # Get diseases studied in this trial
                disease_rels = self.session.query(TrialDisease.disease_id).filter(
                    TrialDisease.disease_id == entity_id
                ).limit(10).all()
                context['disease_ids'] = [rel.disease_id for rel in disease_rels]
            
            # Target context
            elif model_name == 'Target':
                # Get drugs targeting this target
                drug_rels = self.session.query(DrugTarget.drug_id).filter(
                    DrugTarget.target_id == entity_id
                ).limit(20).all()
                context['drug_ids'] = [rel.drug_id for rel in drug_rels]
            
            # Institution context (similar to company)
            elif model_name == 'Institution':
                # Get trials sponsored by this institution
                trial_rels = self.session.query(TrialSponsor.trial_id).filter(
                    and_(
                        TrialSponsor.entity_id == entity_id,
                        TrialSponsor.entity_type == 'institution'
                    )
                ).limit(20).all()
                context['trial_ids'] = [rel.trial_id for rel in trial_rels]
            
        except Exception as e:
            # If context extraction fails, log but don't fail matching
            logger.warning(f"Error extracting context for {model_name} {entity_id}: {e}")
        
        return context
    
    @staticmethod
    def _get_id_field_name(model) -> str:
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
            'Mechanism': 'mechanism_id',
        }
        return id_fields.get(model.__name__, 'id')
    
    def _make_cache_key(self, entity: ExtractedEntity) -> Optional[tuple]:
        """
        Create a cache key from entity identifiers.
        
        Uses primary identifier fields in priority order. Only creates cache key
        if entity has at least one identifier field populated.
        
        IMPORTANT: Cache keys must be consistent for the same entity across
        multiple calls. This method ensures consistency by:
        - Using identifier fields in priority order (first match wins)
        - Normalizing identifier values (strip whitespace)
        - Using same normalization for name fallback
        
        Args:
            entity: ExtractedEntity to create cache key for
            
        Returns:
            Cache key tuple (entity_type, identifier_field, identifier_value) or None
        """
        identifier_fields = self.IDENTIFIER_FIELDS.get(entity.entity_type, [])
        
        # Try each identifier field in priority order
        # This ensures consistent key generation: same entity with same identifier
        # will always produce the same cache key, regardless of other fields
        for field in identifier_fields:
            if field in entity.identifiers and entity.identifiers[field]:
                # Normalize value: convert to string and strip whitespace
                # This ensures "NCT12345678" and "NCT12345678 " produce same key
                value = str(entity.identifiers[field]).strip()
                if value:  # Ensure non-empty
                    return (entity.entity_type.value, field, value)
        
        # Fallback: use normalized name if no identifiers available
        # This is less reliable but allows caching entities without identifiers
        # Uses same normalization as scorer to ensure consistency
        normalized_name = self.scorer._normalize_text(entity.name)
        if normalized_name:
            return (entity.entity_type.value, 'name', normalized_name)
        
        return None
    
    def _lookup_in_memory_cache(self, entity: ExtractedEntity) -> Optional[tuple]:
        """
        Look up entity in memory cache.
        
        Checks cache using identifier-based keys. Returns cached resolution metadata if found.
        
        Args:
            entity: ExtractedEntity to look up
            
        Returns:
            Tuple of (entity_id, match_method, confidence_score, status, reasoning) if found,
            or None if not found
        """
        cache_key = self._make_cache_key(entity)
        if cache_key:
            result = self._memory_cache.get(cache_key)
            if result:
                logger.debug(f"Cache HIT: {cache_key} -> {result[0]} (method: {result[1].value if result[1] else 'N/A'}) for {entity.entity_type.value} '{entity.name}'")
            else:
                logger.debug(f"Cache MISS: {cache_key} for {entity.entity_type.value} '{entity.name}'")
            return result
        logger.debug(f"Cache SKIP: No cache key generated for {entity.entity_type.value} '{entity.name}'")
        return None
    
    def _register_in_cache(self, entity: ExtractedEntity, resolution: ResolutionResult) -> None:
        """
        Register a resolved entity in the memory cache with resolution metadata.
        
        Only caches high-confidence resolutions (EXACT_MATCH or HIGH_CONFIDENCE).
        Stores metadata (match_method, confidence_score, status, reasoning) to preserve
        the original resolution method for audit trails and logging.
        
        Args:
            entity: ExtractedEntity that was resolved
            resolution: ResolutionResult containing entity_id and resolution metadata
        """
        if not resolution.entity_id:
            return
        
        cache_key = self._make_cache_key(entity)
        if cache_key:
            # Store entity_id with resolution metadata
            cache_entry = (
                resolution.entity_id,
                resolution.match_method,
                resolution.confidence_score,
                resolution.status,
                resolution.reasoning
            )
            self._memory_cache[cache_key] = cache_entry
            # Store in reverse cache for deduplication
            self._id_to_cache_key[resolution.entity_id] = cache_key
            logger.debug(
                f"Cached {entity.entity_type.value} {entity.name} -> {resolution.entity_id} "
                f"(method: {resolution.match_method.value if resolution.match_method else 'N/A'})"
            )
    
    def register_entity(self, entity: ExtractedEntity, entity_id: UUID) -> None:
        """
        Public method to register an entity in the cache.
        
        Used by pipeline after entity creation or resolution to ensure
        entities are available for subsequent lookups in the same run.
        
        For newly created entities, uses default metadata (EXACT_MATCH, confidence 1.0).
        For resolved entities, use _register_in_cache() with full ResolutionResult instead.
        
        Args:
            entity: ExtractedEntity that was resolved/created
            entity_id: UUID of the entity
        """
        # Create a default ResolutionResult for newly created entities
        # (entities created in pipeline don't have a resolution result)
        default_result = ResolutionResult(
            status=ResolutionStatus.EXACT_MATCH,
            entity_id=entity_id,
            confidence_score=1.0,
            match_method=MatchMethod.EXACT_IDENTIFIER,
            reasoning="Newly created entity registered in cache"
        )
        self._register_in_cache(entity, default_result)

