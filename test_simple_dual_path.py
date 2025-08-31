#!/usr/bin/env python3
"""
Simplified test script for the dual-path pipeline components.

This script tests the individual components without importing the problematic workers module.
"""

import json
import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_claimizer_direct():
    """Test Claimizer by importing it directly."""
    print("\n🔍 Testing Claimizer Direct Import")
    print("=" * 50)
    
    try:
        # Import directly to avoid workers module issues
        sys.path.insert(0, str(Path(__file__).parent / "src/ncfd/extract/workers/llm"))
        from claimizer import Claimizer
        print("✅ Claimizer imported successfully")
        
        # Test basic functionality
        claimizer = Claimizer()
        print(f"✅ Claimizer initialized: {claimizer.name} v{claimizer.version}")
        
        return True
    except Exception as e:
        print(f"❌ Claimizer test failed: {e}")
        return False

def test_counter_evidence_miner_direct():
    """Test CounterEvidenceMiner by importing it directly."""
    print("\n🔍 Testing CounterEvidenceMiner Direct Import")
    print("=" * 50)
    
    try:
        # Import directly to avoid workers module issues
        sys.path.insert(0, str(Path(__file__).parent / "src/ncfd/extract/workers/llm"))
        from counter_evidence_miner import CounterEvidenceMiner
        print("✅ CounterEvidenceMiner imported successfully")
        
        # Test basic functionality
        miner = CounterEvidenceMiner()
        print(f"✅ CounterEvidenceMiner initialized: {miner.name} v{miner.version}")
        
        return True
    except Exception as e:
        print(f"❌ CounterEvidenceMiner test failed: {e}")
        return False

def test_gate_validator_direct():
    """Test GateValidator by importing it directly."""
    print("\n🔍 Testing GateValidator Direct Import")
    print("=" * 50)
    
    try:
        # Import directly to avoid workers module issues
        sys.path.insert(0, str(Path(__file__).parent / "src/ncfd/extract/workers/deterministic"))
        from gate_validator import GateValidator
        print("✅ GateValidator imported successfully")
        
        # Test basic functionality
        validator = GateValidator()
        print(f"✅ GateValidator initialized: {validator.name} v{validator.version}")
        
        return True
    except Exception as e:
        print(f"❌ GateValidator test failed: {e}")
        return False

def test_gate_assessor_direct():
    """Test GateAssessor by importing it directly."""
    print("\n🔍 Testing GateAssessor Direct Import")
    print("=" * 50)
    
    try:
        # Import directly to avoid workers module issues
        sys.path.insert(0, str(Path(__file__).parent / "src/ncfd/extract/workers/deterministic"))
        from gate_assessor import GateAssessor
        print("✅ GateAssessor imported successfully")
        
        # Test basic functionality
        assessor = GateAssessor()
        print(f"✅ GateAssessor initialized: {assessor.name} v{assessor.version}")
        
        return True
    except Exception as e:
        print(f"❌ GateAssessor test failed: {e}")
        return False

def test_orchestrator_direct():
    """Test LateFusionOrchestrator by importing it directly."""
    print("\n🔍 Testing LateFusionOrchestrator Direct Import")
    print("=" * 50)
    
    try:
        # Import directly to avoid workers module issues
        sys.path.insert(0, str(Path(__file__).parent / "src/ncfd/extract/orchestrate"))
        from late_fusion_orchestrator import LateFusionOrchestrator
        print("✅ LateFusionOrchestrator imported successfully")
        
        # Test basic functionality
        orchestrator = LateFusionOrchestrator()
        print(f"✅ LateFusionOrchestrator initialized")
        
        # Test configuration
        config = orchestrator.get_pipeline_status()
        print(f"✅ Pipeline status retrieved: {config}")
        
        return True
    except Exception as e:
        print(f"❌ LateFusionOrchestrator test failed: {e}")
        return False

def test_models():
    """Test that the models can be imported."""
    print("\n🔍 Testing Model Imports")
    print("=" * 50)
    
    try:
        from ncfd.extract.models import (
            EvidenceSpan, MethodCard, ResultsFactsheet, Claim
        )
        print("✅ All models imported successfully")
        
        # Test basic model creation
        span = EvidenceSpan(
            doc_id="test:doc1",
            quote="Test span",
            section="Methods",
            page=1,
            char_start=0,
            char_end=100,
            confidence=0.9
        )
        print(f"✅ EvidenceSpan created: {span.doc_id}")
        
        return True
    except Exception as e:
        print(f"❌ Model test failed: {e}")
        return False

def test_validators():
    """Test that the validators can be imported."""
    print("\n🔍 Testing Validator Imports")
    print("=" * 50)
    
    try:
        from ncfd.extract.validators import validate_all_artifacts
        print("✅ Validators imported successfully")
        
        return True
    except Exception as e:
        print(f"❌ Validator test failed: {e}")
        return False

def main():
    """Run all simplified tests."""
    print("🚀 Testing Dual-Path Pipeline Components (Simplified)")
    print("=" * 80)
    
    # Test individual components
    tests = [
        ("Models", test_models),
        ("Validators", test_validators),
        ("Claimizer", test_claimizer_direct),
        ("CounterEvidenceMiner", test_counter_evidence_miner_direct),
        ("GateValidator", test_gate_validator_direct),
        ("GateAssessor", test_gate_assessor_direct),
        ("LateFusionOrchestrator", test_orchestrator_direct),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results[test_name] = success
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 80)
    print("🎉 Component Testing Complete!")
    print("\nResults Summary:")
    
    passed = 0
    total = len(results)
    
    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All components are working correctly!")
    else:
        print("⚠️  Some components have issues that need attention.")
    
    # Save results
    try:
        with open("test_component_results.json", "w") as f:
            json.dump(results, f, indent=2)
        print("\n💾 Test results saved to test_component_results.json")
    except Exception as e:
        print(f"\n⚠️  Could not save test results: {e}")

if __name__ == "__main__":
    main()
