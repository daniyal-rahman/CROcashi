#!/usr/bin/env python3
"""
Content Validation System

Validates retrieved content to ensure it's Cassava-relevant and has proper academic structure.
Prevents generic content from being processed by LLM.
"""

import logging
import re
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Cassava-specific terms for validation
CASSAVA_TERMS = {
    "company": ["cassava sciences", "cassava"],
    "asset": ["simufilam", "pti-125", "pti125", "pti 125"],
    "indication": ["alzheimer", "alzheimer's", "alzheimer disease", "ad"],
    "mechanism": ["filamin", "flna", "mtor", "receptor", "lymphocyte"]
}

# Academic paper structure indicators
PAPER_STRUCTURE_TERMS = [
    "abstract", "summary", "introduction", "background",
    "methods", "methodology", "experimental", "materials",
    "results", "findings", "outcomes", "data",
    "discussion", "conclusion", "implications",
    "references", "bibliography", "cited", "doi"
]

# Generic content indicators (should be absent)
GENERIC_CONTENT_INDICATORS = [
    "bill clinton", "norway", "prime minister", "population growth",
    "sustainable development", "international conference", "forum",
    "keynote speaker", "two-day", "representatives", "countries"
]


@dataclass
class ValidationResult:
    """Result of content validation."""
    is_valid: bool
    confidence: float
    reasons: List[str]
    warnings: List[str]
    cassava_relevance_score: float
    paper_structure_score: float
    generic_content_score: float


class ContentValidator:
    """Validates content for Cassava relevance and academic structure."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the content validator."""
        self.config = config or {}
        self.min_cassava_score = self.config.get('min_cassava_score', 0.3)
        self.min_paper_structure_score = self.config.get('min_paper_structure_score', 0.2)
        self.max_generic_score = self.config.get('max_generic_score', 0.1)
        self.require_title_match = self.config.get('require_title_match', True)
    
    def validate_content(self, content: str, title: str = "", source_id: str = "") -> ValidationResult:
        """
        Validate content for Cassava relevance and academic structure.
        
        Args:
            content: The content text to validate
            title: Document title (optional)
            source_id: Source identifier (PMCID, PMID, etc.)
            
        Returns:
            ValidationResult with validation details
        """
        if not content or len(content.strip()) < 50:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                reasons=["content_too_short"],
                warnings=[],
                cassava_relevance_score=0.0,
                paper_structure_score=0.0,
                generic_content_score=0.0
            )
        
        content_lower = content.lower()
        title_lower = title.lower()
        
        # Calculate scores
        cassava_score = self._calculate_cassava_relevance(content_lower, title_lower)
        paper_structure_score = self._calculate_paper_structure(content_lower)
        generic_score = self._calculate_generic_content_score(content_lower)
        
        # Determine validity
        reasons = []
        warnings = []
        
        if cassava_score < self.min_cassava_score:
            reasons.append(f"low_cassava_relevance_{cassava_score:.2f}")
        
        if paper_structure_score < self.min_paper_structure_score:
            reasons.append(f"low_paper_structure_{paper_structure_score:.2f}")
        
        if generic_score > self.max_generic_score:
            reasons.append(f"high_generic_content_{generic_score:.2f}")
        
        if self.require_title_match and title:
            if not self._title_matches_asset(title_lower):
                reasons.append("title_not_matching_asset")
        
        # Check for specific issues
        if self._has_generic_content_patterns(content_lower):
            reasons.append("generic_content_patterns")
            warnings.append("Content appears to be generic web content, not academic paper")
        
        if self._has_suspicious_patterns(content_lower):
            warnings.append("Content has suspicious patterns that may indicate wrong source")
        
        # Overall validity
        is_valid = len(reasons) == 0
        
        # Calculate confidence
        confidence = min(1.0, (cassava_score + paper_structure_score + (1.0 - generic_score)) / 3.0)
        
        return ValidationResult(
            is_valid=is_valid,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings,
            cassava_relevance_score=cassava_score,
            paper_structure_score=paper_structure_score,
            generic_content_score=generic_score
        )
    
    def _calculate_cassava_relevance(self, content: str, title: str) -> float:
        """Calculate Cassava relevance score."""
        total_hits = 0
        category_hits = 0
        
        for category, terms in CASSAVA_TERMS.items():
            category_matches = sum(1 for term in terms if term in content or term in title)
            if category_matches > 0:
                category_hits += 1
                total_hits += category_matches
        
        # Normalize score (0-1)
        max_possible_hits = sum(len(terms) for terms in CASSAVA_TERMS.values())
        hit_score = total_hits / max_possible_hits if max_possible_hits > 0 else 0
        
        # Bonus for multiple categories
        category_score = category_hits / len(CASSAVA_TERMS) if CASSAVA_TERMS else 0
        
        # Weighted combination
        return (hit_score * 0.7) + (category_score * 0.3)
    
    def _calculate_paper_structure(self, content: str) -> float:
        """Calculate academic paper structure score."""
        structure_hits = sum(1 for term in PAPER_STRUCTURE_TERMS if term in content)
        
        # Normalize score (0-1)
        max_possible_hits = len(PAPER_STRUCTURE_TERMS)
        return structure_hits / max_possible_hits if max_possible_hits > 0 else 0
    
    def _calculate_generic_content_score(self, content: str) -> float:
        """Calculate generic content score (lower is better)."""
        generic_hits = sum(1 for term in GENERIC_CONTENT_INDICATORS if term in content)
        
        # Normalize score (0-1)
        max_possible_hits = len(GENERIC_CONTENT_INDICATORS)
        return generic_hits / max_possible_hits if max_possible_hits > 0 else 0
    
    def _title_matches_asset(self, title: str) -> bool:
        """Check if title contains asset-related terms."""
        asset_terms = CASSAVA_TERMS["asset"]
        return any(term in title for term in asset_terms)
    
    def _has_generic_content_patterns(self, content: str) -> bool:
        """Check for patterns that indicate generic web content."""
        generic_patterns = [
            r"president.*clinton",
            r"prime minister.*norway",
            r"international conference",
            r"two-day forum",
            r"representatives.*countries",
            r"keynote speaker"
        ]
        
        return any(re.search(pattern, content) for pattern in generic_patterns)
    
    def _has_suspicious_patterns(self, content: str) -> bool:
        """Check for suspicious patterns that may indicate wrong source."""
        suspicious_patterns = [
            r"population.*growth",
            r"sustainable development",
            r"forum.*addressing",
            r"discusses.*issues"
        ]
        
        return any(re.search(pattern, content) for pattern in suspicious_patterns)
    
    def validate_numeric_evidence(self, field_name: str, value: Any, evidence: str) -> Tuple[bool, str]:
        """
        Validate that numeric values have evidence in the source text.
        
        Args:
            field_name: Name of the field being validated
            value: The extracted value
            evidence: The source evidence text
            
        Returns:
            Tuple of (is_valid, reason)
        """
        if value is None:
            return True, "null_value"
        
        # Check if value contains numbers
        if not any(c.isdigit() for c in str(value)):
            return True, "non_numeric_value"
        
        # Check if evidence contains numbers
        if not evidence or not any(c.isdigit() for c in evidence):
            return False, "no_numeric_evidence"
        
        # Check if the specific numbers from value appear in evidence
        value_str = str(value)
        if any(char.isdigit() for char in value_str):
            # Extract numbers from value
            value_numbers = re.findall(r'\d+', value_str)
            evidence_numbers = re.findall(r'\d+', evidence)
            
            # Check if any value numbers appear in evidence
            if not any(num in evidence_numbers for num in value_numbers):
                return False, "numbers_not_in_evidence"
        
        return True, "valid_evidence"


def is_cassava_relevant(text: str) -> bool:
    """Quick check for Cassava relevance."""
    validator = ContentValidator()
    result = validator.validate_content(text)
    return result.is_valid and result.cassava_relevance_score >= 0.3


def has_paper_structure(text: str) -> bool:
    """Quick check for academic paper structure."""
    validator = ContentValidator()
    result = validator.validate_content(text)
    return result.paper_structure_score >= 0.2


def validate_source(doc: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a document source.
    
    Args:
        doc: Document dictionary with 'text' and 'title' keys
        
    Returns:
        Tuple of (is_valid, reasons)
    """
    validator = ContentValidator()
    result = validator.validate_content(
        doc.get('text', ''),
        doc.get('title', ''),
        doc.get('source_id', '')
    )
    
    return result.is_valid, result.reasons


# Global validator instance
_global_validator: Optional[ContentValidator] = None


def get_content_validator(config: Optional[Dict[str, Any]] = None) -> ContentValidator:
    """Get global content validator instance."""
    global _global_validator
    if _global_validator is None:
        _global_validator = ContentValidator(config)
    return _global_validator
