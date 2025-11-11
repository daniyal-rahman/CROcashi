"""add company risk metrics view

Revision ID: f1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2025-11-08 21:32:18.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create materialized view for company risk metrics
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS company_risk_metrics AS
        SELECT 
            c.company_id,
            c.name as company_name,
            COUNT(DISTINCT t.trial_id) as total_trials,
            COUNT(DISTINCT CASE 
                WHEN t.status IN ('ACTIVE', 'RECRUITING', 'ENROLLING_BY_INVITATION') 
                THEN t.trial_id 
            END) as active_trials,
            COUNT(DISTINCT CASE 
                WHEN t.status IN ('TERMINATED', 'WITHDRAWN', 'SUSPENDED') 
                THEN t.trial_id 
            END) as terminated_count,
            COUNT(DISTINCT CASE 
                WHEN t.phase_numeric = 1 AND t.status = 'COMPLETED' 
                THEN t.trial_id 
            END)::float / NULLIF(COUNT(DISTINCT CASE WHEN t.phase_numeric = 1 THEN t.trial_id END), 0) 
                as phase_1_success_rate,
            COUNT(DISTINCT CASE 
                WHEN t.phase_numeric = 2 AND t.status = 'COMPLETED' 
                THEN t.trial_id 
            END)::float / NULLIF(COUNT(DISTINCT CASE WHEN t.phase_numeric = 2 THEN t.trial_id END), 0) 
                as phase_2_success_rate,
            COUNT(DISTINCT CASE 
                WHEN t.phase_numeric = 3 AND t.status = 'COMPLETED' 
                THEN t.trial_id 
            END)::float / NULLIF(COUNT(DISTINCT CASE WHEN t.phase_numeric = 3 THEN t.trial_id END), 0) 
                as phase_3_success_rate,
            MAX(t.registration_date) as last_trial_registration_date,
            MAX(e.event_date) as last_pipeline_update_date
        FROM companies c
        LEFT JOIN trial_sponsors ts ON c.company_id = ts.entity_id 
            AND ts.entity_type = 'company'
            AND ts.deleted_at IS NULL
        LEFT JOIN clinical_trials t ON ts.trial_id = t.trial_id 
            AND t.deleted_at IS NULL
        LEFT JOIN events e ON e.entities_involved @> ARRAY[c.company_id]::uuid[]
            AND e.deleted_at IS NULL
        WHERE c.deleted_at IS NULL
        GROUP BY c.company_id, c.name;
    """)
    
    # Create unique index on company_id for fast lookups
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_company_risk_metrics_company_id 
        ON company_risk_metrics(company_id);
    """)
    
    # Create function to refresh the materialized view
    op.execute("""
        CREATE OR REPLACE FUNCTION refresh_company_risk_metrics()
        RETURNS void AS $$
        BEGIN
            REFRESH MATERIALIZED VIEW CONCURRENTLY company_risk_metrics;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Drop function
    op.execute("DROP FUNCTION IF EXISTS refresh_company_risk_metrics();")
    
    # Drop index
    op.execute("DROP INDEX IF EXISTS idx_company_risk_metrics_company_id;")
    
    # Drop materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS company_risk_metrics;")

