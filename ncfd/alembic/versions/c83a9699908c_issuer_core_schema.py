"""issuer core schema

Revision ID: c83a9699908c
Revises: dbe4ea2d9e57
Create Date: 2025-08-17 11:26:52.760435
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c83a9699908c"
down_revision: Union[str, Sequence[str], None] = "dbe4ea2d9e57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # --- Extensions ---
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # --- Enums ---
    security_status = postgresql.ENUM(
        "active", "delisted", "suspended", "pending", "acquired",
        name="security_status", create_type=False
    )
    security_status.create(op.get_bind(), checkfirst=True)

    security_type = postgresql.ENUM(
        "common", "adr", "preferred", "warrant", "unit", "right", "etf", "other",
        name="security_type", create_type=False
    )
    security_type.create(op.get_bind(), checkfirst=True)

    alias_type = postgresql.ENUM(
        "aka", "dba", "former_name", "short", "subsidiary", "brand", "domain", "other",
        name="alias_type", create_type=False
    )
    alias_type.create(op.get_bind(), checkfirst=True)

    # --- exchanges ---
    op.create_table(
        "exchanges",
        sa.Column("exchange_id", sa.Integer, primary_key=True),
        sa.Column("code", sa.Text, nullable=False, unique=True),
        sa.Column("mic", sa.Text, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("country", sa.Text, nullable=False, server_default="US"),
        sa.Column("is_allowed", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    # Seed whitelist (idempotent)
    op.execute(
        """
        INSERT INTO exchanges(code, mic, name, country, is_allowed) VALUES
          ('NASDAQ','XNAS','Nasdaq Stock Market','US',TRUE),
          ('NYSE','XNYS','New York Stock Exchange','US',TRUE),
          ('NYSE American','XASE','NYSE American','US',TRUE),
          ('OTCQX','OTCQ','OTC Markets OTCQX','US',TRUE),
          ('OTCQB','OTCQB','OTC Markets OTCQB','US',TRUE)
        ON CONFLICT (code) DO NOTHING
        """
    )

    # --- companies (ALTER existing minimal table from dbe4ea2d9e57) ---
    # Make name NOT NULL
    op.alter_column("companies", "name", existing_type=sa.String(), nullable=False)

    # Add new columns (table is empty on a fresh nuke, so we can add as NOT NULL where appropriate)
    op.add_column("companies", sa.Column("cik", sa.BigInteger(), nullable=False))
    op.add_column("companies", sa.Column("name_norm", sa.Text(), nullable=False))
    op.add_column("companies", sa.Column("state_incorp", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("country_incorp", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("sic", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("website_domain", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("lei", sa.Text(), nullable=True))
    op.add_column(
        "companies",
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column(
        "companies",
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column(
        "companies",
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )

    # Constraints & indexes on companies
    op.create_check_constraint("ck_companies_cik_range", "companies", "cik >= 1 AND cik <= 9999999999")
    op.create_unique_constraint("uq_companies_cik", "companies", ["cik"])
    op.create_index("idx_companies_name_norm", "companies", ["name_norm"], unique=False)

    # --- company_aliases ---
    op.create_table(
        "company_aliases",
        sa.Column("alias_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            sa.Integer,
            sa.ForeignKey("companies.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.Text, nullable=False),
        sa.Column("alias_norm", sa.Text, nullable=False),
        sa.Column("alias_type", alias_type, nullable=False),
        sa.Column("source", sa.Text),
        sa.Column("source_url", sa.Text),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column(
            "alias_company_id",
            sa.Integer,
            sa.ForeignKey("companies.company_id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "(confidence IS NULL) OR (confidence >= 0 AND confidence <= 1)",
            name="ck_alias_confidence",
        ),
    )
    op.create_index("idx_alias_norm", "company_aliases", ["alias_norm"], unique=False)
    op.create_unique_constraint(
        "uq_alias_by_company_norm_type", "company_aliases", ["company_id", "alias_norm", "alias_type"]
    )

    # --- securities ---
    op.create_table(
        "securities",
        sa.Column("security_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            sa.Integer,
            sa.ForeignKey("companies.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "exchange_id",
            sa.Integer,
            sa.ForeignKey("exchanges.exchange_id"),
            nullable=False,
        ),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("ticker_norm", sa.Text, nullable=False),
        sa.Column("type", security_type, nullable=False, server_default="common"),
        sa.Column("status", security_status, nullable=False, server_default="active"),
        sa.Column("is_primary_listing", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("effective_range", postgresql.DATERANGE(), nullable=False),
        sa.Column("currency", sa.Text, nullable=False, server_default="USD"),
        sa.Column("figi", sa.Text),
        sa.Column("cik", sa.BigInteger),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("ticker_norm = upper(ticker)", name="ck_ticker_norm_upper"),
    )
    op.create_index("idx_securities_ticker", "securities", ["ticker_norm"], unique=False)
    op.create_index("idx_securities_company", "securities", ["company_id"], unique=False)
    op.create_index("idx_securities_exchange", "securities", ["exchange_id"], unique=False)

    # Partial unique index: one active row per ticker globally
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_active_ticker_global
        ON securities (ticker_norm)
        WHERE status = 'active'
        """
    )

    # Exclusion constraint: no overlapping ranges for a ticker
    op.execute(
        """
        ALTER TABLE securities
        ADD CONSTRAINT ex_no_overlap_ticker
        EXCLUDE USING gist (
            ticker_norm WITH =,
            effective_range WITH &&
        )
        """
    )

    # Materialized view of allowed, active US listings
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS v_active_us_securities AS
        SELECT s.*, e.code AS exchange_code, e.mic
        FROM securities s
        JOIN exchanges e ON s.exchange_id = e.exchange_id
        WHERE s.status = 'active' AND e.is_allowed = TRUE
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # Drop MV first
    op.execute("DROP MATERIALIZED VIEW IF EXISTS v_active_us_securities")

    # securities
    op.execute("ALTER TABLE securities DROP CONSTRAINT IF EXISTS ex_no_overlap_ticker")
    op.execute("DROP INDEX IF EXISTS uq_active_ticker_global")
    op.drop_index("idx_securities_exchange", table_name="securities")
    op.drop_index("idx_securities_company", table_name="securities")
    op.drop_index("idx_securities_ticker", table_name="securities")
    op.drop_table("securities")

    # company_aliases
    op.drop_constraint("uq_alias_by_company_norm_type", "company_aliases", type_="unique")
    op.drop_index("idx_alias_norm", table_name="company_aliases")
    op.drop_table("company_aliases")

    # companies: drop added indexes/constraints/columns (keep original minimal table)
    op.drop_index("idx_companies_name_norm", table_name="companies")
    op.drop_constraint("uq_companies_cik", "companies", type_="unique")
    op.drop_constraint("ck_companies_cik_range", "companies", type_="check")
    op.drop_column("companies", "metadata")
    op.drop_column("companies", "updated_at")
    op.drop_column("companies", "created_at")
    op.drop_column("companies", "lei")
    op.drop_column("companies", "website_domain")
    op.drop_column("companies", "sic")
    op.drop_column("companies", "country_incorp")
    op.drop_column("companies", "state_incorp")
    op.drop_column("companies", "name_norm")
    op.drop_column("companies", "cik")
    op.alter_column("companies", "name", existing_type=sa.String(), nullable=True)

    # exchanges
    op.drop_table("exchanges")

    # enums (drop last)
    postgresql.ENUM(name="alias_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="security_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="security_status").drop(op.get_bind(), checkfirst=True)
