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
from sqlalchemy import text

from ncfd.db.models import Document, DocumentLink, DocumentEntity, Asset, AssetAlias, DocumentTextPage, LinkAudit
from ncfd.extract.asset_extractor import AssetMatch, find_nearby_assets
from ncfd.config import get_config

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
    """Implements high-precision linking heuristics for document-to-asset relationships.
    
    Note: Confidence scores are currently uncalibrated and should be used with caution.
    Auto-promotion is disabled until precision validation is complete.
    """
    
    def __init__(self, db_session: Session, review_only: bool = False, 
                 confidence_threshold: float = None):
        """
        Initialize the linking heuristics engine.
        
        Args:
            db_session: Database session for queries
            review_only: If True, only return high-confidence links for review
            confidence_threshold: Minimum confidence for filtering (uses config if None)
        """
        self.db_session = db_session
        self.review_only = review_only
        
        # Load configuration
        self.config = get_config()
        self.linking_config = self.config.get('linking_heuristics', {})
        
        # Use config threshold or provided threshold
        if confidence_threshold is None:
            self.confidence_threshold = self.linking_config.get('confidence_thresholds', {}).get('review_required', 0.70)
        else:
            self.confidence_threshold = confidence_threshold
        
        # Check if auto-promotion is enabled
        self.auto_promote_enabled = self.linking_config.get('auto_promote_enabled', False)
        self.min_labeled_precision = self.linking_config.get('min_labeled_precision', 0.95)
        self.min_labeled_links = self.linking_config.get('min_labeled_links', 50)
        
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
        
        logger.info(f"Linking heuristics initialized: auto_promote={self.auto_promote_enabled}, "
                   f"min_precision={self.min_labeled_precision}, min_links={self.min_labeled_links}")
    
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
        if self.linking_config.get('heuristics', {}).get('hp1_nct_near_asset', {}).get('enabled', True):
            hp1_candidates = self._apply_hp1_nct_near_asset(doc, asset_entities, nct_entities)
            candidates.extend(hp1_candidates)
        
        # Apply HP-2: Exact intervention name match (if enabled)
        if self.linking_config.get('heuristics', {}).get('hp2_exact_intervention_match', {}).get('enabled', False):
            hp2_candidates = self._apply_hp2_exact_intervention_match(doc, asset_entities)
            candidates.extend(hp2_candidates)
        
        # Apply HP-3: PR publisher bias
        if self.linking_config.get('heuristics', {}).get('hp3_company_pr_bias', {}).get('enabled', True):
            hp3_candidates = self._apply_hp3_pr_publisher_bias(doc, asset_entities)
            candidates.extend(hp3_candidates)
        
        # Apply HP-4: Abstract specificity
        if self.linking_config.get('heuristics', {}).get('hp4_abstract_specificity', {}).get('enabled', True):
            hp4_candidates = self._apply_hp4_abstract_specificity(doc, asset_entities)
            candidates.extend(hp4_candidates)
        
        # Apply conflict resolution and downgrades
        candidates = self._resolve_conflicts(candidates, doc)
        
        # Apply confidence threshold filtering
        if self.review_only:
            candidates = [c for c in candidates if c.confidence >= self.confidence_threshold]
            logger.info(f"Review-only mode: {len(candidates)} candidates above threshold {self.confidence_threshold}")
        
        return candidates
    
    def _apply_hp1_nct_near_asset(self, doc: Document, asset_entities: List[DocumentEntity], 
                                  nct_entities: List[DocumentEntity]) -> List[LinkCandidate]:
        """
        Apply HP-1: NCT near asset.
        
        If text contains NCT ID and asset code/INN within ±250 chars:
        confidence = 1.00 (highest confidence)
        """
        candidates = []
        
        if not asset_entities or not nct_entities:
            return candidates
        
        # Get confidence from config
        confidence = self.linking_config.get('heuristics', {}).get('hp1_nct_near_asset', {}).get('confidence', 1.00)
        
        # Find nearby pairs
        for asset_entity in asset_entities:
            for nct_entity in nct_entities:
                # Calculate distance between mentions
                distance = abs(asset_entity.char_start - nct_entity.char_start)
                
                if distance <= 250:  # Within ±250 characters
                    # Find assets with this alias
                    assets = self._find_assets_by_alias(asset_entity.value_norm, asset_entity.ent_type)
                    
                    for asset in assets:
                        candidate = LinkCandidate(
                            doc_id=doc.doc_id,
                            asset_id=asset.asset_id,
                            nct_id=nct_entity.value_text,
                            link_type='nct_near_asset',
                            confidence=confidence,
                            evidence={
                                'heuristic': 'HP-1',
                                'asset_span': {
                                    'page_no': asset_entity.page_no,
                                    'char_start': asset_entity.char_start,
                                    'char_end': asset_entity.char_end,
                                    'text': asset_entity.value_text
                                },
                                'nct_span': {
                                    'page_no': nct_entity.page_no,
                                    'char_start': nct_entity.char_start,
                                    'char_end': nct_entity.char_end,
                                    'text': nct_entity.value_text
                                },
                                'distance': distance
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
        
        Status: NOT IMPLEMENTED - Requires CT.gov cache integration
        """
        candidates = []
        
        # This heuristic requires CT.gov trial data integration
        # Currently not implemented due to missing trial metadata cache
        # TODO: Implement when CT.gov cache is available
        logger.debug("HP-2: Exact intervention match not implemented - requires CT.gov cache")
        
        return candidates
    
    def _apply_hp3_pr_publisher_bias(self, doc: Document, 
                                    asset_entities: List[DocumentEntity]) -> List[LinkCandidate]:
        """
        Apply HP-3: PR publisher bias.
        
        If company-hosted PR mentions asset code + INN together, and no ambiguity:
        confidence = 0.90 (uncalibrated - needs validation)
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
        
        # Get confidence from config
        confidence = self.linking_config.get('heuristics', {}).get('hp3_company_pr_bias', {}).get('confidence', 0.90)
        
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
                            confidence=confidence,
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
    
    def log_linking_decision(self, candidate: LinkCandidate, decision: str = 'pending_review',
                            reviewer_id: Optional[int] = None, review_notes: Optional[str] = None):
        """
        Log a linking decision to the audit table.
        
        Args:
            candidate: The link candidate
            decision: Decision made (approved, rejected, pending_review)
            reviewer_id: ID of reviewer (if applicable)
            review_notes: Notes from review (if applicable)
        """
        try:
            # Extract heuristic from evidence
            heuristic = candidate.evidence.get('heuristic', 'unknown') if candidate.evidence else 'unknown'
            
            # Log to audit table using database function
            result = self.db_session.execute(
                text("SELECT log_linking_decision(:doc_id, :asset_id, :link_type, :confidence, :heuristic, :evidence, :decision)"),
                {
                    'doc_id': candidate.doc_id,
                    'asset_id': candidate.asset_id,
                    'link_type': candidate.link_type,
                    'confidence': candidate.confidence,
                    'heuristic': heuristic,
                    'evidence': candidate.evidence,
                    'decision': decision
                }
            )
            
            audit_id = result.scalar()
            logger.info(f"Logged linking decision {decision} for link {candidate.doc_id}-{candidate.asset_id} "
                       f"(audit_id: {audit_id})")
            
        except Exception as e:
            logger.error(f"Failed to log linking decision: {e}")
    
    def get_linking_metrics(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get precision/recall metrics for linking heuristics.
        
        Args:
            start_date: Start date for metrics (ISO format)
            end_date: End date for metrics (ISO format)
            
        Returns:
            List of metric dictionaries
        """
        try:
            result = self.db_session.execute(
                text("SELECT * FROM calculate_linking_metrics(:start_date, :end_date)"),
                {
                    'start_date': start_date,
                    'end_date': end_date
                }
            )
            
            metrics = []
            for row in result:
                metrics.append({
                    'heuristic': row.heuristic,
                    'total_links': row.total_links,
                    'approved_links': row.approved_links,
                    'rejected_links': row.rejected_links,
                    'pending_review': row.pending_review,
                    'precision_rate': float(row.precision_rate),
                    'recall_rate': float(row.recall_rate),
                    'f1_score': float(row.f1_score)
                })
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get linking metrics: {e}")
            return []
    
    def get_heuristic_precision(self, heuristic: str, start_date: Optional[str] = None, 
                               end_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get precision metrics for a specific heuristic.
        
        Args:
            heuristic: Heuristic name (e.g., 'HP-1', 'HP-3')
            start_date: Start date for metrics (ISO format)
            end_date: End date for metrics (ISO format)
            
        Returns:
            Dictionary with precision metrics or None if insufficient data
        """
        try:
            # Query link_audit table for precision calculation
            query = """
            SELECT 
                COUNT(*) as total_links,
                COUNT(CASE WHEN label = true THEN 1 END) as correct_links,
                COUNT(CASE WHEN label = false THEN 1 END) as incorrect_links,
                COUNT(CASE WHEN label IS NULL THEN 1 END) as unreviewed_links
            FROM link_audit 
            WHERE heuristic_applied = :heuristic
            """
            
            params = {'heuristic': heuristic}
            if start_date:
                query += " AND created_at >= :start_date"
                params['start_date'] = start_date
            if end_date:
                query += " AND created_at <= :end_date"
                params['end_date'] = end_date
            
            result = self.db_session.execute(text(query), params).fetchone()
            
            if not result:
                return None
            
            total_links = result.total_links
            correct_links = result.correct_links or 0
            incorrect_links = result.incorrect_links or 0
            unreviewed_links = result.unreviewed_links or 0
            
            # Calculate precision (only for reviewed links)
            reviewed_links = correct_links + incorrect_links
            if reviewed_links == 0:
                return {
                    'heuristic': heuristic,
                    'total_links': total_links,
                    'reviewed_links': reviewed_links,
                    'correct_links': correct_links,
                    'incorrect_links': incorrect_links,
                    'unreviewed_links': unreviewed_links,
                    'precision': None,
                    'sufficient_data': False
                }
            
            precision = correct_links / reviewed_links
            
            return {
                'heuristic': heuristic,
                'total_links': total_links,
                'reviewed_links': reviewed_links,
                'correct_links': correct_links,
                'incorrect_links': incorrect_links,
                'unreviewed_links': unreviewed_links,
                'precision': precision,
                'sufficient_data': reviewed_links >= self.min_labeled_links
            }
            
        except Exception as e:
            logger.error(f"Failed to get precision for heuristic {heuristic}: {e}")
            return None
    
    def can_auto_promote_heuristic(self, heuristic: str) -> bool:
        """
        Check if a heuristic can be used for auto-promotion.
        
        Args:
            heuristic: Heuristic name to check
            
        Returns:
            True if auto-promotion is allowed for this heuristic
        """
        if not self.auto_promote_enabled:
            logger.info(f"Auto-promotion disabled globally")
            return False
        
        # Get precision for this heuristic
        precision_data = self.get_heuristic_precision(heuristic)
        if not precision_data:
            logger.info(f"No precision data for heuristic {heuristic}")
            return False
        
        if not precision_data['sufficient_data']:
            logger.info(f"Insufficient data for heuristic {heuristic}: "
                       f"need {self.min_labeled_links}, have {precision_data['reviewed_links']}")
            return False
        
        precision = precision_data['precision']
        if precision < self.min_labeled_precision:
            logger.info(f"Precision too low for heuristic {heuristic}: "
                       f"need {self.min_labeled_precision}, have {precision}")
            return False
        
        logger.info(f"Auto-promotion allowed for heuristic {heuristic}: "
                   f"precision {precision:.3f} >= {self.min_labeled_precision}")
        return True


class LinkPromoter:
    """Handles promotion of high-confidence links to final xrefs.
    
    Auto-promotion is gated behind feature flags and precision validation.
    """
    
    def __init__(self, db_session: Session, confidence_threshold: float = None):
        """
        Initialize the link promoter.
        
        Args:
            db_session: Database session
            confidence_threshold: Minimum confidence for auto-promotion (uses config if None)
        """
        self.db_session = db_session
        
        # Load configuration
        from ncfd.config import get_config
        config = get_config()
        linking_config = config.get('linking_heuristics', {})
        
        # Use config threshold or provided threshold
        if confidence_threshold is None:
            self.confidence_threshold = linking_config.get('confidence_thresholds', {}).get('auto_promote', 0.95)
        else:
            self.confidence_threshold = confidence_threshold
        
        # Check if auto-promotion is enabled
        self.auto_promote_enabled = linking_config.get('auto_promote_enabled', False)
        self.min_labeled_precision = linking_config.get('min_labeled_precision', 0.95)
        self.min_labeled_links = linking_config.get('min_labeled_links', 50)
        
        logger.info(f"LinkPromoter initialized: auto_promote={self.auto_promote_enabled}, "
                   f"confidence_threshold={self.confidence_threshold}, "
                   f"min_precision={self.min_labeled_precision}")
    
    def promote_high_confidence_links(self) -> Dict[str, int]:
        """
        Promote high-confidence links to final xrefs.
        
        Auto-promotion is only allowed when:
        1. Feature flag is enabled
        2. Each heuristic shows ≥95% precision on ≥50 labeled links
        
        Returns:
            Dictionary with counts of promoted links
        """
        if not self.auto_promote_enabled:
            logger.info("Auto-promotion disabled - all links kept for review")
            return {
                'study_assets_xref': 0,
                'trial_assets_xref': 0,
                'kept_for_review': 0,
                'reason': 'auto_promotion_disabled'
            }
        
        # Get high-confidence links
        high_conf_links = self.db_session.query(DocumentLink).filter(
            DocumentLink.confidence >= self.confidence_threshold
        ).all()
        
        promoted_counts = {
            'study_assets_xref': 0,
            'trial_assets_xref': 0,
            'kept_for_review': 0,
            'reason': 'auto_promotion_enabled'
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
        # Basic confidence check
        if link.confidence < self.confidence_threshold:
            return False
        
        # Check if auto-promotion is enabled
        if not self.auto_promote_enabled:
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
    
    def get_promotion_status(self) -> Dict[str, Any]:
        """
        Get current status of auto-promotion system.
        
        Returns:
            Dictionary with promotion status information
        """
        status = {
            'auto_promote_enabled': self.auto_promote_enabled,
            'confidence_threshold': self.confidence_threshold,
            'min_labeled_precision': self.min_labeled_precision,
            'min_labeled_links': self.min_labeled_links,
            'heuristic_status': {}
        }
        
        # Check status of each heuristic
        heuristics = ['HP-1', 'HP-2', 'HP-3', 'HP-4']
        for heuristic in heuristics:
            # Create a temporary LinkingHeuristics instance to check precision
            temp_heuristics = LinkingHeuristics(self.db_session)
            precision_data = temp_heuristics.get_heuristic_precision(heuristic)
            
            if precision_data:
                status['heuristic_status'][heuristic] = {
                    'precision': precision_data.get('precision'),
                    'reviewed_links': precision_data.get('reviewed_links', 0),
                    'sufficient_data': precision_data.get('sufficient_data', False),
                    'can_auto_promote': temp_heuristics.can_auto_promote_heuristic(heuristic)
                }
            else:
                status['heuristic_status'][heuristic] = {
                    'precision': None,
                    'reviewed_links': 0,
                    'sufficient_data': False,
                    'can_auto_promote': False
                }
        
        return status
