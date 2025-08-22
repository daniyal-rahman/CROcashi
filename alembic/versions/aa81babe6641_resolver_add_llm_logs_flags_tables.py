"""resolver: add llm logs + flags tables

Revision ID: aa81babe6641
Revises: 3e0f78bd8559
Create Date: 2025-08-20 21:19:23.632928

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql as psql

# revision identifiers, used by Alembic.
revision: str = 'aa81babe6641'
down_revision: Union[str, Sequence[str], None] = '3e0f78bd8559'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'resolver_llm_logs',
        sa.Column('llm_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('run_id', sa.Text(), nullable=False),
        sa.Column('nct_id', sa.Text(), nullable=False),
        sa.Column('sponsor_text', sa.Text(), nullable=False),
        sa.Column('candidates', psql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('response_json', psql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('decision_mode', sa.Text(), nullable=True),
        sa.Column('chosen_company_id', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.Numeric(6, 3), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("decision_mode in ('accept','review','reject')", name='resolver_llm_logs_mode_check'),
    )
    op.create_index('resolver_llm_logs_nct_idx', 'resolver_llm_logs', ['nct_id'])

    op.create_table(
        'resolver_flags',
        sa.Column('key', sa.Text(), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # seed the “probabilistic disabled” flag (idempotent)
    op.execute("""
        INSERT INTO resolver_flags(key, value)
        VALUES ('probabilistic_disabled','true')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """)

def downgrade() -> None:
    op.drop_table('resolver_flags')
    op.drop_index('resolver_llm_logs_nct_idx', table_name='resolver_llm_logs')
    op.drop_table('resolver_llm_logs')
