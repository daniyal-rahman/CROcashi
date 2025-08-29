"""add_asset_indication_dictionaries

Revision ID: 9c3d4e5f6g7h
Revises: 8b2c3d4e5f6g
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9c3d4e5f6g7h'
down_revision: Union[str, Sequence[str], None] = '8b2c3d4e5f6g'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add asset/indication dictionaries and enhance asset aliases."""
    
    # 1. Create indication dictionaries table
    op.create_table('indication_dictionaries',
        sa.Column('indication_id', sa.Integer, nullable=False),
        sa.Column('indication_text', sa.Text, nullable=False),
        sa.Column('indication_norm', sa.Text, nullable=False),
        sa.Column('indication_type', sa.Text, nullable=False),
        sa.Column('mesh_id', sa.Text, nullable=True),
        sa.Column('mesh_term', sa.Text, nullable=True),
        sa.Column('synonyms_jsonb', postgresql.JSONB, nullable=True),
        sa.Column('therapeutic_area', sa.Text, nullable=True),
        sa.Column('source', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('indication_id'),
        sa.CheckConstraint("indication_type::text = ANY (ARRAY['primary','secondary','related','excluded']::text[])", name='ck_indication_dictionaries_type')
    )
    
    # 2. Create asset-indication relationships table
    op.create_table('asset_indications',
        sa.Column('asset_id', sa.Integer, nullable=False),
        sa.Column('indication_id', sa.Integer, nullable=False),
        sa.Column('relationship_type', sa.Text, nullable=False),
        sa.Column('evidence_level', sa.Text, nullable=True),
        sa.Column('source', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('asset_id', 'indication_id'),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.asset_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['indication_id'], ['indication_dictionaries.indication_id'], ondelete='CASCADE'),
        sa.CheckConstraint("relationship_type::text = ANY (ARRAY['approved','investigational','off_label','contraindicated']::text[])", name='ck_asset_indications_relationship'),
        sa.CheckConstraint("evidence_level::text = ANY (ARRAY['phase_1','phase_2','phase_3','approved','real_world']::text[])", name='ck_asset_indications_evidence')
    )
    
    # 3. Create indication aliases table for normalization
    op.create_table('indication_aliases',
        sa.Column('alias_id', sa.Integer, nullable=False),
        sa.Column('indication_id', sa.Integer, nullable=False),
        sa.Column('alias_text', sa.Text, nullable=False),
        sa.Column('alias_norm', sa.Text, nullable=False),
        sa.Column('alias_type', sa.Text, nullable=False),
        sa.Column('source', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('alias_id'),
        sa.ForeignKeyConstraint(['indication_id'], ['indication_dictionaries.indication_id'], ondelete='CASCADE'),
        sa.CheckConstraint("alias_type::text = ANY (ARRAY['synonym','abbreviation','acronym','misspelling','brand_name','generic_name']::text[])", name='ck_indication_aliases_type')
    )
    
    # 4. Add normalization fields to existing asset_aliases table
    op.add_column('asset_aliases', sa.Column('alias_ascii', sa.Text, nullable=True))
    op.add_column('asset_aliases', sa.Column('alias_hyphen_variants', postgresql.JSONB, nullable=True))
    op.add_column('asset_aliases', sa.Column('alias_phonetic', sa.Text, nullable=True))
    op.add_column('asset_aliases', sa.Column('alias_fuzzy', postgresql.JSONB, nullable=True))
    
    # 5. Create comprehensive indexes for performance
    # Indication dictionaries
    op.create_index('ix_indication_dictionaries_text', 'indication_dictionaries', ['indication_text'])
    op.create_index('ix_indication_dictionaries_norm', 'indication_dictionaries', ['indication_norm'])
    op.create_index('ix_indication_dictionaries_mesh', 'indication_dictionaries', ['mesh_id'])
    op.create_index('ix_indication_dictionaries_therapeutic', 'indication_dictionaries', ['therapeutic_area'])
    op.create_index('ix_indication_dictionaries_type', 'indication_dictionaries', ['indication_type'])
    
    # Indication aliases
    op.create_index('ix_indication_aliases_text', 'indication_aliases', ['alias_text'])
    op.create_index('ix_indication_aliases_norm', 'indication_aliases', ['alias_norm'])
    op.create_index('ix_indication_aliases_type', 'indication_aliases', ['alias_type'])
    op.create_index('ix_indication_aliases_indication', 'indication_aliases', ['indication_id'])
    
    # Asset indications
    op.create_index('ix_asset_indications_asset', 'asset_indications', ['asset_id'])
    op.create_index('ix_asset_indications_indication', 'asset_indications', ['indication_id'])
    op.create_index('ix_asset_indications_relationship', 'asset_indications', ['relationship_type'])
    op.create_index('ix_asset_indications_evidence', 'asset_indications', ['evidence_level'])
    
    # Enhanced asset aliases
    op.create_index('ix_asset_aliases_ascii', 'asset_aliases', ['alias_ascii'])
    op.create_index('ix_asset_aliases_phonetic', 'asset_aliases', ['alias_phonetic'])
    op.create_index('ix_asset_aliases_fuzzy', 'asset_aliases', ['alias_fuzzy'], postgresql_using='gin')
    
    # 6. Insert some common indication patterns for normalization
    op.execute("""
        INSERT INTO indication_dictionaries (indication_text, indication_norm, indication_type, therapeutic_area, source) VALUES
        ('Non-Small Cell Lung Cancer', 'non small cell lung cancer', 'primary', 'oncology', 'manual'),
        ('Non-Small Cell Lung Carcinoma', 'non small cell lung cancer', 'primary', 'oncology', 'manual'),
        ('NSCLC', 'non small cell lung cancer', 'primary', 'oncology', 'manual'),
        ('Breast Cancer', 'breast cancer', 'primary', 'oncology', 'manual'),
        ('Breast Carcinoma', 'breast cancer', 'primary', 'oncology', 'manual'),
        ('Multiple Myeloma', 'multiple myeloma', 'primary', 'oncology', 'manual'),
        ('MM', 'multiple myeloma', 'primary', 'oncology', 'manual'),
        ('Rheumatoid Arthritis', 'rheumatoid arthritis', 'primary', 'rheumatology', 'manual'),
        ('RA', 'rheumatoid arthritis', 'primary', 'rheumatology', 'manual'),
        ('Type 2 Diabetes', 'type 2 diabetes', 'primary', 'endocrinology', 'manual'),
        ('T2D', 'type 2 diabetes', 'primary', 'endocrinology', 'manual'),
        ('T2DM', 'type 2 diabetes', 'primary', 'endocrinology', 'manual'),
        ('Alzheimer''s Disease', 'alzheimers disease', 'primary', 'neurology', 'manual'),
        ('AD', 'alzheimers disease', 'primary', 'neurology', 'manual'),
        ('Parkinson''s Disease', 'parkinsons disease', 'primary', 'neurology', 'manual'),
        ('PD', 'parkinsons disease', 'primary', 'neurology', 'manual')
    ON CONFLICT DO NOTHING
    """)
    
    # 7. Insert indication aliases for normalization
    op.execute("""
        INSERT INTO indication_aliases (indication_id, alias_text, alias_norm, alias_type, source)
        SELECT 
            id.indication_id,
            'Non-Small Cell Lung Cancer' as alias_text,
            'non small cell lung cancer' as alias_norm,
            'synonym' as alias_type,
            'manual' as source
        FROM indication_dictionaries id 
        WHERE id.indication_norm = 'non small cell lung cancer'
        UNION ALL
        SELECT 
            id.indication_id,
            'NSCLC' as alias_text,
            'non small cell lung cancer' as alias_norm,
            'acronym' as alias_type,
            'manual' as source
        FROM indication_dictionaries id 
        WHERE id.indication_norm = 'non small cell lung cancer'
        UNION ALL
        SELECT 
            id.indication_id,
            'Breast Cancer' as alias_text,
            'breast cancer' as alias_norm,
            'synonym' as alias_type,
            'manual' as source
        FROM indication_dictionaries id 
        WHERE id.indication_norm = 'breast cancer'
        UNION ALL
        SELECT 
            id.indication_id,
            'RA' as alias_text,
            'rheumatoid arthritis' as alias_norm,
            'acronym' as alias_type,
            'manual' as source
        FROM indication_dictionaries id 
        WHERE id.indication_norm = 'rheumatoid arthritis'
        UNION ALL
        SELECT 
            id.indication_id,
            'T2D' as alias_text,
            'type 2 diabetes' as alias_norm,
            'acronym' as alias_type,
            'manual' as source
        FROM indication_dictionaries id 
        WHERE id.indication_norm = 'type 2 diabetes'
        UNION ALL
        SELECT 
            id.indication_id,
            'T2DM' as alias_text,
            'type 2 diabetes' as alias_norm,
            'acronym' as alias_type,
            'manual' as source
        FROM indication_dictionaries id 
        WHERE id.indication_norm = 'type 2 diabetes'
        UNION ALL
        SELECT 
            id.indication_id,
            'AD' as alias_text,
            'alzheimers disease' as alias_norm,
            'acronym' as alias_type,
            'manual' as source
        FROM indication_dictionaries id 
        WHERE id.indication_norm = 'alzheimers disease'
        UNION ALL
        SELECT 
            id.indication_id,
            'PD' as alias_text,
            'parkinsons disease' as alias_norm,
            'acronym' as alias_type,
            'manual' as source
        FROM indication_dictionaries id 
        WHERE id.indication_norm = 'parkinsons disease'
    ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    """Remove asset/indication dictionaries."""
    
    # Drop indexes
    op.drop_index('ix_asset_aliases_fuzzy', 'asset_aliases')
    op.drop_index('ix_asset_aliases_phonetic', 'asset_aliases')
    op.drop_index('ix_asset_aliases_ascii', 'asset_aliases')
    op.drop_index('ix_asset_indications_evidence', 'asset_indications')
    op.drop_index('ix_asset_indications_relationship', 'asset_indications')
    op.drop_index('ix_asset_indications_indication', 'asset_indications')
    op.drop_index('ix_asset_indications_asset', 'asset_indications')
    op.drop_index('ix_indication_aliases_indication', 'indication_aliases')
    op.drop_index('ix_indication_aliases_type', 'indication_aliases')
    op.drop_index('ix_indication_aliases_norm', 'indication_aliases')
    op.drop_index('ix_indication_aliases_text', 'indication_aliases')
    op.drop_index('ix_indication_dictionaries_type', 'indication_dictionaries')
    op.drop_index('ix_indication_dictionaries_therapeutic', 'indication_dictionaries')
    op.drop_index('ix_indication_dictionaries_mesh', 'indication_dictionaries')
    op.drop_index('ix_indication_dictionaries_norm', 'indication_dictionaries')
    op.drop_index('ix_indication_dictionaries_text', 'indication_dictionaries')
    
    # Drop columns from asset_aliases
    op.drop_column('asset_aliases', 'alias_fuzzy')
    op.drop_column('asset_aliases', 'alias_phonetic')
    op.drop_column('asset_aliases', 'alias_hyphen_variants')
    op.drop_column('asset_aliases', 'alias_ascii')
    
    # Drop tables
    op.drop_table('asset_indications')
    op.drop_table('indication_aliases')
    op.drop_table('indication_dictionaries')
