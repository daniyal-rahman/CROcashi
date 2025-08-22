"""
Document ingestion for PR/IR and conference abstracts.

This module handles the discovery, fetching, parsing, and entity extraction
for company PR/IR documents and conference abstracts (AACR, ASCO, ESMO).
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ncfd.db.models import (
    Document, DocumentTextPage, DocumentTable, DocumentEntity,
    DocumentCitation, DocumentNote, Asset, AssetAlias, DocumentLink
)
from ncfd.extract.asset_extractor import (
    AssetMatch, extract_all_entities, find_nearby_assets,
    get_confidence_for_link_type
)
from ncfd.storage import StorageBackend, StorageError, create_storage_backend, create_unified_storage_manager

logger = logging.getLogger(__name__)


class DocumentIngester:
    """Handles document ingestion workflow for PR/IR and conference abstracts."""
    
    def __init__(self, db_session: Session, storage_config: Dict[str, Any] = None):
        """
        Initialize the document ingester.
        
        Args:
            db_session: Database session
            storage_config: Storage configuration dictionary
        """
        self.db_session = db_session
        self.storage_config = storage_config or {}
        self.storage_backend = None
        
        # Initialize storage backend if config provided
        if self.storage_config:
            try:
                # Try to create unified storage manager first
                if 'fs' in self.storage_config and 's3' in self.storage_config:
                    self.storage_backend = create_unified_storage_manager(self.storage_config)
                    logger.info("Unified storage manager initialized with local and S3 backends")
                else:
                    # Fall back to single backend
                    self.storage_backend = create_storage_backend(self.storage_config)
                    
                    # Set up fallback if using local storage
                    if (self.storage_config.get('kind') == 'local' and 
                        self.storage_config.get('fs', {}).get('fallback_s3', True)):
                        try:
                            # Create proper fallback config with S3 settings
                            fallback_config = {
                                'kind': 's3',
                                's3': self.storage_config.get('s3', {})
                            }
                            fallback_backend = create_storage_backend(fallback_config)
                            if hasattr(self.storage_backend, 'set_fallback_backend'):
                                self.storage_backend.set_fallback_backend(fallback_backend)
                        except Exception as e:
                            logger.warning(f"Failed to configure S3 fallback: {e}")
                            
            except Exception as e:
                logger.error(f"Failed to initialize storage backend: {e}")
                self.storage_backend = None
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NCFD-Document-Ingester/1.0'
        })
    
    def discover_company_pr_ir(self, company_domains: List[str]) -> List[Dict[str, Any]]:
        """
        Discover PR/IR endpoints from company domains.
        
        Args:
            company_domains: List of company website domains
            
        Returns:
            List of discovered document URLs
        """
        discovered_docs = []
        
        for domain in company_domains:
            if not domain.startswith('http'):
                domain = f"https://{domain}"
            
            # Common IR/PR paths to try
            ir_paths = [
                f"{domain}/investors",
                f"{domain}/ir",
                f"{domain}/newsroom",
                f"{domain}/news",
                f"{domain}/press-releases",
                f"{domain}/media",
                f"{domain}/press"
            ]
            
            for path in ir_paths:
                try:
                    response = self.session.get(path, timeout=10)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Look for news/article links
                        links = soup.find_all('a', href=True)
                        for link in links:
                            href = link.get('href')
                            if href and self._is_news_link(href, link.text):
                                full_url = self._make_absolute_url(href, path)
                                discovered_docs.append({
                                    'url': full_url,
                                    'title': link.text.strip(),
                                    'domain': domain,
                                    'source_type': 'PR' if 'press' in href.lower() else 'IR'
                                })
                        
                        # Check for sitemap
                        sitemap_links = soup.find_all('a', href=re.compile(r'sitemap', re.I))
                        for sitemap_link in sitemap_links:
                            # Could parse sitemap for more URLs
                            pass
                            
                except Exception as e:
                    logger.warning(f"Failed to discover from {path}: {e}")
                    continue
        
        return discovered_docs
    
    def discover_conference_abstracts(self) -> List[Dict[str, Any]]:
        """
        Discover conference abstract sources (AACR, ASCO, ESMO).
        
        Returns:
            List of discovered abstract sources
        """
        discovered_sources = []
        
        # AACR Proceedings (open access)
        aacr_sources = [
            "https://cancerres.aacrjournals.org/content/by/year",
            "https://aacrjournals.org/cancerres/issue"
        ]
        
        # ASCO Journal Supplements (DOI-based)
        asco_sources = [
            "https://ascopubs.org/journal/jco",
            "https://ascopubs.org/journal/jco-go",
            "https://ascopubs.org/journal/jco-precision-oncology"
        ]
        
        # ESMO Annals of Oncology (open subsets)
        esmo_sources = [
            "https://www.annalsofoncology.org/issue",
            "https://www.esmo.org/meetings/esmo-congress"
        ]
        
        for source in aacr_sources + asco_sources + esmo_sources:
            discovered_sources.append({
                'url': source,
                'publisher': self._get_publisher_from_url(source),
                'source_type': 'Abstract'
            })
        
        return discovered_sources
    
    def fetch_document(self, url: str, source_type: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a document from URL and compute metadata.
        
        Args:
            url: Document URL
            source_type: Type of document source
            
        Returns:
            Document metadata and content, or None if failed
        """
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Compute SHA256 hash of raw content
            content = response.content
            sha256 = hashlib.sha256(content).hexdigest()
            
            # Determine content type
            content_type = response.headers.get('content-type', 'text/html')
            
            # Extract publication date from headers or HTML
            published_at = self._extract_publication_date(response, content)
            
            # Determine open access status
            oa_status = self._determine_oa_status(url, content_type, response.headers)
            
            return {
                'url': url,
                'content': content,
                'sha256': sha256,
                'content_type': content_type,
                'published_at': published_at,
                'oa_status': oa_status,
                'headers': dict(response.headers)
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
    
    def parse_document(self, content: bytes, content_type: str, url: str) -> Dict[str, Any]:
        """
        Parse document content and extract text, tables, and entities.
        
        Args:
            content: Raw document content
            content_type: MIME type of content
            url: Source URL for context
            
        Returns:
            Parsed document data
        """
        parsed_data = {
            'text_pages': [],
            'tables': [],
            'entities': [],
            'citations': {}
        }
        
        if 'text/html' in content_type:
            # Parse HTML
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract main content
            main_content = self._extract_main_content(soup)
            
            # Split into pages (treat as single page for now)
            text = main_content.get_text(separator=' ', strip=True)
            parsed_data['text_pages'].append({
                'page_no': 1,
                'char_count': len(text),
                'text': text
            })
            
            # Extract tables if any
            tables = soup.find_all('table')
            for i, table in enumerate(tables):
                table_data = self._extract_table_data(table)
                parsed_data['tables'].append({
                    'page_no': 1,
                    'table_idx': i,
                    'table_jsonb': table_data,
                    'detector': 'beautifulsoup'
                })
            
            # Extract citations (DOIs, PMIDs)
            citations = self._extract_citations(text)
            parsed_data['citations'] = citations
            
            # Extract entities using asset extractor
            entities = extract_all_entities(text, page_no=1)
            parsed_data['entities'] = [self._asset_match_to_dict(entity) for entity in entities]
            
        elif 'application/pdf' in content_type:
            # PDF parsing would go here
            # For now, return minimal data
            parsed_data['text_pages'].append({
                'page_no': 1,
                'char_count': 0,
                'text': '[PDF content - parsing not implemented]'
            })
        
        return parsed_data
    
    def store_document(self, fetch_data: Dict[str, Any], parsed_data: Dict[str, Any],
                      source_type: str, publisher: str = None) -> Optional[Document]:
        """
        Store document in database and storage backend.
        
        Args:
            fetch_data: Data from fetch_document
            parsed_data: Data from parse_document
            source_type: Type of document source
            publisher: Publisher information
            
        Returns:
            Created Document object or None if failed
        """
        try:
            # Upload to storage backend if available
            storage_uri = None
            if self.storage_backend:
                storage_uri = self._upload_to_storage(
                    fetch_data['content'],
                    fetch_data['sha256'],
                    fetch_data['url']
                )
            else:
                # Fallback to local storage path
                storage_uri = f"file:///tmp/{fetch_data['sha256']}"
            
            # Create document record
            doc = Document(
                source_type=source_type,
                source_url=fetch_data['url'],
                publisher=publisher,
                published_at=fetch_data['published_at'],
                storage_uri=storage_uri,
                content_type=fetch_data['content_type'],
                sha256=fetch_data['sha256'],
                oa_status=fetch_data['oa_status'],
                status='fetched',
                fetched_at=datetime.utcnow()
            )
            
            self.db_session.add(doc)
            self.db_session.flush()  # Get the doc_id
            
            # Create text pages
            for page_data in parsed_data['text_pages']:
                text_page = DocumentTextPage(
                    doc_id=doc.doc_id,
                    page_no=page_data['page_no'],
                    char_count=page_data['char_count'],
                    text=page_data['text']
                )
                self.db_session.add(text_page)
            
            # Create tables
            for table_data in parsed_data['tables']:
                table = DocumentTable(
                    doc_id=doc.doc_id,
                    page_no=table_data['page_no'],
                    table_idx=table_data['table_idx'],
                    table_jsonb=table_data['table_jsonb'],
                    detector=table_data['detector']
                )
                self.db_session.add(table)
            
            # Create entities
            for entity_data in parsed_data['entities']:
                entity = DocumentEntity(
                    doc_id=doc.doc_id,
                    ent_type=entity_data['alias_type'],
                    value_text=entity_data['value_text'],
                    value_norm=entity_data['value_norm'],
                    page_no=entity_data['page_no'],
                    char_start=entity_data['char_start'],
                    char_end=entity_data['char_end'],
                    detector=entity_data['detector']
                )
                self.db_session.add(entity)
            
            # Create citations if any
            if parsed_data['citations']:
                citation = DocumentCitation(
                    doc_id=doc.doc_id,
                    doi=parsed_data['citations'].get('doi'),
                    pmid=parsed_data['citations'].get('pmid'),
                    pmcid=parsed_data['citations'].get('pmcid')
                )
                self.db_session.add(citation)
            
            # Update status to parsed
            doc.status = 'parsed'
            doc.parsed_at = datetime.utcnow()
            
            self.db_session.commit()
            return doc
            
        except Exception as e:
            logger.error(f"Failed to store document: {e}")
            self.db_session.rollback()
            return None
    
    def create_document_links(self, doc: Document, entities: List[Dict[str, Any]]) -> None:
        """
        Create document links based on extracted entities.
        
        Args:
            doc: Document object
            entities: List of extracted entities
        """
        try:
            # Group entities by type
            asset_entities = [e for e in entities if e['alias_type'] in ['code', 'inn', 'generic']]
            nct_entities = [e for e in entities if e['alias_type'] == 'nct']
            
            # Find nearby assets and NCTs (HP-1 heuristic)
            nearby_pairs = find_nearby_assets(
                [self._dict_to_asset_match(e) for e in asset_entities],
                [self._dict_to_asset_match(e) for e in nct_entities]
            )
            
            # Create high-confidence links for nearby pairs
            for asset_match, nct_match in nearby_pairs:
                # Create or find asset
                asset = self._get_or_create_asset(asset_match)
                
                # Create document link
                link = DocumentLink(
                    doc_id=doc.doc_id,
                    nct_id=nct_match.value_norm,
                    asset_id=asset.asset_id,
                    link_type='nct_near_asset',
                    confidence=get_confidence_for_link_type('nct_near_asset')
                )
                self.db_session.add(link)
            
            # Create other entity links
            for entity in asset_entities:
                asset = self._get_or_create_asset(self._dict_to_asset_match(entity))
                
                link = DocumentLink(
                    doc_id=doc.doc_id,
                    asset_id=asset.asset_id,
                    link_type=f"{entity['alias_type']}_in_text",
                    confidence=get_confidence_for_link_type(f"{entity['alias_type']}_in_text")
                )
                self.db_session.add(link)
            
            # Update document status
            doc.status = 'linked'
            self.db_session.commit()
            
        except Exception as e:
            logger.error(f"Failed to create document links: {e}")
            self.db_session.rollback()
    
    def _is_news_link(self, href: str, text: str) -> bool:
        """Check if a link is likely a news/article link."""
        news_keywords = ['news', 'press', 'release', 'article', 'announcement']
        href_lower = href.lower()
        text_lower = text.lower()
        
        return any(keyword in href_lower or keyword in text_lower for keyword in news_keywords)
    
    def _make_absolute_url(self, href: str, base_url: str) -> str:
        """Convert relative URL to absolute URL."""
        if href.startswith('http'):
            return href
        elif href.startswith('/'):
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{href}"
        else:
            return f"{base_url.rstrip('/')}/{href}"
    
    def _get_publisher_from_url(self, url: str) -> str:
        """Extract publisher name from URL."""
        if 'aacr' in url:
            return 'AACR / Cancer Research Proceedings'
        elif 'asco' in url:
            return 'ASCO / JCO*'
        elif 'esmo' in url:
            return 'ESMO / Annals of Oncology'
        else:
            return 'Unknown'
    
    def _extract_publication_date(self, response: requests.Response, content: bytes) -> Optional[datetime]:
        """Extract publication date from response headers or content."""
        # Try to get date from headers first
        date_header = response.headers.get('last-modified') or response.headers.get('date')
        if date_header:
            try:
                return datetime.strptime(date_header, '%a, %d %b %Y %H:%M:%S %Z')
            except ValueError:
                pass
        
        # Try to parse from HTML content
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for common date meta tags
            date_selectors = [
                'meta[property="article:published_time"]',
                'meta[name="publication_date"]',
                'meta[name="publish_date"]',
                'time[datetime]'
            ]
            
            for selector in date_selectors:
                element = soup.select_one(selector)
                if element:
                    date_str = element.get('content') or element.get('datetime')
                    if date_str:
                        # Parse various date formats
                        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S']:
                            try:
                                return datetime.strptime(date_str[:19], fmt)
                            except ValueError:
                                continue
        except Exception:
            pass
        
        return None
    
    def _determine_oa_status(self, url: str, content_type: str, headers: Dict[str, str]) -> str:
        """Determine open access status of document."""
        # This is a simplified implementation
        # In production, you'd check DOIs against Unpaywall API, etc.
        if 'pdf' in content_type.lower():
            return 'unknown'
        elif 'aacr' in url.lower():
            return 'open'  # AACR proceedings are generally open
        else:
            return 'unknown'
    
    def _extract_main_content(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Extract main content from HTML, removing navigation, ads, etc."""
        # Look for common content containers
        content_selectors = [
            'article',
            '[role="main"]',
            '.content',
            '.main-content',
            '#content',
            '#main'
        ]
        
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                return content
        
        # Fallback: remove common non-content elements
        for element in soup(['nav', 'header', 'footer', 'aside', 'script', 'style']):
            element.decompose()
        
        return soup
    
    def _extract_table_data(self, table: BeautifulSoup) -> Dict[str, Any]:
        """Extract table data as structured JSON."""
        rows = []
        for tr in table.find_all('tr'):
            row = []
            for td in tr.find_all(['td', 'th']):
                row.append(td.get_text(strip=True))
            if row:
                rows.append(row)
        
        return {
            'rows': rows,
            'row_count': len(rows),
            'col_count': len(rows[0]) if rows else 0
        }
    
    def _extract_citations(self, text: str) -> Dict[str, str]:
        """Extract citations (DOIs, PMIDs) from text."""
        import re
        
        citations = {}
        
        # DOI pattern
        doi_pattern = r'\b10\.\d{4,}/[-._;()/:\w]+\b'
        doi_match = re.search(doi_pattern, text)
        if doi_match:
            citations['doi'] = doi_match.group(0)
        
        # PMID pattern
        pmid_pattern = r'\bPMID:\s*(\d+)\b'
        pmid_match = re.search(pmid_pattern, text)
        if pmid_match:
            citations['pmid'] = pmid_match.group(1)
        
        return citations
    
    def _upload_to_storage(self, content: bytes, sha256: str, url: str) -> str:
        """Upload content to storage backend."""
        if self.storage_backend:
            try:
                filename = self._get_filename_from_url(url)
                metadata = {
                    'source_url': url,
                    'uploaded_at': datetime.utcnow().isoformat(),
                    'content_length': len(content)
                }
                
                storage_uri = self.storage_backend.store(content, sha256, filename, metadata)
                logger.info(f"Content stored: {storage_uri}")
                return storage_uri
                
            except Exception as e:
                logger.error(f"Storage upload failed: {e}")
                # Fail hard instead of using dangerous /tmp fallback
                raise StorageError(f"Storage upload failed: {e}")
        else:
            # No storage backend configured - fail hard
            raise StorageError("No storage backend configured")
    
    def _get_filename_from_url(self, url: str) -> str:
        """Extract filename from URL."""
        parsed = urlparse(url)
        path = parsed.path
        if path.endswith('/'):
            return 'index.html'
        return path.split('/')[-1] or 'index.html'
    
    def _asset_match_to_dict(self, asset_match: AssetMatch) -> Dict[str, Any]:
        """Convert AssetMatch to dictionary."""
        return {
            'alias_type': asset_match.alias_type,
            'value_text': asset_match.value_text,
            'value_norm': asset_match.value_norm,
            'page_no': asset_match.page_no,
            'char_start': asset_match.char_start,
            'char_end': asset_match.char_end,
            'detector': asset_match.detector
        }
    
    def _dict_to_asset_match(self, entity_dict: Dict[str, Any]) -> AssetMatch:
        """Convert dictionary to AssetMatch."""
        return AssetMatch(
            alias_type=entity_dict['alias_type'],
            value_text=entity_dict['value_text'],
            value_norm=entity_dict['value_norm'],
            page_no=entity_dict['page_no'],
            char_start=entity_dict['char_start'],
            char_end=entity_dict['char_end'],
            detector=entity_dict['detector']
        )
    
    def _get_or_create_asset(self, asset_match: AssetMatch) -> Asset:
        """Get existing asset or create new one."""
        # Look for existing asset by alias
        existing_alias = self.db_session.query(AssetAlias).filter(
            AssetAlias.alias_norm == asset_match.value_norm,
            AssetAlias.alias_type == asset_match.alias_type
        ).first()
        
        if existing_alias:
            return existing_alias.asset
        
        # Create new asset
        asset = Asset()
        self.db_session.add(asset)
        self.db_session.flush()
        
        # Create alias
        alias = AssetAlias(
            asset_id=asset.asset_id,
            alias=asset_match.value_text,
            alias_norm=asset_match.value_norm,
            alias_type=asset_match.alias_type,
            source='document_extraction'
        )
        self.db_session.add(alias)
        
        return asset

    # Phase 4 Workflow Methods
    
    def run_discovery_job(self, company_domains: List[str] = None) -> List[Dict[str, Any]]:
        """
        Run the discovery job to find new documents.
        
        This implements the first step of the Phase 4 pipeline:
        - Discover company PR/IR documents
        - Discover conference abstracts
        
        Args:
            company_domains: List of company domains to search
            
        Returns:
            List of discovered document sources
        """
        logger.info("Starting discovery job")
        
        discovered_sources = []
        
        # Discover company PR/IR documents
        if company_domains:
            company_docs = self.discover_company_pr_ir(company_domains)
            discovered_sources.extend(company_docs)
            logger.info(f"Discovered {len(company_docs)} company documents")
        
        # Discover conference abstracts
        conference_docs = self.discover_conference_abstracts()
        discovered_sources.extend(conference_docs)
        logger.info(f"Discovered {len(conference_docs)} conference sources")
        
        # Store discovery results for tracking
        self._store_discovery_results(discovered_sources)
        
        logger.info(f"Discovery job completed: {len(discovered_sources)} sources found")
        return discovered_sources
    
    def run_fetch_job(self, sources: List[Dict[str, Any]], max_docs: int = 100) -> List[Dict[str, Any]]:
        """
        Run the fetch job to download documents.
        
        This implements the second step of the Phase 4 pipeline:
        - Download document content
        - Compute metadata and hashes
        - Upload to storage
        
        Args:
            sources: List of document sources from discovery
            max_docs: Maximum number of documents to fetch
            
        Returns:
            List of fetched document data
        """
        logger.info(f"Starting fetch job for {len(sources)} sources")
        
        fetched_docs = []
        failed_sources = []
        
        for i, source in enumerate(sources[:max_docs]):
            try:
                logger.info(f"Fetching {i+1}/{len(sources)}: {source['url']}")
                
                fetch_data = self.fetch_document(source['url'], source.get('source_type', 'unknown'))
                if fetch_data:
                    fetched_docs.append({
                        'source': source,
                        'fetch_data': fetch_data
                    })
                    logger.info(f"Successfully fetched: {source['url']}")
                else:
                    failed_sources.append(source)
                    logger.warning(f"Failed to fetch: {source['url']}")
                    
            except Exception as e:
                failed_sources.append(source)
                logger.error(f"Error fetching {source['url']}: {e}")
                continue
        
        # Store fetch results for tracking
        self._store_fetch_results(fetched_docs, failed_sources)
        
        logger.info(f"Fetch job completed: {len(fetched_docs)} fetched, {len(failed_sources)} failed")
        return fetched_docs
    
    def run_parse_job(self, fetched_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run the parse job to extract text and entities.
        
        This implements the third step of the Phase 4 pipeline:
        - Parse document content
        - Extract text, tables, and entities
        - Store parsed data
        
        Args:
            fetched_docs: List of fetched documents
            
        Returns:
            List of parsed documents
        """
        logger.info(f"Starting parse job for {len(fetched_docs)} documents")
        
        parsed_docs = []
        failed_parses = []
        
        for i, doc_data in enumerate(fetched_docs):
            try:
                source = doc_data['source']
                fetch_data = doc_data['fetch_data']
                
                logger.info(f"Parsing {i+1}/{len(fetched_docs)}: {source['url']}")
                
                # Parse document content
                parsed_data = self.parse_document(
                    fetch_data['content'],
                    fetch_data['content_type'],
                    source['url']
                )
                
                # Store document in database
                doc = self.store_document(fetch_data, parsed_data, source)
                
                parsed_docs.append({
                    'source': source,
                    'fetch_data': fetch_data,
                    'parsed_data': parsed_data,
                    'document': doc
                })
                
                logger.info(f"Successfully parsed: {source['url']} -> doc_id {doc.doc_id}")
                
            except Exception as e:
                failed_parses.append(doc_data)
                logger.error(f"Error parsing {source['url']}: {e}")
                continue
        
        # Store parse results for tracking
        self._store_parse_results(parsed_docs, failed_parses)
        
        logger.info(f"Parse job completed: {len(parsed_docs)} parsed, {len(failed_parses)} failed")
        return parsed_docs
    
    def run_link_job(self, parsed_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run the link job to create document-entity links.
        
        This implements the fourth step of the Phase 4 pipeline:
        - Extract entities from parsed documents
        - Create links between documents and assets
        - Apply linking heuristics (HP-1 through HP-4)
        
        Args:
            parsed_docs: List of parsed documents
            
        Returns:
            List of linked documents
        """
        logger.info(f"Starting link job for {len(parsed_docs)} documents")
        
        linked_docs = []
        failed_links = []
        
        for i, doc_data in enumerate(parsed_docs):
            try:
                source = doc_data['source']
                doc = doc_data['document']
                parsed_data = doc_data['parsed_data']
                
                logger.info(f"Linking {i+1}/{len(parsed_docs)}: {source['url']} -> doc_id {doc.doc_id}")
                
                # Extract entities using asset extractor
                entities = self._extract_entities_from_parsed_data(parsed_data, doc.doc_id)
                
                # Create document links
                self.create_document_links(doc, entities)
                
                linked_docs.append({
                    'source': source,
                    'document': doc,
                    'entities': entities
                })
                
                logger.info(f"Successfully linked: {source['url']} -> {len(entities)} entities")
                
            except Exception as e:
                failed_links.append(doc_data)
                logger.error(f"Error linking {source['url']}: {e}")
                continue
        
        # Store link results for tracking
        self._store_link_results(linked_docs, failed_links)
        
        logger.info(f"Link job completed: {len(linked_docs)} linked, {len(failed_links)} failed")
        return linked_docs
    
    def run_full_pipeline(self, company_domains: List[str] = None, max_docs: int = 100) -> Dict[str, Any]:
        """
        Run the complete Phase 4 pipeline.
        
        This orchestrates all four jobs:
        1. Discovery: Find document sources
        2. Fetch: Download documents
        3. Parse: Extract text and entities
        4. Link: Create document-entity links
        
        Args:
            company_domains: List of company domains to search
            max_docs: Maximum number of documents to process
            
        Returns:
            Pipeline results summary
        """
        logger.info("Starting Phase 4 full pipeline")
        
        try:
            # Step 1: Discovery
            sources = self.run_discovery_job(company_domains)
            
            # Step 2: Fetch
            fetched_docs = self.run_fetch_job(sources, max_docs)
            
            # Step 3: Parse
            parsed_docs = self.run_parse_job(fetched_docs)
            
            # Step 4: Link
            linked_docs = self.run_link_job(parsed_docs)
            
            # Compile results
            results = {
                'discovery': {
                    'total_sources': len(sources),
                    'company_docs': len([s for s in sources if s.get('source_type') in ['PR', 'IR']]),
                    'conference_sources': len([s for s in sources if s.get('source_type') == 'Abstract'])
                },
                'fetch': {
                    'total_fetched': len(fetched_docs),
                    'failed_fetches': len(sources) - len(fetched_docs)
                },
                'parse': {
                    'total_parsed': len(parsed_docs),
                    'failed_parses': len(fetched_docs) - len(parsed_docs)
                },
                'link': {
                    'total_linked': len(linked_docs),
                    'failed_links': len(parsed_docs) - len(linked_docs)
                }
            }
            
            logger.info("Phase 4 full pipeline completed successfully")
            return results
            
        except Exception as e:
            logger.error(f"Phase 4 pipeline failed: {e}")
            raise
    
    # Helper methods for workflow tracking
    
    def _store_discovery_results(self, sources: List[Dict[str, Any]]) -> None:
        """Store discovery results for tracking."""
        # In production, this would store to a job tracking table
        logger.info(f"Discovery results stored: {len(sources)} sources")
    
    def _store_fetch_results(self, fetched_docs: List[Dict[str, Any]], failed_sources: List[Dict[str, Any]]) -> None:
        """Store fetch results for tracking."""
        # In production, this would store to a job tracking table
        logger.info(f"Fetch results stored: {len(fetched_docs)} fetched, {len(failed_sources)} failed")
    
    def _store_parse_results(self, parsed_docs: List[Dict[str, Any]], failed_parses: List[Dict[str, Any]]) -> None:
        """Store parse results for tracking."""
        # In production, this would store to a job tracking table
        logger.info(f"Parse results stored: {len(parsed_docs)} parsed, {len(failed_parses)} failed")
    
    def _store_link_results(self, linked_docs: List[Dict[str, Any]], failed_links: List[Dict[str, Any]]) -> None:
        """Store link results for tracking."""
        # In production, this would store to a job tracking table
        logger.info(f"Link results stored: {len(linked_docs)} linked, {len(failed_links)} failed")
    
    def _extract_entities_from_parsed_data(self, parsed_data: Dict[str, Any], doc_id: int) -> List[Dict[str, Any]]:
        """Extract entities from parsed document data."""
        from ncfd.extract.asset_extractor import extract_all_entities
        
        entities = []
        
        # Extract entities from each text page
        for page_data in parsed_data.get('text_pages', []):
            page_no = page_data.get('page_no', 1)
            text = page_data.get('text', '')
            
            if text:
                # Extract all entity types
                asset_matches = extract_all_entities(text, page_no)
                
                # Convert to entity dictionaries
                for match in asset_matches:
                    entity = {
                        'alias_type': match.alias_type,
                        'value_text': match.value_text,
                        'value_norm': match.value_norm,
                        'page_no': match.page_no,
                        'char_start': match.char_start,
                        'char_end': match.char_end,
                        'detector': match.detector,
                        'confidence': match.confidence
                    }
                    entities.append(entity)
        
        logger.info(f"Extracted {len(entities)} entities from document {doc_id}")
        return entities
