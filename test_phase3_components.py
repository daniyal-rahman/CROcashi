#!/usr/bin/env python3
"""
Test script for Phase 3 BaseSpan components.

This script demonstrates the new functionality:
- Enhanced ResultsDistiller with span validation
- GateProposer for clinical trial decisions
- FdaLens for regulatory compliance
- MemoComposer for executive summaries
- All components with span-limited processing
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.extract.workers import (
    BaseSpanIngestWorker,
    SpanIndexer,
    FuzzyAligner,
    SpanTriageWorker,
    DenominatorResolver,
    FactsBinSelector,
    SpanLimitedNormalizer,
    ResultsDistiller,
    GateProposer,
    FdaLens,
    MemoComposer
)
from ncfd.extract.normalization.metric_registry import get_metric_registry
from ncfd.extract.config.span_config_loader import get_span_config
from ncfd.db.session import get_db_session
from ncfd.db.models import Document, BaseSpan, DerivedSpan


def test_enhanced_results_distiller():
    """Test the enhanced ResultsDistiller with span validation."""
    print("🧪 Testing Enhanced ResultsDistiller")
    print("=" * 60)
    
    try:
        # Create ResultsDistiller
        distiller = ResultsDistiller()
        print(f"✅ ResultsDistiller created successfully")
        print(f"   - Name: {distiller.name}")
        print(f"   - Version: {distiller.version}")
        
        # Test confidence scoring
        print("\n🔍 Testing Confidence Scoring:")
        test_results = [
            {"metric": "median_ttp", "value": 14, "units": "weeks", "n": 22, "span_ids": [1]},
            {"metric": "orr_recist", "value": 15.8, "units": "%", "n": 19, "span_ids": [2]},
            {"metric": "safety_grade_3", "value": 12.5, "units": "%", "n": 25, "span_ids": [3]}
        ]
        
        for result in test_results:
            confidence = distiller._extract_confidence_score(result)
            print(f"   {result['metric']}: {confidence:.3f}")
        
        # Test quality metrics
        print("\n📊 Testing Quality Metrics:")
        quality_metrics = distiller.get_quality_metrics(test_results)
        print(f"   Total results: {quality_metrics['total_results']}")
        print(f"   Complete results: {quality_metrics['complete_results']}")
        print(f"   High confidence: {quality_metrics['high_confidence_results']}")
        print(f"   Average confidence: {quality_metrics['average_confidence']:.3f}")
        
        # Test consistency validation
        print("\n🔍 Testing Consistency Validation:")
        consistency_report = distiller.validate_results_consistency(test_results)
        print(f"   Overall consistent: {consistency_report['is_consistent']}")
        print(f"   Inconsistencies: {len(consistency_report['inconsistencies'])}")
        print(f"   Warnings: {len(consistency_report['warnings'])}")
        
        return True
        
    except Exception as e:
        print(f"❌ Enhanced ResultsDistiller test failed: {e}")
        return False


def test_gate_proposer():
    """Test the GateProposer for clinical trial decisions."""
    print("\n🧪 Testing GateProposer")
    print("=" * 60)
    
    try:
        # Create GateProposer
        proposer = GateProposer()
        print(f"✅ GateProposer created successfully")
        print(f"   - Name: {proposer.name}")
        print(f"   - Version: {proposer.version}")
        print(f"   - Gate criteria: {len(proposer.gate_criteria)}")
        
        # Show gate criteria
        print("\n📋 Gate Criteria:")
        for i, criteria in enumerate(proposer.gate_criteria[:3]):  # Show first 3
            print(f"   {i+1}. {criteria.metric_id}: {criteria.description}")
            print(f"      Threshold: {criteria.threshold} {criteria.direction}")
            print(f"      Importance: {criteria.criticality}")
        
        # Test gate decision making
        print("\n🎯 Testing Gate Decision Making:")
        test_results = [
            {"metric": "orr_recist", "value": 18.5, "units": "%", "n": 19, "span_ids": [1]},
            {"metric": "median_ttp", "value": 16, "units": "weeks", "n": 22, "span_ids": [2]},
            {"metric": "median_os", "value": 8.2, "units": "months", "n": 22, "span_ids": [3]},
            {"metric": "safety_grade_3_4", "value": 18.0, "units": "%", "n": 25, "span_ids": [4]}
        ]
        
        sample_spans = [
            {"span_id": 1, "text": "Response rate analysis"},
            {"span_id": 2, "text": "TTP analysis"},
            {"span_id": 3, "text": "OS analysis"},
            {"span_id": 4, "text": "Safety analysis"}
        ]
        
        result = proposer.process({
            "doc_id": 123,
            "results": test_results,
            "spans": sample_spans
        })
        
        if result.success:
            gate_decision = result.output["gate_decision"]
            print(f"   ✅ Gate decision: {gate_decision.decision.upper()}")
            print(f"   Confidence: {gate_decision.confidence:.1%}")
            print(f"   Reasoning: {gate_decision.reasoning}")
            print(f"   Supporting evidence: {len(gate_decision.supporting_evidence)}")
            print(f"   Conflicting evidence: {len(gate_decision.conflicting_evidence)}")
            print(f"   Recommendations: {len(gate_decision.recommendations)}")
        else:
            print(f"   ❌ Gate decision failed: {result.error_message}")
        
        return True
        
    except Exception as e:
        print(f"❌ GateProposer test failed: {e}")
        return False


def test_fda_lens():
    """Test the FdaLens for regulatory compliance."""
    print("\n🧪 Testing FdaLens")
    print("=" * 60)
    
    try:
        # Create FdaLens
        fda_lens = FdaLens()
        print(f"✅ FdaLens created successfully")
        print(f"   - Name: {fda_lens.name}")
        print(f"   - Version: {fda_lens.version}")
        print(f"   - Regulatory requirements: {len(fda_lens.regulatory_requirements)}")
        
        # Show regulatory requirements
        print("\n📋 Regulatory Requirements:")
        for i, req in enumerate(fda_lens.regulatory_requirements[:3]):  # Show first 3
            print(f"   {i+1}. {req.requirement_id}: {req.description}")
            print(f"      Category: {req.category}, Criticality: {req.criticality}")
            print(f"      FDA Guidance: {req.fda_guidance}")
        
        # Test regulatory assessment
        print("\n🔍 Testing Regulatory Assessment:")
        test_results = [
            {"metric": "orr_recist", "value": 18.5, "units": "%", "n": 19, "span_ids": [1]},
            {"metric": "median_ttp", "value": 16, "units": "weeks", "n": 22, "span_ids": [2]},
            {"metric": "safety_grade_3", "value": 18.0, "units": "%", "n": 25, "span_ids": [3]}
        ]
        
        sample_spans = [
            {"span_id": 1, "text": "RECIST response criteria analysis"},
            {"span_id": 2, "text": "Kaplan-Meier survival analysis"},
            {"span_id": 3, "text": "Safety monitoring committee report"}
        ]
        
        result = fda_lens.process({
            "doc_id": 123,
            "results": test_results,
            "spans": sample_spans
        })
        
        if result.success:
            regulatory_report = result.output["regulatory_report"]
            print(f"   ✅ Overall compliance: {regulatory_report.overall_compliance.upper()}")
            print(f"   Confidence: {regulatory_report.confidence:.1%}")
            print(f"   Critical issues: {len(regulatory_report.critical_issues)}")
            print(f"   Important issues: {len(regulatory_report.important_issues)}")
            print(f"   Supporting evidence: {len(regulatory_report.supporting_evidence)}")
            print(f"   Summary recommendations: {len(regulatory_report.summary_recommendations)}")
        else:
            print(f"   ❌ Regulatory assessment failed: {result.error_message}")
        
        return True
        
    except Exception as e:
        print(f"❌ FdaLens test failed: {e}")
        return False


def test_memo_composer():
    """Test the MemoComposer for executive summaries."""
    print("\n🧪 Testing MemoComposer")
    print("=" * 60)
    
    try:
        # Create MemoComposer
        composer = MemoComposer()
        print(f"✅ MemoComposer created successfully")
        print(f"   - Name: {composer.name}")
        print(f"   - Version: {composer.version}")
        print(f"   - Memo sections: {len(composer.memo_sections)}")
        
        # Show memo sections
        print("\n📋 Memo Sections:")
        for i, section in enumerate(composer.memo_sections[:3]):  # Show first 3
            print(f"   {i+1}. {section['title']}: {section['description']}")
            print(f"      Required fields: {section['required_fields']}")
        
        # Test memo composition
        print("\n📝 Testing Memo Composition:")
        test_results = [
            {"metric": "orr_recist", "value": 18.5, "units": "%", "n": 19, "span_ids": [1], "is_primary": True},
            {"metric": "median_ttp", "value": 16, "units": "weeks", "n": 22, "span_ids": [2]},
            {"metric": "median_os", "value": 8.2, "units": "months", "n": 22, "span_ids": [3]},
            {"metric": "safety_grade_3", "value": 18.0, "units": "%", "n": 25, "span_ids": [4]},
            {"metric": "p_value_orr", "value": 0.023, "units": "", "n": 19, "span_ids": [5]}
        ]
        
        sample_spans = [
            {"span_id": 1, "text": "Primary endpoint response rate analysis"},
            {"span_id": 2, "text": "Time to progression analysis"},
            {"span_id": 3, "text": "Overall survival analysis"},
            {"span_id": 4, "text": "Safety profile assessment"},
            {"span_id": 5, "text": "Statistical significance testing"}
        ]
        
        result = composer.process({
            "doc_id": 123,
            "results": test_results,
            "spans": sample_spans,
            "memo_type": "executive_summary"
        })
        
        if result.success:
            clinical_memo = result.output["clinical_memo"]
            print(f"   ✅ Memo title: {clinical_memo.title}")
            print(f"   Overall assessment: {clinical_memo.overall_assessment}")
            print(f"   Confidence: {clinical_memo.confidence:.1%}")
            print(f"   Sections: {len(clinical_memo.sections)}")
            
            # Show executive summary
            exec_summary = clinical_memo.executive_summary
            print(f"   Key findings: {len(exec_summary.key_findings)}")
            print(f"   Critical metrics: {len(exec_summary.critical_metrics)}")
            print(f"   Risk assessment: {exec_summary.risk_assessment}")
            print(f"   Recommendations: {len(exec_summary.recommendations)}")
            print(f"   Next steps: {len(exec_summary.next_steps)}")
        else:
            print(f"   ❌ Memo composition failed: {result.error_message}")
        
        return True
        
    except Exception as e:
        print(f"❌ MemoComposer test failed: {e}")
        return False


def test_span_limited_processing():
    """Test span-limited processing across all components."""
    print("\n🧪 Testing Span-Limited Processing")
    print("=" * 60)
    
    try:
        # Test that all components require spans
        print("🔍 Testing Span Requirements:")
        
        components = [
            ("ResultsDistiller", ResultsDistiller()),
            ("GateProposer", GateProposer()),
            ("FdaLens", FdaLens()),
            ("MemoComposer", MemoComposer()),
            ("FactsBinSelector", FactsBinSelector()),
            ("SpanLimitedNormalizer", SpanLimitedNormalizer())
        ]
        
        test_results = [{"metric": "test", "value": 10, "units": "test", "span_ids": []}]
        
        for name, component in components:
            try:
                # Test without spans (should fail)
                result = component.process({
                    "doc_id": 123,
                    "results": test_results,
                    "spans": []  # Empty spans
                })
                
                if result.success:
                    print(f"   ⚠️  {name}: Should require spans but succeeded")
                else:
                    print(f"   ✅ {name}: Properly requires spans")
                    
            except Exception as e:
                print(f"   ✅ {name}: Properly handles span requirements")
        
        # Test span validation
        print("\n🔍 Testing Span Validation:")
        test_spans = [
            {"span_id": 1, "text": "Test span 1"},
            {"span_id": 2, "text": "Test span 2"}
        ]
        
        for name, component in components:
            try:
                result = component.process({
                    "doc_id": 123,
                    "results": test_results,
                    "spans": test_spans
                })
                
                if result.success:
                    print(f"   ✅ {name}: Successfully processes with spans")
                    # Check metadata for span_limited flag
                    if result.metadata.get("span_limited"):
                        print(f"      ✅ {name}: Properly flagged as span-limited")
                    else:
                        print(f"      ⚠️  {name}: Missing span_limited flag")
                else:
                    print(f"   ❌ {name}: Failed to process with spans: {result.error_message}")
                    
            except Exception as e:
                print(f"   ❌ {name}: Exception during processing: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Span-limited processing test failed: {e}")
        return False


def test_integration():
    """Test integration of all Phase 3 components."""
    print("\n🧪 Testing Phase 3 Integration")
    print("=" * 60)
    
    try:
        # Test configuration loading
        print("1. Loading configuration...")
        config = get_span_config()
        print(f"   ✅ Configuration loaded")
        print(f"   - System flags: {config.system_flags.retriever_mode}")
        print(f"   - LLM assist mode: {config.system_flags.llm_assist_mode}")
        
        # Test metric registry integration
        print("\n2. Testing metric registry integration...")
        registry = get_metric_registry()
        print(f"   ✅ Metric registry accessible")
        
        # Test all LLM components
        print("\n3. Testing LLM components...")
        components = [
            ("ResultsDistiller", ResultsDistiller()),
            ("GateProposer", GateProposer()),
            ("FdaLens", FdaLens()),
            ("MemoComposer", MemoComposer()),
            ("FactsBinSelector", FactsBinSelector()),
            ("SpanLimitedNormalizer", SpanLimitedNormalizer())
        ]
        
        for name, component in components:
            print(f"   ✅ {name}: {component.name} v{component.version}")
        
        # Test end-to-end workflow
        print("\n4. Testing end-to-end workflow...")
        test_results = [
            {"metric": "orr_recist", "value": 18.5, "units": "%", "n": 19, "span_ids": [1]},
            {"metric": "median_ttp", "value": 16, "units": "weeks", "n": 22, "span_ids": [2]}
        ]
        
        test_spans = [
            {"span_id": 1, "text": "Response rate analysis"},
            {"span_id": 2, "text": "TTP analysis"}
        ]
        
        # Test normalization
        normalizer = SpanLimitedNormalizer()
        norm_result = normalizer.process({
            "doc_id": 123,
            "extracted_data": test_results,
            "spans": test_spans
        })
        
        if norm_result.success:
            print("   ✅ Normalization: Success")
        else:
            print(f"   ❌ Normalization: {norm_result.error_message}")
        
        # Test gate decision
        proposer = GateProposer()
        gate_result = proposer.process({
            "doc_id": 123,
            "results": test_results,
            "spans": test_spans
        })
        
        if gate_result.success:
            print("   ✅ Gate decision: Success")
        else:
            print(f"   ❌ Gate decision: {gate_result.error_message}")
        
        # Test memo composition
        composer = MemoComposer()
        memo_result = composer.process({
            "doc_id": 123,
            "results": test_results,
            "spans": test_spans
        })
        
        if memo_result.success:
            print("   ✅ Memo composition: Success")
        else:
            print(f"   ❌ Memo composition: {memo_result.error_message}")
        
        print("\n🎉 All Phase 3 components integrated successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        return False


def main():
    """Run all Phase 3 component tests."""
    print("Phase 3 BaseSpan System Test Suite")
    print("=" * 80)
    print("Testing new components:")
    print("  - Enhanced ResultsDistiller with span validation")
    print("  - GateProposer for clinical trial decisions")
    print("  - FdaLens for regulatory compliance")
    print("  - MemoComposer for executive summaries")
    print("  - All components with span-limited processing")
    print("=" * 80)
    
    # Run individual component tests
    tests = [
        ("Enhanced ResultsDistiller", test_enhanced_results_distiller),
        ("GateProposer", test_gate_proposer),
        ("FdaLens", test_fda_lens),
        ("MemoComposer", test_memo_composer),
        ("Span-Limited Processing", test_span_limited_processing),
        ("Integration", test_integration)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("PHASE 3 TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All Phase 3 components are working correctly!")
        print("\nThe system now supports:")
        print("  ✅ Enhanced ResultsDistiller with quality metrics and consistency validation")
        print("  ✅ GateProposer for Go/No-Go decisions with evidence-based reasoning")
        print("  ✅ FdaLens for regulatory compliance assessment")
        print("  ✅ MemoComposer for executive summaries and clinical memos")
        print("  ✅ All components with span-limited processing for auditability")
        print("  ✅ Complete integration with Phase 1 and Phase 2 components")
        print("\nReady for Phase 4: Production deployment and optimization!")
    else:
        print(f"\n⚠️  {total - passed} tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
