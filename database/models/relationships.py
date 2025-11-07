"""
Relationship tables connecting entities.
"""
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, Column, Date, Integer,
    Numeric, ForeignKey, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database.models.base import BaseModel


class CompanyOwnershipHistory(BaseModel):
    """Temporal ownership tracking for companies."""
    
    __tablename__ = 'company_ownership_history'
    
    history_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    parent_company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    ownership_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='subsidiary, acquired, merged_into, spun_out_from, joint_venture'
    )
    ownership_percentage = Column(Numeric(5, 2), nullable=True)
    
    effective_start_date = Column(Date, nullable=True, index=True)
    effective_end_date = Column(Date, nullable=True, index=True)
    announcement_date = Column(Date, nullable=True)
    
    deal_value = Column(Numeric(20, 2), nullable=True)
    source_url = Column(String(1000), nullable=True)
    data_source = Column(String(200), nullable=True)
    
    company = relationship('Company', foreign_keys=[company_id], backref='ownership_history')
    parent_company = relationship('Company', foreign_keys=[parent_company_id])
    
    __table_args__ = (
        CheckConstraint(
            "ownership_type IN ('subsidiary', 'acquired', 'merged_into', 'spun_out_from', 'joint_venture')",
            name='check_ownership_type'
        ),
    )


class CompanyDrug(BaseModel):
    """Company-drug relationships (ownership/development)."""
    
    __tablename__ = 'company_drugs'
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    relationship_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='originator, licensee, developer, acquirer, co_developer'
    )
    start_date = Column(Date, nullable=True, index=True)
    end_date = Column(Date, nullable=True, index=True)
    
    development_stage = Column(
        String(50),
        nullable=True,
        index=True,
        comment='preclinical, clinical, approved, terminated'
    )
    rights = Column(
        String(50),
        nullable=True,
        comment='worldwide, ex_US, US_only, specific_territories'
    )
    territory_details = Column(Text, nullable=True)
    
    data_sources = Column(JSONB, nullable=True)
    
    company = relationship('Company', backref='drugs')
    drug = relationship('Drug', backref='companies')
    
    __table_args__ = (
        UniqueConstraint('company_id', 'drug_id', 'start_date', name='uq_company_drug_start'),
        CheckConstraint(
            "relationship_type IN ('originator', 'licensee', 'developer', 'acquirer', 'co_developer')",
            name='check_relationship_type'
        ),
        CheckConstraint(
            "rights IN ('worldwide', 'ex_US', 'US_only', 'specific_territories') OR rights IS NULL",
            name='check_rights'
        ),
    )


class DrugOwnershipHistory(BaseModel):
    """Temporal drug ownership tracking."""
    
    __tablename__ = 'drug_ownership_history'
    
    history_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    ownership_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='originator, acquirer, licensee, co_developer'
    )
    effective_start_date = Column(Date, nullable=True, index=True)
    effective_end_date = Column(Date, nullable=True, index=True)
    
    license_territory = Column(String(200), nullable=True)
    license_type = Column(String(100), nullable=True)
    source_url = Column(String(1000), nullable=True)
    
    drug = relationship('Drug', backref='ownership_history')
    company = relationship('Company', backref='drug_ownership_history')


class DrugTarget(BaseModel):
    """Drug-target relationships."""
    
    __tablename__ = 'drug_targets'
    
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    target_id = Column(
        UUID(as_uuid=True),
        ForeignKey('targets.target_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    interaction_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='primary, secondary'
    )
    data_sources = Column(JSONB, nullable=True)
    
    drug = relationship('Drug', backref='targets')
    target = relationship('Target', backref='drugs')
    
    __table_args__ = (
        CheckConstraint(
            "interaction_type IN ('primary', 'secondary') OR interaction_type IS NULL",
            name='check_interaction_type'
        ),
    )


class DrugMechanism(BaseModel):
    """Drug-mechanism relationships."""
    
    __tablename__ = 'drug_mechanisms'
    
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    mechanism_id = Column(
        UUID(as_uuid=True),
        ForeignKey('mechanisms.mechanism_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    data_sources = Column(JSONB, nullable=True)
    
    drug = relationship('Drug', backref='mechanisms')
    mechanism = relationship('Mechanism', backref='drugs')


class DrugIndication(BaseModel):
    """Drug-disease indication relationships."""
    
    __tablename__ = 'drug_indications'
    
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    disease_id = Column(
        UUID(as_uuid=True),
        ForeignKey('diseases.disease_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    development_phase = Column(
        String(50),
        nullable=True,
        index=True,
        comment='preclinical, phase_1, phase_2, phase_3, approved, terminated'
    )
    approved = Column(Boolean, default=False, index=True)
    approval_date = Column(Date, nullable=True, index=True)
    
    data_sources = Column(JSONB, nullable=True)
    
    drug = relationship('Drug', backref='indications')
    disease = relationship('Disease', backref='drug_indications')
    
    __table_args__ = (
        CheckConstraint(
            "development_phase IN ('preclinical', 'phase_1', 'phase_2', 'phase_3', 'approved', 'terminated') OR development_phase IS NULL",
            name='check_development_phase'
        ),
    )


class DrugCombination(BaseModel):
    """Drug combination entities."""
    
    __tablename__ = 'drug_combinations'
    
    combination_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    combination_name = Column(String(500), nullable=True)
    component_drug_ids = Column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        comment='Array of drug UUIDs'
    )
    combination_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='fixed_dose, co_administered, sequential'
    )
    has_formal_name = Column(Boolean, default=False)
    formal_name = Column(String(500), nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "combination_type IN ('fixed_dose', 'co_administered', 'sequential') OR combination_type IS NULL",
            name='check_combination_type'
        ),
    )


class TrialSponsor(BaseModel):
    """Trial sponsor relationships (companies or institutions)."""
    
    __tablename__ = 'trial_sponsors'
    
    trial_id = Column(
        UUID(as_uuid=True),
        ForeignKey('clinical_trials.trial_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    entity_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        primary_key=True,
        comment='Can reference companies OR institutions'
    )
    entity_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='company, institution, government'
    )
    sponsor_role = Column(
        String(50),
        nullable=False,
        index=True,
        primary_key=True,
        comment='lead_sponsor, collaborator, funding_source'
    )
    is_regulatory_sponsor = Column(Boolean, default=False, index=True)
    is_financial_sponsor = Column(Boolean, default=False, index=True)
    
    sponsor_start_date = Column(Date, nullable=True)
    sponsor_end_date = Column(Date, nullable=True)
    
    data_sources = Column(JSONB, nullable=True)
    
    trial = relationship('ClinicalTrial', backref='sponsors')
    
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('company', 'institution', 'government')",
            name='check_entity_type'
        ),
        CheckConstraint(
            "sponsor_role IN ('lead_sponsor', 'collaborator', 'funding_source')",
            name='check_sponsor_role'
        ),
    )


class TrialFunding(BaseModel):
    """Trial funding relationships."""
    
    __tablename__ = 'trial_funding'
    
    trial_id = Column(
        UUID(as_uuid=True),
        ForeignKey('clinical_trials.trial_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    funder_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    funder_type = Column(String(50), nullable=True)
    funding_role = Column(
        String(50),
        nullable=True,
        index=True,
        comment='primary_funder, co_funder, drug_supplier'
    )
    funding_disclosed_in = Column(String(200), nullable=True)
    
    trial = relationship('ClinicalTrial', backref='funding')
    funder = relationship('Company', backref='trial_funding')


class TrialDrug(BaseModel):
    """Trial-drug relationships."""
    
    __tablename__ = 'trial_drugs'
    
    trial_id = Column(
        UUID(as_uuid=True),
        ForeignKey('clinical_trials.trial_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    arm_name = Column(
        String(100),
        nullable=True,
        comment='experimental, control, comparator'
    )
    data_sources = Column(JSONB, nullable=True)
    
    trial = relationship('ClinicalTrial', backref='trial_drugs')
    drug = relationship('Drug', backref='trials')


class TrialDisease(BaseModel):
    """Trial-disease relationships."""
    
    __tablename__ = 'trial_diseases'
    
    trial_id = Column(
        UUID(as_uuid=True),
        ForeignKey('clinical_trials.trial_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    disease_id = Column(
        UUID(as_uuid=True),
        ForeignKey('diseases.disease_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    specificity_level = Column(Integer, nullable=True)
    use_for_aggregation_level = Column(Integer, nullable=True)
    
    biomarker_requirements = Column(ARRAY(Text), nullable=True)
    stage_requirements = Column(ARRAY(Text), nullable=True)
    prior_treatment_requirements = Column(ARRAY(Text), nullable=True)
    
    data_sources = Column(JSONB, nullable=True)
    
    trial = relationship('ClinicalTrial', backref='trial_diseases')
    disease = relationship('Disease', backref='trials')


class PublicationDrug(BaseModel):
    """Publication-drug relationships."""
    
    __tablename__ = 'publication_drugs'
    
    pub_id = Column(
        UUID(as_uuid=True),
        ForeignKey('publications.pub_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    mention_context = Column(
        String(50),
        nullable=True,
        comment='primary_subject, comparator, mentioned'
    )
    data_sources = Column(JSONB, nullable=True)
    
    publication = relationship('Publication', backref='drugs')
    drug = relationship('Drug', backref='publications')
    
    __table_args__ = (
        CheckConstraint(
            "mention_context IN ('primary_subject', 'comparator', 'mentioned') OR mention_context IS NULL",
            name='check_mention_context'
        ),
    )


class PublicationTrial(BaseModel):
    """Publication-trial relationships."""
    
    __tablename__ = 'publication_trials'
    
    pub_id = Column(
        UUID(as_uuid=True),
        ForeignKey('publications.pub_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    trial_id = Column(
        UUID(as_uuid=True),
        ForeignKey('clinical_trials.trial_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    is_primary_publication = Column(Boolean, default=False, index=True)
    data_sources = Column(JSONB, nullable=True)
    
    publication = relationship('Publication', backref='trials')
    trial = relationship('ClinicalTrial', backref='publications')


class PublicationCompany(BaseModel):
    """Publication-company relationships."""
    
    __tablename__ = 'publication_companies'
    
    pub_id = Column(
        UUID(as_uuid=True),
        ForeignKey('publications.pub_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    affiliation_type = Column(
        String(50),
        nullable=True,
        comment='author_affiliation, funding_source, medical_writing'
    )
    data_sources = Column(JSONB, nullable=True)
    
    publication = relationship('Publication', backref='companies')
    company = relationship('Company', backref='publications')
    
    __table_args__ = (
        CheckConstraint(
            "affiliation_type IN ('author_affiliation', 'funding_source', 'medical_writing') OR affiliation_type IS NULL",
            name='check_affiliation_type'
        ),
    )


class PatentDrug(BaseModel):
    """Patent-drug relationships."""
    
    __tablename__ = 'patent_drugs'
    
    patent_id = Column(
        UUID(as_uuid=True),
        ForeignKey('patents.patent_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    data_sources = Column(JSONB, nullable=True)
    
    patent = relationship('Patent', backref='drugs')
    drug = relationship('Drug', backref='patents')


class PatentCompany(BaseModel):
    """Patent-company relationships."""
    
    __tablename__ = 'patent_companies'
    
    patent_id = Column(
        UUID(as_uuid=True),
        ForeignKey('patents.patent_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    ownership_type = Column(
        String(50),
        nullable=True,
        comment='assignee, licensee'
    )
    data_sources = Column(JSONB, nullable=True)
    
    patent = relationship('Patent', backref='companies')
    company = relationship('Company', backref='patents')
    
    __table_args__ = (
        CheckConstraint(
            "ownership_type IN ('assignee', 'licensee') OR ownership_type IS NULL",
            name='check_patent_ownership_type'
        ),
    )


class RegulatoryDrugEvent(BaseModel):
    """Regulatory event-drug relationships."""
    
    __tablename__ = 'regulatory_drug_events'
    
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey('regulatory_events.event_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    disease_id = Column(
        UUID(as_uuid=True),
        ForeignKey('diseases.disease_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    data_sources = Column(JSONB, nullable=True)
    
    event = relationship('RegulatoryEvent', backref='drugs')
    drug = relationship('Drug', backref='regulatory_events')
    disease = relationship('Disease', backref='regulatory_events')


class RegulatoryCompanyEvent(BaseModel):
    """Regulatory event-company relationships."""
    
    __tablename__ = 'regulatory_company_events'
    
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey('regulatory_events.event_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    data_sources = Column(JSONB, nullable=True)
    
    event = relationship('RegulatoryEvent', backref='companies')
    company = relationship('Company', backref='regulatory_events')


class PresentationDrug(BaseModel):
    """Conference presentation-drug relationships."""
    
    __tablename__ = 'presentation_drugs'
    
    presentation_id = Column(
        UUID(as_uuid=True),
        ForeignKey('conference_presentations.presentation_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    data_sources = Column(JSONB, nullable=True)
    
    presentation = relationship('ConferencePresentation', backref='drugs')
    drug = relationship('Drug', backref='presentations')


class PresentationCompany(BaseModel):
    """Conference presentation-company relationships."""
    
    __tablename__ = 'presentation_companies'
    
    presentation_id = Column(
        UUID(as_uuid=True),
        ForeignKey('conference_presentations.presentation_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    data_sources = Column(JSONB, nullable=True)
    
    presentation = relationship('ConferencePresentation', backref='companies')
    company = relationship('Company', backref='presentations')


class PresentationTrial(BaseModel):
    """Conference presentation-trial relationships."""
    
    __tablename__ = 'presentation_trials'
    
    presentation_id = Column(
        UUID(as_uuid=True),
        ForeignKey('conference_presentations.presentation_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    trial_id = Column(
        UUID(as_uuid=True),
        ForeignKey('clinical_trials.trial_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    data_sources = Column(JSONB, nullable=True)
    
    presentation = relationship('ConferencePresentation', backref='trials')
    trial = relationship('ClinicalTrial', backref='presentations')


class FilingCompany(BaseModel):
    """SEC filing-company relationships."""
    
    __tablename__ = 'filing_companies'
    
    filing_id = Column(
        UUID(as_uuid=True),
        ForeignKey('sec_filings.filing_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    
    filing = relationship('SECFiling', backref='companies')
    company = relationship('Company', backref='filings')


class FilingDrug(BaseModel):
    """SEC filing-drug relationships."""
    
    __tablename__ = 'filing_drugs'
    
    filing_id = Column(
        UUID(as_uuid=True),
        ForeignKey('sec_filings.filing_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        primary_key=True
    )
    mention_type = Column(
        String(50),
        nullable=True,
        comment='pipeline_update, termination, milestone, licensing'
    )
    data_sources = Column(JSONB, nullable=True)
    
    filing = relationship('SECFiling', backref='drugs')
    drug = relationship('Drug', backref='filings')
    
    __table_args__ = (
        CheckConstraint(
            "mention_type IN ('pipeline_update', 'termination', 'milestone', 'licensing') OR mention_type IS NULL",
            name='check_mention_type'
        ),
    )

