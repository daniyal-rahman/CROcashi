"""
USPTO patent data types and models.

Data structures for handling USPTO patent grants, assignments, and related data.
Follows the same patterns as SEC data types in the codebase.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Any, Literal
from decimal import Decimal


@dataclass
class PatentRecord:
    """Represents a US patent record from USPTO data."""
    
    # Core patent identification
    patent_number: str  # e.g., "US10123456B2"
    patent_id: str  # USPTO internal ID
    application_number: str  # e.g., "16/123456"
    
    # Dates
    application_date: Optional[date] = None
    grant_date: Optional[date] = None
    publication_date: Optional[date] = None
    priority_date: Optional[date] = None
    
    # Patent content
    title: Optional[str] = None
    abstract: Optional[str] = None
    claims: List[str] = field(default_factory=list)
    description: Optional[str] = None
    
    # Classification
    cpc_classes: List[str] = field(default_factory=list)  # Cooperative Patent Classification
    uspc_classes: List[str] = field(default_factory=list)  # US Patent Classification
    
    # People and entities
    inventors: List[str] = field(default_factory=list)
    assignees: List[str] = field(default_factory=list)  # Current assignees
    applicants: List[str] = field(default_factory=list)  # Original applicants
    
    # Status and metadata
    patent_status: Optional[str] = None  # "granted", "expired", "abandoned"
    patent_type: str = "utility"  # "utility", "design", "plant"
    
    # References
    cited_patents: List[str] = field(default_factory=list)
    citing_patents: List[str] = field(default_factory=list)
    non_patent_references: List[str] = field(default_factory=list)
    
    # Family information
    family_id: Optional[str] = None
    continuation_data: Dict[str, Any] = field(default_factory=dict)
    
    # Ingestion metadata
    source_url: Optional[str] = None
    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    content_hash: Optional[str] = None
    
    def __post_init__(self):
        """Compute content hash after initialization."""
        if not self.content_hash:
            content = f"{self.patent_number}_{self.title}_{self.abstract}"
            self.content_hash = hashlib.md5(content.encode()).hexdigest()
    
    @property
    def is_pharmaceutical(self) -> bool:
        """Check if patent is likely pharmaceutical based on classification."""
        pharma_classes = ['A61K', 'A61P', 'C07D', 'C07C', 'C07H']
        return any(cpc.startswith(cls) for cls in pharma_classes for cpc in self.cpc_classes)


@dataclass 
class AssignmentRecord:
    """Represents a USPTO patent assignment record."""
    
    # Assignment identification
    assignment_id: str  # USPTO assignment ID
    reel_frame: Optional[str] = None  # Reel/Frame number
    
    # Patent information
    patent_numbers: List[str] = field(default_factory=list)
    application_numbers: List[str] = field(default_factory=list)
    
    # Parties
    assignor: str = ""  # Who is transferring
    assignee: str = ""  # Who is receiving
    
    # Assignment details
    assignment_type: str = ""  # "assignment", "license", "security agreement"
    execution_date: Optional[date] = None
    recorded_date: Optional[date] = None
    
    # Financial information
    consideration_amount: Optional[Decimal] = None
    consideration_type: Optional[str] = None  # "monetary", "equity", "licensing"
    
    # Document details
    assignment_text: Optional[str] = None
    document_pages: int = 0
    
    # Cross-references
    sec_exhibit_reference: Optional[str] = None  # Reference to SEC filing
    
    # Metadata
    source_url: Optional[str] = None
    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    parsed_metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_acquisition(self) -> bool:
        """Check if assignment represents full acquisition."""
        return self.assignment_type.lower() in ['assignment', 'acquisition', 'sale']
    
    @property
    def is_licensing(self) -> bool:
        """Check if assignment represents licensing."""
        return 'license' in self.assignment_type.lower()


@dataclass
class PatentFamily:
    """Represents a patent family (US-focused)."""
    
    family_id: str
    family_type: str = "simple"  # "simple", "continuation", "divisional"
    
    # Member patents
    us_patents: List[str] = field(default_factory=list)
    priority_patent: Optional[str] = None
    
    # Dates
    earliest_priority_date: Optional[date] = None
    latest_grant_date: Optional[date] = None
    
    # Metadata
    patent_count: int = 0
    active_patents: int = 0
    
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OwnershipEvent:
    """Represents an ownership change event for an asset."""
    
    # Event identification
    event_id: str
    asset_id: int
    
    # Ownership details
    from_company_id: Optional[int] = None
    to_company_id: Optional[int] = None
    ownership_type: str = ""  # "assignee", "licensee", "co_owner"
    ownership_percentage: Optional[Decimal] = None
    
    # Event details
    event_date: date
    event_type: str = ""  # "patent_assignment", "sec_filing", "press_release"
    
    # Evidence
    evidence_source: str = ""
    evidence_url: Optional[str] = None
    confidence_score: Decimal = Decimal("0.0")
    
    # Additional metadata
    consideration_amount: Optional[Decimal] = None
    description: Optional[str] = None
    
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PatentSearchQuery:
    """Query parameters for USPTO patent search."""
    
    # Search terms
    assignee: Optional[str] = None
    inventor: Optional[str] = None
    title_keywords: List[str] = field(default_factory=list)
    abstract_keywords: List[str] = field(default_factory=list)
    
    # Date ranges
    application_date_start: Optional[date] = None
    application_date_end: Optional[date] = None
    grant_date_start: Optional[date] = None
    grant_date_end: Optional[date] = None
    
    # Classification
    cpc_classes: List[str] = field(default_factory=list)
    
    # Limits
    max_results: int = 1000
    pharmaceutical_only: bool = False
    
    def to_uspto_query(self) -> str:
        """Convert to USPTO API query string."""
        query_parts = []
        
        if self.assignee:
            query_parts.append(f'assignee:"{self.assignee}"')
        
        if self.inventor:
            query_parts.append(f'inventor:"{self.inventor}"')
            
        if self.title_keywords:
            title_query = " OR ".join(f'title:"{kw}"' for kw in self.title_keywords)
            query_parts.append(f"({title_query})")
            
        if self.cpc_classes:
            cpc_query = " OR ".join(f'cpc:"{cls}"' for cls in self.cpc_classes)
            query_parts.append(f"({cpc_query})")
            
        if self.application_date_start:
            query_parts.append(f'appdate:>={self.application_date_start.strftime("%Y-%m-%d")}')
            
        if self.application_date_end:
            query_parts.append(f'appdate:<={self.application_date_end.strftime("%Y-%m-%d")}')
            
        return " AND ".join(query_parts)


@dataclass
class IngestionResult:
    """Result of USPTO data ingestion operation."""
    
    # Counts
    patents_processed: int = 0
    patents_successful: int = 0
    patents_failed: int = 0
    
    assignments_processed: int = 0
    assignments_successful: int = 0
    assignments_failed: int = 0
    
    # Asset linking
    assets_linked: int = 0
    new_ownership_events: int = 0
    
    # Timing
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: Optional[datetime] = None
    processing_time_seconds: Optional[float] = None
    
    # Results
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Metadata
    run_id: Optional[str] = None
    config_used: Dict[str, Any] = field(default_factory=dict)
    
    def finalize(self):
        """Finalize the result by computing timing."""
        self.end_time = datetime.now(UTC)
        if self.start_time:
            self.processing_time_seconds = (self.end_time - self.start_time).total_seconds()
    
    @property
    def success_rate(self) -> float:
        """Calculate overall success rate."""
        total_processed = self.patents_processed + self.assignments_processed
        total_successful = self.patents_successful + self.assignments_successful
        
        if total_processed == 0:
            return 0.0
        
        return total_successful / total_processed


@dataclass
class PatentLinkCandidate:
    """Candidate for linking a patent to an asset."""
    
    patent_id: int
    asset_id: int
    
    # Linking evidence
    link_method: Literal['inn_exact', 'code_mention', 'text_similarity', 'assignee_temporal', 'manual']
    confidence_score: float
    
    # Evidence details
    evidence_spans: List[Dict[str, Any]] = field(default_factory=list)
    match_text: Optional[str] = None
    similarity_score: Optional[float] = None
    
    # Temporal alignment
    patent_date: Optional[date] = None
    asset_first_mention: Optional[date] = None
    temporal_distance_days: Optional[int] = None
    
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    
    @property
    def is_high_confidence(self) -> bool:
        """Check if this is a high-confidence link."""
        return self.confidence_score >= 0.85
    
    @property
    def is_temporal_match(self) -> bool:
        """Check if patent and asset dates align reasonably."""
        if not (self.patent_date and self.asset_first_mention):
            return False
        
        # Allow patents to be filed up to 2 years before or after asset first mention
        days_diff = abs((self.patent_date - self.asset_first_mention).days)
        return days_diff <= 730  # 2 years


# Type aliases for common use cases
USPatentNumber = str  # e.g., "US10123456B2"
AssignmentID = str    # USPTO assignment record ID
AssetCode = str       # Internal asset code like "ABC-123"
CompanyName = str     # Company name for resolution


# Constants
USPTO_API_BASE = "https://developer.uspto.gov/ptab-api/v1"
USPTO_BULK_DATA_BASE = "https://bulkdata.uspto.gov"
USPTO_ASSIGNMENT_BASE = "https://assignment.uspto.gov"

# Patent classification codes for pharmaceuticals
PHARMACEUTICAL_CPC_CLASSES = [
    'A61K',  # Preparations for medical, dental, or toilet purposes
    'A61P',  # Therapeutic activity of chemical compounds
    'C07D',  # Heterocyclic compounds
    'C07C',  # Acyclic or carbocyclic compounds
    'C07H',  # Sugars; derivatives thereof; nucleosides; nucleotides
    'C07J',  # Steroids
    'C12N',  # Microorganisms or enzymes; compositions thereof
    'G01N',  # Investigating or analyzing materials (for drug testing)
]

# Common assignment types
ASSIGNMENT_TYPES = {
    'assignment': 'Full ownership transfer',
    'license': 'Licensing agreement', 
    'security_agreement': 'Patent as collateral',
    'merger': 'Corporate merger/acquisition',
    'court_order': 'Court-ordered transfer',
    'inheritance': 'Transfer by inheritance',
    'government_interest': 'Government rights statement'
}

# Evidence source types for ownership events
EVIDENCE_SOURCE_TYPES = {
    'patent_assignment': 'USPTO assignment record',
    'sec_filing': 'SEC filing (8-K, 10-K, 10-Q)',
    'press_release': 'Company press release',
    'clinical_trial': 'Clinical trial sponsor change',
    'manual': 'Manual entry/research'
}
