#!/usr/bin/env python3
"""
PMC Client Manager - Fixed version with proper session management.

Fixes the "Client session not initialized" issue by managing HTTP sessions properly.
"""

import asyncio
import logging
import aiohttp
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PMCClientConfig:
    """Configuration for PMC client."""
    base_url: str = "https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi"
    user_agent: str = "NCFD-Research-Tool/1.0"
    contact_email: str = "ncfd-ingest@example.com"
    http_timeout_s: int = 30
    rate_limit_per_sec: float = 1.0
    max_retries: int = 3
    backoff_factor: float = 2.0


class PMCClientManager:
    """Manages PMC client instances with proper session lifecycle."""
    
    _session: Optional[aiohttp.ClientSession] = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_client(cls, config: PMCClientConfig) -> 'PMCClient':
        """Get PMC client with proper session management."""
        async with cls._lock:
            if cls._session is None or cls._session.closed:
                headers = {
                    "User-Agent": config.user_agent,
                    "From": config.contact_email,
                }
                timeout = aiohttp.ClientTimeout(total=config.http_timeout_s)
                cls._session = aiohttp.ClientSession(
                    headers=headers, 
                    timeout=timeout
                )
                logger.info(f"Created PMC client session with User-Agent: {config.user_agent}")
        
        return PMCClient(session=cls._session, config=config)
    
    @classmethod
    async def close_session(cls):
        """Close the shared session."""
        if cls._session and not cls._session.closed:
            await cls._session.close()
            logger.info("Closed PMC client session")


class PMCClient:
    """PMC client with proper session handling."""
    
    def __init__(self, session: aiohttp.ClientSession, config: PMCClientConfig):
        """Initialize PMC client."""
        self.session = session
        self.config = config
        self.base_url = config.base_url
    
    async def get_pmc_full_text(self, pmcid: str) -> Optional[str]:
        """
        Retrieve full text from PMC.
        
        Args:
            pmcid: PMC ID (e.g., "PMC10531384")
            
        Returns:
            Full text content or None
        """
        try:
            logger.info(f"Fetching PMC full text for {pmcid}")
            
            # Try JATS first (more comprehensive)
            full_text = await self.get_pmc_full_text_jats(pmcid)
            if full_text:
                return full_text
            
            # Fallback to plain text
            logger.warning(f"JATS failed for {pmcid}, trying plain text")
            return await self._get_pmc_plain_text(pmcid)
            
        except Exception as e:
            logger.error(f"Error retrieving PMC full text for {pmcid}: {e}")
            return None
    
    async def get_pmc_full_text_jats(self, pmcid: str, include_refs: bool = True, include_captions: bool = True) -> Optional[str]:
        """
        Retrieve full text from PMC using JATS XML format.
        
        Args:
            pmcid: PMC ID
            include_refs: Include references
            include_captions: Include captions
            
        Returns:
            Full text content or None
        """
        try:
            # Extract numeric ID from PMCID
            numeric_id = pmcid.replace("PMC", "")
            
            params = {
                "verb": "GetRecord",
                "identifier": f"oai:pubmedcentral.nih.gov:{pmcid}",
                "metadataPrefix": "pmc"
            }
            
            # Add rate limiting
            await asyncio.sleep(1.0 / self.config.rate_limit_per_sec)
            
            async with self.session.get(self.base_url, params=params) as response:
                if response.status == 403:
                    error_text = await response.text()
                    if "robot" in error_text.lower():
                        logger.warning(f"PMC OAI returned 403 (robot detection) for {pmcid}")
                        # Backoff with jitter
                        await asyncio.sleep(2.0)
                        return None
                    else:
                        logger.warning(f"PMC OAI returned 403 for {pmcid}: {error_text}")
                        return None
                
                if response.status != 200:
                    logger.warning(f"PMC OAI returned {response.status} for {pmcid}")
                    return None
                
                content = await response.text()
                
                if not content or len(content) < 100:
                    logger.warning(f"PMC OAI returned minimal content for {pmcid}")
                    return None
                
                # Parse JATS XML (simplified)
                full_text = self._parse_jats_xml(content, include_refs, include_captions)
                
                if full_text:
                    logger.info(f"Successfully retrieved {len(full_text)} chars from PMC JATS for {pmcid}")
                    return full_text
                else:
                    logger.warning(f"Failed to parse JATS XML for {pmcid}")
                    return None
                
        except Exception as e:
            logger.error(f"Error retrieving PMC JATS for {pmcid}: {e}")
            return None
    
    async def _get_pmc_plain_text(self, pmcid: str) -> Optional[str]:
        """Retrieve plain text from PMC."""
        try:
            # Try direct PMC URL
            pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
            
            async with self.session.get(pmc_url) as response:
                if response.status != 200:
                    logger.warning(f"PMC direct URL returned {response.status} for {pmcid}")
                    return None
                
                content = await response.text()
                
                # Extract text content (simplified)
                full_text = self._extract_text_from_html(content)
                
                if full_text:
                    logger.info(f"Successfully retrieved {len(full_text)} chars from PMC plain text for {pmcid}")
                    return full_text
                else:
                    logger.warning(f"Failed to extract text from PMC HTML for {pmcid}")
                    return None
                
        except Exception as e:
            logger.error(f"Error retrieving PMC plain text for {pmcid}: {e}")
            return None
    
    def _parse_jats_xml(self, xml_content: str, include_refs: bool, include_captions: bool) -> Optional[str]:
        """Parse JATS XML content."""
        try:
            # Simplified JATS parsing - extract text content
            import re
            
            # Remove XML tags and extract text
            text_content = re.sub(r'<[^>]+>', ' ', xml_content)
            
            # Clean up whitespace
            text_content = re.sub(r'\s+', ' ', text_content).strip()
            
            # Basic validation - should have substantial content
            if len(text_content) < 200:
                return None
            
            return text_content
            
        except Exception as e:
            logger.error(f"Error parsing JATS XML: {e}")
            return None
    
    def _extract_text_from_html(self, html_content: str) -> Optional[str]:
        """Extract text content from HTML."""
        try:
            # Simplified HTML text extraction
            import re
            
            # Remove HTML tags
            text_content = re.sub(r'<[^>]+>', ' ', html_content)
            
            # Clean up whitespace
            text_content = re.sub(r'\s+', ' ', text_content).strip()
            
            # Basic validation
            if len(text_content) < 200:
                return None
            
            return text_content
            
        except Exception as e:
            logger.error(f"Error extracting text from HTML: {e}")
            return None


# Global manager instance
_global_manager: Optional[PMCClientManager] = None


def get_pmc_client_manager() -> PMCClientManager:
    """Get global PMC client manager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = PMCClientManager()
    return _global_manager


async def get_pmc_client(config: PMCClientConfig) -> PMCClient:
    """Convenience function to get PMC client."""
    manager = get_pmc_client_manager()
    return await manager.get_client(config)


async def close_pmc_session():
    """Convenience function to close PMC session."""
    manager = get_pmc_client_manager()
    await manager.close_session()
