"""
Data types for SEC filings ingestion.

This module provides structured data types for SEC documents,
sections, and extracted information with proper validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Dict, Any, Union
from enum import Enum


class FormType(Enum):
    """SEC form types."""
    FORM_8K = "8-K"
    FORM_10K = "10-K"
    FORM_10Q = "10-Q"
    FORM_20F = "20-F"
    FORM_6K = "6-K"
    FORM_424B = "424B"
    FORM_S1 = "S-1"
    FORM_S3 = "S-3"
    FORM_8A12B = "8-A12B"
    FORM_8A12G = "8-A12G"


class SectionConfidence(Enum):
    """Confidence level for extracted sections."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ContentHash:
    """Content hash for change detection."""
    
    def __init__(self, content: str, algorithm: str = "sha256"):
        self.algorithm = algorithm
        self.hash_value = self._compute_hash(content)
        self.content_length = len(content)
        self.computed_at = datetime.utcnow()
    
    def _compute_hash(self, content: str) -> str:
        """Compute hash of content."""
        import hashlib
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ContentHash):
            return False
        return self.hash_value == other.hash_value
    
    def __hash__(self) -> int:
        return hash(self.hash_value)


@dataclass
class FilingMetadata:
    """Metadata for an SEC filing."""
    cik: int
    accession: str
    form_type: str
    filing_date: date
    company_name: str
    description: str
    url: str
    
    # Additional metadata
    file_size: Optional[int] = None
    document_count: Optional[int] = None
    primary_document: Optional[str] = None
    
    # Parsing metadata
    parsed_at: Optional[datetime] = None
    parse_success: Optional[bool] = None
    parse_errors: List[str] = field(default_factory=list)


@dataclass
class DocumentSection:
    """A section extracted from an SEC document."""
    title: str
    content: str
    content_hash: str
    start_offset: int
    end_offset: int
    confidence: str = "MEDIUM"
    
    # Additional metadata
    section_type: Optional[str] = None
    item_number: Optional[str] = None
    subsection: Optional[str] = None
    
    # Parsing metadata
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    extraction_method: str = "unknown"
    
    # Content analysis
    word_count: int = field(init=False)
    has_tables: bool = field(init=False)
    has_numbers: bool = field(init=False)
    
    def __post_init__(self):
        """Compute derived fields."""
        self.word_count = len(self.content.split())
        self.has_tables = '<table' in self.content.lower() or '|' in self.content
        self.has_numbers = any(char.isdigit() for char in self.content)


@dataclass
class FilingDocument:
    """Complete SEC filing document with parsed sections."""
    metadata: FilingMetadata
    content: str
    content_hash: str
    sections: List[DocumentSection]
    extracted_at: datetime
    
    # Document analysis
    total_sections: int = field(init=False)
    total_words: int = field(init=False)
    section_confidence_distribution: Dict[str, int] = field(init=False)
    
    # Processing metadata
    processing_time_seconds: Optional[float] = None
    extraction_errors: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Compute derived fields."""
        self.total_sections = len(self.sections)
        self.total_words = sum(s.word_count for s in self.sections)
        
        # Count sections by confidence
        self.section_confidence_distribution = {}
        for section in self.sections:
            conf = section.confidence
            self.section_confidence_distribution[conf] = self.section_confidence_distribution.get(conf, 0) + 1
    
    def get_section_by_title(self, title: str) -> Optional[DocumentSection]:
        """Get section by title (case-insensitive)."""
        for section in self.sections:
            if section.title.lower() == title.lower():
                return section
        return None
    
    def get_sections_by_confidence(self, confidence: str) -> List[DocumentSection]:
        """Get sections by confidence level."""
        return [s for s in self.sections if s.confidence == confidence]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'metadata': {
                'cik': self.metadata.cik,
                'accession': self.metadata.accession,
                'form_type': self.metadata.form_type,
                'filing_date': self.metadata.filing_date.isoformat(),
                'company_name': self.metadata.company_name,
                'description': self.metadata.description,
                'url': self.metadata.url,
                'file_size': self.metadata.file_size,
                'document_count': self.metadata.document_count,
                'primary_document': self.metadata.primary_document,
                'parsed_at': self.metadata.parsed_at.isoformat() if self.metadata.parsed_at else None,
                'parse_success': self.metadata.parse_success,
                'parse_errors': self.metadata.parse_errors
            },
            'content_hash': self.content_hash,
            'sections': [
                {
                    'title': s.title,
                    'content': s.content,
                    'content_hash': s.content_hash,
                    'start_offset': s.start_offset,
                    'end_offset': s.end_offset,
                    'confidence': s.confidence,
                    'section_type': s.section_type,
                    'item_number': s.item_number,
                    'subsection': s.subsection,
                    'extracted_at': s.extracted_at.isoformat(),
                    'extraction_method': s.extraction_method,
                    'word_count': s.word_count,
                    'has_tables': s.has_tables,
                    'has_numbers': s.has_numbers
                }
                for s in self.sections
            ],
            'extracted_at': self.extracted_at.isoformat(),
            'total_sections': self.total_sections,
            'total_words': self.total_words,
            'section_confidence_distribution': self.section_confidence_distribution,
            'processing_time_seconds': self.processing_time_seconds,
            'extraction_errors': self.extraction_errors
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FilingDocument:
        """Create FilingDocument from dictionary."""
        # Reconstruct metadata
        metadata = FilingMetadata(
            cik=data['metadata']['cik'],
            accession=data['metadata']['accession'],
            form_type=data['metadata']['form_type'],
            filing_date=datetime.fromisoformat(data['metadata']['filing_date']).date(),
            company_name=data['metadata']['company_name'],
            description=data['metadata']['description'],
            url=data['metadata']['url'],
            file_size=data['metadata']['file_size'],
            document_count=data['metadata']['document_count'],
            primary_document=data['metadata']['primary_document'],
            parsed_at=datetime.fromisoformat(data['metadata']['parsed_at']) if data['metadata']['parsed_at'] else None,
            parse_success=data['metadata']['parse_success'],
            parse_errors=data['metadata']['parse_errors']
        )
        
        # Reconstruct sections
        sections = []
        for s_data in data['sections']:
            section = DocumentSection(
                title=s_data['title'],
                content=s_data['content'],
                content_hash=s_data['content_hash'],
                start_offset=s_data['start_offset'],
                end_offset=s_data['end_offset'],
                confidence=s_data['confidence'],
                section_type=s_data['section_type'],
                item_number=s_data['item_number'],
                subsection=s_data['subsection'],
                extracted_at=datetime.fromisoformat(s_data['extracted_at']),
                extraction_method=s_data['extraction_method']
            )
            # Set computed fields
            section.word_count = s_data['word_count']
            section.has_tables = s_data['has_tables']
            section.has_numbers = s_data['has_numbers']
            sections.append(section)
        
        # Create document
        doc = cls(
            metadata=metadata,
            content="",  # Don't store full content in cache
            content_hash=data['content_hash'],
            sections=sections,
            extracted_at=datetime.fromisoformat(data['extracted_at']),
            processing_time_seconds=data.get('processing_time_seconds'),
            extraction_errors=data.get('extraction_errors', [])
        )
        
        return doc


@dataclass
class EightKItem:
    """Extracted 8-K item information."""
    item_number: str
    title: str
    content: str
    content_hash: str
    
    # Trial-related information
    trial_events: List[str] = field(default_factory=list)
    endpoints_mentioned: List[str] = field(default_factory=list)
    safety_signals: List[str] = field(default_factory=list)
    program_changes: List[str] = field(default_factory=list)
    
    # Extraction metadata
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    extraction_method: str = "unknown"
    confidence: float = 0.0
    
    # Evidence spans
    evidence_spans: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TenKSection:
    """Extracted 10-K section information."""
    section_name: str
    content: str
    content_hash: str
    
    # Business information
    clinical_development: List[str] = field(default_factory=list)
    regulatory_updates: List[str] = field(default_factory=list)
    pipeline_changes: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    
    # Extraction metadata
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    extraction_method: str = "unknown"
    confidence: float = 0.0
    
    # Evidence spans
    evidence_spans: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Result of information extraction from SEC documents."""
    filing_id: str
    extraction_type: str  # "8k_trial_events", "10k_clinical", etc.
    
    # Extracted information
    extracted_items: List[Union[EightKItem, TenKSection]] = field(default_factory=list)
    
    # Quality metrics
    total_items: int = 0
    high_confidence_items: int = 0
    medium_confidence_items: int = 0
    low_confidence_items: int = 0
    
    # Processing metadata
    processing_time_seconds: float = 0.0
    extraction_errors: List[str] = field(default_factory=list)
    extraction_warnings: List[str] = field(default_factory=list)
    
    # Validation results
    validation_passed: bool = False
    validation_errors: List[str] = field(default_factory=list)
    
    extracted_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Compute derived fields."""
        self.total_items = len(self.extracted_items)
        
        # Count by confidence
        for item in self.extracted_items:
            if hasattr(item, 'confidence'):
                if item.confidence >= 0.8:
                    self.high_confidence_items += 1
                elif item.confidence >= 0.5:
                    self.medium_confidence_items += 1
                else:
                    self.low_confidence_items += 1


@dataclass
class SecIngestionResult:
    """Result of SEC ingestion operation."""
    success: bool
    company_cik: int
    filings_processed: int = 0
    filings_successful: int = 0
    filings_failed: int = 0
    
    # Content metrics
    total_sections_extracted: int = 0
    total_words_processed: int = 0
    
    # Quality metrics
    average_section_confidence: float = 0.0
    high_confidence_sections: int = 0
    
    # Processing metadata
    processing_time_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Change detection
    new_filings: int = 0
    updated_filings: int = 0
    unchanged_filings: int = 0
    
    completed_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Compute derived fields."""
        if self.filings_processed > 0:
            self.filings_successful = self.filings_processed - self.filings_failed
