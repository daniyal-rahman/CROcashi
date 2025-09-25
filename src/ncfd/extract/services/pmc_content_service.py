"""
PMC Content Retrieval Service

Retrieves real content from PMC for testing purposes.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from ...ingest.pubmed.client_manager import get_client_manager

logger = logging.getLogger(__name__)


@dataclass
class PMCContent:
    """PMC content result."""
    pmcid: str
    title: str
    abstract: str
    full_text: str
    success: bool
    error: Optional[str] = None


class PMCContentService:
    """Service for retrieving real PMC content."""
    
    def __init__(self):
        self.client_manager = get_client_manager()
    
    async def get_pmc_content(self, pmcid: str, title: str) -> PMCContent:
        """
        Retrieve real content from PMC.
        
        Args:
            pmcid: PMC ID (e.g., "PMC10531384")
            title: Paper title for fallback
            
        Returns:
            PMCContent with real abstract and full text
        """
        try:
            logger.info(f"🔍 Retrieving real PMC content for {pmcid}")
            
            # Get PubMed client
            client = await self.client_manager.get_client()
            
            # Try JATS first (more comprehensive)
            full_text = await client.get_pmc_full_text_jats(
                pmcid, 
                include_refs=True, 
                include_captions=True
            )
            
            # Fallback to plain text if JATS fails
            if not full_text:
                logger.warning(f"JATS failed for {pmcid}, trying plain text")
                full_text = await client.get_pmc_full_text(pmcid)
            
            if not full_text:
                logger.error(f"Failed to retrieve content for {pmcid}")
                return PMCContent(
                    pmcid=pmcid,
                    title=title,
                    abstract="",
                    full_text="",
                    success=False,
                    error="No content retrieved from PMC"
                )
            
            # Extract abstract from full text (simple heuristic)
            abstract = self._extract_abstract(full_text)
            
            logger.info(f"✅ Successfully retrieved {len(full_text)} chars for {pmcid}")
            
            return PMCContent(
                pmcid=pmcid,
                title=title,
                abstract=abstract,
                full_text=full_text,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Error retrieving PMC content for {pmcid}: {e}")
            return PMCContent(
                pmcid=pmcid,
                title=title,
                abstract="",
                full_text="",
                success=False,
                error=str(e)
            )
    
    def _extract_abstract(self, full_text: str) -> str:
        """
        Extract abstract from full text using simple heuristics.
        
        Args:
            full_text: Full text content
            
        Returns:
            Extracted abstract
        """
        # Look for common abstract patterns
        abstract_patterns = [
            "Abstract:",
            "ABSTRACT:",
            "Abstract\n",
            "ABSTRACT\n",
            "## Abstract",
            "# Abstract"
        ]
        
        for pattern in abstract_patterns:
            if pattern in full_text:
                # Find the start of abstract
                start_idx = full_text.find(pattern) + len(pattern)
                
                # Look for end patterns
                end_patterns = ["Introduction:", "INTRODUCTION:", "Keywords:", "KEYWORDS:", "## ", "# "]
                end_idx = len(full_text)
                
                for end_pattern in end_patterns:
                    end_pos = full_text.find(end_pattern, start_idx)
                    if end_pos != -1 and end_pos < end_idx:
                        end_idx = end_pos
                
                abstract = full_text[start_idx:end_idx].strip()
                if len(abstract) > 100:  # Reasonable abstract length
                    return abstract
        
        # Fallback: use first 500 characters
        return full_text[:500].strip()


# Global instance
_pmc_service: Optional[PMCContentService] = None


def get_pmc_service() -> PMCContentService:
    """Get global PMC content service instance."""
    global _pmc_service
    if _pmc_service is None:
        _pmc_service = PMCContentService()
    return _pmc_service
