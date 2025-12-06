#!/usr/bin/env python3
"""
Verify relationship inference will actually work before running it.
Checks for extractable content, entity aliases, and linkable data.
"""
import sys
from pathlib import Path
import re

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, func
from database.config import get_db_session
from database.models.publications import Publication
from database.models.clinical import ClinicalTrial
from database.models.entities import Drug, Company
from database.models.publications import SECFiling
from database.models.resolution import EntityAlias


def main():
    print("=" * 80)
    print("RELATIONSHIP INFERENCE READINESS VERIFICATION")
    print("=" * 80)
    
    with get_db_session() as session:
        # 1. Check publication content
        print("\n[1] PUBLICATION CONTENT VERIFICATION")
        print("-" * 80)
        verify_publication_content(session)
        
        # 2. Check SEC filing extraction
        print("\n[2] SEC FILING EXTRACTION VERIFICATION")
        print("-" * 80)
        verify_filing_extraction(session)
        
        # 3. Check entity aliases
        print("\n[3] ENTITY ALIASES VERIFICATION")
        print("-" * 80)
        check_entity_aliases(session)
        
        # 4. Check entity name normalization
        print("\n[4] ENTITY NAME NORMALIZATION")
        print("-" * 80)
        check_entity_normalization(session)
        
        # 5. Test on small sample
        print("\n[5] SAMPLE LINKABILITY TEST")
        print("-" * 80)
        test_sample_linkability(session)
        
        # 6. Final assessment
        print("\n[6] FINAL ASSESSMENT")
        print("-" * 80)
        final_assessment(session)


def verify_publication_content(session):
    """Verify publications have extractable content for linking."""
    print("Checking publication content...")
    
    # Total publications
    total_pubs = session.query(Publication).filter(
        Publication.deleted_at.is_(None)
    ).count()
    
    # Publications with abstracts
    pubs_with_abstract = session.query(Publication).filter(
        Publication.deleted_at.is_(None),
        Publication.abstract.isnot(None),
        func.length(Publication.abstract) > 100
    ).count()
    
    # Publications mentioning NCT
    pubs_with_nct = session.execute(
        text("""
            SELECT COUNT(*) 
            FROM publications 
            WHERE (title ILIKE '%NCT%' OR abstract ILIKE '%NCT%')
              AND deleted_at IS NULL
        """)
    ).scalar()
    
    # Publications mentioning trial-related terms
    pubs_with_trial_terms = session.execute(
        text("""
            SELECT COUNT(*) 
            FROM publications 
            WHERE (
                title ~* '\\btrial\\b|\\bstudy\\b|\\bclinical\\b' 
                OR abstract ~* '\\btrial\\b|\\bstudy\\b|\\bclinical\\b'
            )
            AND deleted_at IS NULL
        """)
    ).scalar()
    
    # Publications mentioning drug-related terms
    pubs_with_drug_terms = session.execute(
        text("""
            SELECT COUNT(*) 
            FROM publications 
            WHERE (
                title ~* '\\bdrug\\b|\\btreatment\\b|\\btherapeutic\\b|\\bmedication\\b'
                OR abstract ~* '\\bdrug\\b|\\btreatment\\b|\\btherapeutic\\b|\\bmedication\\b'
            )
            AND deleted_at IS NULL
        """)
    ).scalar()
    
    print(f"\nPublication content analysis:")
    print(f"  Total publications: {total_pubs}")
    print(f"  With abstracts (>100 chars): {pubs_with_abstract} ({pubs_with_abstract/total_pubs*100:.1f}%)")
    print(f"  Mentioning NCT: {pubs_with_nct} ({pubs_with_nct/total_pubs*100:.1f}%)")
    print(f"  Mentioning trial terms: {pubs_with_trial_terms} ({pubs_with_trial_terms/total_pubs*100:.1f}%)")
    print(f"  Mentioning drug terms: {pubs_with_drug_terms} ({pubs_with_drug_terms/total_pubs*100:.1f}%)")
    
    # Sample abstracts
    print(f"\nSample abstracts (first 200 chars):")
    sample_pubs = session.query(Publication).filter(
        Publication.deleted_at.is_(None),
        Publication.abstract.isnot(None),
        func.length(Publication.abstract) > 100
    ).limit(3).all()
    
    for pub in sample_pubs:
        abstract_preview = pub.abstract[:200] if pub.abstract else "No abstract"
        print(f"\n  {pub.pmid or pub.pub_id}:")
        print(f"    {abstract_preview}...")
    
    # Assessment
    print(f"\nAssessment:")
    if pubs_with_abstract < total_pubs * 0.5:
        print(f"  ⚠ WARNING: Less than 50% have abstracts - linking will be difficult")
    else:
        print(f"  ✓ Good abstract coverage")
    
    if pubs_with_nct == 0 and pubs_with_trial_terms < total_pubs * 0.3:
        print(f"  ⚠ WARNING: Low trial mention rate - may need NLP extraction")
    else:
        print(f"  ✓ Some trial mentions found")
    
    if pubs_with_drug_terms < total_pubs * 0.3:
        print(f"  ⚠ WARNING: Low drug mention rate - may need NLP extraction")
    else:
        print(f"  ✓ Some drug mentions found")


def verify_filing_extraction(session):
    """Verify SEC filings have extractable text."""
    print("Checking SEC filing extraction...")
    
    # Total filings
    total_filings = session.query(SECFiling).filter(
        SECFiling.deleted_at.is_(None)
    ).count()
    
    # Filings with full_text
    filings_with_text = session.query(SECFiling).filter(
        SECFiling.deleted_at.is_(None),
        SECFiling.full_text.isnot(None),
        func.length(SECFiling.full_text) > 500
    ).count()
    
    # Filings mentioning drug terms
    filings_with_drug_terms = session.execute(
        text("""
            SELECT COUNT(*) 
            FROM sec_filings 
            WHERE (
                full_text ILIKE '%drug%' 
                OR full_text ILIKE '%treatment%' 
                OR full_text ILIKE '%therapeutic%'
                OR full_text ILIKE '%clinical%'
            )
            AND deleted_at IS NULL
        """)
    ).scalar()
    
    # Filings mentioning trial terms
    filings_with_trial_terms = session.execute(
        text("""
            SELECT COUNT(*) 
            FROM sec_filings 
            WHERE (
                full_text ILIKE '%trial%' 
                OR full_text ILIKE '%study%' 
                OR full_text ILIKE '%clinical%'
            )
            AND deleted_at IS NULL
        """)
    ).scalar()
    
    print(f"\nSEC filing content analysis:")
    print(f"  Total filings: {total_filings}")
    print(f"  With full_text (>500 chars): {filings_with_text} ({filings_with_text/total_filings*100:.1f}%)")
    print(f"  Mentioning drug terms: {filings_with_drug_terms} ({filings_with_drug_terms/total_filings*100:.1f}%)")
    print(f"  Mentioning trial terms: {filings_with_trial_terms} ({filings_with_trial_terms/total_filings*100:.1f}%)")
    
    # Sample filing text
    print(f"\nSample filing text (first 300 chars):")
    sample_filings = session.query(SECFiling).filter(
        SECFiling.deleted_at.is_(None),
        SECFiling.full_text.isnot(None),
        func.length(SECFiling.full_text) > 500
    ).limit(2).all()
    
    for filing in sample_filings:
        text_preview = filing.full_text[:300] if filing.full_text else "No text"
        print(f"\n  {filing.accession_number}:")
        print(f"    {text_preview}...")
    
    # Assessment
    print(f"\nAssessment:")
    if filings_with_text < total_filings * 0.5:
        print(f"  ⚠ WARNING: Less than 50% have extractable text")
    else:
        print(f"  ✓ Good text coverage")
    
    if filings_with_drug_terms == 0:
        print(f"  ⚠ WARNING: No drug mentions found - linking will be difficult")
    else:
        print(f"  ✓ Some drug mentions found")


def check_entity_aliases(session):
    """Check if entity aliases exist for fuzzy matching."""
    print("Checking entity aliases...")
    
    # Count aliases
    total_aliases = session.query(EntityAlias).filter(
        EntityAlias.deleted_at.is_(None)
    ).count()
    
    # Aliases by entity type
    aliases_by_type = session.execute(
        text("""
            SELECT entity_type, COUNT(*) as count
            FROM entity_aliases
            WHERE deleted_at IS NULL
            GROUP BY entity_type
            ORDER BY count DESC
        """)
    ).fetchall()
    
    print(f"\nEntity alias counts:")
    print(f"  Total aliases: {total_aliases}")
    for entity_type, count in aliases_by_type:
        print(f"  {entity_type}: {count}")
    
    # Check drug aliases specifically
    drug_aliases = session.query(EntityAlias).filter(
        EntityAlias.entity_type == 'drug',
        EntityAlias.deleted_at.is_(None)
    ).count()
    
    drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
    
    print(f"\nDrug alias coverage:")
    print(f"  Drugs: {drug_count}")
    print(f"  Drug aliases: {drug_aliases}")
    if drug_count > 0:
        alias_ratio = drug_aliases / drug_count
        print(f"  Alias ratio: {alias_ratio:.2f}")
        
        if alias_ratio < 0.5:
            print(f"  ⚠ WARNING: Low alias coverage - fuzzy matching may fail")
        else:
            print(f"  ✓ Good alias coverage")
    
    # Check company aliases
    company_aliases = session.query(EntityAlias).filter(
        EntityAlias.entity_type == 'company',
        EntityAlias.deleted_at.is_(None)
    ).count()
    
    company_count = session.query(Company).filter(Company.deleted_at.is_(None)).count()
    
    print(f"\nCompany alias coverage:")
    print(f"  Companies: {company_count}")
    print(f"  Company aliases: {company_aliases}")
    if company_count > 0:
        alias_ratio = company_aliases / company_count
        print(f"  Alias ratio: {alias_ratio:.2f}")


def check_entity_normalization(session):
    """Check if entity names are normalized."""
    print("Checking entity name normalization...")
    
    # Check drug name normalization
    total_drugs = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
    
    normalized_drugs = session.execute(
        text("""
            SELECT COUNT(DISTINCT lower(trim(primary_name)))
            FROM drugs
            WHERE deleted_at IS NULL
        """)
    ).scalar()
    
    print(f"\nDrug name normalization:")
    print(f"  Total drugs: {total_drugs}")
    print(f"  Unique normalized names: {normalized_drugs}")
    
    if total_drugs > 0:
        normalization_ratio = normalized_drugs / total_drugs
        print(f"  Normalization ratio: {normalization_ratio:.2f}")
        
        if normalization_ratio > 0.9:
            print(f"  ⚠ WARNING: High normalization ratio - may indicate duplicates")
        elif normalization_ratio < 0.7:
            print(f"  ✓ Good normalization (some duplicates expected)")
        else:
            print(f"  ✓ Reasonable normalization")
    
    # Check company name normalization
    total_companies = session.query(Company).filter(Company.deleted_at.is_(None)).count()
    
    normalized_companies = session.execute(
        text("""
            SELECT COUNT(DISTINCT lower(trim(name)))
            FROM companies
            WHERE deleted_at IS NULL
        """)
    ).scalar()
    
    print(f"\nCompany name normalization:")
    print(f"  Total companies: {total_companies}")
    print(f"  Unique normalized names: {normalized_companies}")
    
    if total_companies > 0:
        normalization_ratio = normalized_companies / total_companies
        print(f"  Normalization ratio: {normalization_ratio:.2f}")


def test_sample_linkability(session):
    """Test if we can actually link a small sample."""
    print("Testing sample linkability...")
    
    # Get sample publications
    sample_pubs = session.query(Publication).filter(
        Publication.deleted_at.is_(None),
        Publication.abstract.isnot(None),
        func.length(Publication.abstract) > 100
    ).limit(5).all()
    
    print(f"\nTesting {len(sample_pubs)} publications for linkability:")
    
    linkable_count = 0
    
    for pub in sample_pubs:
        abstract = (pub.abstract or "").lower()
        title = (pub.title or "").lower()
        combined = f"{title} {abstract}"
        
        # Check for NCT mentions
        nct_pattern = r'\bNCT\d{8}\b'
        nct_matches = re.findall(nct_pattern, combined)
        
        # Check for drug mentions (simple - just check if any drug names appear)
        drug_names = session.query(Drug.primary_name).filter(
            Drug.deleted_at.is_(None)
        ).limit(20).all()
        
        drug_mentions = []
        for (drug_name,) in drug_names:
            if drug_name and drug_name.lower() in combined:
                drug_mentions.append(drug_name)
        
        is_linkable = len(nct_matches) > 0 or len(drug_mentions) > 0
        
        print(f"\n  {pub.pmid or pub.pub_id}:")
        print(f"    NCT mentions: {len(nct_matches)} ({', '.join(nct_matches[:3]) if nct_matches else 'None'})")
        print(f"    Drug mentions: {len(drug_mentions)} ({', '.join(drug_mentions[:3]) if drug_mentions else 'None'})")
        print(f"    Linkable: {'✓' if is_linkable else '✗'}")
        
        if is_linkable:
            linkable_count += 1
    
    linkability_rate = linkable_count / len(sample_pubs) if sample_pubs else 0
    print(f"\nSample linkability rate: {linkability_rate*100:.1f}%")
    
    if linkability_rate < 0.2:
        print(f"  ⚠ WARNING: Very low linkability - inference may create 0 relationships")
    elif linkability_rate < 0.5:
        print(f"  ⚠ CAUTION: Low linkability - may need NLP extraction")
    else:
        print(f"  ✓ Good linkability - inference should work")


def final_assessment(session):
    """Provide final assessment."""
    print("Final assessment:")
    
    # Get key metrics
    total_pubs = session.query(Publication).filter(Publication.deleted_at.is_(None)).count()
    pubs_with_abstract = session.query(Publication).filter(
        Publication.deleted_at.is_(None),
        Publication.abstract.isnot(None),
        func.length(Publication.abstract) > 100
    ).count()
    
    total_filings = session.query(SECFiling).filter(SECFiling.deleted_at.is_(None)).count()
    filings_with_text = session.query(SECFiling).filter(
        SECFiling.deleted_at.is_(None),
        SECFiling.full_text.isnot(None),
        func.length(SECFiling.full_text) > 500
    ).count()
    
    drug_aliases = session.query(EntityAlias).filter(
        EntityAlias.entity_type == 'drug',
        EntityAlias.deleted_at.is_(None)
    ).count()
    drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
    
    print(f"\nReadiness checklist:")
    
    # Publication readiness
    pub_ready = pubs_with_abstract >= total_pubs * 0.5
    print(f"  Publications have extractable content: {'✓' if pub_ready else '✗'}")
    
    # Filing readiness
    filing_ready = filings_with_text >= total_filings * 0.5
    print(f"  Filings have extractable text: {'✓' if filing_ready else '✗'}")
    
    # Alias readiness
    alias_ready = drug_aliases >= drug_count * 0.3 if drug_count > 0 else False
    print(f"  Entity aliases exist: {'✓' if alias_ready else '✗'}")
    
    # Overall assessment
    all_ready = pub_ready and filing_ready and alias_ready
    
    print(f"\nOverall assessment:")
    if all_ready:
        print(f"  ✅ READY: Relationship inference should work")
        print(f"  Recommendation: Run on small sample first (10 records)")
    elif pub_ready or filing_ready:
        print(f"  ⚠ PARTIALLY READY: Some sources ready, others need work")
        print(f"  Recommendation: Fix missing pieces first, then run")
    else:
        print(f"  ❌ NOT READY: Missing extractable content")
        print(f"  Recommendation: Need NLP extraction or better data sources")
        print(f"  Estimated work: 20+ hours for NLP extraction")


if __name__ == '__main__':
    main()

