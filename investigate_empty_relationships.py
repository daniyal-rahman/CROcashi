#!/usr/bin/env python3
"""
Deep investigation into why relationship tables are empty.
Checks each step of the relationship creation pipeline.
"""
import sys
import re
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database.config import get_db_session
from database.models.publications import Publication
from database.models.clinical import ClinicalTrial
from database.models.relationships import PublicationTrial, PublicationDrug, FilingDrug
from database.models.publications import SECFiling
from database.models import Drug
from database.models.staging import StagingRawData
from database.models.resolution import SourceProcessingLog
from sqlalchemy import text
from src.processors.pubmed_processor import PubMedProcessor
from src.processors.sec_filings_processor import SECFilingsProcessor


def investigate_publication_trials():
    """Investigate why publication-trial relationships are empty."""
    print("\n" + "="*80)
    print("INVESTIGATION: Publication-Trial Relationships")
    print("="*80)
    
    with get_db_session() as session:
        # Check publications
        pub_count = session.query(Publication).filter(Publication.deleted_at.is_(None)).count()
        print(f"\n1. Publications in database: {pub_count}")
        
        # Check if publications have NCT IDs in text
        pubs = session.query(Publication).filter(Publication.deleted_at.is_(None)).limit(10).all()
        nct_ids_found = []
        for pub in pubs:
            text = (pub.title or '') + ' ' + (pub.abstract or '')
            matches = re.findall(r'NCT\d{8}', text, re.IGNORECASE)
            if matches:
                nct_ids_found.extend(matches)
                print(f"   PMID {pub.pmid}: Found {matches}")
        
        print(f"\n2. NCT IDs found in sample publications: {len(nct_ids_found)}")
        
        # Check if trials exist for those NCT IDs
        trial_count = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
        print(f"3. Trials in database: {trial_count}")
        
        if nct_ids_found:
            unique_nct_ids = list(set([n.upper() for n in nct_ids_found]))
            matching_trials = session.query(ClinicalTrial).filter(
                ClinicalTrial.nct_id.in_(unique_nct_ids)
            ).all()
            print(f"4. Trials matching found NCT IDs: {len(matching_trials)}")
            for trial in matching_trials:
                print(f"   - {trial.nct_id}: {trial.trial_title[:50] if trial.trial_title else 'No title'}")
        
        # Check if publications were processed
        pubmed_logs = session.query(SourceProcessingLog).filter(
            SourceProcessingLog.source_name == 'pubmed',
            SourceProcessingLog.deleted_at.is_(None)
        ).count()
        print(f"\n5. PubMed processing logs: {pubmed_logs}")
        
        # Check staging data
        pubmed_staging = session.query(StagingRawData).filter(
            StagingRawData.source_system == 'pubmed',
            StagingRawData.deleted_at.is_(None)
        ).count()
        print(f"6. PubMed staging records: {pubmed_staging}")
        
        # Test processor extraction
        print("\n7. Testing processor extraction...")
        processor = PubMedProcessor(session)
        sample_pub = session.query(StagingRawData).filter(
            StagingRawData.source_system == 'pubmed',
            StagingRawData.deleted_at.is_(None)
        ).first()
        
        if sample_pub:
            print(f"   Testing with staging record: {sample_pub.source_record_id}")
            raw_data = sample_pub.raw_data
            
            # Extract entities
            entities = processor.extract_entities(raw_data)
            print(f"   Entities extracted: {sum(len(v) for v in entities.values())}")
            print(f"   - Publications: {len(entities.get('publications', []))}")
            print(f"   - Drugs: {len(entities.get('drugs', []))}")
            print(f"   - Diseases: {len(entities.get('diseases', []))}")
            
            # Check NCT ID extraction
            nct_ids = processor._extract_nct_ids(raw_data)
            print(f"   NCT IDs extracted: {nct_ids}")
            
            if nct_ids:
                # Check if trials exist
                trials = session.query(ClinicalTrial).filter(
                    ClinicalTrial.nct_id.in_([n.upper() for n in nct_ids])
                ).all()
                print(f"   Matching trials found: {len(trials)}")
        else:
            print("   No staging records found to test")


def investigate_publication_drugs():
    """Investigate why publication-drug relationships are empty."""
    print("\n" + "="*80)
    print("INVESTIGATION: Publication-Drug Relationships")
    print("="*80)
    
    with get_db_session() as session:
        # Check drugs in database
        drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
        print(f"\n1. Drugs in database: {drug_count}")
        
        # Check if processor can load drug names
        processor = PubMedProcessor(session)
        drug_names = processor._get_all_drug_names()
        print(f"2. Drug names loaded by processor: {len(drug_names)}")
        
        if drug_names:
            print(f"   Sample drug names: {list(drug_names)[:5]}")
        
        # Test drug extraction from a publication
        print("\n3. Testing drug extraction from publication...")
        sample_pub = session.query(StagingRawData).filter(
            StagingRawData.source_system == 'pubmed',
            StagingRawData.deleted_at.is_(None)
        ).first()
        
        if sample_pub:
            raw_data = sample_pub.raw_data
            drugs = processor._extract_drugs(raw_data)
            print(f"   Drugs extracted: {len(drugs)}")
            if drugs:
                for drug in drugs[:3]:
                    print(f"   - {drug.name}")
            else:
                # Check what text is available
                title = raw_data.get('title', '')
                abstract = raw_data.get('abstract', '')
                text = (title if isinstance(title, str) else ' '.join(title) if isinstance(title, list) else '') + ' ' + \
                       (abstract if isinstance(abstract, str) else ' '.join(abstract) if isinstance(abstract, list) else '')
                print(f"   Text length: {len(text)}")
                if text:
                    # Check if any drug names appear in text
                    text_lower = text.lower()
                    found = []
                    for drug_name in list(drug_names)[:20]:  # Check first 20
                        if drug_name.lower() in text_lower:
                            found.append(drug_name)
                    print(f"   Drug names found in text (sample): {len(found)}")
                    if found:
                        print(f"   - {found[:3]}")
        else:
            print("   No staging records found to test")


def investigate_filing_drugs():
    """Investigate why filing-drug relationships are empty."""
    print("\n" + "="*80)
    print("INVESTIGATION: Filing-Drug Relationships")
    print("="*80)
    
    with get_db_session() as session:
        # Check filings
        filing_count = session.query(SECFiling).filter(SECFiling.deleted_at.is_(None)).count()
        print(f"\n1. SEC Filings in database: {filing_count}")
        
        # Check if filings have full_text
        filings_with_text = session.query(SECFiling).filter(
            SECFiling.deleted_at.is_(None),
            SECFiling.full_text.isnot(None)
        ).count()
        print(f"2. Filings with full_text: {filings_with_text}")
        
        # Check drugs
        drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
        print(f"3. Drugs in database: {drug_count}")
        
        # Test processor
        processor = SECFilingsProcessor(session)
        drug_names = processor._get_all_drug_names()
        print(f"4. Drug names loaded by processor: {len(drug_names)}")
        
        # Test extraction from a filing
        print("\n5. Testing drug extraction from filing...")
        sample_filing = session.query(StagingRawData).filter(
            StagingRawData.source_system == 'sec_edgar',
            StagingRawData.deleted_at.is_(None)
        ).first()
        
        if sample_filing:
            raw_data = sample_filing.raw_data
            print(f"   Testing with filing: {sample_filing.source_record_id}")
            
            # Check if full_text exists
            full_text = raw_data.get('full_text', '')
            print(f"   Full text length: {len(full_text) if full_text else 0}")
            
            if full_text:
                drugs = processor._extract_drugs_text_search(raw_data)
                print(f"   Drugs extracted: {len(drugs)}")
                if drugs:
                    for drug in drugs[:3]:
                        print(f"   - {drug.name} (mention_type: {drug.context.get('mention_type')})")
                else:
                    # Check if any drug names appear
                    text_lower = full_text.lower()
                    found = []
                    for drug_name in list(drug_names)[:50]:  # Check first 50
                        if drug_name.lower() in text_lower:
                            found.append(drug_name)
                    print(f"   Drug names found in text (sample): {len(found)}")
                    if found:
                        print(f"   - {found[:3]}")
        else:
            print("   No staging records found to test")
        
        # Check if filings were processed
        sec_logs = session.query(SourceProcessingLog).filter(
            SourceProcessingLog.source_name == 'sec_edgar',
            SourceProcessingLog.deleted_at.is_(None)
        ).count()
        print(f"\n6. SEC processing logs: {sec_logs}")


def check_relationship_creation_flow():
    """Check if relationships are being created during processing."""
    print("\n" + "="*80)
    print("INVESTIGATION: Relationship Creation Flow")
    print("="*80)
    
    with get_db_session() as session:
        # Check processing logs for relationship creation
        pubmed_logs = session.query(SourceProcessingLog).filter(
            SourceProcessingLog.source_name == 'pubmed',
            SourceProcessingLog.deleted_at.is_(None)
        ).order_by(SourceProcessingLog.processing_started_at.desc()).limit(5).all()
        
        print("\n1. Recent PubMed processing logs:")
        for log in pubmed_logs:
            print(f"   {log.source_identifier}:")
            print(f"     - Entities extracted: {log.entities_extracted}")
            print(f"     - Entities created: {log.entities_created}")
            print(f"     - Relationships created: {log.relationships_created}")
            print(f"     - Status: {log.processing_status}")
            if log.errors:
                print(f"     - Errors: {log.errors}")
        
        # Check if relationships were actually created
        pub_trial_count = session.query(PublicationTrial).filter(
            PublicationTrial.deleted_at.is_(None)
        ).count()
        pub_drug_count = session.query(PublicationDrug).filter(
            PublicationDrug.deleted_at.is_(None)
        ).count()
        filing_drug_count = session.query(FilingDrug).filter(
            FilingDrug.deleted_at.is_(None)
        ).count()
        
        print(f"\n2. Actual relationship counts:")
        print(f"   - Publication-Trial: {pub_trial_count}")
        print(f"   - Publication-Drug: {pub_drug_count}")
        print(f"   - Filing-Drug: {filing_drug_count}")


def main():
    """Run all investigations."""
    print("\n" + "="*80)
    print("DEEP INVESTIGATION: Why Relationship Tables Are Empty")
    print("="*80)
    
    investigate_publication_trials()
    investigate_publication_drugs()
    investigate_filing_drugs()
    check_relationship_creation_flow()
    
    print("\n" + "="*80)
    print("INVESTIGATION COMPLETE")
    print("="*80)


if __name__ == '__main__':
    main()

