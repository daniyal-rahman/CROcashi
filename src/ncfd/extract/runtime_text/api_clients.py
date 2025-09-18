"""
API Clients for Runtime Document Text Retrieval
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any
import aiohttp
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TextRetrievalOutput:
    """Result from text retrieval attempt."""
    success: bool
    text: str
    source: str
    length: int
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BaseTextClient:
    """Base class for text retrieval clients."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.rate_limit_per_minute = config.get("rate_limit_per_minute", 60)
        self.timeout_seconds = config.get("timeout_seconds", 30)
        self.max_retries = config.get("max_retries", 3)
        self.backoff_base = config.get("backoff_base", 2.0)
        
        # Rate limiting
        self.last_request_time = 0
        self.min_interval = 60.0 / self.rate_limit_per_minute
        
    async def _rate_limit(self):
        """Apply rate limiting."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    async def _make_request(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Make HTTP request with retry logic."""
        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)) as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status == 200:
                            return await response.text()
                        elif response.status == 429:  # Rate limited
                            wait_time = self.backoff_base ** attempt
                            logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt + 1}")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.warning(f"HTTP {response.status} for {url}")
                            return None
                            
            except Exception as e:
                logger.warning(f"Request attempt {attempt + 1} failed for {url}: {e}")
                if attempt < self.max_retries - 1:
                    wait_time = self.backoff_base ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed for {url}")
                    return None
        
        return None


class PubMedTextClient(BaseTextClient):
    """Client for fetching abstracts from PubMed."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    
    async def fetch_abstract(self, pmid: str) -> TextRetrievalOutput:
        """Fetch abstract for a PMID."""
        try:
            url = f"{self.base_url}?db=pubmed&id={pmid}&retmode=xml&rettype=abstract"
            
            text = await self._make_request(url)
            if not text:
                return TextRetrievalOutput(
                    success=False,
                    text="",
                    source="pubmed",
                    length=0,
                    error_message="Failed to fetch from PubMed"
                )
            
            # Parse XML to extract abstract
            abstract = self._extract_abstract_from_xml(text)
            
            if abstract and len(abstract.strip()) >= 100:
                return TextRetrievalOutput(
                    success=True,
                    text=abstract,
                    source="pubmed",
                    length=len(abstract),
                    metadata={"pmid": pmid, "type": "abstract"}
                )
            else:
                return TextRetrievalOutput(
                    success=False,
                    text="",
                    source="pubmed",
                    length=0,
                    error_message="No valid abstract found"
                )
                
        except Exception as e:
            logger.error(f"Error fetching abstract for PMID {pmid}: {e}")
            return TextRetrievalOutput(
                success=False,
                text="",
                source="pubmed",
                length=0,
                error_message=str(e)
            )
    
    def _extract_abstract_from_xml(self, xml_text: str) -> str:
        """Extract abstract text from PubMed XML."""
        try:
            # Simple XML parsing - look for AbstractText tags
            import re
            abstract_match = re.search(r'<AbstractText[^>]*>(.*?)</AbstractText>', xml_text, re.DOTALL)
            if abstract_match:
                abstract = abstract_match.group(1)
                # Clean up HTML entities and tags
                abstract = re.sub(r'<[^>]+>', '', abstract)
                abstract = abstract.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
                return abstract.strip()
            return ""
        except Exception as e:
            logger.warning(f"Error parsing PubMed XML: {e}")
            return ""


class PMCTextClient(BaseTextClient):
    """Client for fetching full text from PMC."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = "https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi"
    
    async def fetch_fulltext(self, pmcid: str) -> TextRetrievalOutput:
        """Fetch full text for a PMCID."""
        try:
            # PMC OAI endpoint
            url = f"{self.base_url}?verb=GetRecord&identifier=oai:pubmedcentral.nih.gov:{pmcid}&metadataPrefix=pmc"
            
            text = await self._make_request(url)
            if not text:
                return TextRetrievalOutput(
                    success=False,
                    text="",
                    source="pmc",
                    length=0,
                    error_message="Failed to fetch from PMC"
                )
            
            # Parse XML to extract full text
            fulltext = self._extract_fulltext_from_xml(text)
            
            if fulltext and len(fulltext.strip()) >= 500:
                return TextRetrievalOutput(
                    success=True,
                    text=fulltext,
                    source="pmc",
                    length=len(fulltext),
                    metadata={"pmcid": pmcid, "type": "fulltext"}
                )
            else:
                return TextRetrievalOutput(
                    success=False,
                    text="",
                    source="pmc",
                    length=0,
                    error_message="No valid full text found"
                )
                
        except Exception as e:
            logger.error(f"Error fetching full text for PMCID {pmcid}: {e}")
            return TextRetrievalOutput(
                success=False,
                text="",
                source="pmc",
                length=0,
                error_message=str(e)
            )
    
    def _extract_fulltext_from_xml(self, xml_text: str) -> str:
        """Extract full text from PMC XML."""
        try:
            # Simple XML parsing - look for article body
            import re
            
            # Extract main text content
            body_match = re.search(r'<body[^>]*>(.*?)</body>', xml_text, re.DOTALL)
            if body_match:
                body_text = body_match.group(1)
                # Clean up XML tags but preserve structure
                body_text = re.sub(r'<[^>]+>', ' ', body_text)
                body_text = re.sub(r'\s+', ' ', body_text)
                return body_text.strip()
            
            return ""
        except Exception as e:
            logger.warning(f"Error parsing PMC XML: {e}")
            return ""


class UnpaywallTextClient(BaseTextClient):
    """Client for fetching full text from Unpaywall."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = "https://api.unpaywall.org/v2"
    
    async def fetch_fulltext(self, doi: str) -> TextRetrievalOutput:
        """Fetch full text for a DOI via Unpaywall."""
        try:
            url = f"{self.base_url}/{doi}?email=ncfd@example.com"
            
            text = await self._make_request(url)
            if not text:
                return TextRetrievalOutput(
                    success=False,
                    text="",
                    source="unpaywall",
                    length=0,
                    error_message="Failed to fetch from Unpaywall"
                )
            
            # Parse JSON response
            import json
            data = json.loads(text)
            
            if data.get("is_oa") and data.get("best_oa_location"):
                pdf_url = data["best_oa_location"].get("url_for_pdf")
                if pdf_url:
                    # For now, return metadata - full PDF parsing would require additional libraries
                    return TextRetrievalOutput(
                        success=True,
                        text=f"Open access PDF available at: {pdf_url}",
                        source="unpaywall",
                        length=len(pdf_url),
                        metadata={"doi": doi, "type": "pdf_url", "pdf_url": pdf_url}
                    )
            
            return TextRetrievalOutput(
                success=False,
                text="",
                source="unpaywall",
                length=0,
                error_message="No open access version found"
            )
                
        except Exception as e:
            logger.error(f"Error fetching full text for DOI {doi}: {e}")
            return TextRetrievalOutput(
                success=False,
                text="",
                source="unpaywall",
                length=0,
                error_message=str(e)
            )
