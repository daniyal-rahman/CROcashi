"""
Database models package - exports all models.
"""
from database.models.base import Base, BaseModel

# Entity models
from database.models.entities import (
    Company, Institution, Drug, DrugChemicalIdentity,
    DrugName, Target, Mechanism, Disease, DiseaseName
)

# Clinical models
from database.models.clinical import ClinicalTrial, RegulatoryEvent

# Publication models
from database.models.publications import (
    Publication, Patent, Conference, ConferencePresentation, SECFiling
)

# Relationship models
from database.models.relationships import (
    CompanyOwnershipHistory, CompanyDrug, DrugOwnershipHistory,
    DrugTarget, DrugMechanism, DrugIndication, DrugCombination,
    TrialSponsor, TrialFunding, TrialDrug, TrialDisease,
    PublicationDrug, PublicationTrial, PublicationCompany,
    PatentDrug, PatentCompany,
    RegulatoryDrugEvent, RegulatoryCompanyEvent,
    PresentationDrug, PresentationCompany, PresentationTrial,
    FilingCompany, FilingDrug
)

# Resolution models
from database.models.resolution import (
    EntityAlias, EntityMatch, EntityMatchConfidence,
    MatchingReviewQueue, EntityMatchCandidate,
    EntityMatchingRule, SourceProcessingLog, DataQualityMetric
)

# Staging models
from database.models.staging import StagingRawData

__all__ = [
    # Base
    'Base',
    'BaseModel',
    
    # Entities
    'Company',
    'Institution',
    'Drug',
    'DrugChemicalIdentity',
    'DrugName',
    'Target',
    'Mechanism',
    'Disease',
    'DiseaseName',
    
    # Clinical
    'ClinicalTrial',
    'RegulatoryEvent',
    
    # Publications
    'Publication',
    'Patent',
    'Conference',
    'ConferencePresentation',
    'SECFiling',
    
    # Relationships
    'CompanyOwnershipHistory',
    'CompanyDrug',
    'DrugOwnershipHistory',
    'DrugTarget',
    'DrugMechanism',
    'DrugIndication',
    'DrugCombination',
    'TrialSponsor',
    'TrialFunding',
    'TrialDrug',
    'TrialDisease',
    'PublicationDrug',
    'PublicationTrial',
    'PublicationCompany',
    'PatentDrug',
    'PatentCompany',
    'RegulatoryDrugEvent',
    'RegulatoryCompanyEvent',
    'PresentationDrug',
    'PresentationCompany',
    'PresentationTrial',
    'FilingCompany',
    'FilingDrug',
    
    # Resolution
    'EntityAlias',
    'EntityMatch',
    'EntityMatchConfidence',
    'MatchingReviewQueue',
    'EntityMatchCandidate',
    'EntityMatchingRule',
    'SourceProcessingLog',
    'DataQualityMetric',
    
    # Staging
    'StagingRawData',
]

