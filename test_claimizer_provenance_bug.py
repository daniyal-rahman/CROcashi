#!/usr/bin/env python3
"""
Test to debug Claimizer provenance issue where claims have empty span_ids.

This test addresses the bug where claims are created with span_ids=[] despite
the EvidenceSpan having proper span_id values.

The issue is that every numeric claim must be span-anchored for proper provenance tracking.

Fixes implemented:
1. Ensure EvidenceSpan span_id is properly generated
2. Verify Claimizer sets claim.span_ids = [source_span_id]
3. Add global validator: any numeric with empty span_ids ⇒ FAIL
"""

import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.extract.models import EvidenceSpan, Claim
from ncfd.extract.workers.llm.claimizer import Claimizer


class ClaimizerProvenanceBugTest:
    """Test to debug and fix Claimizer provenance issue."""
    
    def __init__(self):
        self.paper_id = "pmc:PMC2978916"
        self.title = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
    
    def get_evidence_spans(self):
        """Get evidence spans with clear numeric data that should trigger claims."""
        # Test spans with comprehensive data - these should definitely trigger claims
        test_spans_data = [
            # Methods - Study design
            {
                "doc_id": "pmc:PMC2978916",
                "text": "This was a single-arm phase 2 study using Gehan's two-stage design.",
                "section": "Methods",
                "char_start": 100,
                "char_end": 200,
                "confidence": 0.95
            },
            # Methods - Response assessment
            {
                "doc_id": "pmc:PMC2978916",
                "text": "Response was assessed every 6 weeks using RECIST v1.1 criteria.",
                "section": "Methods",
                "char_start": 200,
                "char_end": 300,
                "confidence": 0.95
            },
            # Methods - Sample size
            {
                "doc_id": "pmc:PMC2978916",
                "text": "Twenty-two patients were evaluable for analysis.",
                "section": "Methods",
                "char_start": 300,
                "char_end": 400,
                "confidence": 0.90
            },
            # Results - Response rate (SHOULD TRIGGER numeric claim)
            {
                "doc_id": "pmc:PMC2978916",
                "text": "The ORR was 15.8% (95% CI: 3.4-39.6).",
                "section": "Results",
                "char_start": 100,
                "char_end": 200,
                "confidence": 0.95
            },
            # Results - Survival (SHOULD TRIGGER numeric claims)
            {
                "doc_id": "pmc:PMC2978916",
                "text": "Median PFS was 14 weeks and OS was 13.1 months.",
                "section": "Results",
                "char_start": 200,
                "char_end": 300,
                "confidence": 0.90
            },
            # Results - Safety (SHOULD TRIGGER numeric claim)
            {
                "doc_id": "pmc:PMC2978916",
                "text": "Grade 3+ AEs occurred in 25% of patients.",
                "section": "Results",
                "char_start": 300,
                "char_end": 400,
                "confidence": 0.85
            }
        ]
        
        # Convert spans to EvidenceSpan objects
        evidence_spans = []
        for span_data in test_spans_data:
            span = EvidenceSpan(
                doc_id=span_data["doc_id"],
                quote=span_data["text"],
                section=span_data["section"],
                page=None,
                char_start=span_data["char_start"],
                char_end=span_data["char_end"],
                confidence=span_data["confidence"]
            )
            evidence_spans.append(span)
        
        return evidence_spans
    
    def test_evidence_span_span_id_generation(self):
        """Test that EvidenceSpan objects properly generate span_id values."""
        print("🧪 EVIDENCE SPAN SPAN_ID GENERATION TEST")
        print("=" * 80)
        
        evidence_spans = self.get_evidence_spans()
        
        print("📊 Testing EvidenceSpan span_id generation:")
        for i, span in enumerate(evidence_spans):
            print(f"  Span {i+1}: {span.quote[:50]}...")
            print(f"    doc_id: {span.doc_id}")
            print(f"    section: {span.section}")
            print(f"    char_start: {span.char_start}")
            print(f"    char_end: {span.char_end}")
            print(f"    span_id: {span.span_id}")
            print(f"    span_ids list: {span.span_ids}")
            print()
        
        # Verify all spans have proper span_id values
        for span in evidence_spans:
            if not span.span_id:
                print(f"❌ FAIL: Span missing span_id: {span.quote[:50]}...")
                return False
            if not span.span_ids:
                print(f"❌ FAIL: Span missing span_ids list: {span.quote[:50]}...")
                return False
        
        print("✅ PASS: All EvidenceSpan objects have proper span_id values")
        return True
    
    def test_claimizer_provenance(self):
        """Test that Claimizer properly sets span_ids in claims."""
        print("\n🔧 TESTING CLAIMIZER PROVENANCE")
        print("-" * 50)
        
        evidence_spans = self.get_evidence_spans()
        
        # Test Claimizer
        claimizer = Claimizer()
        
        claim_result = claimizer.process({
            'evidence_spans': evidence_spans
        })
        
        print(f"✅ Success: {claim_result.success}")
        if claim_result.success:
            print("📊 Output:")
            print(json.dumps(claim_result.output, indent=2, default=str))
            
            # Check if we got claims
            claims = claim_result.output.get('claims', [])
            if claims:
                print(f"\n🎉 SUCCESS: Got {len(claims)} claims!")
                
                # Check provenance for each claim
                provenance_issues = []
                for i, claim in enumerate(claims):
                    print(f"\n  Claim {i+1}: {claim.proposition}")
                    print(f"    Type: {claim.type}")
                    print(f"    Value: {claim.value}")
                    print(f"    Units: {claim.units}")
                    print(f"    span_ids: {claim.span_ids}")
                    print(f"    doc_id: {claim.doc_id}")
                    
                    # Check if this is a numeric claim
                    if claim.value is not None:
                        if not claim.span_ids:
                            provenance_issues.append(f"Claim {i+1} ({claim.proposition}) has numeric value but empty span_ids")
                        elif len(claim.span_ids) == 0:
                            provenance_issues.append(f"Claim {i+1} ({claim.proposition}) has numeric value but empty span_ids list")
                        else:
                            print(f"    ✅ PROVENANCE: span_ids properly set")
                
                if provenance_issues:
                    print(f"\n❌ PROVENANCE ISSUES FOUND:")
                    for issue in provenance_issues:
                        print(f"  - {issue}")
                    return False
                else:
                    print(f"\n✅ PASS: All numeric claims have proper span_ids provenance")
            else:
                print("\n❌ FAILURE: No claims generated!")
                return False
        else:
            print(f"❌ Error: {claim_result.error_message}")
            return False
        
        return True
    
    def test_global_provenance_validator(self):
        """Test the global validator that rejects claims with empty span_ids."""
        print("\n🚨 TESTING GLOBAL PROVENANCE VALIDATOR")
        print("-" * 50)
        
        # Test the global validator directly
        from ncfd.extract.validators import GlobalValidator
        
        # Create a test claim with empty span_ids (this should fail validation)
        invalid_claim = Claim(
            claim_id="test#claim_0",
            doc_id="test",
            span_ids=[],  # Empty span_ids - this should cause validation failure
            type="effect_size",
            proposition="test_value: 15.8",
            stance="neutral",
            value=15.8,
            units="percent",
            endpoint="test_value"
        )
        
        print(f"Testing invalid claim with empty span_ids:")
        print(f"  span_ids: {invalid_claim.span_ids}")
        print(f"  value: {invalid_claim.value}")
        print(f"  units: {invalid_claim.units}")
        
        # Test the global validator
        is_valid, error_msg = GlobalValidator.validate_claim_provenance(invalid_claim)
        print(f"  Global validator result: is_valid={is_valid}, error_msg={error_msg}")
        
        # This should fail validation
        if is_valid:
            print("❌ FAIL: Global validator should reject claim with empty span_ids")
            print("This violates the requirement: 'any numeric with empty span_ids ⇒ FAIL'")
            return False
        else:
            print("✅ PASS: Global validator correctly rejects claim with empty span_ids")
        
        # Test the hard fail function
        hard_fail_result = GlobalValidator.hard_fail_on_empty_provenance([invalid_claim])
        print(f"  Hard fail result: {hard_fail_result}")
        
        if hard_fail_result:
            print("❌ FAIL: Hard fail should return False for claims with empty span_ids")
            return False
        else:
            print("✅ PASS: Hard fail correctly returns False for claims with empty span_ids")
        
        return True
    
    def run_test(self):
        """Run all tests."""
        print("🧪 CLAIMIZER PROVENANCE BUG TEST")
        print("=" * 80)
        print(f"📄 Paper: {self.paper_id}")
        print(f"📝 Title: {self.title}")
        print("=" * 80)
        
        # Run all tests
        tests = [
            ("EvidenceSpan span_id generation", self.test_evidence_span_span_id_generation),
            ("Claimizer provenance", self.test_claimizer_provenance),
            ("Global provenance validator", self.test_global_provenance_validator)
        ]
        
        results = []
        for test_name, test_func in tests:
            print(f"\n{'='*20} {test_name} {'='*20}")
            try:
                result = test_func()
                results.append((test_name, result))
            except Exception as e:
                print(f"❌ ERROR in {test_name}: {e}")
                results.append((test_name, False))
        
        # Summary
        print(f"\n🎯 TEST SUMMARY:")
        print("=" * 30)
        all_passed = True
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {test_name}: {status}")
            if not result:
                all_passed = False
        
        return all_passed


def main():
    """Run the test."""
    test = ClaimizerProvenanceBugTest()
    success = test.run_test()
    
    if success:
        print("\n🎉 ALL CLAIMIZER PROVENANCE TESTS PASSED!")
        print("Claims now have proper span_ids provenance tracking.")
    else:
        print("\n❌ SOME CLAIMIZER PROVENANCE TESTS FAILED!")
        print("Please review the errors above and implement additional fixes.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
