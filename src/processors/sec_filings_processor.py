"""
SEC EDGAR 8-K Filings processor for extracting company, drug, and filing data.

Extracts:
- SECFiling entity (8-K filing with metadata)
- Company entity (filer)
- Drug entities (from structured Item 8.01 and text search)
- Financial metrics (cash position, runway)
"""
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from database.models import Drug
from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, RelationshipExtraction
)

logger = logging.getLogger(__name__)

# Keywords that indicate program terminations in SEC 8-K filings
TERMINATION_KEYWORDS = [
    'discontinue', 'discontinued', 'termination', 'terminated',
    'clinical hold', 'clinical trial halt', 'program stopped',
    'cease development', 'no longer pursuing', 'halt development',
    'stop development', 'abandon', 'abandoned', 'withdraw', 'withdrawn'
]


class SECFilingsProcessor(BaseProcessor):
    """
    Processor for SEC EDGAR 8-K filings.
    
    SEC 8-K filings provide:
    - Company information (filer CIK and name)
    - Filing metadata (accession number, filing date, form type)
    - Structured items (Item 8.01 for pipeline updates)
    - Full text for drug name extraction
    - Financial metrics (cash position, runway)
    """
    
    SOURCE_NAME = "sec_edgar"
    
    def __init__(self, session: Session):
        """Initialize SEC filings processor."""
        super().__init__(session)
        self._drug_names_cache: Optional[Set[str]] = None
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get accession number from SEC filing data."""
        return raw_data.get('accession_number', raw_data.get('accessionNumber', ''))
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from SEC 8-K filing."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'filings': [],  # Will be converted to 'filing' (singular) by pipeline
            'companies': [],
            'drugs': [],
            'regulatory_events': []
        }
        
        try:
            # Extract filing entity
            filing = self._extract_filing(raw_data)
            if filing:
                entities['filings'].append(filing)
                self.metrics.entities_extracted += 1
            
            # Extract company (filer)
            company = self._extract_company(raw_data)
            if company:
                entities['companies'].append(company)
                self.metrics.entities_extracted += 1
            
            # Extract drugs from structured Item 8.01
            drugs_structured = self._extract_drugs_structured(raw_data)
            entities['drugs'].extend(drugs_structured)
            self.metrics.entities_extracted += len(drugs_structured)
            
            # Extract drugs from text search
            drugs_text = self._extract_drugs_text_search(raw_data)
            entities['drugs'].extend(drugs_text)
            self.metrics.entities_extracted += len(drugs_text)
            
            # Detect program terminations and create regulatory events
            terminations = self._detect_program_terminations(raw_data)
            entities['regulatory_events'].extend(terminations)
            self.metrics.entities_extracted += len(terminations)
            
        except Exception as e:
            logger.error(f"Error extracting SEC filing data: {e}")
            self.add_error(f"Extraction error: {e}")
        
        self.metrics.end_time = datetime.now()
        return entities
    
    def extract_relationships(
        self,
        raw_data: Dict[str, Any],
        resolved_entities: Dict[str, UUID],
        id_to_entity: Dict[UUID, ExtractedEntity]
    ) -> List[RelationshipExtraction]:
        """Extract relationships after entities are resolved."""
        relationships = []
        
        filing_id = resolved_entities.get('filing')
        # Handle both 'company' (singular) and 'companies' (plural) keys
        company_id = resolved_entities.get('company')
        if not company_id:
            # Try plural form (for non-ClinicalTrials sources)
            companies = resolved_entities.get('companies', [])
            if isinstance(companies, list) and len(companies) > 0:
                company_id = companies[0]
            elif isinstance(companies, UUID):
                company_id = companies
        
        # Filing-company relationship (filer)
        if filing_id and company_id:
            filing_entity = id_to_entity.get(filing_id)
            company_entity = id_to_entity.get(company_id)
            if filing_entity and company_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='filing_company',
                    source_entity=filing_entity,
                    target_entity=company_entity,
                    attributes={},
                    temporal={}
                ))
        
        # Filing-drug relationships
        if filing_id:
            filing_entity = id_to_entity.get(filing_id)
            if filing_entity:
                for drug_id in resolved_entities.get('drugs', []):
                    drug_entity = id_to_entity.get(drug_id)
                    if drug_entity:
                        # Get mention_type from drug entity context
                        mention_type = drug_entity.context.get('mention_type', 'pipeline_update')
                        
                        relationships.append(RelationshipExtraction(
                            relationship_type='filing_drug',
                            source_entity=filing_entity,
                            target_entity=drug_entity,
                            attributes={
                                'mention_type': mention_type
                            },
                            temporal={}
                        ))
        
        # Regulatory event relationships for terminations
        event_ids = resolved_entities.get('regulatory_events', [])
        if isinstance(event_ids, UUID):
            event_ids = [event_ids]
        elif not isinstance(event_ids, list):
            event_ids = []
        
        for event_id in event_ids:
            event_entity = id_to_entity.get(event_id)
            if not event_entity:
                continue
            
            # Link termination event to company
            if company_id:
                company_entity = id_to_entity.get(company_id)
                if company_entity:
                    relationships.append(RelationshipExtraction(
                        relationship_type='regulatory_company_event',
                        source_entity=event_entity,
                        target_entity=company_entity,
                        attributes={},
                        temporal={}
                    ))
            
            # Link termination event to terminated drugs
            for drug_id in resolved_entities.get('drugs', []):
                drug_entity = id_to_entity.get(drug_id)
                if drug_entity:
                    # Only link if drug was mentioned in termination context
                    mention_type = drug_entity.context.get('mention_type', '')
                    if mention_type == 'termination':
                        relationships.append(RelationshipExtraction(
                            relationship_type='regulatory_drug_event',
                            source_entity=event_entity,
                            target_entity=drug_entity,
                            attributes={},
                            temporal={}
                        ))
        
        return relationships
    
    def _extract_filing(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract SECFiling entity from raw data."""
        accession_number = raw_data.get('accession_number', raw_data.get('accessionNumber', ''))
        if not accession_number:
            logger.warning("No accession number found in SEC filing")
            return None
        
        filing_type = raw_data.get('form', '8-K')
        filing_date_str = raw_data.get('filing_date', raw_data.get('filingDate', ''))
        company_name = raw_data.get('company_name', 'Unknown Company')
        
        # Parse filing date (CRITICAL: filing_date is nullable=False in database)
        filing_date = None
        if filing_date_str:
            try:
                filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                try:
                    filing_date = datetime.strptime(filing_date_str, '%Y%m%d').date()
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse filing date: {filing_date_str}")
        
        # CRITICAL: filing_date is required (nullable=False)
        # If we can't parse it, we cannot create the entity
        if not filing_date:
            logger.error(f"Cannot create SECFiling without filing_date. Accession: {accession_number}")
            return None
        
        # Parse 8-K items from full_text if available
        full_text = raw_data.get('full_text', '')
        items = self._parse_8k_items(raw_data)
        
        # Extract financial metrics
        financial_metrics = self._extract_financial_metrics(raw_data)
        
        # Determine if filing mentions milestones or restructuring
        mentions_milestones = self._check_mentions_milestones(items, full_text)
        mentions_restructuring = self._check_mentions_restructuring(items, full_text)
        
        # Extract terminated program names from context (if terminations were detected)
        # Note: terminations are detected in extract_entities(), so we extract from items/full_text here
        terminated_programs = self._extract_terminated_program_names(items, full_text)
        
        # Create filing name
        filing_name = f"{filing_type} - {accession_number}"
        if filing_date:
            filing_name = f"{company_name} {filing_type} {filing_date}"
        
        filing = ExtractedEntity(
            entity_type=EntityType.SEC_FILING,
            name=filing_name,
            identifiers={
                'accession_number': accession_number
            },
            context={
                'filing_type': filing_type,
                'filing_date': filing_date,
                'filing_url': raw_data.get('filing_url', ''),
                'full_text': full_text[:50000] if full_text else None,  # Truncate if too long
                'mentions_milestones': mentions_milestones,
                'mentions_restructuring': mentions_restructuring,
                'mentions_programs': terminated_programs,  # Store terminated program names
                'cash_position': financial_metrics.get('cash_position'),
                'runway_months': financial_metrics.get('runway_months'),
                'items': items
            },
            source_name=self.SOURCE_NAME,
            source_identifier=accession_number,
            raw_data=raw_data
        )
        
        return filing
    
    def _extract_company(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract company (filer) from SEC filing data."""
        company_name = raw_data.get('company_name', '')
        cik = raw_data.get('cik', '')
        
        if not company_name:
            logger.warning("No company name found in SEC filing")
            return None
        
        # Normalize company name
        company_name = self.normalize_company_name(company_name)
        
        company = ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={
                'cik': cik
            } if cik else {},
            context={
                'role': 'filer',
                'cik': cik
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'company_name': company_name, 'cik': cik}
        )
        
        return company
    
    def _extract_drugs_structured(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract drugs from Item 8.01 (Other Events) section."""
        drugs = []
        
        items = self._parse_8k_items(raw_data)
        item_801 = items.get('8.01', '')
        
        if not item_801:
            return drugs
        
        # Look for drug names in Item 8.01
        # This is a simple pattern - can be enhanced with NLP
        # For now, we'll rely on text search for drug names
        
        return drugs
    
    def _extract_drugs_text_search(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract drugs by searching full text for known drug names."""
        drugs = []
        
        full_text = raw_data.get('full_text', '')
        if not full_text:
            return drugs
        
        # Get all drug names from database
        drug_names = self._get_all_drug_names()
        if not drug_names:
            logger.warning("No drug names found in database for text search")
            return drugs
        
        logger.debug(f"Searching SEC filing text for {len(drug_names)} drug names")
        
        # Search for drug mentions
        drug_mentions = self._search_drug_names_in_text(full_text, drug_names)
        
        logger.debug(f"Found {len(drug_mentions)} drug mentions in SEC filing")
        
        for drug_name, mention_type, context_text in drug_mentions:
            # Normalize drug name
            normalized_name = self.normalize_drug_name(drug_name)
            
            drug = ExtractedEntity(
                entity_type=EntityType.DRUG,
                name=normalized_name,
                identifiers={},
                context={
                    'mention_type': mention_type,
                    'item': 'text',
                    'context_text': context_text[:500] if context_text else None  # Truncate context
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'drug_name': drug_name, 'mention_type': mention_type}
            )
            
            drugs.append(drug)
        
        return drugs
    
    def _extract_financial_metrics(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract financial metrics from filing."""
        metrics = {
            'cash_position': None,
            'runway_months': None
        }
        
        full_text = raw_data.get('full_text', '')
        items = self._parse_8k_items(raw_data)
        item_202 = items.get('2.02', '')
        
        # Search for cash position
        text_to_search = item_202 + ' ' + full_text if item_202 else full_text
        
        # Pattern for cash position: "$X million", "$X.XB", etc.
        cash_patterns = [
            r'\$[\d,]+\.?\d*\s*(?:million|billion|M|B|thousand|K)',
            r'cash\s+(?:and\s+)?(?:cash\s+)?equivalents?\s+(?:of\s+)?\$?[\d,]+\.?\d*\s*(?:million|billion|M|B)?',
            r'cash\s+position\s+(?:of\s+)?\$?[\d,]+\.?\d*\s*(?:million|billion|M|B)?'
        ]
        
        for pattern in cash_patterns:
            matches = re.finditer(pattern, text_to_search, re.IGNORECASE)
            for match in matches:
                cash_text = match.group(0)
                # Extract numeric value (simplified)
                numbers = re.findall(r'[\d,]+\.?\d*', cash_text)
                if numbers:
                    try:
                        value = float(numbers[0].replace(',', ''))
                        # Check for million/billion multiplier
                        if 'billion' in cash_text.lower() or 'B' in cash_text.upper():
                            value *= 1000
                        metrics['cash_position'] = value
                        break
                    except (ValueError, IndexError):
                        continue
            if metrics['cash_position']:
                break
        
        # Search for runway/burn rate
        runway_patterns = [
            r'cash\s+runway\s+(?:of\s+)?(\d+)\s+months?',
            r'burn\s+rate.*?(\d+)\s+months?',
            r'runway\s+(?:of\s+)?(\d+)\s+months?'
        ]
        
        for pattern in runway_patterns:
            matches = re.finditer(pattern, text_to_search, re.IGNORECASE)
            for match in matches:
                try:
                    months = int(match.group(1))
                    metrics['runway_months'] = months
                    break
                except (ValueError, IndexError):
                    continue
            if metrics['runway_months']:
                break
        
        return metrics
    
    def _parse_8k_items(self, raw_data: Dict[str, Any]) -> Dict[str, str]:
        """Parse 8-K items from filing text."""
        items = {}
        
        full_text = raw_data.get('full_text', '')
        if not full_text:
            return items
        
        # Pattern to match 8-K items: "Item 8.01", "ITEM 8.01", etc.
        item_pattern = r'Item\s+(\d+\.\d+)[\s:]+(.*?)(?=Item\s+\d+\.\d+|$)'
        
        matches = re.finditer(item_pattern, full_text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            item_number = match.group(1)
            item_content = match.group(2).strip()
            items[item_number] = item_content
        
        return items
    
    def _check_mentions_milestones(self, items: Dict[str, str], full_text: str) -> bool:
        """Check if filing mentions milestones."""
        milestone_keywords = ['milestone', 'achievement', 'approval', 'breakthrough', 'success']
        
        # Check Item 8.01
        item_801 = items.get('8.01', '')
        if any(keyword in item_801.lower() for keyword in milestone_keywords):
            return True
        
        # Check full text
        if any(keyword in full_text.lower() for keyword in milestone_keywords):
            return True
        
        return False
    
    def _check_mentions_restructuring(self, items: Dict[str, str], full_text: str) -> bool:
        """Check if filing mentions restructuring."""
        restructuring_keywords = ['restructuring', 'layoff', 'reduction', 'workforce', 'reorganization']
        
        # Check Item 2.05 (Results of Operations)
        item_205 = items.get('2.05', '')
        if any(keyword in item_205.lower() for keyword in restructuring_keywords):
            return True
        
        # Check full text
        if any(keyword in full_text.lower() for keyword in restructuring_keywords):
            return True
        
        return False
    
    def _get_all_drug_names(self) -> Set[str]:
        """Get all drug names from database for text search."""
        if self._drug_names_cache is not None:
            return self._drug_names_cache
        
        drug_names = set()
        
        try:
            # Query all drugs from database
            drugs = self.session.query(Drug).all()
            
            for drug in drugs:
                # Add primary name
                if drug.primary_name:
                    normalized = self.normalize_drug_name(drug.primary_name)
                    drug_names.add(normalized)
                
                # Add generic name
                if drug.generic_name:
                    normalized = self.normalize_drug_name(drug.generic_name)
                    drug_names.add(normalized)
                
                # Add aliases
                if drug.aliases:
                    for alias in drug.aliases:
                        if alias:
                            normalized = self.normalize_drug_name(alias)
                            drug_names.add(normalized)
            
            self._drug_names_cache = drug_names
            logger.info(f"Loaded {len(drug_names)} drug names for text search")
            
        except Exception as e:
            logger.error(f"Error loading drug names from database: {e}")
            drug_names = set()
        
        return drug_names
    
    def _search_drug_names_in_text(
        self,
        text: str,
        drug_names: Set[str]
    ) -> List[Tuple[str, str, str]]:
        """
        Search text for drug names and determine mention type.
        
        Returns:
            List of tuples: (drug_name, mention_type, context_text)
        """
        mentions = []
        
        # Normalize text for searching (lowercase, remove punctuation)
        text_lower = text.lower()
        
        # Search for each drug name
        for drug_name in drug_names:
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(drug_name.lower()) + r'\b'
            matches = list(re.finditer(pattern, text_lower))
            
            if matches:
                # Get context around first mention
                first_match = matches[0]
                start = max(0, first_match.start() - 200)
                end = min(len(text), first_match.end() + 200)
                context_text = text[start:end]
                
                # Determine mention type from context
                mention_type = self._determine_mention_type(context_text)
                
                mentions.append((drug_name, mention_type, context_text))
        
        return mentions
    
    def _determine_mention_type(self, context_text: str) -> str:
        """Determine mention type from context text."""
        context_lower = context_text.lower()
        
        # Check for termination keywords
        termination_keywords = ['terminate', 'discontinue', 'halt', 'stop', 'cease', 'withdraw']
        if any(keyword in context_lower for keyword in termination_keywords):
            return 'termination'
        
        # Check for milestone keywords
        milestone_keywords = ['milestone', 'achievement', 'approval', 'breakthrough', 'success']
        if any(keyword in context_lower for keyword in milestone_keywords):
            return 'milestone'
        
        # Check for licensing keywords
        licensing_keywords = ['license', 'partnership', 'collaboration', 'agreement', 'deal']
        if any(keyword in context_lower for keyword in licensing_keywords):
            return 'licensing'
        
        # Default to pipeline update
        return 'pipeline_update'
    
    def _detect_program_terminations(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """
        Detect program terminations in SEC 8-K filing.
        
        Looks for termination language in Item 8.01 and full text,
        extracts terminated drug/program names, and creates regulatory events.
        
        Returns:
            List of RegulatoryEvent entities for detected terminations
        """
        terminations = []
        
        full_text = raw_data.get('full_text', '')
        items = self._parse_8k_items(raw_data)
        item_801 = items.get('8.01', '')
        
        # Focus on Item 8.01 (Other Events) where terminations are typically announced
        text_to_search = item_801 if item_801 else full_text
        
        if not text_to_search:
            return terminations
        
        text_lower = text_to_search.lower()
        
        # Check if filing contains termination keywords
        has_termination = any(keyword in text_lower for keyword in TERMINATION_KEYWORDS)
        
        if not has_termination:
            return terminations
        
        # Extract termination details
        filing_date_str = raw_data.get('filing_date', raw_data.get('filingDate', ''))
        filing_date = None
        if filing_date_str:
            try:
                filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                try:
                    filing_date = datetime.strptime(filing_date_str, '%Y%m%d').date()
                except (ValueError, TypeError):
                    pass
        
        # If we can't get a date, use current date as fallback
        if not filing_date:
            filing_date = datetime.now().date()
        
        # Try to extract program/drug names from termination context
        # Look for sentences containing termination keywords
        termination_sentences = self._extract_termination_sentences(text_to_search)
        
        if termination_sentences:
            # Extract drug/program names from termination sentences
            drug_names = self._get_all_drug_names()
            for sentence in termination_sentences:
                # Check if sentence mentions any known drugs
                mentioned_drugs = []
                for drug_name in drug_names:
                    if drug_name.lower() in sentence.lower():
                        mentioned_drugs.append(drug_name)
                
                # Create regulatory event for termination
                # Use first mentioned drug as program name, or generic description
                program_name = mentioned_drugs[0] if mentioned_drugs else 'Program'
                termination_reason = self._extract_termination_reason(sentence)
                
                event = ExtractedEntity(
                    entity_type=EntityType.REGULATORY_EVENT,
                    name=f"Program Termination: {program_name}",
                    identifiers={},
                    context={
                        'event_type': 'withdrawal',  # Use 'withdrawal' for voluntary terminations
                        'event_date': filing_date,
                        'regulatory_body': 'FDA',  # Use FDA as regulatory body (constraint requirement)
                        'country': 'US',
                        'description': termination_reason or f"Program termination announced in SEC 8-K filing (source: SEC EDGAR)",
                        'program_name': program_name,
                        'termination_context': sentence[:500],  # Store context
                        'mentioned_drugs': mentioned_drugs
                    },
                    source_name=self.SOURCE_NAME,
                    source_identifier=self.get_source_identifier(raw_data),
                    raw_data={'termination_sentence': sentence, 'filing_date': filing_date_str}
                )
                
                terminations.append(event)
        else:
            # No specific sentences found, but termination keywords present
            # Create generic termination event
            event = ExtractedEntity(
                entity_type=EntityType.REGULATORY_EVENT,
                name="Program Termination (SEC 8-K)",
                identifiers={},
                context={
                    'event_type': 'withdrawal',
                    'event_date': filing_date,
                    'regulatory_body': 'FDA',  # Use FDA as regulatory body (constraint requirement)
                    'country': 'US',
                    'description': 'Program termination mentioned in SEC 8-K filing (source: SEC EDGAR)',
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'filing_date': filing_date_str}
            )
            terminations.append(event)
        
        return terminations
    
    def _extract_termination_sentences(self, text: str) -> List[str]:
        """
        Extract sentences that contain termination keywords.
        
        Returns:
            List of sentences containing termination language
        """
        sentences = []
        
        # Split text into sentences (simple approach)
        # Look for sentence boundaries: . ! ? followed by space and capital letter
        sentence_pattern = r'[.!?]\s+(?=[A-Z])'
        parts = re.split(sentence_pattern, text)
        
        for part in parts:
            part_lower = part.lower()
            # Check if sentence contains termination keywords
            if any(keyword in part_lower for keyword in TERMINATION_KEYWORDS):
                sentences.append(part.strip())
        
        return sentences
    
    def _extract_termination_reason(self, sentence: str) -> Optional[str]:
        """
        Extract reason for termination from sentence.
        
        Looks for common reason phrases like "due to", "because of", etc.
        """
        sentence_lower = sentence.lower()
        
        # Common reason indicators
        reason_patterns = [
            r'due to\s+([^.]{0,200})',
            r'because of\s+([^.]{0,200})',
            r'following\s+([^.]{0,200})',
            r'based on\s+([^.]{0,200})',
        ]
        
        for pattern in reason_patterns:
            match = re.search(pattern, sentence_lower, re.IGNORECASE)
            if match:
                reason = match.group(1).strip()
                if reason:
                    return reason
        
        return None
    
    def _extract_terminated_program_names(self, items: Dict[str, str], full_text: str) -> List[str]:
        """
        Extract terminated program names from filing text.
        
        This is a helper to populate mentions_programs field without
        duplicating the full termination detection logic.
        """
        programs = []
        
        item_801 = items.get('8.01', '')
        text_to_search = item_801 if item_801 else full_text
        
        if not text_to_search:
            return programs
        
        text_lower = text_to_search.lower()
        
        # Check if filing contains termination keywords
        if not any(keyword in text_lower for keyword in TERMINATION_KEYWORDS):
            return programs
        
        # Extract drug names mentioned in termination context
        drug_names = self._get_all_drug_names()
        termination_sentences = self._extract_termination_sentences(text_to_search)
        
        for sentence in termination_sentences:
            for drug_name in drug_names:
                if drug_name.lower() in sentence.lower():
                    if drug_name not in programs:
                        programs.append(drug_name)
        
        return programs

