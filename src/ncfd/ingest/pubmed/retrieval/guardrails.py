"""
Guardrails system for PubMed retrieval to prevent off-topic content contamination.

This module implements the guardrails from the retrieval specification:
- Mechanism-only drift guard
- Indication gate  
- Field-coverage guard
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Literal
from ncfd.entities.schema import EntityPack

logger = logging.getLogger(__name__)


@dataclass
class GuardrailConfig:
    """Configuration for guardrails system."""
    
    # Stage-aware configuration
    stage: Literal["retrieval", "post_extract", "final"] = "retrieval"
    
    # Mechanism-only drift guard
    require_must_link_for_oncology: bool = True
    
    # Indication gate (stage-aware)
    require_indication_signal: bool = True
    
    # Field-coverage guard (stage-aware)
    require_field_coverage: bool = True
    
    # Minimum field coverage requirements (stage-aware)
    min_drug_field_coverage: bool = True  # Require drug in [tiab]
    min_nct_field_coverage: bool = False  # Require NCT in [si] (optional)
    
    # Oncology detection
    oncology_penalty_threshold: float = 0.5  # Minimum oncology score to trigger penalty
    
    @classmethod
    def for_retrieval_stage(cls) -> 'GuardrailConfig':
        """Create config appropriate for retrieval stage (lenient)."""
        return cls(
            stage="retrieval",
            require_indication_signal=False,  # Too strict for retrieval
            require_field_coverage=False,     # Too strict for retrieval
            min_drug_field_coverage=False,    # Too strict for retrieval
            min_nct_field_coverage=False
        )
    
    @classmethod
    def for_post_extract_stage(cls) -> 'GuardrailConfig':
        """Create config appropriate for post-extraction stage (strict)."""
        return cls(
            stage="post_extract",
            require_indication_signal=True,
            require_field_coverage=True,
            min_drug_field_coverage=True,
            min_nct_field_coverage=False
        )
    
    @classmethod
    def for_final_stage(cls) -> 'GuardrailConfig':
        """Create config appropriate for final filtering (very strict)."""
        return cls(
            stage="final",
            require_indication_signal=True,
            require_field_coverage=True,
            min_drug_field_coverage=True,
            min_nct_field_coverage=True
        )


@dataclass
class GuardrailOutput:
    """Result of guardrail validation."""
    
    passes_validation: bool
    guardrail_name: str
    reason: str
    details: Dict[str, Any]
    penalty_score: float = 0.0


class GuardrailsSystem:
    """
    Guardrails system to prevent off-topic content contamination.
    
    Implements three main guardrails:
    1. Mechanism-only drift guard: Reject oncology content without must-link terms
    2. Indication gate: Require Alzheimer's disease signal
    3. Field-coverage guard: Require drug in title/abstract or NCT in secondary ID
    """
    
    def __init__(self, config: GuardrailConfig):
        self.config = config
        self.rejection_counts = {
            'mechanism_only_drift_guard': 0,
            'indication_gate': 0,
            'field_coverage_guard': 0
        }
        logger.info(f"Initialized guardrails system for stage '{config.stage}' with config: {config}")
    
    def validate_document(self, document: Dict[str, Any], entity_pack: EntityPack) -> List[GuardrailOutput]:
        """
        Apply all guardrails to a document.
        
        Args:
            document: Document metadata with title, abstract, etc.
            entity_pack: Entity pack for validation context
            
        Returns:
            List of guardrail results
        """
        results = []
        
        # Apply each guardrail
        results.append(self._mechanism_only_drift_guard(document, entity_pack))
        results.append(self._indication_gate(document, entity_pack))
        results.append(self._field_coverage_guard(document, entity_pack))
        
        return results
    
    def _mechanism_only_drift_guard(self, document: Dict[str, Any], entity_pack: EntityPack) -> GuardrailOutput:
        """
        Mechanism-only drift guard: Reject oncology content without must-link terms.
        
        This prevents papers that mention cancer/oncology terms but don't have
        any must-link terms (drug, company, NCT ID) from being included.
        """
        title = document.get('title', '').lower()
        abstract = document.get('abstract', '').lower()
        text = f"{title} {abstract}"
        
        # Check for oncology terms
        oncology_terms = entity_pack.get_cannot_link_terms()
        oncology_detected = any(term.lower() in text for term in oncology_terms)
        
        # Check for must-link terms
        must_link_terms = entity_pack.get_must_link_terms()
        has_must_link = any(term.lower() in text for term in must_link_terms)
        
        # Apply guardrail logic
        if oncology_detected and not has_must_link:
            return GuardrailOutput(
                passes_validation=False,
                guardrail_name="mechanism_only_drift_guard",
                reason="Oncology content without must-link terms",
                details={
                    "oncology_detected": oncology_detected,
                    "has_must_link": has_must_link,
                    "oncology_terms_found": [term for term in oncology_terms if term.lower() in text],
                    "must_link_terms_found": [term for term in must_link_terms if term.lower() in text]
                },
                penalty_score=2.0
            )
        
        return GuardrailOutput(
            passes_validation=True,
            guardrail_name="mechanism_only_drift_guard",
            reason="No oncology drift detected or must-link terms present",
            details={
                "oncology_detected": oncology_detected,
                "has_must_link": has_must_link
            }
        )
    
    def _indication_gate(self, document: Dict[str, Any], entity_pack: EntityPack) -> GuardrailOutput:
        """
        Indication gate: Require Alzheimer's disease signal.
        
        Documents must contain Alzheimer's disease related terms unless
        they have an NCT ID that ties them to the indication.
        """
        # Skip check if not required for this stage
        if not self.config.require_indication_signal:
            return GuardrailOutput(
                passes_validation=True,
                guardrail_name="indication_gate",
                reason=f"Indication signal check disabled for stage '{self.config.stage}'",
                details={"stage": self.config.stage, "require_indication_signal": False}
            )
        
        title = document.get('title', '').lower()
        abstract = document.get('abstract', '').lower()
        text = f"{title} {abstract}"
        
        # Check for indication terms
        indication_terms = []
        indication_terms.extend(entity_pack.indications.synonyms)
        indication_terms.append(entity_pack.indications.primary[0] if entity_pack.indications.primary else "")
        
        has_indication_signal = any(term.lower() in text for term in indication_terms if term)
        
        # Also check for drug terms (expression of concern papers might not mention indication)
        drug_terms = []
        if entity_pack.asset is not None:
            drug_terms.extend(entity_pack.asset.aliases)
            drug_terms.append(entity_pack.asset.canonical)
        has_drug_signal = any(term.lower() in text for term in drug_terms)
        
        # Check for NCT ID (overrides indication requirement)
        nct_id = document.get('nct_id')
        has_nct_id = nct_id is not None and nct_id.strip() != ""
        
        # Apply guardrail logic - accept if indication OR drug OR NCT ID is present
        if not has_indication_signal and not has_drug_signal and not has_nct_id:
            self.rejection_counts['indication_gate'] += 1
            return GuardrailOutput(
                passes_validation=False,
                guardrail_name="indication_gate",
                reason="No indication signal found and no NCT ID",
                details={
                    "has_indication_signal": has_indication_signal,
                    "has_drug_signal": has_drug_signal,
                    "has_nct_id": has_nct_id,
                    "indication_terms_found": [term for term in indication_terms if term and term.lower() in text],
                    "drug_terms_found": [term for term in drug_terms if term.lower() in text],
                    "nct_id": nct_id,
                    "stage": self.config.stage
                },
                penalty_score=1.0
            )
        
        return GuardrailOutput(
            passes_validation=True,
            guardrail_name="indication_gate",
            reason="Indication signal found or NCT ID present",
            details={
                "has_indication_signal": has_indication_signal,
                "has_drug_signal": has_drug_signal,
                "has_nct_id": has_nct_id,
                "stage": self.config.stage
            }
        )
    
    def _field_coverage_guard(self, document: Dict[str, Any], entity_pack: EntityPack) -> GuardrailOutput:
        """
        Field-coverage guard: Require drug in title/abstract or NCT in secondary ID.
        
        This ensures documents have sufficient field coverage to be relevant.
        """
        # Skip check if not required for this stage
        if not self.config.require_field_coverage:
            return GuardrailOutput(
                passes_validation=True,
                guardrail_name="field_coverage_guard",
                reason=f"Field coverage check disabled for stage '{self.config.stage}'",
                details={"stage": self.config.stage, "require_field_coverage": False}
            )
            
        title = document.get('title', '').lower()
        abstract = document.get('abstract', '').lower()
        text = f"{title} {abstract}"
        
        # Check for drug terms in title/abstract
        drug_terms = []
        if entity_pack.asset is not None:
            drug_terms.extend(entity_pack.asset.aliases)
            drug_terms.append(entity_pack.asset.canonical)
        
        # Also check for mechanism targets (e.g., "filamin A" for simufilam)
        mechanism_terms = entity_pack.mechanism.targets if hasattr(entity_pack.mechanism, 'targets') else []
        
        has_drug_in_tiab = any(term.lower() in text for term in drug_terms)
        has_mechanism_in_tiab = any(term.lower() in text for term in mechanism_terms)
        
        # Accept if either drug OR mechanism target is mentioned
        has_relevant_term = has_drug_in_tiab or has_mechanism_in_tiab
        
        # Check for NCT ID in secondary ID field
        nct_id = document.get('nct_id')
        has_nct_in_si = nct_id is not None and nct_id.strip() != ""
        
        # Apply guardrail logic
        field_coverage_met = False
        if self.config.min_drug_field_coverage and has_relevant_term:
            field_coverage_met = True
        if self.config.min_nct_field_coverage and has_nct_in_si:
            field_coverage_met = True
        if not self.config.min_drug_field_coverage and not self.config.min_nct_field_coverage:
            field_coverage_met = True  # No requirements
        
        if not field_coverage_met:
            self.rejection_counts['field_coverage_guard'] += 1
            return GuardrailOutput(
                passes_validation=False,
                guardrail_name="field_coverage_guard",
                reason="Insufficient field coverage",
                details={
                    "has_drug_in_tiab": has_drug_in_tiab,
                    "has_mechanism_in_tiab": has_mechanism_in_tiab,
                    "has_relevant_term": has_relevant_term,
                    "has_nct_in_si": has_nct_in_si,
                    "drug_terms_found": [term for term in drug_terms if term.lower() in text],
                    "mechanism_terms_found": [term for term in mechanism_terms if term.lower() in text],
                    "nct_id": nct_id,
                    "min_drug_coverage_required": self.config.min_drug_field_coverage,
                    "min_nct_coverage_required": self.config.min_nct_field_coverage,
                    "stage": self.config.stage
                },
                penalty_score=1.5
            )
        
        return GuardrailOutput(
            passes_validation=True,
            guardrail_name="field_coverage_guard",
            reason="Sufficient field coverage",
            details={
                "has_drug_in_tiab": has_drug_in_tiab,
                "has_mechanism_in_tiab": has_mechanism_in_tiab,
                "has_relevant_term": has_relevant_term,
                "has_nct_in_si": has_nct_in_si,
                "stage": self.config.stage
            }
        )
    
    def get_total_penalty(self, guardrail_results: List[GuardrailOutput]) -> float:
        """Calculate total penalty score from all guardrail results."""
        return sum(result.penalty_score for result in guardrail_results if not result.passes_validation)
    
    def should_reject_document(self, guardrail_results: List[GuardrailOutput]) -> bool:
        """Determine if document should be rejected based on guardrail results."""
        return any(not result.passes_validation for result in guardrail_results)
    
    def get_rejection_summary(self) -> Dict[str, int]:
        """Get summary of rejection counts by guardrail."""
        return self.rejection_counts.copy()
    
    def reset_rejection_counts(self):
        """Reset rejection counters."""
        for key in self.rejection_counts:
            self.rejection_counts[key] = 0
