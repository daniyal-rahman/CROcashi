"""
CT.gov to PubMed Full Text Retrieval Service

This service retrieves full text for CT.gov trials by:
1. Searching PubMed for publications related to the NCT ID
2. Retrieving full text from PMC or Unpaywall
3. Combining trial metadata with publication content
"""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from ncfd.ingest.pubmed.client import PubMedClient
from ncfd.ingest.pubmed.client_manager import get_client_manager
from ncfd.ingest.pubmed.oa_worker import OAWorker
from ncfd.db.session import session_scope
from ncfd.db.models import Document, DocumentText

logger = logging.getLogger(__name__)


@dataclass
class CTgovPublicationMatch:
    """Represents a publication found for a CT.gov trial."""
    pmid: str
    pmcid: Optional[str]
    title: str
    authors: List[str]
    journal: str
    publication_date: Optional[datetime]
    abstract: str
    full_text: Optional[str]
    match_confidence: float
    match_reasons: List[str]


@dataclass
class CTgovRetrievalResult:
    """Result of CT.gov to PubMed retrieval."""
    nct_id: str
    trial_title: str
    publications_found: int
    publications_with_full_text: int
    combined_content: str
    publication_matches: List[CTgovPublicationMatch]
    retrieval_success: bool
    error_message: Optional[str]


class CTgovPubMedRetrievalService:
    """
    Service for retrieving full text for CT.gov trials from PubMed.
    
    This service:
    1. Searches PubMed for publications mentioning the NCT ID
    2. Retrieves full text from PMC/Unpaywall
    3. Combines trial metadata with publication content
    4. Returns structured content for LLM processing
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the CT.gov to PubMed retrieval service.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.retrieval_config = config.get('ctgov_pubmed_retrieval', {})
        
        # Configuration values
        self.max_publications_per_trial = self.retrieval_config.get('max_publications_per_trial', 5)
        self.min_match_confidence = self.retrieval_config.get('min_match_confidence', 0.3)
        self.enable_pmc_retrieval = self.retrieval_config.get('enable_pmc_retrieval', True)
        self.enable_unpaywall_retrieval = self.retrieval_config.get('enable_unpaywall_retrieval', True)
        
        # Initialize PubMed client manager
        self.client_manager = get_client_manager()
        
        # Initialize OA worker for full text retrieval
        # Note: OAWorker requires TaskQueueService, but we'll use direct client calls instead
        # self.oa_worker = OAWorker(config)  # Commented out - will use direct client calls
    
    async def retrieve_full_text_for_trial(
        self, 
        trial: Dict[str, Any]
    ) -> CTgovRetrievalResult:
        """
        Retrieve full text for a CT.gov trial from PubMed.
        
        Args:
            trial: Trial information including NCT ID
            
        Returns:
            CTgovRetrievalResult with combined content
        """
        nct_id = trial.get('nct_id')
        trial_title = trial.get('title', 'Unknown Trial')
        
        if not nct_id:
            return CTgovRetrievalResult(
                nct_id='',
                trial_title=trial_title,
                publications_found=0,
                publications_with_full_text=0,
                combined_content=self._get_fallback_content(trial),
                publication_matches=[],
                retrieval_success=False,
                error_message="No NCT ID provided"
            )
        
        logger.info(f"🔍 Retrieving full text for CT.gov trial: {nct_id}")
        
        try:
            # Step 1: Search PubMed for publications related to this NCT ID
            publication_matches = await self._search_pubmed_for_nct(nct_id, trial_title)
            
            if not publication_matches:
                logger.warning(f"No publications found for NCT ID: {nct_id}")
                return CTgovRetrievalResult(
                    nct_id=nct_id,
                    trial_title=trial_title,
                    publications_found=0,
                    publications_with_full_text=0,
                    combined_content=self._get_fallback_content(trial),
                    publication_matches=[],
                    retrieval_success=False,
                    error_message="No publications found for NCT ID"
                )
            
            # Step 2: Retrieve full text for publications
            publications_with_full_text = await self._retrieve_publication_full_text(publication_matches)
            
            # Step 3: Combine trial metadata with publication content
            combined_content = self._combine_trial_and_publication_content(
                trial, publications_with_full_text
            )
            
            logger.info(f"✅ Retrieved full text for NCT {nct_id}: {len(publications_with_full_text)} publications with full text")
            
            return CTgovRetrievalResult(
                nct_id=nct_id,
                trial_title=trial_title,
                publications_found=len(publication_matches),
                publications_with_full_text=len(publications_with_full_text),
                combined_content=combined_content,
                publication_matches=publications_with_full_text,
                retrieval_success=True,
                error_message=None
            )
            
        except Exception as e:
            logger.error(f"Error retrieving full text for CT.gov trial {nct_id}: {e}")
            return CTgovRetrievalResult(
                nct_id=nct_id,
                trial_title=trial_title,
                publications_found=0,
                publications_with_full_text=0,
                combined_content=self._get_fallback_content(trial),
                publication_matches=[],
                retrieval_success=False,
                error_message=str(e)
            )
    
    async def _search_pubmed_for_nct(
        self, 
        nct_id: str, 
        trial_title: str
    ) -> List[CTgovPublicationMatch]:
        """
        Search PubMed for publications related to an NCT ID.
        
        Args:
            nct_id: NCT ID to search for
            trial_title: Trial title for additional context
            
        Returns:
            List of publication matches
        """
        try:
            # Get PubMed client
            client = await self.client_manager.get_client(self.config)
            
            async with client:
                # Build search queries for NCT ID
                queries = self._build_nct_search_queries(nct_id, trial_title)
                
                all_pmids = []
                for query in queries:
                    try:
                        logger.info(f"Searching PubMed with query: {query}")
                        search_result = await client.esearch(
                            query=query,
                            max_results=self.max_publications_per_trial * 2,  # Get more to filter
                            sort="relevance"
                        )
                        
                        pmids = search_result.get('idlist', [])
                        all_pmids.extend(pmids)
                        logger.info(f"Found {len(pmids)} PMIDs for query: {query}")
                        
                    except Exception as e:
                        logger.error(f"Error searching PubMed with query '{query}': {e}")
                        continue
                
                # Remove duplicates
                unique_pmids = list(set(all_pmids))
                logger.info(f"Total unique PMIDs found: {len(unique_pmids)}")
                
                if not unique_pmids:
                    return []
                
                # Get publication details
                publication_matches = await self._get_publication_details(client, unique_pmids, nct_id)
                
                # Filter and score matches
                scored_matches = self._score_publication_matches(publication_matches, nct_id, trial_title)
                
                # Sort by confidence and return top matches
                scored_matches.sort(key=lambda x: x.match_confidence, reverse=True)
                return scored_matches[:self.max_publications_per_trial]
                
        except Exception as e:
            logger.error(f"Error searching PubMed for NCT {nct_id}: {e}")
            return []
    
    def _build_nct_search_queries(self, nct_id: str, trial_title: str) -> List[str]:
        """
        Build PubMed search queries for an NCT ID.
        
        Args:
            nct_id: NCT ID to search for
            trial_title: Trial title for additional context
            
        Returns:
            List of search queries
        """
        queries = []
        
        # Primary query: NCT ID in secondary identifier field
        queries.append(f"{nct_id}[si]")
        
        # Secondary query: NCT ID anywhere in text
        queries.append(f"{nct_id}[tw]")
        
        # Tertiary query: NCT ID with trial title keywords
        if trial_title:
            # Extract key terms from trial title (remove common words)
            title_words = self._extract_key_terms(trial_title)
            if title_words:
                title_query = " AND ".join(title_words[:3])  # Use top 3 terms
                queries.append(f"{nct_id}[tw] AND {title_query}[tw]")
        
        return queries
    
    def _extract_key_terms(self, text: str) -> List[str]:
        """
        Extract key terms from text, removing common words.
        
        Args:
            text: Text to extract terms from
            
        Returns:
            List of key terms
        """
        # Common words to exclude
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
            'study', 'trial', 'clinical', 'phase', 'randomized', 'double', 'blind', 'placebo',
            'controlled', 'multicenter', 'safety', 'efficacy', 'dose', 'escalation'
        }
        
        # Extract words (alphanumeric, at least 3 characters)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        
        # Filter out stop words and return unique terms
        key_terms = [word for word in words if word not in stop_words]
        return list(set(key_terms))
    
    async def _get_publication_details(
        self, 
        client: PubMedClient, 
        pmids: List[str], 
        nct_id: str
    ) -> List[CTgovPublicationMatch]:
        """
        Get detailed information for publications.
        
        Args:
            client: PubMed client
            pmids: List of PMIDs
            nct_id: NCT ID for context
            
        Returns:
            List of publication matches
        """
        try:
            # Get publication summaries
            summaries = await client.esummary_batch(pmids)
            
            publication_matches = []
            for pmid, summary in summaries.items():
                try:
                    # Extract publication details
                    title = summary.get('title', 'Unknown Title')
                    authors = summary.get('authors', [])
                    journal = summary.get('source', 'Unknown Journal')
                    pub_date = summary.get('pubdate', '')
                    abstract = summary.get('abstract', '')
                    
                    # Get PMCID if available
                    pmcid = summary.get('pmcid')
                    
                    publication_match = CTgovPublicationMatch(
                        pmid=pmid,
                        pmcid=pmcid,
                        title=title,
                        authors=authors,
                        journal=journal,
                        publication_date=self._parse_publication_date(pub_date),
                        abstract=abstract,
                        full_text=None,  # Will be retrieved later
                        match_confidence=0.0,  # Will be scored later
                        match_reasons=[]
                    )
                    
                    publication_matches.append(publication_match)
                    
                except Exception as e:
                    logger.error(f"Error processing publication {pmid}: {e}")
                    continue
            
            return publication_matches
            
        except Exception as e:
            logger.error(f"Error getting publication details: {e}")
            return []
    
    def _parse_publication_date(self, pub_date: str) -> Optional[datetime]:
        """
        Parse publication date string.
        
        Args:
            pub_date: Publication date string
            
        Returns:
            Parsed datetime or None
        """
        try:
            # Try common date formats
            formats = [
                '%Y %b %d',
                '%Y %b',
                '%Y',
                '%Y-%m-%d',
                '%Y-%m'
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(pub_date, fmt)
                except ValueError:
                    continue
            
            return None
            
        except Exception:
            return None
    
    def _score_publication_matches(
        self, 
        publications: List[CTgovPublicationMatch], 
        nct_id: str, 
        trial_title: str
    ) -> List[CTgovPublicationMatch]:
        """
        Score publication matches based on relevance to the NCT ID.
        
        Args:
            publications: List of publications to score
            nct_id: NCT ID for scoring
            trial_title: Trial title for scoring
            
        Returns:
            List of scored publications
        """
        for pub in publications:
            confidence = 0.0
            reasons = []
            
            # Check for NCT ID in abstract
            if nct_id.lower() in pub.abstract.lower():
                confidence += 0.4
                reasons.append(f"NCT ID found in abstract")
            
            # Check for NCT ID in title
            if nct_id.lower() in pub.title.lower():
                confidence += 0.3
                reasons.append(f"NCT ID found in title")
            
            # Check for trial title keywords in abstract
            if trial_title:
                title_words = self._extract_key_terms(trial_title)
                matches = sum(1 for word in title_words if word in pub.abstract.lower())
                if matches > 0:
                    confidence += min(0.2, matches * 0.05)
                    reasons.append(f"{matches} trial title keywords found in abstract")
            
            # Check for PMCID (indicates open access)
            if pub.pmcid:
                confidence += 0.1
                reasons.append("Open access publication (PMCID available)")
            
            pub.match_confidence = confidence
            pub.match_reasons = reasons
        
        return publications
    
    async def _retrieve_publication_full_text(
        self, 
        publications: List[CTgovPublicationMatch]
    ) -> List[CTgovPublicationMatch]:
        """
        Retrieve full text for publications.
        
        Args:
            publications: List of publications to retrieve full text for
            
        Returns:
            List of publications with full text
        """
        publications_with_full_text = []
        
        for pub in publications:
            try:
                # Try PMC retrieval first
                if self.enable_pmc_retrieval and pub.pmcid:
                    full_text = await self._retrieve_pmc_full_text(pub.pmcid)
                    if full_text:
                        pub.full_text = full_text
                        publications_with_full_text.append(pub)
                        logger.info(f"Retrieved PMC full text for PMID {pub.pmid}")
                        continue
                
                # Try Unpaywall retrieval
                if self.enable_unpaywall_retrieval:
                    full_text = await self._retrieve_unpaywall_full_text(pub.pmid)
                    if full_text:
                        pub.full_text = full_text
                        publications_with_full_text.append(pub)
                        logger.info(f"Retrieved Unpaywall full text for PMID {pub.pmid}")
                        continue
                
                # If no full text available, use abstract
                if pub.abstract:
                    pub.full_text = pub.abstract
                    publications_with_full_text.append(pub)
                    logger.info(f"Using abstract as full text for PMID {pub.pmid}")
                
            except Exception as e:
                logger.error(f"Error retrieving full text for PMID {pub.pmid}: {e}")
                continue
        
        return publications_with_full_text
    
    async def _retrieve_pmc_full_text(self, pmcid: str) -> Optional[str]:
        """
        Retrieve full text from PMC.
        
        Args:
            pmcid: PMC ID
            
        Returns:
            Full text content or None
        """
        try:
            # Get PubMed client and retrieve PMC full text directly
            client = await self.client_manager.get_client(self.config)
            
            async with client:
                full_text = await client.get_pmc_full_text(pmcid)
                if full_text:
                    logger.info(f"Retrieved PMC full text for {pmcid}: {len(full_text)} characters")
                    return full_text
                else:
                    logger.warning(f"No PMC full text available for {pmcid}")
                    return None
            
        except Exception as e:
            logger.error(f"Error retrieving PMC full text for {pmcid}: {e}")
            return None
    
    async def _retrieve_unpaywall_full_text(self, pmid: str) -> Optional[str]:
        """
        Retrieve full text via Unpaywall.
        
        Args:
            pmid: PMID
            
        Returns:
            Full text content or None
        """
        try:
            # For now, return None - Unpaywall integration would require additional setup
            # In a full implementation, this would use the Unpaywall API
            logger.info(f"Unpaywall retrieval not implemented for PMID {pmid}")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving Unpaywall full text for PMID {pmid}: {e}")
            return None
    
    def _combine_trial_and_publication_content(
        self, 
        trial: Dict[str, Any], 
        publications: List[CTgovPublicationMatch]
    ) -> str:
        """
        Combine trial metadata with publication content.
        
        Args:
            trial: Trial information
            publications: List of publications with full text
            
        Returns:
            Combined content for LLM processing
        """
        # Start with trial metadata
        content_parts = [
            f"# Clinical Trial: {trial.get('title', 'Unknown Trial')}",
            f"**NCT ID:** {trial.get('nct_id', 'Unknown')}",
            f"**Phase:** {trial.get('phase', 'Unknown')}",
            f"**Indication:** {trial.get('indication', 'Unknown')}",
            f"**Sponsor:** {trial.get('sponsor_text', 'Unknown')}",
            "",
            "## Trial Information",
            f"This clinical trial investigates the efficacy and safety of the intervention in the specified indication.",
            ""
        ]
        
        # Add publication content
        if publications:
            content_parts.append("## Related Publications")
            content_parts.append("")
            
            for i, pub in enumerate(publications, 1):
                content_parts.extend([
                    f"### Publication {i}: {pub.title}",
                    f"**PMID:** {pub.pmid}",
                    f"**Journal:** {pub.journal}",
                    f"**Authors:** {', '.join(pub.authors[:5])}{'...' if len(pub.authors) > 5 else ''}",
                    f"**Match Confidence:** {pub.match_confidence:.2f}",
                    f"**Match Reasons:** {', '.join(pub.match_reasons)}",
                    "",
                    "**Abstract:**",
                    pub.abstract,
                    "",
                    "**Full Text:**",
                    pub.full_text or pub.abstract,
                    "",
                    "---",
                    ""
                ])
        else:
            content_parts.extend([
                "## Related Publications",
                "No related publications found in PubMed for this NCT ID.",
                ""
            ])
        
        return "\n".join(content_parts)
    
    def _get_fallback_content(self, trial: Dict[str, Any]) -> str:
        """
        Generate fallback content when retrieval fails.
        
        Args:
            trial: Trial information
            
        Returns:
            Fallback content
        """
        return f"""
# Clinical Trial: {trial.get('title', 'Unknown Trial')}

**NCT ID:** {trial.get('nct_id', 'Unknown')}
**Phase:** {trial.get('phase', 'Unknown')}
**Indication:** {trial.get('indication', 'Unknown')}
**Sponsor:** {trial.get('sponsor_text', 'Unknown')}

## Trial Information
This clinical trial investigates the efficacy and safety of the intervention in the specified indication.

## Related Publications
No related publications were found in PubMed for this NCT ID. This may be because:
- The trial is very recent and publications are not yet available
- The trial has not yet been published in peer-reviewed journals
- The NCT ID is not referenced in the publication abstracts/titles

## Note
This content was generated from CT.gov trial metadata only. In a full implementation, this would include:
- Full trial protocol details from CT.gov API
- Related publications from PubMed
- Full text content from PMC/Unpaywall
- Additional trial information from clinical trial registries
"""
