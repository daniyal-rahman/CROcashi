"""
R/S Scoring Implementation for PubMed Documents

Implements relevance (R) and shortability (S) scoring based on document content,
asset matches, indication matches, and risk signals.
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RSConfig:
    """Configuration for R/S scoring."""
    r_thresholds: Dict[str, float]
    s_thresholds: Dict[str, float]
    risk_phrases: Dict[str, List[str]]
    success_phrases: Dict[str, List[str]]
    scoring_weights: Dict[str, float]
    risk_weights: Dict[str, float]


@dataclass
class RSScore:
    """R/S scoring result."""
    r_score: float
    s_score: float
    r_tier: str
    s_tier: str
    r_components: Dict[str, Any]
    s_components: Dict[str, Any]


class RSScorer:
    """R/S scorer for PubMed documents."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize R/S scorer.
        
        Args:
            config_path: Path to R/S config file
        """
        self.config = self._load_config(config_path)
        self.logger = logging.getLogger(__name__)
    
    def _load_config(self, config_path: Optional[str]) -> RSConfig:
        """Load R/S scoring configuration."""
        if config_path is None:
            # Use default config path
            config_path = Path(__file__).parent.parent.parent / "score" / "minimal_rs_config.yaml"
        
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            return RSConfig(
                r_thresholds=config_data['r_thresholds'],
                s_thresholds=config_data['s_thresholds'],
                risk_phrases=config_data['risk_phrases'],
                success_phrases=config_data['success_phrases'],
                scoring_weights=config_data['scoring_weights'],
                risk_weights=config_data['risk_weights']
            )
        except Exception as e:
            logger.error(f"Failed to load R/S config: {e}")
            # Return default config
            return RSConfig(
                r_thresholds={'r3': 0.75, 'r2': 0.55, 'r1': 0.35},
                s_thresholds={'s3': 0.70, 's2': 0.45, 's1': 0.20},
                risk_phrases={'fail_primary': ['failed', 'futility']},
                success_phrases={'met_primary': ['met primary', 'statistically significant']},
                scoring_weights={'asset_match': 0.4, 'indication_match': 0.3, 'nct_match': 0.2, 'phase_relevance': 0.1},
                risk_weights={'fail_primary': 0.4, 'trend_only': 0.3, 'post_hoc': 0.2, 'interim': 0.1}
            )
    
    def score_document(
        self, 
        doc: Dict[str, Any], 
        trial_asset: str, 
        trial_indication: str, 
        trial_nct: Optional[str] = None,
        trial_phase: Optional[str] = None
    ) -> RSScore:
        """
        Score a document for R (relevance) and S (shortability).
        
        Args:
            doc: Document data
            trial_asset: Asset name for the trial
            trial_indication: Indication for the trial
            trial_nct: NCT ID for the trial
            trial_phase: Trial phase
            
        Returns:
            R/S score result
        """
        try:
            # Extract document text
            doc_text = self._extract_document_text(doc)
            if not doc_text:
                return self._create_default_score()
            
            # Calculate R score (relevance)
            r_score, r_components = self._calculate_r_score(
                doc_text, doc, trial_asset, trial_indication, trial_nct, trial_phase
            )
            
            # Calculate S score (shortability/risk)
            s_score, s_components = self._calculate_s_score(doc_text, doc)
            
            # Determine tiers
            r_tier = self._determine_r_tier(r_score)
            s_tier = self._determine_s_tier(s_score)
            
            return RSScore(
                r_score=r_score,
                s_score=s_score,
                r_tier=r_tier,
                s_tier=s_tier,
                r_components=r_components,
                s_components=s_components
            )
            
        except Exception as e:
            self.logger.error(f"Error scoring document {doc.get('pmid', 'unknown')}: {e}")
            return self._create_default_score()
    
    def _extract_document_text(self, doc: Dict[str, Any]) -> str:
        """Extract text from document for analysis."""
        text_parts = []
        
        # Add title
        if doc.get('title'):
            text_parts.append(doc['title'])
        
        # Add abstract
        if doc.get('abstract'):
            text_parts.append(doc['abstract'])
        
        return ' '.join(text_parts).lower()
    
    def _calculate_r_score(
        self, 
        doc_text: str, 
        doc: Dict[str, Any], 
        trial_asset: str, 
        trial_indication: str, 
        trial_nct: Optional[str],
        trial_phase: Optional[str]
    ) -> Tuple[float, Dict[str, Any]]:
        """Calculate R score (relevance)."""
        components = {}
        total_score = 0.0
        
        # Asset match scoring
        asset_score = self._score_asset_match(doc_text, trial_asset)
        components['asset_match'] = asset_score
        total_score += asset_score * self.config.scoring_weights['asset_match']
        
        # Indication match scoring
        indication_score = self._score_indication_match(doc_text, trial_indication)
        components['indication_match'] = indication_score
        total_score += indication_score * self.config.scoring_weights['indication_match']
        
        # NCT match scoring
        nct_score = self._score_nct_match(doc_text, doc, trial_nct)
        components['nct_match'] = nct_score
        total_score += nct_score * self.config.scoring_weights['nct_match']
        
        # Phase relevance scoring
        phase_score = self._score_phase_relevance(doc_text, trial_phase)
        components['phase_relevance'] = phase_score
        total_score += phase_score * self.config.scoring_weights['phase_relevance']
        
        # Normalize to 0-1 range
        r_score = min(1.0, total_score)
        
        return r_score, components
    
    def _score_asset_match(self, doc_text: str, trial_asset: str) -> float:
        """Score asset name matches in document."""
        if not trial_asset:
            return 0.0
        
        asset_lower = trial_asset.lower()
        score = 0.0
        
        # Direct match
        if asset_lower in doc_text:
            score += 0.8
        
        # Partial matches (for compound names)
        asset_words = asset_lower.split()
        if len(asset_words) > 1:
            matches = sum(1 for word in asset_words if word in doc_text)
            partial_score = matches / len(asset_words) * 0.6
            score = max(score, partial_score)
        
        # Special handling for common drug name variations
        if 'simufilam' in asset_lower:
            if any(variant in doc_text for variant in ['simufilam', 'pti-125', 'pti 125']):
                score = max(score, 0.9)
        
        return min(1.0, score)
    
    def _score_indication_match(self, doc_text: str, trial_indication: str) -> float:
        """Score indication matches in document."""
        if not trial_indication:
            return 0.0
        
        indication_lower = trial_indication.lower()
        score = 0.0
        
        # Direct match
        if indication_lower in doc_text:
            score += 0.8
        
        # Common indication synonyms
        indication_synonyms = {
            'alzheimer': ['alzheimer', 'dementia', 'cognitive impairment', 'ad'],
            'cancer': ['cancer', 'tumor', 'neoplasm', 'oncology'],
            'diabetes': ['diabetes', 'diabetic', 'glucose', 'insulin']
        }
        
        for key, synonyms in indication_synonyms.items():
            if key in indication_lower:
                if any(syn in doc_text for syn in synonyms):
                    score = max(score, 0.7)
                break
        
        return min(1.0, score)
    
    def _score_nct_match(self, doc_text: str, doc: Dict[str, Any], trial_nct: Optional[str]) -> float:
        """Score NCT ID matches."""
        if not trial_nct:
            return 0.0
        
        # Check in document text
        if trial_nct.lower() in doc_text:
            return 1.0
        
        # Check in document metadata
        if doc.get('nct_id') == trial_nct:
            return 1.0
        
        return 0.0
    
    def _score_phase_relevance(self, doc_text: str, trial_phase: Optional[str]) -> float:
        """Score trial phase relevance."""
        if not trial_phase:
            return 0.0
        
        phase_lower = trial_phase.lower()
        score = 0.0
        
        # Phase-specific keywords
        phase_keywords = {
            'phase1': ['phase i', 'phase 1', 'first-in-human', 'dose escalation'],
            'phase2': ['phase ii', 'phase 2', 'phase ii', 'efficacy'],
            'phase3': ['phase iii', 'phase 3', 'phase iii', 'pivotal', 'registration'],
            'phase4': ['phase iv', 'phase 4', 'post-marketing', 'surveillance']
        }
        
        for phase_key, keywords in phase_keywords.items():
            if phase_key in phase_lower:
                if any(keyword in doc_text for keyword in keywords):
                    score = 0.8
                break
        
        return score
    
    def _calculate_s_score(self, doc_text: str, doc: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """Calculate S score (shortability/risk) - quick and cheap version."""
        if not doc_text:
            return 0.0, {}
        
        text_lower = doc_text.lower()
        components = {}
        
        # Quick keyword-based scoring (fast and cheap)
        high_risk_keywords = ['comment', 'novel', 'candidate', 'suggested', 'preliminary']
        medium_risk_keywords = ['small molecule', 'phase 3', 'mechanism', 'biomarker', 
                               'lymphocyte', 'in vitro', 'in vivo', 'preclinical']
        
        # Count matches
        high_count = sum(1 for kw in high_risk_keywords if kw in text_lower)
        medium_count = sum(1 for kw in medium_risk_keywords if kw in text_lower)
        
        # Simple linear scoring
        s_score = (high_count * 0.2) + (medium_count * 0.1)
        s_score = min(1.0, s_score)
        
        components = {
            'high_risk_keywords': high_count,
            'medium_risk_keywords': medium_count,
            'quick_score': s_score
        }
        
        return s_score, components
    
    def _score_risk_phrases(self, doc_text: str) -> float:
        """Score risk phrases in document."""
        total_risk = 0.0
        
        for risk_type, phrases in self.config.risk_phrases.items():
            risk_weight = self.config.risk_weights.get(risk_type, 0.1)
            
            for phrase in phrases:
                if phrase.lower() in doc_text:
                    total_risk += risk_weight
                    break  # Only count once per risk type
        
        return min(1.0, total_risk)
    
    def _score_success_phrases(self, doc_text: str) -> float:
        """Score success phrases in document."""
        total_success = 0.0
        
        for success_type, phrases in self.config.success_phrases.items():
            for phrase in phrases:
                if phrase.lower() in doc_text:
                    total_success += 0.2
                    break  # Only count once per success type
        
        return min(1.0, total_success)
    
    def _score_clinical_outcomes(self, doc_text: str) -> float:
        """Score clinical trial outcome indicators."""
        score = 0.0
        
        # Negative outcome indicators
        negative_indicators = [
            'did not meet', 'failed to meet', 'missed primary', 'futility',
            'stopped early', 'discontinued', 'withdrawn', 'safety concern'
        ]
        
        for indicator in negative_indicators:
            if indicator in doc_text:
                score += 0.3
        
        # Positive outcome indicators (reduce risk)
        positive_indicators = [
            'met primary', 'achieved primary', 'statistically significant',
            'positive results', 'efficacious', 'well tolerated'
        ]
        
        for indicator in positive_indicators:
            if indicator in doc_text:
                score -= 0.2
        
        return max(0.0, min(1.0, score))
    
    def _determine_r_tier(self, r_score: float) -> str:
        """Determine R tier based on score."""
        if r_score >= self.config.r_thresholds['r3']:
            return "R3"
        elif r_score >= self.config.r_thresholds['r2']:
            return "R2"
        elif r_score >= self.config.r_thresholds['r1']:
            return "R1"
        else:
            return "R0"
    
    def _determine_s_tier(self, s_score: float) -> str:
        """Determine S tier based on score."""
        if s_score >= self.config.s_thresholds['s3']:
            return "S3"
        elif s_score >= self.config.s_thresholds['s2']:
            return "S2"
        elif s_score >= self.config.s_thresholds['s1']:
            return "S1"
        else:
            return "S0"
    
    def _create_default_score(self) -> RSScore:
        """Create default R/S score for error cases."""
        return RSScore(
            r_score=0.0,
            s_score=0.0,
            r_tier="R0",
            s_tier="S0",
            r_components={'error': 'default_score'},
            s_components={'error': 'default_score'}
        )
