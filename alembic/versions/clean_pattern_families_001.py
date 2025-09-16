"""Clean Pattern Families Migration - Remove Legacy, Add New System

Revision ID: clean_pattern_families_001
Revises: fe02bb9a421d
Create Date: 2025-01-15 00:00:00.000000

This migration:
1. Drops legacy S1-S9 signal system
2. Creates clean Pattern Families schema
3. Removes old gates and scoring tables
4. Implements elegant F1-F9 system

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql

# revision identifiers, used by Alembic.
revision: str = 'clean_pattern_families_001'
down_revision: Union[str, Sequence[str], None] = 'fe02bb9a421d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Clean migration to Pattern Families system."""
    
    # 1. Drop legacy tables (clean slate)
    _drop_legacy_tables()
    
    # 2. Create clean Pattern Families schema
    _create_pattern_families_schema()
    
    # 3. Create new scoring system
    _create_pattern_scoring_system()

def downgrade() -> None:
    """Rollback to legacy system."""
    
    # Drop new tables
    op.drop_table('pattern_scores')
    op.drop_table('pattern_detections')
    op.drop_table('pattern_families')
    
    # Recreate legacy tables (simplified)
    _recreate_legacy_tables()

def _drop_legacy_tables():
    """Drop all legacy signal/gate/scoring tables."""
    print("Dropping legacy tables...")
    
    # Drop in dependency order
    legacy_tables = [
        'signal_evidence',
        'signals', 
        'gates',
        'scores',
        'lr_tables'
    ]
    
    for table in legacy_tables:
        try:
            op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            print(f"Dropped table: {table}")
        except Exception as e:
            print(f"Could not drop {table}: {e}")

def _create_pattern_families_schema():
    """Create clean Pattern Families schema."""
    
    # Pattern Families Configuration
    op.create_table(
        'pattern_families',
        sa.Column('family_id', sa.String(2), nullable=False, primary_key=True),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
    )
    
    # Pattern Detections (LLM Results)
    op.create_table(
        'pattern_detections',
        sa.Column('detection_id', sa.BigInteger, nullable=False, autoincrement=True, primary_key=True),
        sa.Column('trial_id', sa.Integer, nullable=False),
        sa.Column('run_id', sa.String(50), nullable=False),
        sa.Column('family_id', sa.String(2), nullable=False),
        sa.Column('pattern_id', sa.String(4), nullable=False),  # F1P1, F1P2, etc.
        sa.Column('severity', sa.Integer, nullable=False),  # 0-3 scale
        sa.Column('confidence', sa.Numeric(3, 2), nullable=False),  # 0-1 scale
        sa.Column('rationale', sa.Text),
        sa.Column('evidence_spans', psql.JSONB),  # Array of {doc_id, snippet_hash, char_start, char_end}
        sa.Column('detected_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['family_id'], ['pattern_families.family_id'], ondelete='CASCADE'),
        
        # Constraints
        sa.CheckConstraint('severity >= 0 AND severity <= 3', name='ck_severity_range'),
        sa.CheckConstraint('confidence >= 0 AND confidence <= 1', name='ck_confidence_range'),
        
        # Indexes
        sa.Index('idx_pattern_detections_trial', 'trial_id'),
        sa.Index('idx_pattern_detections_family', 'family_id'),
        sa.Index('idx_pattern_detections_run', 'run_id'),
        sa.Index('idx_pattern_detections_severity', 'severity'),
    )
    
    # Insert Pattern Families data
    _insert_pattern_families_data()

def _create_pattern_scoring_system():
    """Create new Pattern Families scoring system."""
    
    op.create_table(
        'pattern_scores',
        sa.Column('score_id', sa.BigInteger, nullable=False, autoincrement=True, primary_key=True),
        sa.Column('trial_id', sa.Integer, nullable=False),
        sa.Column('run_id', sa.String(50), nullable=False),
        
        # LLM scoring
        sa.Column('p_fail_llm', sa.Numeric(5, 4)),  # LLM probability 0-1
        sa.Column('score_0_100', sa.Integer, nullable=False),  # Final blended score 0-100
        sa.Column('uncertainty', sa.Numeric(3, 2)),  # LLM uncertainty 0-1
        
        # Family contributions
        sa.Column('family_contributions', psql.JSONB),  # {F1: weight, F2: weight, ...}
        sa.Column('over_index', sa.Numeric(6, 3)),  # Over-index vs peers
        
        # Top contributing patterns
        sa.Column('top_patterns', psql.JSONB),  # Array of {pattern_id, severity, confidence}
        
        # Version tracking
        sa.Column('model_version', sa.String(50)),
        sa.Column('prompt_hash', sa.String(64)),
        
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        
        # Foreign key
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        
        # Constraints
        sa.CheckConstraint('p_fail_llm IS NULL OR (p_fail_llm >= 0 AND p_fail_llm <= 1)', name='ck_p_fail_llm_range'),
        sa.CheckConstraint('score_0_100 >= 0 AND score_0_100 <= 100', name='ck_score_0_100_range'),
        sa.CheckConstraint('uncertainty IS NULL OR (uncertainty >= 0 AND uncertainty <= 1)', name='ck_uncertainty_range'),
        
        # Indexes
        sa.Index('idx_pattern_scores_trial', 'trial_id'),
        sa.Index('idx_pattern_scores_run', 'run_id'),
        sa.Index('idx_pattern_scores_score', 'score_0_100'),
        sa.Index('idx_pattern_scores_created', 'created_at'),
    )

def _insert_pattern_families_data():
    """Insert Pattern Families configuration."""
    
    families = [
        ('F1', 'Endpoint Validity & Clinical Meaningfulness'),
        ('F2', 'Power & Analysis Robustness'),
        ('F3', 'Core Design Adequacy'),
        ('F4', 'Operational Integrity'),
        ('F5', 'Mechanistic & External Coherence'),
        ('F6', 'CMC / Dose / PK–PD Fitness'),
        ('F7', 'Safety/Tolerability Margin'),
        ('F8', 'Sponsor Incentives & Communications'),
        ('F9', 'Transparency & Reporting'),
    ]
    
    for family_id, name in families:
        op.execute(f"""
            INSERT INTO pattern_families (family_id, name) 
            VALUES ('{family_id}', '{name}')
        """)

def _recreate_legacy_tables():
    """Recreate simplified legacy tables for rollback."""
    
    # Simplified signals table
    op.create_table(
        'signals',
        sa.Column('signal_id', sa.BigInteger, nullable=False, autoincrement=True, primary_key=True),
        sa.Column('trial_id', sa.Integer, nullable=False),
        sa.Column('run_id', sa.String(50), nullable=False),
        sa.Column('s_id', sa.String(4), nullable=False),
        sa.Column('severity', sa.String(1), nullable=False),
        sa.Column('value', sa.Numeric(10, 6)),
        sa.Column('fired_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('metadata', psql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
    )
    
    # Simplified gates table
    op.create_table(
        'gates',
        sa.Column('gate_id', sa.BigInteger, nullable=False, autoincrement=True, primary_key=True),
        sa.Column('trial_id', sa.Integer, nullable=False),
        sa.Column('run_id', sa.String(50), nullable=False),
        sa.Column('g_id', sa.String(4), nullable=False),
        sa.Column('fired_bool', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('supporting_s_ids', psql.ARRAY(sa.Text)),
        sa.Column('lr_used', sa.Numeric(10, 6)),
        sa.Column('rationale_text', sa.Text),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
    )
    
    # Simplified scores table
    op.create_table(
        'scores',
        sa.Column('score_id', sa.BigInteger, nullable=False, autoincrement=True, primary_key=True),
        sa.Column('trial_id', sa.Integer, nullable=False),
        sa.Column('run_id', sa.String(50), nullable=False),
        sa.Column('prior_pi', sa.Numeric(5, 4)),
        sa.Column('logit_prior', sa.Numeric(10, 6)),
        sa.Column('sum_log_lr', sa.Numeric(10, 6)),
        sa.Column('logit_post', sa.Numeric(10, 6)),
        sa.Column('p_fail', sa.Numeric(5, 4)),
        sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
    )
