#!/usr/bin/env python3
"""
Check relationship inference status and readiness.
Verifies if cross-source relationships can be created.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from database.config import get_db_session
from database.models.entities import Company, Drug
from database.models.clinical import ClinicalTrial
from database.models.publications import Publication, SECFiling
from database.models.relationships import (
    PublicationTrial, PublicationDrug, FilingDrug,
    TrialSponsor, TrialDrug
)


def main():
    print("=" * 80)
    print("RELATIONSHIP INFERENCE READINESS CHECK")
    print("=" * 80)
    
    with get_db_session() as session:
        # 1. Check entity coverage
        print("\n[1] ENTITY COVERAGE")
        print("-" * 80)
        check_entity_coverage(session)
        
        # 2. Check current relationships
        print("\n[2] CURRENT RELATIONSHIPS")
        print("-" * 80)
        check_current_relationships(session)
        
        # 3. Check relationship inference readiness
        print("\n[3] RELATIONSHIP INFERENCE READINESS")
        print("-" * 80)
        check_inference_readiness(session)
        
        # 4. Sample potential relationships
        print("\n[4] SAMPLE POTENTIAL RELATIONSHIPS")
        print("-" * 80)
        sample_potential_relationships(session)


def check_entity_coverage(session):
    """Check if we have enough entities for relationship inference."""
    print("Checking entity coverage...")
    
    company_count = session.query(Company).filter(Company.deleted_at.is_(None)).count()
    drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
    trial_count = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
    pub_count = session.query(Publication).filter(Publication.deleted_at.is_(None)).count()
    filing_count = session.query(SECFiling).filter(SECFiling.deleted_at.is_(None)).count()
    
    print(f"\nEntity counts:")
    print(f"  Companies: {company_count}")
    print(f"  Drugs: {drug_count}")
    print(f"  Trials: {trial_count}")
    print(f"  Publications: {pub_count}")
    print(f"  SEC Filings: {filing_count}")
    
    # Check if we have enough for meaningful relationships
    print(f"\nReadiness assessment:")
    
    if pub_count > 0 and trial_count > 0:
        print(f"  ✓ Publication-Trial: Ready ({pub_count} pubs, {trial_count} trials)")
    else:
        print(f"  ✗ Publication-Trial: Not ready (need both pubs and trials)")
    
    if pub_count > 0 and drug_count > 0:
        print(f"  ✓ Publication-Drug: Ready ({pub_count} pubs, {drug_count} drugs)")
    else:
        print(f"  ✗ Publication-Drug: Not ready (need both pubs and drugs)")
    
    if filing_count > 0 and drug_count > 0:
        print(f"  ✓ Filing-Drug: Ready ({filing_count} filings, {drug_count} drugs)")
    else:
        print(f"  ✗ Filing-Drug: Not ready (need both filings and drugs)")


def check_current_relationships(session):
    """Check current relationship counts."""
    print("Checking current relationships...")
    
    trial_sponsor_count = session.query(TrialSponsor).filter(
        TrialSponsor.deleted_at.is_(None)
    ).count()
    
    trial_drug_count = session.query(TrialDrug).filter(
        TrialDrug.deleted_at.is_(None)
    ).count()
    
    pub_trial_count = session.query(PublicationTrial).filter(
        PublicationTrial.deleted_at.is_(None)
    ).count()
    
    pub_drug_count = session.query(PublicationDrug).filter(
        PublicationDrug.deleted_at.is_(None)
    ).count()
    
    filing_drug_count = session.query(FilingDrug).filter(
        FilingDrug.deleted_at.is_(None)
    ).count()
    
    print(f"\nCurrent relationship counts:")
    print(f"  Trial-Sponsor: {trial_sponsor_count} ✅")
    print(f"  Trial-Drug: {trial_drug_count} ✅")
    print(f"  Publication-Trial: {pub_trial_count} {'❌' if pub_trial_count == 0 else '✅'}")
    print(f"  Publication-Drug: {pub_drug_count} {'❌' if pub_drug_count == 0 else '✅'}")
    print(f"  Filing-Drug: {filing_drug_count} {'❌' if filing_drug_count == 0 else '✅'}")
    
    if pub_trial_count == 0 or pub_drug_count == 0 or filing_drug_count == 0:
        print(f"\n  ⚠ MISSING: Cross-source relationships not created")
        print(f"    This is your competitive moat - need to run relationship inference")


def check_inference_readiness(session):
    """Check if relationship inference can run."""
    print("Checking inference readiness...")
    
    # Check if inference script exists
    inference_script = project_root / 'scripts' / 'infer_relationships.py'
    if inference_script.exists():
        print(f"  ✓ Inference script exists: {inference_script}")
    else:
        print(f"  ✗ Inference script not found: {inference_script}")
    
    # Check if relationship inference service exists
    inference_service = project_root / 'src' / 'services' / 'relationship_inference.py'
    if inference_service.exists():
        print(f"  ✓ Inference service exists: {inference_service}")
    else:
        print(f"  ✗ Inference service not found: {inference_service}")
    
    # Check for matching fields
    print(f"\nChecking for matching fields...")
    
    # Publications with NCT IDs
    pubs_with_nct = session.execute(
        text("""
            SELECT COUNT(*) 
            FROM publications 
            WHERE (title LIKE '%NCT%' OR abstract LIKE '%NCT%')
              AND deleted_at IS NULL
        """)
    ).scalar()
    
    print(f"  Publications mentioning NCT: {pubs_with_nct}")
    
    # Publications with drug names
    pubs_with_drugs = session.execute(
        text("""
            SELECT COUNT(*) 
            FROM publications 
            WHERE (title LIKE '%drug%' OR abstract LIKE '%drug%' OR title LIKE '%treatment%')
              AND deleted_at IS NULL
        """)
    ).scalar()
    
    print(f"  Publications mentioning drugs: {pubs_with_drugs}")
    
    # Filings with drug mentions
    filings_with_drugs = session.execute(
        text("""
            SELECT COUNT(*) 
            FROM sec_filings 
            WHERE (full_text LIKE '%drug%' OR full_text LIKE '%treatment%' OR full_text LIKE '%therapeutic%')
              AND deleted_at IS NULL
        """)
    ).scalar()
    
    print(f"  Filings mentioning drugs: {filings_with_drugs}")


def sample_potential_relationships(session):
    """Sample potential relationships that could be created."""
    print("Sampling potential relationships...")
    
    # Sample publications that might link to trials
    print(f"\nSample publications (potential trial links):")
    pubs = session.query(Publication).filter(
        Publication.deleted_at.is_(None)
    ).limit(5).all()
    
    for pub in pubs:
        # Check if title/abstract mentions NCT
        has_nct = 'NCT' in (pub.title or '') or 'NCT' in (pub.abstract or '')
        print(f"  {pub.pmid or pub.pub_id}:")
        print(f"    Title: {pub.title[:80] if pub.title else 'N/A'}...")
        print(f"    Has NCT mention: {'✓' if has_nct else '✗'}")
    
    # Sample filings that might link to drugs
    print(f"\nSample filings (potential drug links):")
    filings = session.query(SECFiling).filter(
        SECFiling.deleted_at.is_(None)
    ).limit(5).all()
    
    for filing in filings:
        # Check if full_text mentions drug-related terms
        text_sample = (filing.full_text or '')[:200]
        has_drug_terms = any(term in text_sample.lower() for term in ['drug', 'treatment', 'therapeutic', 'clinical'])
        print(f"  {filing.accession_number}:")
        print(f"    Type: {filing.filing_type}")
        print(f"    Date: {filing.filing_date}")
        print(f"    Has drug terms: {'✓' if has_drug_terms else '✗'}")
        print(f"    Text sample: {text_sample[:100]}...")


if __name__ == '__main__':
    main()

