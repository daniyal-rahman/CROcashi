"""
Advanced document scoring system for PubMed retrieval.

Implements multi-factor scoring with bonuses and penalties as specified
in the retrieval specification.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from ...entities.schema import EntityPack
from .policy_engine import PolicyResult

logger = logging.getLogger(__name__)


@dataclass
class ScoringConfig:
    """Configuration for advanced scoring system."""
    base_score_weight: float = 1.0
    publication_type_bonus: float = 1.5
    mesh_bonus: float = 0.5
    nct_bonus: float = 1.0
    recency_bonus: float = 0.3
    max_recency_bonus: float = 1.0
    recency_window_months: int = 18


@dataclass
class ScoringResult:
    """Result from advanced scoring."""
    total_score: float
    base_score: float
    policy_score: float
    publication_type_bonus: float
    mesh_bonus: float
    nct_bonus: float
    recency_bonus: float
    final_rank: Optional[int] = None
    score_breakdown: Dict[str, Any] = None


class BM25Calculator:
    """Calculates BM25 scores for documents."""
    
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        """
        Initialize BM25 calculator.
        
        Args:
            k1: Term frequency saturation parameter
            b: Length normalization parameter
        """
        self.k1 = k1
        self.b = b
        self.logger = logging.getLogger(__name__)
    
    def calculate_score(self, doc_text: str, query_terms: List[str]) -> float:
        """
        Calculate BM25 score for document.
        
        Args:
            doc_text: Document text
            query_terms: Query terms
            
        Returns:
            BM25 score
        """
        try:
            if not doc_text or not query_terms:
                return 0.0
            
            # Tokenize document text
            doc_tokens = self._tokenize(doc_text.lower())
            doc_length = len(doc_tokens)
            
            if doc_length == 0:
                return 0.0
            
            # Calculate average document length (simplified)
            avg_doc_length = doc_length  # In real implementation, this would be corpus average
            
            score = 0.0
            doc_term_counts = {}
            
            # Count term frequencies in document
            for token in doc_tokens:
                doc_term_counts[token] = doc_term_counts.get(token, 0) + 1
            
            # Calculate score for each query term
            for term in query_terms:
                term_lower = term.lower()
                if term_lower in doc_term_counts:
                    tf = doc_term_counts[term_lower]
                    
                    # BM25 formula
                    idf = 1.0  # Simplified IDF (in real implementation, would use corpus statistics)
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * (doc_length / avg_doc_length))
                    
                    score += idf * (numerator / denominator)
            
            return score
            
        except Exception as e:
            self.logger.error(f"Error calculating BM25 score: {e}")
            return 0.0
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into terms."""
        # Simple tokenization - in real implementation, would use proper NLP tokenization
        return re.findall(r'\b\w+\b', text)


class AdvancedDocumentScorer:
    """Advanced document scorer with multi-factor scoring."""
    
    def __init__(self, config: Optional[ScoringConfig] = None):
        """
        Initialize advanced document scorer.
        
        Args:
            config: Scoring configuration
        """
        self.config = config or ScoringConfig()
        self.bm25_calculator = BM25Calculator()
        self.logger = logging.getLogger(__name__)
        
        logger.info(f"Initialized advanced document scorer with config: {self.config}")
    
    def calculate_score(
        self, 
        doc: Dict[str, Any], 
        entity_pack: EntityPack,
        policy_result: Optional[PolicyResult] = None
    ) -> ScoringResult:
        """
        Calculate sophisticated score for document.
        
        Args:
            doc: Document to score
            entity_pack: Entity pack with scoring context
            policy_result: Policy engine result (if available)
            
        Returns:
            Scoring result
        """
        try:
            # Extract document text for analysis
            doc_text = self._extract_document_text(doc)
            
            # Calculate base BM25 score
            query_terms = self._extract_query_terms(entity_pack)
            base_score = self.bm25_calculator.calculate_score(doc_text, query_terms)
            
            # Apply policy engine scoring if available
            policy_score = 0.0
            if policy_result:
                policy_score = policy_result.total_score
            
            # Calculate bonuses
            pub_type_bonus = self._calculate_publication_type_bonus(doc)
            mesh_bonus = self._calculate_mesh_bonus(doc, entity_pack)
            nct_bonus = self._calculate_nct_bonus(doc, entity_pack)
            recency_bonus = self._calculate_recency_bonus(doc)
            
            # Calculate total score
            total_score = (
                base_score * self.config.base_score_weight +
                policy_score +
                pub_type_bonus +
                mesh_bonus +
                nct_bonus +
                recency_bonus
            )
            
            # Create score breakdown
            score_breakdown = {
                'base_score': base_score,
                'policy_score': policy_score,
                'publication_type_bonus': pub_type_bonus,
                'mesh_bonus': mesh_bonus,
                'nct_bonus': nct_bonus,
                'recency_bonus': recency_bonus,
                'total_score': total_score
            }
            
            return ScoringResult(
                total_score=total_score,
                base_score=base_score,
                policy_score=policy_score,
                publication_type_bonus=pub_type_bonus,
                mesh_bonus=mesh_bonus,
                nct_bonus=nct_bonus,
                recency_bonus=recency_bonus,
                score_breakdown=score_breakdown
            )
            
        except Exception as e:
            self.logger.error(f"Error calculating advanced score: {e}")
            return ScoringResult(
                total_score=0.0,
                base_score=0.0,
                policy_score=0.0,
                publication_type_bonus=0.0,
                mesh_bonus=0.0,
                nct_bonus=0.0,
                recency_bonus=0.0,
                score_breakdown={'error': str(e)}
            )
    
    def _extract_document_text(self, doc: Dict[str, Any]) -> str:
        """Extract text content from document for scoring."""
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
        
        return ' '.join(text_parts)
    
    def _extract_query_terms(self, entity_pack: EntityPack) -> List[str]:
        """Extract query terms from entity pack."""
        terms = []
        
        # Add asset terms
        terms.extend(entity_pack.get_all_asset_terms())
        
        # Add company terms
        terms.extend(entity_pack.get_all_company_terms())
        
        # Add indication terms
        terms.extend(entity_pack.get_all_indication_terms())
        
        # Add mechanism terms
        terms.extend(entity_pack.mechanism.targets)
        
        # Add NCT IDs
        terms.extend(entity_pack.registries.nct_ids)
        
        return terms
    
    def _calculate_publication_type_bonus(self, doc: Dict[str, Any]) -> float:
        """
        Calculate publication type bonus.
        
        Args:
            doc: Document
            
        Returns:
            Publication type bonus
        """
        pub_type = doc.get('publication_type', '')
        pub_type_lower = pub_type.lower()
        
        # High-value publication types
        high_value_types = [
            'randomized controlled trial',
            'clinical trial',
            'controlled clinical trial'
        ]
        
        for pub_type_pattern in high_value_types:
            if pub_type_pattern in pub_type_lower:
                return self.config.publication_type_bonus
        
        return 0.0
    
    def _calculate_mesh_bonus(self, doc: Dict[str, Any], entity_pack: EntityPack) -> float:
        """
        Calculate MeSH bonus.
        
        Args:
            doc: Document
            entity_pack: Entity pack
            
        Returns:
            MeSH bonus
        """
        mesh_terms = doc.get('mesh_terms', [])
        if not mesh_terms:
            return 0.0
        
        # Check for Alzheimer Disease MeSH
        alzheimer_mesh_terms = ['alzheimer disease', "alzheimer's disease"]
        
        for mesh_term in mesh_terms:
            mesh_term_lower = str(mesh_term).lower()
            for alzheimer_term in alzheimer_mesh_terms:
                if alzheimer_term in mesh_term_lower:
                    return self.config.mesh_bonus
        
        return 0.0
    
    def _calculate_nct_bonus(self, doc: Dict[str, Any], entity_pack: EntityPack) -> float:
        """
        Calculate NCT bonus.
        
        Args:
            doc: Document
            entity_pack: Entity pack
            
        Returns:
            NCT bonus
        """
        # Check for NCT IDs in document
        doc_text = self._extract_document_text(doc)
        nct_ids = entity_pack.registries.nct_ids
        
        for nct_id in nct_ids:
            if nct_id.lower() in doc_text.lower():
                return self.config.nct_bonus
        
        return 0.0
    
    def _calculate_recency_bonus(self, doc: Dict[str, Any]) -> float:
        """
        Calculate recency bonus.
        
        Args:
            doc: Document
            
        Returns:
            Recency bonus
        """
        try:
            pub_date = doc.get('pubdate', '')
            if not pub_date:
                return 0.0
            
            # Parse publication date (simplified)
            # In real implementation, would use proper date parsing
            import datetime
            
            # Try to extract year from pubdate
            year_match = re.search(r'(\d{4})', pub_date)
            if year_match:
                pub_year = int(year_match.group(1))
                current_year = datetime.datetime.now().year
                
                # Calculate recency bonus
                years_ago = current_year - pub_year
                if years_ago <= self.config.recency_window_months / 12:
                    # Linear decay within recency window
                    recency_factor = 1.0 - (years_ago / (self.config.recency_window_months / 12))
                    return self.config.recency_bonus * recency_factor
            
            return 0.0
            
        except Exception as e:
            self.logger.error(f"Error calculating recency bonus: {e}")
            return 0.0
    
    def rank_documents(
        self, 
        documents: List[Dict[str, Any]], 
        entity_pack: EntityPack
    ) -> List[Tuple[Dict[str, Any], ScoringResult]]:
        """
        Rank documents by advanced scoring.
        
        Args:
            documents: List of documents to rank
            entity_pack: Entity pack for scoring context
            
        Returns:
            List of (document, scoring_result) tuples sorted by score
        """
        try:
            scored_documents = []
            
            for doc in documents:
                # Get policy result if available
                policy_result = doc.get('policy_result')
                
                # Calculate score
                scoring_result = self.calculate_score(doc, entity_pack, policy_result)
                
                scored_documents.append((doc, scoring_result))
            
            # Sort by total score (descending), then by publication date (descending)
            scored_documents.sort(
                key=lambda x: (
                    -x[1].total_score,
                    -self._get_pubdate_numeric(x[0].get('pubdate', '1900-01-01'))
                )
            )
            
            # Assign final ranks
            for i, (doc, scoring_result) in enumerate(scored_documents):
                scoring_result.final_rank = i + 1
            
            self.logger.info(f"Ranked {len(scored_documents)} documents")
            return scored_documents
            
        except Exception as e:
            self.logger.error(f"Error ranking documents: {e}")
            return []
    
    def _get_pubdate_numeric(self, pubdate: str) -> int:
        """Convert publication date to numeric for sorting."""
        try:
            # Extract year from pubdate
            year_match = re.search(r'(\d{4})', pubdate)
            if year_match:
                return int(year_match.group(1))
            return 1900
        except:
            return 1900
    
    def get_scoring_summary(self) -> Dict[str, Any]:
        """Get summary of scoring configuration."""
        return {
            'base_score_weight': self.config.base_score_weight,
            'publication_type_bonus': self.config.publication_type_bonus,
            'mesh_bonus': self.config.mesh_bonus,
            'nct_bonus': self.config.nct_bonus,
            'recency_bonus': self.config.recency_bonus,
            'max_recency_bonus': self.config.max_recency_bonus,
            'recency_window_months': self.config.recency_window_months
        }


class ScoreCalculator:
    """Utility class for score calculations."""
    
    @staticmethod
    def normalize_scores(scores: List[float]) -> List[float]:
        """
        Normalize scores to 0-1 range.
        
        Args:
            scores: List of scores
            
        Returns:
            Normalized scores
        """
        if not scores:
            return []
        
        min_score = min(scores)
        max_score = max(scores)
        
        if max_score == min_score:
            return [1.0] * len(scores)
        
        return [(score - min_score) / (max_score - min_score) for score in scores]
    
    @staticmethod
    def calculate_percentile_rank(scores: List[float], target_score: float) -> float:
        """
        Calculate percentile rank of target score.
        
        Args:
            scores: List of scores
            target_score: Target score
            
        Returns:
            Percentile rank (0-100)
        """
        if not scores:
            return 0.0
        
        sorted_scores = sorted(scores)
        count_below = sum(1 for score in sorted_scores if score < target_score)
        
        return (count_below / len(scores)) * 100
