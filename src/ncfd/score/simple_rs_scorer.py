"""
Simple R/S scoring system for minimal testing.

Implements basic Relevance (R) and Shortability (S) scoring for clinical trial literature.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import re

from ..extract.abstract_features import AbstractFeatureExtractor, ExtractedEntity

logger = logging.getLogger(__name__)


@dataclass
class RSScore:
    """R/S score for a document."""
    R_score: float
    R_tier: str
    S_score: float
    S_tier: str
    R_components: Dict[str, Any]
    S_components: Dict[str, Any]
    confidence: float


class SimpleRSScorer:
    """Simple R/S scorer for clinical trial literature."""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize R/S scorer.
        
        Args:
            config: Configuration dictionary with scoring parameters
        """
        self.config = config or {}
        
        # R tier thresholds
        self.r_thresholds = self.config.get('r_thresholds', {
            'r3': 0.75,
            'r2': 0.55,
            'r1': 0.35
        })
        
        # S tier thresholds
        self.s_thresholds = self.config.get('s_thresholds', {
            's3': 0.70,
            's2': 0.45,
            's1': 0.20
        })
        
        # Feature extractor
        self.extractor = AbstractFeatureExtractor()
        
        # Risk signal phrases
        self.risk_phrases = self.config.get('risk_phrases', {
            'fail_primary': ['did not meet primary', 'failed', 'futility', 'non-inferiority not demonstrated'],
            'trend_only': ['trend only', 'trend toward', 'borderline'],
            'post_hoc': ['post-hoc', 'post hoc', 'subgroup', 'subgroup analysis'],
            'interim': ['interim', 'interim analysis', 'early stopping'],
            'pp_not_itt': ['per protocol', 'per-protocol', 'not intention to treat']
        })
        
        # Success phrases
        self.success_phrases = self.config.get('success_phrases', {
            'met_primary': ['met primary', 'achieved primary', 'primary endpoint met'],
            'statistically_significant': ['statistically significant', 'p < 0.05', 'p < 0.01'],
            'robust': ['robust', 'strong', 'consistent', 'convincing']
        })
        
        # Generic drug terms with reduced weight
        self.generic_terms = ['drug', 'compound', 'agent', 'therapy', 'treatment']
        
        # Article type boosts
        self.article_boosts = {
            'clinical trial': 0.05,
            'randomized': 0.05,
            'controlled': 0.03
        }
        
        # S scoring weights - rebalanced for better distribution
        self.s_weights = {
            'risk_signals': 0.6,      # Increased from 0.5
            'safety_signals': 0.25,   # Reduced from 0.3
            'statistical_concerns': 0.15  # Reduced from 0.2
        }
    
    def score_document(
        self, 
        doc_text: str, 
        trial_asset: str, 
        trial_indication: str,
        trial_nct: Optional[str] = None,
        trial_aliases: Optional[List[str]] = None
    ) -> RSScore:
        """
        Score a document for R and S dimensions.
        
        Args:
            doc_text: Document text (title + abstract)
            trial_asset: Asset name from the trial
            trial_indication: Indication from the trial
            trial_nct: NCT ID from the trial (optional)
            trial_aliases: List of asset aliases/codes (optional)
            
        Returns:
            RSScore with R and S scores and tiers
        """
        # Extract features from document
        entities = self.extractor.extract_all_features(doc_text)
        
        # Score Relevance (R)
        r_score, r_components = self._score_relevance(
            doc_text, entities, trial_asset, trial_indication, trial_nct, trial_aliases
        )
        
        # Score Shortability (S)
        s_score, s_components = self._score_shortability(doc_text, entities)
        
        # Check for S0 override (success phrases without risk signals)
        s_score, s_components = self._apply_s0_override(doc_text, s_score, s_components)
        
        # Determine tiers
        r_tier = self._get_r_tier(r_score)
        s_tier = self._get_s_tier(s_score)
        
        # Calculate overall confidence
        confidence = self._calculate_confidence(r_components, s_components)
        
        # Clean up components by removing rollup keys
        r_components_clean = {k: v for k, v in r_components.items() 
                             if k not in ['total_r_score']}
        s_components_clean = {k: v for k, v in s_components.items() 
                             if k not in ['total_s_score']}
        
        return RSScore(
            R_score=r_score,
            R_tier=r_tier,
            S_score=s_score,
            S_tier=s_tier,
            R_components=r_components_clean,
            S_components=s_components_clean,
            confidence=confidence
        )
    
    def _score_relevance(
        self, 
        doc_text: str, 
        entities: List[ExtractedEntity],
        trial_asset: str,
        trial_indication: str,
        trial_nct: Optional[str],
        trial_aliases: Optional[List[str]]
    ) -> Tuple[float, Dict[str, Any]]:
        """Score document relevance to the trial."""
        components = {}
        score = 0.0
        
        # 1. Asset match (0-0.4 points)
        asset_score = self._score_asset_match(doc_text, trial_asset, trial_aliases)
        components['asset_match'] = asset_score
        score += asset_score * 0.4
        
        # 2. Indication match (0-0.3 points)
        indication_score = self._score_indication_match(doc_text, trial_indication)
        components['indication_match'] = indication_score
        score += indication_score * 0.3
        
        # 3. NCT match (0-0.2 points)
        nct_score = self._score_nct_match(entities, trial_nct)
        components['nct_match'] = nct_score
        score += nct_score * 0.2
        
        # 4. Trial phase relevance (0-0.1 points)
        phase_score = self._score_phase_relevance(entities)
        components['phase_relevance'] = phase_score
        score += phase_score * 0.1
        
        # 5. Article type and clinical context (0-0.05 points)
        article_boost = self._score_article_context(doc_text)
        components['article_context'] = article_boost
        score += article_boost * 0.05
        
        # Store the final score but don't include rollup keys in components
        components['total_r_score'] = score
        return score, components
    
    def _score_asset_match(self, doc_text: str, trial_asset: str, trial_aliases: Optional[List[str]]) -> float:
        """Score how well the document matches the trial asset."""
        if not trial_asset or not doc_text:
            return 0.0
        
        doc_lower = doc_text.lower()
        asset_lower = trial_asset.lower()
        
        # Exact match with word boundaries
        if re.search(r'\b' + re.escape(asset_lower) + r'\b', doc_lower):
            return 1.0
        
        # Partial match (asset name contains key words)
        asset_words = asset_lower.split()
        if len(asset_words) > 1:
            # Check if key words from asset name appear in document with word boundaries
            key_words = [w for w in asset_words if len(w) > 3]  # Skip short words
            matches = 0
            for word in key_words:
                if re.search(r'\b' + re.escape(word) + r'\b', doc_lower):
                    matches += 1
            
            if matches > 0:
                return min(0.8, matches / len(key_words))
        
        # Check for aliases
        if trial_aliases:
            for alias in trial_aliases:
                alias_lower = alias.lower()
                if re.search(r'\b' + re.escape(alias_lower) + r'\b', doc_lower):
                    return 0.7  # Good boost for aliases
        
        # Generic drug terms with much reduced weight and context check
        generic_terms = ['drug', 'compound', 'agent', 'therapy', 'treatment']
        for term in generic_terms:
            if re.search(r'\b' + term + r'\b', doc_lower):
                # Only give small boost if in clinical context
                if any(context in doc_lower for context in ['trial', 'study', 'clinical', 'patient', 'treatment']):
                    return 0.05  # Much reduced from 0.3
        
        return 0.0
    
    def _score_indication_match(self, doc_text: str, trial_indication: str) -> float:
        """Score how well the document matches the trial indication."""
        if not trial_indication or not doc_text:
            return 0.0
        
        doc_lower = doc_text.lower()
        indication_lower = trial_indication.lower()
        
        # Exact match
        if indication_lower in doc_lower:
            return 1.0
        
        # Partial match
        indication_words = indication_lower.split()
        if len(indication_words) > 1:
            key_words = [w for w in indication_words if len(w) > 3]
            matches = sum(1 for word in key_words if word in doc_lower)
            if matches > 0:
                return min(0.8, matches / len(key_words))
        
        # Disease category match
        disease_categories = {
            'cancer': ['cancer', 'carcinoma', 'tumor', 'neoplasm', 'malignancy'],
            'diabetes': ['diabetes', 'diabetic', 'glucose', 'insulin'],
            'arthritis': ['arthritis', 'arthritic', 'joint', 'rheumatoid'],
            'cardiovascular': ['cardiac', 'heart', 'cardiovascular', 'vascular']
        }
        
        for category, terms in disease_categories.items():
            if any(term in indication_lower for term in terms):
                if any(term in doc_lower for term in terms):
                    return 0.6
        
        return 0.0
    
    def _score_nct_match(self, entities: List[ExtractedEntity], trial_nct: Optional[str]) -> float:
        """Score NCT ID match."""
        if not trial_nct:
            return 0.0
        
        # Check if trial NCT appears in document
        nct_entities = [e for e in entities if e.ent_type == 'nct_id']
        for entity in nct_entities:
            if entity.value_norm == trial_nct:
                return 1.0
        
        return 0.0
    
    def _score_phase_relevance(self, entities: List[ExtractedEntity]) -> float:
        """Score trial phase relevance."""
        phase_entities = [e for e in entities if e.ent_type == 'phase']
        
        if not phase_entities:
            return 0.0
        
        # Higher phases are more relevant for clinical decision making
        phase_scores = {
            'PHASE4': 0.9,  # Post-marketing studies
            'PHASE3': 1.0,  # Pivotal trials
            'PHASE2': 0.8,  # Efficacy trials
            'PHASE1': 0.6,  # Safety/dosing trials
            'PHASE5': 0.7   # Additional studies
        }
        
        max_score = 0.0
        for entity in phase_entities:
            phase = entity.value_norm
            score = phase_scores.get(phase, 0.5)
            max_score = max(max_score, score)
        
        return max_score
    
    def _score_article_context(self, doc_text: str) -> float:
        """Score article type and clinical context for relevance."""
        doc_lower = doc_text.lower()
        boost = 0.0
        
        # Check for common clinical trial keywords
        if re.search(r'\b(clinical trial|study|research|trial|investigation)\b', doc_lower):
            boost += 0.05
        
        # Check for common randomized/controlled trial keywords
        if re.search(r'\b(randomized|controlled|double blind|triple blind)\b', doc_lower):
            boost += 0.05
        
        # Check for common drug/treatment terms
        if re.search(r'\b(drug|compound|agent|therapy|treatment)\b', doc_lower):
            boost += 0.03
        
        # Check for common patient/patient-related terms
        if re.search(r'\b(patient|subject|participant|individual)\b', doc_lower):
            boost += 0.03
        
        # Check for common adverse event/safety terms
        if re.search(r'\b(adverse event|toxicity|side effect|safety concern|tolerability issue|dose limiting)\b', doc_lower):
            boost += 0.03
        
        # Check for common statistical terms
        if re.search(r'\b(p-value|p value|p < 0.05|p < 0.01|confidence interval|ci)\b', doc_lower):
            boost += 0.03
        
        # Check for common effect size terms
        if re.search(r'\b(effect size|hr|or|rr|hazard ratio|odds ratio|relative risk)\b', doc_lower):
            boost += 0.03
        
        return min(0.05, boost) # Cap boost at 0.05
    
    def _score_shortability(self, doc_text: str, entities: List[ExtractedEntity]) -> Tuple[float, Dict[str, Any]]:
        """Score document shortability (risk signals)."""
        components = {}
        score = 0.0
        
        doc_lower = doc_text.lower()
        
        # 1. Risk signal phrases (0-0.5 points)
        risk_score = self._score_risk_signals(doc_lower)
        components['risk_signals'] = risk_score
        score += risk_score * self.s_weights['risk_signals']
        
        # 2. Safety signals (0-0.3 points)
        safety_score = self._score_safety_signals(doc_lower)
        components['safety_signals'] = safety_score
        score += safety_score * self.s_weights['safety_signals']
        
        # 3. Statistical concerns (0-0.2 points)
        stats_score = self._score_statistical_concerns(entities)
        components['statistical_concerns'] = stats_score
        score += stats_score * self.s_weights['statistical_concerns']
        
        components['total_s_score'] = score
        return score, components
    
    def _apply_s0_override(self, doc_text: str, s_score: float, s_components: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """Apply S0 override when success phrases are present without risk signals."""
        doc_lower = doc_text.lower()
        
        # Check for success phrases
        has_success = False
        for category, phrases in self.success_phrases.items():
            if any(phrase in doc_lower for phrase in phrases):
                has_success = True
                break
        
        if not has_success:
            return s_score, s_components
        
        # Check for risk signals
        has_risk = False
        for category, phrases in self.risk_phrases.items():
            if any(phrase in doc_lower for phrase in phrases):
                has_risk = True
                break
        
        # If success phrases present but no risk signals, force S0
        if has_success and not has_risk:
            s_components['s0_override'] = True
            s_components['override_reason'] = 'Success phrases without risk signals'
            return 0.0, s_components
        
        return s_score, s_components
    
    def _score_risk_signals(self, doc_lower: str) -> float:
        """Score risk signal phrases in document."""
        total_score = 0.0
        max_possible = 0.0
        
        for category, phrases in self.risk_phrases.items():
            category_score = 0.0
            for phrase in phrases:
                if phrase in doc_lower:
                    category_score = 1.0
                    break
            
            # Weight different risk categories - rebalanced for better S distribution
            if category == 'fail_primary':
                weight = 0.6  # Primary endpoint failure is most important (increased from 0.4)
            elif category == 'trend_only':
                weight = 0.25  # Reduced from 0.3
            elif category == 'post_hoc':
                weight = 0.25  # Increased from 0.2
            elif category == 'pp_not_itt':
                weight = 0.25  # Increased from 0.1
            elif category == 'interim':
                weight = 0.15  # Reduced from 0.1
            else:
                weight = 0.1
            
            total_score += category_score * weight
            max_possible += weight
        
        return total_score / max_possible if max_possible > 0 else 0.0
    
    def _score_safety_signals(self, doc_lower: str) -> float:
        """Score safety signal phrases in document."""
        safety_terms = [
            'discontinuation', 'adverse event', 'toxicity', 'side effect',
            'safety concern', 'tolerability issue', 'dose limiting'
        ]
        
        matches = sum(1 for term in safety_terms if term in doc_lower)
        return min(1.0, matches / 3.0)  # Normalize to 0-1
    
    def _score_statistical_concerns(self, entities: List[ExtractedEntity]) -> float:
        """Score statistical concerns from extracted entities."""
        score = 0.0
        
        # Check for borderline p-values
        p_entities = [e for e in entities if e.ent_type == 'p_value']
        for entity in p_entities:
            try:
                p_val = float(entity.value_norm)
                if 0.05 <= p_val <= 0.1:  # Borderline significance
                    score += 0.5
                elif p_val > 0.1:  # Non-significant
                    score += 1.0
            except ValueError:
                continue
        
        # Check effect sizes and confidence intervals
        effect_entities = [e for e in entities if e.ent_type == 'effect_size']
        ci_entities = [e for e in entities if e.ent_type == 'ci']
        
        # Score effect sizes
        for entity in effect_entities:
            try:
                effect_val = float(entity.value_norm)
                # Unfavorable effect sizes (HR/OR/RR > 1.0)
                if effect_val > 1.0:
                    # Log scale penalty for unfavorable effects
                    score += min(1.0, (effect_val - 1.0) * 0.5)
            except ValueError:
                continue
        
        # Score confidence intervals
        for entity in ci_entities:
            metadata = entity.metadata or {}
            
            # Check if CI crosses null value (1.0 for ratios)
            if metadata.get('crosses_null', False):
                score += 0.8  # Significant concern
            
            # Check for wide confidence intervals
            width = metadata.get('width', 0)
            if width > 0:
                # Penalize wide CIs relative to effect size
                if width > 1.0:  # Very wide CI
                    score += 0.6
                elif width > 0.5:  # Moderately wide CI
                    score += 0.3
        
        return min(1.0, score)
    
    def _get_r_tier(self, r_score: float) -> str:
        """Get R tier based on score."""
        if r_score >= self.r_thresholds['r3']:
            return 'R3'
        elif r_score >= self.r_thresholds['r2']:
            return 'R2'
        elif r_score >= self.r_thresholds['r1']:
            return 'R1'
        else:
            return 'R0'
    
    def _get_s_tier(self, s_score: float) -> str:
        """Get S tier based on score."""
        if s_score >= self.s_thresholds['s3']:
            return 'S3'
        elif s_score >= self.s_thresholds['s2']:
            return 'S2'
        elif s_score >= self.s_thresholds['s1']:
            return 'S1'
        else:
            return 'S0'
    
    def _calculate_confidence(self, r_components: Dict[str, Any], s_components: Dict[str, Any]) -> float:
        """Calculate overall confidence in the scoring."""
        # Exclude rollup keys and use only primitive components
        rollup_keys = ['total_r_score', 'total_s_score', 's0_override', 'override_reason']
        
        r_primitive = {k: v for k, v in r_components.items() 
                       if k not in rollup_keys and isinstance(v, (int, float))}
        s_primitive = {k: v for k, v in s_components.items() 
                       if k not in rollup_keys and isinstance(v, (int, float))}
        
        # Calculate confidence from primitive components only
        r_confidence = sum(r_primitive.values()) / len(r_primitive) if r_primitive else 0
        s_confidence = sum(s_primitive.values()) / len(s_primitive) if s_primitive else 0
        
        # Average confidence, clamped to [0, 1]
        confidence = (r_confidence + s_confidence) / 2
        return max(0.0, min(1.0, confidence))
    
    def score_batch(
        self, 
        documents: List[Dict[str, Any]], 
        trial_asset: str, 
        trial_indication: str,
        trial_nct: Optional[str] = None,
        trial_aliases: Optional[List[str]] = None
    ) -> List[Tuple[Dict[str, Any], RSScore]]:
        """
        Score a batch of documents.
        
        Args:
            documents: List of document dictionaries
            trial_asset: Asset name from the trial
            trial_indication: Indication from the trial
            trial_nct: NCT ID from the trial (optional)
            trial_aliases: List of asset aliases/codes (optional)
            
        Returns:
            List of (document, score) tuples
        """
        scored_docs = []
        
        for doc in documents:
            try:
                # Extract text for scoring
                doc_text = self._extract_document_text(doc)
                if not doc_text:
                    continue
                
                # Score the document
                score = self.score_document(doc_text, trial_asset, trial_indication, trial_nct, trial_aliases)
                scored_docs.append((doc, score))
                
            except Exception as e:
                logger.warning(f"Failed to score document: {e}")
                continue
        
        return scored_docs
    
    def _extract_document_text(self, doc: Dict[str, Any]) -> str:
        """Extract text content from document for scoring."""
        text_parts = []
        
        # Add title
        if doc.get('title'):
            text_parts.append(doc['title'])
        
        # Add abstract - check multiple possible locations with type safety
        abstract_text = None
        
        # Check direct abstract_text field (Stage U1 format)
        if doc.get('abstract_text'):
            abstract_text = doc['abstract_text']
        # Check nested text.abstract_text field (original format) - with type safety
        elif 'text' in doc and isinstance(doc['text'], dict) and doc['text'].get('abstract_text'):
            abstract_text = doc['text']['abstract_text']
        # Check for any other abstract fields
        elif doc.get('abstract'):
            abstract_text = doc['abstract']
        
        if abstract_text:
            text_parts.append(abstract_text)
        
        # Debug logging
        if not text_parts:
            logger.warning(f"No text content found in document: {list(doc.keys())}")
        elif not abstract_text:
            logger.warning(f"No abstract found in document, only title available")
        
        return ' '.join(text_parts)
    
    def rank_by_r_score(self, scored_docs: List[Tuple[Dict[str, Any], RSScore]]) -> List[Tuple[Dict[str, Any], RSScore]]:
        """Rank documents by R score (descending)."""
        return sorted(scored_docs, key=lambda x: x[1].R_score, reverse=True)
    
    def rank_by_s_score(self, scored_docs: List[Tuple[Dict[str, Any], RSScore]]) -> List[Tuple[Dict[str, Any], RSScore]]:
        """Rank documents by S score (descending)."""
        return sorted(scored_docs, key=lambda x: x[1].S_score, reverse=True)
    
    def filter_by_r_tier(self, scored_docs: List[Tuple[Dict[str, Any], RSScore]], min_r_tier: str) -> List[Tuple[Dict[str, Any], RSScore]]:
        """Filter documents by minimum R tier."""
        tier_order = {'R0': 0, 'R1': 1, 'R2': 2, 'R3': 3}
        min_order = tier_order.get(min_r_tier, 0)
        
        return [
            (doc, score) for doc, score in scored_docs
            if tier_order.get(score.R_tier, 0) >= min_order
        ]
    
    def filter_by_s_tier(self, scored_docs: List[Tuple[Dict[str, Any], RSScore]], min_s_tier: str) -> List[Tuple[Dict[str, Any], RSScore]]:
        """Filter documents by minimum S tier."""
        tier_order = {'S0': 0, 'S1': 1, 'S2': 2, 'S3': 3}
        min_order = tier_order.get(min_s_tier, 0)
        
        return [
            (doc, score) for doc, score in scored_docs
            if tier_order.get(score.S_tier, 0) >= min_order
        ]
