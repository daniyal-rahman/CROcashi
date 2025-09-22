"""
XML Utilities

Shared utilities for parsing XML content from various sources.
"""

import re
import logging

logger = logging.getLogger(__name__)


def extract_abstract_from_pubmed_xml(xml_text: str) -> str:
    """
    Extract abstract text from PubMed XML.
    
    Args:
        xml_text: Raw XML text from PubMed
        
    Returns:
        Extracted abstract text or empty string if not found
    """
    try:
        # Simple XML parsing - look for AbstractText tags
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


def extract_fulltext_from_pmc_xml(xml_text: str) -> str:
    """
    Extract full text from PMC XML.
    
    Args:
        xml_text: Raw XML text from PMC
        
    Returns:
        Extracted full text or empty string if not found
    """
    try:
        # Simple XML parsing - look for article body
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
