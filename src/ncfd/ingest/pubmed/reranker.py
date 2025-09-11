"""
Universal reranking system for PubMed search results.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from ...entities.schema import EntityPack
from .policy_engine import RetrievalPolicy, PolicyResult
from .advanced_scorer import AdvancedDocumentScorer, ScoringResult
from .guardrails import GuardrailsSystem, GuardrailResult

logger = logging.getLogger(__name__)


@dataclass
class RerankConfig:
    """Configuration for document reranking."""
    feat_weights: Dict[str, float]
    require_any: List[str]
    mechanism_requires_must: bool = True
    drop_if_cannot_without_must: bool = True
    min_score_threshold: float = 0.0
    max_results: Optional[int] = None


class PubMedReranker:
    """Universal reranker for PubMed search results."""
    
    def __init__(self, config: Optional[RerankConfig] = None):
        """
        Initialize reranker.
        
        Args:
            config: Reranking configuration
        """
        self.config = config or self._get_default_config()
        
        # New retrieval system components (optional)
        self.retrieval_policy = None
        self.advanced_scorer = None
        self.guardrails_system = None
    
    def inject_retrieval_components(self, retrieval_policy: RetrievalPolicy, 
                                 advanced_scorer: AdvancedDocumentScorer,
                                 guardrails_system: GuardrailsSystem):
        """Inject new retrieval system components into the reranker."""
        self.retrieval_policy = retrieval_policy
        self.advanced_scorer = advanced_scorer
        self.guardrails_system = guardrails_system
        logger.info("Injected new retrieval components into reranker")
    
    def _get_default_config(self) -> RerankConfig:
        """Get default reranking configuration."""
        return RerankConfig(
            feat_weights={
                "bm25": 1.0,
                "has_must": 3.0,
                "should_hits_capped": 1.0,
                "cannot_without_must": -2.0,
                "pubtype_trial": 1.5,
                "mesh_primary": 0.5,
                "nct_si": 1.0,
                "recency": 0.3
            },
            require_any=["drug_tiab", "company_tiab", "nct_si"],
            mechanism_requires_must=True,
            drop_if_cannot_without_must=True,
            min_score_threshold=0.0,
            max_results=None
        )
    
    def rerank_documents(self, docs: List[Dict], rules: Dict[str, List[str]]) -> List[Dict]:
        """
        Rerank documents based on rules and features.
        
        Args:
            docs: List of documents to rerank
            rules: Must/should/cannot rules
            
        Returns:
            Reranked list of documents
        """
        if not docs:
            return []
        
        scored_docs = []
        
        for doc in docs:
            try:
                score = self._calculate_score(doc, rules)
                
                # Apply guards
                if not self._passes_guards(doc, rules, score):
                    continue
                
                # Apply minimum score threshold
                if score < self.config.min_score_threshold:
                    continue
                
                doc['rerank_score'] = score
                scored_docs.append(doc)
                
            except Exception as e:
                logger.warning(f"Error scoring document {doc.get('pmid', 'unknown')}: {e}")
                continue
        
        # Sort by score desc, then pubdate desc, then PMID asc
        scored_docs.sort(key=lambda x: (
            -x['rerank_score'], 
            -self._get_pubdate_numeric(x.get('pubdate', '1900-01-01')), 
            x.get('pmid', '0')
        ))
        
        # Apply max results limit
        if self.config.max_results:
            scored_docs = scored_docs[:self.config.max_results]
        
        logger.info(f"Reranked {len(scored_docs)} documents from {len(docs)} input")
        return scored_docs
    
    def rerank_with_new_system(self, docs: List[Dict], entity_pack: EntityPack) -> List[Dict]:
        """
        Rerank documents using the new retrieval system components.
        
        Args:
            docs: List of documents to rerank
            entity_pack: Entity pack for validation context
            
        Returns:
            Reranked list of documents with new scoring
        """
        if not docs:
            return []
        
        if not all([self.retrieval_policy, self.advanced_scorer, self.guardrails_system]):
            logger.warning("New retrieval system components not available, falling back to legacy reranking")
            return self.rerank_documents(docs, self._convert_entity_pack_to_rules(entity_pack))
        
        scored_docs = []
        
        for doc in docs:
            try:
                # Apply policy engine validation
                policy_result = self.retrieval_policy.validate_document(doc, entity_pack)
                
                # Apply guardrails
                guardrail_results = self.guardrails_system.validate_document(doc, entity_pack)
                
                # Check if document should be rejected
                if self.guardrails_system.should_reject_document(guardrail_results):
                    logger.debug(f"Document {doc.get('pmid', 'unknown')} rejected by guardrails")
                    continue
                
                # Apply advanced scoring
                scoring_result = self.advanced_scorer.calculate_score(doc, entity_pack)
                
                # Combine scores
                total_score = (
                    scoring_result.total_score + 
                    policy_result.total_score + 
                    self.guardrails_system.get_total_penalty(guardrail_results)
                )
                
                doc['rerank_score'] = total_score
                doc['policy_result'] = policy_result
                doc['scoring_result'] = scoring_result
                doc['guardrail_results'] = guardrail_results
                scored_docs.append(doc)
                
            except Exception as e:
                logger.warning(f"Error scoring document {doc.get('pmid', 'unknown')}: {e}")
                continue
        
        # Sort by score desc, then pubdate desc, then PMID asc
        scored_docs.sort(key=lambda x: (
            -x['rerank_score'], 
            -self._get_pubdate_numeric(x.get('pubdate', '1900-01-01')), 
            x.get('pmid', '0')
        ))
        
        # Apply max results limit
        if self.config.max_results:
            scored_docs = scored_docs[:self.config.max_results]
        
        logger.info(f"Reranked {len(scored_docs)} documents using new retrieval system from {len(docs)} input")
        return scored_docs
    
    def _convert_entity_pack_to_rules(self, entity_pack: EntityPack) -> Dict[str, List[str]]:
        """Convert entity pack to legacy rules format for fallback."""
        return {
            'must': (
                entity_pack.asset.aliases + 
                entity_pack.company.aliases + 
                entity_pack.registries.nct_ids +
                [entity_pack.asset.canonical, entity_pack.company.canonical]
            ),
            'should': entity_pack.indications.synonyms + entity_pack.indications.primary,
            'cannot': entity_pack.get_cannot_link_terms()
        }
    
    def _calculate_score(self, doc: Dict, rules: Dict[str, List[str]]) -> float:
        """Calculate rerank score for a document."""
        score = 0.0
        
        # BM25 base score (if available)
        if 'bm25_score' in doc:
            score += doc['bm25_score'] * self.config.feat_weights.get('bm25', 1.0)
        
        # Must-link terms
        if self._has_must_terms(doc, rules['must']):
            score += self.config.feat_weights.get('has_must', 3.0)
        
        # Should-link terms (capped)
        should_hits = self._count_should_terms(doc, rules['should'])
        score += min(should_hits, 3) * self.config.feat_weights.get('should_hits_capped', 1.0)
        
        # Cannot terms without must
        if self._has_cannot_without_must(doc, rules['cannot'], rules['must']):
            score += self.config.feat_weights.get('cannot_without_must', -2.0)
        
        # Publication type bonus
        if self._is_trial_publication(doc):
            score += self.config.feat_weights.get('pubtype_trial', 1.5)
        
        # MeSH primary indication
        if self._has_primary_mesh(doc, rules['should'][:1]):
            score += self.config.feat_weights.get('mesh_primary', 0.5)
        
        # NCT in secondary source
        if self._has_nct_si(doc):
            score += self.config.feat_weights.get('nct_si', 1.0)
        
        # Recency bonus
        if self._is_recent(doc):
            score += self.config.feat_weights.get('recency', 0.3)
        
        return score
    
    def _passes_guards(self, doc: Dict, rules: Dict[str, List[str]], score: float) -> bool:
        """Check if document passes guard rules."""
        # Require at least one must-link
        if not self._has_must_terms(doc, rules['must']):
            return False
        
        # Mechanism requires must-link
        if self.config.mechanism_requires_must:
            if self._has_only_mechanism(doc, rules['mechanism'], rules['must']):
                return False
        
        # Drop if cannot terms without must
        if self.config.drop_if_cannot_without_must:
            if self._has_cannot_without_must(doc, rules['cannot'], rules['must']):
                return False
        
        return True
    
    def _has_must_terms(self, doc: Dict, must_terms: List[str]) -> bool:
        """Check if document contains any must-link terms."""
        text = self._get_document_text(doc).lower()
        return any(term.lower() in text for term in must_terms)
    
    def _count_should_terms(self, doc: Dict, should_terms: List[str]) -> int:
        """Count should-link terms in document."""
        text = self._get_document_text(doc).lower()
        return sum(1 for term in should_terms if term.lower() in text)
    
    def _has_cannot_without_must(self, doc: Dict, cannot_terms: List[str], must_terms: List[str]) -> bool:
        """Check if document has cannot terms without must terms."""
        text = self._get_document_text(doc).lower()
        has_cannot = any(term.lower() in text for term in cannot_terms)
        has_must = self._has_must_terms(doc, must_terms)
        return has_cannot and not has_must
    
    def _is_trial_publication(self, doc: Dict) -> bool:
        """Check if document is a trial publication."""
        pub_types = doc.get('publication_types', [])
        trial_types = ['Randomized Controlled Trial', 'Clinical Trial', 'Controlled Clinical Trial']
        return any(pt in trial_types for pt in pub_types)
    
    def _has_primary_mesh(self, doc: Dict, primary_terms: List[str]) -> bool:
        """Check if document has primary MeSH terms."""
        mesh_terms = doc.get('mesh_terms', [])
        return any(term.lower() in [m.lower() for m in mesh_terms] for term in primary_terms)
    
    def _has_nct_si(self, doc: Dict) -> bool:
        """Check if document has NCT in secondary source."""
        secondary_ids = doc.get('secondary_source_ids', [])
        if isinstance(secondary_ids, str):
            return 'nct' in secondary_ids.lower()
        elif isinstance(secondary_ids, list):
            return any('nct' in str(sid).lower() for sid in secondary_ids)
        return False
    
    def _is_recent(self, doc: Dict, years_threshold: int = 5) -> bool:
        """Check if document is recent."""
        pubdate = doc.get('pubdate')
        if not pubdate:
            return False
        
        try:
            # Handle different date formats
            if isinstance(pubdate, str):
                # Extract year from date string
                year_match = re.search(r'(\d{4})', pubdate)
                if year_match:
                    year = int(year_match.group(1))
                else:
                    return False
            elif isinstance(pubdate, int):
                year = pubdate
            else:
                return False
            
            from datetime import datetime
            current_year = datetime.now().year
            return (current_year - year) <= years_threshold
            
        except (ValueError, TypeError):
            return False
    
    def _has_only_mechanism(self, doc: Dict, mechanism_terms: List[str], must_terms: List[str]) -> bool:
        """Check if document has only mechanism terms without must terms."""
        text = self._get_document_text(doc).lower()
        has_mechanism = any(term.lower() in text for term in mechanism_terms)
        has_must = self._has_must_terms(doc, must_terms)
        return has_mechanism and not has_must
    
    def _get_document_text(self, doc: Dict) -> str:
        """Get combined text from document."""
        title = doc.get('title', '')
        abstract = doc.get('abstract', '')
        return f"{title} {abstract}".strip()
    
    def _get_pubdate_numeric(self, pubdate: str) -> int:
        """Convert pubdate string to numeric value for sorting."""
        try:
            if isinstance(pubdate, str):
                # Extract year from date string
                year_match = re.search(r'(\d{4})', pubdate)
                if year_match:
                    return int(year_match.group(1))
            elif isinstance(pubdate, int):
                return pubdate
        except (ValueError, TypeError):
            pass
        return 1900  # Default to 1900 for invalid dates
    
    def get_rerank_stats(self, docs: List[Dict]) -> Dict[str, Any]:
        """
        Get statistics about reranked documents.
        
        Args:
            docs: List of reranked documents
            
        Returns:
            Dictionary with rerank statistics
        """
        if not docs:
            return {"count": 0, "avg_score": 0.0, "score_range": (0.0, 0.0)}
        
        scores = [doc.get('rerank_score', 0.0) for doc in docs]
        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)
        
        return {
            "count": len(docs),
            "avg_score": avg_score,
            "min_score": min_score,
            "max_score": max_score,
            "score_range": (min_score, max_score)
        }
    
    def filter_by_score(self, docs: List[Dict], min_score: float) -> List[Dict]:
        """
        Filter documents by minimum score.
        
        Args:
            docs: List of documents
            min_score: Minimum score threshold
            
        Returns:
            Filtered list of documents
        """
        return [doc for doc in docs if doc.get('rerank_score', 0.0) >= min_score]
    
    def get_top_k(self, docs: List[Dict], k: int) -> List[Dict]:
        """
        Get top k documents.
        
        Args:
            docs: List of documents
            k: Number of top documents to return
            
        Returns:
            Top k documents
        """
        return docs[:k] if docs else []
