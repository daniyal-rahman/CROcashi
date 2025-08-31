"""
DocumentCard Model

Represents a source document with metadata and references.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from .base import BaseModel, ProvenanceMixin


@dataclass
class DocumentCard(BaseModel, ProvenanceMixin):
    """Source document representation with metadata and fulltext references."""
    
    # Required fields
    doc_id: str = ""  # e.g., pmid:, doi:, ctgov:NCT..., pr:..., sec:8-K ...
    doc_type: str = ""  # PR, Abstract, Paper, Registry, FDA
    title: str = ""
    year: int = 0
    
    # Optional fields
    venue: Optional[str] = None
    study_type: Optional[str] = None
    disease: Optional[str] = None
    intervention: Optional[str] = None
    route: Optional[str] = None
    dose_units: Optional[str] = None
    region: Optional[str] = None
    url: Optional[str] = None
    source_id: Optional[str] = None  # NCT ID, PMID, etc.
    
    # Fulltext references (page→char ranges, figure/table ids)
    fulltext_refs: List[Dict[str, Any]] = field(default_factory=list)
    
    # Concepts (MeSH/UMLS/CT.gov vocab)
    concepts: List[str] = field(default_factory=list)
    
    # Additional metadata
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    
    def __post_init__(self):
        """Initialize provenance fields."""
        ProvenanceMixin.__init__(self)
    
    def validate(self) -> bool:
        """Validate the DocumentCard."""
        if not self.doc_id or not self.title or not self.year:
            return False
        if self.year < 1900 or self.year > datetime.now().year + 1:
            return False
        return True
    
    def add_fulltext_ref(self, page: int, start_char: int, end_char: int, 
                        ref_type: str = "text", figure_id: Optional[str] = None,
                        table_id: Optional[str] = None) -> None:
        """Add a fulltext reference."""
        ref = {
            "page": page,
            "start_char": start_char,
            "end_char": end_char,
            "ref_type": ref_type,
            "figure_id": figure_id,
            "table_id": table_id
        }
        self.fulltext_refs.append(ref)
    
    def add_concept(self, concept: str) -> None:
        """Add a concept term."""
        if concept not in self.concepts:
            self.concepts.append(concept)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with all fields."""
        base_dict = super().to_dict()
        base_dict.update({
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "title": self.title,
            "year": self.year,
            "venue": self.venue,
            "study_type": self.study_type,
            "disease": self.disease,
            "intervention": self.intervention,
            "route": self.route,
            "dose_units": self.dose_units,
            "region": self.region,
            "url": self.url,
            "source_id": self.source_id,
            "fulltext_refs": self.fulltext_refs,
            "concepts": self.concepts,
            "abstract": self.abstract,
            "authors": self.authors,
            "journal": self.journal,
            "doi": self.doi,
            "pmid": self.pmid
        })
        return base_dict
