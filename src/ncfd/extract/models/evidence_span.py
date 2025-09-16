# src/ncfd/extract/models/evidence_span.py
"""
EvidenceSpan Model

Represents a span of text extracted from a document with provenance tracking.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
import uuid


@dataclass
class Span:
    """A span of text extracted from a document."""
    
    # Document identification
    doc_id: str  # e.g., "pmc:PMC2978916"
    
    # Content
    quote: str  # The actual text content (≤400 chars)
    section: str  # Methods, Results, Table, Figure, Protocol, SAP
    
    # Location information
    page: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    
    # Quality and confidence
    confidence: float = 0.8  # OCR/parse quality (0.0-1.0)
    
    # Additional metadata
    table_id: Optional[str] = None  # For table spans
    table_row: Optional[int] = None  # Row position in table (0-indexed)
    table_col: Optional[int] = None  # Column position in table (0-indexed)
    table_header_ids: List[str] = field(default_factory=list)  # Header span IDs for context
    figure_id: Optional[str] = None  # For figure spans
    supplementary_id: Optional[str] = None  # For supplementary material
    
    # Span type and provenance
    kind: Literal["base", "derived"] = "base"  # Distinguishes base vs derived spans
    parent_span_ids: List[str] = field(default_factory=list)  # For derived spans, stores base parent IDs
    
    # Provenance fields
    internal_id: str = field(default_factory=lambda: f"span_{str(uuid.uuid4())[:8]}")
    status: str = "draft"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    version: int = 1
    input_hash: str = field(default_factory=lambda: f"{uuid.uuid4().hex[:16]}")
    span_ids: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize provenance fields and validate."""
        # Set span_ids to include self-reference
        if not self.span_ids:
            self.span_ids = [self.span_id]
        
        # Validate quote length
        if len(self.quote) > 1000:  # Increased from 400 to 1000 to allow longer quotes
            raise ValueError(f"Quote too long: {len(self.quote)} chars (max 1000)")
        
        # Validate confidence range
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
        
        # Validate kind-specific constraints
        if self.kind == "derived" and not self.parent_span_ids:
            raise ValueError("Derived spans must have parent_span_ids")
        elif self.kind == "base" and self.parent_span_ids:
            raise ValueError("Base spans should not have parent_span_ids")
        
        # Validate table-specific constraints
        if self.section.lower() == "table" and self.table_id:
            if self.table_row is None or self.table_col is None:
                raise ValueError("Table spans must have table_row and table_col specified")
    
    @property
    def span_id(self) -> str:
        """Generate span_id based on document and location.
        
        Follows the specification format: {doc_id}#sec:{section}:char{start}-{end}
        with optional page context for additional precision.
        For tables: {doc_id}#table:{table_id}:r{row}c{col}
        """
        if self.section.lower() == "table" and self.table_id:
            if self.table_row is not None and self.table_col is not None:
                return f"{self.doc_id}#table:{self.table_id}:r{self.table_row}c{self.table_col}"
            else:
                # Fallback for table spans without row/col info
                return f"{self.doc_id}#table:{self.table_id}:r*"
        elif self.section.lower() == "figure" and self.figure_id:
            return f"{self.doc_id}#fig:{self.figure_id}"
        elif self.char_start is not None and self.char_end is not None:
            # Primary format: section-based with character positions
            base_id = f"{self.doc_id}#sec:{self.section}:char{self.char_start}-{self.char_end}"
            
            # Add page context if available for additional precision
            if self.page is not None:
                base_id += f":p{self.page}"
            
            return base_id
        else:
            # Fallback to generic format
            return f"{self.doc_id}#sec:{self.section}:unknown"
    
    @property
    def length(self) -> int:
        """Get the length of the span in characters."""
        if self.char_start is not None and self.char_end is not None:
            return self.char_end - self.char_start
        return len(self.quote)
    
    @property
    def is_table_span(self) -> bool:
        """Check if this is a table span."""
        return self.section.lower() == "table" and self.table_id is not None
    
    @property
    def is_table_cell_span(self) -> bool:
        """Check if this is a table cell span with precise row/column addressing."""
        return self.is_table_span and self.table_row is not None and self.table_col is not None
    
    @property
    def is_base_span(self) -> bool:
        """Check if this is a base span."""
        return self.kind == "base"
    
    @property
    def is_derived_span(self) -> bool:
        """Check if this is a derived span."""
        return self.kind == "derived"
    
    @property
    def has_parents(self) -> bool:
        """Check if this span has parent spans."""
        return len(self.parent_span_ids) > 0
    
    @property
    def has_table_headers(self) -> bool:
        """Check if this table span has header context."""
        return len(self.table_header_ids) > 0
    
    @property
    def is_figure_span(self) -> bool:
        """Check if this is a figure span."""
        return self.section.lower() == "figure" and self.figure_id is not None
    
    def overlaps_with(self, other: 'Span') -> bool:
        """Check if this span overlaps with another span."""
        if self.doc_id != other.doc_id or self.page != other.page:
            return False
        
        if self.char_start is None or self.char_end is None or other.char_start is None or other.char_end is None:
            return False
        
        return not (self.char_end <= other.char_start or other.char_end <= self.char_start)
    
    def get_overlap_ratio(self, other: 'Span') -> float:
        """Calculate the overlap ratio with another span."""
        if not self.overlaps_with(other):
            return 0.0
        
        if self.char_start is None or self.char_end is None or other.char_start is None or other.char_end is None:
            return 0.0
        
        overlap_start = max(self.char_start, other.char_start)
        overlap_end = min(self.char_end, other.char_end)
        overlap_length = overlap_end - overlap_start
        
        union_start = min(self.char_start, other.char_start)
        union_end = max(self.char_end, other.char_end)
        union_length = union_end - union_start
        
        return overlap_length / union_length if union_length > 0 else 0.0
    
    def is_duplicate_of(self, other: 'EvidenceSpan', threshold: float = 0.8) -> bool:
        """Check if this span is a duplicate of another span."""
        if self.doc_id != other.doc_id:
            return False
        
        # Check text similarity
        if self.quote == other.quote:
            return True
        
        # Check overlap ratio
        overlap_ratio = self.get_overlap_ratio(other)
        return overlap_ratio >= threshold
    
    def to_dict(self) -> dict:
        """Convert to dictionary with proper span_id."""
        data = asdict(self)
        # Ensure span_id is included
        data['span_id'] = self.span_id
        return data
    
    def validate(self) -> bool:
        """Validate the EvidenceSpan."""
        if not self.doc_id or not self.quote or not self.section:
            return False
        if self.confidence < 0.0 or self.confidence > 1.0:
            return False
        if len(self.quote) > 400:
            return False
        return True
