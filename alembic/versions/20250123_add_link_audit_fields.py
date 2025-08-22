"""Add new fields to link_audit table

This migration adds label, label_source, reviewed_by, reviewed_at fields for precision validation.
This was previously applied manually via SQL script.

Revision ID: 20250123_add_link_audit_fields
Revises: 20250123_add_storage_objects_and_references
Create Date: 2025-01-23 17:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250123_add_link_audit_fields'
down_revision = '20250123_add_storage_objects_and_references'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to link_audit table
    op.execute("""
        ALTER TABLE link_audit 
        ADD COLUMN IF NOT EXISTS label BOOLEAN,
        ADD COLUMN IF NOT EXISTS label_source TEXT,
        ADD COLUMN IF NOT EXISTS reviewed_by TEXT;
    """)
    
    # Add reviewed_at column (already exists, but ensure it's properly typed)
    # Note: reviewed_at column already exists in the model, so this is just for safety
    
    # Add indexes for the new fields
    op.create_index('ix_link_audit_label', 'link_audit', ['label'])
    op.create_index('ix_link_audit_reviewed_at', 'link_audit', ['reviewed_at'])
    
    # Add comments to document the new fields
    op.execute("""
        COMMENT ON COLUMN link_audit.label IS 'True=correct, False=incorrect, NULL=unreviewed';
        COMMENT ON COLUMN link_audit.label_source IS 'Source of label: human_review, gold_standard, external_validation';
        COMMENT ON COLUMN link_audit.reviewed_by IS 'Username or system identifier of reviewer';
        COMMENT ON COLUMN link_audit.reviewed_at IS 'When review was completed';
    """)
    
    # Create a view for easy precision calculation
    op.execute("""
        CREATE OR REPLACE VIEW heuristic_precision_summary AS
        SELECT 
            heuristic_applied,
            COUNT(*) as total_links,
            COUNT(CASE WHEN label = true THEN 1 END) as correct_links,
            COUNT(CASE WHEN label = false THEN 1 END) as incorrect_links,
            COUNT(CASE WHEN label IS NULL THEN 1 END) as unreviewed_links,
            CASE 
                WHEN COUNT(CASE WHEN label IS NOT NULL THEN 1 END) > 0 
                THEN ROUND(
                    COUNT(CASE WHEN label = true THEN 1 END)::numeric / 
                    COUNT(CASE WHEN label IS NOT NULL THEN 1 END)::numeric, 
                    4
                )
                ELSE NULL 
            END as precision_rate
        FROM link_audit 
        WHERE heuristic_applied IS NOT NULL
        GROUP BY heuristic_applied
        ORDER BY heuristic_applied;
    """)
    
    # Create a function to calculate precision for a specific heuristic
    op.execute("""
        CREATE OR REPLACE FUNCTION get_heuristic_precision(
            p_heuristic TEXT,
            p_start_date TIMESTAMPTZ DEFAULT NULL,
            p_end_date TIMESTAMPTZ DEFAULT NULL
        ) RETURNS TABLE(
            heuristic TEXT,
            total_links BIGINT,
            reviewed_links BIGINT,
            correct_links BIGINT,
            incorrect_links BIGINT,
            unreviewed_links BIGINT,
            precision_rate NUMERIC(5,4)
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                la.heuristic_applied as heuristic,
                COUNT(*)::BIGINT as total_links,
                COUNT(CASE WHEN la.label IS NOT NULL THEN 1 END)::BIGINT as reviewed_links,
                COUNT(CASE WHEN la.label = true THEN 1 END)::BIGINT as correct_links,
                COUNT(CASE WHEN la.label = false THEN 1 END)::BIGINT as incorrect_links,
                COUNT(CASE WHEN la.label IS NULL THEN 1 END)::BIGINT as unreviewed_links,
                CASE 
                    WHEN COUNT(CASE WHEN la.label IS NOT NULL THEN 1 END) > 0 
                    THEN ROUND(
                        COUNT(CASE WHEN la.label = true THEN 1 END)::numeric / 
                        COUNT(CASE WHEN la.label IS NOT NULL THEN 1 END)::numeric, 
                        4
                    )
                    ELSE NULL 
                END as precision_rate
            FROM link_audit la
            WHERE la.heuristic_applied = p_heuristic
                AND (p_start_date IS NULL OR la.created_at >= p_start_date)
                AND (p_end_date IS NULL OR la.created_at <= p_end_date)
            GROUP BY la.heuristic_applied;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create a function to check if auto-promotion is allowed for a heuristic
    op.execute("""
        CREATE OR REPLACE FUNCTION can_auto_promote_heuristic(
            p_heuristic TEXT,
            p_min_precision NUMERIC DEFAULT 0.95,
            p_min_links INTEGER DEFAULT 50
        ) RETURNS BOOLEAN AS $$
        DECLARE
            v_precision_data RECORD;
        BEGIN
            -- Get precision data for the heuristic
            SELECT * INTO v_precision_data
            FROM get_heuristic_precision(p_heuristic)
            LIMIT 1;
            
            -- Check if we have sufficient data
            IF v_precision_data.total_links < p_min_links THEN
                RETURN FALSE;
            END IF;
            
            -- Check if precision meets threshold
            IF v_precision_data.precision_rate IS NULL OR v_precision_data.precision_rate < p_min_precision THEN
                RETURN FALSE;
            END IF;
            
            RETURN TRUE;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS can_auto_promote_heuristic(TEXT, NUMERIC, INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS get_heuristic_precision(TEXT, TIMESTAMPTZ, TIMESTAMPTZ)")
    
    # Drop view
    op.execute("DROP VIEW IF EXISTS heuristic_precision_summary")
    
    # Drop indexes
    op.drop_index('ix_link_audit_reviewed_at', table_name='link_audit')
    op.drop_index('ix_link_audit_label', table_name='link_audit')
    
    # Drop columns
    op.execute("""
        ALTER TABLE link_audit 
        DROP COLUMN IF EXISTS label,
        DROP COLUMN IF EXISTS label_source,
        DROP COLUMN IF EXISTS reviewed_by;
    """)
