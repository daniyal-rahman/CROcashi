"""remove_deprecated_resolver_tables

Revision ID: 752afa19e084
Revises: 46e2cf011429
Create Date: 2025-09-20 10:39:30.285756

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '752afa19e084'
down_revision: Union[str, Sequence[str], None] = '46e2cf011429'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove deprecated resolver tables that are no longer referenced in the codebase."""
    
    connection = op.get_bind()
    
    # First, drop foreign key constraints that reference resolver_inputs
    fk_constraints_to_drop = [
        ('fk_resolver_features_input_id', 'resolver_features'),
        ('fk_resolver_decisions_input_id', 'resolver_decisions'),
        ('fk_resolver_candidate_snapshots_input_id_resolver_inputs', 'resolver_candidate_snapshots'),
        ('fk_resolver_llm_logs_input_id_resolver_inputs', 'resolver_llm_logs'),
        ('fk_review_queue_input_id', 'review_queue')
    ]
    
    for constraint_name, table_name in fk_constraints_to_drop:
        # Check if constraint exists before dropping
        result = connection.execute(sa.text("""
            SELECT EXISTS (
                SELECT FROM information_schema.table_constraints 
                WHERE constraint_schema = 'public' 
                AND constraint_name = :constraint_name
                AND table_name = :table_name
            )
        """), {"constraint_name": constraint_name, "table_name": table_name})
        
        constraint_exists = result.fetchone()[0]
        
        if constraint_exists:
            op.drop_constraint(constraint_name, table_name, type_='foreignkey')
            print(f"Dropped foreign key constraint: {constraint_name} from {table_name}")
    
    # Tables to remove (in dependency order to avoid foreign key conflicts)
    # Drop dependent tables first, then parent tables
    deprecated_tables = [
        'resolver_features',           # references resolver_inputs
        'resolver_decisions',          # references resolver_inputs  
        'resolver_candidate_snapshots', # references resolver_inputs
        'resolver_llm_logs',          # references resolver_inputs
        'resolver_overrides',         # references resolver_inputs
        'resolver_rules',             # references resolver_inputs
        'resolver_inputs',           # referenced by above tables
        'resolver_runs'              # referenced by resolver_inputs
    ]
    
    for table in deprecated_tables:
        # Check if table exists before dropping
        result = connection.execute(sa.text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = :table_name
            )
        """), {"table_name": table})
        
        table_exists = result.fetchone()[0]
        
        if table_exists:
            op.drop_table(table)
            print(f"Dropped deprecated table: {table}")


def downgrade() -> None:
    """Recreate the deprecated resolver tables (not recommended)."""
    
    # Note: This downgrade is not implemented because:
    # 1. These tables were deprecated and not used in the current codebase
    # 2. Recreating them would require restoring their original schema
    # 3. The data they contained was empty (0 rows each)
    # 4. They were part of a legacy resolver system that has been replaced
    
    # If you need to restore these tables, you would need to:
    # 1. Check the git history for their original schema
    # 2. Recreate them with the proper structure
    # 3. This is not recommended as they are no longer used
    
    raise NotImplementedError(
        "Downgrade not implemented for deprecated resolver tables. "
        "These tables were not referenced in the current codebase and contained no data. "
        "If restoration is needed, check git history for original schema."
    )
