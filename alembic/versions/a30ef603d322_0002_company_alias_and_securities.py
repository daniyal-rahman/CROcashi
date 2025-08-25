"""0002 Company alias and securities

Revision ID: a30ef603d322
Revises: 9d2e40215ede
Create Date: 2025-08-24 21:15:14.970151

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a30ef603d322'
down_revision: Union[str, Sequence[str], None] = '9d2e40215ede'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    from alembic import op
    import sqlalchemy as sa

    # --- companies ---
    op.create_table(
        "companies",
        sa.Column("company_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_norm", sa.Text(), nullable=True),
        sa.Column("cik", sa.Text(), nullable=True),
        sa.Column("lei", sa.Text(), nullable=True),
        sa.Column("state_incorp", sa.VARCHAR(), nullable=True),
        sa.Column("country_incorp", sa.VARCHAR(), nullable=True),
        sa.Column("sic", sa.VARCHAR(), nullable=True),
        sa.Column("website_domain", sa.VARCHAR(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("company_id", name="pk_companies"),
    )
    # partial unique on cik where not null
    op.create_index(
        "uq_companies_cik",
        "companies",
        ["cik"],
        unique=True,
        postgresql_where=sa.text("cik IS NOT NULL"),
    )
    # search/helpful indexes
    op.create_index("idx_companies_website_domain", "companies", ["website_domain"])
    op.create_index(
        "idx_companies_name_trgm",
        "companies",
        ["name_norm"],
        postgresql_using="gin",
        postgresql_ops={"name_norm": "gin_trgm_ops"},
    )

    # --- company_aliases ---
    op.create_table(
        "company_aliases",
        sa.Column("alias_id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("alias_id", name="pk_company_aliases"),
    )
    op.create_index("idx_company_aliases_company", "company_aliases", ["company_id"])
    op.create_index(
        "idx_company_aliases_alias_trgm",
        "company_aliases",
        ["alias"],
        postgresql_using="gin",
        postgresql_ops={"alias": "gin_trgm_ops"},
    )

    # --- securities ---
    op.create_table(
        "securities",
        sa.Column("security_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("exchange", sa.VARCHAR(), nullable=False),
        sa.Column("is_adr", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "exchange IN ('NASDAQ','NYSE','NYSE_AM','OTCQX','OTCQB')",
            name="ck_securities_exchange",
        ),
        sa.UniqueConstraint("ticker", name="uq_securities_ticker"),
        sa.PrimaryKeyConstraint("security_id", name="pk_securities"),
    )
    op.create_index("idx_securities_company", "securities", ["company_id"])
    op.create_index("idx_securities_exchange", "securities", ["exchange"])


def downgrade() -> None:
    from alembic import op

    # drop in reverse dependency order; indexes/constraints drop with tables
    op.drop_table("securities")
    op.drop_table("company_aliases")
    op.drop_table("companies")
