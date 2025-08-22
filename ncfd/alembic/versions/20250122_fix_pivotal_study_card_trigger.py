"""Fix pivotal study card trigger to prevent crashes

This migration fixes critical issues in the enforce_pivotal_study_card trigger:
1. Add JSONB array access guards to prevent crashes on null values
2. Implement robust integer parsing for strings like "842 participants"
3. Change from hard failures to warnings to prevent pipeline blocking
4. Add staging_errors table for failed validations

Revision ID: 20250122_fix_pivotal_study_card_trigger
Revises: 20250121_create_studies_table_and_guardrails
Create Date: 2025-01-22 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250122_fix_pivotal_study_card_trigger'
down_revision = '20250121_create_studies_table_and_guardrails'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create staging_errors table for failed validations
    op.create_table(
        'staging_errors',
        sa.Column('error_id', sa.BigInteger(), nullable=False),
        sa.Column('study_id', sa.BigInteger(), nullable=True),
        sa.Column('trial_id', sa.BigInteger(), nullable=True),
        sa.Column('error_type', sa.Text(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('extracted_jsonb', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('error_id'),
        sa.ForeignKeyConstraint(['study_id'], ['studies.study_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
    )
    
    # Create index on staging_errors
    op.create_index('ix_staging_errors_trial_id', 'staging_errors', ['trial_id'])
    op.create_index('ix_staging_errors_error_type', 'staging_errors', ['error_type'])
    op.create_index('ix_staging_errors_created_at', 'staging_errors', ['created_at'])
    
    # Fix the trigger function with proper guards and robust parsing
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_pivotal_study_card()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
          is_piv bool;
          card jsonb;
          total_n int;
          primary_count int;
          has_effect_or_p bool := false;
          error_details text[];
          error_msg text;
        BEGIN
          -- Check if trial is pivotal
          SELECT is_pivotal INTO is_piv FROM trials WHERE trial_id = NEW.trial_id;
          IF NOT is_piv THEN RETURN NEW; END IF;

          card := NEW.extracted_jsonb;
          IF card IS NULL THEN RETURN NEW; END IF;

          error_details := ARRAY[]::text[];

          -- Check primary endpoints with safe array access
          IF jsonb_typeof(card->'primary_endpoints') = 'array' THEN
            SELECT COALESCE(jsonb_array_length(card->'primary_endpoints'), 0) INTO primary_count;
          ELSE
            primary_count := 0;
          END IF;
          
          IF primary_count = 0 THEN
            error_details := array_append(error_details, 'primary_endpoints');
          END IF;

          -- Robust integer parsing for total_n
          BEGIN
            -- Try direct integer conversion first
            total_n := (card #>> '{sample_size,total_n}')::int;
          EXCEPTION WHEN OTHERS THEN
            -- Fallback: extract digits from string
            total_n := NULLIF(regexp_replace(
              COALESCE(card #>> '{sample_size,total_n}', '0'), 
              '[^0-9]', '', 'g'
            ), '')::int;
          END;
          
          IF total_n IS NULL THEN
            error_details := array_append(error_details, 'sample_size.total_n');
          END IF;

          -- Check analysis population
          IF card #>> '{populations,analysis_primary_on}' IS NULL THEN
            error_details := array_append(error_details, 'populations.analysis_primary_on');
          END IF;

          -- Safe array access for results.primary with proper guards
          IF jsonb_typeof(card->'results') = 'object' AND 
             jsonb_typeof(card->'results'->'primary') = 'array' THEN
            has_effect_or_p := EXISTS (
              SELECT 1
              FROM jsonb_array_elements(card->'results'->'primary') AS it(item)
              WHERE (it.item #>> '{effect_size,value}') IS NOT NULL
                 OR (it.item #>> '{p_value}') IS NOT NULL
            );
          ELSE
            has_effect_or_p := false;
          END IF;
          
          IF NOT has_effect_or_p THEN
            error_details := array_append(error_details, 'results.primary.(effect_size.value OR p_value)');
          END IF;

          -- If there are validation errors, log them instead of failing
          IF array_length(error_details, 1) > 0 THEN
            error_msg := 'PivotalStudyMissingFields: ' || array_to_string(error_details, ', ');
            
            -- Log error to staging_errors table
            INSERT INTO staging_errors (trial_id, error_type, error_message, extracted_jsonb)
            VALUES (NEW.trial_id, 'pivotal_validation', error_msg, NEW.extracted_jsonb);
            
            -- Log warning instead of raising exception
            RAISE WARNING '%', error_msg;
            
            -- Still allow the insert to proceed (for review queue)
            RETURN NEW;
          END IF;

          RETURN NEW;
        END $$;
    """)
    
    # Recreate trigger
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_pivotal_study_card ON public.studies;")
    op.execute("""
        CREATE TRIGGER trg_enforce_pivotal_study_card
          BEFORE INSERT OR UPDATE OF extracted_jsonb ON public.studies
          FOR EACH ROW
          EXECUTE FUNCTION enforce_pivotal_study_card();
    """)


def downgrade() -> None:
    # Restore original trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_pivotal_study_card()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
          is_piv bool;
          card jsonb;
          total_n int;
          primary_count int;
          has_effect_or_p bool := false;
        BEGIN
          SELECT is_pivotal INTO is_piv FROM trials WHERE trial_id = NEW.trial_id;
          IF NOT is_piv THEN RETURN NEW; END IF;

          card := NEW.extracted_jsonb;
          IF card IS NULL THEN RETURN NEW; END IF;

          SELECT COALESCE(jsonb_array_length(card->'primary_endpoints'),0)
          INTO primary_count;
          IF primary_count = 0 THEN
            RAISE EXCEPTION 'PivotalStudyMissingFields: primary_endpoints';
          END IF;

          total_n := (card #>> '{sample_size,total_n}')::int;
          IF total_n IS NULL THEN
            RAISE EXCEPTION 'PivotalStudyMissingFields: sample_size.total_n';
          END IF;

          IF card #>> '{populations,analysis_primary_on}' IS NULL THEN
            RAISE EXCEPTION 'PivotalStudyMissingFields: populations.analysis_primary_on';
          END IF;

          has_effect_or_p := EXISTS (
            SELECT 1
            FROM jsonb_array_elements(card->'results'->'primary') AS it(item)
            WHERE (it.item #>> '{effect_size,value}') IS NOT NULL
               OR (it.item #>> '{p_value}') IS NOT NULL
          );
          IF NOT has_effect_or_p THEN
            RAISE EXCEPTION 'PivotalStudyMissingFields: results.primary.(effect_size.value OR p_value)';
          END IF;

          RETURN NEW;
        END $$;
    """)
    
    # Recreate original trigger
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_pivotal_study_card ON public.studies;")
    op.execute("""
        CREATE TRIGGER trg_enforce_pivotal_study_card
          BEFORE INSERT OR UPDATE OF extracted_jsonb ON public.studies
          FOR EACH ROW
          EXECUTE FUNCTION enforce_pivotal_study_card();
    """)
    
    # Drop staging_errors table
    op.drop_index('ix_staging_errors_created_at', table_name='staging_errors')
    op.drop_index('ix_staging_errors_error_type', table_name='staging_errors')
    op.drop_index('ix_staging_errors_trial_id', table_name='staging_errors')
    op.drop_table('staging_errors')
