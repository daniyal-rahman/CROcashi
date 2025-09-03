"""
LLM Extraction Draft Models

Data structures for LLM-first extraction with verbatim quotes and evidence metadata.
These are draft artifacts that will be processed by the provenance backtracer.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from pydantic import field_validator
from .base import BaseModel


class EvidenceKind(Enum):
    """Enum for evidence kind (text vs table)."""
    TEXT = "text"
    TABLE = "table"
    MIXED = "mixed"


class EvidenceStatus(Enum):
    """Enum for evidence status."""
    QUOTED = "quoted"
    NO_QUOTE = "no_quote"
    UNRESOLVED = "unresolved"


@dataclass
class LLMResultsDraft(BaseModel):
    """Draft results data with verbatim quotes and evidence metadata."""
    
    # Document identifier
    doc_id: str = field(default="")
    
    # Results array with verbatim quotes
    results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Evidence metadata
    verbatim_quotes: List[str] = field(default_factory=list)
    evidence_kinds: List[EvidenceKind] = field(default_factory=list)
    section_hints: List[str] = field(default_factory=list)
    table_hints: List[Optional[str]] = field(default_factory=list)
    page_hints: List[Optional[str]] = field(default_factory=list)
    confidence_llm: List[float] = field(default_factory=list)
    evidence_status: List[EvidenceStatus] = field(default_factory=list)
    
    # Provenance tracking (to be filled by backtracer)
    span_ids: List[str] = field(default_factory=list)
    provenance_status: List[str] = field(default_factory=list)
    
    @field_validator('doc_id')
    @classmethod
    def validate_doc_id(cls, v):
        """Validate doc_id format."""
        if not v or not isinstance(v, str) or v == "":
            raise ValueError(f"Invalid doc_id format: {v}")
        return v
    
    def add_result(self, 
                   metric: str, 
                   value: Any, 
                   units: Optional[str] = None,
                   summary_statistic: Optional[str] = None,
                   verbatim_quote: str = "",
                   evidence_kind: EvidenceKind = EvidenceKind.TEXT,
                   section_hint: str = "",
                   table_hint: Optional[str] = None,
                   page_hint: Optional[str] = None,
                   confidence_llm: float = 0.8):
        """Add a result with verbatim quote and evidence metadata."""
        result = {
            'metric': metric,
            'value': value,
            'units': units,
            'summary_statistic': summary_statistic
        }
        
        self.results.append(result)
        self.verbatim_quotes.append(verbatim_quote)
        self.evidence_kinds.append(evidence_kind)
        self.section_hints.append(section_hint)
        self.table_hints.append(table_hint)
        self.page_hints.append(page_hint)
        self.confidence_llm.append(confidence_llm)
        
        # Set evidence status based on quote presence
        if verbatim_quote and len(verbatim_quote.strip()) > 0:
            self.evidence_status.append(EvidenceStatus.QUOTED)
        else:
            self.evidence_status.append(EvidenceStatus.NO_QUOTE)
            # Lower confidence if no quote
            self.confidence_llm[-1] = max(0.3, self.confidence_llm[-1] - 0.3)
        
        # Initialize provenance fields
        self.span_ids.append("")
        self.provenance_status.append("pending")


@dataclass
class LLMMethodDraft(BaseModel):
    """Draft method data with verbatim quotes and evidence metadata."""
    
    # Document identifier
    doc_id: str = field(default="")
    
    # Method fields with verbatim quotes
    field_names: List[str] = field(default_factory=list)
    normalized_values: List[Any] = field(default_factory=list)
    verbatim_quotes: List[str] = field(default_factory=list)
    evidence_kinds: List[EvidenceKind] = field(default_factory=list)
    section_hints: List[str] = field(default_factory=list)
    page_hints: List[Optional[str]] = field(default_factory=list)
    confidence_llm: List[float] = field(default_factory=list)
    evidence_status: List[EvidenceStatus] = field(default_factory=list)
    
    # Provenance tracking (to be filled by backtracer)
    span_ids: List[str] = field(default_factory=list)
    provenance_status: List[str] = field(default_factory=list)
    
    @field_validator('doc_id')
    @classmethod
    def validate_doc_id(cls, v):
        """Validate doc_id format."""
        if not v or not isinstance(v, str) or v == "":
            raise ValueError(f"Invalid doc_id format: {v}")
        return v
    
    def add_field(self,
                  field_name: str,
                  normalized_value: Any,
                  verbatim_quote: str = "",
                  evidence_kind: EvidenceKind = EvidenceKind.TEXT,
                  section_hint: str = "",
                  page_hint: Optional[str] = None,
                  confidence_llm: float = 0.8):
        """Add a method field with verbatim quote and evidence metadata."""
        self.field_names.append(field_name)
        self.normalized_values.append(normalized_value)
        self.verbatim_quotes.append(verbatim_quote)
        self.evidence_kinds.append(evidence_kind)
        self.section_hints.append(section_hint)
        self.page_hints.append(page_hint)
        self.confidence_llm.append(confidence_llm)
        
        # Set evidence status based on quote presence
        if verbatim_quote and len(verbatim_quote.strip()) > 0:
            self.evidence_status.append(EvidenceStatus.QUOTED)
        else:
            self.evidence_status.append(EvidenceStatus.NO_QUOTE)
            # Lower confidence if no quote
            self.confidence_llm[-1] = max(0.3, self.confidence_llm[-1] - 0.3)
        
        # Initialize provenance fields
        self.span_ids.append("")
        self.provenance_status.append("pending")


@dataclass
class LLMClaimDraft(BaseModel):
    """Draft claim data with verbatim quotes and evidence metadata."""
    
    # Document identifier
    doc_id: str = field(default="")
    
    # Claim data with verbatim quotes
    claim_types: List[str] = field(default_factory=list)
    propositions: List[str] = field(default_factory=list)
    values: List[Optional[Any]] = field(default_factory=list)
    verbatim_quotes: List[str] = field(default_factory=list)
    evidence_kinds: List[EvidenceKind] = field(default_factory=list)
    section_hints: List[str] = field(default_factory=list)
    confidence_llm: List[float] = field(default_factory=list)
    evidence_status: List[EvidenceStatus] = field(default_factory=list)
    
    # Provenance tracking (to be filled by backtracer)
    span_ids: List[str] = field(default_factory=list)
    provenance_status: List[str] = field(default_factory=list)
    
    @field_validator('doc_id')
    @classmethod
    def validate_doc_id(cls, v):
        """Validate doc_id format."""
        if not v or not isinstance(v, str) or v == "":
            raise ValueError(f"Invalid doc_id format: {v}")
        return v
    
    def add_claim(self,
                  claim_type: str,
                  proposition: str,
                  value: Optional[Any] = None,
                  verbatim_quote: str = "",
                  evidence_kind: EvidenceKind = EvidenceKind.TEXT,
                  section_hint: str = "",
                  confidence_llm: float = 0.8):
        """Add a claim with verbatim quote and evidence metadata."""
        self.claim_types.append(claim_type)
        self.propositions.append(proposition)
        self.values.append(value)
        self.verbatim_quotes.append(verbatim_quote)
        self.evidence_kinds.append(evidence_kind)
        self.section_hints.append(section_hint)
        self.confidence_llm.append(confidence_llm)
        
        # Set evidence status based on quote presence
        if verbatim_quote and len(verbatim_quote.strip()) > 0:
            self.evidence_status.append(EvidenceStatus.QUOTED)
        else:
            self.evidence_status.append(EvidenceStatus.NO_QUOTE)
            # Lower confidence if no quote
            self.confidence_llm[-1] = max(0.3, self.confidence_llm[-1] - 0.3)
        
        # Initialize provenance fields
        self.span_ids.append("")
        self.provenance_status.append("pending")


@dataclass
class LLMExtractionDraft(BaseModel):
    """Complete LLM extraction draft with all artifact types."""
    
    # Document identifier
    doc_id: str = field(default="")
    
    # Draft artifacts
    results_draft: Optional[LLMResultsDraft] = None
    method_draft: Optional[LLMMethodDraft] = None
    claims_draft: Optional[LLMClaimDraft] = None
    
    # Metadata
    extraction_timestamp: float = field(default=0.0)
    llm_worker_versions: Dict[str, str] = field(default_factory=dict)
    
    @field_validator('doc_id')
    @classmethod
    def validate_doc_id(cls, v):
        """Validate doc_id format."""
        if not v or not isinstance(v, str) or v == "":
            raise ValueError(f"Invalid doc_id format: {v}")
        return v
    
    def get_all_verbatim_quotes(self) -> List[str]:
        """Get all verbatim quotes from all draft artifacts."""
        quotes = []
        
        if self.results_draft:
            quotes.extend(self.results_draft.verbatim_quotes)
        
        if self.method_draft:
            quotes.extend(self.method_draft.verbatim_quotes)
        
        if self.claims_draft:
            quotes.extend(self.claims_draft.verbatim_quotes)
        
        return quotes
    
    def get_all_evidence_statuses(self) -> List[EvidenceStatus]:
        """Get all evidence statuses from all draft artifacts."""
        statuses = []
        
        if self.results_draft:
            statuses.extend(self.results_draft.evidence_status)
        
        if self.method_draft:
            statuses.extend(self.method_draft.evidence_status)
        
        if self.claims_draft:
            statuses.extend(self.claims_draft.evidence_status)
        
        return statuses
    
    def has_unresolved_provenance(self) -> bool:
        """Check if any fields have unresolved provenance."""
        all_statuses = self.get_all_evidence_statuses()
        return EvidenceStatus.UNRESOLVED in all_statuses
