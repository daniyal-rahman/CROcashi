"""
Utility to load data from ingestion scripts into the staging table.

This bridges the gap between raw data fetching and the processing pipeline.
"""
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from database.config import get_db_session
from database.models.staging import StagingRawData

logger = logging.getLogger(__name__)


class StagingLoader:
    """
    Loads raw data into the staging table for processing.
    
    This provides a standardized way for ingestion scripts to:
    1. Store fetched data in the database
    2. Avoid duplicates
    3. Track what needs processing
    """
    
    def __init__(self, source_system: str):
        """
        Initialize staging loader.
        
        Args:
            source_system: Name of the source system (e.g., 'clinicaltrials_gov')
        """
        self.source_system = source_system
    
    def load_records(
        self,
        records: List[Dict[str, Any]],
        id_extractor: callable,
        skip_duplicates: bool = True
    ) -> Dict[str, int]:
        """
        Load multiple records into staging.
        
        Args:
            records: List of raw data records
            id_extractor: Function to extract source record ID from a record
            skip_duplicates: Whether to skip records that already exist
            
        Returns:
            Dict with statistics (inserted, skipped, errors)
        """
        stats = {
            'inserted': 0,
            'skipped': 0,
            'errors': 0
        }
        
        with get_db_session() as session:
            for record in records:
                try:
                    # Extract source identifier
                    source_record_id = id_extractor(record)
                    
                    if not source_record_id:
                        logger.warning(f"Could not extract ID from record: {record.keys()}")
                        stats['errors'] += 1
                        continue
                    
                    # Check if already exists
                    if skip_duplicates:
                        existing = session.query(StagingRawData).filter_by(
                            source_system=self.source_system,
                            source_record_id=source_record_id
                        ).first()
                        
                        if existing:
                            logger.debug(f"Record {source_record_id} already exists, skipping")
                            stats['skipped'] += 1
                            continue
                    
                    # Insert new record
                    staging_record = StagingRawData(
                        staging_id=uuid4(),
                        source_system=self.source_system,
                        source_record_id=source_record_id,
                        raw_data=record,
                        processed=False
                    )
                    
                    session.add(staging_record)
                    stats['inserted'] += 1
                    
                except Exception as e:
                    logger.error(f"Error loading record: {e}")
                    stats['errors'] += 1
            
            # Commit all records at once
            try:
                session.commit()
                logger.info(
                    f"Loaded {stats['inserted']} records from {self.source_system} "
                    f"(skipped: {stats['skipped']}, errors: {stats['errors']})"
                )
            except Exception as e:
                session.rollback()
                logger.error(f"Error committing records: {e}")
                # Mark all as errors
                stats['errors'] = stats['inserted']
                stats['inserted'] = 0
        
        return stats
    
    def load_single(
        self,
        record: Dict[str, Any],
        source_record_id: str,
        skip_if_exists: bool = True
    ) -> bool:
        """
        Load a single record into staging.
        
        Args:
            record: Raw data record
            source_record_id: Unique identifier for this record
            skip_if_exists: Whether to skip if record already exists
            
        Returns:
            True if inserted, False if skipped or error
        """
        with get_db_session() as session:
            try:
                # Check if already exists
                if skip_if_exists:
                    existing = session.query(StagingRawData).filter_by(
                        source_system=self.source_system,
                        source_record_id=source_record_id
                    ).first()
                    
                    if existing:
                        logger.debug(f"Record {source_record_id} already exists")
                        return False
                
                # Insert new record
                staging_record = StagingRawData(
                    staging_id=uuid4(),
                    source_system=self.source_system,
                    source_record_id=source_record_id,
                    raw_data=record,
                    processed=False
                )
                
                session.add(staging_record)
                session.commit()
                
                logger.debug(f"Inserted record {source_record_id}")
                return True
                
            except Exception as e:
                session.rollback()
                logger.error(f"Error loading record {source_record_id}: {e}")
                return False


# Convenience ID extractors for common data sources

def clinicaltrials_id_extractor(record: Dict[str, Any]) -> Optional[str]:
    """Extract NCT ID from ClinicalTrials.gov record."""
    # Handle nested protocolSection format
    if 'protocolSection' in record:
        protocol = record.get('protocolSection', {})
        id_module = protocol.get('identificationModule', {})
        return id_module.get('nctId')
    
    # Handle flat format
    return record.get('nct_id') or record.get('NCTId')


def pubmed_id_extractor(record: Dict[str, Any]) -> Optional[str]:
    """Extract PMID from PubMed record."""
    return record.get('pmid') or record.get('uid')


def fda_drug_id_extractor(record: Dict[str, Any]) -> Optional[str]:
    """Extract application number from FDA drug record."""
    return record.get('application_number') or record.get('ApplNo')


def sec_filing_id_extractor(record: Dict[str, Any]) -> Optional[str]:
    """Extract accession number from SEC filing."""
    # Try camelCase first (from SEC API)
    accession_number = record.get('accessionNumber')
    if accession_number:
        return str(accession_number)
    
    # Fallback to snake_case (from processor)
    accession_number = record.get('accession_number')
    if accession_number:
        return str(accession_number)
    
    return None


def patent_id_extractor(record: Dict[str, Any]) -> Optional[str]:
    """Extract patent number from patent record."""
    return record.get('patent_number') or record.get('patentNumber')


def patentsview_id_extractor(record: Dict[str, Any]) -> Optional[str]:
    """Extract patent number from PatentsView record."""
    return record.get('patent_number')


def openfda_id_extractor(record: Dict[str, Any]) -> Optional[str]:
    """Extract unique identifier from OpenFDA drug label record."""
    # Try spl_id first (unique per label)
    spl_id = record.get('spl_id')
    if spl_id:
        return str(spl_id)
    
    # Try set_id as fallback (also unique per label)
    set_id = record.get('set_id')
    if set_id:
        return str(set_id)
    
    # Fallback to product_ndc from openfda wrapper
    openfda = record.get('openfda', {})
    if isinstance(openfda, dict):
        product_ndc = openfda.get('product_ndc')
        if isinstance(product_ndc, list) and len(product_ndc) > 0:
            return str(product_ndc[0])
        elif isinstance(product_ndc, str):
            return product_ndc
    
    # Last resort: use 'id' field if present
    record_id = record.get('id')
    if record_id:
        return str(record_id)
    
    return None

