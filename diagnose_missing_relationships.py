"""
Diagnostic script to investigate why relationships are missing.
"""
import sys
from database.config import get_db_session
from database.models import (
    Company, Drug, ClinicalTrial, Publication, Patent, SECFiling,
    CompanyDrug, TrialSponsor, TrialDrug, PublicationDrug, PublicationTrial,
    PatentDrug, PatentCompany, FilingDrug, DrugTarget, DrugMechanism
)

def diagnose_relationships():
    """Diagnose why relationships are missing."""
    print("=" * 80)
    print("RELATIONSHIP DIAGNOSTIC REPORT")
    print("=" * 80)
    print()
    
    try:
        with get_db_session() as session:
            # 1. Check entity counts
            print("1. ENTITY COUNTS")
            print("-" * 80)
            company_count = session.query(Company).filter(Company.deleted_at.is_(None)).count()
            drug_count = session.query(Drug).filter(Drug.deleted_at.is_(None)).count()
            trial_count = session.query(ClinicalTrial).filter(ClinicalTrial.deleted_at.is_(None)).count()
            pub_count = session.query(Publication).filter(Publication.deleted_at.is_(None)).count()
            patent_count = session.query(Patent).filter(Patent.deleted_at.is_(None)).count()
            filing_count = session.query(SECFiling).filter(SECFiling.deleted_at.is_(None)).count()
            
            print(f"  Companies: {company_count:,}")
            print(f"  Drugs: {drug_count:,}")
            print(f"  Trials: {trial_count:,}")
            print(f"  Publications: {pub_count:,}")
            print(f"  Patents: {patent_count:,}")
            print(f"  SEC Filings: {filing_count:,}")
            print()
            
            # 2. Check existing relationships
            print("2. EXISTING RELATIONSHIP COUNTS")
            print("-" * 80)
            trial_sponsor_count = session.query(TrialSponsor).count()
            trial_drug_count = session.query(TrialDrug).count()
            company_drug_count = session.query(CompanyDrug).count()
            pub_drug_count = session.query(PublicationDrug).count()
            pub_trial_count = session.query(PublicationTrial).count()
            patent_drug_count = session.query(PatentDrug).count()
            patent_company_count = session.query(PatentCompany).count()
            filing_drug_count = session.query(FilingDrug).count()
            drug_target_count = session.query(DrugTarget).count()
            drug_mechanism_count = session.query(DrugMechanism).count()
            
            print(f"  TrialSponsor: {trial_sponsor_count:,}")
            print(f"  TrialDrug: {trial_drug_count:,}")
            print(f"  CompanyDrug: {company_drug_count:,}")
            print(f"  PublicationDrug: {pub_drug_count:,}")
            print(f"  PublicationTrial: {pub_trial_count:,}")
            print(f"  PatentDrug: {patent_drug_count:,}")
            print(f"  PatentCompany: {patent_company_count:,}")
            print(f"  FilingDrug: {filing_drug_count:,}")
            print(f"  DrugTarget: {drug_target_count:,}")
            print(f"  DrugMechanism: {drug_mechanism_count:,}")
            print()
            
            # 3. Analyze potential relationships
            print("3. POTENTIAL RELATIONSHIP ANALYSIS")
            print("-" * 80)
            
            # Company-Drug from trials
            if trial_sponsor_count > 0 and trial_drug_count > 0:
                # Count unique company-drug pairs from trials
                from sqlalchemy import func, distinct
                # Use a subquery to get distinct pairs
                subq = session.query(
                    TrialSponsor.entity_id,
                    TrialDrug.drug_id
                ).join(
                    TrialDrug, TrialSponsor.trial_id == TrialDrug.trial_id
                ).filter(
                    TrialSponsor.entity_type == 'company'
                ).distinct().subquery()
                
                potential_company_drugs = session.query(func.count()).select_from(subq).scalar() or 0
                print(f"  Potential CompanyDrug from trials: ~{potential_company_drugs:,}")
                print(f"    (Actual: {company_drug_count:,}, Missing: ~{potential_company_drugs - company_drug_count:,})")
            
            # Publication-Trial
            if pub_count > 0 and trial_count > 0:
                # Check if any publications have NCT IDs in their context or title
                try:
                    pubs_with_nct = session.query(Publication).filter(
                        (Publication.context['title'].astext.ilike('%NCT%')) |
                        (Publication.title.ilike('%NCT%'))
                    ).count()
                except:
                    # Fallback if JSONB query doesn't work
                    pubs_with_nct = session.query(Publication).filter(
                        Publication.title.ilike('%NCT%')
                    ).count()
                print(f"  Publications potentially mentioning trials: {pubs_with_nct:,}")
                print(f"    (Actual PublicationTrial: {pub_trial_count:,})")
            
            # Publication-Drug
            if pub_count > 0 and drug_count > 0:
                print(f"  Potential PublicationDrug relationships: Unknown (requires text search)")
                print(f"    (Actual: {pub_drug_count:,})")
            
            # Patent relationships
            if patent_count > 0:
                print(f"  Patents exist: {patent_count:,}")
                print(f"    PatentDrug: {patent_drug_count:,}")
                print(f"    PatentCompany: {patent_company_count:,}")
                if patent_count > 0 and patent_drug_count == 0 and patent_company_count == 0:
                    print(f"    ⚠️  WARNING: Patents exist but no relationships created!")
            
            # Drug-Target and Drug-Mechanism
            if drug_count > 0:
                print(f"  Drugs exist: {drug_count:,}")
                print(f"    DrugTarget: {drug_target_count:,}")
                print(f"    DrugMechanism: {drug_mechanism_count:,}")
                if drug_count > 0 and drug_target_count == 0 and drug_mechanism_count == 0:
                    print(f"    ⚠️  WARNING: Drugs exist but no target/mechanism relationships!")
                    print(f"    NOTE: OpenFDA processor doesn't extract targets/mechanisms")
            
            print()
            
            # 4. Check data sources
            print("4. DATA SOURCE ANALYSIS")
            print("-" * 80)
            
            # Check which sources have created relationships
            from sqlalchemy import func
            from sqlalchemy.dialects.postgresql import JSONB
            
            # Trial relationships by source
            trial_sponsor_sources = session.query(
                func.jsonb_object_keys(TrialSponsor.data_sources).label('source')
            ).distinct().all()
            if trial_sponsor_sources:
                print(f"  TrialSponsor sources: {[s[0] for s in trial_sponsor_sources]}")
            
            # Publication relationships
            if pub_drug_count > 0:
                pub_drug_sources = session.query(
                    func.jsonb_object_keys(PublicationDrug.data_sources).label('source')
                ).distinct().all()
                print(f"  PublicationDrug sources: {[s[0] for s in pub_drug_sources]}")
            else:
                print(f"  PublicationDrug sources: None (no relationships)")
            
            # Patent relationships
            if patent_company_count > 0:
                patent_company_sources = session.query(
                    func.jsonb_object_keys(PatentCompany.data_sources).label('source')
                ).distinct().all()
                print(f"  PatentCompany sources: {[s[0] for s in patent_company_sources]}")
            else:
                print(f"  PatentCompany sources: None (no relationships)")
            
            print()
            
            # 5. Recommendations
            print("5. RECOMMENDATIONS")
            print("-" * 80)
            
            issues = []
            
            if company_drug_count < 100 and trial_sponsor_count > 0 and trial_drug_count > 0:
                issues.append("CompanyDrug relationships should be inferred from TrialSponsor + TrialDrug")
            
            if pub_count > 0 and pub_drug_count == 0:
                issues.append("PublicationDrug relationships missing - check if PubMed processor is extracting drugs")
            
            if pub_count > 0 and pub_trial_count == 0:
                issues.append("PublicationTrial relationships missing - check if publications have NCT IDs")
            
            if patent_count > 0 and patent_drug_count == 0 and patent_company_count == 0:
                issues.append("Patent relationships missing - check if patents are being processed correctly")
            
            if drug_count > 0 and drug_target_count == 0:
                issues.append("DrugTarget relationships missing - OpenFDA doesn't extract targets, need different source")
            
            if drug_count > 0 and drug_mechanism_count == 0:
                issues.append("DrugMechanism relationships missing - OpenFDA doesn't extract mechanisms, need different source")
            
            if issues:
                for i, issue in enumerate(issues, 1):
                    print(f"  {i}. {issue}")
            else:
                print("  ✓ No obvious issues found")
            
            print()
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == '__main__':
    success = diagnose_relationships()
    sys.exit(0 if success else 1)

