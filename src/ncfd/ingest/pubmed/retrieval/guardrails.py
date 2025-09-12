"""
Guardrails system for PubMed retrieval to prevent off-topic content contamination.

This module implements the guardrails from the retrieval specification:
- Mechanism-only drift guard
- Indication gate  
- Field-coverage guard
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from ....entities.schema import EntityPack

logger = logging.getLogger(__name__)


@dataclass
class GuardrailConfig:
    """Configuration for guardrails system."""
    
    # Mechanism-only drift guard
    require_must_link_for_oncology: bool = True
    
    # Indication gate
    require_indication_signal: bool = True
    
    # Field-coverage guard
    require_field_coverage: bool = True
    
    # Minimum field coverage requirements
    min_drug_field_coverage: bool = True  # Require drug in [tiab]
    min_nct_field_coverage: bool = False  # Require NCT in [si] (optional)
    
    # Oncology detection
    oncology_penalty_threshold: float = 0.5  # Minimum oncology score to trigger penalty


@dataclass
class GuardrailResult:
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
        logger.info(f"Initialized guardrails system with config: {config}")
    
    def validate_document(self, document: Dict[str, Any], entity_pack: EntityPack) -> List[GuardrailResult]:
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
    
    def _mechanism_only_drift_guard(self, document: Dict[str, Any], entity_pack: EntityPack) -> GuardrailResult:
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
        must_link_terms = []
        must_link_terms.extend(entity_pack.asset.aliases)
        must_link_terms.extend(entity_pack.company.aliases)
        must_link_terms.extend(entity_pack.registries.nct_ids)
        must_link_terms.append(entity_pack.asset.canonical)
        must_link_terms.append(entity_pack.company.canonical)
        
        has_must_link = any(term.lower() in text for term in must_link_terms)
        
        # Apply guardrail logic
        if oncology_detected and not has_must_link:
            return GuardrailResult(
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
        
        return GuardrailResult(
            passes_validation=True,
            guardrail_name="mechanism_only_drift_guard",
            reason="No oncology drift detected or must-link terms present",
            details={
                "oncology_detected": oncology_detected,
                "has_must_link": has_must_link
            }
        )
    
    def _indication_gate(self, document: Dict[str, Any], entity_pack: EntityPack) -> GuardrailResult:
        """
        Indication gate: Require Alzheimer's disease signal.
        
        Documents must contain Alzheimer's disease related terms unless
        they have an NCT ID that ties them to the indication.
        """
        title = document.get('title', '').lower()
        abstract = document.get('abstract', '').lower()
        text = f"{title} {abstract}"
        
        # Check for indication terms
        indication_terms = []
        indication_terms.extend(entity_pack.indications.synonyms)
        indication_terms.append(entity_pack.indications.primary[0] if entity_pack.indications.primary else "")
        
        has_indication_signal = any(term.lower() in text for term in indication_terms if term)
        
        # Check for NCT ID (overrides indication requirement)
        nct_id = document.get('nct_id')
        has_nct_id = nct_id is not None and nct_id.strip() != ""
        
        # Apply guardrail logic
        if not has_indication_signal and not has_nct_id:
            return GuardrailResult(
                passes_validation=False,
                guardrail_name="indication_gate",
                reason="No indication signal found and no NCT ID",
                details={
                    "has_indication_signal": has_indication_signal,
                    "has_nct_id": has_nct_id,
                    "indication_terms_found": [term for term in indication_terms if term and term.lower() in text],
                    "nct_id": nct_id
                },
                penalty_score=1.0
            )
        
        return GuardrailResult(
            passes_validation=True,
            guardrail_name="indication_gate",
            reason="Indication signal found or NCT ID present",
            details={
                "has_indication_signal": has_indication_signal,
                "has_nct_id": has_nct_id
            }
        )
    
    def _field_coverage_guard(self, document: Dict[str, Any], entity_pack: EntityPack) -> GuardrailResult:
        """
        Field-coverage guard: Require drug in title/abstract or NCT in secondary ID.
        
        This ensures documents have sufficient field coverage to be relevant.
        """
        title = document.get('title', '').lower()
        abstract = document.get('abstract', '').lower()
        text = f"{title} {abstract}"
        
        # Check for drug terms in title/abstract
        drug_terms = []
        drug_terms.extend(entity_pack.asset.aliases)
        drug_terms.append(entity_pack.asset.canonical)
        
        has_drug_in_tiab = any(term.lower() in text for term in drug_terms)
        
        # Check for NCT ID in secondary ID field
        nct_id = document.get('nct_id')
        has_nct_in_si = nct_id is not None and nct_id.strip() != ""
        
        # Apply guardrail logic
        field_coverage_met = False
        if self.config.min_drug_field_coverage and has_drug_in_tiab:
            field_coverage_met = True
        if self.config.min_nct_field_coverage and has_nct_in_si:
            field_coverage_met = True
        if not self.config.min_drug_field_coverage and not self.config.min_nct_field_coverage:
            field_coverage_met = True  # No requirements
        
        if not field_coverage_met:
            return GuardrailResult(
                passes_validation=False,
                guardrail_name="field_coverage_guard",
                reason="Insufficient field coverage",
                details={
                    "has_drug_in_tiab": has_drug_in_tiab,
                    "has_nct_in_si": has_nct_in_si,
                    "drug_terms_found": [term for term in drug_terms if term.lower() in text],
                    "nct_id": nct_id,
                    "min_drug_coverage_required": self.config.min_drug_field_coverage,
                    "min_nct_coverage_required": self.config.min_nct_field_coverage
                },
                penalty_score=1.5
            )
        
        return GuardrailResult(
            passes_validation=True,
            guardrail_name="field_coverage_guard",
            reason="Sufficient field coverage",
            details={
                "has_drug_in_tiab": has_drug_in_tiab,
                "has_nct_in_si": has_nct_in_si
            }
        )
    
    def get_total_penalty(self, guardrail_results: List[GuardrailResult]) -> float:
        """Calculate total penalty score from all guardrail results."""
        return sum(result.penalty_score for result in guardrail_results if not result.passes_validation)
    
    def should_reject_document(self, guardrail_results: List[GuardrailResult]) -> bool:
        """Determine if document should be rejected based on guardrail results."""
        return any(not result.passes_validation for result in guardrail_results)
