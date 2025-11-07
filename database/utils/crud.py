"""
CRUD utilities for common operations.
"""
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session

from database.models import (
    Company, Drug, ClinicalTrial, Disease, Publication
)


# Company CRUD
def create_company(
    session: Session,
    name: str,
    **kwargs
) -> Company:
    """Create a new company."""
    company = Company(name=name, **kwargs)
    session.add(company)
    session.flush()
    return company


def update_company(
    session: Session,
    company_id: UUID,
    **kwargs
) -> Optional[Company]:
    """Update company fields."""
    company = session.query(Company).filter(
        Company.company_id == company_id
    ).first()
    
    if not company:
        return None
    
    for key, value in kwargs.items():
        if hasattr(company, key):
            setattr(company, key, value)
    
    session.flush()
    return company


def get_company(session: Session, company_id: UUID) -> Optional[Company]:
    """Get company by ID."""
    return session.query(Company).filter(
        Company.company_id == company_id
    ).first()


# Drug CRUD
def create_drug(
    session: Session,
    primary_name: str,
    **kwargs
) -> Drug:
    """Create a new drug."""
    drug = Drug(primary_name=primary_name, **kwargs)
    session.add(drug)
    session.flush()
    return drug


def update_drug(
    session: Session,
    drug_id: UUID,
    **kwargs
) -> Optional[Drug]:
    """Update drug fields."""
    drug = session.query(Drug).filter(
        Drug.drug_id == drug_id
    ).first()
    
    if not drug:
        return None
    
    for key, value in kwargs.items():
        if hasattr(drug, key):
            setattr(drug, key, value)
    
    session.flush()
    return drug


def get_drug(session: Session, drug_id: UUID) -> Optional[Drug]:
    """Get drug by ID."""
    return session.query(Drug).filter(
        Drug.drug_id == drug_id
    ).first()


# Clinical Trial CRUD
def create_trial(
    session: Session,
    trial_title: str,
    **kwargs
) -> ClinicalTrial:
    """Create a new clinical trial."""
    trial = ClinicalTrial(trial_title=trial_title, **kwargs)
    session.add(trial)
    session.flush()
    return trial


def update_trial(
    session: Session,
    trial_id: UUID,
    **kwargs
) -> Optional[ClinicalTrial]:
    """Update trial fields."""
    trial = session.query(ClinicalTrial).filter(
        ClinicalTrial.trial_id == trial_id
    ).first()
    
    if not trial:
        return None
    
    for key, value in kwargs.items():
        if hasattr(trial, key):
            setattr(trial, key, value)
    
    session.flush()
    return trial


def get_trial(session: Session, trial_id: UUID) -> Optional[ClinicalTrial]:
    """Get trial by ID."""
    return session.query(ClinicalTrial).filter(
        ClinicalTrial.trial_id == trial_id
    ).first()


# Disease CRUD
def create_disease(
    session: Session,
    disease_name: str,
    **kwargs
) -> Disease:
    """Create a new disease."""
    disease = Disease(disease_name=disease_name, **kwargs)
    session.add(disease)
    session.flush()
    return disease


def get_disease(session: Session, disease_id: UUID) -> Optional[Disease]:
    """Get disease by ID."""
    return session.query(Disease).filter(
        Disease.disease_id == disease_id
    ).first()


# Publication CRUD
def create_publication(
    session: Session,
    title: str,
    **kwargs
) -> Publication:
    """Create a new publication."""
    publication = Publication(title=title, **kwargs)
    session.add(publication)
    session.flush()
    return publication


def get_publication(session: Session, pub_id: UUID) -> Optional[Publication]:
    """Get publication by ID."""
    return session.query(Publication).filter(
        Publication.pub_id == pub_id
    ).first()

