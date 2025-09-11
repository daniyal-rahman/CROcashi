"""
Policy engine for PubMed retrieval with must/should/cannot rules.

Implements the retrieval policy specification with oncology filtering,
must-link validation, and sophisticated scoring.
"""

import logging
import re
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from ...entities.schema import EntityPack

logger = logging.getLogger(__name__)


@dataclass
class PolicyConfig:
    """Configuration for retrieval policy engine."""
    must_link_weight: float = 3.0
    should_link_weight: float = 1.0
    cannot_link_penalty: float = 2.0
    max_should_link_bonus: float = 3.0
    require_must_link_for_oncology: bool = True
    require_indication_signal: bool = True
    require_field_coverage: bool = True


@dataclass
class PolicyResult:
    """Result from policy engine validation."""
    passes_validation: bool
    total_score: float
    must_link_score: float
    should_link_score: float
    cannot_link_penalty: float
    oncology_detected: bool
    has_indication_signal: bool
    has_field_coverage: bool
    validation_errors: List[str]


class OncologyDetector:
    """Detects oncology/cancer terms in documents."""
    
    def __init__(self, oncology_terms: Optional[List[str]] = None):
        """
        Initialize oncology detector.
        
        Args:
            oncology_terms: List of oncology terms to detect
        """
        self.oncology_terms = oncology_terms or [
            "carcinoma", "esophageal", "melanoma", "chemoradiotherapy", 
            "oncology", "cancer", "tumor", "neoplasm", "metastasis", 
            "chemotherapy", "radiation", "radiotherapy", "sarcoma",
            "lymphoma", "leukemia", "adenocarcinoma", "squamous cell"
        ]
        
        # Create compiled regex patterns for efficient matching
        self.oncology_patterns = [
            re.compile(rf'\b{term}\b', re.IGNORECASE) 
            for term in self.oncology_terms
        ]
    
    def detect_oncology_terms(self, text: str) -> List[str]:
        """
        Detect oncology terms in text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of detected oncology terms
        """
        if not text:
            return []
        
        detected_terms = []
        text_lower = text.lower()
        
        for term in self.oncology_terms:
            if term.lower() in text_lower:
                detected_terms.append(term)
        
        return detected_terms
    
    def has_oncology_content(self, text: str) -> bool:
        """
        Check if text contains oncology content.
        
        Args:
            text: Text to analyze
            
        Returns:
            True if oncology content detected
        """
        return len(self.detect_oncology_terms(text)) > 0


class RetrievalPolicy:
    """Policy engine for document retrieval validation."""
    
    def __init__(self, config: Optional[PolicyConfig] = None):
        """
        Initialize retrieval policy engine.
        
        Args:
            config: Policy configuration
        """
        self.config = config or PolicyConfig()
        self.oncology_detector = OncologyDetector()
        
        logger.info(f"Initialized retrieval policy engine with config: {self.config}")
    
    def validate_document(
        self, 
        doc: Dict[str, Any], 
        entity_pack: EntityPack
    ) -> PolicyResult:
        """
        Validate document against must/should/cannot rules.
        
        Args:
            doc: Document to validate
            entity_pack: Entity pack with rules
            
        Returns:
            Policy validation result
        """
        try:
            # Extract document text for analysis
            doc_text = self._extract_document_text(doc)
            
            # Calculate individual scores
            must_link_score = self._calculate_must_link_score(doc_text, entity_pack)
            should_link_score = self._calculate_should_link_score(doc_text, entity_pack)
            cannot_link_penalty = self._calculate_cannot_link_penalty(doc_text, entity_pack)
            
            # Check validation criteria
            oncology_detected = self.oncology_detector.has_oncology_content(doc_text)
            has_indication_signal = self._has_indication_signal(doc_text, entity_pack)
            has_field_coverage = self._has_field_coverage(doc_text, entity_pack)
            
            # Calculate total score
            total_score = must_link_score + should_link_score - cannot_link_penalty
            
            # Determine if document passes validation
            validation_errors = []
            passes_validation = True
            
            # Must-link validation
            if must_link_score == 0:
                validation_errors.append("No must-link terms found")
                passes_validation = False
            
            # Oncology guardrail
            if oncology_detected and must_link_score == 0 and self.config.require_must_link_for_oncology:
                validation_errors.append("Oncology content without must-link terms")
                passes_validation = False
            
            # Indication gate - be more flexible if must-link terms are present
            if not has_indication_signal and self.config.require_indication_signal:
                # If we have strong must-link terms (drug/company), be more lenient
                if must_link_score >= 3.0:  # Strong must-link presence
                    # Only require indication signal if oncology is detected
                    if oncology_detected:
                        validation_errors.append("No indication signal found (oncology detected)")
                        passes_validation = False
                    # Otherwise, allow through with a warning
                else:
                    validation_errors.append("No indication signal found")
                    passes_validation = False
            
            # Field coverage guard
            if not has_field_coverage and self.config.require_field_coverage:
                validation_errors.append("Insufficient field coverage")
                passes_validation = False
            
            return PolicyResult(
                passes_validation=passes_validation,
                total_score=total_score,
                must_link_score=must_link_score,
                should_link_score=should_link_score,
                cannot_link_penalty=cannot_link_penalty,
                oncology_detected=oncology_detected,
                has_indication_signal=has_indication_signal,
                has_field_coverage=has_field_coverage,
                validation_errors=validation_errors
            )
            
        except Exception as e:
            logger.error(f"Error validating document: {e}")
            return PolicyResult(
                passes_validation=False,
                total_score=0.0,
                must_link_score=0.0,
                should_link_score=0.0,
                cannot_link_penalty=0.0,
                oncology_detected=False,
                has_indication_signal=False,
                has_field_coverage=False,
                validation_errors=[f"Validation error: {str(e)}"]
            )
    
    def _extract_document_text(self, doc: Dict[str, Any]) -> str:
        """Extract text content from document for analysis."""
        text_parts = []
        
        # Add title
        if doc.get('title'):
            text_parts.append(doc['title'])
        
        # Add abstract
        if doc.get('abstract'):
            text_parts.append(doc['abstract'])
        
        # Add MeSH terms
        if doc.get('mesh_terms'):
            if isinstance(doc['mesh_terms'], list):
                text_parts.extend(doc['mesh_terms'])
            else:
                text_parts.append(str(doc['mesh_terms']))
        
        # Add keywords
        if doc.get('keywords'):
            if isinstance(doc['keywords'], list):
                text_parts.extend(doc['keywords'])
            else:
                text_parts.append(str(doc['keywords']))
        
        return ' '.join(text_parts)
    
    def _calculate_must_link_score(self, text: str, entity_pack: EntityPack) -> float:
        """
        Calculate must-link score.
        
        Args:
            text: Document text
            entity_pack: Entity pack with must-link terms
            
        Returns:
            Must-link score
        """
        must_link_terms = entity_pack.get_must_link_terms()
        text_lower = text.lower()
        
        must_link_count = 0
        for term in must_link_terms:
            if term.lower() in text_lower:
                must_link_count += 1
        
        # Return weight if any must-link terms found
        return self.config.must_link_weight if must_link_count > 0 else 0.0
    
    def _calculate_should_link_score(self, text: str, entity_pack: EntityPack) -> float:
        """
        Calculate should-link score.
        
        Args:
            text: Document text
            entity_pack: Entity pack with should-link terms
            
        Returns:
            Should-link score (capped at max_should_link_bonus)
        """
        should_link_terms = entity_pack.get_should_link_terms()
        text_lower = text.lower()
        
        should_link_count = 0
        for term in should_link_terms:
            if term.lower() in text_lower:
                should_link_count += 1
        
        # Apply weight and cap at maximum
        score = should_link_count * self.config.should_link_weight
        return min(score, self.config.max_should_link_bonus)
    
    def _calculate_cannot_link_penalty(self, text: str, entity_pack: EntityPack) -> float:
        """
        Calculate cannot-link penalty.
        
        Args:
            text: Document text
            entity_pack: Entity pack (for must-link validation)
            
        Returns:
            Cannot-link penalty
        """
        # Check for oncology terms
        oncology_terms = self.oncology_detector.detect_oncology_terms(text)
        
        if not oncology_terms:
            return 0.0
        
        # Check if document has must-link terms
        must_link_terms = entity_pack.get_must_link_terms()
        text_lower = text.lower()
        
        has_must_link = any(term.lower() in text_lower for term in must_link_terms)
        
        # Apply penalty only if oncology terms present AND no must-link
        if oncology_terms and not has_must_link:
            return self.config.cannot_link_penalty
        
        return 0.0
    
    def _has_indication_signal(self, text: str, entity_pack: EntityPack) -> bool:
        """
        Check if document has indication signal.
        
        Args:
            text: Document text
            entity_pack: Entity pack with indication terms
            
        Returns:
            True if indication signal found
        """
        indication_terms = entity_pack.get_all_indication_terms()
        text_lower = text.lower()
        
        # Check for MeSH terms (more specific)
        mesh_terms = ["alzheimer disease", "alzheimer's disease"]
        for mesh_term in mesh_terms:
            if mesh_term in text_lower:
                return True
        
        # Check for general indication terms
        for term in indication_terms:
            if term.lower() in text_lower:
                return True
        
        return False
    
    def _has_field_coverage(self, text: str, entity_pack: EntityPack) -> bool:
        """
        Check if document has sufficient field coverage.
        
        Args:
            text: Document text
            entity_pack: Entity pack
            
        Returns:
            True if sufficient field coverage
        """
        # Require at least one of: drug in [tiab], NCT in [si]
        asset_terms = entity_pack.get_all_asset_terms()
        nct_ids = entity_pack.registries.nct_ids
        
        text_lower = text.lower()
        
        # Check for drug terms
        has_drug_term = any(term.lower() in text_lower for term in asset_terms)
        
        # Check for NCT IDs
        has_nct_id = any(nct_id.lower() in text_lower for nct_id in nct_ids)
        
        return has_drug_term or has_nct_id
    
    def get_policy_summary(self) -> Dict[str, Any]:
        """Get summary of policy configuration."""
        return {
            'must_link_weight': self.config.must_link_weight,
            'should_link_weight': self.config.should_link_weight,
            'cannot_link_penalty': self.config.cannot_link_penalty,
            'max_should_link_bonus': self.config.max_should_link_bonus,
            'require_must_link_for_oncology': self.config.require_must_link_for_oncology,
            'require_indication_signal': self.config.require_indication_signal,
            'require_field_coverage': self.config.require_field_coverage,
            'oncology_terms_count': len(self.oncology_detector.oncology_terms)
        }


class RuleEngine:
    """Rule engine for processing multiple documents."""
    
    def __init__(self, policy: RetrievalPolicy):
        """
        Initialize rule engine.
        
        Args:
            policy: Retrieval policy instance
        """
        self.policy = policy
        self.logger = logging.getLogger(__name__)
    
    def process_documents(
        self, 
        documents: List[Dict[str, Any]], 
        entity_pack: EntityPack
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Process multiple documents through policy engine.
        
        Args:
            documents: List of documents to process
            entity_pack: Entity pack with rules
            
        Returns:
            Tuple of (valid_documents, rejected_documents, stats)
        """
        valid_documents = []
        rejected_documents = []
        stats = {
            'total_processed': len(documents),
            'valid_count': 0,
            'rejected_count': 0,
            'oncology_rejected': 0,
            'no_must_link_rejected': 0,
            'no_indication_rejected': 0,
            'no_field_coverage_rejected': 0
        }
        
        for doc in documents:
            try:
                result = self.policy.validate_document(doc, entity_pack)
                
                if result.passes_validation:
                    # Add policy result to document
                    doc['policy_result'] = result
                    valid_documents.append(doc)
                    stats['valid_count'] += 1
                else:
                    # Add rejection reason
                    doc['rejection_reason'] = result.validation_errors
                    rejected_documents.append(doc)
                    stats['rejected_count'] += 1
                    
                    # Update rejection stats
                    if result.oncology_detected:
                        stats['oncology_rejected'] += 1
                    if not result.must_link_score:
                        stats['no_must_link_rejected'] += 1
                    if not result.has_indication_signal:
                        stats['no_indication_rejected'] += 1
                    if not result.has_field_coverage:
                        stats['no_field_coverage_rejected'] += 1
                        
            except Exception as e:
                self.logger.error(f"Error processing document {doc.get('pmid', 'unknown')}: {e}")
                doc['rejection_reason'] = [f"Processing error: {str(e)}"]
                rejected_documents.append(doc)
                stats['rejected_count'] += 1
        
        self.logger.info(f"Policy engine processed {stats['total_processed']} documents: "
                        f"{stats['valid_count']} valid, {stats['rejected_count']} rejected")
        
        return valid_documents, rejected_documents, stats
