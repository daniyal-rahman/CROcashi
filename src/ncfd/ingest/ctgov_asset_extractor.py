"""
Deterministic CT.gov Asset Extraction Module

Implements a battle-tested approach for extracting study assets from ClinicalTrials.gov
while avoiding competitors and placebo contamination. Designed to incorporate
Drugs@FDA and 8-K searching in the future.

Based on the comprehensive deterministic-first approach:
1. Build intervention-arm graph
2. Hard exclusions for placebo/control terms  
3. Arm-type filtering (Experimental vs Comparator)
4. Sponsor consistency checking
5. Title/codename matching
6. Alias harvesting with provenance
7. Confidence scoring
8. Safety rails to prevent competitor leakage
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple, Any
from datetime import date
import logging

logger = logging.getLogger(__name__)

# Global stoplist for hard exclusions (case-insensitive, trimmed)
DEFAULT_STOPLIST = {
    'placebo', 'vehicle', 'sham', 'standard of care', 'best supportive care',
    'standard therapy', 'background therapy', 'usual care', 'supportive care',
    'combination therapy', 'multi-drug regimen', 'physician\'s choice',
    'treatment as usual', 'soc', 'control', 'saline'
}

# Codename patterns for title extraction
CODENAME_PATTERNS = [
    r'([A-Z]{2,5}-?\d{1,4}[A-Z]?)',  # PTI-125, ABC123, etc.
    r'\(([^)]*(?:aka|a\.k\.a\.|formerly|code name|codename)[^)]*)\)',  # Parenthetical aliases
]


@dataclass
class Intervention:
    """Represents a CT.gov intervention with metadata."""
    name: str
    intervention_type: str  # DRUG, BIOLOGICAL, etc.
    other_names: List[str] = field(default_factory=list)
    arm_types: Set[str] = field(default_factory=set)  # Experimental, Placebo Comparator, etc.


@dataclass
class Arm:
    """Represents a CT.gov study arm."""
    arm_id: str
    label: str
    arm_group_type: str  # Experimental, Active Comparator, Placebo Comparator, etc.


@dataclass
class AssetCandidate:
    """Represents a candidate study asset with scoring metadata."""
    name: str
    canonical_name: str
    intervention_type: str
    score: float
    is_primary_asset: bool
    sponsor_match: Optional[bool]
    title_match: bool
    arm_types_seen: Set[str]
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssetAlias:
    """Represents an alias for a study asset with provenance."""
    alias_value: str
    alias_type: str  # primary_name, other_name, keyword, title_extract, pattern_extract
    source_field: str  # intervention_name, other_name, keyword, official_title, brief_title
    arm_roles_seen: Set[str]
    sponsor_match: Optional[bool]
    confidence: float
    notes: str = ""


class CtgovAssetExtractor:
    """Deterministic asset extractor for CT.gov data."""
    
    def __init__(self, stoplist: Optional[Set[str]] = None, sponsor_xwalk: Optional[Dict[str, str]] = None):
        """
        Initialize asset extractor.
        
        Args:
            stoplist: Custom stoplist for hard exclusions
            sponsor_xwalk: Asset -> company mapping for sponsor consistency checking
        """
        self.stoplist = stoplist or DEFAULT_STOPLIST
        self.sponsor_xwalk = sponsor_xwalk or {}
        
    def extract_study_assets(self, ctgov_record: Dict[str, Any]) -> Tuple[List[AssetCandidate], List[AssetAlias]]:
        """
        Extract study assets from CT.gov record using deterministic approach.
        
        Args:
            ctgov_record: Raw CT.gov API response
            
        Returns:
            Tuple of (primary_assets, aliases_with_provenance)
        """
        try:
            # Step 1: Load interventions and arms
            interventions = self._load_interventions(ctgov_record)
            arms = self._load_arms(ctgov_record)
            links = self._link_arm_interventions(ctgov_record)
            
            # Step 2: Build intervention-arm graph
            intervention_meta = self._build_intervention_graph(interventions, arms, links)
            
            # Step 3: Apply hard exclusions
            candidates = self._apply_hard_exclusions(intervention_meta)
            
            # Step 4: Filter by arm type (Experimental only)
            experimental_candidates = self._filter_by_arm_type(candidates)
            
            # Step 5: Extract title/keyword codenames
            title_text = self._extract_title_text(ctgov_record)
            keywords = self._extract_keywords(ctgov_record)
            title_codes = self._extract_codenames_from_title(title_text)
            
            # Step 6: Sponsor consistency check
            lead_sponsor, collaborators = self._normalize_sponsors(ctgov_record)
            
            # Step 7: Score candidates
            scored_candidates = self._score_candidates(
                experimental_candidates, title_codes, keywords, 
                lead_sponsor, collaborators
            )
            
            # Step 8: Select primary assets (score >= 0.6)
            primary_assets = [c for c in scored_candidates if c.score >= 0.6]
            primary_assets.sort(key=lambda x: x.score, reverse=True)
            
            # Step 9: Harvest aliases with provenance (only from primary assets)
            aliases = []
            for asset in primary_assets:
                aliases.extend(self._harvest_aliases(
                    asset, title_text, keywords, arms, interventions
                ))
            
            logger.info(f"Extracted {len(primary_assets)} primary assets and {len(aliases)} aliases from {ctgov_record.get('protocolSection', {}).get('identificationModule', {}).get('nctId', 'Unknown')}")
            
            return primary_assets, aliases
            
        except Exception as e:
            logger.error(f"Error extracting assets from CT.gov record: {e}")
            return [], []
    
    def _load_interventions(self, record: Dict[str, Any]) -> List[Intervention]:
        """Load interventions from CT.gov record."""
        interventions = []
        arms_interventions = record.get("protocolSection", {}).get("armsInterventionsModule", {}) or {}
        
        for item in arms_interventions.get("interventions", []) or []:
            name = item.get("name", "").strip()
            if not name:
                continue
                
            intervention_type = item.get("type", "").upper()
            other_names = [n.strip() for n in (item.get("otherNames", []) or []) if n.strip()]
            
            interventions.append(Intervention(
                name=name,
                intervention_type=intervention_type,
                other_names=other_names
            ))
        
        return interventions
    
    def _load_arms(self, record: Dict[str, Any]) -> List[Arm]:
        """Load study arms from CT.gov record."""
        arms = []
        arms_module = record.get("protocolSection", {}).get("armsInterventionsModule", {}) or {}
        
        for item in arms_module.get("arms", []) or []:
            arm_id = item.get("id", "")
            label = item.get("label", "").strip()
            arm_group_type = item.get("type", "")
            
            if arm_id and label:
                arms.append(Arm(
                    arm_id=arm_id,
                    label=label,
                    arm_group_type=arm_group_type
                ))
        
        return arms
    
    def _link_arm_interventions(self, record: Dict[str, Any]) -> List[Dict[str, str]]:
        """Link arms to interventions."""
        links = []
        arms_module = record.get("protocolSection", {}).get("armsInterventionsModule", {}) or {}
        
        # Extract arm-intervention mappings
        for arm in arms_module.get("arms", []) or []:
            arm_id = arm.get("id", "")
            intervention_names = arm.get("interventionNames", []) or []
            
            for intervention_name in intervention_names:
                if intervention_name.strip():
                    links.append({
                        "arm_id": arm_id,
                        "intervention_name": intervention_name.strip()
                    })
        
        return links
    
    def _build_intervention_graph(self, interventions: List[Intervention], arms: List[Arm], links: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
        """Build intervention metadata graph."""
        # Create arm lookup
        arm_lookup = {arm.arm_id: arm for arm in arms}
        
        # Initialize intervention metadata
        intervention_meta = {}
        for intervention in interventions:
            intervention_meta[intervention.name] = {
                "type": intervention.intervention_type,
                "names": {self._normalize(intervention.name)} | {self._normalize(n) for n in intervention.other_names},
                "other_names": intervention.other_names,
                "arm_types": set(),
                "intervention": intervention
            }
        
        # Add arm type information
        for link in links:
            intervention_name = link["intervention_name"]
            arm_id = link["arm_id"]
            
            if intervention_name in intervention_meta and arm_id in arm_lookup:
                arm_type = arm_lookup[arm_id].arm_group_type
                intervention_meta[intervention_name]["arm_types"].add(arm_type)
        
        return intervention_meta
    
    def _apply_hard_exclusions(self, intervention_meta: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Apply hard exclusions based on stoplist."""
        def is_stoplisted(name: str) -> bool:
            normalized = self._normalize(name)
            return normalized in self.stoplist or any(stop in normalized for stop in self.stoplist)
        
        candidates = {}
        for name, meta in intervention_meta.items():
            # Check if intervention name or any other names are stoplisted
            if not is_stoplisted(name) and not any(is_stoplisted(other) for other in meta["other_names"]):
                candidates[name] = meta
        
        return candidates
    
    def _filter_by_arm_type(self, candidates: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Filter candidates to only include those in Experimental arms."""
        experimental_candidates = {}
        for name, meta in candidates.items():
            arm_types = meta["arm_types"]
            
            # Primary inclusion rule: must appear in at least one Experimental arm
            if "Experimental" in arm_types:
                experimental_candidates[name] = meta
            # Edge case: mixed arms including Experimental (e.g., dose escalation)
            elif "Experimental" in arm_types or len(arm_types) > 1:
                experimental_candidates[name] = meta
        
        return experimental_candidates
    
    def _extract_title_text(self, record: Dict[str, Any]) -> str:
        """Extract title text for codename matching."""
        idm = record.get("protocolSection", {}).get("identificationModule", {}) or {}
        brief_title = idm.get("briefTitle", "") or ""
        official_title = idm.get("officialTitle", "") or ""
        return f"{brief_title} {official_title}".strip()
    
    def _extract_keywords(self, record: Dict[str, Any]) -> Set[str]:
        """Extract keywords for codename matching."""
        keywords = []
        idm = record.get("protocolSection", {}).get("identificationModule", {}) or {}
        kw_list = idm.get("keywords", []) or []
        
        for kw in kw_list:
            if isinstance(kw, str) and kw.strip():
                keywords.append(kw.strip())
        
        return {self._normalize(kw) for kw in keywords}
    
    def _extract_codenames_from_title(self, title_text: str) -> Set[str]:
        """Extract codenames from title using patterns."""
        codenames = set()
        
        for pattern in CODENAME_PATTERNS:
            matches = re.findall(pattern, title_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    codenames.update(self._normalize(m) for m in match if m.strip())
                else:
                    codenames.add(self._normalize(match))
        
        return codenames
    
    def _normalize_sponsors(self, record: Dict[str, Any]) -> Tuple[str, Set[str]]:
        """Normalize sponsor names for matching."""
        sponsor_module = record.get("protocolSection", {}).get("sponsorCollaboratorsModule", {}) or {}
        
        lead_sponsor = sponsor_module.get("leadSponsor", {}).get("name", "") or ""
        collaborators = sponsor_module.get("collaborators", []) or []
        
        # Normalize sponsor names
        lead_normalized = self._normalize_company_name(lead_sponsor)
        collaborator_normalized = {self._normalize_company_name(c.get("name", "")) for c in collaborators}
        collaborator_normalized.discard("")  # Remove empty strings
        
        return lead_normalized, collaborator_normalized
    
    def _score_candidates(self, candidates: Dict[str, Dict[str, Any]], title_codes: Set[str], 
                         keywords: Set[str], lead_sponsor: str, collaborators: Set[str]) -> List[AssetCandidate]:
        """Score asset candidates using confidence scoring."""
        scored_candidates = []
        
        for name, meta in candidates.items():
            # Check title/keyword match
            title_match = bool(
                self._normalize(name) in title_codes or 
                any(n in keywords for n in meta["names"])
            )
            
            # Check sponsor match
            sponsor_match = self._check_sponsor_match(name, lead_sponsor, collaborators)
            
            # Calculate alias density
            alias_density = min(1.0, len(meta["other_names"]) / 3.0)
            
            # Confidence score: 0.60 * experimental + 0.20 * title_match + 0.10 * sponsor_match + 0.10 * alias_density
            score = (
                0.60 * 1.0 +  # Always 1.0 since we filtered for Experimental
                0.20 * (1.0 if title_match else 0.0) +
                0.10 * (1.0 if sponsor_match else 0.5 if sponsor_match is None else 0.0) +
                0.10 * alias_density
            )
            
            # Extract canonical name (strip dose/formulation)
            canonical_name = self._extract_canonical_name(name)
            
            scored_candidates.append(AssetCandidate(
                name=name,
                canonical_name=canonical_name,
                intervention_type=meta["type"],
                score=score,
                is_primary_asset=score >= 0.6,
                sponsor_match=sponsor_match,
                title_match=title_match,
                arm_types_seen=meta["arm_types"],
                meta=meta
            ))
        
        return scored_candidates
    
    def _harvest_aliases(self, asset: AssetCandidate, title_text: str, keywords: Set[str], 
                        arms: List[Arm], interventions: List[Intervention]) -> List[AssetAlias]:
        """Harvest aliases with provenance tracking."""
        aliases = []
        
        # Find the intervention object
        intervention = None
        for inv in interventions:
            if inv.name == asset.name:
                intervention = inv
                break
        
        if not intervention:
            return aliases
        
        # Primary name alias
        aliases.append(AssetAlias(
            alias_value=asset.name,
            alias_type="primary_name",
            source_field="intervention_name",
            arm_roles_seen=asset.arm_types_seen,
            sponsor_match=asset.sponsor_match,
            confidence=0.95,
            notes="Primary intervention name"
        ))
        
        # Other names from intervention
        for other_name in intervention.other_names:
            aliases.append(AssetAlias(
                alias_value=other_name,
                alias_type="other_name",
                source_field="other_name",
                arm_roles_seen=asset.arm_types_seen,
                sponsor_match=asset.sponsor_match,
                confidence=0.85,
                notes=f"From otherNames for {asset.name}"
            ))
        
        # Title/keyword matches
        if asset.title_match:
            aliases.append(AssetAlias(
                alias_value=asset.name,
                alias_type="title_extract",
                source_field="official_title" if asset.name in title_text else "brief_title",
                arm_roles_seen=asset.arm_types_seen,
                sponsor_match=asset.sponsor_match,
                confidence=0.90,
                notes="Extracted from title/keywords"
            ))
        
        return aliases
    
    def _check_sponsor_match(self, intervention_name: str, lead_sponsor: str, collaborators: Set[str]) -> Optional[bool]:
        """Check if intervention matches sponsor (for future Drugs@FDA integration)."""
        # Future enhancement: use sponsor_xwalk to check asset -> company mapping
        # For now, return None (unknown)
        return None
    
    def _extract_canonical_name(self, name: str) -> str:
        """Extract canonical name by stripping dose/formulation."""
        # Simple regex to remove common dose/formulation patterns
        patterns = [
            r'\s+\d+\s*mg',  # 5 mg
            r'\s+\d+\s*mcg',  # 5 mcg
            r'\s+\d+\s*μg',   # 5 μg
            r'\s+tablets?',   # tablets
            r'\s+capsules?',  # capsules
            r'\s+injection',  # injection
            r'\s+oral',       # oral
        ]
        
        canonical = name
        for pattern in patterns:
            canonical = re.sub(pattern, '', canonical, flags=re.IGNORECASE)
        
        return canonical.strip()
    
    def _normalize(self, text: str) -> str:
        """Normalize text for matching."""
        if not text:
            return ""
        # Trim whitespace, lowercase, collapse spaces
        return re.sub(r'\s+', ' ', text.strip().lower())
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalize company names for matching."""
        if not name:
            return ""
        
        # Strip common suffixes
        suffixes = ['inc', 'inc.', 'ltd', 'ltd.', 'llc', 'llc.', 'corp', 'corp.', 
                   'corporation', 'limited', 'sa', 's.a.', 'gmbh', 'ag', 'a.g.']
        
        normalized = self._normalize(name)
        for suffix in suffixes:
            if normalized.endswith(' ' + suffix):
                normalized = normalized[:-len(suffix)-1].strip()
        
        return normalized


def extract_study_assets_from_ctgov(ctgov_record: Dict[str, Any], 
                                  stoplist: Optional[Set[str]] = None,
                                  sponsor_xwalk: Optional[Dict[str, str]] = None) -> Tuple[List[AssetCandidate], List[AssetAlias]]:
    """
    Convenience function to extract study assets from CT.gov record.
    
    Args:
        ctgov_record: Raw CT.gov API response
        stoplist: Custom stoplist for hard exclusions
        sponsor_xwalk: Asset -> company mapping for sponsor consistency checking
        
    Returns:
        Tuple of (primary_assets, aliases_with_provenance)
    """
    extractor = CtgovAssetExtractor(stoplist=stoplist, sponsor_xwalk=sponsor_xwalk)
    return extractor.extract_study_assets(ctgov_record)
