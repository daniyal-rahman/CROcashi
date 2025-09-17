"""
Asset-Patent Linking Engine

Links assets to patents using multiple evidence sources:
1. INN exact match in patent text
2. Internal code mentions in patent abstracts/claims
3. Company assignee + temporal proximity
4. Text similarity with confidence scoring

Follows the existing asset mapping patterns in the codebase.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.models import Asset, Patent, Company
from ..ingest.uspto.patent_types import PatentLinkCandidate
from ..extract.models.evidence_span import Span

logger = logging.getLogger(__name__)


@dataclass
class PatentLinkResult:
    """Result of asset-patent linking operation."""
    asset_id: int
    patent_id: int
    confidence_score: float
    link_method: str
    evidence_spans: List[Dict[str, Any]]
    match_details: Dict[str, Any]
    
    @property
    def is_high_confidence(self) -> bool:
        """Check if this is a high confidence link."""
        return self.confidence_score >= 0.85
    
    @property
    def is_acceptable(self) -> bool:
        """Check if link meets minimum confidence threshold."""
        return self.confidence_score >= 0.60


class AssetPatentLinker:
    """
    Links assets to patents using multiple evidence sources.
    
    Uses a multi-stage approach:
    1. INN exact matches (high confidence)
    2. Internal code mentions (high confidence)
    3. Assignee + temporal matching (medium confidence)
    4. Text similarity (lower confidence)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize asset-patent linker.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Confidence thresholds
        self.high_confidence_threshold = self.config.get("high_confidence", 0.85)
        self.medium_confidence_threshold = self.config.get("medium_confidence", 0.65)
        self.min_confidence_threshold = self.config.get("min_confidence", 0.40)
        
        # Temporal matching configuration
        self.max_temporal_distance_days = self.config.get("max_temporal_distance_days", 730)  # 2 years
        
        # Text similarity configuration
        self.min_similarity_score = self.config.get("min_similarity_score", 0.7)
        self.similarity_method = self.config.get("similarity_method", "fuzzy")
        
        # Compile regex patterns
        self._compile_patterns()
        
        logger.info("Initialized asset-patent linker")
    
    def link_asset_to_patents(self, session: Session, asset_id: int) -> List[PatentLinkResult]:
        """
        Link an asset to patents using multiple evidence sources.
        
        Args:
            session: Database session
            asset_id: Asset ID to link
            
        Returns:
            List of patent link results
        """
        logger.info(f"Linking asset {asset_id} to patents")
        
        # Get asset with aliases
        asset = self._get_asset_with_aliases(session, asset_id)
        if not asset:
            logger.warning(f"Asset {asset_id} not found")
            return []
        
        all_links = []
        
        # Stage 1: INN exact matches (highest confidence)
        inn_links = self._find_inn_matches(session, asset)
        all_links.extend(inn_links)
        logger.debug(f"Found {len(inn_links)} INN matches for asset {asset_id}")
        
        # Stage 2: Internal code mentions (high confidence)
        code_links = self._find_code_mentions(session, asset)
        all_links.extend(code_links)
        logger.debug(f"Found {len(code_links)} code mentions for asset {asset_id}")
        
        # Stage 3: Assignee + temporal matching (medium confidence)
        temporal_links = self._find_temporal_matches(session, asset)
        all_links.extend(temporal_links)
        logger.debug(f"Found {len(temporal_links)} temporal matches for asset {asset_id}")
        
        # Stage 4: Text similarity (lower confidence)
        similarity_links = self._find_similarity_matches(session, asset)
        all_links.extend(similarity_links)
        logger.debug(f"Found {len(similarity_links)} similarity matches for asset {asset_id}")
        
        # Deduplicate and score
        final_links = self._deduplicate_and_score(all_links)
        
        logger.info(f"Found {len(final_links)} total patent links for asset {asset_id}")
        return final_links
    
    def link_patent_to_assets(self, session: Session, patent_id: int) -> List[PatentLinkResult]:
        """
        Link a patent to assets (reverse direction).
        
        Args:
            session: Database session
            patent_id: Patent ID to link
            
        Returns:
            List of asset link results
        """
        logger.info(f"Linking patent {patent_id} to assets")
        
        # Get patent
        patent = session.query(Patent).filter(Patent.patent_id == patent_id).first()
        if not patent:
            logger.warning(f"Patent {patent_id} not found")
            return []
        
        # Find assets that mention this patent's content
        linked_assets = []
        
        # Search for INN mentions in patent text
        if patent.abstract or patent.title:
            patent_text = f"{patent.title or ''} {patent.abstract or ''}"
            asset_matches = self._find_assets_by_text_mentions(session, patent_text)
            
            for asset_id, match_score, match_method in asset_matches:
                link = PatentLinkResult(
                    asset_id=asset_id,
                    patent_id=patent_id,
                    confidence_score=match_score,
                    link_method=f"reverse_{match_method}",
                    evidence_spans=[],
                    match_details={"patent_text_match": True}
                )
                linked_assets.append(link)
        
        return linked_assets
    
    def batch_link_assets(self, session: Session, asset_ids: List[int]) -> Dict[int, List[PatentLinkResult]]:
        """
        Link multiple assets to patents in batch.
        
        Args:
            session: Database session
            asset_ids: List of asset IDs to link
            
        Returns:
            Dictionary mapping asset ID to list of patent links
        """
        logger.info(f"Batch linking {len(asset_ids)} assets to patents")
        
        results = {}
        
        for asset_id in asset_ids:
            try:
                links = self.link_asset_to_patents(session, asset_id)
                results[asset_id] = links
            except Exception as e:
                logger.error(f"Error linking asset {asset_id}: {e}")
                results[asset_id] = []
        
        return results
    
    def _get_asset_with_aliases(self, session: Session, asset_id: int) -> Optional[Dict[str, Any]]:
        """Get asset with all aliases."""
        try:
            # Get asset
            asset = session.query(Asset).filter(Asset.asset_id == asset_id).first()
            if not asset:
                return None
            
            # Extract names from JSONB
            names = asset.names_jsonb or {}
            inn = names.get('inn', '')
            internal_codes = names.get('internal_codes', [])
            generic_names = names.get('generic', [])
            brand_names = names.get('brand', [])
            synonyms = names.get('synonyms', [])
            
            # Combine all names
            alias_names = synonyms + generic_names + brand_names
            
            return {
                'asset_id': asset_id,
                'inn': inn,
                'internal_codes': internal_codes,
                'generic_names': generic_names,
                'brand_names': brand_names,
                'aliases': alias_names,
                'modality': asset.modality,
                'target': asset.target,
                'moa': asset.moa
            }
            
        except Exception as e:
            logger.error(f"Error getting asset {asset_id} with aliases: {e}")
            return None
    
    def _find_inn_matches(self, session: Session, asset: Dict[str, Any]) -> List[PatentLinkResult]:
        """Find patents that mention the asset's INN exactly."""
        links = []
        
        inn = asset.get('inn', '')
        if not inn or len(inn) < 3:  # Skip very short INNs
            return links
        
        try:
            # Search for INN in patent abstracts and titles
            query = text("""
                SELECT patent_id, title, abstract, assignees
                FROM patents
                WHERE (title ILIKE :inn_pattern OR abstract ILIKE :inn_pattern)
                AND jurisdiction = 'US'
                ORDER BY grant_date DESC NULLS LAST
                LIMIT 100
            """)
            
            inn_pattern = f"%{inn}%"
            results = session.execute(query, {"inn_pattern": inn_pattern}).fetchall()
            
            for row in results:
                patent_id, title, abstract, assignees = row
                
                # Verify this is actually an INN mention (not a substring)
                patent_text = f"{title or ''} {abstract or ''}"
                if self._verify_inn_mention(patent_text, inn):
                    
                    # Extract evidence spans
                    evidence_spans = self._extract_evidence_spans(patent_text, inn, patent_id)
                    
                    # High confidence for exact INN matches
                    confidence = 0.95
                    
                    link = PatentLinkResult(
                        asset_id=asset['asset_id'],
                        patent_id=patent_id,
                        confidence_score=confidence,
                        link_method='inn_exact',
                        evidence_spans=evidence_spans,
                        match_details={
                            'inn': inn,
                            'matches_found': len(evidence_spans),
                            'assignees': assignees
                        }
                    )
                    links.append(link)
                    
        except Exception as e:
            logger.error(f"Error finding INN matches for asset {asset['asset_id']}: {e}")
        
        return links
    
    def _find_code_mentions(self, session: Session, asset: Dict[str, Any]) -> List[PatentLinkResult]:
        """Find patents that mention internal asset codes."""
        links = []
        
        internal_codes = asset.get('internal_codes', [])
        if not internal_codes:
            return links
        
        try:
            for code in internal_codes:
                if len(code) < 3:  # Skip very short codes
                    continue
                
                # Search for code in patent text
                query = text("""
                    SELECT patent_id, title, abstract, assignees, grant_date
                    FROM patents
                    WHERE (title ILIKE :code_pattern OR abstract ILIKE :code_pattern)
                    AND jurisdiction = 'US'
                    ORDER BY grant_date DESC NULLS LAST
                    LIMIT 50
                """)
                
                code_pattern = f"%{code}%"
                results = session.execute(query, {"code_pattern": code_pattern}).fetchall()
                
                for row in results:
                    patent_id, title, abstract, assignees, grant_date = row
                    
                    # Verify this is actually a code mention
                    patent_text = f"{title or ''} {abstract or ''}"
                    if self._verify_code_mention(patent_text, code):
                        
                        # Extract evidence spans
                        evidence_spans = self._extract_evidence_spans(patent_text, code, patent_id)
                        
                        # High confidence for internal code matches
                        confidence = 0.90
                        
                        link = PatentLinkResult(
                            asset_id=asset['asset_id'],
                            patent_id=patent_id,
                            confidence_score=confidence,
                            link_method='code_mention',
                            evidence_spans=evidence_spans,
                            match_details={
                                'code': code,
                                'matches_found': len(evidence_spans),
                                'assignees': assignees,
                                'grant_date': grant_date
                            }
                        )
                        links.append(link)
                        
        except Exception as e:
            logger.error(f"Error finding code mentions for asset {asset['asset_id']}: {e}")
        
        return links
    
    def _find_temporal_matches(self, session: Session, asset: Dict[str, Any]) -> List[PatentLinkResult]:
        """Find patents based on assignee company and temporal proximity."""
        links = []
        
        try:
            # Get company that owns this asset
            asset_query = text("""
                SELECT owner_company_id
                FROM assets
                WHERE asset_id = :asset_id
                AND owner_company_id IS NOT NULL
            """)
            
            result = session.execute(asset_query, {"asset_id": asset['asset_id']}).first()
            ownerships = [result] if result and result[0] else []
            
            for ownership in ownerships:
                company_id = ownership[0]
                # Find patents assigned to this company
                company_patents = self._find_patents_by_assignee_company(session, company_id)
                
                for patent_id, grant_date, assignee_name in company_patents:
                    # Check temporal alignment
                    temporal_score = self._calculate_temporal_score(grant_date, start_date, end_date)
                    
                    if temporal_score > 0.5:  # Minimum temporal alignment
                        
                        # Medium confidence for temporal matches
                        confidence = 0.70 * temporal_score
                        
                        link = PatentLinkResult(
                            asset_id=asset['asset_id'],
                            patent_id=patent_id,
                            confidence_score=confidence,
                            link_method='assignee_temporal',
                            evidence_spans=[],
                            match_details={
                                'company_id': company_id,
                                'assignee_name': assignee_name,
                                'grant_date': grant_date,
                                'ownership_start': start_date,
                                'ownership_end': end_date,
                                'temporal_score': temporal_score
                            }
                        )
                        links.append(link)
                        
        except Exception as e:
            logger.error(f"Error finding temporal matches for asset {asset['asset_id']}: {e}")
        
        return links
    
    def _find_similarity_matches(self, session: Session, asset: Dict[str, Any]) -> List[PatentLinkResult]:
        """Find patents based on text similarity."""
        links = []
        
        try:
            # Build search text from asset names
            search_terms = []
            
            if asset.get('inn'):
                search_terms.append(asset['inn'])
            
            search_terms.extend(asset.get('generic_names', []))
            search_terms.extend(asset.get('brand_names', []))
            search_terms.extend(asset.get('aliases', []))
            
            # Add target and MOA for context
            if asset.get('target'):
                search_terms.append(asset['target'])
            if asset.get('moa'):
                search_terms.append(asset['moa'])
            
            # Search for patents with similar content
            for term in search_terms[:5]:  # Limit to avoid too many queries
                if len(term) < 4:  # Skip very short terms
                    continue
                
                similar_patents = self._find_patents_by_similarity(session, term)
                
                for patent_id, similarity_score, match_text in similar_patents:
                    if similarity_score >= self.min_similarity_score:
                        
                        # Lower confidence for similarity matches
                        confidence = 0.50 * similarity_score
                        
                        link = PatentLinkResult(
                            asset_id=asset['asset_id'],
                            patent_id=patent_id,
                            confidence_score=confidence,
                            link_method='text_similarity',
                            evidence_spans=[],
                            match_details={
                                'search_term': term,
                                'similarity_score': similarity_score,
                                'match_text': match_text
                            }
                        )
                        links.append(link)
                        
        except Exception as e:
            logger.error(f"Error finding similarity matches for asset {asset['asset_id']}: {e}")
        
        return links
    
    def _verify_inn_mention(self, text: str, inn: str) -> bool:
        """Verify that INN is mentioned as a word, not substring."""
        # Use word boundaries to ensure exact match
        pattern = rf'\b{re.escape(inn)}\b'
        return bool(re.search(pattern, text, re.IGNORECASE))
    
    def _verify_code_mention(self, text: str, code: str) -> bool:
        """Verify that code is mentioned appropriately."""
        # Look for code with common prefixes/suffixes
        patterns = [
            rf'\b{re.escape(code)}\b',  # Exact word
            rf'\b{re.escape(code)}-\d+',  # Code with number suffix
            rf'compound\s+{re.escape(code)}\b',  # "compound ABC-123"
            rf'drug\s+{re.escape(code)}\b',  # "drug ABC-123"
        ]
        
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
    
    def _extract_evidence_spans(self, text: str, search_term: str, patent_id: int) -> List[Dict[str, Any]]:
        """Extract evidence spans for matches."""
        spans = []
        
        # Find all occurrences
        pattern = rf'\b{re.escape(search_term)}\b'
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - 50)  # Context before
            end = min(len(text), match.end() + 50)  # Context after
            
            span = {
                'doc_id': f'patent:{patent_id}',
                'quote': text[start:end],
                'section': 'abstract' if 'abstract' in text.lower() else 'title',
                'char_start': match.start(),
                'char_end': match.end(),
                'confidence': 0.95,
                'match_term': search_term
            }
            spans.append(span)
        
        return spans
    
    def _find_patents_by_assignee_company(self, session: Session, company_id: int) -> List[Tuple[int, Optional[date], str]]:
        """Find patents assigned to a specific company."""
        try:
            # Get company name for matching
            company = session.query(Company).filter(Company.company_id == company_id).first()
            if not company:
                return []
            
            # Search for patents with this assignee
            query = text("""
                SELECT patent_id, grant_date, assignees
                FROM patents
                WHERE assignees @> :company_name::jsonb
                AND jurisdiction = 'US'
                ORDER BY grant_date DESC NULLS LAST
                LIMIT 100
            """)
            
            results = session.execute(query, {"company_name": f'["{company.name}"]'}).fetchall()
            return [(row[0], row[1], row[2]) for row in results]
            
        except Exception as e:
            logger.error(f"Error finding patents for company {company_id}: {e}")
            return []
    
    def _calculate_temporal_score(self, patent_date: Optional[date], 
                                 ownership_start: Optional[date],
                                 ownership_end: Optional[date]) -> float:
        """Calculate temporal alignment score."""
        if not patent_date or not ownership_start:
            return 0.0
        
        # Check if patent is within ownership period
        if ownership_end and patent_date > ownership_end:
            return 0.0
        
        if patent_date < ownership_start:
            # Patent before ownership - calculate penalty
            days_diff = (ownership_start - patent_date).days
            if days_diff > self.max_temporal_distance_days:
                return 0.0
            else:
                # Exponential decay
                return max(0.0, 1.0 - (days_diff / self.max_temporal_distance_days))
        else:
            # Patent during ownership period
            return 1.0
    
    def _find_patents_by_similarity(self, session: Session, search_term: str) -> List[Tuple[int, float, str]]:
        """Find patents by text similarity."""
        try:
            # Use PostgreSQL similarity functions if available
            query = text("""
                SELECT patent_id, 
                       GREATEST(
                           similarity(title, :search_term),
                           similarity(abstract, :search_term)
                       ) as sim_score,
                       CASE 
                           WHEN similarity(title, :search_term) > similarity(abstract, :search_term) 
                           THEN title 
                           ELSE abstract 
                       END as match_text
                FROM patents
                WHERE (title % :search_term OR abstract % :search_term)
                AND jurisdiction = 'US'
                ORDER BY sim_score DESC
                LIMIT 20
            """)
            
            results = session.execute(query, {"search_term": search_term}).fetchall()
            return [(row[0], float(row[1]), row[2]) for row in results]
            
        except Exception as e:
            logger.debug(f"Similarity search failed for '{search_term}': {e}")
            return []
    
    def _find_assets_by_text_mentions(self, session: Session, patent_text: str) -> List[Tuple[int, float, str]]:
        """Find assets mentioned in patent text."""
        assets = []
        
        try:
            # Get all assets with their names
            query = text("""
                SELECT a.asset_id, a.names_jsonb, aa.alias, aa.alias_type
                FROM assets a
                LEFT JOIN asset_aliases aa ON a.asset_id = aa.asset_id
            """)
            
            results = session.execute(query).fetchall()
            
            for asset_id, names_jsonb, alias, alias_type in results:
                names = names_jsonb or {}
                
                # Check INN
                inn = names.get('inn', '')
                if inn and self._verify_inn_mention(patent_text, inn):
                    assets.append((asset_id, 0.95, 'inn_match'))
                
                # Check internal codes
                internal_codes = names.get('internal_codes', [])
                for code in internal_codes:
                    if self._verify_code_mention(patent_text, code):
                        assets.append((asset_id, 0.90, 'code_match'))
                
                # Check aliases
                if alias and self._verify_inn_mention(patent_text, alias):
                    confidence = 0.85 if alias_type == 'inn' else 0.75
                    assets.append((asset_id, confidence, f'alias_match_{alias_type}'))
                    
        except Exception as e:
            logger.error(f"Error finding assets by text mentions: {e}")
        
        return assets
    
    def _deduplicate_and_score(self, links: List[PatentLinkResult]) -> List[PatentLinkResult]:
        """Deduplicate links and keep the highest confidence for each asset-patent pair."""
        
        # Group by (asset_id, patent_id)
        link_groups = {}
        for link in links:
            key = (link.asset_id, link.patent_id)
            if key not in link_groups:
                link_groups[key] = []
            link_groups[key].append(link)
        
        # Keep the best link for each pair
        final_links = []
        for key, group in link_groups.items():
            # Sort by confidence, then by method priority
            method_priority = {
                'inn_exact': 1,
                'code_mention': 2,
                'assignee_temporal': 3,
                'text_similarity': 4,
                'reverse_inn_exact': 5,
                'reverse_code_mention': 6
            }
            
            best_link = max(group, key=lambda x: (
                x.confidence_score,
                -method_priority.get(x.link_method, 10)
            ))
            
            # Only include if meets minimum threshold
            if best_link.confidence_score >= self.min_confidence_threshold:
                final_links.append(best_link)
        
        # Sort by confidence score descending
        final_links.sort(key=lambda x: x.confidence_score, reverse=True)
        
        return final_links
    
    def _compile_patterns(self):
        """Compile regex patterns for text matching."""
        self.patterns = {
            'drug_mention': re.compile(r'\b(?:compound|drug|agent|molecule)\s+([A-Z0-9-]+)\b', re.IGNORECASE),
            'code_pattern': re.compile(r'\b[A-Z]{2,4}-?\d{2,5}[A-Z]?\b'),
            'inn_suffix': re.compile(r'\b\w+(?:mab|tinib|ciclib|nib|parib|inib|zomib|mide|afil|pril|sartan|statin|prazole|oxacin|mycin|vir|rel|umab|zumab|ximab|omab)\b', re.IGNORECASE)
        }
    
    def get_linking_stats(self, links: List[PatentLinkResult]) -> Dict[str, Any]:
        """Get statistics about linking results."""
        total = len(links)
        high_confidence = sum(1 for link in links if link.is_high_confidence)
        methods = {}
        
        for link in links:
            method = link.link_method
            methods[method] = methods.get(method, 0) + 1
        
        return {
            "total_links": total,
            "high_confidence_count": high_confidence,
            "high_confidence_rate": high_confidence / total if total > 0 else 0.0,
            "methods_used": methods,
            "average_confidence": sum(link.confidence_score for link in links) / total if total > 0 else 0.0,
            "confidence_distribution": {
                "high": sum(1 for link in links if link.confidence_score >= 0.85),
                "medium": sum(1 for link in links if 0.65 <= link.confidence_score < 0.85),
                "low": sum(1 for link in links if link.confidence_score < 0.65)
            }
        }
