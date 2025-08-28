"""
Test Phase 5 Database Models

This test suite verifies that the new literature scoring and budget monitoring
models can be imported and used correctly.
"""

import pytest
from decimal import Decimal
from datetime import datetime, date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

# Import the models
from ncfd.db.models import (
    Base, Trial, Document, TrialEvaluation, DocumentUtility, 
    TrialPriorityQueue, CostRecord, BudgetPeriod
)


class TestPhase5Models:
    """Test the new Phase 5 database models."""
    
    def test_model_imports(self):
        """Test that all Phase 5 models can be imported successfully."""
        # This test will fail if there are any import errors
        assert TrialEvaluation is not None
        assert DocumentUtility is not None
        assert TrialPriorityQueue is not None
        assert CostRecord is not None
        assert BudgetPeriod is not None
    
    def test_trial_evaluation_model(self):
        """Test TrialEvaluation model structure."""
        # Check table name
        assert TrialEvaluation.__tablename__ == "trial_evaluations"
        
        # Check primary key
        assert hasattr(TrialEvaluation, 'evaluation_id')
        
        # Check required fields
        assert hasattr(TrialEvaluation, 'trial_id')
        assert hasattr(TrialEvaluation, 'run_id')
        assert hasattr(TrialEvaluation, 'evaluation_status')
        
        # Check optional fields
        assert hasattr(TrialEvaluation, 'prior_p_short')
        assert hasattr(TrialEvaluation, 'posterior_p_short')
        assert hasattr(TrialEvaluation, 'llm_evaluation_count')
        assert hasattr(TrialEvaluation, 'last_evaluation_at')
        assert hasattr(TrialEvaluation, 'evaluation_summary')
        assert hasattr(TrialEvaluation, 'metadata_jsonb')
        
        # Check timestamps
        assert hasattr(TrialEvaluation, 'created_at')
        assert hasattr(TrialEvaluation, 'updated_at')
    
    def test_document_utility_model(self):
        """Test DocumentUtility model structure."""
        # Check table name
        assert DocumentUtility.__tablename__ == "document_utilities"
        
        # Check primary key
        assert hasattr(DocumentUtility, 'utility_id')
        
        # Check required fields
        assert hasattr(DocumentUtility, 'doc_id')
        assert hasattr(DocumentUtility, 'trial_id')
        assert hasattr(DocumentUtility, 'run_id')
        assert hasattr(DocumentUtility, 'u0_score')
        
        # Check optional fields
        assert hasattr(DocumentUtility, 'u1_score')
        assert hasattr(DocumentUtility, 'uncertainty')
        assert hasattr(DocumentUtility, 'scoring_metadata')
        
        # Check timestamps
        assert hasattr(DocumentUtility, 'created_at')
        assert hasattr(DocumentUtility, 'updated_at')
    
    def test_trial_priority_queue_model(self):
        """Test TrialPriorityQueue model structure."""
        # Check table name
        assert TrialPriorityQueue.__tablename__ == "trial_priority_queue"
        
        # Check primary key
        assert hasattr(TrialPriorityQueue, 'queue_id')
        
        # Check required fields
        assert hasattr(TrialPriorityQueue, 'trial_id')
        assert hasattr(TrialPriorityQueue, 'run_id')
        assert hasattr(TrialPriorityQueue, 'priority_score')
        assert hasattr(TrialPriorityQueue, 'queue_status')
        
        # Check optional fields
        assert hasattr(TrialPriorityQueue, 'last_processed_at')
        assert hasattr(TrialPriorityQueue, 'processing_stage')
        assert hasattr(TrialPriorityQueue, 'queue_metadata')
        
        # Check stage completion flags
        assert hasattr(TrialPriorityQueue, 'stage_a_completed')
        assert hasattr(TrialPriorityQueue, 'stage_b_completed')
        assert hasattr(TrialPriorityQueue, 'stage_c_completed')
        
        # Check timestamps
        assert hasattr(TrialPriorityQueue, 'created_at')
        assert hasattr(TrialPriorityQueue, 'updated_at')
    
    def test_cost_record_model(self):
        """Test CostRecord model structure."""
        # Check table name
        assert CostRecord.__tablename__ == "cost_records"
        
        # Check primary key
        assert hasattr(CostRecord, 'cost_id')
        
        # Check required fields
        assert hasattr(CostRecord, 'transaction_id')
        assert hasattr(CostRecord, 'trial_id')
        assert hasattr(CostRecord, 'run_id')
        assert hasattr(CostRecord, 'operation_type')
        assert hasattr(CostRecord, 'cost_amount')
        
        # Check optional fields
        assert hasattr(CostRecord, 'operation_metadata')
        
        # Check timestamp
        assert hasattr(CostRecord, 'recorded_at')
    
    def test_budget_period_model(self):
        """Test BudgetPeriod model structure."""
        # Check table name
        assert BudgetPeriod.__tablename__ == "budget_periods"
        
        # Check primary key
        assert hasattr(BudgetPeriod, 'period_id')
        
        # Check required fields
        assert hasattr(BudgetPeriod, 'period_type')
        assert hasattr(BudgetPeriod, 'period_start')
        assert hasattr(BudgetPeriod, 'period_end')
        assert hasattr(BudgetPeriod, 'daily_limit')
        assert hasattr(BudgetPeriod, 'monthly_limit')
        assert hasattr(BudgetPeriod, 'trial_limit')
        assert hasattr(BudgetPeriod, 'total_spent')
        assert hasattr(BudgetPeriod, 'status')
        
        # Check timestamps
        assert hasattr(BudgetPeriod, 'created_at')
        assert hasattr(BudgetPeriod, 'updated_at')
    
    def test_trial_relationships(self):
        """Test that Trial model has the new relationships."""
        # Check that Trial has the new relationships
        assert hasattr(Trial, 'evaluations')
        assert hasattr(Trial, 'document_utilities')
        assert hasattr(Trial, 'priority_queue')
        assert hasattr(Trial, 'cost_records')
    
    def test_document_relationships(self):
        """Test that Document model has the new relationships."""
        # Check that Document has the new relationship
        assert hasattr(Document, 'utilities')
    
    def test_model_metadata(self):
        """Test that models have proper metadata."""
        # Check that all models inherit from Base
        assert issubclass(TrialEvaluation, Base)
        assert issubclass(DocumentUtility, Base)
        assert issubclass(TrialPriorityQueue, Base)
        assert issubclass(CostRecord, Base)
        assert issubclass(BudgetPeriod, Base)
        
        # Check that models have __tablename__
        assert hasattr(TrialEvaluation, '__tablename__')
        assert hasattr(DocumentUtility, '__tablename__')
        assert hasattr(TrialPriorityQueue, '__tablename__')
        assert hasattr(CostRecord, '__tablename__')
        assert hasattr(BudgetPeriod, '__tablename__')


class TestPhase5ModelConstraints:
    """Test the constraints and validation of Phase 5 models."""
    
    def test_trial_evaluation_constraints(self):
        """Test TrialEvaluation model constraints."""
        # Check that the model has table_args with constraints
        assert hasattr(TrialEvaluation, '__table_args__')
        table_args = TrialEvaluation.__table_args__
        
        # Should have indexes and constraints
        assert len(table_args) > 0
        
        # Check for unique constraint
        unique_constraints = [arg for arg in table_args if hasattr(arg, 'name') and 'uq_' in arg.name]
        assert len(unique_constraints) > 0
    
    def test_document_utility_constraints(self):
        """Test DocumentUtility model constraints."""
        # Check that the model has table_args with constraints
        assert hasattr(DocumentUtility, '__table_args__')
        table_args = DocumentUtility.__table_args__
        
        # Should have indexes and constraints
        assert len(table_args) > 0
        
        # Check for unique constraint
        unique_constraints = [arg for arg in table_args if hasattr(arg, 'name') and 'uq_' in arg.name]
        assert len(unique_constraints) > 0
    
    def test_trial_priority_queue_constraints(self):
        """Test TrialPriorityQueue model constraints."""
        # Check that the model has table_args with constraints
        assert hasattr(TrialPriorityQueue, '__table_args__')
        table_args = TrialPriorityQueue.__table_args__
        
        # Should have indexes and constraints
        assert len(table_args) > 0
        
        # Check for unique constraint
        unique_constraints = [arg for arg in table_args if hasattr(arg, 'name') and 'uq_' in arg.name]
        assert len(unique_constraints) > 0


class TestPhase5ModelIndexes:
    """Test the indexes of Phase 5 models."""
    
    def test_trial_evaluation_indexes(self):
        """Test TrialEvaluation model indexes."""
        table_args = TrialEvaluation.__table_args__
        
        # Check for indexes
        indexes = [arg for arg in table_args if hasattr(arg, 'name') and 'idx_' in arg.name]
        assert len(indexes) > 0
        
        # Should have indexes for common query patterns
        index_names = [idx.name for idx in indexes]
        assert any('trial_id' in name for name in index_names)
        assert any('run_id' in name for name in index_names)
    
    def test_document_utility_indexes(self):
        """Test DocumentUtility model indexes."""
        table_args = DocumentUtility.__table_args__
        
        # Check for indexes
        indexes = [arg for arg in table_args if hasattr(arg, 'name') and 'idx_' in arg.name]
        assert len(indexes) > 0
        
        # Should have indexes for common query patterns
        index_names = [idx.name for idx in indexes]
        assert any('doc_id' in name for name in index_names)
        assert any('trial_id' in name for name in index_names)
        assert any('u0_score' in name for name in index_names)
    
    def test_trial_priority_queue_indexes(self):
        """Test TrialPriorityQueue model indexes."""
        table_args = TrialPriorityQueue.__table_args__
        
        # Check for indexes
        indexes = [arg for arg in table_args if hasattr(arg, 'name') and 'idx_' in arg.name]
        assert len(indexes) > 0
        
        # Should have indexes for common query patterns
        index_names = [idx.name for idx in indexes]
        assert any('trial_id' in name for name in index_names)
        assert any('priority' in name for name in index_names)  # Changed from 'priority_score' to 'priority'
        assert any('queue_status' in name for name in index_names)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
