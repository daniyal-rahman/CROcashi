"""
Type definitions and data structures for entity resolution.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID


class EntityType(str, Enum):
    """Entity types supported by the resolution system."""
    COMPANY = "company"
    INSTITUTION = "institution"
    DRUG = "drug"
    DISEASE = "disease"
    TARGET = "target"
    MECHANISM = "mechanism"
    TRIAL = "trial"
    PUBLICATION = "publication"
    PATENT = "patent"
    REGULATORY_EVENT = "regulatory_event"


class MatchMethod(str, Enum):
    """Methods used for entity matching."""
    EXACT_IDENTIFIER = "exact_identifier"
    EXACT_NAME = "exact_name"
    ALIAS = "alias"
    FUZZY_CONTEXT = "fuzzy_context"
    FUZZY_ALONE = "fuzzy_alone"
    MANUAL = "manual"
    NO_MATCH = "no_match"


class ResolutionStatus(str, Enum):
    """Status of entity resolution."""
    EXACT_MATCH = "exact_match"
    HIGH_CONFIDENCE = "high_confidence"
    LOW_CONFIDENCE = "low_confidence"
    NEEDS_REVIEW = "needs_review"
    NO_MATCH = "no_match"


@dataclass
class ExtractedEntity:
    """
    An entity extracted from a source data record.
    
    Attributes:
        entity_type: Type of entity (company, drug, etc.)
        name: Primary name/text of the entity
        identifiers: Dict of external identifiers (e.g., {'ticker': 'MRNA', 'cik': '1682852'})
        context: Additional context for matching (e.g., associated companies, dates)
        source_name: Name of the data source
        source_identifier: Unique identifier in source (e.g., NCT number, PMID)
        raw_data: Original raw data for reference
    """
    entity_type: EntityType
    name: str
    identifiers: Dict[str, str] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    source_name: str = ""
    source_identifier: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchCandidate:
    """
    A potential match for an extracted entity.
    
    Attributes:
        entity_id: UUID of the candidate entity in the database
        entity_name: Name of the candidate entity
        confidence_score: Match confidence (0.0 to 1.0)
        match_reasons: List of reasons why this is a potential match
        entity_data: Additional data about the candidate entity
    """
    entity_id: UUID
    entity_name: str
    confidence_score: float
    match_reasons: List[str] = field(default_factory=list)
    entity_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchingContext:
    """
    Context information to boost matching confidence.
    
    Attributes:
        company_ids: Associated company IDs
        disease_ids: Associated disease IDs
        drug_ids: Associated drug IDs
        target_ids: Associated target IDs
        date_range: Time period (start, end)
        additional_context: Any other contextual information
    """
    company_ids: List[UUID] = field(default_factory=list)
    disease_ids: List[UUID] = field(default_factory=list)
    drug_ids: List[UUID] = field(default_factory=list)
    target_ids: List[UUID] = field(default_factory=list)
    date_range: Optional[tuple[datetime, datetime]] = None
    additional_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolutionResult:
    """
    Result of entity resolution attempt.
    
    Attributes:
        status: Resolution status (exact_match, high_confidence, etc.)
        entity_id: UUID of matched entity (if matched)
        confidence_score: Overall confidence score (0.0 to 1.0)
        match_method: Method that succeeded in matching
        candidates: List of potential matches if ambiguous
        reasoning: Explanation of matching decision
        should_create_new: Whether to create a new entity
        metadata: Additional metadata about the resolution
    """
    status: ResolutionStatus
    entity_id: Optional[UUID] = None
    confidence_score: float = 0.0
    match_method: Optional[MatchMethod] = None
    candidates: List[MatchCandidate] = field(default_factory=list)
    reasoning: str = ""
    should_create_new: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingMetrics:
    """
    Metrics for a processing run.
    
    Attributes:
        entities_extracted: Number of entities extracted
        entities_matched: Number of entities matched to existing
        entities_created: Number of new entities created
        relationships_created: Number of relationships created
        warnings: List of warning messages
        errors: List of error messages
        start_time: Processing start time
        end_time: Processing end time
    """
    entities_extracted: int = 0
    entities_matched: int = 0
    entities_created: int = 0
    relationships_created: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        """Calculate processing duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate match success rate."""
        if self.entities_extracted == 0:
            return 0.0
        return (self.entities_matched + self.entities_created) / self.entities_extracted


@dataclass
class RelationshipExtraction:
    """
    A relationship extracted from source data.
    
    Attributes:
        relationship_type: Type of relationship (e.g., 'company_drug', 'drug_target')
        source_entity: Source entity in relationship
        target_entity: Target entity in relationship
        attributes: Additional relationship attributes
        temporal: Temporal information (start_date, end_date)
    """
    relationship_type: str
    source_entity: ExtractedEntity
    target_entity: ExtractedEntity
    attributes: Dict[str, Any] = field(default_factory=dict)
    temporal: Dict[str, Any] = field(default_factory=dict)

