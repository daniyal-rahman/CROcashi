"""add_pubmed_literature_system

Revision ID: 8b2c3d4e5f6g
Revises: 6c4909ab66ac
Create Date: 2025-01-27 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8b2c3d4e5f6g'
down_revision: Union[str, Sequence[str], None] = '6c4909ab66ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add PubMed literature processing system to existing database."""
    
    # 1. Update source_type enum to include PubMed and PMC
    op.execute("ALTER TYPE source_type_enum ADD VALUE 'PubMed'")
    op.execute("ALTER TYPE source_type_enum ADD VALUE 'PMC'")
    
    # 2. Update document status enum to include new states
    op.execute("ALTER TYPE document_status_enum ADD VALUE 'scored'")
    op.execute("ALTER TYPE document_status_enum ADD VALUE 'parked'")
    op.execute("ALTER TYPE document_status_enum ADD VALUE 'promoted'")
    
    # 3. Add new entity types for literature analysis
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'effect_size'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'p_value'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'ci'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'hr'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'rr'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'orr'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'n_total'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'population'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'subgroup'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'phase'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'design'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'control_type'")
    op.execute("ALTER TYPE entity_type_enum ADD VALUE 'asset_name'")
    
    # 4. Add detailed citation fields to existing document_citations table
    op.add_column('document_citations', sa.Column('journal', sa.Text, nullable=True))
    op.add_column('document_citations', sa.Column('volume', sa.Text, nullable=True))
    op.add_column('document_citations', sa.Column('issue', sa.Text, nullable=True))
    op.add_column('document_citations', sa.Column('pages', sa.Text, nullable=True))
    op.add_column('document_citations', sa.Column('article_type', sa.Text, nullable=True))
    op.add_column('document_citations', sa.Column('pub_year', sa.Integer, nullable=True))
    op.add_column('document_citations', sa.Column('mesh_jsonb', postgresql.JSONB, nullable=True))
    op.add_column('document_citations', sa.Column('substances_jsonb', postgresql.JSONB, nullable=True))
    
    # 5. Create document_text table for abstracts and full text
    op.create_table('document_text',
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('abstract_text', sa.Text, nullable=True),
        sa.Column('fulltext_text', sa.Text, nullable=True),
        sa.Column('fulltext_ttl_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('char_count_abstract', sa.Integer, nullable=True),
        sa.Column('char_count_fulltext', sa.Integer, nullable=True),
        sa.PrimaryKeyConstraint('doc_id'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE')
    )
    
    # 6. Create pubmed_meta table for PubMed-specific metadata
    op.create_table('pubmed_meta',
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('pmid', sa.Text, nullable=True),
        sa.Column('medline_xml_sha', sa.Text, nullable=True),
        sa.Column('language', sa.Text, nullable=True),
        sa.Column('authors_jsonb', postgresql.JSONB, nullable=True),
        sa.Column('affiliations_jsonb', postgresql.JSONB, nullable=True),
        sa.Column('esummary_jsonb', postgresql.JSONB, nullable=True),
        sa.Column('efetch_header_jsonb', postgresql.JSONB, nullable=True),
        sa.PrimaryKeyConstraint('doc_id'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE')
    )
    
    # 7. Create pmc_meta table for PMC-specific metadata
    op.create_table('pmc_meta',
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('pmcid', sa.Text, nullable=True),
        sa.Column('license', sa.Text, nullable=True),
        sa.Column('oa_route', sa.Text, nullable=True),
        sa.Column('oai_identifier', sa.Text, nullable=True),
        sa.PrimaryKeyConstraint('doc_id'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE')
    )
    
    # 8. Create trial_doc_candidates table for trial-document relationships
    op.create_table('trial_doc_candidates',
        sa.Column('trial_id', sa.Integer, nullable=False),
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('stage', sa.Text, nullable=False),
        sa.Column('selected', sa.Boolean, nullable=True),
        sa.Column('dropped_reason', sa.Text, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.PrimaryKeyConstraint('trial_id', 'doc_id'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        sa.CheckConstraint("stage::text = ANY (ARRAY['U0_meta','U1_abstract','OA_fulltext']::text[])", name='ck_trial_doc_candidates_stage')
    )
    
    # 9. Create doc_rs_scores table for R/S scoring
    op.create_table('doc_rs_scores',
        sa.Column('trial_id', sa.Integer, nullable=False),
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('R_score', sa.Numeric, nullable=False),
        sa.Column('R_tier', sa.Text, nullable=False),
        sa.Column('S_score', sa.Numeric, nullable=False),
        sa.Column('S_tier', sa.Text, nullable=False),
        sa.Column('R_components_jsonb', postgresql.JSONB, nullable=True),
        sa.Column('S_components_jsonb', postgresql.JSONB, nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('trial_id', 'doc_id'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        sa.CheckConstraint('"R_score" >= 0 AND "R_score" <= 1', name='ck_doc_rs_scores_R_score_range'),
        sa.CheckConstraint('"S_score" >= 0 AND "S_score" <= 1', name='ck_doc_rs_scores_S_score_range'),
        sa.CheckConstraint('"R_tier"::text = ANY (ARRAY[\'R0\',\'R1\',\'R2\',\'R3\']::text[])', name='ck_doc_rs_scores_R_tier'),
        sa.CheckConstraint('"S_tier"::text = ANY (ARRAY[\'S0\',\'S1\',\'S2\',\'S3\']::text[])', name='ck_doc_rs_scores_S_tier')
    )
    
    # 10. Create trial_lit_state table for trial-level literature state
    op.create_table('trial_lit_state',
        sa.Column('trial_id', sa.Integer, nullable=False),
        sa.Column('best_S_Rge2', sa.Numeric, nullable=True),
        sa.Column('n_docs_seen', sa.Integer, nullable=False, server_default='0'),
        sa.Column('n_docs_selected', sa.Integer, nullable=False, server_default='0'),
        sa.Column('p_short', sa.Numeric, nullable=True),
        sa.Column('uncertainty', sa.Numeric, nullable=True),
        sa.Column('max_expected_utility_next_doc', sa.Numeric, nullable=True),
        sa.Column('status', sa.Text, nullable=False, server_default='active'),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('trial_id'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.CheckConstraint('"best_S_Rge2" IS NULL OR ("best_S_Rge2" >= 0 AND "best_S_Rge2" <= 1)', name='ck_trial_lit_state_best_S_Rge2_range'),
        sa.CheckConstraint('p_short IS NULL OR (p_short >= 0 AND p_short <= 1)', name='ck_trial_lit_state_p_short_range'),
        sa.CheckConstraint('uncertainty IS NULL OR (uncertainty >= 0 AND uncertainty <= 1)', name='ck_trial_lit_state_uncertainty_range'),
        sa.CheckConstraint('max_expected_utility_next_doc IS NULL OR (max_expected_utility_next_doc >= 0 AND max_expected_utility_next_doc <= 1)', name='ck_trial_lit_state_utility_range'),
        sa.CheckConstraint("status::text = ANY (ARRAY['active','stopped','parked','promoted']::text[])", name='ck_trial_lit_state_status')
    )
    
    # 11. Create key indexes for performance
    # Core document indexes
    op.create_index('ix_documents_source_type_status', 'documents', ['source_type', 'status'])
    op.create_index('ix_documents_source_type_published', 'documents', ['source_type', 'published_at'])
    
    # Citation indexes
    op.create_index('ix_document_citations_journal_year', 'document_citations', ['journal', 'pub_year'])
    op.create_index('ix_document_citations_article_type', 'document_citations', ['article_type'])
    
    # Text indexes
    op.create_index('ix_document_text_abstract_length', 'document_text', ['char_count_abstract'])
    op.create_index('ix_document_text_fulltext_ttl', 'document_text', ['fulltext_ttl_date'])
    
    # PubMed-specific indexes
    op.create_index('ix_pubmed_meta_pmid', 'pubmed_meta', ['pmid'])
    op.create_index('ix_pmc_meta_pmcid', 'pmc_meta', ['pmcid'])
    
    # Trial-document relationship indexes
    op.create_index('ix_trial_doc_candidates_trial_stage', 'trial_doc_candidates', ['trial_id', 'stage'])
    op.create_index('ix_trial_doc_candidates_selected', 'trial_doc_candidates', ['selected'])
    
    # R/S scoring indexes
    op.create_index('ix_doc_rs_scores_trial_rs', 'doc_rs_scores', ['trial_id', 'R_tier', 'S_tier'])
    op.create_index('ix_doc_rs_scores_r_tier', 'doc_rs_scores', ['R_tier'])
    op.create_index('ix_doc_rs_scores_s_tier', 'doc_rs_scores', ['S_tier'])
    
    # Trial literature state indexes
    op.create_index('ix_trial_lit_state_status_best_s', 'trial_lit_state', ['status', 'best_S_Rge2'])
    op.create_index('ix_trial_lit_state_p_short', 'trial_lit_state', ['p_short'])
    op.create_index('ix_trial_lit_state_uncertainty', 'trial_lit_state', ['uncertainty'])
    
    # Entity extraction indexes
    op.create_index('ix_document_entities_literature', 'document_entities', ['ent_type', 'value_text'])
    op.create_index('ix_document_entities_phase', 'document_entities', ['ent_type', 'value_text'], postgresql_where=sa.text("ent_type = 'phase'"))
    op.create_index('ix_document_entities_effect_size', 'document_entities', ['ent_type', 'value_text'], postgresql_where=sa.text("ent_type = 'effect_size'"))
    
    # Link confidence indexes
    op.create_index('ix_document_links_confidence', 'document_links', ['link_type', 'confidence'])
    op.create_index('ix_document_links_trial_asset', 'document_links', ['trial_id', 'asset_id'])


def downgrade() -> None:
    """Remove PubMed literature processing system."""
    
    # Drop indexes
    op.drop_index('ix_document_links_trial_asset', 'document_links')
    op.drop_index('ix_document_links_confidence', 'document_links')
    op.drop_index('ix_document_entities_effect_size', 'document_entities')
    op.drop_index('ix_document_entities_phase', 'document_entities')
    op.drop_index('ix_document_entities_literature', 'document_entities')
    op.drop_index('ix_trial_lit_state_uncertainty', 'trial_lit_state')
    op.drop_index('ix_trial_lit_state_p_short', 'trial_lit_state')
    op.drop_index('ix_trial_lit_state_status_best_s', 'trial_lit_state')
    op.drop_index('ix_doc_rs_scores_s_tier', 'doc_rs_scores')
    op.drop_index('ix_doc_rs_scores_r_tier', 'doc_rs_scores')
    op.drop_index('ix_doc_rs_scores_trial_rs', 'doc_rs_scores')
    op.drop_index('ix_trial_doc_candidates_selected', 'trial_doc_candidates')
    op.drop_index('ix_trial_doc_candidates_trial_stage', 'trial_doc_candidates')
    op.drop_index('ix_pmc_meta_pmcid', 'pmc_meta')
    op.drop_index('ix_pubmed_meta_pmid', 'pubmed_meta')
    op.drop_index('ix_document_text_fulltext_ttl', 'document_text')
    op.drop_index('ix_document_text_abstract_length', 'document_text')
    op.drop_index('ix_document_citations_article_type', 'document_citations')
    op.drop_index('ix_document_citations_journal_year', 'document_citations')
    op.drop_index('ix_documents_source_type_published', 'documents')
    op.drop_index('ix_documents_source_type_status', 'documents')
    
    # Drop tables
    op.drop_table('trial_lit_state')
    op.drop_table('doc_rs_scores')
    op.drop_table('trial_doc_candidates')
    op.drop_table('pmc_meta')
    op.drop_table('pubmed_meta')
    op.drop_table('document_text')
    
    # Remove columns from document_citations
    op.drop_column('document_citations', 'substances_jsonb')
    op.drop_column('document_citations', 'mesh_jsonb')
    op.drop_column('document_citations', 'pub_year')
    op.drop_column('document_citations', 'article_type')
    op.drop_column('document_citations', 'pages')
    op.drop_column('document_citations', 'issue')
    op.drop_column('document_citations', 'volume')
    op.drop_column('document_citations', 'journal')
    
    # Note: Removing enum values is complex in PostgreSQL and may require manual cleanup
    # The following would need to be done manually if needed:
    # - Remove new entity types from entity_type_enum
    # - Remove new statuses from document_status_enum  
    # - Remove new source types from source_type_enum
