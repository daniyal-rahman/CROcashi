"""
Patent Assignee to Company Resolver

Maps patent assignees to companies in the CROcashi database using the existing
company resolution infrastructure. Handles university assignments, corporate
subsidiaries, and name variations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session

from .resolve_service import resolve_sponsor
from .normalize import norm_name, norm_name_loose
from .deterministic import has_academic_keywords
from ..db.models import Company, CompanyAlias

logger = logging.getLogger(__name__)


@dataclass
class AssigneeResolution:
    """Result of assignee to company resolution."""
    company_id: Optional[int]
    company_name: Optional[str]
    confidence: float
    method: str
    evidence: Dict[str, Any]
    
    @property
    def is_resolved(self) -> bool:
        """Check if assignee was successfully resolved."""
        return self.company_id is not None
    
    @property
    def is_high_confidence(self) -> bool:
        """Check if resolution is high confidence."""
        return self.confidence >= 0.85


class PatentAssigneeResolver:
    """
    Resolver for mapping patent assignees to companies.
    
    Uses the existing company resolution infrastructure with patent-specific
    enhancements for handling assignee name variations.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize assignee resolver.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Resolution configuration
        self.resolve_universities = self.config.get("resolve_universities", False)
        self.min_confidence = self.config.get("min_confidence", 0.6)
        self.use_subsidiary_mapping = self.config.get("use_subsidiary_mapping", True)
        
        # Patent-specific name patterns
        self._compile_assignee_patterns()
        
        logger.info("Initialized patent assignee resolver")
    
    def resolve_assignee(self, session: Session, assignee_name: str, 
                        context: Optional[Dict[str, Any]] = None) -> AssigneeResolution:
        """
        Resolve a patent assignee to a company.
        
        Args:
            session: Database session
            assignee_name: Name of patent assignee
            context: Additional context (patent date, technology area, etc.)
            
        Returns:
            AssigneeResolution with company mapping results
        """
        if not assignee_name or not assignee_name.strip():
            return AssigneeResolution(
                company_id=None,
                company_name=None,
                confidence=0.0,
                method="empty_input",
                evidence={}
            )
        
        # Clean and normalize assignee name
        cleaned_name = self._clean_assignee_name(assignee_name)
        
        # Skip if university/academic and not configured to resolve
        if not self.resolve_universities and self._is_academic_assignee(cleaned_name):
            return AssigneeResolution(
                company_id=None,
                company_name=cleaned_name,
                confidence=0.0,
                method="academic_skipped",
                evidence={"original_name": assignee_name, "is_academic": True}
            )
        
        # Try direct company resolution using existing infrastructure
        resolution = self._try_direct_resolution(session, cleaned_name, context)
        if resolution.is_resolved:
            return resolution
        
        # Try patent-specific name variations
        resolution = self._try_patent_variations(session, assignee_name, context)
        if resolution.is_resolved:
            return resolution
        
        # Try subsidiary mapping if enabled
        if self.use_subsidiary_mapping:
            resolution = self._try_subsidiary_mapping(session, cleaned_name, context)
            if resolution.is_resolved:
                return resolution
        
        # Return unresolved result
        return AssigneeResolution(
            company_id=None,
            company_name=cleaned_name,
            confidence=0.0,
            method="unresolved",
            evidence={"original_name": assignee_name, "cleaned_name": cleaned_name}
        )
    
    def resolve_assignees_batch(self, session: Session, 
                               assignee_names: List[str],
                               context: Optional[Dict[str, Any]] = None) -> List[AssigneeResolution]:
        """
        Resolve multiple assignees in batch for efficiency.
        
        Args:
            session: Database session
            assignee_names: List of assignee names
            context: Additional context
            
        Returns:
            List of AssigneeResolution objects
        """
        results = []
        
        for assignee_name in assignee_names:
            try:
                resolution = self.resolve_assignee(session, assignee_name, context)
                results.append(resolution)
            except Exception as e:
                logger.error(f"Error resolving assignee '{assignee_name}': {e}")
                results.append(AssigneeResolution(
                    company_id=None,
                    company_name=assignee_name,
                    confidence=0.0,
                    method="error",
                    evidence={"error": str(e)}
                ))
        
        return results
    
    def _try_direct_resolution(self, session: Session, assignee_name: str,
                             context: Optional[Dict[str, Any]]) -> AssigneeResolution:
        """Try direct resolution using existing company resolver."""
        try:
            # Use existing resolve_sponsor function with default config
            config = {
                "model": {"weights": {}, "intercept": 0.0},
                "thresholds": {
                    "tau_accept": 0.85,
                    "review_low": 0.65,
                    "min_top2_margin": 0.1
                }
            }
            
            result = resolve_sponsor(session, assignee_name, config, context)
            
            if result.get("company_id"):
                # Get company name
                company = session.query(Company).filter(
                    Company.company_id == result["company_id"]
                ).first()
                
                return AssigneeResolution(
                    company_id=result["company_id"],
                    company_name=company.name if company else None,
                    confidence=result.get("p", 0.0),
                    method=f"direct_{result.get('mode', 'unknown')}",
                    evidence=result
                )
        
        except Exception as e:
            logger.debug(f"Direct resolution failed for '{assignee_name}': {e}")
        
        return AssigneeResolution(
            company_id=None,
            company_name=None,
            confidence=0.0,
            method="direct_failed",
            evidence={}
        )
    
    def _try_patent_variations(self, session: Session, assignee_name: str,
                             context: Optional[Dict[str, Any]]) -> AssigneeResolution:
        """Try patent-specific name variations."""
        
        # Generate name variations
        variations = self._generate_assignee_variations(assignee_name)
        
        best_resolution = AssigneeResolution(
            company_id=None,
            company_name=None,
            confidence=0.0,
            method="variations_failed",
            evidence={}
        )
        
        for variation in variations:
            try:
                resolution = self._try_direct_resolution(session, variation, context)
                
                # Keep the best resolution
                if resolution.confidence > best_resolution.confidence:
                    best_resolution = resolution
                    best_resolution.method = f"variation_{resolution.method}"
                    best_resolution.evidence["original_name"] = assignee_name
                    best_resolution.evidence["variation_used"] = variation
                
                # If we found a high-confidence match, use it
                if resolution.is_high_confidence:
                    break
                    
            except Exception as e:
                logger.debug(f"Variation resolution failed for '{variation}': {e}")
                continue
        
        return best_resolution
    
    def _try_subsidiary_mapping(self, session: Session, assignee_name: str,
                              context: Optional[Dict[str, Any]]) -> AssigneeResolution:
        """Try mapping through subsidiary relationships."""
        try:
            # Look for potential parent companies based on name patterns
            parent_candidates = self._find_parent_candidates(session, assignee_name)
            
            for parent_id, parent_name, match_method in parent_candidates:
                # Verify this is actually a subsidiary relationship
                if self._verify_subsidiary_relationship(session, assignee_name, parent_id):
                    return AssigneeResolution(
                        company_id=parent_id,
                        company_name=parent_name,
                        confidence=0.75,  # Medium confidence for subsidiary mapping
                        method=f"subsidiary_{match_method}",
                        evidence={
                            "assignee_name": assignee_name,
                            "parent_company": parent_name,
                            "parent_id": parent_id
                        }
                    )
        
        except Exception as e:
            logger.debug(f"Subsidiary mapping failed for '{assignee_name}': {e}")
        
        return AssigneeResolution(
            company_id=None,
            company_name=None,
            confidence=0.0,
            method="subsidiary_failed",
            evidence={}
        )
    
    def _clean_assignee_name(self, assignee_name: str) -> str:
        """Clean and normalize assignee name for resolution."""
        name = assignee_name.strip()
        
        # Remove common patent assignee suffixes
        patent_suffixes = [
            r'\s*,?\s*as\s+assignee\s*$',
            r'\s*,?\s*assignee\s*$',
            r'\s*,?\s*as\s+successor\s+in\s+interest\s*$',
            r'\s*,?\s*successor\s+in\s+interest\s*$',
        ]
        
        for suffix in patent_suffixes:
            name = re.sub(suffix, '', name, flags=re.IGNORECASE)
        
        # Clean up extra whitespace and punctuation
        name = re.sub(r'\s+', ' ', name).strip()
        name = name.rstrip(',.')
        
        return name
    
    def _generate_assignee_variations(self, assignee_name: str) -> List[str]:
        """Generate name variations for patent assignees."""
        variations = [assignee_name]
        
        # Remove common patent-specific suffixes
        base_name = self._clean_assignee_name(assignee_name)
        if base_name != assignee_name:
            variations.append(base_name)
        
        # Try with and without common corporate suffixes
        corporate_suffixes = [
            'inc', 'incorporated', 'corp', 'corporation', 'company', 'co',
            'ltd', 'limited', 'llc', 'lp', 'sa', 'ag', 'gmbh'
        ]
        
        for suffix in corporate_suffixes:
            # Remove suffix
            pattern = rf'\s*,?\s*{re.escape(suffix)}\.?\s*$'
            variation = re.sub(pattern, '', base_name, flags=re.IGNORECASE)
            if variation != base_name and variation not in variations:
                variations.append(variation)
            
            # Add suffix if not present
            if not re.search(rf'\b{re.escape(suffix)}\b', base_name, re.IGNORECASE):
                variation = f"{base_name}, {suffix.upper()}"
                if variation not in variations:
                    variations.append(variation)
        
        # Try acronym expansion if assignee looks like acronym
        if self._is_likely_acronym(base_name):
            # Look for expanded forms in the database
            expanded_forms = self._find_acronym_expansions(base_name)
            variations.extend(expanded_forms)
        
        return variations
    
    def _find_parent_candidates(self, session: Session, assignee_name: str) -> List[Tuple[int, str, str]]:
        """Find potential parent companies for subsidiary mapping."""
        candidates = []
        
        # Extract potential parent company name from assignee
        parent_patterns = [
            r'^(.+?)\s+(?:inc|corp|ltd|llc|company|co)\.?\s*[,-]\s*.+$',  # "Parent Corp - Subsidiary"
            r'^(.+?)\s+.+\s+(?:division|subsidiary|unit)$',  # "Parent Subsidiary Division"
            r'^(.+?)\s+(?:holdings?|group|international)(?:\s+inc|corp|ltd)?\.?\s*$',  # "Parent Holdings Inc"
        ]
        
        for pattern in parent_patterns:
            match = re.search(pattern, assignee_name, re.IGNORECASE)
            if match:
                potential_parent = match.group(1).strip()
                
                # Look for companies with similar names
                parent_companies = self._find_companies_by_name(session, potential_parent)
                for company_id, company_name in parent_companies:
                    candidates.append((company_id, company_name, "pattern_match"))
        
        return candidates
    
    def _find_companies_by_name(self, session: Session, name: str) -> List[Tuple[int, str]]:
        """Find companies by name similarity."""
        companies = []
        
        try:
            # Try exact match first
            company = session.query(Company).filter(
                Company.name_norm == norm_name(name)
            ).first()
            
            if company:
                companies.append((company.company_id, company.name))
            else:
                # Try fuzzy matching
                # This could use the existing candidate retrieval system
                pass
        
        except Exception as e:
            logger.debug(f"Error finding companies by name '{name}': {e}")
        
        return companies
    
    def _verify_subsidiary_relationship(self, session: Session, assignee_name: str, parent_id: int) -> bool:
        """Verify that assignee is actually a subsidiary of the parent company."""
        try:
            # Check if assignee name contains parent company name
            parent = session.query(Company).filter(Company.company_id == parent_id).first()
            if not parent:
                return False
            
            # Simple heuristic: if assignee contains parent name, likely a subsidiary
            parent_words = set(norm_name(parent.name).split())
            assignee_words = set(norm_name(assignee_name).split())
            
            # At least 50% of parent company words should be in assignee name
            overlap = len(parent_words & assignee_words)
            overlap_ratio = overlap / len(parent_words) if parent_words else 0
            
            return overlap_ratio >= 0.5
        
        except Exception as e:
            logger.debug(f"Error verifying subsidiary relationship: {e}")
            return False
    
    def _is_academic_assignee(self, assignee_name: str) -> bool:
        """Check if assignee is academic/university."""
        return has_academic_keywords(assignee_name)
    
    def _is_likely_acronym(self, name: str) -> bool:
        """Check if name is likely an acronym."""
        # Simple heuristic: all caps, short length, no lowercase letters
        cleaned = re.sub(r'[^A-Za-z]', '', name)
        return (len(cleaned) <= 6 and 
                cleaned.isupper() and 
                len(cleaned) >= 2)
    
    def _find_acronym_expansions(self, acronym: str) -> List[str]:
        """Find potential expansions for acronyms."""
        # This could be enhanced with a lookup table of known acronyms
        # For now, return empty list
        return []
    
    def _compile_assignee_patterns(self):
        """Compile regex patterns for assignee name processing."""
        self.assignee_patterns = {
            'successor': re.compile(r'\bas\s+successor\s+(?:in\s+interest\s+)?to\b', re.IGNORECASE),
            'assignee_suffix': re.compile(r'\bas\s+assignee\s*$', re.IGNORECASE),
            'subsidiary_indicator': re.compile(r'\b(?:subsidiary|division|unit|affiliate)\s+of\b', re.IGNORECASE),
            'holding_company': re.compile(r'\b(?:holdings?|group)\b', re.IGNORECASE),
        }
    
    def get_resolution_stats(self, resolutions: List[AssigneeResolution]) -> Dict[str, Any]:
        """Get statistics about resolution results."""
        total = len(resolutions)
        resolved = sum(1 for r in resolutions if r.is_resolved)
        high_confidence = sum(1 for r in resolutions if r.is_high_confidence)
        
        methods = {}
        for resolution in resolutions:
            method = resolution.method
            methods[method] = methods.get(method, 0) + 1
        
        return {
            "total_assignees": total,
            "resolved_count": resolved,
            "resolution_rate": resolved / total if total > 0 else 0.0,
            "high_confidence_count": high_confidence,
            "high_confidence_rate": high_confidence / total if total > 0 else 0.0,
            "methods_used": methods,
            "average_confidence": sum(r.confidence for r in resolutions) / total if total > 0 else 0.0
        }
