"""
CROcashi Pipeline Orchestrator

This module orchestrates the complete workflow:
1. Filter CT.gov trials for public companies
2. Run literature review pipeline on filtered companies
3. Coordinate asset extraction and linking
4. Prepare data for LLM analysis and red flag detection

The orchestrator maintains the original CT.gov data while creating
filtered subsets for investment analysis.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text

from ncfd.db.models import (
    Trial, Company, Security, CompanyAlias, Asset, Document, DocumentLink
)
from ncfd.ingest.document_ingest import DocumentIngester
from ncfd.extract.asset_extractor import extract_all_entities
from ncfd.mapping.resolver_service import ResolverService

logger = logging.getLogger(__name__)


@dataclass
class CompanyFilter:
    """Configuration for company filtering."""
    min_market_cap: float = 100_000_000  # $100M minimum
    max_market_cap: Optional[float] = None  # No upper limit
    exchanges: List[str] = None  # Default to all US exchanges
    exclude_countries: List[str] = None  # Countries to exclude
    min_trial_count: int = 1  # Minimum trials for company inclusion
    include_private: bool = False  # Whether to include private companies
    
    def __post_init__(self):
        if self.exchanges is None:
            self.exchanges = ['NASDAQ', 'NYSE', 'NYSE American']
        if self.exclude_countries is None:
            self.exclude_countries = ['CN', 'HK']  # Exclude China/Hong Kong


@dataclass
class PipelineConfig:
    """Configuration for the literature review pipeline."""
    max_documents_per_company: int = 100
    max_total_documents: int = 1000
    discovery_batch_size: int = 50
    fetch_batch_size: int = 25
    parse_batch_size: int = 25
    link_batch_size: int = 25
    rate_limit_delay: float = 1.0  # seconds between requests
    enable_storage: bool = True
    enable_parallel_processing: bool = False


@dataclass
class PipelineResult:
    """Result of a pipeline execution."""
    execution_id: str
    start_time: datetime
    end_time: datetime
    companies_processed: int
    trials_filtered: int
    documents_discovered: int
    documents_fetched: int
    documents_parsed: int
    documents_linked: int
    assets_extracted: int
    links_created: int
    errors: List[str]
    warnings: List[str]


class CROcashiOrchestrator:
    """
    Main orchestrator for the CROcashi pipeline.
    
    Coordinates the complete workflow from CT.gov trial filtering
    through literature review and asset extraction.
    """
    
    def __init__(self, db_session: Session, config: PipelineConfig = None):
        """
        Initialize the orchestrator.
        
        Args:
            db_session: Database session
            config: Pipeline configuration
        """
        self.db_session = db_session
        self.config = config or PipelineConfig()
        
        # Initialize components
        self.document_ingester = DocumentIngester(db_session)
        self.resolver_service = ResolverService(db_session)
        
        # Pipeline state
        self.execution_id = None
        self.current_company = None
        self.pipeline_stats = {
            'companies_processed': 0,
            'trials_filtered': 0,
            'documents_discovered': 0,
            'documents_fetched': 0,
            'documents_parsed': 0,
            'documents_linked': 0,
            'assets_extracted': 0,
            'links_created': 0
        }
        
        logger.info("CROcashi Orchestrator initialized")
    
    def run_complete_pipeline(self, 
                            company_filter: CompanyFilter = None,
                            dry_run: bool = False) -> PipelineResult:
        """
        Run the complete CROcashi pipeline.
        
        Args:
            company_filter: Company filtering criteria
            dry_run: If True, only analyze without making changes
            
        Returns:
            Pipeline execution results
        """
        start_time = datetime.now()
        self.execution_id = f"pipeline_{start_time.strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"Starting complete pipeline execution: {self.execution_id}")
        
        try:
            # Step 1: Filter CT.gov trials for public companies
            logger.info("Step 1: Filtering CT.gov trials for public companies")
            filtered_companies = self._filter_companies_for_investment(company_filter)
            
            if not filtered_companies:
                logger.warning("No companies found matching investment criteria")
                return self._create_pipeline_result(start_time, "No companies found")
            
            logger.info(f"Found {len(filtered_companies)} companies matching criteria")
            
            if dry_run:
                logger.info("Dry run mode - analysis complete")
                return self._create_pipeline_result(start_time, "Dry run completed")
            
            # Step 2: Run literature review pipeline for filtered companies
            logger.info("Step 2: Running literature review pipeline")
            self._run_literature_review_pipeline(filtered_companies)
            
            # Step 3: Extract and link assets from documents
            logger.info("Step 3: Extracting and linking assets")
            self._extract_and_link_assets()
            
            # Step 4: Prepare data for LLM analysis (hook for future)
            logger.info("Step 4: Preparing data for LLM analysis")
            self._prepare_llm_analysis_data()
            
            # Step 5: Generate company dossiers (hook for future)
            logger.info("Step 5: Generating company dossiers")
            self._generate_company_dossiers()
            
            logger.info(f"Pipeline execution completed successfully: {self.execution_id}")
            return self._create_pipeline_result(start_time, "Success")
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            return self._create_pipeline_result(start_time, f"Failed: {e}")
    
    def _filter_companies_for_investment(self, 
                                       company_filter: CompanyFilter = None) -> List[Company]:
        """
        Filter companies based on investment criteria.
        
        Args:
            company_filter: Filtering criteria
            
        Returns:
            List of companies meeting investment criteria
        """
        if company_filter is None:
            company_filter = CompanyFilter()
        
        logger.info(f"Filtering companies with criteria: {company_filter}")
        
        # Build base query for companies with trials
        query = self.db_session.query(Company).join(
            Trial, Company.company_id == Trial.sponsor_company_id
        ).join(
            Security, Company.company_id == Security.company_id
        )
        
        # Apply market cap filters
        if company_filter.min_market_cap:
            query = query.filter(Security.market_cap >= company_filter.min_market_cap)
        
        if company_filter.max_market_cap:
            query = query.filter(Security.market_cap <= company_filter.max_market_cap)
        
        # Apply exchange filters
        if company_filter.exchanges:
            query = query.filter(Security.exchange.in_(company_filter.exchanges))
        
        # Apply country exclusions
        if company_filter.exclude_countries:
            query = query.filter(~Company.country_incorp.in_(company_filter.exclude_countries))
            query = query.filter(~Company.hq_country.in_(company_filter.exclude_countries))
        
        # Apply trial count filter
        if company_filter.min_trial_count > 1:
            # Subquery to count trials per company
            trial_counts = self.db_session.query(
                Trial.sponsor_company_id,
                text('COUNT(*) as trial_count')
            ).group_by(Trial.sponsor_company_id).subquery()
            
            query = query.join(
                trial_counts,
                Company.company_id == trial_counts.c.sponsor_company_id
            ).filter(trial_counts.c.trial_count >= company_filter.min_trial_count)
        
        # Get unique companies
        companies = query.distinct().all()
        
        # Additional filtering for private companies
        if not company_filter.include_private:
            companies = [c for c in companies if c.is_public]
        
        # Update pipeline stats
        self.pipeline_stats['companies_processed'] = len(companies)
        
        # Log filtering results
        logger.info(f"Company filtering results:")
        logger.info(f"  - Total companies with trials: {len(companies)}")
        logger.info(f"  - Market cap range: ${company_filter.min_market_cap:,} - {company_filter.max_market_cap or 'unlimited'}")
        logger.info(f"  - Exchanges: {', '.join(company_filter.exchanges)}")
        logger.info(f"  - Excluded countries: {', '.join(company_filter.exclude_countries)}")
        
        return companies
    
    def _run_literature_review_pipeline(self, companies: List[Company]) -> None:
        """
        Run the literature review pipeline for filtered companies.
        
        Args:
            companies: List of companies to process
        """
        logger.info(f"Running literature review pipeline for {len(companies)} companies")
        
        total_documents = 0
        
        for i, company in enumerate(companies):
            self.current_company = company
            logger.info(f"Processing company {i+1}/{len(companies)}: {company.name}")
            
            try:
                # Get company domains for PR/IR discovery
                company_domains = self._get_company_domains(company)
                
                if not company_domains:
                    logger.warning(f"No domains found for company: {company.name}")
                    continue
                
                # Run discovery job for this company
                sources = self.document_ingester.run_discovery_job(company_domains)
                self.pipeline_stats['documents_discovered'] += len(sources)
                
                if not sources:
                    logger.info(f"No documents discovered for {company.name}")
                    continue
                
                # Limit documents per company
                max_docs = min(len(sources), self.config.max_documents_per_company)
                sources = sources[:max_docs]
                
                # Run fetch job
                fetched_docs = self.document_ingester.run_fetch_job(
                    sources, 
                    max_docs=max_docs
                )
                self.pipeline_stats['documents_fetched'] += len(fetched_docs)
                
                if not fetched_docs:
                    logger.info(f"No documents fetched for {company.name}")
                    continue
                
                # Run parse job
                parsed_docs = self.document_ingester.run_parse_job(fetched_docs)
                self.pipeline_stats['documents_parsed'] += len(parsed_docs)
                
                if not parsed_docs:
                    logger.info(f"No documents parsed for {company.name}")
                    continue
                
                # Run link job
                linked_docs = self.document_ingester.run_link_job(parsed_docs)
                self.pipeline_stats['documents_linked'] += len(linked_docs)
                
                total_documents += len(linked_docs)
                
                # Rate limiting between companies
                if i < len(companies) - 1:
                    time.sleep(self.config.rate_limit_delay)
                
            except Exception as e:
                logger.error(f"Error processing company {company.name}: {e}")
                continue
        
        logger.info(f"Literature review pipeline completed: {total_documents} documents processed")
    
    def _get_company_domains(self, company: Company) -> List[str]:
        """
        Extract company domains for document discovery.
        
        Args:
            company: Company to extract domains for
            
        Returns:
            List of company domains
        """
        domains = []
        
        # Check if company has website in metadata
        if hasattr(company, 'metadata') and company.metadata:
            website = company.metadata.get('website')
            if website:
                domains.append(website)
        
        # Check company aliases for domain-like patterns
        aliases = self.db_session.query(CompanyAlias).filter(
            CompanyAlias.company_id == company.company_id
        ).all()
        
        for alias in aliases:
            alias_text = alias.alias_text
            if '.' in alias_text and any(tld in alias_text for tld in ['.com', '.org', '.net']):
                domains.append(alias_text)
        
        # Remove duplicates and normalize
        unique_domains = list(set(domains))
        normalized_domains = []
        
        for domain in unique_domains:
            if not domain.startswith('http'):
                domain = f"https://{domain}"
            normalized_domains.append(domain)
        
        logger.info(f"Found {len(normalized_domains)} domains for {company.name}")
        return normalized_domains
    
    def _extract_and_link_assets(self) -> None:
        """
        Extract assets from documents and create links.
        
        This method processes all documents to extract asset codes,
        drug names, and create comprehensive entity links.
        """
        logger.info("Extracting and linking assets from documents")
        
        # Get all documents that have been parsed but not fully processed
        documents = self.db_session.query(Document).filter(
            Document.status == 'parsed'
        ).all()
        
        logger.info(f"Processing {len(documents)} documents for asset extraction")
        
        for doc in documents:
            try:
                # Extract entities from document text
                entities = self._extract_entities_from_document(doc)
                self.pipeline_stats['assets_extracted'] += len(entities)
                
                # Create asset links
                links_created = self._create_asset_links(doc, entities)
                self.pipeline_stats['links_created'] += links_created
                
                # Update document status
                doc.status = 'processed'
                
            except Exception as e:
                logger.error(f"Error processing document {doc.doc_id}: {e}")
                doc.status = 'error'
                continue
        
        self.db_session.commit()
        logger.info(f"Asset extraction completed: {self.pipeline_stats['assets_extracted']} entities, {self.pipeline_stats['links_created']} links")
    
    def _extract_entities_from_document(self, doc: Document) -> List[Dict[str, Any]]:
        """
        Extract entities from a document.
        
        Args:
            doc: Document to extract entities from
            
        Returns:
            List of extracted entities
        """
        entities = []
        
        # Get document text pages
        text_pages = self.db_session.query(DocumentTextPage).filter(
            DocumentTextPage.doc_id == doc.doc_id
        ).all()
        
        for page in text_pages:
            if page.text_content:
                # Extract all entity types
                asset_matches = extract_all_entities(
                    page.text_content, 
                    page_no=page.page_no,
                    source_document_id=str(doc.doc_id)
                )
                
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
                        'confidence': match.confidence,
                        'source_document_id': doc.doc_id
                    }
                    entities.append(entity)
        
        return entities
    
    def _create_asset_links(self, doc: Document, entities: List[Dict[str, Any]]) -> int:
        """
        Create asset links for extracted entities.
        
        Args:
            doc: Document containing entities
            entities: List of extracted entities
            
        Returns:
            Number of links created
        """
        links_created = 0
        
        for entity in entities:
            try:
                # Get or create asset
                asset = self._get_or_create_asset(entity)
                
                # Create document link
                link = DocumentLink(
                    doc_id=doc.doc_id,
                    asset_id=asset.asset_id,
                    link_type=f"{entity['alias_type']}_extraction",
                    confidence=entity.get('confidence', 0.8),
                    metadata={
                        'extraction_method': entity['detector'],
                        'page_no': entity['page_no'],
                        'char_start': entity['char_start'],
                        'char_end': entity['char_end'],
                        'pipeline_execution_id': self.execution_id
                    }
                )
                
                self.db_session.add(link)
                links_created += 1
                
            except Exception as e:
                logger.error(f"Error creating link for entity {entity}: {e}")
                continue
        
        return links_created
    
    def _get_or_create_asset(self, entity: Dict[str, Any]) -> Asset:
        """
        Get existing asset or create new one.
        
        Args:
            entity: Entity data
            
        Returns:
            Asset instance
        """
        # Look for existing asset by normalized value
        existing_asset = self.db_session.query(Asset).join(
            AssetAlias, Asset.asset_id == AssetAlias.asset_id
        ).filter(
            AssetAlias.alias_norm == entity['value_norm']
        ).first()
        
        if existing_asset:
            return existing_asset
        
        # Create new asset
        asset = Asset(
            names_jsonb={
                'primary_name': entity['value_text'],
                'normalized_name': entity['value_norm'],
                'discovery_source': 'pipeline_extraction',
                'pipeline_execution_id': self.execution_id
            }
        )
        
        self.db_session.add(asset)
        self.db_session.flush()
        
        # Create initial alias
        alias = AssetAlias(
            asset_id=asset.asset_id,
            alias_text=entity['value_text'],
            alias_norm=entity['value_norm'],
            alias_type=entity['alias_type'],
            confidence=entity.get('confidence', 0.8),
            source='pipeline_extraction'
        )
        
        self.db_session.add(alias)
        
        return asset
    
    def _prepare_llm_analysis_data(self) -> None:
        """
        Prepare data for LLM analysis.
        
        This is a hook for future implementation of LLM-based
        red flag detection and analysis.
        """
        logger.info("Preparing data for LLM analysis (hook for future implementation)")
        
        # TODO: Implement LLM data preparation
        # - Aggregate company trial data
        # - Prepare document summaries
        # - Create analysis prompts
        # - Set up LLM service integration
        
        pass
    
    def _generate_company_dossiers(self) -> None:
        """
        Generate comprehensive company dossiers.
        
        This is a hook for future implementation of dossier
        generation and report creation.
        """
        logger.info("Generating company dossiers (hook for future implementation)")
        
        # TODO: Implement dossier generation
        # - Compile company trial summaries
        # - Aggregate literature findings
        # - Generate risk assessments
        # - Create investment recommendations
        
        pass
    
    def _create_pipeline_result(self, start_time: datetime, status: str) -> PipelineResult:
        """
        Create pipeline result summary.
        
        Args:
            start_time: Pipeline start time
            status: Pipeline execution status
            
        Returns:
            Pipeline result object
        """
        end_time = datetime.now()
        duration = end_time - start_time
        
        return PipelineResult(
            execution_id=self.execution_id or "unknown",
            start_time=start_time,
            end_time=end_time,
            companies_processed=self.pipeline_stats['companies_processed'],
            trials_filtered=0,  # TODO: Implement trial counting
            documents_discovered=self.pipeline_stats['documents_discovered'],
            documents_fetched=self.pipeline_stats['documents_fetched'],
            documents_parsed=self.pipeline_stats['documents_parsed'],
            documents_linked=self.pipeline_stats['documents_linked'],
            assets_extracted=self.pipeline_stats['assets_extracted'],
            links_created=self.pipeline_stats['links_created'],
            errors=[],  # TODO: Implement error tracking
            warnings=[]  # TODO: Implement warning tracking
        )
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """
        Get current pipeline status.
        
        Returns:
            Dictionary with pipeline status information
        """
        return {
            'execution_id': self.execution_id,
            'current_company': self.current_company.name if self.current_company else None,
            'stats': self.pipeline_stats.copy(),
            'config': {
                'max_documents_per_company': self.config.max_documents_per_company,
                'max_total_documents': self.config.max_total_documents,
                'rate_limit_delay': self.config.rate_limit_delay
            }
        }
    
    def reset_pipeline_stats(self) -> None:
        """Reset pipeline statistics."""
        self.pipeline_stats = {
            'companies_processed': 0,
            'trials_filtered': 0,
            'documents_discovered': 0,
            'documents_fetched': 0,
            'documents_parsed': 0,
            'documents_linked': 0,
            'assets_extracted': 0,
            'links_created': 0
        }
        logger.info("Pipeline statistics reset")


# Convenience functions for common use cases

def run_investment_filtered_pipeline(db_session: Session,
                                   min_market_cap: float = 100_000_000,
                                   exchanges: List[str] = None,
                                   max_documents: int = 1000) -> PipelineResult:
    """
    Convenience function to run pipeline with common investment filters.
    
    Args:
        db_session: Database session
        min_market_cap: Minimum market cap in USD
        exchanges: List of exchanges to include
        max_documents: Maximum documents to process
        
    Returns:
        Pipeline execution results
    """
    if exchanges is None:
        exchanges = ['NASDAQ', 'NYSE', 'NYSE American']
    
    company_filter = CompanyFilter(
        min_market_cap=min_market_cap,
        exchanges=exchanges,
        exclude_countries=['CN', 'HK']
    )
    
    config = PipelineConfig(
        max_total_documents=max_documents,
        max_documents_per_company=100
    )
    
    orchestrator = CROcashiOrchestrator(db_session, config)
    return orchestrator.run_complete_pipeline(company_filter)


def run_company_specific_pipeline(db_session: Session,
                                company_ids: List[int],
                                max_documents_per_company: int = 100) -> PipelineResult:
    """
    Run pipeline for specific companies.
    
    Args:
        db_session: Database session
        company_ids: List of company IDs to process
        max_documents_per_company: Maximum documents per company
        
    Returns:
        Pipeline execution results
    """
    config = PipelineConfig(
        max_documents_per_company=max_documents_per_company
    )
    
    orchestrator = CROcashiOrchestrator(db_session, config)
    
    # Get companies by ID
    companies = db_session.query(Company).filter(
        Company.company_id.in_(company_ids)
    ).all()
    
    if not companies:
        raise ValueError(f"No companies found with IDs: {company_ids}")
    
    # Run pipeline for specific companies
    return orchestrator._run_literature_review_pipeline(companies)
