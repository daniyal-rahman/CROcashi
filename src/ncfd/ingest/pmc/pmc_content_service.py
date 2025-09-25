#!/usr/bin/env python3
"""
Fixed PMC Content Service

Uses the new PMC client manager with proper session management.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from .client_manager import PMCClientManager, PMCClientConfig, PMCClient
from ncfd.extract.validation.content_validator import ContentValidator, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class PMCContent:
    """PMC content result."""
    pmcid: str
    title: str
    abstract: str
    full_text: str
    success: bool = False
    error: Optional[str] = None
    validation_result: Optional[ValidationResult] = None


class PMCContentService:
    """Fixed service for retrieving real PMC content."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize PMC content service."""
        self.config = config or {}
        
        # Create PMC client config
        self.pmc_config = PMCClientConfig(
            user_agent=self.config.get('user_agent', 'NCFD-Research-Tool/1.0'),
            contact_email=self.config.get('contact_email', 'ncfd-ingest@example.com'),
            http_timeout_s=self.config.get('http_timeout_s', 30),
            rate_limit_per_sec=self.config.get('rate_limit_per_sec', 1.0)
        )
        
        # Initialize content validator
        self.validator = ContentValidator(self.config.get('validation', {}))
        
        self.client: Optional[PMCClient] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        manager = PMCClientManager()
        self.client = await manager.get_client(self.pmc_config)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        # Keep shared session alive; do not close here
        return False
    
    async def get_pmc_content(self, pmcid: str, title: str) -> PMCContent:
        """
        Retrieve real content from PMC with validation.
        
        Args:
            pmcid: PMC ID (e.g., "PMC10531384")
            title: Paper title for fallback
            
        Returns:
            PMCContent with real abstract and full text
        """
        if not self.client:
            return PMCContent(
                pmcid=pmcid,
                title=title,
                abstract="",
                full_text="",
                success=False,
                error="PMC client not initialized - use async context manager"
            )
        
        try:
            logger.info(f"🔍 Retrieving real PMC content for {pmcid}")
            
            # Retrieve full text
            full_text = await self.client.get_pmc_full_text(pmcid)
            
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
            
            # Extract abstract from full text
            abstract = self._extract_abstract(full_text)
            
            # Validate content
            validation_result = self.validator.validate_content(full_text, title, pmcid)
            
            if not validation_result.is_valid:
                logger.warning(f"Content validation failed for {pmcid}: {validation_result.reasons}")
                if validation_result.warnings:
                    for warning in validation_result.warnings:
                        logger.warning(f"Validation warning for {pmcid}: {warning}")
            
            logger.info(f"✅ Successfully retrieved {len(full_text)} chars for {pmcid}")
            logger.info(f"📊 Validation: valid={validation_result.is_valid}, confidence={validation_result.confidence:.2f}")
            
            return PMCContent(
                pmcid=pmcid,
                title=title,
                abstract=abstract,
                full_text=full_text,
                success=True,
                validation_result=validation_result
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


def get_pmc_service(config: Optional[Dict[str, Any]] = None) -> PMCContentService:
    """Get global PMC content service instance."""
    global _pmc_service
    if _pmc_service is None:
        _pmc_service = PMCContentService(config)
    return _pmc_service
