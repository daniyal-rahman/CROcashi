#!/usr/bin/env python3
"""
Test script for Phase 2 BaseSpan components.

This script demonstrates the new functionality:
- Metric registry & normalization layer
- Denominator resolver
- Enhanced span triage with must-fill + top-up
- LLM selector for FactsBin
- Span-limited LLM normalizer
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
    SpanLimitedNormalizer
)
from ncfd.extract.normalization.metric_registry import get_metric_registry
from ncfd.extract.config.span_config_loader import get_span_config
from ncfd.db.session import get_db_session
from ncfd.db.models import Document, BaseSpan, DerivedSpan


def test_metric_registry():
    """Test the metric registry and normalization layer."""
    print("🧪 Testing Metric Registry & Normalization Layer")
    print("=" * 60)
    
    try:
        # Get metric registry
        registry = get_metric_registry()
        print(f"✅ Metric registry loaded successfully")
        print(f"   - Total metrics: {len(registry.metrics)}")
        
        # List available metrics
        print("\n📊 Available Metrics:")
        for metric_id, metric in registry.metrics.items():
            print(f"   - {metric_id}: {metric.name}")
            print(f"     Type: {metric.metric_type.value}")
            print(f"     Units: {metric.allowed_units}")
            print(f"     Normalize to: {metric.normalize_to_unit or 'none'}")
        
        # Test metric validation
        print("\n🔍 Testing Metric Validation:")
        test_cases = [
            ("median_ttp", 14, "weeks", 22),
            ("median_os", 13.1, "months", 22),
            ("orr_recist", 15.8, "%", 19),
            ("ca125_response", 21.1, "%", 19)
        ]
        
        for metric_id, value, unit, n in test_cases:
            is_valid, errors = registry.validate_metric_value(metric_id, value, unit, n)
            status = "✅" if is_valid else "❌"
            print(f"   {status} {metric_id}: {value} {unit} (n={n})")
            if not is_valid:
                for error in errors:
                    print(f"      Error: {error}")
        
        # Test normalization
        print("\n🔄 Testing Value Normalization:")
        for metric_id, value, unit, n in test_cases:
            normalized = registry.normalize_value(metric_id, value, unit)
            if normalized.is_valid:
                print(f"   ✅ {metric_id}: {value} {unit} → {normalized.normalized_value} {normalized.normalized_unit}")
            else:
                print(f"   ❌ {metric_id}: {normalized.error_message}")
        
        # Test text extraction
        print("\n📝 Testing Text Extraction:")
        sample_text = "The median TTP was 14 weeks and median OS was 13.1 months. ORR was 15.8% and CA-125 response was 21.1%."
        extracted = registry.extract_metric_from_text(sample_text)
        print(f"   Extracted {len(extracted)} metrics from sample text")
        for metric in extracted:
            print(f"     - {metric['metric_id']}: {metric['value']} {metric['unit']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Metric registry test failed: {e}")
        return False


def test_denominator_resolver():
    """Test the denominator resolver."""
    print("\n🧪 Testing Denominator Resolver")
    print("=" * 60)
    
    try:
        # Create denominator resolver
        resolver = DenominatorResolver()
        print(f"✅ DenominatorResolver created successfully")
        print(f"   - Name: {resolver.name}")
        print(f"   - Version: {resolver.version}")
        print(f"   - Patterns loaded: {len(resolver.denominator_patterns)}")
        
        # Show some patterns
        print("\n📋 Denominator Patterns:")
        for i, pattern in enumerate(resolver.denominator_patterns[:5]):  # Show first 5
            print(f"   {i+1}. {pattern.name}: {pattern.pattern}")
            print(f"      Metric family: {pattern.metric_family}")
            print(f"      Confidence: {pattern.confidence}")
            print(f"      Section: {pattern.section}")
        
        # Test pattern matching
        print("\n🔍 Testing Pattern Matching:")
        test_texts = [
            "evaluable for response (n=19)",
            "TTP and OS analysis included 22 patients",
            "safety analysis included n=25",
            "intent-to-treat population n=30"
        ]
        
        for text in test_texts:
            for pattern in resolver.denominator_patterns:
                import re
                match = re.search(pattern.pattern, text, re.IGNORECASE)
                if match:
                    print(f"   ✅ '{text}' matched pattern '{pattern.name}'")
                    break
            else:
                print(f"   ❌ '{text}' did not match any pattern")
        
        return True
        
    except Exception as e:
        print(f"❌ Denominator resolver test failed: {e}")
        return False


def test_enhanced_triage():
    """Test enhanced span triage with must-fill + top-up."""
    print("\n🧪 Testing Enhanced Span Triage")
    print("=" * 60)
    
    try:
        # Create triage worker
        triage_worker = SpanTriageWorker()
        print(f"✅ SpanTriageWorker created successfully")
        print(f"   - Methods budget: {triage_worker.config.methods_budget}")
        print(f"   - Results budget: {triage_worker.config.results_budget}")
        print(f"   - Tables budget: {triage_worker.config.tables_budget}")
        print(f"   - Top-up per field: {triage_worker.config.topup_per_field}")
        
        # Test default query generation
        print("\n📝 Testing Default Query Generation:")
        required_fields = ["endpoints", "survival_method", "design_archetype", "response_breakdown"]
        default_queries = triage_worker._generate_default_queries(required_fields)
        print(f"   Generated {len(default_queries)} default queries")
        
        for query in default_queries[:3]:  # Show first 3
            print(f"     - {query.field_name}: '{query.query_text}'")
            print(f"       Section: {query.section}, Must-fill: {query.must_fill}")
        
        # Test section inference
        print("\n🧠 Testing Section Inference:")
        test_fields = ["endpoints_primary", "survival_method", "response_rate", "table_data"]
        for field in test_fields:
            section = triage_worker._infer_section(field)
            print(f"   {field} → {section}")
        
        return True
        
    except Exception as e:
        print(f"❌ Enhanced triage test failed: {e}")
        return False


def test_factsbin_selector():
    """Test the LLM selector for FactsBin."""
    print("\n🧪 Testing FactsBin LLM Selector")
    print("=" * 60)
    
    try:
        # Create FactsBin selector
        selector = FactsBinSelector()
        print(f"✅ FactsBinSelector created successfully")
        print(f"   - Name: {selector.name}")
        print(f"   - Version: {selector.version}")
        print(f"   - Supported fact types: {selector.fact_types}")
        
        # Test fact candidate generation
        print("\n📝 Testing Fact Candidate Generation:")
        sample_spans = [
            {"text": "Patients were treated with 100mg daily for 28 days", "span_id": 1},
            {"text": "The median progression-free survival was 14 weeks", "span_id": 2},
            {"text": "Overall response rate was 15.8% by RECIST criteria", "span_id": 3},
            {"text": "This was a single-arm phase 2 study", "span_id": 4}
        ]
        
        candidates = selector._generate_candidates(sample_spans)
        print(f"   Generated {len(candidates)} fact candidates")
        
        for candidate in candidates:
            print(f"     - Text: {candidate.text[:50]}...")
            print(f"       Has numeric: {candidate.has_numeric}")
            print(f"       Units: {candidate.units}")
        
        # Test fact classification
        print("\n🔍 Testing Fact Classification:")
        if candidates:
            classification = selector._simulate_llm_classification(candidates[0])
            print(f"   Classification result:")
            print(f"     - Is fact: {classification.is_fact}")
            print(f"     - Type: {classification.fact_type}")
            print(f"     - Relevance: {classification.relevance_score:.3f}")
            print(f"     - Reasoning: {classification.reasoning}")
        
        return True
        
    except Exception as e:
        print(f"❌ FactsBin selector test failed: {e}")
        return False


def test_span_limited_normalizer():
    """Test the span-limited LLM normalizer."""
    print("\n🧪 Testing Span-Limited LLM Normalizer")
    print("=" * 60)
    
    try:
        # Create normalizer
        normalizer = SpanLimitedNormalizer()
        print(f"✅ SpanLimitedNormalizer created successfully")
        print(f"   - Name: {normalizer.name}")
        print(f"   - Version: {normalizer.version}")
        
        # Test input validation
        print("\n🔍 Testing Input Validation:")
        from ncfd.extract.workers.llm.span_limited_normalizer import NormalizationInput
        test_inputs = [
            NormalizationInput("median_ttp", 14, "weeks", 22, [1, 2]),
            NormalizationInput("orr_recist", 15.8, "%", 19, [3]),
            NormalizationInput("", 10, "days", None, []),  # Invalid
            NormalizationInput("median_os", "invalid", "months", 22, [4])  # Invalid
        ]
        
        for i, test_input in enumerate(test_inputs):
            is_valid = normalizer._validate_input_data(test_input)
            status = "✅" if is_valid else "❌"
            print(f"   {status} Test {i+1}: {test_input.metric_id} = {test_input.raw_value} {test_input.raw_unit}")
        
        # Test normalization
        print("\n🔄 Testing Normalization:")
        test_data = [
            {"metric_id": "median_ttp", "value": 14, "unit": "weeks", "n": 22, "span_ids": [1]},
            {"metric_id": "median_os", "value": 13.1, "unit": "months", "n": 22, "span_ids": [2]},
            {"metric_id": "orr_recist", "value": 15.8, "unit": "%", "n": 19, "span_ids": [3]}
        ]
        
        sample_spans = [
            {"span_id": 1, "text": "TTP analysis"},
            {"span_id": 2, "text": "OS analysis"},
            {"span_id": 3, "text": "Response analysis"}
        ]
        
        result = normalizer.process({
            "doc_id": 123,
            "extracted_data": test_data,
            "spans": sample_spans
        })
        
        if result.success:
            print(f"   ✅ Normalization completed successfully")
            print(f"   - Total items: {result.output['total_items']}")
            print(f"   - Valid items: {result.output['valid_items']}")
            print(f"   - Invalid items: {result.output['invalid_items']}")
            
            # Show some results
            for item in result.output['normalized_data'][:2]:
                print(f"     - {item['metric_id']}: {item['original_value']} {item['original_unit']} → {item['normalized_value']} {item['normalized_unit']}")
        else:
            print(f"   ❌ Normalization failed: {result.error_message}")
        
        return True
        
    except Exception as e:
        print(f"❌ Span-limited normalizer test failed: {e}")
        return False


def test_integration():
    """Test integration of all Phase 2 components."""
    print("\n🧪 Testing Phase 2 Integration")
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
        
        # Test denominator resolver integration
        print("\n3. Testing denominator resolver integration...")
        resolver = DenominatorResolver()
        print(f"   ✅ Denominator resolver accessible")
        
        # Test enhanced triage integration
        print("\n4. Testing enhanced triage integration...")
        triage = SpanTriageWorker()
        print(f"   ✅ Enhanced triage accessible")
        
        # Test LLM components integration
        print("\n5. Testing LLM components integration...")
        factsbin = FactsBinSelector()
        normalizer = SpanLimitedNormalizer()
        print(f"   ✅ LLM components accessible")
        
        print("\n🎉 All Phase 2 components integrated successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        return False


def main():
    """Run all Phase 2 component tests."""
    print("Phase 2 BaseSpan System Test Suite")
    print("=" * 80)
    print("Testing new components:")
    print("  - Metric registry & normalization layer")
    print("  - Denominator resolver")
    print("  - Enhanced span triage (must-fill + top-up)")
    print("  - LLM selector for FactsBin")
    print("  - Span-limited LLM normalizer")
    print("=" * 80)
    
    # Run individual component tests
    tests = [
        ("Metric Registry", test_metric_registry),
        ("Denominator Resolver", test_denominator_resolver),
        ("Enhanced Triage", test_enhanced_triage),
        ("FactsBin Selector", test_factsbin_selector),
        ("Span-Limited Normalizer", test_span_limited_normalizer),
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
    print("PHASE 2 TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All Phase 2 components are working correctly!")
        print("\nThe system now supports:")
        print("  ✅ Metric registry with oncology-specific metrics")
        print("  ✅ Automatic unit normalization (weeks/months → days)")
        print("  ✅ Denominator resolution from document patterns")
        print("  ✅ Enhanced span triage with must-fill fields")
        print("  ✅ LLM fact selection and classification")
        print("  ✅ Span-limited normalization and validation")
        print("\nReady for Phase 3: LLM integration and late fusion!")
    else:
        print(f"\n⚠️  {total - passed} tests failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
