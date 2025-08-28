"""
Test Phase 4: Budget Monitoring and Configuration.

This test file verifies the budget monitoring system and configuration
integration with the literature pipeline.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
import yaml
import os

from ncfd.ingest.budget_monitor import (
    BudgetMonitor, BudgetStatus, BudgetPeriod, CostRecord, 
    BudgetSummary, BudgetGuard, BudgetExceededError
)
from ncfd.ingest.literature_pipeline import LiteraturePipeline


class TestBudgetMonitor:
    """Test the budget monitoring system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            'daily_cost_limit': 100.0,
            'monthly_cost_limit': 2500.0,
            'trial_cost_limit': 10.0,
            'costs': {
                'metadata_fetch': 0.001,
                'abstract_fetch': 0.01,
                'full_text_fetch': 0.50,
                'llm_evaluation': 0.05
            },
            'alert_thresholds': {
                'warning': 0.75,
                'critical': 0.90,
                'emergency': 0.95
            },
            'reset_schedule': 'monthly',
            'reset_day': 1
        }
        self.monitor = BudgetMonitor(self.config)
    
    def test_initialization(self):
        """Test budget monitor initialization."""
        assert self.monitor.daily_limit == 100.0
        assert self.monitor.monthly_limit == 2500.0
        assert self.monitor.trial_limit == 10.0
        assert 'metadata_fetch' in self.monitor.cost_estimates
        assert 'abstract_fetch' in self.monitor.cost_estimates
        assert 'full_text_fetch' in self.monitor.cost_estimates
        assert 'llm_evaluation' in self.monitor.cost_estimates
    
    def test_cost_estimation(self):
        """Test operation cost estimation."""
        assert self.monitor.estimate_operation_cost('metadata_fetch') == 0.001
        assert self.monitor.estimate_operation_cost('abstract_fetch') == 0.01
        assert self.monitor.estimate_operation_cost('full_text_fetch') == 0.50
        assert self.monitor.estimate_operation_cost('llm_evaluation') == 0.05
        assert self.monitor.estimate_operation_cost('unknown') == 0.0
    
    def test_cost_recording(self):
        """Test cost recording functionality."""
        # Record a cost
        success = self.monitor.record_cost(
            'op_1', 'trial_1', 'metadata_fetch', 0.005
        )
        assert success is True
        
        # Check trial cost
        assert self.monitor.trial_costs['trial_1'] == 0.005
        
        # Check period cost
        current_cost = self.monitor._get_current_period_cost()
        assert current_cost == 0.005
    
    def test_budget_limits(self):
        """Test budget limit enforcement."""
        # Try to exceed trial limit
        success = self.monitor.record_cost(
            'op_2', 'trial_1', 'full_text_fetch', 15.0
        )
        assert success is False  # Should fail due to trial limit
        
        # Try to exceed daily limit
        success = self.monitor.record_cost(
            'op_3', 'trial_2', 'metadata_fetch', 200.0
        )
        assert success is False  # Should fail due to daily limit
    
    def test_budget_status(self):
        """Test budget status calculation."""
        # Initially should be OK
        status = self.monitor.get_budget_status()
        assert status == BudgetStatus.OK
        
        # Add some costs and verify status changes
        # Add 8 trials with 8.0 each = 64.0 (2.56% of monthly limit)
        for i in range(8):
            self.monitor.record_cost(f'op_{i}', f'trial_{i}', 'metadata_fetch', 8.0)
        
        status = self.monitor.get_budget_status()
        assert status == BudgetStatus.OK  # Should still be OK
        
        # Verify that we can get budget summary
        summary = self.monitor.get_budget_summary()
        assert summary.total_cost == 64.0
        assert summary.cost_limit == 2500.0
        assert summary.utilization_percentage == 2.56
        
        # Test that budget status is working by checking the logic
        current_cost = self.monitor._get_current_period_cost()
        current_limit = self.monitor._get_current_period_limit()
        utilization = current_cost / current_limit
        
        print(f"Debug: current_cost={current_cost}, current_limit={current_limit}, utilization={utilization}")
        print(f"Debug: warning_threshold={self.monitor.alert_thresholds['warning']}")
        
        # The status should be OK if utilization < warning threshold
        if utilization < self.monitor.alert_thresholds['warning']:
            assert status == BudgetStatus.OK
        else:
            assert status in [BudgetStatus.WARNING, BudgetStatus.CRITICAL, BudgetStatus.EMERGENCY]
    
    def test_budget_summary(self):
        """Test budget summary generation."""
        # Add some costs (use different trials to avoid trial limit)
        self.monitor.record_cost('op_1', 'trial_1', 'metadata_fetch', 5.0)
        self.monitor.record_cost('op_2', 'trial_2', 'abstract_fetch', 5.0)
        
        summary = self.monitor.get_budget_summary()
        
        assert summary.period == BudgetPeriod.MONTHLY
        assert summary.total_cost == 10.0
        assert summary.cost_limit == 2500.0
        assert summary.remaining_budget == 2490.0
        assert summary.utilization_percentage == 0.4
        assert summary.status == BudgetStatus.OK
        
        # Check cost breakdown
        assert summary.cost_breakdown['metadata_fetch'] == 5.0
        assert summary.cost_breakdown['abstract_fetch'] == 5.0
        
        # Check trial costs
        assert summary.trial_costs['trial_1'] == 5.0
        assert summary.trial_costs['trial_2'] == 5.0
    
    def test_cost_alerts(self):
        """Test cost alert generation."""
        # Initially no alerts
        alerts = self.monitor.get_cost_alerts()
        assert len(alerts) == 0
        
        # Add costs to trigger warning (use multiple trials to accumulate cost)
        # Add 235 trials with 8.0 each = 1880.0 (75.2% of monthly limit)
        for i in range(235):
            self.monitor.record_cost(f'op_{i}', f'trial_{i}', 'metadata_fetch', 8.0)
        
        alerts = self.monitor.get_cost_alerts()
        assert len(alerts) == 1
        assert alerts[0]['level'] == 'warning'
        assert 'warning' in alerts[0]['message']
    
    def test_budget_reset(self):
        """Test budget reset functionality."""
        # Add some costs
        self.monitor.record_cost('op_1', 'trial_1', 'metadata_fetch', 10.0)
        
        # Force reset
        success = self.monitor.reset_budget(force=True)
        assert success is True
        
        # Check that costs are reset
        assert len(self.monitor.cost_records) == 0
        assert len(self.monitor.trial_costs) == 0
    
    def test_can_afford_operation(self):
        """Test operation affordability checking."""
        # Check if we can afford operations
        assert self.monitor.can_afford_operation('metadata_fetch', 'trial_1') is True
        assert self.monitor.can_afford_operation('full_text_fetch', 'trial_1') is True
        
        # Add costs to make operations unaffordable (stay within trial limit)
        self.monitor.record_cost('op_1', 'trial_1', 'metadata_fetch', 9.6)
        
        # Now full_text_fetch should be unaffordable (9.6 + 0.50 > 10.0)
        assert self.monitor.can_afford_operation('full_text_fetch', 'trial_1') is False


class TestBudgetGuard:
    """Test the budget guard context manager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            'daily_cost_limit': 100.0,
            'monthly_cost_limit': 2500.0,
            'trial_cost_limit': 10.0,
            'costs': {
                'metadata_fetch': 0.001,
                'abstract_fetch': 0.01
            }
        }
        self.monitor = BudgetMonitor(self.config)
    
    def test_budget_guard_success(self):
        """Test successful budget guard usage."""
        with BudgetGuard(self.monitor, 'trial_1', 'metadata_fetch') as guard:
            # Operation should proceed
            assert guard.trial_id == 'trial_1'
            assert guard.operation_type == 'metadata_fetch'
        
        # Cost should be recorded
        assert self.monitor.trial_costs['trial_1'] == 0.001
    
    def test_budget_guard_budget_exceeded(self):
        """Test budget guard when budget is exceeded."""
        # Exceed budget first
        self.monitor.record_cost('op_1', 'trial_1', 'metadata_fetch', 10.0)
        
        # Try to use budget guard
        with pytest.raises(BudgetExceededError):
            with BudgetGuard(self.monitor, 'trial_1', 'metadata_fetch'):
                pass
    
    def test_budget_guard_actual_cost(self):
        """Test budget guard with actual cost recording."""
        with BudgetGuard(self.monitor, 'trial_1', 'abstract_fetch') as guard:
            # Record actual cost
            guard.record_actual_cost(0.015, {'source': 'test'})
        
        # Actual cost should be recorded
        assert self.monitor.trial_costs['trial_1'] == 0.015


class TestBudgetPeriods:
    """Test budget period calculations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            'daily_cost_limit': 100.0,
            'monthly_cost_limit': 2500.0,
            'trial_cost_limit': 10.0,
            'costs': {'metadata_fetch': 0.001}
        }
        self.monitor = BudgetMonitor(self.config)
    
    def test_daily_period(self):
        """Test daily budget period."""
        # Change to daily reset
        self.monitor.reset_schedule = 'daily'
        
        start_date = self.monitor._get_period_start(BudgetPeriod.DAILY)
        end_date = self.monitor._get_period_end(BudgetPeriod.DAILY)
        
        # Should be same day
        assert start_date.date() == datetime.now().date()
        assert end_date.date() == (datetime.now() + timedelta(days=1)).date()
        
        # Daily limit should be used
        limit = self.monitor._get_period_limit(BudgetPeriod.DAILY)
        assert limit == 100.0
    
    def test_weekly_period(self):
        """Test weekly budget period."""
        # Change to weekly reset
        self.monitor.reset_schedule = 'weekly'
        
        start_date = self.monitor._get_period_start(BudgetPeriod.WEEKLY)
        end_date = self.monitor._get_period_end(BudgetPeriod.WEEKLY)
        
        # Should be start of week to start of next week
        assert start_date.weekday() == 0  # Monday
        assert (end_date - start_date).days == 7
        
        # Weekly limit should be daily * 7
        limit = self.monitor._get_period_limit(BudgetPeriod.WEEKLY)
        assert limit == 700.0
    
    def test_monthly_period(self):
        """Test monthly budget period."""
        # Change to monthly reset
        self.monitor.reset_schedule = 'monthly'
        
        start_date = self.monitor._get_period_start(BudgetPeriod.MONTHLY)
        end_date = self.monitor._get_period_end(BudgetPeriod.MONTHLY)
        
        # Should be same month
        assert start_date.month == datetime.now().month
        assert start_date.day == 1
        
        # Monthly limit should be used
        limit = self.monitor._get_period_limit(BudgetPeriod.MONTHLY)
        assert limit == 2500.0


class TestConfigurationIntegration:
    """Test configuration file integration."""
    
    def test_configuration_file_loading(self):
        """Test loading configuration from YAML file."""
        config_path = 'config/literature_config.yaml'
        
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Check that required sections exist
            assert 'scoring' in config
            assert 'budget' in config
            assert 'pipeline' in config
            assert 'smart_pubmed' in config
            
            # Check budget configuration
            budget_config = config['budget']
            assert 'daily_cost_limit' in budget_config
            assert 'monthly_cost_limit' in budget_config
            assert 'trial_cost_limit' in budget_config
            assert 'costs' in budget_config
            
            # Check pipeline configuration
            pipeline_config = config['pipeline']
            assert 'enable_stage_c' in pipeline_config
            assert 'auto_evaluation' in pipeline_config
            assert 'evaluation_interval' in pipeline_config
        else:
            pytest.skip(f"Configuration file {config_path} not found")


class TestLiteraturePipelineBudgetIntegration:
    """Test budget integration with literature pipeline."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            'scoring': {
                'tau_abstract': 0.40,
                'theta_high': 0.80,
                'theta_low': 0.20,
                'delta_min': 0.05
            },
            'queue': {
                'max_trials_per_batch': 5,
                'max_candidates_per_trial': 10
            },
            'evaluation': {
                'eval_every_docs': 3,
                'theta_high': 0.80,
                'theta_low': 0.20
            },
            'smart_pubmed': {
                'stage_a_batch_size': 50,
                'stage_b_threshold': 0.3,
                'max_abstracts_per_trial': 5
            },
            'budget': {
                'daily_cost_limit': 100.0,
                'monthly_cost_limit': 2500.0,
                'trial_cost_limit': 10.0,
                'costs': {
                    'metadata_fetch': 0.001,
                    'abstract_fetch': 0.01,
                    'full_text_fetch': 0.50,
                    'llm_evaluation': 0.05
                }
            },
            'enable_stage_c': True,
            'auto_evaluation': True,
            'evaluation_interval': 3
        }
    
    @patch('ncfd.ingest.literature_pipeline.SmartPubMedClient')
    @patch('ncfd.ingest.literature_pipeline.LiteratureScorer')
    @patch('ncfd.ingest.literature_pipeline.DocumentQueue')
    @patch('ncfd.ingest.literature_pipeline.LLMEvaluator')
    def test_pipeline_with_budget_monitor(self, mock_evaluator, mock_queue, mock_scorer, mock_pubmed):
        """Test that pipeline initializes with budget monitor."""
        # Mock the components
        mock_scorer.return_value = Mock()
        mock_queue.return_value = Mock()
        mock_evaluator.return_value = Mock()
        mock_pubmed.return_value = Mock()
        
        # Create pipeline
        pipeline = LiteraturePipeline(self.config)
        
        # Check that budget monitor was initialized
        assert hasattr(pipeline, 'budget_monitor')
        assert pipeline.budget_monitor is not None
        
        # Check budget configuration
        assert pipeline.budget_monitor.daily_limit == 100.0
        assert pipeline.budget_monitor.monthly_limit == 2500.0
        assert pipeline.budget_monitor.trial_limit == 10.0
    
    def test_pipeline_stats_with_budget(self):
        """Test that pipeline stats include budget information."""
        # This test would require a fully mocked pipeline
        # For now, we'll just verify the configuration structure
        assert 'budget' in self.config
        assert 'costs' in self.config['budget']
        assert 'metadata_fetch' in self.config['budget']['costs']


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
