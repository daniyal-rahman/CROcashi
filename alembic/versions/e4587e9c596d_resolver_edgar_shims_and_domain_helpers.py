"""resolver_edgar_shims_and_domain_helpers

Revision ID: e4587e9c596d
Revises: 3e20e9a225d2
Create Date: 2025-08-18 12:39:57.640663

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4587e9c596d'
down_revision: Union[str, Sequence[str], None] = '3e20e9a225d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------
    # (A) Optional EDGAR shim schema + tables
    # -----------------------------------------
    op.execute("CREATE SCHEMA IF NOT EXISTS edgar")

    # filings
    op.create_table(
        "filings",
        sa.Column("cik", sa.Text(), nullable=True),
        sa.Column("form", sa.Text(), nullable=True),
        sa.Column("filed_at", sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column("accession_no", sa.Text(), primary_key=True),
        schema="edgar",
    )
    op.create_index("ix_edgar_filings_form", "filings", ["form"], unique=False, schema="edgar")
    op.create_index("ix_edgar_filings_filed_at", "filings", ["filed_at"], unique=False, schema="edgar")

    # documents
    op.create_table(
        "documents",
        sa.Column("accession_no", sa.Text(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("local_path", sa.Text(), nullable=True),
        schema="edgar",
    )
    op.create_index("ix_edgar_documents_acc", "documents", ["accession_no"], unique=False, schema="edgar")
    op.create_index("ix_edgar_documents_type", "documents", ["document_type"], unique=False, schema="edgar")

    # -----------------------------------------
    # (B) Domain alias acceleration
    # -----------------------------------------
    # Supports deterministic.domain matching: WHERE alias_type='domain' AND lower(alias)=...
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_company_aliases_domain_lower "
        "ON company_aliases (lower(alias)) WHERE alias_type='domain'"
    )

    # (C) Helper view for domain roots (company_aliases + companies.website_domain)
    op.execute(
        """
        CREATE OR REPLACE VIEW v_domain_aliases AS
        SELECT company_id, lower(alias) AS domain_root, 'alias'::text AS src
          FROM company_aliases
         WHERE alias_type = 'domain' AND alias IS NOT NULL AND alias <> ''
        UNION ALL
        SELECT company_id, lower(website_domain) AS domain_root, 'company'::text AS src
          FROM companies
         WHERE website_domain IS NOT NULL AND website_domain <> '';
        """
    )


def downgrade() -> None:
    # Drop helper view + index
    op.execute("DROP VIEW IF EXISTS v_domain_aliases")
    op.execute("DROP INDEX IF EXISTS ix_company_aliases_domain_lower")

    # Drop EDGAR shims (order: indexes via table drop, then tables, then schema)
    op.drop_index("ix_edgar_documents_type", table_name="documents", schema="edgar")
    op.drop_index("ix_edgar_documents_acc", table_name="documents", schema="edgar")
    op.drop_table("documents", schema="edgar")

    op.drop_index("ix_edgar_filings_filed_at", table_name="filings", schema="edgar")
    op.drop_index("ix_edgar_filings_form", table_name="filings", schema="edgar")
    op.drop_table("filings", schema="edgar")

    op.execute("DROP SCHEMA IF EXISTS edgar CASCADE")
