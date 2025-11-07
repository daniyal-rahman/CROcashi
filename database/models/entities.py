"""
Core entity models: Companies, Institutions, Drugs, Targets, Mechanisms, Diseases.
"""
import uuid
from datetime import date
from typing import List, Optional

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, Column, Date, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database.models.base import BaseModel


class Company(BaseModel):
    """Company entity with ownership hierarchy and metadata."""
    
    __tablename__ = 'companies'
    
    company_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    name = Column(
        String(500),
        unique=True,
        nullable=False,
        index=True,
        comment='Primary company name'
    )
    ticker = Column(
        String(20),
        nullable=True,
        index=True,
        comment='Stock ticker symbol'
    )
    founded_date = Column(Date, nullable=True, comment='Company founding date')
    defunct_date = Column(Date, nullable=True, comment='Company closure date')
    
    status = Column(
        String(50),
        nullable=False,
        default='active',
        index=True,
        comment='Company status: active, acquired, defunct, merged, subsidiary'
    )
    legal_entity_status = Column(
        String(100),
        nullable=True,
        comment='Legal entity status'
    )
    
    # Self-referential foreign keys for ownership hierarchy
    current_parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    ultimate_parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    headquarters_location = Column(String(500), nullable=True)
    company_type = Column(
        String(50),
        nullable=True,
        comment='public, private, subsidiary, government, nonprofit'
    )
    is_public = Column(Boolean, default=False, index=True)
    
    # URLs
    website_url = Column(String(1000), nullable=True)
    pipeline_page_url = Column(String(1000), nullable=True)
    linkedin_url = Column(String(1000), nullable=True)
    crunchbase_url = Column(String(1000), nullable=True)
    
    # Flexible metadata
    data_sources = Column(
        JSONB,
        nullable=True,
        comment='Track which sources mention this company'
    )
    aliases = Column(
        ARRAY(Text),
        nullable=True,
        comment='Alternative names and aliases'
    )
    
    # Relationships
    current_parent = relationship(
        'Company',
        foreign_keys=[current_parent_id],
        remote_side=[company_id],
        backref='subsidiaries'
    )
    ultimate_parent_rel = relationship(
        'Company',
        foreign_keys=[ultimate_parent_id],
        remote_side=[company_id]
    )
    
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'acquired', 'defunct', 'merged', 'subsidiary')",
            name='check_company_status'
        ),
        CheckConstraint(
            "company_type IN ('public', 'private', 'subsidiary', 'government', 'nonprofit') OR company_type IS NULL",
            name='check_company_type'
        ),
        {'comment': 'Companies table with ownership hierarchy'}
    )


class Institution(BaseModel):
    """Academic/hospital/research institutions."""
    
    __tablename__ = 'institutions'
    
    institution_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    name = Column(
        String(500),
        nullable=False,
        index=True,
        comment='Institution name'
    )
    institution_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='university, hospital, research_institute, government, cooperative_group'
    )
    country = Column(String(100), nullable=True, index=True)
    
    # Self-referential for hierarchy
    parent_institution_id = Column(
        UUID(as_uuid=True),
        ForeignKey('institutions.institution_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    frequent_industry_partners = Column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment='References to companies'
    )
    
    data_sources = Column(JSONB, nullable=True)
    aliases = Column(ARRAY(Text), nullable=True)
    
    parent_institution = relationship(
        'Institution',
        foreign_keys=[parent_institution_id],
        remote_side=[institution_id],
        backref='child_institutions'
    )
    
    __table_args__ = (
        CheckConstraint(
            "institution_type IN ('university', 'hospital', 'research_institute', 'government', 'cooperative_group') OR institution_type IS NULL",
            name='check_institution_type'
        ),
    )


class Drug(BaseModel):
    """Drug entity with chemical and biological identifiers."""
    
    __tablename__ = 'drugs'
    
    drug_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    primary_name = Column(
        String(500),
        nullable=False,
        index=True,
        comment='Primary drug name'
    )
    generic_name = Column(String(500), nullable=True, index=True)
    code_name = Column(String(200), nullable=True, index=True)
    
    drug_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='small_molecule, biologic, antibody, gene_therapy, cell_therapy, vaccine'
    )
    
    molecular_weight = Column(Numeric(10, 2), nullable=True)
    formula = Column(String(500), nullable=True)
    
    # External identifiers
    chembl_id = Column(String(50), nullable=True, index=True)
    drugbank_id = Column(String(50), nullable=True, index=True)
    pubchem_cid = Column(String(50), nullable=True, index=True)
    inchi_key = Column(String(100), nullable=True, index=True)
    cas_number = Column(String(50), nullable=True, index=True)
    unii_code = Column(String(50), nullable=True, index=True)
    
    data_sources = Column(JSONB, nullable=True)
    aliases = Column(ARRAY(Text), nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "drug_type IN ('small_molecule', 'biologic', 'antibody', 'gene_therapy', 'cell_therapy', 'vaccine') OR drug_type IS NULL",
            name='check_drug_type'
        ),
    )


class DrugChemicalIdentity(BaseModel):
    """Definitive chemical identity for drug matching."""
    
    __tablename__ = 'drug_chemical_identity'
    
    drug_id = Column(
        UUID(as_uuid=True),
        ForeignKey('drugs.drug_id', ondelete='CASCADE'),
        primary_key=True
    )
    inchi_key = Column(String(100), unique=True, nullable=True, index=True)
    smiles = Column(Text, nullable=True)
    molecular_formula = Column(String(500), nullable=True)
    sequence = Column(Text, nullable=True, comment='For biologics')
    sequence_hash = Column(String(64), nullable=True, index=True, comment='For faster matching')
    cas_registry_number = Column(String(50), nullable=True, index=True)
    unii_code = Column(String(50), nullable=True, index=True)
    
    drug = relationship('Drug', backref='chemical_identity')


class DrugName(BaseModel):
    """Temporal name tracking for drugs."""
    
    __tablename__ = 'drug_names'
    
    name_id = Column(
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
    name_text = Column(
        String(500),
        nullable=False,
        index=True,
        comment='Name text'
    )
    name_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='research_code, generic_name, brand_name, former_name, combination_name, synonym'
    )
    valid_from = Column(Date, nullable=True, index=True)
    valid_until = Column(Date, nullable=True, index=True)
    country = Column(String(100), nullable=True)
    regulatory_region = Column(String(100), nullable=True)
    
    used_by_company_id = Column(
        UUID(as_uuid=True),
        ForeignKey('companies.company_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    is_primary_name = Column(Boolean, default=False, index=True)
    source = Column(String(200), nullable=True)
    data_source = Column(JSONB, nullable=True)
    
    drug = relationship('Drug', backref='names')
    used_by_company = relationship('Company', backref='drug_names')
    
    __table_args__ = (
        CheckConstraint(
            "name_type IN ('research_code', 'generic_name', 'brand_name', 'former_name', 'combination_name', 'synonym')",
            name='check_drug_name_type'
        ),
    )


class Target(BaseModel):
    """Biological targets (proteins, genes, pathways)."""
    
    __tablename__ = 'targets'
    
    target_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    target_name = Column(
        String(500),
        nullable=False,
        index=True
    )
    target_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='protein, gene, pathway, receptor, enzyme'
    )
    uniprot_id = Column(String(50), nullable=True, index=True)
    gene_symbol = Column(String(50), nullable=True, index=True)
    gene_id = Column(String(50), nullable=True, index=True)
    description = Column(Text, nullable=True)
    data_sources = Column(JSONB, nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('protein', 'gene', 'pathway', 'receptor', 'enzyme') OR target_type IS NULL",
            name='check_target_type'
        ),
    )


class Mechanism(BaseModel):
    """Drug mechanisms of action."""
    
    __tablename__ = 'mechanisms'
    
    mechanism_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    mechanism_name = Column(
        String(500),
        nullable=False,
        index=True
    )
    mechanism_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='inhibitor, agonist, antagonist, modulator'
    )
    description = Column(Text, nullable=True)
    data_sources = Column(JSONB, nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "mechanism_type IN ('inhibitor', 'agonist', 'antagonist', 'modulator') OR mechanism_type IS NULL",
            name='check_mechanism_type'
        ),
    )


class Disease(BaseModel):
    """Disease entities with hierarchical structure."""
    
    __tablename__ = 'diseases'
    
    disease_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    disease_name = Column(
        String(500),
        nullable=False,
        index=True
    )
    
    # Self-referential for hierarchy
    parent_disease_id = Column(
        UUID(as_uuid=True),
        ForeignKey('diseases.disease_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    disease_level = Column(
        Integer,
        nullable=True,
        comment='0=broad category, 1=disease class, etc.'
    )
    
    # Classification codes
    icd10_code = Column(String(50), nullable=True, index=True)
    mesh_id = Column(String(50), nullable=True, index=True)
    snomed_code = Column(String(50), nullable=True, index=True)
    disease_ontology_id = Column(String(50), nullable=True, index=True)
    
    is_rare_disease = Column(Boolean, default=False, index=True)
    is_orphan_designation_eligible = Column(Boolean, default=False, index=True)
    
    description = Column(Text, nullable=True)
    
    classification_valid_from = Column(Date, nullable=True)
    classification_valid_until = Column(Date, nullable=True)
    
    data_sources = Column(JSONB, nullable=True)
    aliases = Column(ARRAY(Text), nullable=True)
    
    parent_disease = relationship(
        'Disease',
        foreign_keys=[parent_disease_id],
        remote_side=[disease_id],
        backref='child_diseases'
    )


class DiseaseName(BaseModel):
    """Temporal naming for diseases."""
    
    __tablename__ = 'disease_names'
    
    name_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    disease_id = Column(
        UUID(as_uuid=True),
        ForeignKey('diseases.disease_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    name_text = Column(
        String(500),
        nullable=False,
        index=True
    )
    name_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='current_name, former_name, synonym, abbreviation'
    )
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    data_source = Column(String(200), nullable=True)
    
    disease = relationship('Disease', backref='names')
    
    __table_args__ = (
        CheckConstraint(
            "name_type IN ('current_name', 'former_name', 'synonym', 'abbreviation')",
            name='check_disease_name_type'
        ),
    )

