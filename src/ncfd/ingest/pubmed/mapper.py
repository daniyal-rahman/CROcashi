"""
PubMed API response mapper.

Maps PubMed E-utilities API responses to database staging tables with data validation and transformation.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class PubMedMapper:
    """Maps PubMed API responses to database staging tables."""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize PubMed mapper.
        
        Args:
            config: Configuration dictionary with mapping parameters
        """
        self.config = config or {}
        self.default_language = self.config.get('default_language', 'en')
        
    def map_esearch_result(self, esearch_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map ESearch result to document staging format.
        
        Args:
            esearch_result: Raw ESearch API response
            
        Returns:
            Mapped document data for staging
        """
        try:
            # Extract basic search metadata
            count = int(esearch_result.get('count', '0'))
            retmax = int(esearch_result.get('retmax', '0'))
            retstart = int(esearch_result.get('retstart', '0'))
            
            # Extract PMIDs
            id_list = esearch_result.get('idlist', [])
            if isinstance(id_list, str):
                id_list = [id_list]
            
            # Map to staging format
            mapped_data = {
                'search_metadata': {
                    'count': count,
                    'retmax': retmax,
                    'retstart': retstart,
                    'query_translation': esearch_result.get('querytranslation', ''),
                    'error_list': esearch_result.get('errorlist', {}),
                    'warning_list': esearch_result.get('warninglist', {})
                },
                'pmids': id_list,
                'total_results': count,
                'mapped_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"Mapped ESearch result: {count} PMIDs found")
            return mapped_data
            
        except Exception as e:
            logger.error(f"Failed to map ESearch result: {e}")
            raise
    
    def map_esummary_result(
        self, 
        esummary_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Map ESummary results to document staging format.
        
        Note: ESummary contains metadata only, NOT abstracts.
        Abstracts must be fetched separately via EFetch.
        
        Args:
            esummary_result: Raw ESummary API response
            
        Returns:
            List of mapped document data for staging
        """
        mapped_documents = []
        
        try:
            # Extract individual document summaries
            for pmid, doc_data in esummary_result.items():
                # Skip non-digit keys (like 'uids' metadata)
                if not pmid.isdigit():
                    continue
                    
                try:
                    mapped_doc = self._map_single_esummary(pmid, doc_data)
                    if mapped_doc:
                        mapped_documents.append(mapped_doc)
                except Exception as e:
                    logger.warning(f"Failed to map PMID {pmid}: {e}")
                    continue
            
            logger.info(f"Mapped {len(mapped_documents)} documents from ESummary")
            return mapped_documents
            
        except Exception as e:
            logger.error(f"Failed to map ESummary results: {e}")
            raise
    
    def _map_single_esummary(self, pmid: str, doc_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Map a single ESummary document to staging format."""
        try:
            # Extract basic document information
            title = doc_data.get('title', '')
            # ESummary does NOT contain abstracts - this will be empty
            # Abstracts come from EFetch (XML/MEDLINE)
            abstract = ""  # Will be populated by EFetch later
            
            authors = doc_data.get('authors', [])
            journal = doc_data.get('fulljournalname', '')
            pub_date = doc_data.get('pubdate', '')
            article_type = doc_data.get('pubtype', [])
            
            # Parse publication date
            parsed_date = self._parse_pub_date(pub_date)
            
            # Extract and normalize authors
            normalized_authors = self._normalize_authors(authors)
            
            # Extract affiliations
            affiliations = self._extract_affiliations(doc_data)
            
            # Extract DOI from articleids (correct location)
            doi = self._extract_doi_from_articleids(doc_data)
            
            # Map to staging format
            mapped_doc = {
                'doc_id': None,  # Will be assigned during insertion
                'source_type': 'PubMed',
                'source_url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                'url_hash': self._calculate_url_hash(f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"),
                'published_at': parsed_date,
                'discovered_at': datetime.utcnow(),
                'title': title,
                'doi': doi,
                'pmid': pmid,
                'pmcid': None,  # Will be populated by ELink
                'nct_id': None,  # Will be extracted from text
                'sponsor_text': None,  # Will be extracted from text
                'status': 'discovered',
                'content_type': 'abstract',  # Will be updated after EFetch
                'publisher': journal,
                'sha256': None  # Will be calculated from content
            }
            
            # Add PubMed-specific metadata
            pubmed_meta = {
                'doc_id': None,  # Will be linked after document insertion
                'pmid': pmid,
                'medline_xml_sha': None,  # Will be populated if available
                'language': doc_data.get('lang', [self.default_language])[0],
                'authors_jsonb': normalized_authors,
                'affiliations_jsonb': affiliations,
                'esummary_jsonb': doc_data
            }
            
            mapped_doc['pubmed_meta'] = pubmed_meta
            
            # Add citation information
            citation_data = {
                'doc_id': None,  # Will be linked after document insertion
                'doi': doi,
                'pmid': pmid,
                'pmcid': None,
                'nct_id': None,
                'journal': journal,
                'volume': doc_data.get('volume', ''),
                'issue': doc_data.get('issue', ''),
                'pages': doc_data.get('pages', ''),
                'article_type': ', '.join(article_type) if article_type else None,
                'pub_year': parsed_date.year if parsed_date else None,
                # MeSH and substances come from EFetch, not ESummary
                'mesh_jsonb': [],
                'substances_jsonb': []
            }
            
            mapped_doc['citation'] = citation_data
            
            # Add text content - abstract will be populated by EFetch
            text_data = {
                'doc_id': None,  # Will be linked after document insertion
                'abstract_text': abstract,  # Empty from ESummary
                'fulltext_text': None,  # Will be populated by PMC if available
                'fulltext_ttl_date': None,
                'char_count_abstract': 0,  # Will be updated by EFetch
                'char_count_fulltext': None
            }
            
            mapped_doc['text'] = text_data
            
            return mapped_doc
            
        except Exception as e:
            logger.error(f"Failed to map single ESummary for PMID {pmid}: {e}")
            return None
    
    def _extract_doi_from_articleids(self, doc_data: Dict[str, Any]) -> str:
        """Extract DOI from articleids field (correct location)."""
        try:
            articleids = doc_data.get('articleids', [])
            if isinstance(articleids, list):
                for article_id in articleids:
                    if isinstance(article_id, dict) and article_id.get('idtype') == 'doi':
                        return article_id.get('value', '')
            
            # Fallback to elocationid (less reliable)
            return doc_data.get('elocationid', '')
        except Exception as e:
            logger.warning(f"Failed to extract DOI: {e}")
            return ''
    
    def _parse_pub_date(self, pub_date: str) -> Optional[datetime]:
        """Parse PubMed publication date string."""
        if not pub_date:
            return None
        
        try:
            # Handle various PubMed date formats
            # Common formats: "2023 Dec", "2023 Dec 15", "2023", "Dec 2023"
            
            # Extract year
            year_match = re.search(r'(\d{4})', pub_date)
            if not year_match:
                return None
            
            year = int(year_match.group(1))
            
            # Extract month
            month = 1  # Default to January
            month_names = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }
            
            for month_name, month_num in month_names.items():
                if month_name in pub_date.lower():
                    month = month_num
                    break
            
            # Extract day - only if we have a month AND a separate day token
            day = 1  # Default to first day of month
            if month != 1:  # Only look for day if we found a month
                # Look for day pattern that's NOT part of the year
                day_pattern = r'(?<!\d)(\d{1,2})(?!\d)'
                day_matches = list(re.finditer(day_pattern, pub_date))
                
                # Find the day that's not the year
                for match in day_matches:
                    day_val = int(match.group(1))
                    if day_val != year % 100:  # Not the last two digits of year
                        day = day_val
                        break
            
            return datetime(year, month, day)
            
        except Exception as e:
            logger.warning(f"Failed to parse publication date '{pub_date}': {e}")
            return None
    
    def _normalize_authors(self, authors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize author information from ESummary."""
        normalized = []
        
        try:
            for author in authors:
                if isinstance(author, dict):
                    normalized_author = {
                        'name': author.get('name', ''),
                        'authtype': author.get('authtype', ''),
                        'cluster_id': author.get('clusterid', ''),
                        'affiliation': author.get('affiliation', '')
                    }
                    normalized.append(normalized_author)
                elif isinstance(author, str):
                    normalized.append({
                        'name': author,
                        'authtype': '',
                        'cluster_id': '',
                        'affiliation': ''
                    })
            
            return normalized
            
        except Exception as e:
            logger.warning(f"Failed to normalize authors: {e}")
            return []
    
    def _extract_affiliations(self, doc_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract affiliation information from ESummary."""
        affiliations = []
        
        try:
            # Look for affiliation data in various fields
            affil_data = doc_data.get('affiliation', [])
            if isinstance(affil_data, list):
                for affil in affil_data:
                    if isinstance(affil, dict):
                        affiliations.append({
                            'institution': affil.get('institution', ''),
                            'city': affil.get('city', ''),
                            'country': affil.get('country', ''),
                            'raw_text': affil.get('affiliation', '')
                        })
                    elif isinstance(affil, str):
                        affiliations.append({
                            'institution': '',
                            'city': '',
                            'country': '',
                            'raw_text': affil
                        })
            
            return affiliations
            
        except Exception as e:
            logger.warning(f"Failed to extract affiliations: {e}")
            return []
    
    def _calculate_url_hash(self, url: str) -> str:
        """Calculate hash for URL deduplication."""
        import hashlib
        return hashlib.sha256(url.encode()).hexdigest()
    
    def map_efetch_abstracts(
        self, 
        efetch_result: Dict[str, str],
        existing_docs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Map EFetch results to update existing documents with abstracts.
        
        This method specifically handles abstracts from PubMed EFetch,
        NOT full text content.
        
        Args:
            efetch_result: Raw EFetch API response (abstracts)
            existing_docs: List of existing document data
            
        Returns:
            List of updated document data
        """
        updated_docs = []
        
        try:
            for pmid, abstract_content in efetch_result.items():
                # Find existing document
                existing_doc = next(
                    (doc for doc in existing_docs if doc.get('pmid') == pmid), 
                    None
                )
                
                if existing_doc:
                    # Update abstract text content
                    if 'text' in existing_doc:
                        existing_doc['text']['abstract_text'] = abstract_content
                        existing_doc['text']['char_count_abstract'] = len(abstract_content)
                    
                    # Keep content_type as 'abstract' for PubMed abstracts
                    existing_doc['content_type'] = 'abstract'
                    
                    updated_docs.append(existing_doc)
                else:
                    logger.warning(f"No existing document found for PMID {pmid}")
            
            logger.info(f"Updated {len(updated_docs)} documents with abstracts from EFetch")
            return updated_docs
            
        except Exception as e:
            logger.error(f"Failed to map EFetch abstracts: {e}")
            raise
    
    def map_efetch_result(
        self, 
        efetch_result: Dict[str, str],
        existing_docs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Map EFetch results to update existing documents.
        
        Note: This method is deprecated. Use map_efetch_abstracts() for abstracts
        and map_pmc_fulltext() for full text content.
        
        Args:
            efetch_result: Raw EFetch API response
            existing_docs: List of existing document data
            
        Returns:
            List of updated document data
        """
        logger.warning("map_efetch_result is deprecated. Use map_efetch_abstracts() instead.")
        return self.map_efetch_abstracts(efetch_result, existing_docs)
    
    def map_pmc_fulltext(
        self, 
        pmc_content: Dict[str, str],
        existing_docs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Map PMC full text content to update existing documents.
        
        This method handles full text content from PMC, not abstracts.
        
        Args:
            pmc_content: PMC full text content
            existing_docs: List of existing document data
            
        Returns:
            List of updated document data
        """
        updated_docs = []
        
        try:
            for pmcid, fulltext_content in pmc_content.items():
                # Find existing document by PMCID
                existing_doc = next(
                    (doc for doc in existing_docs if doc.get('pmcid') == pmcid), 
                    None
                )
                
                if existing_doc:
                    # Update full text content
                    if 'text' in existing_doc:
                        existing_doc['text']['fulltext_text'] = fulltext_content
                        existing_doc['text']['char_count_fulltext'] = len(fulltext_content)
                        # Set TTL to 90 days as per spec
                        existing_doc['text']['fulltext_ttl_date'] = (
                            datetime.utcnow() + timedelta(days=90)
                        ).isoformat()
                    
                    # Update content type to fulltext
                    existing_doc['content_type'] = 'fulltext'
                    
                    updated_docs.append(existing_doc)
                else:
                    logger.warning(f"No existing document found for PMCID {pmcid}")
            
            logger.info(f"Updated {len(updated_docs)} documents with PMC full text")
            return updated_docs
            
        except Exception as e:
            logger.error(f"Failed to map PMC full text: {e}")
            raise
    
    def map_elink_result(
        self, 
        elink_result: Dict[str, Optional[str]],
        existing_docs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Map ELink results to update existing documents with PMCIDs.
        
        Args:
            elink_result: Raw ELink API response
            existing_docs: List of existing document data
            
        Returns:
            List of updated document data
        """
        updated_docs = []
        
        try:
            for pmid, pmcid in elink_result.items():
                # Find existing document
                existing_doc = next(
                    (doc for doc in existing_docs if doc.get('pmid') == pmid), 
                    None
                )
                
                if existing_doc:
                    # Update PMCID
                    existing_doc['pmcid'] = pmcid
                    
                    # Update citation
                    if 'citation' in existing_doc:
                        existing_doc['citation']['pmcid'] = pmcid
                    
                    # Add PMC metadata if available
                    if pmcid:
                        # Validate PMCID format
                        if pmcid.startswith('PMC'):
                            pmc_meta = {
                                'doc_id': None,  # Will be linked after document insertion
                                'pmcid': pmcid,
                                'license': None,  # Will be populated by PMC ESummary
                                'oa_route': None,
                                'oai_identifier': None
                            }
                            existing_doc['pmc_meta'] = pmc_meta
                        else:
                            logger.warning(f"Invalid PMCID format for PMID {pmid}: {pmcid}")
                    
                    updated_docs.append(existing_doc)
                else:
                    logger.warning(f"No existing document found for PMID {pmid}")
            
            logger.info(f"Updated {len(updated_docs)} documents with PMCIDs")
            return updated_docs
            
        except Exception as e:
            logger.error(f"Failed to map ELink results: {e}")
            raise
    
    def map_pmc_oa_status(
        self, 
        oa_status_result: Dict[str, Dict[str, Any]],
        existing_docs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Map PMC OA status results to update existing documents.
        
        Args:
            oa_status_result: Raw PMC OA status API response
            existing_docs: List of existing document data
            
        Returns:
            List of updated document data
        """
        updated_docs = []
        
        try:
            for pmcid, oa_info in oa_status_result.items():
                # Find existing document by PMCID
                existing_doc = next(
                    (doc for doc in existing_docs if doc.get('pmcid') == pmcid), 
                    None
                )
                
                if existing_doc and 'pmc_meta' in existing_doc:
                    # Update PMC metadata
                    existing_doc['pmc_meta'].update({
                        'license': oa_info.get('license', 'unknown'),
                        'oa_route': oa_info.get('oa_route', 'unknown'),
                        'oai_identifier': oa_info.get('oai_identifier')
                    })
                    
                    # Update content type if full text is available
                    if oa_info.get('full_text_available', False):
                        existing_doc['content_type'] = 'fulltext'
                    
                    updated_docs.append(existing_doc)
                else:
                    logger.warning(f"No existing document found for PMCID {pmcid}")
            
            logger.info(f"Updated {len(updated_docs)} documents with PMC OA status")
            return updated_docs
            
        except Exception as e:
            logger.error(f"Failed to map PMC OA status: {e}")
            raise
    
    def validate_mapped_data(self, mapped_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate mapped data for required fields and data quality.
        
        Args:
            mapped_data: Mapped document data
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Check required fields
        required_fields = ['source_type', 'pmid', 'title']
        for field in required_fields:
            if not mapped_data.get(field):
                issues.append(f"Missing required field: {field}")
        
        # Validate PMID format
        pmid = mapped_data.get('pmid')
        if pmid and not re.match(r'^\d+$', str(pmid)):
            issues.append(f"Invalid PMID format: {pmid}")
        
        # Validate URL format
        source_url = mapped_data.get('source_url')
        if source_url:
            try:
                urlparse(source_url)
            except Exception:
                issues.append(f"Invalid source URL: {source_url}")
        
        # Check data quality
        title = mapped_data.get('title', '')
        if len(title) < 10:
            issues.append("Title too short")
        
        # Check if abstract is populated for clinical trials
        content_type = mapped_data.get('content_type', '')
        if content_type == 'abstract':
            abstract = mapped_data.get('text', {}).get('abstract_text', '')
            if not abstract:
                # Log warning for clinical trials without abstracts
                article_type = mapped_data.get('citation', {}).get('article_type', '')
                if article_type and any(trial_type in article_type for trial_type in 
                                      ['Clinical Trial', 'Randomized Controlled Trial']):
                    logger.warning(f"Clinical trial PMID {pmid} has no abstract text")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def get_mapping_stats(self, mapped_documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get statistics about mapped documents.
        
        Args:
            mapped_documents: List of mapped document data
            
        Returns:
            Dictionary with mapping statistics
        """
        if not mapped_documents:
            return {}
        
        total_docs = len(mapped_documents)
        docs_with_abstract = sum(
            1 for doc in mapped_documents 
            if doc.get('text', {}).get('abstract_text')
        )
        docs_with_fulltext = sum(
            1 for doc in mapped_documents 
            if doc.get('text', {}).get('fulltext_text')
        )
        docs_with_pmcid = sum(
            1 for doc in mapped_documents 
            if doc.get('pmcid')
        )
        
        # Content length statistics
        abstract_lengths = [
            len(doc.get('text', {}).get('abstract_text', ''))
            for doc in mapped_documents
        ]
        
        return {
            'total_documents': total_docs,
            'documents_with_abstract': docs_with_abstract,
            'documents_with_fulltext': docs_with_fulltext,
            'documents_with_pmcid': docs_with_pmcid,
            'abstract_coverage': docs_with_abstract / total_docs if total_docs > 0 else 0,
            'fulltext_coverage': docs_with_fulltext / total_docs if total_docs > 0 else 0,
            'pmcid_coverage': docs_with_pmcid / total_docs if total_docs > 0 else 0,
            'avg_abstract_length': sum(abstract_lengths) / len(abstract_lengths) if abstract_lengths else 0,
            'min_abstract_length': min(abstract_lengths) if abstract_lengths else 0,
            'max_abstract_length': max(abstract_lengths) if abstract_lengths else 0
        }
