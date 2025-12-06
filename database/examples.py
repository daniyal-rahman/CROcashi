"""
Example queries demonstrating key relationship traversals.
"""
from database.config import get_db_session
from database.utils import (
    get_company_by_name,
    get_company_with_drugs,
    get_drug_with_indications,
    get_trials_for_drug,
    get_company_pipeline,
    get_drugs_for_disease,
    search_companies,
    search_drugs,
)


def example_company_drug_relationships():
    """Example: Find all drugs for a company."""
    with get_db_session() as session:
        # Find company by name
        company = get_company_by_name(session, "Pfizer")
        
        if company:
            print(f"Found company: {company.name}")
            
            # Get all drugs in pipeline
            drugs = get_company_pipeline(session, company.company_id)
            print(f"\nDrugs in pipeline: {len(drugs)}")
            for drug in drugs:
                print(f"  - {drug.primary_name}")
            
            # Get all trials sponsored by company
            trials = get_trials_for_company(session, company.company_id)
            print(f"\nTrials sponsored: {len(trials)}")


def example_drug_indications():
    """Example: Find all indications for a drug."""
    with get_db_session() as session:
        # Find drug by name
        drug = get_drug_by_name(session, "Keytruda")
        
        if drug:
            print(f"Found drug: {drug.primary_name}")
            
            # Get all indications
            drug_with_indications = get_drug_with_indications(
                session, drug.drug_id
            )
            
            if drug_with_indications:
                print("\nIndications:")
                for indication in drug_with_indications.indications:
                    disease = indication.disease
                    status = "✓ Approved" if indication.approved else f"  {indication.development_phase}"
                    print(f"  {status}: {disease.disease_name}")


def example_trial_drugs():
    """Example: Find all drugs in a trial."""
    with get_db_session() as session:
        # Get trials for a drug
        drug = get_drug_by_name(session, "Keytruda")
        
        if drug:
            trials = get_trials_for_drug(
                session,
                drug.drug_id,
                status='active',
                phase=3
            )
            
            print(f"\nActive Phase 3 trials for {drug.primary_name}: {len(trials)}")
            for trial in trials:
                print(f"  - {trial.trial_title}")
                print(f"    NCT: {trial.nct_id}")
                print(f"    Status: {trial.status}")


def example_disease_drugs():
    """Example: Find all drugs for a disease."""
    with get_db_session() as session:
        from database.models import Disease
        from database.utils.queries import get_drugs_for_disease
        
        # Find disease
        disease = session.query(Disease).filter(
            Disease.disease_name.ilike("%melanoma%")
        ).first()
        
        if disease:
            print(f"Found disease: {disease.disease_name}")
            
            # Get approved drugs
            approved_drugs = get_drugs_for_disease(
                session,
                disease.disease_id,
                approved_only=True
            )
            
            print(f"\nApproved drugs: {len(approved_drugs)}")
            for drug in approved_drugs:
                print(f"  - {drug.primary_name}")


def example_search():
    """Example: Search functionality."""
    with get_db_session() as session:
        # Search companies
        companies = search_companies(session, "biotech", limit=5)
        print(f"\nCompanies matching 'biotech': {len(companies)}")
        for company in companies:
            print(f"  - {company.name} ({company.ticker})")
        
        # Search drugs
        drugs = search_drugs(session, "umab", limit=5)
        print(f"\nDrugs matching 'umab': {len(drugs)}")
        for drug in drugs:
            print(f"  - {drug.primary_name}")


def example_complex_query():
    """Example: Complex multi-table query."""
    with get_db_session() as session:
        from database.models import (
            Company, Drug, ClinicalTrial, TrialDrug, TrialSponsor,
            DrugIndication, Disease, TrialDisease, CompanyDrug
        )
        from sqlalchemy import and_
        
        # Find companies with drugs in Phase 3 trials for cancer
        results = session.query(
            Company.name,
            Drug.primary_name,
            ClinicalTrial.nct_id,
            Disease.disease_name
        ).join(
            CompanyDrug, CompanyDrug.company_id == Company.company_id
        ).join(
            Drug, Drug.drug_id == CompanyDrug.drug_id
        ).join(
            TrialDrug, TrialDrug.drug_id == Drug.drug_id
        ).join(
            ClinicalTrial, ClinicalTrial.trial_id == TrialDrug.trial_id
        ).join(
            TrialDisease, TrialDisease.trial_id == ClinicalTrial.trial_id
        ).join(
            Disease, Disease.disease_id == TrialDisease.disease_id
        ).filter(
            and_(
                ClinicalTrial.phase_numeric == 3,
                ClinicalTrial.status.in_(['active', 'recruiting']),
                Disease.disease_name.ilike("%cancer%")
            )
        ).limit(10).all()
        
        print(f"\nPhase 3 cancer trials:")
        for company_name, drug_name, nct_id, disease_name in results:
            print(f"  {company_name} - {drug_name} ({nct_id}) for {disease_name}")


if __name__ == '__main__':
    print("Example queries for biotech knowledge graph")
    print("=" * 50)
    
    # Uncomment to run examples (requires database to be set up)
    # example_company_drug_relationships()
    # example_drug_indications()
    # example_trial_drugs()
    # example_disease_drugs()
    # example_search()
    # example_complex_query()
    
    print("\nNote: These are example queries. Uncomment in examples.py to run.")

