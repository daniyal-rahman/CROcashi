"""
Common query utilities for the biotech knowledge graph.
"""
from datetime import date
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session, joinedload

from database.models import (
    Company, Drug, ClinicalTrial, Publication, Disease,
    CompanyDrug, TrialDrug, DrugIndication, TrialSponsor, TrialDisease
)


def get_company_by_name(session: Session, name: str) -> Optional[Company]:
    """Get company by name (case-insensitive)."""
    return session.query(Company).filter(
        func.lower(Company.name) == name.lower()
    ).first()


def get_company_with_drugs(session: Session, company_id: UUID) -> Optional[Company]:
    """Get company with all associated drugs."""
    return session.query(Company).options(
        joinedload(Company.drugs).joinedload(CompanyDrug.drug)
    ).filter(Company.company_id == company_id).first()


def get_drug_by_name(session: Session, name: str) -> Optional[Drug]:
    """Get drug by name (searches primary name and aliases)."""
    # Try primary name first
    drug = session.query(Drug).filter(
        func.lower(Drug.primary_name) == name.lower()
    ).first()
    
    if drug:
        return drug
    
    # Try aliases
    return session.query(Drug).filter(
        func.lower(func.any(Drug.aliases)) == name.lower()
    ).first()


def get_drug_with_companies(session: Session, drug_id: UUID) -> Optional[Drug]:
    """Get drug with all associated companies."""
    return session.query(Drug).options(
        joinedload(Drug.companies).joinedload(CompanyDrug.company)
    ).filter(Drug.drug_id == drug_id).first()


def get_drug_with_indications(session: Session, drug_id: UUID) -> Optional[Drug]:
    """Get drug with all indications."""
    return session.query(Drug).options(
        joinedload(Drug.indications).joinedload(DrugIndication.disease)
    ).filter(Drug.drug_id == drug_id).first()


def get_trials_for_drug(
    session: Session,
    drug_id: UUID,
    status: Optional[str] = None,
    phase: Optional[int] = None
) -> List[ClinicalTrial]:
    """Get all trials for a drug, optionally filtered by status and phase."""
    query = session.query(ClinicalTrial).join(
        TrialDrug
    ).filter(TrialDrug.drug_id == drug_id)
    
    if status:
        query = query.filter(ClinicalTrial.status == status)
    
    if phase:
        query = query.filter(ClinicalTrial.phase_numeric == phase)
    
    return query.all()


def get_company_pipeline(
    session: Session,
    company_id: UUID,
    development_stage: Optional[str] = None
) -> List[Drug]:
    """Get all drugs in a company's pipeline."""
    query = session.query(Drug).join(
        CompanyDrug
    ).filter(CompanyDrug.company_id == company_id)
    
    if development_stage:
        query = query.filter(CompanyDrug.development_stage == development_stage)
    
    return query.all()


def get_drugs_for_disease(
    session: Session,
    disease_id: UUID,
    approved_only: bool = False
) -> List[Drug]:
    """Get all drugs for a disease, optionally only approved ones."""
    query = session.query(Drug).join(
        DrugIndication
    ).filter(DrugIndication.disease_id == disease_id)
    
    if approved_only:
        query = query.filter(DrugIndication.approved == True)
    
    return query.all()


def get_trials_for_company(
    session: Session,
    company_id: UUID,
    status: Optional[str] = None
) -> List[ClinicalTrial]:
    """Get all trials sponsored by a company."""
    query = session.query(ClinicalTrial).join(
        TrialSponsor
    ).filter(
        and_(
            TrialSponsor.entity_id == company_id,
            TrialSponsor.entity_type == 'company'
        )
    )
    
    if status:
        query = query.filter(ClinicalTrial.status == status)
    
    return query.all()


def get_publications_for_drug(
    session: Session,
    drug_id: UUID,
    limit: Optional[int] = None
) -> List[Publication]:
    """Get publications mentioning a drug."""
    query = session.query(Publication).join(
        PublicationDrug
    ).filter(PublicationDrug.drug_id == drug_id)
    
    if limit:
        query = query.limit(limit)
    
    return query.order_by(Publication.publication_date.desc()).all()


def search_companies(
    session: Session,
    search_term: str,
    limit: int = 10
) -> List[Company]:
    """Search companies by name or ticker."""
    search_lower = f"%{search_term.lower()}%"
    return session.query(Company).filter(
        or_(
            func.lower(Company.name).like(search_lower),
            func.lower(Company.ticker).like(search_lower) if Company.ticker else False
        )
    ).limit(limit).all()


def search_drugs(
    session: Session,
    search_term: str,
    limit: int = 10
) -> List[Drug]:
    """Search drugs by name or alias."""
    search_lower = f"%{search_term.lower()}%"
    return session.query(Drug).filter(
        or_(
            func.lower(Drug.primary_name).like(search_lower),
            func.lower(Drug.generic_name).like(search_lower) if Drug.generic_name else False,
            func.lower(Drug.code_name).like(search_lower) if Drug.code_name else False
        )
    ).limit(limit).all()


def get_active_trials_count(session: Session) -> int:
    """Get count of active/recruiting trials."""
    return session.query(ClinicalTrial).filter(
        ClinicalTrial.status.in_(['recruiting', 'active'])
    ).count()


def get_companies_with_most_drugs(
    session: Session,
    limit: int = 10
) -> List[tuple]:
    """Get companies with the most drugs in pipeline."""
    return session.query(
        Company.name,
        func.count(CompanyDrug.drug_id).label('drug_count')
    ).join(
        CompanyDrug
    ).group_by(
        Company.company_id, Company.name
    ).order_by(
        func.count(CompanyDrug.drug_id).desc()
    ).limit(limit).all()

