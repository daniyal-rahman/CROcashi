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
from sqlalchemy.orm import Session

from database.models import (
    Company, Drug, Disease, Target, ClinicalTrial, Publication,
    Institution, EntityAlias, EntityMatchCandidate
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
    }
    
    def __init__(self, session: Session):
        """
        Initialize entity resolver.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.scorer = ConfidenceScorer(session)
    
    def resolve(self, entity: ExtractedEntity) -> ResolutionResult:
        """
        Resolve an extracted entity using hierarchical matching.
        
        Args:
            entity: Extracted entity to resolve
            
        Returns:
            ResolutionResult with match details
        """
        logger.info(f"Resolving {entity.entity_type.value}: {entity.name}")
        
        # Level 1: Try exact identifier match
        result = self._try_exact_identifier(entity)
        if result.status == ResolutionStatus.EXACT_MATCH:
            logger.info(f"Exact identifier match found: {result.entity_id}")
            return result
        
        # Level 2: Try exact name match
        result = self._try_exact_name(entity)
        if result.status == ResolutionStatus.EXACT_MATCH:
            logger.info(f"Exact name match found: {result.entity_id}")
            return result
        
        # Level 3: Try alias lookup
        result = self._try_alias_lookup(entity)
        if result.status in (ResolutionStatus.EXACT_MATCH, ResolutionStatus.HIGH_CONFIDENCE):
            logger.info(f"Alias match found: {result.entity_id}")
            return result
        elif result.status == ResolutionStatus.NEEDS_REVIEW:
            logger.info(f"Multiple alias matches found, needs review")
            return result
        
        # Level 4: Try fuzzy match with context
        result = self._try_fuzzy_context(entity)
        if result.status == ResolutionStatus.HIGH_CONFIDENCE:
            logger.info(f"Fuzzy context match found: {result.entity_id} (score: {result.confidence_score:.2f})")
            return result
        elif result.status == ResolutionStatus.NEEDS_REVIEW:
            logger.info(f"Fuzzy context match needs review (score: {result.confidence_score:.2f})")
            return result
        
        # Level 5: Try fuzzy match alone
        result = self._try_fuzzy_alone(entity)
        if result.status == ResolutionStatus.NEEDS_REVIEW:
            logger.info(f"Fuzzy match needs review (score: {result.confidence_score:.2f})")
            return result
        
        # Level 6: No match found
        logger.info(f"No match found for {entity.name}, marking for new entity creation")
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
        
        # Use PostgreSQL similarity search
        # Get top candidates by trigram similarity
        similarity_threshold = 0.3  # Minimum base similarity to consider
        
        query_text = text(f"""
            SELECT *, similarity({name_field}, :search_name) as sim_score
            FROM {model.__tablename__}
            WHERE similarity({name_field}, :search_name) > :threshold
            ORDER BY sim_score DESC
            LIMIT 10
        """)
        
        results = self.session.execute(
            query_text,
            {"search_name": entity.name, "threshold": similarity_threshold}
        ).fetchall()
        
        if not results:
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning="No fuzzy matches above threshold"
            )
        
        # Score each candidate with context
        candidates = []
        for row in results:
            # Get entity ID (first column varies by model)
            entity_id = row[0]
            
            # Calculate score with context
            candidate_context = self._get_entity_context(model, entity_id)
            score, reasons = self.scorer.calculate_score(
                entity.name,
                str(row[self._get_name_field_index(model)]),
                entity.context,
                candidate_context
            )
            
            if score >= 0.70:  # Only include if above fuzzy threshold
                candidates.append(
                    MatchCandidate(
                        entity_id=UUID(str(entity_id)),
                        entity_name=str(row[self._get_name_field_index(model)]),
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
        
        # Use PostgreSQL similarity search with higher threshold
        similarity_threshold = 0.70  # Higher threshold for fuzzy alone
        
        query_text = text(f"""
            SELECT *, similarity({name_field}, :search_name) as sim_score
            FROM {model.__tablename__}
            WHERE similarity({name_field}, :search_name) > :threshold
            ORDER BY sim_score DESC
            LIMIT 5
        """)
        
        results = self.session.execute(
            query_text,
            {"search_name": entity.name, "threshold": similarity_threshold}
        ).fetchall()
        
        if not results:
            return ResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                reasoning="No fuzzy matches above threshold (without context)"
            )
        
        # Convert to candidates
        candidates = []
        for row in results:
            entity_id = UUID(str(row[0]))
            entity_name = str(row[self._get_name_field_index(model)])
            sim_score = float(row[-1])  # Last column is sim_score
            
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
            'target_id', 'trial_id', 'pub_id', 'patent_id'
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
        }
        return name_fields.get(model.__name__)
    
    @staticmethod
    def _get_name_field_index(model) -> int:
        """Get the index of the name field in SELECT * query."""
        # This is a simplification - in production you'd want a more robust approach
        # For now, assume name is in the first few columns after ID
        return 1
    
    def _get_entity_context(self, model, entity_id: UUID) -> Dict:
        """Get context information for an entity to boost matching."""
        # This would query relationship tables to get associated entities
        # For now, return empty dict - full implementation would join relationship tables
        return {}

