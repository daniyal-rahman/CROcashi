"""
Asset resolution for CTGov pipeline.

This module handles:
- Drug name normalization and parsing
- Asset alias matching and disambiguation
- Asset creation for new drugs
- Integration with sponsor ownership for disambiguation
"""

import re
import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.models import Asset, AssetOwnership, Company, Trial
from ..mapping.normalize import norm_name, norm_name_loose


logger = logging.getLogger(__name__)


@dataclass
class DrugName:
    """Normalized drug name with metadata."""
    original: str
    normalized: str
    name_type: str  # 'inn', 'generic', 'brand', 'internal_code', 'unknown'
    confidence: float  # 0.0-1.0
    source_field: str  # Which CTGov field this came from


@dataclass
class AssetMatch:
    """Asset match result."""
    asset_id: int
    confidence: float
    match_type: str  # 'exact', 'fuzzy', 'sponsor_preferred'
    matched_alias: str
    heuristics: Dict[str, Any]


class AssetResolver:
    """Resolves drug names to assets with robust normalization and disambiguation."""
    
    # Stoplist for non-asset interventions
    NON_ASSET_TERMS = {
        'placebo', 'saline', 'vehicle', 'vitamin', 'standard of care', 'soc',
        'best supportive care', 'bsc', 'no treatment', 'observation',
        'sham', 'mock', 'dummy', 'control'
    }
    
    # Common suffixes to strip
    SUFFIXES_TO_STRIP = [
        r'\s*hydrochloride\b', r'\s*hcl\b', r'\s*sulfate\b', r'\s*phosphate\b',
        r'\s*acetate\b', r'\s*citrate\b', r'\s*sodium\b', r'\s*calcium\b',
        r'\s*tablet\b', r'\s*capsule\b', r'\s*injection\b', r'\s*oral\b',
        r'\s*iv\b', r'\s*intravenous\b', r'\s*subcutaneous\b', r'\s*sc\b',
        r'\s*mg\b', r'\s*ml\b', r'\s*mg/ml\b', r'\s*mg/kg\b'
    ]
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def extract_drug_names(self, trial_data: Dict[str, Any]) -> List[DrugName]:
        """
        Extract and normalize drug names from CTGov trial data.
        
        Args:
            trial_data: Raw CTGov trial JSON
            
        Returns:
            List of normalized drug names with metadata
        """
        drug_names = []
        
        try:
            protocol = trial_data.get('protocolSection', {})
            # Handle both old and new CTGov API structures
            arms_module = protocol.get('armsInterventionsModule', {})
            interventions = arms_module.get('interventions', [])
            
            for intervention in interventions:
                    if intervention.get('type') in ['DRUG', 'BIOLOGICAL']:
                        name = intervention.get('name', '').strip()
                        if name and not self._is_non_asset(name):
                            normalized = self._normalize_drug_name(name)
                            if normalized:
                                drug_names.append(DrugName(
                                    original=name,
                                    normalized=normalized,
                                    name_type=self._classify_name_type(normalized),
                                    confidence=self._assess_confidence(normalized),
                                    source_field='intervention.name'
                                ))
                        
                        # Check otherNames field
                        other_names = intervention.get('otherNames', [])
                        for other_name in other_names:
                            if other_name and not self._is_non_asset(other_name):
                                normalized = self._normalize_drug_name(other_name)
                                if normalized:
                                    drug_names.append(DrugName(
                                        original=other_name,
                                        normalized=normalized,
                                        name_type=self._classify_name_type(normalized),
                                        confidence=self._assess_confidence(normalized),
                                        source_field='intervention.otherNames'
                                    ))
        
        except Exception as e:
            self.logger.warning(f"Error extracting drug names: {e}")
        
        return drug_names
    
    def _normalize_drug_name(self, name: str) -> Optional[str]:
        """Normalize drug name for matching."""
        if not name or len(name.strip()) < 2:
            return None
        
        # Basic cleaning
        normalized = name.strip().lower()
        
        # Remove common suffixes
        for suffix_pattern in self.SUFFIXES_TO_STRIP:
            normalized = re.sub(suffix_pattern, '', normalized, flags=re.IGNORECASE)
        
        # Remove punctuation and extra whitespace
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Skip if too short after normalization
        if len(normalized) < 2:
            return None
        
        return normalized
    
    def _is_non_asset(self, name: str) -> bool:
        """Check if name is a non-asset intervention."""
        normalized = name.lower().strip()
        return any(term in normalized for term in self.NON_ASSET_TERMS)
    
    def _classify_name_type(self, normalized: str) -> str:
        """Classify the type of drug name."""
        # Check for internal codes (alphanumeric with possible hyphens)
        if re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', normalized):
            return 'internal_code'
        
        # Check for brand names (capitalized words)
        if re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)*$', normalized):
            return 'brand'
        
        # Default to generic/inn
        return 'generic'
    
    def _assess_confidence(self, normalized: str) -> float:
        """Assess confidence in the normalized name."""
        # Higher confidence for shorter, cleaner names
        if len(normalized) <= 20 and re.match(r'^[a-z\s]+$', normalized):
            return 0.9
        elif len(normalized) <= 30:
            return 0.7
        else:
            return 0.5
    
    def resolve_assets(self, session: Session, drug_names: List[DrugName], 
                      sponsor_company_id: Optional[int] = None) -> List[AssetMatch]:
        """
        Resolve drug names to assets with disambiguation.
        
        Args:
            session: Database session
            drug_names: List of normalized drug names
            sponsor_company_id: Optional sponsor company ID for disambiguation
            
        Returns:
            List of asset matches with confidence scores
        """
        matches = []
        
        for drug_name in drug_names:
            # Look for exact matches in aliases
            exact_matches = self._find_exact_matches(session, drug_name.normalized)
            
            if exact_matches:
                # Disambiguate if multiple matches
                if len(exact_matches) == 1:
                    matches.append(AssetMatch(
                        asset_id=exact_matches[0].asset_id,
                        confidence=drug_name.confidence,
                        match_type='exact',
                        matched_alias=drug_name.normalized,
                        heuristics={'method': 'exact_alias_match'}
                    ))
                else:
                    # Multiple matches - use sponsor preference
                    best_match = self._disambiguate_matches(
                        session, exact_matches, sponsor_company_id
                    )
                    matches.append(AssetMatch(
                        asset_id=best_match.asset_id,
                        confidence=drug_name.confidence * 0.8,  # Slight penalty for ambiguity
                        match_type='exact',
                        matched_alias=drug_name.normalized,
                        heuristics={'method': 'exact_alias_match', 'disambiguation': 'sponsor_preference'}
                    ))
            
            # Try fuzzy matching if no exact match
            elif drug_name.confidence > 0.7:
                fuzzy_matches = self._find_fuzzy_matches(session, drug_name.normalized)
                if fuzzy_matches:
                    best_match = self._disambiguate_matches(
                        session, fuzzy_matches, sponsor_company_id
                    )
                    matches.append(AssetMatch(
                        asset_id=best_match.asset_id,
                        confidence=drug_name.confidence * 0.6,  # Penalty for fuzzy match
                        match_type='fuzzy',
                        matched_alias=best_match.alias,
                        heuristics={'method': 'fuzzy_match', 'original': drug_name.normalized}
                    ))
        
        return matches
    
    def _find_exact_matches(self, session: Session, normalized_name: str) -> List[Asset]:
        """Find exact matches in asset names (asset_aliases table removed)."""
        # Since asset_aliases table is removed, match against asset names directly
        return session.query(Asset).filter(
            Asset.names_jsonb.op('->>')('inn') == normalized_name
        ).all()
    
    def _find_fuzzy_matches(self, session: Session, normalized_name: str) -> List[Asset]:
        """Find fuzzy matches using trigram similarity on asset names."""
        # Use PostgreSQL trigram similarity on asset names since asset_aliases is removed
        query = text("""
            SELECT a.*, similarity(a.names_jsonb->>'inn', :name) as sim_score
            FROM assets a
            WHERE a.names_jsonb->>'inn' % :name
            ORDER BY sim_score DESC
            LIMIT 5
        """)
        
        result = session.execute(query, {'name': normalized_name})
        return [Asset(**row._asdict()) for row in result]
    
    def _disambiguate_matches(self, session: Session, matches: List[Asset], 
                             sponsor_company_id: Optional[int]) -> Asset:
        """Disambiguate between multiple asset matches."""
        if len(matches) == 1:
            return matches[0]
        
        # If sponsor is known, prefer assets owned by sponsor
        if sponsor_company_id:
            for match in matches:
                ownership = session.query(AssetOwnership).filter(
                    AssetOwnership.asset_id == match.asset_id,
                    AssetOwnership.company_id == sponsor_company_id
                ).first()
                if ownership:
                    return match
        
        # Fallback to first match (could be enhanced with more heuristics)
        return matches[0]
    
    def create_asset_if_needed(self, session: Session, drug_name: DrugName) -> Optional[int]:
        """
        Create a new asset if the drug name is confident and doesn't exist.
        
        Args:
            session: Database session
            drug_name: Normalized drug name
            
        Returns:
            New asset_id if created, None otherwise
        """
        # Only create for high-confidence names
        if drug_name.confidence < 0.8:
            return None
        
        # Check if already exists (asset_aliases table removed)
        existing = session.query(Asset).filter(
            Asset.names_jsonb.op('->>')('inn') == drug_name.normalized
        ).first()
        
        if existing:
            return existing.asset_id
        
        # Create new asset
        try:
            # Determine canonical name
            canonical_name = drug_name.original
            if drug_name.name_type == 'internal_code':
                canonical_name = drug_name.normalized.upper()
            
            # Create asset
            asset = Asset(
                names_jsonb={
                    'inn': canonical_name,
                    'synonyms': [drug_name.original],
                    'internal_codes': []
                }
            )
            session.add(asset)
            session.flush()
            
            # Note: AssetAlias table removed, aliases now stored in Asset.names_jsonb
            
            self.logger.info(f"Created new asset {asset.asset_id} for '{drug_name.original}'")
            return asset.asset_id
            
        except Exception as e:
            self.logger.error(f"Error creating asset for '{drug_name.original}': {e}")
            session.rollback()
            return None
    
    def link_trial_to_assets(self, session: Session, trial_id: int, nct_id: str,
                           asset_matches: List[AssetMatch]) -> None:
        """
        Link trial to matched assets via DocumentLink.
        
        Args:
            session: Database session
            trial_id: Trial ID
            nct_id: NCT ID
            asset_matches: List of asset matches
        """
        from ..db.models import Document, DocumentLink
        
        # Get or create registry document
        doc = session.query(Document).filter(
            Document.nct_id == nct_id,
            Document.source_type == 'Registry'
        ).first()
        
        if not doc:
            # Create registry document if it doesn't exist
            import hashlib
            doc = Document(
                source_type='Registry',
                source_url=f"https://clinicaltrials.gov/study/{nct_id}",
                url_hash=hashlib.sha256(f"ctgov:{nct_id}".encode()).hexdigest(),
                discovered_at=datetime.now(timezone.utc),
                content_type='registry',
                nct_id=nct_id,
                status='discovered',
                publisher='ClinicalTrials.gov'
            )
            session.add(doc)
            session.flush()
        
        # Create document links for each asset
        for match in asset_matches:
            # Check if link already exists
            existing_link = session.query(DocumentLink).filter(
                DocumentLink.doc_id == doc.doc_id,
                DocumentLink.nct_id == nct_id,
                DocumentLink.trial_id == trial_id,
                DocumentLink.asset_id == match.asset_id
            ).first()
            
            if not existing_link:
                # Get company_id from trial if available
                trial = session.query(Trial).filter(Trial.trial_id == trial_id).first()
                company_id = trial.sponsor_company_id if trial else None
                
                # If no company_id, we can't create the link due to NOT NULL constraint
                if company_id is None:
                    self.logger.warning(f"Cannot link trial {nct_id} to asset {match.asset_id}: no company_id")
                    continue
                
                link = DocumentLink(
                    doc_id=doc.doc_id,
                    nct_id=nct_id,
                    trial_id=trial_id,
                    asset_id=match.asset_id,
                    company_id=company_id,
                    link_type='asset_mapping',
                    confidence=match.confidence,
                    heuristics=match.heuristics,
                    evidence_json={
                        'match_type': match.match_type,
                        'matched_alias': match.matched_alias,
                        'resolved_at': datetime.now(timezone.utc).isoformat()
                    }
                )
                session.add(link)
                
                self.logger.info(f"Linked trial {nct_id} to asset {match.asset_id} "
                               f"(confidence: {match.confidence:.2f})")
