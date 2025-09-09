#!/usr/bin/env python3
"""
Example: Historical Universe Backtest

This example demonstrates how to run a complete historical universe backtest
for Alzheimer's disease trials from 2018-2023.
"""

import subprocess
import sys
from pathlib import Path

def run_example():
    """Run a complete historical universe backtest example"""
    
    print("🚀 Starting Historical Universe Backtest Example")
    print("=" * 60)
    
    # Example configuration
    indication = "Alzheimer"
    start_date = "2018-01-01"
    end_date = "2023-12-31"
    
    print(f"📊 Analyzing {indication} trials from {start_date} to {end_date}")
    print()
    
    # Run the complete pipeline
    cmd = [
        sys.executable, "scripts/universe_pipeline.py",
        "--indication", indication,
        "--start-date", start_date,
        "--end-date", end_date,
        "--base-dir", "backtest_example"
    ]
    
    print("🔄 Running complete pipeline...")
    print("   This may take several minutes depending on data size")
    print()
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Pipeline completed successfully!")
        print()
        
        # Display results
        print("📈 Results Summary:")
        print(result.stdout)
        
    except subprocess.CalledProcessError as e:
        print("❌ Pipeline failed!")
        print(f"Error: {e.stderr}")
        return False
    
    # Show output files
    output_dir = Path("backtest_example")
    if output_dir.exists():
        print("\n📁 Generated Files:")
        print(f"   Universe: {output_dir / 'universe'}")
        print(f"   Splits: {output_dir / 'splits'}")
        print(f"   Snapshots: {output_dir / 'snapshots'}")
        print(f"   Results: {output_dir / 'results'}")
        
        # Show key metrics
        metrics_file = output_dir / "results" / "metrics.json"
        if metrics_file.exists():
            import json
            with open(metrics_file, "r") as f:
                metrics = json.load(f)
            
            print("\n🎯 Key Metrics:")
            print(f"   Total Trials: {metrics['total_trials']}")
            print(f"   Coverage Rate: {metrics['coverage_rate'] * 100:.1f}%")
            print(f"   Precision@1: {metrics['precision_at_k'].get('1', 0):.3f}")
            print(f"   Precision@3: {metrics['precision_at_k'].get('3', 0):.3f}")
    
    print("\n🎉 Example completed!")
    return True

def run_individual_phases():
    """Run individual phases to demonstrate the pipeline"""
    
    print("🔧 Running Individual Phases Example")
    print("=" * 60)
    
    phases = [
        ("universe", "Building universe from CT.gov"),
        ("harvest", "Harvesting documents"),
        ("labels", "Building labels"),
        ("status", "Building public status"),
        ("splits", "Creating time splits"),
        ("snapshots", "Building T-14 snapshots"),
        ("backtest", "Running backtest")
    ]
    
    for phase, description in phases:
        print(f"\n🔄 Phase: {phase}")
        print(f"   {description}")
        
        cmd = [
            sys.executable, "scripts/universe_pipeline.py",
            "--indication", "Alzheimer",
            "--phase", phase,
            "--base-dir", "backtest_phases"
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"   ✅ {phase} completed")
        except subprocess.CalledProcessError as e:
            print(f"   ❌ {phase} failed: {e.stderr}")
            break
    
    print("\n🎉 Individual phases example completed!")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Historical Universe Backtest Example")
    parser.add_argument("--mode", choices=["full", "phases"], default="full",
                       help="Run full pipeline or individual phases")
    
    args = parser.parse_args()
    
    if args.mode == "full":
        run_example()
    else:
        run_individual_phases()
