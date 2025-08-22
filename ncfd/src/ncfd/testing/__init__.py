"""
Testing and validation module for trial failure detection.

This module provides comprehensive testing utilities including synthetic data
generation, performance benchmarks, validation frameworks, and stress testing.
"""

from .synthetic_data import (
    SyntheticDataGenerator,
    generate_synthetic_study_card,
    generate_synthetic_trial_versions,
    generate_synthetic_historical_data,
    create_test_scenarios,
)

from .performance import (
    PerformanceBenchmark,
    benchmark_signal_evaluation,
    benchmark_gate_evaluation,
    benchmark_scoring_system,
    benchmark_full_pipeline,
)

from .validation import (
    ValidationFramework,
    validate_signal_accuracy,
    validate_gate_logic,
    validate_scoring_accuracy,
    cross_validate_system,
)

from .edge_cases import (
    EdgeCaseValidator,
    test_missing_data_scenarios,
    test_extreme_values,
    test_boundary_conditions,
    test_error_handling,
)

__all__ = [
    # Synthetic data generation
    "SyntheticDataGenerator",
    "generate_synthetic_study_card",
    "generate_synthetic_trial_versions",
    "generate_synthetic_historical_data",
    "create_test_scenarios",
    
    # Performance benchmarking
    "PerformanceBenchmark",
    "benchmark_signal_evaluation",
    "benchmark_gate_evaluation", 
    "benchmark_scoring_system",
    "benchmark_full_pipeline",
    
    # Validation framework
    "ValidationFramework",
    "validate_signal_accuracy",
    "validate_gate_logic",
    "validate_scoring_accuracy",
    "cross_validate_system",
    
    # Edge case testing
    "EdgeCaseValidator",
    "test_missing_data_scenarios",
    "test_extreme_values",
    "test_boundary_conditions",
    "test_error_handling",
]
