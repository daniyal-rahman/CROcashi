"""
PubMed/OpenAlex→Unpaywall→PMC literature ingestion.

This module implements the core OA intake path for legal literature metadata + OA fulltext.
"""

import logging
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs
import hashlib
from sqlalchemy.orm import Session

from ncfd.db.models import Document, DocumentTextPage, DocumentCitation, DocumentEntity
from ncfd.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class PubRecord:
    """Represents a publication record from PubMed/OpenAlex."""
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    doi: Optional[str] = None
    title: str = ""
    authors: List[str] = None
    journal: str = ""
    publication_date: Optional[datetime] = None
    abstract: str = ""
    keywords: List[str] = None
    mesh_terms: List[str] = None
    nct_ids: List[str] = None
    source: str = ""  # 'pubmed', 'openalex', 'crossref'
    
    def __post_init__(self):
        if self.authors is None:
            self.authors = []
        if self.keywords is None:
            self.keywords = []
        if self.mesh_terms is None:
            self.mesh_terms = []
        if self.nct_ids is None:
            self.nct_ids = []


@dataclass
class RetrievedDoc:
    """Represents a retrieved document with full text."""
    doc_id: str
    content: bytes
    content_type: str
    url: str
    metadata: Dict[str, Any]
    text_pages: List[str] = None
    tables: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.text_pages is None:
            self.text_pages = []
        if self.tables is None:
            self.tables = []


@dataclass
class CrossrefMeta:
    """Metadata from Crossref API."""
    doi: str
    title: str
    authors: List[str]
    journal: str
    publication_date: Optional[datetime]
    abstract: str
    references: List[str]
    license: Optional[str] = None
    oa_status: str = "unknown"


@dataclass
class OARecord:
    """Open Access information from Unpaywall."""
    doi: str
    is_oa: bool
    oa_status: str
    best_oa_location: Optional[Dict[str, Any]] = None
    pmc_url: Optional[str] = None
    pdf_url: Optional[str] = None


class PubMedClient:
    """Client for PubMed E-utilities API."""
    
    def __init__(self, email: str = None, api_key: str = None):
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.email = email or "ncfd@example.com"
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': f'NCFD-PubMed-Client/1.0 ({self.email})'
        })
    
    def search_by_nct(self, nct_id: str, max_results: int = 100) -> List[PubRecord]:
        """
        Search PubMed for publications related to a specific NCT ID.
        
        Args:
            nct_id: Clinical trial identifier (e.g., "NCT12345678")
            max_results: Maximum number of results to return
            
        Returns:
            List of publication records
        """
        try:
            # Search for NCT ID in PubMed
            search_query = f'"{nct_id}"[All Fields]'
            
            # First, search for the NCT ID
            search_params = {
                'db': 'pubmed',
                'term': search_query,
                'retmax': max_results,
                'retmode': 'json',
                'email': self.email
            }
            
            if self.api_key:
                search_params['api_key'] = self.api_key
            
            response = self.session.get(f"{self.base_url}/esearch.fcgi", params=search_params)
            response.raise_for_status()
            
            search_data = response.json()
            id_list = search_data.get('esearchresult', {}).get('idlist', [])
            
            if not id_list:
                logger.info(f"No PubMed results found for NCT ID: {nct_id}")
                return []
            
            # Fetch details for each publication
            publications = []
            for pmid in id_list[:max_results]:
                try:
                    pub_record = self._fetch_publication_details(pmid)
                    if pub_record:
                        publications.append(pub_record)
                except Exception as e:
                    logger.warning(f"Failed to fetch details for PMID {pmid}: {e}")
                    continue
            
            logger.info(f"Found {len(publications)} publications for NCT ID: {nct_id}")
            return publications
            
        except Exception as e:
            logger.error(f"PubMed search failed for NCT ID {nct_id}: {e}")
            return []
    
    def search_by_drug(self, drug_name: str, max_results: int = 100) -> List[PubRecord]:
        """
        Search PubMed for publications related to a specific drug.
        
        Args:
            drug_name: Drug name (e.g., "Ruxolitinib", "JAK inhibitor")
            max_results: Maximum number of results to return
            
        Returns:
            List of publication records
        """
        try:
            # Search for drug name in title, abstract, and MeSH terms
            search_query = f'"{drug_name}"[Title/Abstract] OR "{drug_name}"[MeSH Terms]'
            
            search_params = {
                'db': 'pubmed',
                'term': search_query,
                'retmax': max_results,
                'retmode': 'json',
                'email': self.email
            }
            
            if self.api_key:
                search_params['api_key'] = self.api_key
            
            response = self.session.get(f"{self.base_url}/esearch.fcgi", params=search_params)
            response.raise_for_status()
            
            search_data = response.json()
            id_list = search_data.get('esearchresult', {}).get('idlist', [])
            
            if not id_list:
                logger.info(f"No PubMed results found for drug: {drug_name}")
                return []
            
            # Fetch details for each publication
            publications = []
            for pmid in id_list[:max_results]:
                try:
                    pub_record = self._fetch_publication_details(pmid)
                    if pub_record:
                        publications.append(pub_record)
                except Exception as e:
                    logger.warning(f"Failed to fetch details for PMID {pmid}: {e}")
                    continue
            
            logger.info(f"Found {len(publications)} publications for drug: {drug_name}")
            return publications
            
        except Exception as e:
            logger.error(f"PubMed search failed for drug {drug_name}: {e}")
            return []
    
    def search_by_drug_and_condition(self, drug_name: str, condition: str, max_results: int = 100) -> List[PubRecord]:
        """
        Search PubMed for publications about a drug and specific condition.
        
        Args:
            drug_name: Drug name (e.g., "Ruxolitinib")
            condition: Medical condition (e.g., "myelofibrosis", "COVID-19")
            max_results: Maximum number of results to return
            
        Returns:
            List of publication records
        """
        try:
            query = f'("{drug_name}"[Title/Abstract] OR "{drug_name}"[MeSH Terms]) AND "{condition}"[Title/Abstract]'
            
            search_params = {
                'db': 'pubmed',
                'term': query,
                'retmax': max_results,
                'retmode': 'json',
                'email': self.email
            }
            
            if self.api_key:
                search_params['api_key'] = self.api_key
            
            response = self.session.get(f"{self.base_url}/esearch.fcgi", params=search_params)
            response.raise_for_status()
            
            search_data = response.json()
            id_list = search_data.get('esearchresult', {}).get('idlist', [])
            
            if not id_list:
                logger.info(f"No PubMed results found for drug {drug_name} and condition {condition}")
                return []
            
            # Fetch details for each publication
            publications = []
            for pmid in id_list[:max_results]:
                try:
                    pub_record = self._fetch_publication_details(pmid)
                    if pub_record:
                        publications.append(pub_record)
                except Exception as e:
                    logger.warning(f"Failed to fetch details for PMID {pmid}: {e}")
                    continue
            
            logger.info(f"Found {len(publications)} publications for drug {drug_name} and condition {condition}")
            return publications
            
        except Exception as e:
            logger.error(f"PubMed search failed for drug {drug_name} and condition {condition}: {e}")
            return []
    
    def _fetch_publication_details(self, pmid: str) -> Optional[PubRecord]:
        """Fetch detailed information for a specific PMID."""
        try:
            params = {
                'db': 'pubmed',
                'id': pmid,
                'retmode': 'xml',
                'email': self.email
            }
            
            if self.api_key:
                params['api_key'] = self.api_key
            
            response = self.session.get(f"{self.base_url}/efetch.fcgi", params=params)
            response.raise_for_status()
            
            # Parse XML response (simplified - in production use proper XML parser)
            content = response.text
            
            # Extract basic information
            title_match = re.search(r'<ArticleTitle>(.*?)</ArticleTitle>', content)
            title = title_match.group(1) if title_match else ""
            
            # Extract authors
            authors = re.findall(r'<LastName>(.*?)</LastName><ForeName>(.*?)</ForeName>', content)
            author_list = [f"{last} {first}" for last, first in authors]
            
            # Extract journal
            journal_match = re.search(r'<Journal><Title>(.*?)</Title>', content)
            journal = journal_match.group(1) if journal_match else ""
            
            # Extract abstract
            abstract_match = re.search(r'<AbstractText>(.*?)</AbstractText>', content)
            abstract = abstract_match.group(1) if abstract_match else ""
            
            # Extract NCT IDs from abstract/text
            nct_ids = re.findall(r'NCT\d{8}', content)
            
            # Extract publication date
            pub_date_match = re.search(r'<PubDate><Year>(\d{4})</Year>', content)
            pub_date = None
            if pub_date_match:
                year = int(pub_date_match.group(1))
                pub_date = datetime(year, 1, 1)  # Approximate date
            
            return PubRecord(
                pmid=pmid,
                title=title,
                authors=author_list,
                journal=journal,
                abstract=abstract,
                publication_date=pub_date,
                nct_ids=nct_ids,
                source='pubmed'
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch publication details for PMID {pmid}: {e}")
            return None


class PMCClient:
    """Client for PubMed Central (PMC) full-text retrieval."""
    
    def __init__(self):
        self.base_url = "https://www.ncbi.nlm.nih.gov/pmc"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NCFD-PMC-Client/1.0'
        })
    
    def fetch_fulltext(self, pmcid: str) -> Optional[RetrievedDoc]:
        """
        Fetch full text from PMC.
        
        Args:
            pmcid: PMC identifier (e.g., "PMC123456")
            
        Returns:
            Retrieved document with full text
        """
        try:
            # PMC full-text URL
            url = f"{self.base_url}/articles/{pmcid}/"
            
            response = self.session.get(url)
            response.raise_for_status()
            
            content = response.content
            content_type = response.headers.get('content-type', 'text/html')
            
            # Generate document ID
            doc_id = hashlib.sha256(f"{pmcid}_{len(content)}".encode()).hexdigest()[:16]
            
            # Extract text content (simplified - in production use proper HTML parser)
            text_content = self._extract_text_from_html(content)
            
            # Split into pages (simplified - treat as single page for now)
            text_pages = [text_content]
            
            # Extract tables if any
            tables = self._extract_tables_from_html(content)
            
            metadata = {
                'pmcid': pmcid,
                'url': url,
                'retrieved_at': datetime.utcnow().isoformat(),
                'content_length': len(content)
            }
            
            return RetrievedDoc(
                doc_id=doc_id,
                content=content,
                content_type=content_type,
                url=url,
                metadata=metadata,
                text_pages=text_pages,
                tables=tables
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch PMC fulltext for {pmcid}: {e}")
            return None
    
    def _extract_text_from_html(self, html_content: bytes) -> str:
        """Extract text content from HTML."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text
        except ImportError:
            # Fallback if BeautifulSoup not available
            import re
            # Simple regex to remove HTML tags
            text = re.sub(r'<[^>]+>', '', html_content.decode('utf-8', errors='ignore'))
            return text
    
    def _extract_tables_from_html(self, html_content: bytes) -> List[Dict[str, Any]]:
        """Extract table data from HTML."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            tables = []
            for i, table in enumerate(soup.find_all('table')):
                table_data = []
                for row in table.find_all('tr'):
                    row_data = []
                    for cell in row.find_all(['td', 'th']):
                        row_data.append(cell.get_text(strip=True))
                    if row_data:
                        table_data.append(row_data)
                
                if table_data:
                    tables.append({
                        'table_idx': i,
                        'rows': table_data,
                        'row_count': len(table_data),
                        'col_count': len(table_data[0]) if table_data else 0
                    })
            
            return tables
        except ImportError:
            return []


class CrossrefClient:
    """Client for Crossref API."""
    
    def __init__(self, email: str = None):
        self.base_url = "https://api.crossref.org"
        self.email = email or "ncfd@example.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': f'NCFD-Crossref-Client/1.0 ({self.email})'
        })
    
    def get_metadata(self, doi: str) -> Optional[CrossrefMeta]:
        """
        Get metadata for a DOI from Crossref.
        
        Args:
            doi: Digital Object Identifier
            
        Returns:
            Crossref metadata
        """
        try:
            url = f"{self.base_url}/works/{doi}"
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            work = data.get('message', {})
            
            # Extract title
            title = work.get('title', [''])[0] if work.get('title') else ""
            
            # Extract authors
            authors = []
            for author in work.get('author', []):
                given = author.get('given', '')
                family = author.get('family', '')
                if given and family:
                    authors.append(f"{given} {family}")
                elif family:
                    authors.append(family)
            
            # Extract journal
            journal = work.get('container-title', [''])[0] if work.get('container-title') else ""
            
            # Extract publication date
            pub_date = None
            date_parts = work.get('published-print', {}).get('date-parts', [[]])[0]
            if date_parts and len(date_parts) >= 1:
                year = int(date_parts[0])
                month = int(date_parts[1]) if len(date_parts) > 1 else 1
                day = int(date_parts[2]) if len(date_parts) > 2 else 1
                pub_date = datetime(year, month, day)
            
            # Extract abstract
            abstract = work.get('abstract', '')
            
            # Extract references
            references = []
            for ref in work.get('reference', []):
                ref_doi = ref.get('DOI')
                if ref_doi:
                    references.append(ref_doi)
            
            # Extract license
            license_info = work.get('license', [{}])[0]
            license_url = license_info.get('URL') if license_info else None
            
            return CrossrefMeta(
                doi=doi,
                title=title,
                authors=authors,
                journal=journal,
                publication_date=pub_date,
                abstract=abstract,
                references=references,
                license=license_url
            )
            
        except Exception as e:
            logger.error(f"Failed to get Crossref metadata for DOI {doi}: {e}")
            return None


class UnpaywallClient:
    """Client for Unpaywall API."""
    
    def __init__(self, email: str = None):
        self.base_url = "https://api.unpaywall.org/v2"
        self.email = email or "ncfd@example.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': f'NCFD-Unpaywall-Client/1.0 ({self.email})'
        })
    
    def get_oa_status(self, doi: str) -> Optional[OARecord]:
        """
        Get open access status for a DOI.
        
        Args:
            doi: Digital Object Identifier
            
        Returns:
            Open access information
        """
        try:
            url = f"{self.base_url}/{doi}"
            params = {'email': self.email}
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            is_oa = data.get('is_oa', False)
            oa_status = data.get('oa_status', 'unknown')
            
            # Get best OA location
            best_oa_location = data.get('best_oa_location', {})
            pmc_url = best_oa_location.get('url_for_pdf') if best_oa_location else None
            
            # Look for PMC URL specifically
            if not pmc_url:
                for location in data.get('oa_locations', []):
                    if 'pmc' in location.get('url', '').lower():
                        pmc_url = location.get('url')
                        break
            
            return OARecord(
                doi=doi,
                is_oa=is_oa,
                oa_status=oa_status,
                best_oa_location=best_oa_location,
                pmc_url=pmc_url
            )
            
        except Exception as e:
            logger.error(f"Failed to get Unpaywall data for DOI {doi}: {e}")
            return None


class LiteratureIngester:
    """Main literature ingestion orchestrator."""
    
    def __init__(self, db_session: Session, config: Dict[str, Any] = None):
        self.db_session = db_session
        self.config = config or get_config().get('literature_ingestion', {})
        
        # Initialize clients
        self.pubmed_client = PubMedClient(
            email=self.config.get('pubmed_email'),
            api_key=self.config.get('pubmed_api_key')
        )
        self.pmc_client = PMCClient()
        self.crossref_client = CrossrefClient(
            email=self.config.get('crossref_email')
        )
        self.unpaywall_client = UnpaywallClient(
            email=self.config.get('unpaywall_email')
        )
        
        logger.info("Literature ingester initialized")
    
    def ingest_trial_literature(self, nct_id: str, max_pubs: int = 50) -> Dict[str, Any]:
        """
        Main method: ingest all literature for a clinical trial.
        
        Args:
            nct_id: Clinical trial identifier
            max_pubs: Maximum number of publications to process
            
        Returns:
            Summary of ingestion results
        """
        logger.info(f"Starting literature ingestion for trial: {nct_id}")
        
        results = {
            'nct_id': nct_id,
            'publications_found': 0,
            'publications_processed': 0,
            'fulltext_retrieved': 0,
            'documents_created': 0,
            'errors': []
        }
        
        try:
            # Step 1: Search PubMed for publications about this trial
            publications = self.pubmed_client.search_by_nct(nct_id, max_pubs)
            results['publications_found'] = len(publications)
            
            logger.info(f"Found {len(publications)} publications for trial {nct_id}")
            
            # Step 2: Process each publication
            for pub in publications:
                try:
                    self._process_publication(pub, nct_id)
                    results['publications_processed'] += 1
                except Exception as e:
                    error_msg = f"Failed to process publication {pub.pmid}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
                    continue
            
            logger.info(f"Completed literature ingestion for trial {nct_id}")
            return results
            
        except Exception as e:
            error_msg = f"Literature ingestion failed for trial {nct_id}: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
            return results
    
    def ingest_drug_literature(self, drug_name: str, max_pubs: int = 100) -> Dict[str, Any]:
        """
        Main method: ingest all literature for a specific drug.
        
        Args:
            drug_name: Drug name (e.g., "Ruxolitinib")
            max_pubs: Maximum number of publications to process
            
        Returns:
            Summary of ingestion results
        """
        logger.info(f"Starting literature ingestion for drug: {drug_name}")
        
        results = {
            'drug_name': drug_name,
            'publications_found': 0,
            'publications_processed': 0,
            'fulltext_retrieved': 0,
            'documents_created': 0,
            'errors': []
        }
        
        try:
            # Step 1: Search PubMed for publications about this drug
            publications = self.pubmed_client.search_by_drug(drug_name, max_pubs)
            results['publications_found'] = len(publications)
            
            logger.info(f"Found {len(publications)} publications for drug {drug_name}")
            
            # Step 2: Process each publication
            for pub in publications:
                try:
                    self._process_publication_for_drug(pub, drug_name)
                    results['publications_processed'] += 1
                except Exception as e:
                    error_msg = f"Failed to process publication {pub.pmid}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
                    continue
            
            logger.info(f"Completed literature ingestion for drug {drug_name}")
            return results
            
        except Exception as e:
            error_msg = f"Literature ingestion failed for drug {drug_name}: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
            return results
    
    def _process_publication_for_drug(self, pub: PubRecord, drug_name: str) -> None:
        """Process a single publication for drug literature and store in database."""
        
        # Check if document already exists
        existing_doc = self.db_session.query(Document).filter(
            Document.pmid == pub.pmid
        ).first()
        
        if existing_doc:
            logger.info(f"Document already exists for PMID {pub.pmid}")
            return
        
        # Create document record
        doc = Document(
            source_type='Abstract' if pub.abstract else 'Paper',
            source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pub.pmid}/" if pub.pmid else None,
            title=pub.title,
            pmid=pub.pmid,
            pmcid=pub.pmcid,
            doi=pub.doi,
            published_at=pub.publication_date,
            status='discovered',
            discovered_at=datetime.utcnow()
        )
        
        self.db_session.add(doc)
        self.db_session.flush()  # Get the doc_id
        
        # Create citation record
        if pub.pmid or pub.doi:
            citation = DocumentCitation(
                doc_id=doc.doc_id,
                doi=pub.doi,
                pmid=pub.pmid,
                pmcid=pub.pmcid
            )
            self.db_session.add(citation)
        
        # Try to get full text if available
        if pub.pmcid:
            try:
                fulltext_doc = self.pmc_client.fetch_fulltext(pub.pmcid)
                if fulltext_doc:
                    # Store text pages
                    for i, text in enumerate(fulltext_doc.text_pages):
                        text_page = DocumentTextPage(
                            doc_id=doc.doc_id,
                            page_no=i + 1,
                            text=text,
                            char_count=len(text)
                        )
                        self.db_session.add(text_page)
                    # Note: results is not accessible here, this is just for logging
                    logger.info(f"Retrieved full text for PMID {pub.pmid}")
            except Exception as e:
                logger.warning(f"Failed to retrieve full text for PMID {pub.pmid}: {e}")
        
        # Store abstract as text page if no full text
        if not pub.pmcid and pub.abstract:
            text_page = DocumentTextPage(
                doc_id=doc.doc_id,
                page_no=1,
                text=pub.abstract,
                char_count=len(pub.abstract)
            )
            self.db_session.add(text_page)
        
        self.db_session.commit()
        logger.info(f"Created document for PMID {pub.pmid}")
    
    def _process_publication(self, pub: PubRecord, nct_id: str) -> None:
        """Process a single publication and store in database."""
        
        # Check if document already exists
        existing_doc = self.db_session.query(Document).filter(
            Document.pmid == pub.pmid
        ).first()
        
        if existing_doc:
            logger.info(f"Document already exists for PMID {pub.pmid}")
            return
        
        # Create document record
        doc = Document(
            source_type='Abstract' if pub.abstract else 'Paper',
            source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pub.pmid}/" if pub.pmid else None,
            title=pub.title,
            pmid=pub.pmid,
            pmcid=pub.pmcid,
            doi=pub.doi,
            nct_id=nct_id,
            published_at=pub.publication_date,
            status='discovered',
            discovered_at=datetime.utcnow()
        )
        
        self.db_session.add(doc)
        self.db_session.flush()  # Get the doc_id
        
        # Create citation record
        if pub.pmid or pub.doi:
            citation = DocumentCitation(
                doc_id=doc.doc_id,
                doi=pub.doi,
                pmid=pub.pmid,
                pmcid=pub.pmcid,
                nct_id=nct_id
            )
            self.db_session.add(citation)
        
        # Try to get full text if available
        if pub.pmcid:
            try:
                fulltext_doc = self.pmc_client.fetch_fulltext(pub.pmcid)
                if fulltext_doc:
                    # Store text pages
                    for i, text in enumerate(fulltext_doc.text_pages):
                        text_page = DocumentTextPage(
                            doc_id=doc.doc_id,
                            page_no=i + 1,
                            text=text,
                            char_count=len(text)
                        )
                        self.db_session.add(text_page)
                    
                    # Update document status
                    doc.status = 'fetched'
                    doc.fetched_at = datetime.utcnow()
                    doc.storage_uri = fulltext_doc.url
                    doc.content_type = fulltext_doc.content_type
                    
                    logger.info(f"Retrieved fulltext for PMID {pub.pmid}")
                    
            except Exception as e:
                logger.warning(f"Failed to retrieve fulltext for PMID {pub.pmid}: {e}")
        
        # Try to get Crossref metadata if DOI available
        if pub.doi:
            try:
                crossref_meta = self.crossref_client.get_metadata(pub.doi)
                if crossref_meta:
                    # Update document with Crossref metadata
                    doc.title = crossref_meta.title or doc.title
                    doc.published_at = crossref_meta.publication_date or doc.published_at
                    
                    # Check OA status
                    oa_record = self.unpaywall_client.get_oa_status(pub.doi)
                    if oa_record:
                        doc.oa_status = oa_record.oa_status
                        
                        # If PMC URL available, try to get full text
                        if oa_record.pmc_url and not doc.storage_uri:
                            try:
                                # Extract PMC ID from URL
                                pmc_match = re.search(r'PMC\d+', oa_record.pmc_url)
                                if pmc_match:
                                    pmc_id = pmc_match.group(0)
                                    fulltext_doc = self.pmc_client.fetch_fulltext(pmc_id)
                                    if fulltext_doc:
                                        # Store text pages
                                        for i, text in enumerate(fulltext_doc.text_pages):
                                            text_page = DocumentTextPage(
                                                doc_id=doc.doc_id,
                                                page_no=i + 1,
                                                text=text,
                                                char_count=len(text)
                                            )
                                            self.db_session.add(text_page)
                                        
                                        doc.status = 'fetched'
                                        doc.fetched_at = datetime.utcnow()
                                        doc.storage_uri = fulltext_doc.url
                                        doc.content_type = fulltext_doc.content_type
                                        
                                        logger.info(f"Retrieved fulltext via Unpaywall for DOI {pub.doi}")
                            except Exception as e:
                                logger.warning(f"Failed to retrieve fulltext via Unpaywall for DOI {pub.doi}: {e}")
                    
            except Exception as e:
                logger.warning(f"Failed to get Crossref metadata for DOI {pub.doi}: {e}")
        
        # Commit the document
        self.db_session.commit()
        logger.info(f"Stored document for PMID {pub.pmid} (doc_id: {doc.doc_id})")


# Convenience functions as specified in the document

def search_pubmed(query: str, since: str = None) -> List[PubRecord]:
    """Search PubMed with a query string."""
    client = PubMedClient()
    # This is a simplified implementation - in production you'd parse the query
    # and use appropriate PubMed search parameters
    return client.search_by_nct(query) if query.startswith('NCT') else []


def fetch_pmc_fulltext(pmcid: str) -> RetrievedDoc:
    """Fetch PMC fulltext for a given PMCID."""
    client = PMCClient()
    return client.fetch_fulltext(pmcid)


def crossref_meta(doi: str) -> CrossrefMeta:
    """Get metadata from Crossref for a DOI."""
    client = CrossrefClient()
    return client.get_metadata(doi)


def unpaywall_oa(doi: str) -> OARecord:
    """Get open access information from Unpaywall for a DOI."""
    client = UnpaywallClient()
    return client.get_oa_status(doi)


def europe_pmc_search(query: str) -> List[PubRecord]:
    """Search Europe PMC (alternative to PubMed)."""
    # TODO: Implement Europe PMC search
    logger.info("Europe PMC search not yet implemented")
    return []
