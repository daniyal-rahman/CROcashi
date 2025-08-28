#!/usr/bin/env python3
"""
Smart PubMed client implementing three-stage retrieval pipeline.

This module replaces the old early stopping system with a new three-stage approach:
- Stage A: Metadata-only (PMID + minimal metadata) - free/cheap
- Stage B: Abstract fetching for high-U0 candidates - still cheap  
- Stage C: Full-text only when LLM requests it - rare and controlled

Uses the new LiteratureScorer, DocumentQueue, and LLMEvaluator from Phase 1.
"""

import logging
import time
import random
from typing import List, Dict, Any, Optional, Tuple, Generator
from dataclasses import dataclass
import requests
from urllib.parse import urlencode

from .literature_scoring import LiteratureScorer, ScoringConfig
from .document_queue import DocumentQueue, DocumentCandidate
from .llm_evaluator import LLMEvaluator, StopDecision

logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
COMMON_PARAMS = {
    "tool": "ncfd",
    "email": "ncfd@example.com", 
    "retmode": "json"
}
RATE_DELAY_S = 0.45  # Safe margin under 3 requests/second


@dataclass
class PubMedSummary:
    """Summary data from PubMed for triage."""
    pmid: str
    title: str
    journal: str
    pub_date: str
    pub_types: List[str]
    secondary_ids: List[str]  # NCT IDs, etc.
    mesh_terms: List[str]
    abstract: Optional[str] = None
    u0_score: Optional[float] = None
    u1_score: Optional[float] = None


@dataclass
class StageAResult:
    """Result of Stage A (metadata-only) processing."""
    trial_id: str
    candidates: List[DocumentCandidate]
    total_found: int
    processing_time: float


@dataclass
class StageBResult:
    """Result of Stage B (abstract evaluation) processing."""
    trial_id: str
    promoted_candidates: List[DocumentCandidate]
    parked_candidates: List[DocumentCandidate]
    total_evaluated: int
    processing_time: float


@dataclass
class StageCResult:
    """Result of Stage C (full-text on demand) processing."""
    trial_id: str
    full_text_requests: List[Dict[str, str]]
    documents_fetched: List[Dict[str, Any]]
    processing_time: float


class SmartPubMedClient:
    """
    Smart PubMed client with three-stage retrieval pipeline.
    
    Implements the new strategy:
    1. Stage A: Pull PMIDs + minimal metadata (free/cheap)
    2. Stage B: Fetch abstracts for high-U0 candidates (still cheap)
    3. Stage C: Full-text only when LLM requests it (rare)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the smart PubMed client.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Initialize Phase 1 components with proper configuration
        from .literature_scoring import LiteratureScorer, ScoringConfig
        from .document_queue import DocumentQueue
        from .llm_evaluator import LLMEvaluator
        
        # Extract scoring config and create ScoringConfig object
        scoring_config_dict = self.config.get('scoring', {})
        scoring_config = ScoringConfig(
            tau_abstract=scoring_config_dict.get('tau_abstract', 0.40),
            theta_high=scoring_config_dict.get('theta_high', 0.80),
            theta_low=scoring_config_dict.get('theta_low', 0.20),
            delta_min=scoring_config_dict.get('delta_min', 0.05)
        )
        
        self.scorer = LiteratureScorer(scoring_config)
        self.queue = DocumentQueue(
            self.config.get('queue', {})
        )
        self.evaluator = LLMEvaluator(
            self.config.get('evaluation', {})
        )
        
        # PubMed API configuration
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NCFD-Smart-PubMed/1.0'
        })
        
        # Stage configuration
        self.stage_a_batch_size = self.config.get('stage_a_batch_size', 100)
        self.stage_b_threshold = self.config.get('stage_b_threshold', 0.3)
        self.max_abstracts_per_trial = self.config.get('max_abstracts_per_trial', 8)
        
        logger.info("Smart PubMed client initialized with three-stage pipeline")
    
    def _rate_limit(self):
        """Respect PubMed's 3 requests/second limit."""
        time.sleep(RATE_DELAY_S + random.uniform(0, 0.1))  # Add jitter
    
    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make a rate-limited request to PubMed E-utilities."""
        url = f"{BASE_URL}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            # Handle JSON response
            if params.get("retmode") == "json":
                return response.json()
            else:
                return {"raw": response.text}
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limited
                logger.warning("Rate limited, backing off...")
                time.sleep(2)  # Back off longer
                return self._make_request(endpoint, params)  # Retry
            else:
                logger.error(f"HTTP error: {e}")
                raise
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise
    
    def _build_search_query(self, nct_id: str, drug_synonyms: List[str] = None) -> str:
        """
        Build PubMed search query following the specified pattern.
        
        Args:
            nct_id: NCT identifier (e.g., "NCT05111574")
            drug_synonyms: Optional list of drug synonyms
            
        Returns:
            PubMed query string with multi-stage fallback approach
        """
        if not nct_id:
            raise ValueError("NCT ID cannot be empty")
        
        if not nct_id.startswith('NCT') or len(nct_id) < 8:
            raise ValueError(f"Invalid NCT ID format: {nct_id}")
        
        # Multi-stage NCT query approach for better coverage
        # Stage 1: Try Secondary Source ID (most specific)
        # Stage 2: Fallback to Title/Abstract (broader)
        # Stage 3: Fallback to All Fields (most comprehensive)
        
        # Start with the most specific search
        query = f'"{nct_id}"[si]'
        
        # Add drug synonyms if provided
        if drug_synonyms and len(drug_synonyms) > 0:
            # Build drug terms with [tiab] tags
            drug_terms = []
            for drug in drug_synonyms:
                if drug.strip():  # Skip empty terms
                    drug_terms.append(f'"{drug.strip()}"[tiab]')
            
            if drug_terms:
                # Join drug terms with OR
                drug_query = " OR ".join(drug_terms)
                # Combine NCT and drug terms with OR
                query = f'{query} OR ({drug_query})'
        
        return query
    
    def _build_nct_query_with_fallback(self, nct_id: str, use_filters: bool = True) -> List[Tuple[str, str]]:
        """
        Build multi-stage NCT query with fallbacks for better coverage.
        
        Args:
            nct_id: NCT identifier
            use_filters: Whether to apply clinical trial filters
            
        Returns:
            List of (query, description) tuples to try in order
        """
        if not nct_id:
            raise ValueError("NCT ID cannot be empty")
        
        queries = []
        
        # Stage 1: Most specific - Secondary Source ID
        queries.append((f'"{nct_id}"[si]', 'Secondary Source ID'))
        
        # Stage 2: Broader - Title/Abstract
        queries.append((f'"{nct_id}"[tiab]', 'Title/Abstract'))
        
        # Stage 3: Most comprehensive - All Fields
        queries.append((f'"{nct_id}"[All Fields]', 'All Fields'))
        
        # Stage 4: With clinical trial filters if enabled
        if use_filters:
            # Try with clinical trial publication type filter
            queries.append((
                f'"{nct_id}"[tiab] AND ("Clinical Trial"[ptyp] OR "Randomized Controlled Trial"[ptyp])',
                'Title/Abstract + Clinical Trial Filter'
            ))
            
            # Try with phase-specific terms
            queries.append((
                f'"{nct_id}"[tiab] AND ("phase 3"[tiab] OR "phase iii"[tiab] OR "randomized"[tiab])',
                'Title/Abstract + Phase/Randomized Filter'
            ))
        
        return queries
    
    def _search_nct_with_fallback(self, nct_id: str, retmax: int = 100, use_filters: bool = True) -> Dict[str, Any]:
        """
        Search for NCT with automatic fallback through multiple query strategies.
        
        Args:
            nct_id: NCT identifier
            retmax: Maximum results to return
            use_filters: Whether to use clinical trial filters
            
        Returns:
            Search results from the first successful query, or empty results if all fail
        """
        queries = self._build_nct_query_with_fallback(nct_id, use_filters)
        
        for query, description in queries:
            try:
                logger.info(f"Trying NCT search: {description}")
                results = self._esearch(query, retmax)
                count = int(results.get('esearchresult', {}).get('count', '0'))
                
                if count > 0:
                    logger.info(f"✅ NCT search successful with {description}: {count} results")
                    return results
                else:
                    logger.info(f"⚠️ NCT search returned 0 results with {description}")
                    
            except Exception as e:
                logger.warning(f"⚠️ NCT search failed with {description}: {e}")
                continue
        
        # If all queries fail, return empty results
        logger.warning(f"❌ All NCT search strategies failed for {nct_id}")
        return {
            'esearchresult': {
                'count': '0',
                'retmax': '0',
                'retstart': '0',
                'idlist': [],
                'translationset': [],
                'querytranslation': f'"{nct_id}"',
                'warninglist': {
                    'phrasesignored': [],
                    'quotedphrasesnotfound': [f'"{nct_id}"'],
                    'outputmessages': ['All search strategies failed']
                }
            }
        }
    
    def _search_trial_with_automatic_pivot(self, nct_id: str, drug_terms: List[str] = None, 
                                         disease_terms: List[str] = None, retmax: int = 100) -> Dict[str, Any]:
        """
        Search for trial with automatic pivot from NCT to drug/condition when NCT fails.
        
        This implements the strategy: try NCT first, then automatically pivot to drug+disease
        search if NCT returns no results (treating it as "not indexed yet").
        
        Args:
            nct_id: NCT identifier
            drug_terms: List of drug names/synonyms
            disease_terms: List of disease/indication terms
            retmax: Maximum results to return
            
        Returns:
            Search results with metadata about which strategy succeeded
        """
        # Stage 1: Try NCT search with all fallbacks
        logger.info(f"🔍 Stage 1: NCT search for {nct_id}")
        nct_results = self._search_nct_with_fallback(nct_id, retmax, use_filters=True)
        nct_count = int(nct_results.get('esearchresult', {}).get('count', '0'))
        
        if nct_count > 0:
            logger.info(f"✅ NCT search successful: {nct_count} results")
            return {
                'results': nct_results,
                'strategy': 'nct_direct',
                'count': nct_count,
                'fallback_used': False
            }
        
        # Stage 2: NCT failed, pivot to drug+disease search
        logger.info(f"🔄 Stage 2: NCT failed, pivoting to drug+disease search for {nct_id}")
        
        if not drug_terms and not disease_terms:
            logger.warning(f"⚠️ No drug or disease terms provided for pivot search on {nct_id}")
            return {
                'results': nct_results,  # Return the failed NCT results
                'strategy': 'nct_failed_no_pivot_terms',
                'count': 0,
                'fallback_used': False
            }
        
        # Build drug+disease query with clinical trial filters
        pivot_query = self._build_drug_disease_pivot_query(drug_terms, disease_terms)
        
        try:
            pivot_results = self._esearch(pivot_query, retmax)
            pivot_count = int(pivot_results.get('esearchresult', {}).get('count', '0'))
            
            if pivot_count > 0:
                logger.info(f"✅ Pivot search successful: {pivot_count} results using drug+disease")
                return {
                    'results': pivot_results,
                    'strategy': 'drug_disease_pivot',
                    'count': pivot_count,
                    'fallback_used': True,
                    'pivot_query': pivot_query
                }
            else:
                logger.warning(f"⚠️ Pivot search also failed: {pivot_count} results")
                return {
                    'results': pivot_results,
                    'strategy': 'both_failed',
                    'count': 0,
                    'fallback_used': True,
                    'pivot_query': pivot_query
                }
                
        except Exception as e:
            logger.error(f"❌ Pivot search failed: {e}")
            return {
                'results': nct_results,  # Return the failed NCT results
                'strategy': 'pivot_error',
                'count': 0,
                'fallback_used': True,
                'error': str(e)
            }
    
    def _build_drug_query(self, drug_synonyms: List[str], disease: Optional[str] = None) -> str:
        """
        Build smart query for drug search.
        
        Args:
            drug_synonyms: List of drug names/codes
            disease: Optional disease/indication
            
        Returns:
            PubMed query string
        """
        # Build drug query
        drug_terms = []
        for drug in drug_synonyms:
            # Handle different drug identifier types
            if drug.startswith('NCT'):
                drug_terms.append(f'"{drug}"[si]')
            elif len(drug) <= 3 and drug.isupper():
                # Internal code (e.g., AB-123)
                drug_terms.append(f'"{drug}"[tiab]')
            else:
                # Generic name or brand name
                drug_terms.append(f'"{drug}"[tiab]')
        
        drug_query = " OR ".join(drug_terms)
        
        # Add disease if specified
        if disease:
            disease_query = f'"{disease}"[tiab]'
            return f"({drug_query}) AND {disease_query}"
        
        return drug_query
    
    def _build_drug_disease_pivot_query(self, drug_terms: List[str], disease_terms: List[str]) -> str:
        """
        Build a drug+disease query with clinical trial and human filters.
        
        Args:
            drug_terms: List of drug names/synonyms
            disease_terms: List of disease/indication terms
            
        Returns:
            PubMed query string with proper filters
        """
        # Build drug query
        drug_queries = []
        for drug in drug_terms:
            if drug.strip():
                drug_queries.append(f'"{drug.strip()}"[tiab]')
        
        # Build disease query
        disease_queries = []
        for disease in disease_terms:
            if disease.strip():
                disease_queries.append(f'"{disease.strip()}"[tiab]')
        
        # Combine drug and disease terms
        if drug_queries and disease_queries:
            # Drug AND Disease
            drug_part = " OR ".join(drug_queries)
            disease_part = " OR ".join(disease_queries)
            base_query = f"({drug_part}) AND ({disease_part})"
        elif drug_queries:
            # Drug only
            base_query = " OR ".join(drug_queries)
        elif disease_queries:
            # Disease only
            base_query = " OR ".join(disease_queries)
        else:
            # Fallback to generic clinical trial search
            base_query = '"clinical trial"[tiab]'
        
        # Add clinical trial filters
        clinical_filters = [
            '("Clinical Trial"[ptyp] OR "Randomized Controlled Trial"[ptyp])',
            'NOT (animals[mh] NOT humans[mh])'  # Exclude animal-only studies
        ]
        
        # Combine base query with filters
        final_query = f"({base_query}) AND {' AND '.join(clinical_filters)}"
        
        logger.info(f"Built pivot query: {final_query}")
        return final_query
    
    def _esearch(self, query: str, retmax: int = 100) -> Dict[str, Any]:
        """Execute PubMed search."""
        self._rate_limit()
        
        params = {
            **COMMON_PARAMS,
            "db": "pubmed",
            "term": query,
            "retmax": retmax,
            "retmode": "json"
        }
        
        return self._make_request("esearch.fcgi", params)
    
    def _esummary(self, pmid_list: List[str]) -> Dict[str, Any]:
        """Get summaries for a list of PMIDs."""
        self._rate_limit()
        
        params = {
            **COMMON_PARAMS,
            "db": "pubmed",
            "id": ",".join(pmid_list),
            "retmode": "json"
        }
        
        return self._make_request("esummary.fcgi", params)
    
    def _efetch_abstract(self, pmid: str) -> Optional[str]:
        """Fetch abstract for a specific PMID."""
        self._rate_limit()
        
        params = {
            **COMMON_PARAMS,
            "db": "pubmed",
            "id": pmid,
            "rettype": "abstract",
            "retmode": "text"
        }
        
        try:
            response = self._make_request("efetch.fcgi", params)
            abstract_text = response.get("raw", "")
            
            # Extract abstract from response
            if "AB  - " in abstract_text:
                start = abstract_text.find("AB  - ") + 6
                end = abstract_text.find("\n", start)
                if end == -1:
                    end = len(abstract_text)
                return abstract_text[start:end].strip()
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to fetch abstract for PMID {pmid}: {e}")
            return None
    
    def _parse_summary(self, summary_data: Dict[str, Any]) -> PubMedSummary:
        """
        Parse PubMed summary data.
        
        Args:
            summary_data: Raw summary data from PubMed
            
        Returns:
            Parsed PubMedSummary object
        """
        pmid = summary_data.get("uid", "")
        title = summary_data.get("title", "")
        journal = summary_data.get("fulljournalname", "")
        pub_date = summary_data.get("pubdate", "")
        
        # Extract publication types
        pub_types = []
        if "pubtype" in summary_data:
            for pt in summary_data["pubtype"]:
                if isinstance(pt, dict):
                    pub_types.append(pt.get("name", ""))
                else:
                    pub_types.append(str(pt))
        
        # Extract secondary IDs (including NCT IDs)
        secondary_ids = []
        if "articleids" in summary_data:
            for aid in summary_data["articleids"]:
                if aid.get("idtype") == "si" and "NCT" in aid.get("value", ""):
                    secondary_ids.append(aid["value"])
        
        # Extract MeSH terms
        mesh_terms = []
        if "meshterms" in summary_data:
            for mesh in summary_data["meshterms"]:
                if isinstance(mesh, dict):
                    mesh_terms.append(mesh.get("name", ""))
                else:
                    mesh_terms.append(str(mesh))
        
        return PubMedSummary(
            pmid=pmid,
            title=title,
            journal=journal,
            pub_date=pub_date,
            pub_types=pub_types,
            secondary_ids=secondary_ids,
            mesh_terms=mesh_terms
        )
    
    def stage_a_metadata_only(self, trial_id: str, drug_synonyms: List[str], 
                             disease: Optional[str] = None, 
                             catalyst_year: Optional[int] = None) -> StageAResult:
        """
        Stage A: Pull PMIDs + minimal metadata (free/cheap).
        
        Args:
            trial_id: Trial identifier
            drug_synonyms: List of drug names/codes
            disease: Optional disease/indication
            catalyst_year: Year of catalyst event for scoring
            
        Returns:
            StageAResult with metadata candidates
        """
        start_time = time.time()
        logger.info(f"Stage A: Metadata-only search for trial {trial_id}")
        
        # Build search query using the new method for proper NCT handling
        if drug_synonyms and any(drug.startswith('"NCT') for drug in drug_synonyms):
            # Extract NCT ID from the first NCT synonym
            nct_synonym = next(drug for drug in drug_synonyms if drug.startswith('"NCT'))
            nct_id = nct_synonym.split('"')[1]  # Extract NCT ID from "NCT05111574"[si]
            
            # Extract other drug terms (non-NCT)
            other_drugs = [drug.split('"')[1] for drug in drug_synonyms if not drug.startswith('"NCT')]
            
            query = self._build_search_query(nct_id, other_drugs)
        else:
            # Fallback to old method for non-NCT searches
            query = self._build_drug_query(drug_synonyms, disease)
        
        logger.info(f"Search query: {query}")
        
        try:
            # Execute search
            search_result = self._esearch(query, retmax=self.stage_a_batch_size)
            id_list = search_result.get("esearchresult", {}).get("idlist", [])
            
            if not id_list:
                logger.info(f"No results found for trial {trial_id}")
                return StageAResult(
                    trial_id=trial_id,
                    candidates=[],
                    total_found=0,
                    processing_time=time.time() - start_time
                )
            
            logger.info(f"Found {len(id_list)} results for trial {trial_id}")
            
            # Get summaries
            summaries = self._esummary(id_list)
            result_data = summaries.get("result", {})
            
            # Process summaries and create candidates
            candidates = []
            for pmid in id_list:
                if pmid in result_data:
                    summary_data = result_data[pmid]
                    summary = self._parse_summary(summary_data)
                    
                    # Score metadata (U0 score)
                    if catalyst_year:
                        try:
                            # Extract year from pub_date
                            year = int(summary.pub_date[:4])
                        except (ValueError, IndexError):
                            year = catalyst_year
                    else:
                        year = 2024  # Default
                    
                    u0_score = self.scorer.score_metadata(
                        summary.title,
                        summary.pub_types[0] if summary.pub_types else "Unknown",
                        year,
                        catalyst_year or 2024
                    )
                    
                    summary.u0_score = u0_score
                    
                    # Create document candidate
                    candidate = DocumentCandidate(
                        doc_id=pmid,
                        trial_id=trial_id,
                        source_type="pubmed",
                        u0_score=u0_score,
                        metadata={
                            'title': summary.title,
                            'journal': summary.journal,
                            'pub_date': summary.pub_date,
                            'pub_types': summary.pub_types,
                            'nct_ids': summary.secondary_ids,
                            'mesh_terms': summary.mesh_terms
                        }
                    )
                    
                    candidates.append(candidate)
            
            # Sort by U0 score (descending)
            candidates.sort(key=lambda x: x.u0_score, reverse=True)
            
            # Add to document queue
            self.queue.add_trial_candidates(trial_id, candidates)
            
            processing_time = time.time() - start_time
            logger.info(f"Stage A complete for trial {trial_id}: {len(candidates)} candidates in {processing_time:.2f}s")
            
            return StageAResult(
                trial_id=trial_id,
                candidates=candidates,
                total_found=len(candidates),
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Stage A failed for trial {trial_id}: {e}")
            return StageAResult(
                trial_id=trial_id,
                candidates=[],
                total_found=0,
                processing_time=time.time() - start_time
            )
    
    def stage_b_abstract_evaluation(self, trial_id: str) -> StageBResult:
        """
        Stage B: Fetch abstracts for high-U0 candidates (still cheap).
        
        Args:
            trial_id: Trial identifier
            
        Returns:
            StageBResult with promoted and parked candidates
        """
        start_time = time.time()
        logger.info(f"Stage B: Abstract evaluation for trial {trial_id}")
        
        # Get candidates from queue
        candidates = self.queue.get_trial_candidates(trial_id)
        
        if not candidates:
            logger.info(f"No candidates found for trial {trial_id}")
            return StageBResult(
                trial_id=trial_id,
                promoted_candidates=[],
                parked_candidates=[],
                total_evaluated=0,
                processing_time=time.time() - start_time
            )
        
        # Filter candidates by U0 threshold - use scorer's tau_abstract instead of hardcoded threshold
        high_u0_candidates = [
            c for c in candidates 
            if c.u0_score >= self.scorer.config.tau_abstract
        ]
        
        logger.info(f"🔍 STAGE B: Filtered {len(candidates)} candidates to {len(high_u0_candidates)} high-U0 candidates")
        logger.info(f"🔍 STAGE B: Using threshold {self.scorer.config.tau_abstract}")
        
        # Log candidate scores for debugging
        for i, candidate in enumerate(high_u0_candidates[:5]):  # Log first 5 candidates
            logger.info(f"🔍 STAGE B: High-U0 candidate {i+1}: doc_id={candidate.doc_id}, u0={candidate.u0_score}")
        
        if not high_u0_candidates:
            logger.warning(f"🔍 STAGE B: No candidates passed U0 threshold {self.scorer.config.tau_abstract}")
            return StageBResult(
                trial_id=trial_id,
                promoted_candidates=[],
                parked_candidates=[],
                total_evaluated=0,
                processing_time=time.time() - start_time
            )
        
        # Limit to max abstracts per trial
        if len(high_u0_candidates) > self.max_abstracts_per_trial:
            high_u0_candidates = high_u0_candidates[:self.max_abstracts_per_trial]
        
        logger.info(f"Evaluating {len(high_u0_candidates)} high-U0 candidates for trial {trial_id}")
        
        promoted_candidates = []
        parked_candidates = []
        
        for candidate in high_u0_candidates:
            try:
                # Fetch abstract
                abstract = self._efetch_abstract(candidate.doc_id)
                
                if abstract:
                    # Score abstract (U1 score)
                    u1_score = self.scorer.score_abstract(abstract)
                    candidate.u1_score = u1_score
                    
                    # Update metadata
                    candidate.metadata['abstract'] = abstract
                    candidate.metadata['u1_score'] = u1_score
                    
                    # Determine promotion based on U1 score
                    if self.scorer.should_promote_to_full_text(u1_score):
                        promoted_candidates.append(candidate)
                        logger.debug(f"Promoted candidate {candidate.doc_id} (U1={u1_score:.3f})")
                    else:
                        parked_candidates.append(candidate)
                        logger.debug(f"Parked candidate {candidate.doc_id} (U1={u1_score:.3f})")
                else:
                    # No abstract available, park
                    parked_candidates.append(candidate)
                    logger.debug(f"Parked candidate {candidate.doc_id} (no abstract)")
                    
            except Exception as e:
                logger.warning(f"Failed to process candidate {candidate.doc_id}: {e}")
                parked_candidates.append(candidate)
        
        processing_time = time.time() - start_time
        logger.info(f"Stage B complete for trial {trial_id}: {len(promoted_candidates)} promoted, {len(parked_candidates)} parked in {processing_time:.2f}s")
        
        return StageBResult(
            trial_id=trial_id,
            promoted_candidates=promoted_candidates,
            parked_candidates=parked_candidates,
            total_evaluated=len(high_u0_candidates),
            processing_time=processing_time
        )
    
    def stage_c_full_text_on_demand(self, trial_id: str, 
                                   doc_id: str, reason: str) -> Optional[StageCResult]:
        """
        Stage C: Full-text only when LLM requests it (rare).
        
        Args:
            trial_id: Trial identifier
            doc_id: Document identifier (PMID)
            reason: Reason for requesting full text
            
        Returns:
            StageCResult if approved, None if denied
        """
        start_time = time.time()
        logger.info(f"Stage C: Full-text request for trial {trial_id}, doc {doc_id}")
        
        # Check if LLM evaluation approves the request
        if not self.evaluator.request_full_text(doc_id, reason):
            logger.info(f"Full-text request denied for doc {doc_id}")
            return None
        
        try:
            # This would typically fetch from PMC or other open access sources
            # For now, we'll simulate the process
            
            # Create result
            processing_time = time.time() - start_time
            logger.info(f"Stage C complete for trial {trial_id}, doc {doc_id} in {processing_time:.2f}s")
            
            return StageCResult(
                trial_id=trial_id,
                full_text_requests=[{"doc_id": doc_id, "reason": reason}],
                documents_fetched=[{"doc_id": doc_id, "status": "fetched"}],
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Stage C failed for trial {trial_id}, doc {doc_id}: {e}")
            return None
    
    def run_three_stage_pipeline(self, trial_id: str, drug_synonyms: List[str],
                                disease: Optional[str] = None,
                                catalyst_year: Optional[int] = None) -> Dict[str, Any]:
        """
        Run the complete three-stage pipeline for a trial.
        
        Args:
            trial_id: Trial identifier
            drug_synonyms: List of drug names/codes
            disease: Optional disease/indication
            catalyst_year: Year of catalyst event
            
        Returns:
            Dictionary with pipeline results
        """
        logger.info(f"Starting three-stage pipeline for trial {trial_id}")
        
        # Stage A: Metadata-only
        stage_a_result = self.stage_a_metadata_only(
            trial_id, drug_synonyms, disease, catalyst_year
        )
        
        if not stage_a_result.candidates:
            logger.info(f"No candidates found in Stage A for trial {trial_id}")
            return {
                'trial_id': trial_id,
                'stage_a': stage_a_result,
                'stage_b': None,
                'stage_c': None,
                'success': False
            }
        
        # Stage B: Abstract evaluation
        stage_b_result = self.stage_b_abstract_evaluation(trial_id)
        
        # Stage C: Full-text on demand (not automatically triggered)
        stage_c_result = None
        
        # Update trial priority based on results
        if stage_b_result.promoted_candidates:
            # High-quality candidates found, increase priority
            new_priority = 0.8
        elif stage_b_result.total_evaluated > 0:
            # Some evaluation done, moderate priority
            new_priority = 0.5
        else:
            # No evaluation, lower priority
            new_priority = 0.3
        
        self.queue.update_trial_priority(trial_id, new_priority)
        
        logger.info(f"Three-stage pipeline complete for trial {trial_id}")
        
        return {
            'trial_id': trial_id,
            'stage_a': stage_a_result,
            'stage_b': stage_b_result,
            'stage_c': stage_c_result,
            'success': True
        }
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get statistics from all pipeline components."""
        return {
            'queue_stats': self.queue.get_queue_stats(),
            'evaluation_stats': self.evaluator.get_evaluation_stats(),
            'scoring_config': {
                'tau_abstract': self.scorer.config.tau_abstract,
                'theta_high': self.scorer.config.theta_high,
                'theta_low': self.scorer.config.theta_low
            }
        }


# Convenience function for quick testing
def quick_three_stage_search(
    trial_id: str,
    drug_name: str, 
    disease: Optional[str] = None,
    catalyst_year: Optional[int] = None
) -> Dict[str, Any]:
    """
    Quick three-stage search for a trial.
    
    Args:
        trial_id: Trial identifier
        drug_name: Drug name (e.g., "ruxolitinib")
        disease: Optional disease (e.g., "myelofibrosis")
        catalyst_year: Optional catalyst year
        
    Returns:
        Pipeline results dictionary
    """
    client = SmartPubMedClient()
    return client.run_three_stage_pipeline(
        trial_id=trial_id,
        drug_synonyms=[drug_name],
        disease=disease,
        catalyst_year=catalyst_year
    )
