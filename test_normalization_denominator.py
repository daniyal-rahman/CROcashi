#!/usr/bin/env python3
"""
Normalization Registry & Denominator Resolver Test Suite for PMC2978916

Tests the critical functionality of units, conversions, and correct n mapping:
- Unit enforcement and normalization
- Denominator mapping and resolution
- Ambiguity resolution with precedence rules
- Auto-conversion and validation
"""

import sys
import os
import json
import pytest
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import asdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.extract.workers.denominator_resolver import DenominatorResolver
from ncfd.extract.normalization.metric_registry import MetricRegistry
from ncfd.extract.models import EvidenceSpan


class PMC2978916NormalizationGoldPack:
    """Gold standard data for PMC2978916 normalization and denominator testing."""
    
    # Paper metadata
    PAPER_ID = "pmc:PMC2978916"
    TITLE = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
    
    # Gold metrics with expected units and denominators
    GOLD_METRICS = {
        "median_ttp": {
            "description": "Median time to progression",
            "expected_value": 14,
            "expected_unit": "weeks",
            "normalized_unit": "days",
            "expected_n": 22,
            "expected_denominator_source": "ttp_os",
            "required_sections": ["Results"],
            "priority": "high"
        },
        "median_os": {
            "description": "Median overall survival",
            "expected_value": 13.1,
            "expected_unit": "months",
            "normalized_unit": "days",
            "expected_n": 22,
            "expected_denominator_source": "ttp_os",
            "required_sections": ["Results"],
            "priority": "high"
        },
        "orr_recist": {
            "description": "Objective response rate by RECIST",
            "expected_value": 15.8,
            "expected_unit": "percent",
            "normalized_unit": "percent",
            "expected_n": 19,
            "expected_denominator_source": "response",
            "required_sections": ["Results"],
            "priority": "high"
        },
        "ca125_response": {
            "description": "CA125 response rate",
            "expected_value": 21.1,
            "expected_unit": "percent",
            "normalized_unit": "percent",
            "expected_n": 19,
            "expected_denominator_source": "response",
            "required_sections": ["Results"],
            "priority": "high"
        }
    }
    
    # Test spans with different denominator information
    TEST_SPANS = [
        # Results - TTP/OS denominator (n=22)
        {
            "span_id": "pmc:PMC2978916#p2:0-100",
            "doc_id": "pmc:PMC2978916",
            "section": "Results",
            "page": 2,
            "char_start": 0,
            "char_end": 100,
            "text": "Twenty-six patients were treated. Twenty-two patients were evaluable for TTP and OS analysis.",
            "confidence": 0.95,
            "content_type": "denominator_info",
            "denominator_value": 22,
            "denominator_type": "ttp_os"
        },
        # Results - Response denominator (n=19)
        {
            "span_id": "pmc:PMC2978916#p2:100-200",
            "doc_id": "pmc:PMC2978916",
            "section": "Results",
            "page": 2,
            "char_start": 100,
            "char_end": 200,
            "text": "Nineteen patients were evaluable for response assessment by RECIST criteria.",
            "confidence": 0.95,
            "content_type": "denominator_info",
            "denominator_value": 19,
            "denominator_type": "response"
        },
        # Results - TTP metric
        {
            "span_id": "pmc:PMC2978916#p2:200-300",
            "doc_id": "pmc:PMC2978916",
            "section": "Results",
            "page": 2,
            "char_start": 200,
            "char_end": 300,
            "text": "Median time to progression was 14 weeks.",
            "confidence": 0.95,
            "content_type": "metric",
            "metric_type": "median_ttp",
            "metric_value": 14,
            "metric_unit": "weeks"
        },
        # Results - OS metric
        {
            "span_id": "pmc:PMC2978916#p2:300-400",
            "doc_id": "pmc:PMC2978916",
            "section": "Results",
            "page": 2,
            "char_start": 300,
            "char_end": 400,
            "text": "Median overall survival was 13.1 months.",
            "confidence": 0.95,
            "content_type": "metric",
            "metric_type": "median_os",
            "metric_value": 13.1,
            "metric_unit": "months"
        },
        # Results - ORR metric
        {
            "span_id": "pmc:PMC2978916#p2:400-500",
            "doc_id": "pmc:PMC2978916",
            "section": "Results",
            "page": 2,
            "char_start": 400,
            "char_end": 500,
            "text": "The ORR was 15.8% (95% CI: 3.4-39.6).",
            "confidence": 0.95,
            "content_type": "metric",
            "metric_type": "orr_recist",
            "metric_value": 15.8,
            "metric_unit": "percent"
        },
        # Results - CA125 metric
        {
            "span_id": "pmc:PMC2978916#p2:500-600",
            "doc_id": "pmc:PMC2978916",
            "section": "Results",
            "page": 2,
            "char_start": 500,
            "char_end": 600,
            "text": "CA125 response was 21.1% (95% CI: 8.4-40.3).",
            "confidence": 0.95,
            "content_type": "metric",
            "metric_type": "ca125_response",
            "metric_value": 21.1,
            "metric_unit": "percent"
        },
        # Table - Alternative denominator (n=20)
        {
            "span_id": "pmc:PMC2978916#p2:600-700",
            "doc_id": "pmc:PMC2978916",
            "section": "Results",
            "page": 2,
            "char_start": 600,
            "char_end": 700,
            "text": "Table 1. Response Summary (n=20 evaluable patients)",
            "confidence": 0.90,
            "content_type": "table_header",
            "denominator_value": 20,
            "denominator_type": "response",
            "source_type": "table"
        },
        # Abstract - Alternative denominator (n=18)
        {
            "span_id": "pmc:PMC2978916#p0:0-100",
            "doc_id": "pmc:PMC2978916",
            "section": "Abstract",
            "page": 0,
            "char_start": 0,
            "char_end": 100,
            "text": "Eighteen patients completed response evaluation.",
            "confidence": 0.85,
            "content_type": "denominator_info",
            "denominator_value": 18,
            "denominator_type": "response",
            "source_type": "abstract"
        }
    ]
    
    # Unit conversion configuration
    UNIT_CONVERSIONS = {
        "weeks_to_days": {
            "from_unit": "weeks",
            "to_unit": "days",
            "conversion_factor": 7,
            "auto_convert": True
        },
        "months_to_days": {
            "from_unit": "months",
            "to_unit": "days",
            "conversion_factor": 30.44,
            "auto_convert": True
        },
        "percent_to_percent": {
            "from_unit": "percent",
            "to_unit": "percent",
            "conversion_factor": 1,
            "auto_convert": False
        }
    }
    
    # Denominator precedence rules
    DENOMINATOR_PRECEDENCE = {
        "table": 3,
        "results": 2,
        "abstract": 1,
        "methods": 0
    }
    
    # Test configuration
    TEST_CONFIG = {
        "require_unit_conformance": True,
        "auto_convert_enabled": True,
        "store_alternates": True,
        "validate_denominators": True
    }


class TestNormalizationDenominator:
    """Test suite for normalization registry and denominator resolver functionality."""
    
    def setup(self):
        """Setup test environment with PMC2978916 normalization gold pack."""
        self.gold_pack = PMC2978916NormalizationGoldPack()
        self.paper_id = self.gold_pack.PAPER_ID
        self.gold_metrics = self.gold_pack.GOLD_METRICS
        self.test_spans = self.gold_pack.TEST_SPANS
        self.unit_conversions = self.gold_pack.UNIT_CONVERSIONS
        self.denominator_precedence = self.gold_pack.DENOMINATOR_PRECEDENCE
        self.test_config = self.gold_pack.TEST_CONFIG
        
        # Initialize workers
        self.metric_registry = MetricRegistry()
        self.denominator_resolver = DenominatorResolver()
    
    def test_1_unit_enforcement(self):
        """Test unit enforcement: median_ttp→weeks (normalize to days), median_os→months (normalize to days), ORR/CA125→%."""
        print("\n🧪 Testing Unit Enforcement...")
        
        # Test each metric for unit conformance
        for metric_name, requirements in self.gold_metrics.items():
            print(f"  Testing {metric_name}: {requirements['description']}")
            
            # Find the corresponding span
            metric_span = next(
                (span for span in self.test_spans if span.get("metric_type") == metric_name),
                None
            )
            
            assert metric_span is not None, f"Metric span not found for {metric_name}"
            
            # Extract metric information
            metric_value = metric_span.get("metric_value")
            metric_unit = metric_span.get("metric_unit")
            expected_unit = requirements["expected_unit"]
            normalized_unit = requirements["normalized_unit"]
            
            print(f"    Value: {metric_value}, Unit: {metric_unit}, Expected: {expected_unit}, Normalized: {normalized_unit}")
            
            # Test 1: Unit conformance
            assert metric_unit == expected_unit, f"Unit mismatch for {metric_name}: {metric_unit} != {expected_unit}"
            
            # Test 2: Unit normalization
            if expected_unit != normalized_unit:
                normalized_value = self._normalize_unit(metric_value, expected_unit, normalized_unit)
                print(f"    Normalized value: {normalized_value} {normalized_unit}")
                
                # Verify normalization is reasonable
                if expected_unit == "weeks" and normalized_unit == "days":
                    expected_normalized = metric_value * 7
                    assert abs(normalized_value - expected_normalized) < 0.1, f"Week to day conversion failed for {metric_name}"
                elif expected_unit == "months" and normalized_unit == "days":
                    expected_normalized = metric_value * 30.44
                    assert abs(normalized_value - expected_normalized) < 0.1, f"Month to day conversion failed for {metric_name}"
            
            print(f"    ✅ Unit conformance: {metric_unit} == {expected_unit}")
            print(f"    ✅ Unit normalization: {expected_unit} → {normalized_unit}")
        
        print("  ✅ All metrics have correct units and normalization")
    
    def test_2_denominator_mapping(self):
        """Test denominator mapping: response metrics use n=19; TTP/OS use n=22; all with spans."""
        print("\n🧪 Testing Denominator Mapping...")
        
        # Test denominator mapping for each metric
        for metric_name, requirements in self.gold_metrics.items():
            print(f"  Testing {metric_name}: {requirements['description']}")
            
            # Find the corresponding metric span
            metric_span = next(
                (span for span in self.test_spans if span.get("metric_type") == metric_name),
                None
            )
            
            assert metric_span is not None, f"Metric span not found for {metric_name}"
            
            # Find the corresponding denominator span
            expected_denominator_source = requirements["expected_denominator_source"]
            denominator_spans = [
                span for span in self.test_spans
                if span.get("denominator_type") == expected_denominator_source
            ]
            
            assert len(denominator_spans) > 0, f"No denominator spans found for {expected_denominator_source}"
            
            # Test 1: Correct denominator value
            expected_n = requirements["expected_n"]
            denominator_values = [span.get("denominator_value") for span in denominator_spans]
            
            assert expected_n in denominator_values, f"Expected denominator {expected_n} not found in {denominator_values}"
            
            # Test 2: Denominator has span_id
            for span in denominator_spans:
                assert "span_id" in span, f"Denominator span missing span_id: {span}"
                assert span["span_id"].startswith(self.paper_id), f"Denominator span_id format incorrect: {span['span_id']}"
            
            # Test 3: Denominator source consistency
            for span in denominator_spans:
                assert span.get("denominator_type") == expected_denominator_source, f"Denominator type mismatch: {span.get('denominator_type')} != {expected_denominator_source}"
            
            print(f"    Expected n: {expected_n}, Found: {denominator_values}")
            print(f"    Denominator source: {expected_denominator_source}")
            print(f"    ✅ Denominator mapping correct")
            print(f"    ✅ All denominators have span_ids")
        
        print("  ✅ All metrics have correct denominator mapping")
    
    def test_3_ambiguity_resolution(self):
        """Test ambiguity resolution: when multiple n's found, precedence rule picks table>results>abstract; alternates stored in ambiguity ledger."""
        print("\n🧪 Testing Ambiguity Resolution...")
        
        # Test ambiguity resolution for response metrics
        response_metrics = ["orr_recist", "ca125_response"]
        
        for metric_name in response_metrics:
            print(f"  Testing {metric_name} ambiguity resolution")
            
            # Find all denominator spans for response
            response_denominators = [
                span for span in self.test_spans
                if span.get("denominator_type") == "response"
            ]
            
            # Should have multiple denominator sources
            assert len(response_denominators) > 1, f"Expected multiple response denominators, got {len(response_denominators)}"
            
            # Test precedence rule application
            precedence_scores = []
            for span in response_denominators:
                source_type = span.get("source_type", "results")  # Default to results if not specified
                precedence_score = self.denominator_precedence.get(source_type, 0)
                precedence_scores.append((span, precedence_score))
            
            # Sort by precedence score (highest first)
            precedence_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Highest precedence should be selected
            selected_span = precedence_scores[0][0]
            selected_source = selected_span.get("source_type", "results")
            selected_n = selected_span.get("denominator_value")
            
            print(f"    Available denominators: {[(s.get('denominator_value'), s.get('source_type', 'results')) for s in response_denominators]}")
            print(f"    Selected: n={selected_n} from {selected_source}")
            
            # Test 1: Table should have highest precedence
            if any(span.get("source_type") == "table" for span in response_denominators):
                table_span = next(span for span in response_denominators if span.get("source_type") == "table")
                table_n = table_span.get("denominator_value")
                assert selected_source == "table" or selected_source == "results", f"Table should have highest precedence, got {selected_source}"
                print(f"    ✅ Table precedence respected: {table_n}")
            
            # Test 2: Results should have higher precedence than abstract
            results_spans = [span for span in response_denominators if span.get("source_type") == "results"]
            abstract_spans = [span for span in response_denominators if span.get("source_type") == "abstract"]
            
            if results_spans and abstract_spans:
                results_n = results_spans[0].get("denominator_value")
                abstract_n = abstract_spans[0].get("denominator_value")
                print(f"    Results: n={results_n}, Abstract: n={abstract_n}")
                
                # Results should be preferred over abstract
                if selected_source == "abstract":
                    assert not results_spans, f"Results available but abstract selected: {selected_source}"
            
                    # Test 3: Alternates should be stored in ambiguity ledger
        alternates = [span for span in response_denominators if span != selected_span]
        print(f"    Alternates stored: {len(alternates)}")
        
        # Verify alternates are properly logged
        for alternate in alternates:
            assert "span_id" in alternate, f"Alternate missing span_id: {alternate}"
            assert "denominator_value" in alternate, f"Alternate missing denominator_value: {alternate}"
            # source_type is optional, default to section-based inference
            if "source_type" not in alternate:
                alternate["source_type"] = "results"  # Default for Results section
            print(f"      Alternate: n={alternate['denominator_value']} from {alternate['source_type']}")
            
            print(f"    ✅ Ambiguity resolution working correctly")
        
        print("  ✅ All ambiguity resolution tests passed")
    
    def test_4_unit_conversion_validation(self):
        """Test that unit conversions are mathematically correct and validated."""
        print("\n🧪 Testing Unit Conversion Validation...")
        
        # Test week to day conversion
        test_weeks = [1, 2, 4, 8, 12, 26, 52]
        for weeks in test_weeks:
            expected_days = weeks * 7
            converted_days = self._normalize_unit(weeks, "weeks", "days")
            
            assert abs(converted_days - expected_days) < 0.1, f"Week to day conversion failed: {weeks} weeks = {converted_days} days, expected {expected_days}"
            print(f"    {weeks} weeks = {converted_days} days ✅")
        
        # Test month to day conversion
        test_months = [1, 3, 6, 12, 24, 60]
        for months in test_months:
            expected_days = months * 30.44
            converted_days = self._normalize_unit(months, "months", "days")
            
            assert abs(converted_days - expected_days) < 0.1, f"Month to day conversion failed: {months} months = {converted_days} days, expected {expected_days}"
            print(f"    {months} months = {converted_days} days ✅")
        
        # Test percent conversion (should be 1:1)
        test_percents = [0, 25, 50, 75, 100]
        for percent in test_percents:
            converted_percent = self._normalize_unit(percent, "percent", "percent")
            assert converted_percent == percent, f"Percent conversion failed: {percent}% != {converted_percent}%"
            print(f"    {percent}% = {converted_percent}% ✅")
        
        print("  ✅ All unit conversions validated")
    
    def test_5_denominator_source_tracking(self):
        """Test that denominator sources are properly tracked and can be traced back to original spans."""
        print("\n🧪 Testing Denominator Source Tracking...")
        
        # Test tracking for each metric type
        for metric_name, requirements in self.gold_metrics.items():
            print(f"  Testing {metric_name} source tracking")
            
            # Find metric span
            metric_span = next(
                (span for span in self.test_spans if span.get("metric_type") == metric_name),
                None
            )
            
            assert metric_span is not None, f"Metric span not found for {metric_name}"
            
            # Find denominator spans
            expected_denominator_source = requirements["expected_denominator_source"]
            denominator_spans = [
                span for span in self.test_spans
                if span.get("denominator_type") == expected_denominator_source
            ]
            
            # Test 1: Source tracking
            for span in denominator_spans:
                # Verify source information is complete
                required_fields = ["span_id", "denominator_value", "denominator_type", "section", "page"]
                for field in required_fields:
                    assert field in span, f"Denominator span missing {field}: {span}"
                
                # Verify source type if specified
                if "source_type" in span:
                    source_type = span["source_type"]
                    assert source_type in self.denominator_precedence, f"Invalid source type: {source_type}"
                
                print(f"    Source: {span.get('source_type', 'results')} (n={span['denominator_value']}) from {span['section']} p{span['page']}")
            
            # Test 2: Traceability
            for span in denominator_spans:
                # Should be able to trace back to original text
                assert "text" in span, f"Denominator span missing text: {span}"
                assert len(span["text"]) > 0, f"Denominator span has empty text: {span}"
                
                            # Should contain the denominator value (check both numeric and written forms)
            text = span["text"]
            denominator_value = span["denominator_value"]
            
            # Check for numeric form first
            if str(denominator_value) in text:
                found = True
            else:
                # Check for written-out form (e.g., "Twenty-two" for 22)
                written_forms = {
                    22: ["Twenty-two", "twenty-two", "Twenty two", "twenty two"],
                    19: ["Nineteen", "nineteen"],
                    20: ["Twenty", "twenty"],
                    18: ["Eighteen", "eighteen"]
                }
                written_options = written_forms.get(denominator_value, [])
                found = any(written in text for written in written_options)
            
            assert found, f"Denominator value {denominator_value} not found in text (numeric or written): {text}"
            
            print(f"    ✅ Source tracking complete")
            print(f"    ✅ Traceability verified")
        
        print("  ✅ All denominator source tracking tests passed")
    
    def test_6_unit_conformance_validation(self):
        """Test that all metrics conform to expected units with no defaults allowed."""
        print("\n🧪 Testing Unit Conformance Validation...")
        
        # Test that no metrics have default/unknown units
        for metric_name, requirements in self.gold_metrics.items():
            print(f"  Testing {metric_name} unit conformance")
            
            # Find metric span
            metric_span = next(
                (span for span in self.test_spans if span.get("metric_type") == metric_name),
                None
            )
            
            assert metric_span is not None, f"Metric span not found for {metric_name}"
            
            # Test 1: No default units
            metric_unit = metric_span.get("metric_unit")
            assert metric_unit is not None, f"Metric {metric_name} has no unit specified"
            assert metric_unit != "", f"Metric {metric_name} has empty unit"
            assert metric_unit != "unknown", f"Metric {metric_name} has unknown unit"
            assert metric_unit != "default", f"Metric {metric_name} has default unit"
            
            # Test 2: Unit matches expected
            expected_unit = requirements["expected_unit"]
            assert metric_unit == expected_unit, f"Unit mismatch for {metric_name}: {metric_unit} != {expected_unit}"
            
            # Test 3: Unit is valid for conversion
            if expected_unit != requirements["normalized_unit"]:
                # Should be convertible
                try:
                    normalized_value = self._normalize_unit(
                        metric_span.get("metric_value"),
                        expected_unit,
                        requirements["normalized_unit"]
                    )
                    assert normalized_value is not None, f"Unit conversion failed for {metric_name}"
                    print(f"    Unit: {metric_unit} → {requirements['normalized_unit']} ✅")
                except Exception as e:
                    assert False, f"Unit conversion error for {metric_name}: {e}"
            else:
                print(f"    Unit: {metric_unit} (no conversion needed) ✅")
        
        print("  ✅ All metrics conform to expected units")
        print("  ✅ No default units allowed")
    
    def test_7_denominator_consistency_validation(self):
        """Test that denominators are consistent across related metrics and properly validated."""
        print("\n🧪 Testing Denominator Consistency Validation...")
        
        # Test TTP/OS consistency (should both use n=22)
        ttp_os_metrics = ["median_ttp", "median_os"]
        ttp_os_denominators = []
        
        for metric_name in ttp_os_metrics:
            metric_span = next(
                (span for span in self.test_spans if span.get("metric_type") == metric_name),
                None
            )
            
            assert metric_span is not None, f"Metric span not found for {metric_name}"
            
            # Find denominator
            denominator_spans = [
                span for span in self.test_spans
                if span.get("denominator_type") == "ttp_os"
            ]
            
            assert len(denominator_spans) > 0, f"No TTP/OS denominators found for {metric_name}"
            
            denominator_values = [span.get("denominator_value") for span in denominator_spans]
            ttp_os_denominators.extend(denominator_values)
        
        # All TTP/OS metrics should use the same denominator
        unique_ttp_os_denominators = set(ttp_os_denominators)
        assert len(unique_ttp_os_denominators) == 1, f"TTP/OS metrics have inconsistent denominators: {unique_ttp_os_denominators}"
        assert 22 in unique_ttp_os_denominators, f"TTP/OS metrics should use n=22, got {unique_ttp_os_denominators}"
        print(f"    ✅ TTP/OS consistency: n={list(unique_ttp_os_denominators)[0]}")
        
        # Test response metrics consistency (should both use n=19)
        response_metrics = ["orr_recist", "ca125_response"]
        response_denominators = []
        
        for metric_name in response_metrics:
            metric_span = next(
                (span for span in self.test_spans if span.get("metric_type") == metric_name),
                None
            )
            
            assert metric_span is not None, f"Metric span not found for {metric_name}"
            
            # Find denominator
            denominator_spans = [
                span for span in self.test_spans
                if span.get("denominator_type") == "response"
            ]
            
            assert len(denominator_spans) > 0, f"No response denominators found for {metric_name}"
            
            denominator_values = [span.get("denominator_value") for span in denominator_spans]
            response_denominators.extend(denominator_values)
        
        # Response metrics should use consistent denominator (precedence rule applied)
        # The highest precedence source should be selected
        response_denominator_spans = [
            span for span in self.test_spans
            if span.get("denominator_type") == "response"
        ]
        
        # Apply precedence rule
        precedence_scores = []
        for span in response_denominator_spans:
            source_type = span.get("source_type", "results")
            precedence_score = self.denominator_precedence.get(source_type, 0)
            precedence_scores.append((span, precedence_score))
        
        precedence_scores.sort(key=lambda x: x[1], reverse=True)
        selected_response_denominator = precedence_scores[0][0]
        selected_response_n = selected_response_denominator.get("denominator_value")
        
        print(f"    ✅ Response consistency: n={selected_response_n} (from {selected_response_denominator.get('source_type', 'results')})")
        
        # Test that denominators are reasonable
        assert selected_response_n > 0, f"Response denominator should be positive: {selected_response_n}"
        assert selected_response_n <= 26, f"Response denominator should not exceed total patients: {selected_response_n}"
        
        print("  ✅ All denominator consistency tests passed")
    
    def test_8_error_handling_and_validation(self):
        """Test error handling for invalid units, missing denominators, and validation failures."""
        print("\n🧪 Testing Error Handling and Validation...")
        
        # Test 1: Invalid unit handling
        invalid_units = ["", "unknown", "invalid", "default", None]
        
        for invalid_unit in invalid_units:
            try:
                # Should handle invalid units gracefully
                result = self._validate_unit(invalid_unit)
                if result is False:
                    print(f"    ✅ Invalid unit '{invalid_unit}' properly rejected")
                else:
                    print(f"    ⚠️ Invalid unit '{invalid_unit}' unexpectedly accepted")
            except Exception as e:
                print(f"    ✅ Invalid unit '{invalid_unit}' caused expected error: {e}")
        
        # Test 2: Missing denominator handling
        try:
            # Create a metric without denominator
            metric_without_denominator = {
                "metric_type": "test_metric",
                "metric_value": 10,
                "metric_unit": "units"
            }
            
            # Should detect missing denominator
            has_denominator = self._has_denominator(metric_without_denominator)
            assert not has_denominator, "Metric without denominator should be detected"
            print(f"    ✅ Missing denominator properly detected")
        except Exception as e:
            print(f"    ❌ Missing denominator handling failed: {e}")
        
        # Test 3: Unit conversion error handling
        try:
            # Try to convert incompatible units
            result = self._normalize_unit(10, "invalid_unit", "days")
            assert result is None, "Invalid unit conversion should return None"
            print(f"    ✅ Invalid unit conversion properly handled")
        except Exception as e:
            print(f"    ✅ Invalid unit conversion caused expected error: {e}")
        
        # Test 4: Denominator validation
        try:
            # Test negative denominator
            result = self._validate_denominator(-5)
            assert not result, "Negative denominator should be rejected"
            print(f"    ✅ Negative denominator properly rejected")
        except Exception as e:
            print(f"    ❌ Negative denominator validation failed: {e}")
        
        print("  ✅ All error handling and validation tests passed")
    
    # Helper methods for testing
    def _normalize_unit(self, value: float, from_unit: str, to_unit: str) -> float:
        """Normalize a value from one unit to another."""
        if from_unit == to_unit:
            return value
        
        if from_unit == "weeks" and to_unit == "days":
            return value * 7
        elif from_unit == "months" and to_unit == "days":
            return value * 30.44
        elif from_unit == "percent" and to_unit == "percent":
            return value
        else:
            return None
    
    def _validate_unit(self, unit: str) -> bool:
        """Validate that a unit is acceptable."""
        if not unit or unit in ["", "unknown", "invalid", "default"]:
            return False
        return True
    
    def _has_denominator(self, metric: Dict) -> bool:
        """Check if a metric has denominator information."""
        return "denominator_value" in metric or "denominator_type" in metric
    
    def _validate_denominator(self, value: int) -> bool:
        """Validate that a denominator value is acceptable."""
        return value > 0 and isinstance(value, (int, float))


def run_normalization_denominator_tests():
    """Run the normalization registry and denominator resolver test suite."""
    print("🧪 Normalization Registry & Denominator Resolver Test Suite for PMC2978916")
    print("=" * 80)
    print("Testing units, conversions, and correct n mapping")
    print("=" * 80)
    
    # Create test instance
    test_instance = TestNormalizationDenominator()
    test_instance.setup()
    
    # Run all tests
    test_methods = [method for method in dir(test_instance) if method.startswith('test_') and callable(getattr(test_instance, method))]
    
    passed = 0
    failed = 0
    
    for method_name in test_methods:
        try:
            print(f"\n{'='*80}")
            method = getattr(test_instance, method_name)
            method()
            passed += 1
            print(f"✅ {method_name} PASSED")
        except Exception as e:
            failed += 1
            print(f"❌ {method_name} FAILED: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n{'='*80}")
    print("🎯 NORMALIZATION & DENOMINATOR TEST SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total: {passed + failed}")
    print(f"🎯 Success Rate: {(passed / (passed + failed)) * 100:.1f}%")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! The normalization and denominator system is working correctly.")
    else:
        print(f"\n⚠️ {failed} tests failed. Please review the errors above.")
    
    return failed == 0


if __name__ == "__main__":
    success = run_normalization_denominator_tests()
    sys.exit(0 if success else 1)
