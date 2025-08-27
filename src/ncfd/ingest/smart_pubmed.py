#!/usr/bin/env python3
"""
Smart PubMed client implementing early stopping pipeline.

Uses PubMed E-utilities (no API key required) with rate limiting and smart triage.
"""

import logging
import time
import random
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import requests
from urllib.parse import urlencode

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
    score: int = 0


@dataclass
class SearchResult:
    """Result of smart search with early stopping decision."""
    decision: str  # "stop" or "promote"
    reason: str
    total_hits: int
    top_summaries: List[PubMedSummary]
    promoted_ids: Optional[List[str]] = None


class SmartPubMedClient:
    """
    Smart PubMed client with early stopping pipeline.
    
    Implements the strategy:
    1. Search with rate limiting
    2. Triage summaries (no abstracts)
    3. Early stop if not promising
    4. Promote only promising papers for deep fetch
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NCFD-Smart-PubMed/1.0'
        })
    
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
    
    def _build_drug_query(self, drug_synonyms: List[str], disease: Optional[str] = None) -> str:
        """
        Build smart query for drug search.
        
        Args:
            drug_synonyms: List of drug names/codes (e.g., ["ruxolitinib", "INCB018424", "Jakafi"])
            disease: Optional disease/indication
            
        Returns:
            PubMed query string
        """
        # Drug synonyms in title/abstract
        drug_part = " OR ".join([f'"{syn}"[tiab]' for syn in drug_synonyms])
        
        if disease:
            # Disease in title/abstract or MeSH major topics
            disease_part = f'"{disease}"[tiab] OR "{disease}"[majr]'
            return f"({drug_part}) AND ({disease_part})"
        else:
            return f"({drug_part})"
    
    def _build_phase_queries(self, drug_synonyms: List[str], disease: Optional[str] = None) -> Dict[str, str]:
        """
        Build the four pass-1 queries as specified in the plan.
        
        Returns:
            Dict with query types and their PubMed queries
        """
        base_drug = " OR ".join([f'"{syn}"[tiab]' for syn in drug_synonyms])
        base_disease = f'"{disease}"[tiab] OR "{disease}"[majr]' if disease else ""
        
        queries = {}
        
        # 1. Phase 1 (first-in-human, dose-escalation)
        if base_disease:
            queries["phase1"] = f"({base_drug}) AND ({base_disease}) AND (\"Clinical Trial, Phase I\"[pt] OR \"first-in-human\"[tiab] OR \"dose-escalation\"[tiab] OR \"3+3\"[tiab]) NOT Review[pt]"
        else:
            queries["phase1"] = f"({base_drug}) AND (\"Clinical Trial, Phase I\"[pt] OR \"first-in-human\"[tiab] OR \"dose-escalation\"[tiab] OR \"3+3\"[tiab]) NOT Review[pt]"
        
        # 2. Phase 2
        if base_disease:
            queries["phase2"] = f"({base_drug}) AND ({base_disease}) AND (\"Clinical Trial, Phase II\"[pt] OR \"randomized\"[tiab]) NOT Review[pt]"
        else:
            queries["phase2"] = f"({base_drug}) AND (\"Clinical Trial, Phase II\"[pt] OR \"randomized\"[tiab]) NOT Review[pt]"
        
        # 3. Preclinical
        if base_disease:
            queries["preclinical"] = f"({base_drug}) AND ({base_disease}) AND (\"Drug Evaluation, Preclinical\"[mh] OR (animals[mh] NOT humans[mh]) OR \"xenograft\"[tiab] OR \"in vivo\"[tiab] OR \"in vitro\"[tiab]) NOT Review[pt]"
        else:
            queries["preclinical"] = f"({base_drug}) AND (\"Drug Evaluation, Preclinical\"[mh] OR (animals[mh] NOT humans[mh]) OR \"xenograft\"[tiab] OR \"in vivo\"[tiab] OR \"in vitro\"[tiab]) NOT Review[pt]"
        
        # 4. Reviews
        if base_disease:
            queries["reviews"] = f"({base_drug}) AND ({base_disease}) AND (Review[pt] OR \"Systematic Review\"[pt] OR \"Meta-Analysis\"[pt])"
        else:
            queries["reviews"] = f"({base_drug}) AND (Review[pt] OR \"Systematic Review\"[pt] OR \"Meta-Analysis\"[pt])"
        
        return queries
    
    def _esearch(self, term: str, retmax: int = 30, sort: str = "relevance") -> Dict[str, Any]:
        """Execute PubMed search with history."""
        params = {
            **COMMON_PARAMS,
            "db": "pubmed",
            "term": term,
            "retmax": retmax,
            "sort": sort,
            "usehistory": "y"
        }
        
        self._rate_limit()
        return self._make_request("esearch.fcgi", params)
    
    def _esummary(self, ids: List[str]) -> Dict[str, Any]:
        """Get summaries for a list of PMIDs."""
        params = {
            **COMMON_PARAMS,
            "db": "pubmed",
            "id": ",".join(ids)
        }
        
        self._rate_limit()
        return self._make_request("esummary.fcgi", params)
    
    def _triage_summary(self, summary: Dict[str, Any]) -> PubMedSummary:
        """
        Score a summary for early stopping decision.
        
        Scoring based on your plan:
        - Direct NCT hit: +3
        - Phase match: +2  
        - Title hints: +1 each
        - Indication match: +1
        """
        pmid = summary.get("uid", "")
        title = summary.get("title", "").lower()
        pub_types = summary.get("pubtype", [])
        secondary_ids = summary.get("articleids", [])
        mesh_terms = summary.get("mesh", [])
        
        # Extract NCT IDs from secondary IDs
        nct_ids = []
        for aid in secondary_ids:
            if aid.get("idtype") == "si" and "NCT" in aid.get("value", ""):
                nct_ids.append(aid["value"])
        
        # Score the summary
        score = 0
        
        # Direct NCT hit (+3)
        if nct_ids:
            score += 3
        
        # Phase match (+2)
        phase_terms = ["Clinical Trial, Phase I", "Clinical Trial, Phase II", "Randomized Controlled Trial"]
        if any(pt in pub_types for pt in phase_terms):
            score += 2
        
        # Title hints (+1 each)
        hints = [
            "primary endpoint", "randomized", "double-blind", "p value", 
            "hazard ratio", "did not meet", "failed to meet", "efficacy",
            "safety", "tolerability", "dose escalation", "first-in-human"
        ]
        score += sum(int(hint in title) for hint in hints)
        
        # Indication match via MeSH (+1)
        if mesh_terms:
            score += 1
        
        return PubMedSummary(
            pmid=pmid,
            title=summary.get("title", ""),
            journal=summary.get("fulljournalname", ""),
            pub_date=summary.get("pubdate", ""),
            pub_types=pub_types,
            secondary_ids=[aid.get("value", "") for aid in secondary_ids],
            mesh_terms=mesh_terms,
            score=score
        )
    
    def smart_search(
        self, 
        drug_synonyms: List[str], 
        disease: Optional[str] = None,
        nct_id: Optional[str] = None,
        k_top: int = 20,
        promote_threshold: int = 4
    ) -> SearchResult:
        """
        Execute smart search with early stopping pipeline.
        
        Args:
            drug_synonyms: List of drug names/codes
            disease: Optional disease/indication
            nct_id: Optional NCT ID to anchor search
            k_top: Number of top results to evaluate
            promote_threshold: Score threshold for promotion
            
        Returns:
            SearchResult with decision and data
        """
        logger.info(f"Starting smart search for drug: {drug_synonyms}")
        if disease:
            logger.info(f"With disease: {disease}")
        if nct_id:
            logger.info(f"Anchored to NCT: {nct_id}")
        
        all_summaries = []
        
        # 1. Build and execute the four phase queries
        phase_queries = self._build_phase_queries(drug_synonyms, disease)
        
        for phase_name, query in phase_queries.items():
            logger.info(f"Searching {phase_name}: {query[:100]}...")
            
            try:
                # Search
                search_result = self._esearch(query, retmax=k_top)
                id_list = search_result.get("esearchresult", {}).get("idlist", [])
                
                if id_list:
                    logger.info(f"Found {len(id_list)} results for {phase_name}")
                    
                    # Get summaries
                    summaries = self._esummary(id_list)
                    result_data = summaries.get("result", {})
                    
                    # Process each summary
                    for pmid in id_list:
                        if pmid in result_data:
                            summary_data = result_data[pmid]
                            summary = self._triage_summary(summary_data)
                            all_summaries.append(summary)
                
            except Exception as e:
                logger.error(f"Error searching {phase_name}: {e}")
                continue
        
        # 2. Add NCT anchor query if provided
        if nct_id:
            try:
                nct_query = f'"{nct_id}"[si]'
                logger.info(f"Searching NCT anchor: {nct_query}")
                
                search_result = self._esearch(nct_query, retmax=10)
                id_list = search_result.get("esearchresult", {}).get("idlist", [])
                
                if id_list:
                    summaries = self._esummary(id_list)
                    result_data = summaries.get("result", {})
                    
                    for pmid in id_list:
                        if pmid in result_data:
                            summary_data = result_data[pmid]
                            summary = self._triage_summary(summary_data)
                            # Boost score for direct NCT match
                            summary.score += 3
                            all_summaries.append(summary)
                            
            except Exception as e:
                logger.error(f"Error searching NCT anchor: {e}")
        
        # 3. Deduplicate and sort by score
        unique_summaries = {}
        for summary in all_summaries:
            if summary.pmid not in unique_summaries:
                unique_summaries[summary.pmid] = summary
            else:
                # Keep the higher score
                if summary.score > unique_summaries[summary.pmid].score:
                    unique_summaries[summary.pmid] = summary
        
        top_summaries = sorted(
            unique_summaries.values(), 
            key=lambda x: x.score, 
            reverse=True
        )[:k_top]
        
        # 4. Smart filtering logic (commented out for now)
        # if not top_summaries:
        #     return SearchResult(
        #         decision="stop",
        #         reason="no hits found",
        #         total_hits=0,
        #         top_summaries=[]
        #     )
        
        # best_score = top_summaries[0].score
        # logger.info(f"Best summary score: {best_score}")
        
        # if best_score < promote_threshold:
        #     return SearchResult(
        #         decision="stop",
        #         reason=f"best_score={best_score} below threshold={promote_threshold}",
        #         total_hits=len(all_summaries),
        #         top_summaries=top_summaries
        #     )
        
        # 5. Promote promising papers
        # promoted_ids = [s.pmid for s in top_summaries if s.score >= promote_threshold]
        
        # logger.info(f"Promoting {len(promoted_ids)} papers for deep fetch")
        
        # return SearchResult(
        #     decision="promote",
        #     reason=f"best_score={best_score} above threshold={promote_threshold}",
        #     total_hits=len(all_summaries),
        #     top_summaries=top_summaries,
        #     promoted_ids=promoted_ids
        # )
        
        # 4. Simple approach: return all papers (no filtering)
        if not top_summaries:
            return SearchResult(
                decision="no_results",
                reason="no hits found",
                total_hits=0,
                top_summaries=[],
                promoted_ids=[]
            )
        
        # 5. Return all papers with their scores
        all_pmid_ids = [s.pmid for s in top_summaries]
        
        logger.info(f"Returning {len(all_pmid_ids)} papers (no filtering applied)")
        
        return SearchResult(
            decision="all_papers",
            reason=f"Returning all {len(all_pmid_ids)} papers found",
            total_hits=len(all_summaries),
            top_summaries=top_summaries,
            promoted_ids=all_pmid_ids
        )


# Convenience function for quick testing
def quick_smart_search(
    drug_name: str, 
    disease: Optional[str] = None,
    nct_id: Optional[str] = None
) -> SearchResult:
    """
    Quick smart search for a single drug.
    
    Args:
        drug_name: Drug name (e.g., "ruxolitinib")
        disease: Optional disease (e.g., "myelofibrosis")
        nct_id: Optional NCT ID
        
    Returns:
        SearchResult with decision and data
    """
    client = SmartPubMedClient()
    return client.smart_search(
        drug_synonyms=[drug_name],
        disease=disease,
        nct_id=nct_id
    )
