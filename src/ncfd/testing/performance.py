"""
Performance benchmarking for trial failure detection system.

This module provides comprehensive performance testing utilities to benchmark
signal evaluation, gate logic, scoring system, and the complete pipeline.
"""

import time
import psutil
import gc
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime
import statistics
import json

from ..signals import evaluate_all_signals, evaluate_all_gates
from ..scoring import ScoringEngine, score_single_trial, batch_score_trials
from .synthetic_data import SyntheticDataGenerator, create_test_scenarios


@dataclass
class PerformanceMetrics:
    """Performance measurement results."""
    operation_name: str
    total_time: float  # seconds
    avg_time_per_item: float  # seconds
    items_per_second: float
    memory_peak_mb: float
    memory_delta_mb: float
    cpu_percent: float
    total_items: int
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class BenchmarkResult:
    """Complete benchmark result."""
    benchmark_name: str
    start_time: datetime
    end_time: datetime
    total_duration: float
    metrics: List[PerformanceMetrics]
    system_info: Dict[str, Any]
    configuration: Dict[str, Any]


class PerformanceBenchmark:
    """Comprehensive performance benchmarking system."""
    
    def __init__(self, warmup_iterations: int = 10):
        """
        Initialize the performance benchmark.
        
        Args:
            warmup_iterations: Number of warmup iterations before measurement
        """
        self.warmup_iterations = warmup_iterations
        self.generator = SyntheticDataGenerator(seed=42)  # Reproducible data
        
    def run_comprehensive_benchmark(self, 
                                  sizes: Optional[List[int]] = None) -> BenchmarkResult:
        """
        Run comprehensive benchmark across all system components.
        
        Args:
            sizes: List of dataset sizes to test
            
        Returns:
            Complete benchmark result
        """
        if sizes is None:
            sizes = [10, 50, 100, 500, 1000]
        
        start_time = datetime.now()
        metrics = []
        
        print("🚀 Starting Comprehensive Performance Benchmark")
        print("=" * 60)
        
        # Benchmark signal evaluation
        print("\n📊 Benchmarking Signal Evaluation...")
        for size in sizes:
            metric = self.benchmark_signal_evaluation(size)
            metrics.append(metric)
            print(f"  {size:4d} trials: {metric.avg_time_per_item*1000:.2f}ms/trial, "
                  f"{metric.items_per_second:.0f} trials/sec")
        
        # Benchmark gate evaluation  
        print("\n🚪 Benchmarking Gate Evaluation...")
        for size in sizes:
            metric = self.benchmark_gate_evaluation(size)
            metrics.append(metric)
            print(f"  {size:4d} trials: {metric.avg_time_per_item*1000:.2f}ms/trial, "
                  f"{metric.items_per_second:.0f} trials/sec")
        
        # Benchmark scoring system
        print("\n🎯 Benchmarking Scoring System...")
        for size in sizes:
            metric = self.benchmark_scoring_system(size)
            metrics.append(metric)
            print(f"  {size:4d} trials: {metric.avg_time_per_item*1000:.2f}ms/trial, "
                  f"{metric.items_per_second:.0f} trials/sec")
        
        # Benchmark full pipeline
        print("\n🔄 Benchmarking Full Pipeline...")
        for size in sizes:
            metric = self.benchmark_full_pipeline(size)
            metrics.append(metric)
            print(f"  {size:4d} trials: {metric.avg_time_per_item*1000:.2f}ms/trial, "
                  f"{metric.items_per_second:.0f} trials/sec")
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        print(f"\n✅ Benchmark completed in {total_duration:.2f} seconds")
        
        return BenchmarkResult(
            benchmark_name="Comprehensive Performance Benchmark",
            start_time=start_time,
            end_time=end_time,
            total_duration=total_duration,
            metrics=metrics,
            system_info=self._get_system_info(),
            configuration={
                "warmup_iterations": self.warmup_iterations,
                "sizes_tested": sizes,
                "generator_seed": 42
            }
        )
    
    def benchmark_signal_evaluation(self, num_trials: int) -> PerformanceMetrics:
        """
        Benchmark signal evaluation performance.
        
        Args:
            num_trials: Number of trials to process
            
        Returns:
            Performance metrics for signal evaluation
        """
        # Generate test data
        study_cards = [
            self.generator.generate_study_card() 
            for _ in range(num_trials)
        ]
        
        # Warmup
        for _ in range(min(self.warmup_iterations, num_trials)):
            evaluate_all_signals(study_cards[0])
        
        # Benchmark
        return self._measure_performance(
            operation_name=f"Signal_Evaluation_{num_trials}",
            operation_func=lambda: [evaluate_all_signals(card) for card in study_cards],
            num_items=num_trials
        )
    
    def benchmark_gate_evaluation(self, num_trials: int) -> PerformanceMetrics:
        """
        Benchmark gate evaluation performance.
        
        Args:
            num_trials: Number of trials to process
            
        Returns:
            Performance metrics for gate evaluation
        """
        # Generate test data with signals
        test_data = []
        for _ in range(num_trials):
            study_card = self.generator.generate_study_card()
            signals = evaluate_all_signals(study_card)
            test_data.append(signals)
        
        # Warmup
        for _ in range(min(self.warmup_iterations, num_trials)):
            evaluate_all_gates(test_data[0])
        
        # Benchmark
        return self._measure_performance(
            operation_name=f"Gate_Evaluation_{num_trials}",
            operation_func=lambda: [evaluate_all_gates(signals) for signals in test_data],
            num_items=num_trials
        )
    
    def benchmark_scoring_system(self, num_trials: int) -> PerformanceMetrics:
        """
        Benchmark scoring system performance.
        
        Args:
            num_trials: Number of trials to process
            
        Returns:
            Performance metrics for scoring system
        """
        # Generate test data
        engine = ScoringEngine()
        trials_data = []
        gates_data = {}
        
        for i in range(num_trials):
            trial_id = i + 1
            
            # Generate trial metadata
            trial_data = {
                "trial_id": trial_id,
                "is_pivotal": i % 2 == 0,
                "indication": ["oncology", "cardiovascular", "rare_disease"][i % 3],
                "phase": ["phase_2", "phase_3"][i % 2],
                "sponsor_experience": "experienced",
                "primary_endpoint_type": "response"
            }
            trials_data.append(trial_data)
            
            # Generate gates
            study_card = self.generator.generate_study_card()
            signals = evaluate_all_signals(study_card)
            gates = evaluate_all_gates(signals)
            gates_data[trial_id] = gates
        
        # Warmup
        for _ in range(min(self.warmup_iterations, num_trials)):
            engine.score_trial(1, trials_data[0], gates_data[1], "warmup")
        
        # Benchmark
        return self._measure_performance(
            operation_name=f"Scoring_System_{num_trials}",
            operation_func=lambda: batch_score_trials(
                trials_data, gates_data, "benchmark"
            ),
            num_items=num_trials
        )
    
    def benchmark_full_pipeline(self, num_trials: int) -> PerformanceMetrics:
        """
        Benchmark the complete pipeline.
        
        Args:
            num_trials: Number of trials to process
            
        Returns:
            Performance metrics for full pipeline
        """
        # Generate test data
        engine = ScoringEngine()
        study_cards = [
            self.generator.generate_study_card() 
            for _ in range(num_trials)
        ]
        
        def full_pipeline():
            results = []
            for i, study_card in enumerate(study_cards):
                # Signal evaluation
                signals = evaluate_all_signals(study_card)
                
                # Gate evaluation
                gates = evaluate_all_gates(signals)
                
                # Scoring
                trial_data = {
                    "trial_id": i + 1,
                    "is_pivotal": True,
                    "indication": "oncology",
                    "phase": "phase_3",
                    "sponsor_experience": "experienced",
                    "primary_endpoint_type": "response"
                }
                score = engine.score_trial(i + 1, trial_data, gates, "benchmark")
                
                results.append({
                    "signals": signals,
                    "gates": gates,
                    "score": score
                })
            
            return results
        
        # Warmup
        for _ in range(min(self.warmup_iterations, 5)):
            full_pipeline()
        
        # Benchmark
        return self._measure_performance(
            operation_name=f"Full_Pipeline_{num_trials}",
            operation_func=full_pipeline,
            num_items=num_trials
        )
    
    def benchmark_memory_usage(self, max_trials: int = 10000) -> Dict[str, Any]:
        """
        Benchmark memory usage scaling.
        
        Args:
            max_trials: Maximum number of trials to test
            
        Returns:
            Memory usage analysis
        """
        print(f"🧠 Benchmarking Memory Usage (up to {max_trials} trials)")
        
        memory_data = []
        sizes = [100, 500, 1000, 2500, 5000, 10000]
        sizes = [s for s in sizes if s <= max_trials]
        
        for size in sizes:
            gc.collect()  # Clean up before measurement
            
            # Measure baseline memory
            process = psutil.Process()
            baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Generate data and measure memory
            study_cards = [
                self.generator.generate_study_card() 
                for _ in range(size)
            ]
            
            peak_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_delta = peak_memory - baseline_memory
            
            memory_data.append({
                "size": size,
                "baseline_mb": baseline_memory,
                "peak_mb": peak_memory,
                "delta_mb": memory_delta,
                "mb_per_trial": memory_delta / size if size > 0 else 0
            })
            
            print(f"  {size:5d} trials: {memory_delta:.1f}MB "
                  f"({memory_delta/size*1024:.1f}KB/trial)")
            
            # Clean up
            del study_cards
            gc.collect()
        
        return {
            "memory_measurements": memory_data,
            "memory_scaling_analysis": self._analyze_memory_scaling(memory_data)
        }
    
    def benchmark_scalability(self, max_size: int = 10000) -> Dict[str, Any]:
        """
        Benchmark system scalability.
        
        Args:
            max_size: Maximum dataset size to test
            
        Returns:
            Scalability analysis
        """
        print(f"📈 Benchmarking Scalability (up to {max_size} trials)")
        
        sizes = [10, 50, 100, 250, 500, 1000, 2500, 5000]
        sizes = [s for s in sizes if s <= max_size]
        
        scalability_data = []
        
        for size in sizes:
            # Benchmark signals
            signal_metric = self.benchmark_signal_evaluation(size)
            
            # Benchmark full pipeline
            pipeline_metric = self.benchmark_full_pipeline(size)
            
            scalability_data.append({
                "size": size,
                "signal_time_per_item": signal_metric.avg_time_per_item,
                "signal_throughput": signal_metric.items_per_second,
                "pipeline_time_per_item": pipeline_metric.avg_time_per_item,
                "pipeline_throughput": pipeline_metric.items_per_second,
                "memory_mb": signal_metric.memory_peak_mb
            })
            
            print(f"  {size:5d} trials: Signal {signal_metric.items_per_second:.0f}/sec, "
                  f"Pipeline {pipeline_metric.items_per_second:.0f}/sec")
        
        return {
            "scalability_measurements": scalability_data,
            "scalability_analysis": self._analyze_scalability(scalability_data)
        }
    
    def _measure_performance(self, operation_name: str, 
                           operation_func: Callable, 
                           num_items: int) -> PerformanceMetrics:
        """
        Measure performance of an operation.
        
        Args:
            operation_name: Name of the operation
            operation_func: Function to measure
            num_items: Number of items processed
            
        Returns:
            Performance metrics
        """
        # Clean up before measurement
        gc.collect()
        
        # Get initial memory
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Measure CPU before
        cpu_before = psutil.cpu_percent(interval=None)
        
        # Run operation and measure time
        start_time = time.perf_counter()
        result = operation_func()
        end_time = time.perf_counter()
        
        # Measure CPU after
        cpu_after = psutil.cpu_percent(interval=None)
        
        # Get peak memory
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Calculate metrics
        total_time = end_time - start_time
        avg_time_per_item = total_time / num_items if num_items > 0 else 0
        items_per_second = num_items / total_time if total_time > 0 else 0
        memory_delta = peak_memory - initial_memory
        avg_cpu = (cpu_before + cpu_after) / 2
        
        return PerformanceMetrics(
            operation_name=operation_name,
            total_time=total_time,
            avg_time_per_item=avg_time_per_item,
            items_per_second=items_per_second,
            memory_peak_mb=peak_memory,
            memory_delta_mb=memory_delta,
            cpu_percent=avg_cpu,
            total_items=num_items,
            metadata={
                "result_size": len(result) if hasattr(result, '__len__') else 1
            }
        )
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information for benchmarks."""
        return {
            "cpu_count": psutil.cpu_count(),
            "cpu_freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else None,
            "memory_total_gb": psutil.virtual_memory().total / 1024 / 1024 / 1024,
            "memory_available_gb": psutil.virtual_memory().available / 1024 / 1024 / 1024,
            "platform": psutil.os.name,
            "timestamp": datetime.now().isoformat()
        }
    
    def _analyze_memory_scaling(self, memory_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze memory scaling characteristics."""
        if len(memory_data) < 2:
            return {"status": "insufficient_data"}
        
        # Calculate memory efficiency
        mb_per_trial_values = [d["mb_per_trial"] for d in memory_data]
        
        min_mb_per_trial = min(mb_per_trial_values)
        max_mb_per_trial = max(mb_per_trial_values)
        
        # Avoid division by zero
        if min_mb_per_trial > 0:
            efficiency_ratio = max_mb_per_trial / min_mb_per_trial
            memory_efficiency = "linear" if efficiency_ratio < 2 else "sublinear"
        else:
            memory_efficiency = "unknown"
        
        return {
            "avg_mb_per_trial": statistics.mean(mb_per_trial_values),
            "max_mb_per_trial": max_mb_per_trial,
            "min_mb_per_trial": min_mb_per_trial,
            "memory_efficiency": memory_efficiency,
            "total_memory_range_mb": memory_data[-1]["delta_mb"] - memory_data[0]["delta_mb"]
        }
    
    def _analyze_scalability(self, scalability_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze scalability characteristics."""
        if len(scalability_data) < 2:
            return {"status": "insufficient_data"}
        
        # Analyze throughput stability
        signal_throughputs = [d["signal_throughput"] for d in scalability_data]
        pipeline_throughputs = [d["pipeline_throughput"] for d in scalability_data]
        
        signal_stability = (max(signal_throughputs) - min(signal_throughputs)) / statistics.mean(signal_throughputs)
        pipeline_stability = (max(pipeline_throughputs) - min(pipeline_throughputs)) / statistics.mean(pipeline_throughputs)
        
        return {
            "signal_throughput_avg": statistics.mean(signal_throughputs),
            "signal_throughput_stability": signal_stability,
            "pipeline_throughput_avg": statistics.mean(pipeline_throughputs),
            "pipeline_throughput_stability": pipeline_stability,
            "scalability_rating": "excellent" if max(signal_stability, pipeline_stability) < 0.3 else "good" if max(signal_stability, pipeline_stability) < 0.5 else "needs_optimization"
        }
    
    def save_benchmark_results(self, result: BenchmarkResult, filepath: str) -> None:
        """Save benchmark results to file."""
        result_dict = {
            "benchmark_name": result.benchmark_name,
            "start_time": result.start_time.isoformat(),
            "end_time": result.end_time.isoformat(),
            "total_duration": result.total_duration,
            "system_info": result.system_info,
            "configuration": result.configuration,
            "metrics": [
                {
                    "operation_name": m.operation_name,
                    "total_time": m.total_time,
                    "avg_time_per_item": m.avg_time_per_item,
                    "items_per_second": m.items_per_second,
                    "memory_peak_mb": m.memory_peak_mb,
                    "memory_delta_mb": m.memory_delta_mb,
                    "cpu_percent": m.cpu_percent,
                    "total_items": m.total_items,
                    "metadata": m.metadata
                }
                for m in result.metrics
            ]
        }
        
        with open(filepath, 'w') as f:
            json.dump(result_dict, f, indent=2)


# Convenience functions
def benchmark_signal_evaluation(num_trials: int = 100) -> PerformanceMetrics:
    """Benchmark signal evaluation."""
    benchmark = PerformanceBenchmark()
    return benchmark.benchmark_signal_evaluation(num_trials)


def benchmark_gate_evaluation(num_trials: int = 100) -> PerformanceMetrics:
    """Benchmark gate evaluation."""
    benchmark = PerformanceBenchmark()
    return benchmark.benchmark_gate_evaluation(num_trials)


def benchmark_scoring_system(num_trials: int = 100) -> PerformanceMetrics:
    """Benchmark scoring system."""
    benchmark = PerformanceBenchmark()
    return benchmark.benchmark_scoring_system(num_trials)


def benchmark_full_pipeline(num_trials: int = 100) -> PerformanceMetrics:
    """Benchmark full pipeline."""
    benchmark = PerformanceBenchmark()
    return benchmark.benchmark_full_pipeline(num_trials)
