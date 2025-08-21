"""
Linking heuristics for document-to-asset relationships.

This module implements the high-precision linking heuristics (HP-1 through HP-4)
that populate document_links and enable promotion to final xrefs.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session

from ncfd.db.models import Document, DocumentLink, DocumentEntity, Asset, AssetAlias, DocumentTextPage
from ncfd.extract.asset_extractor import AssetMatch, find_nearby_assets

logger = logging.getLogger(__name__)


@dataclass
class LinkCandidate:
    """Represents a potential link between document and asset."""
    doc_id: int
    asset_id: int
    nct_id: Optional[str] = None
    company_id: Optional[int] = None
    link_type: str = ""
    confidence: float = 0.0
    evidence: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.evidence is None:
            self.evidence = {}


class LinkingHeuristics:
    """Implements high-precision linking heuristics for document-to-asset relationships."""
    
    def __init__(self, db_session: Session):
        """
        Initialize the linking heuristics engine.
        
        Args:
            db_session: Database session for queries
        """
        self.db_session = db_session
        
        # Phase and indication keywords for HP-4
        self.phase_keywords = [
            'phase i', 'phase ii', 'phase iii', 'phase iv',
            'phase 1', 'phase 2', 'phase 3', 'phase 4',
            'p1', 'p2', 'p3', 'p4'
        ]
        
        self.indication_keywords = [
            'cancer', 'oncology', 'tumor', 'metastatic',
            'breast', 'lung', 'colorectal', 'prostate',
            'leukemia', 'lymphoma', 'melanoma'
        ]
    
    def apply_heuristics(self, doc: Document) -> List[LinkCandidate]:
        """
        Apply all linking heuristics to a document.
        
        Args:
            doc: Document to analyze
            
        Returns:
            List of link candidates with confidence scores
        """
        candidates = []
        
        # Get document entities
        entities = self.db_session.query(DocumentEntity).filter(
            DocumentEntity.doc_id == doc.doc_id
        ).all()
        
        # Group entities by type
        asset_entities = [e for e in entities if e.ent_type in ['code', 'inn', 'generic']]
        nct_entities = [e for e in entities if e.ent_type == 'nct']
        
        # Apply HP-1: NCT near asset
        hp1_candidates = self._apply_hp1_nct_near_asset(doc, asset_entities, nct_entities)
        candidates.extend(hp1_candidates)
        
        # Apply HP-2: Exact intervention name match (if CT.gov cache available)
        hp2_candidates = self._apply_hp2_exact_intervention_match(doc, asset_entities)
        candidates.extend(hp2_candidates)
        
        # Apply HP-3: PR publisher bias
        hp3_candidates = self._apply_hp3_pr_publisher_bias(doc, asset_entities)
        candidates.extend(hp3_candidates)
        
        # Apply HP-4: Abstract specificity
        hp4_candidates = self._apply_hp4_abstract_specificity(doc, asset_entities)
        candidates.extend(hp4_candidates)
        
        # Apply conflict resolution and downgrades
        candidates = self._resolve_conflicts(candidates, doc)
        
        return candidates
    
    def _apply_hp1_nct_near_asset(self, doc: Document, asset_entities: List[DocumentEntity], 
                                  nct_entities: List[DocumentEntity]) -> List[LinkCandidate]:
        """
        Apply HP-1: NCT near asset heuristic.
        
        If text contains NCT ID and asset code/INN within ±250 chars:
        confidence = 1.00
        """
        candidates = []
        
        if not asset_entities or not nct_entities:
            return candidates
        
        # Convert to AssetMatch format for nearby detection
        asset_matches = []
        for entity in asset_entities:
            asset_match = AssetMatch(
                value_text=entity.value_text,
                value_norm=entity.value_norm or entity.value_text,
                alias_type=entity.ent_type,
                page_no=entity.page_no or 1,
                char_start=entity.char_start or 0,
                char_end=entity.char_end or 0,
                detector=entity.detector or 'unknown'
            )
            asset_matches.append(asset_match)
        
        nct_matches = []
        for entity in nct_entities:
            nct_match = AssetMatch(
                value_text=entity.value_text,
                value_norm=entity.value_norm or entity.value_text,
                alias_type='nct',
                page_no=entity.page_no or 1,
                char_start=entity.char_start or 0,
                char_end=entity.char_end or 0,
                detector=entity.detector or 'unknown'
            )
            nct_matches.append(nct_match)
        
        # Find nearby pairs
        nearby_pairs = find_nearby_assets(asset_matches, nct_matches, window_size=250)
        
        # Create link candidates for nearby pairs
        for asset_match, nct_match in nearby_pairs:
            # Find the asset by alias
            asset = self._find_asset_by_alias(asset_match.value_norm, asset_match.alias_type)
            if asset:
                candidate = LinkCandidate(
                    doc_id=doc.doc_id,
                    asset_id=asset.asset_id,
                    nct_id=nct_match.value_norm,
                    link_type='nct_near_asset',
                    confidence=1.00,
                    evidence={
                        'heuristic': 'HP-1',
                        'asset_span': {
                            'page_no': asset_match.page_no,
                            'char_start': asset_match.char_start,
                            'char_end': asset_match.char_end,
                            'text': asset_match.value_text
                        },
                        'nct_span': {
                            'page_no': nct_match.page_no,
                            'char_start': nct_match.char_start,
                            'char_end': nct_match.char_end,
                            'text': nct_match.value_text
                        },
                        'distance': abs(
                            (asset_match.char_start + asset_match.char_end) // 2 -
                            (nct_match.char_start + nct_match.char_end) // 2
                        )
                    }
                )
                candidates.append(candidate)
        
        return candidates
    
    def _apply_hp2_exact_intervention_match(self, doc: Document, 
                                          asset_entities: List[DocumentEntity]) -> List[LinkCandidate]:
        """
        Apply HP-2: Exact intervention name match.
        
        If asset alias_norm equals trial intervention name_norm (exact):
        confidence = 0.95
        
        Note: This requires CT.gov cache integration
        """
        candidates = []
        
        # This heuristic requires CT.gov trial data
        # For now, return empty list - would need integration with trial metadata
        # TODO: Implement when CT.gov cache is available
        
        return candidates
    
    def _apply_hp3_pr_publisher_bias(self, doc: Document, 
                                    asset_entities: List[DocumentEntity]) -> List[LinkCandidate]:
        """
        Apply HP-3: PR publisher bias.
        
        If company-hosted PR mentions asset code + INN together, and no ambiguity:
        confidence = 0.90
        """
        candidates = []
        
        # Only apply to PR documents
        if doc.source_type not in ['PR', 'IR']:
            return candidates
        
        # Check if this is company-hosted (not wire service)
        if not self._is_company_hosted(doc):
            return candidates
        
        # Group entities by type
        code_entities = [e for e in asset_entities if e.ent_type == 'code']
        inn_entities = [e for e in asset_entities if e.ent_type in ['inn', 'generic']]
        
        # Need both code and INN for this heuristic
        if not code_entities or not inn_entities:
            return candidates
        
        # Check for ambiguity (multiple assets)
        for code_entity in code_entities:
            # Find assets with this code
            assets_with_code = self._find_assets_by_alias(code_entity.value_norm, 'code')
            
            if len(assets_with_code) == 1:  # No ambiguity
                asset = assets_with_code[0]
                
                # Check if any INN entities are associated with this asset
                for inn_entity in inn_entities:
                    asset_aliases = self.db_session.query(AssetAlias).filter(
                        AssetAlias.asset_id == asset.asset_id,
                        AssetAlias.alias_type.in_(['inn', 'generic'])
                    ).all()
                    
                    if any(alias.alias_norm == inn_entity.value_norm for alias in asset_aliases):
                        candidate = LinkCandidate(
                            doc_id=doc.doc_id,
                            asset_id=asset.asset_id,
                            link_type='code_inn_company_pr',
                            confidence=0.90,
                            evidence={
                                'heuristic': 'HP-3',
                                'code_span': {
                                    'page_no': code_entity.page_no,
                                    'char_start': code_entity.char_start,
                                    'char_end': code_entity.char_end,
                                    'text': code_entity.value_text
                                },
                                'inn_span': {
                                    'page_no': inn_entity.page_no,
                                    'char_start': inn_entity.char_start,
                                    'char_end': inn_entity.char_end,
                                    'text': inn_entity.value_text
                                },
                                'company_hosted': True
                            }
                        )
                        candidates.append(candidate)
                        break
        
        return candidates
    
    def _apply_hp4_abstract_specificity(self, doc: Document, 
                                      asset_entities: List[DocumentEntity]) -> List[LinkCandidate]:
        """
        Apply HP-4: Abstract specificity.
        
        If abstract title contains code/INN and body mentions phase/indication:
        confidence = 0.85
        """
        candidates = []
        
        # Only apply to abstracts
        if doc.source_type != 'Abstract':
            return candidates
        
        # Get document text for analysis
        text_pages = self.db_session.query(DocumentTextPage).filter(
            DocumentTextPage.doc_id == doc.doc_id
        ).all()
        
        if not text_pages:
            return candidates
        
        # Combine all text
        full_text = ' '.join(page.text for page in text_pages)
        full_text_lower = full_text.lower()
        
        # Check for phase/indication keywords
        has_phase = any(keyword in full_text_lower for keyword in self.phase_keywords)
        has_indication = any(keyword in full_text_lower for keyword in self.indication_keywords)
        
        if not (has_phase or has_indication):
            return candidates
        
        # Process each asset entity
        for entity in asset_entities:
            asset = self._find_asset_by_alias(entity.value_norm, entity.ent_type)
            if not asset:
                continue
            
            # Check if code is unique to one asset
            if entity.ent_type == 'code':
                assets_with_code = self._find_assets_by_alias(entity.value_norm, 'code')
                if len(assets_with_code) > 1:
                    # Code collision - don't auto-promote
                    continue
            
            # Check if entity appears in title (approximate)
            title_text = doc.source_url or ""  # Use URL as proxy for title
            if entity.value_text.lower() in title_text.lower():
                candidate = LinkCandidate(
                    doc_id=doc.doc_id,
                    asset_id=asset.asset_id,
                    link_type='abstract_specificity',
                    confidence=0.85,
                    evidence={
                        'heuristic': 'HP-4',
                        'entity_span': {
                            'page_no': entity.page_no,
                            'char_start': entity.char_start,
                            'char_end': entity.char_end,
                            'text': entity.value_text
                        },
                        'has_phase': has_phase,
                        'has_indication': has_indication,
                        'in_title': entity.value_text.lower() in title_text.lower(),
                        'code_unique': len(self._find_assets_by_alias(entity.value_norm, 'code')) == 1
                    }
                )
                candidates.append(candidate)
        
        return candidates
    
    def _resolve_conflicts(self, candidates: List[LinkCandidate], doc: Document) -> List[LinkCandidate]:
        """
        Apply conflict resolution and downgrades.
        
        - If multiple assets match same doc with no combo wording → downgrade by 0.20
        - If combo detected → allow multiple assets, no downgrade
        """
        if len(candidates) <= 1:
            return candidates
        
        # Group candidates by asset_id
        asset_groups = {}
        for candidate in candidates:
            if candidate.asset_id not in asset_groups:
                asset_groups[candidate.asset_id] = []
            asset_groups[candidate.asset_id].append(candidate)
        
        # Check for combo wording in document
        has_combo = self._detect_combo_wording(doc)
        
        if has_combo:
            # Allow multiple assets, no downgrade
            return candidates
        
        # Multiple assets without combo - apply downgrades
        if len(asset_groups) > 1:
            for candidate in candidates:
                candidate.confidence = max(0.0, candidate.confidence - 0.20)
                candidate.evidence['conflict_resolution'] = 'downgraded_multiple_assets'
                candidate.evidence['original_confidence'] = candidate.confidence + 0.20
        
        return candidates
    
    def _detect_combo_wording(self, doc: Document) -> bool:
        """Detect combination therapy wording in document."""
        combo_patterns = [
            r'\bcombination\b',
            r'\bcombo\b',
            r'\bplus\b',
            r'\b\+',
            r'\bin combination with\b',
            r'\barm\s+\w+',
            r'\bcohort\s+\w+'
        ]
        
        text_pages = self.db_session.query(DocumentTextPage).filter(
            DocumentTextPage.doc_id == doc.doc_id
        ).all()
        
        if not text_pages:
            return False
        
        full_text = ' '.join(page.text for page in text_pages)
        
        for pattern in combo_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return True
        
        return False
    
    def _is_company_hosted(self, doc: Document) -> bool:
        """Check if document is hosted by company (not wire service)."""
        # Simple heuristic: check if source_url contains company domain patterns
        # This could be enhanced with company domain database
        wire_services = ['prnewswire', 'businesswire', 'globenewswire', 'marketwired']
        
        if not doc.source_url:
            return False
        
        url_lower = doc.source_url.lower()
        return not any(wire in url_lower for wire in wire_services)
    
    def _find_asset_by_alias(self, alias_norm: str, alias_type: str) -> Optional[Asset]:
        """Find asset by normalized alias."""
        alias = self.db_session.query(AssetAlias).filter(
            AssetAlias.alias_norm == alias_norm,
            AssetAlias.alias_type == alias_type
        ).first()
        
        if alias:
            return alias.asset
        return None
    
    def _find_assets_by_alias(self, alias_norm: str, alias_type: str) -> List[Asset]:
        """Find all assets with a given alias."""
        aliases = self.db_session.query(AssetAlias).filter(
            AssetAlias.alias_norm == alias_norm,
            AssetAlias.alias_type == alias_type
        ).all()
        
        return [alias.asset for alias in aliases if alias.asset]


class LinkPromoter:
    """Handles promotion of high-confidence links to final xrefs."""
    
    def __init__(self, db_session: Session, confidence_threshold: float = 0.95):
        """
        Initialize the link promoter.
        
        Args:
            db_session: Database session
            confidence_threshold: Minimum confidence for auto-promotion
        """
        self.db_session = db_session
        self.confidence_threshold = confidence_threshold
    
    def promote_high_confidence_links(self) -> Dict[str, int]:
        """
        Promote high-confidence links to final xrefs.
        
        Returns:
            Dictionary with counts of promoted links
        """
        # Get high-confidence links
        high_conf_links = self.db_session.query(DocumentLink).filter(
            DocumentLink.confidence >= self.confidence_threshold
        ).all()
        
        promoted_counts = {
            'study_assets_xref': 0,
            'trial_assets_xref': 0,
            'kept_for_review': 0
        }
        
        for link in high_conf_links:
            try:
                # Check if this should be promoted
                if self._should_promote_link(link):
                    self._promote_link(link)
                    
                    if link.nct_id:
                        promoted_counts['trial_assets_xref'] += 1
                    else:
                        promoted_counts['study_assets_xref'] += 1
                else:
                    promoted_counts['kept_for_review'] += 1
                    
            except Exception as e:
                logger.error(f"Failed to promote link {link.doc_id}-{link.asset_id}: {e}")
                promoted_counts['kept_for_review'] += 1
        
        return promoted_counts
    
    def _should_promote_link(self, link: DocumentLink) -> bool:
        """Determine if a link should be promoted."""
        # Basic checks
        if link.confidence < self.confidence_threshold:
            return False
        
        # Check if link is already promoted
        # TODO: Implement check against existing xref tables
        
        return True
    
    def _promote_link(self, link: DocumentLink):
        """Promote a link to final xref tables."""
        # TODO: Implement actual promotion to study_assets_xref and trial_assets_xref
        # For now, just mark as ready for promotion
        
        # Update link status or create promotion record
        link.evidence = link.evidence or {}
        link.evidence['promoted_at'] = 'pending_implementation'
        
        logger.info(f"Link {link.doc_id}-{link.asset_id} marked for promotion "
                   f"(confidence: {link.confidence})")
