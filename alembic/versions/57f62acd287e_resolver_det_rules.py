"""resolver det rules

Revision ID: 57f62acd287e
Revises: 0272ed4ed4ec
Create Date: 2025-08-25 17:42:53.353044

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57f62acd287e'
down_revision: Union[str, Sequence[str], None] = '0272ed4ed4ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.create_table(
        "resolver_det_rules",
        sa.Column("rule_id", sa.Integer, primary_key=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("pattern", sa.Text, nullable=False),
        sa.Column("company_id", sa.Integer, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resolver_det_rules_priority "
        "ON resolver_det_rules (priority DESC, rule_id ASC)"
    )

def downgrade():
    op.drop_index("ix_resolver_det_rules_priority", table_name="resolver_det_rules")
    op.drop_table("resolver_det_rules")
