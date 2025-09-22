"""
Extract Utilities

Shared utilities for the extract module to avoid code duplication.
"""

from .document_utils import resolve_external_doc_id, get_document_metadata, get_document_text, get_standardized_doc_id
from .xml_utils import extract_abstract_from_pubmed_xml, extract_fulltext_from_pmc_xml

__all__ = [
    "resolve_external_doc_id",
    "get_document_metadata",
    "get_document_text",
    "get_standardized_doc_id",
    "extract_abstract_from_pubmed_xml",
    "extract_fulltext_from_pmc_xml"
]
