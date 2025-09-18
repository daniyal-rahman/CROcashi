"""
Runtime Document Text Generator

Generates document text at runtime from external APIs with intelligent fallback.
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from .api_clients import PubMedTextClient, PMCTextClient, UnpaywallTextClient, TextRetrievalOutput
from .config import RUNTIME_TEXT_CONFIG
from ...db.models import Document, DocumentText
from ...db.session import get_session

logger = logging.getLogger(__name__)


class RuntimeTextGenerator:
    """Generates document text at runtime from external APIs."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or RUNTIME_TEXT_CONFIG
        self.api_config = self.config.get("apis", {})
        self.quality_config = self.config.get("quality", {})
        self.fallback_order = self.config.get("fallback_order", ["pmc", "pubmed", "unpaywall"])
        
        # Initialize API clients
        self.pubmed_client = PubMedTextClient(self.api_config.get("pubmed", {}))
        self.pmc_client = PMCTextClient(self.api_config.get("pmc", {}))
        self.unpaywall_client = UnpaywallTextClient(self.api_config.get("unpaywall", {}))
        
        logger.info("Runtime text generator initialized")
    
    async def generate_text(self, doc_id: str) -> str:
        """
        Generate text for a document using external APIs.
        
        Args:
            doc_id: Document ID to generate text for
            
        Returns:
            Generated text content or empty string if failed
        """
        try:
            # Get document metadata
            doc_metadata = await self._get_document_metadata(doc_id)
            if not doc_metadata:
                logger.warning(f"No metadata found for document {doc_id}")
                return ""
            
            # Try each source in fallback order
            for source in self.fallback_order:
                try:
                    result = await self._try_source(doc_metadata, source)
                    if result.success and self._is_text_quality_acceptable(result.text):
                        logger.info(f"Successfully generated {len(result.text)} chars from {source} for doc {doc_id}")
                        return result.text
                    else:
                        logger.debug(f"Source {source} failed or low quality for doc {doc_id}: {result.error_message}")
                except Exception as e:
                    logger.warning(f"Error with source {source} for doc {doc_id}: {e}")
                    continue
            
            logger.warning(f"All sources failed for document {doc_id}")
            return ""
            
        except Exception as e:
            logger.error(f"Error generating text for document {doc_id}: {e}")
            return ""
    
    async def _get_document_metadata(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document metadata from database."""
        try:
            with get_session() as session:
                # Resolve external doc_id to internal doc_id
                internal_doc_id = self._resolve_external_doc_id(session, doc_id)
                if not internal_doc_id:
                    return None
                
                document = session.query(Document).filter(
                    Document.doc_id == internal_doc_id
                ).first()
                
                if not document:
                    return None
                
                return {
                    "doc_id": internal_doc_id,
                    "pmid": document.pmid,
                    "pmcid": document.pmcid,
                    "doi": document.doi,
                    "title": document.title,
                    "source_type": document.source_type
                }
                
        except Exception as e:
            logger.error(f"Error getting metadata for doc {doc_id}: {e}")
            return None
    
    def _resolve_external_doc_id(self, session, doc_id: str) -> Optional[int]:
        """Resolve external doc_id format to internal doc_id."""
        try:
            if doc_id.startswith('db:'):
                return int(doc_id.split(':')[1])
            elif doc_id.startswith('pmid:'):
                pmid = doc_id.split(':')[1]
                doc = session.query(Document).filter(Document.pmid == pmid).first()
                return doc.doc_id if doc else None
            elif doc_id.startswith('pmcid:'):
                pmcid = doc_id.split(':')[1]
                doc = session.query(Document).filter(Document.pmcid == pmcid).first()
                return doc.doc_id if doc else None
            else:
                # Assume it's already an internal doc_id
                return int(doc_id)
        except (ValueError, AttributeError):
            return None
    
    async def _try_source(self, doc_metadata: Dict[str, Any], source: str) -> TextRetrievalOutput:
        """Try to get text from a specific source."""
        if source == "pubmed" and doc_metadata.get("pmid"):
            return await self.pubmed_client.fetch_abstract(doc_metadata["pmid"])
        elif source == "pmc" and doc_metadata.get("pmcid"):
            return await self.pmc_client.fetch_fulltext(doc_metadata["pmcid"])
        elif source == "unpaywall" and doc_metadata.get("doi"):
            return await self.unpaywall_client.fetch_fulltext(doc_metadata["doi"])
        else:
            return TextRetrievalOutput(
                success=False,
                text="",
                source=source,
                length=0,
                error_message=f"No identifier available for source {source}"
            )
    
    def _is_text_quality_acceptable(self, text: str) -> bool:
        """Check if text meets quality requirements."""
        if not text or not text.strip():
            return False
        
        min_length = self.quality_config.get("min_abstract_length", 100)
        return len(text.strip()) >= min_length
    
    async def generate_texts_batch(self, doc_ids: List[str]) -> Dict[str, str]:
        """
        Generate text for multiple documents concurrently.
        
        Args:
            doc_ids: List of document IDs
            
        Returns:
            Dictionary mapping doc_id to generated text
        """
        # Limit concurrent requests to avoid overwhelming APIs
        max_concurrent = 5
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def generate_with_semaphore(doc_id: str) -> tuple[str, str]:
            async with semaphore:
                text = await self.generate_text(doc_id)
                return doc_id, text
        
        # Run all generations concurrently
        tasks = [generate_with_semaphore(doc_id) for doc_id in doc_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        generated_texts = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Batch generation error: {result}")
                continue
            
            doc_id, text = result
            if text:
                generated_texts[doc_id] = text
        
        logger.info(f"Generated text for {len(generated_texts)}/{len(doc_ids)} documents")
        return generated_texts
