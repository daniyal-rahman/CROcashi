#!/usr/bin/env python3
"""
Test to verify that the safety misclassification bug is fixed.

This test addresses the bug where "Grade 3+ AEs 25%" was incorrectly classified
as response_rate when it should be classified as safety with endpoint grade≥3_AE_rate.

Fixes implemented:
1. Route sentences containing {"AE", "adverse", "toxicity", "grade"} to type='safety' and endpoint grade≥3_AE_rate, not response_rate
2. Add a unit test: any claim with token "grade" cannot be mapped to response_rate
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


class SafetyMisclassificationBugTest:
    """Test to verify that the safety misclassification bug is fixed."""
    
    def __init__(self):
        self.paper_id = "pmc:PMC2978916"
        self.title = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
    
    def get_test_spans(self):
        """Get test spans with safety content that was being misclassified."""
        test_spans = [
            # This span contains the problematic pattern: "Grade 3+ AEs occurred in 25% of patients"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Grade 3+ AEs occurred in 25% of patients.",
                section="Results",
                char_start=300,
                char_end=400,
                confidence=0.85
            ),
            # Additional test case: "Grade 4 toxicity was observed in 10% of subjects"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Grade 4 toxicity was observed in 10% of subjects.",
                section="Results",
                char_start=400,
                char_end=500,
                confidence=0.90
            ),
            # Test case: "Overall AE rate was 45%"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Overall AE rate was 45%",
                section="Results",
                char_start=500,
                char_end=600,
                confidence=0.85
            ),
            # Control case: "Response rate was 15.8%"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Response rate was 15.8%",
                section="Results",
                char_start=600,
                char_end=700,
                confidence=0.95
            )
        ]
        return test_spans
    
    def test_safety_classification(self):
        """Test that safety content is properly classified as safety type."""
        print("🧪 TESTING SAFETY CLASSIFICATION - PREVENTING MISCLASSIFICATION")
        print("=" * 80)
        
        test_spans = self.get_test_spans()
        
        # Test Claimizer
        claimizer = Claimizer()
        
        claim_result = claimizer.process({
            'evidence_spans': test_spans
        })
        
        print(f"✅ Success: {claim_result.success}")
        if claim_result.success:
            print("📊 Output:")
            print(json.dumps(claim_result.output, indent=2, default=str))
            
            # Check if we got claims
            claims = claim_result.output.get('claims', [])
            if claims:
                print(f"\n🎉 SUCCESS: Got {len(claims)} claims!")
                
                # Analyze the claims to check for safety misclassification
                safety_misclassification_issues = []
                safety_claims_found = 0
                response_rate_claims_found = 0
                
                for i, claim in enumerate(claims):
                    print(f"\n  Claim {i+1}: {claim.proposition}")
                    print(f"    Type: {claim.type}")
                    print(f"    Value: {claim.value}")
                    print(f"    Units: {claim.units}")
                    print(f"    Endpoint: {claim.endpoint}")
                    print(f"    span_ids: {claim.span_ids}")
                    
                    # Check for safety claims
                    if claim.type == 'safety':
                        safety_claims_found += 1
                        print(f"    ✅ SAFETY: Properly classified as safety")
                        
                        # Check endpoint mapping
                        if 'grade' in claim.proposition.lower():
                            if not claim.endpoint.startswith('grade≥'):
                                safety_misclassification_issues.append(f"Claim {i+1} ({claim.proposition}) has grade but wrong endpoint: {claim.endpoint}")
                                print(f"    ❌ MISCLASSIFICATION: Grade claim has wrong endpoint")
                            else:
                                print(f"    ✅ ENDPOINT: Proper grade endpoint: {claim.endpoint}")
                        elif 'AE' in claim.proposition.lower() or 'toxicity' in claim.proposition.lower():
                            if not any(safety_term in claim.endpoint.lower() for safety_term in ['ae', 'toxicity', 'safety']):
                                safety_misclassification_issues.append(f"Claim {i+1} ({claim.proposition}) has AE/toxicity but wrong endpoint: {claim.endpoint}")
                                print(f"    ❌ MISCLASSIFICATION: AE/toxicity claim has wrong endpoint")
                            else:
                                print(f"    ✅ ENDPOINT: Proper safety endpoint: {claim.endpoint}")
                    
                    # Check for response_rate claims (should NOT be safety content)
                    elif claim.type == 'effect_size' and 'response_rate' in claim.proposition:
                        response_rate_claims_found += 1
                        # Verify this is NOT safety content
                        if any(safety_term in claim.proposition.lower() for safety_term in ['grade', 'ae', 'adverse', 'toxicity']):
                            safety_misclassification_issues.append(f"Claim {i+1} ({claim.proposition}) has safety content but classified as effect_size")
                            print(f"    ❌ MISCLASSIFICATION: Safety content classified as effect_size")
                        else:
                            print(f"    ✅ RESPONSE_RATE: Properly classified as effect_size")
                    
                    # Check for misclassified safety content
                    if any(safety_term in claim.proposition.lower() for safety_term in ['grade', 'ae', 'adverse', 'toxicity']):
                        if claim.type != 'safety':
                            safety_misclassification_issues.append(f"Claim {i+1} ({claim.proposition}) has safety content but wrong type: {claim.type}")
                            print(f"    ❌ MISCLASSIFICATION: Safety content has wrong type: {claim.type}")
                
                # Summary of findings
                print(f"\n🔍 SAFETY CLASSIFICATION ANALYSIS:")
                print("-" * 50)
                print(f"Safety claims found: {safety_claims_found}")
                print(f"Response rate claims found: {response_rate_claims_found}")
                
                if safety_misclassification_issues:
                    print(f"\n❌ SAFETY MISCLASSIFICATION ISSUES FOUND:")
                    for issue in safety_misclassification_issues:
                        print(f"  - {issue}")
                    return False
                else:
                    print(f"\n✅ NO SAFETY MISCLASSIFICATION ISSUES FOUND")
                
                print(f"\n✅ PASS: Safety classification working correctly")
                return True
            else:
                print("\n❌ FAILURE: No claims generated!")
                return False
        else:
            print(f"❌ Error: {claim_result.error_message}")
            return False
    
    def test_grade_token_validation(self):
        """Test that any claim with token 'grade' cannot be mapped to response_rate."""
        print("\n🚨 TESTING GRADE TOKEN VALIDATION")
        print("-" * 50)
        
        # Test the specific rule: any claim with token "grade" cannot be mapped to response_rate
        test_cases = [
            "Grade 3+ AEs occurred in 25% of patients",
            "Grade 4 toxicity was observed in 10% of subjects",
            "Grade 2 adverse events were common",
            "Response rate was 15.8%"  # Control case - should NOT have grade
        ]
        
        validation_issues = []
        
        for test_text in test_cases:
            print(f"\nTesting: '{test_text}'")
            
            # Create a test span
            span = EvidenceSpan(
                doc_id="test",
                quote=test_text,
                section="Results",
                char_start=100,
                char_end=200,
                confidence=0.9
            )
            
            # Test Claimizer
            claimizer = Claimizer()
            
            claim_result = claimizer.process({
                'evidence_spans': [span]
            })
            
            if claim_result.success:
                claims = claim_result.output.get('claims', [])
                
                for claim in claims:
                    print(f"  Generated claim: {claim.proposition}")
                    print(f"    Type: {claim.type}")
                    print(f"    Endpoint: {claim.endpoint}")
                    
                    # Check the rule: grade token → safety type, not response_rate
                    if 'grade' in test_text.lower():
                        if claim.type != 'safety':
                            validation_issues.append(f"Text with 'grade' classified as {claim.type}, not safety")
                            print(f"    ❌ VIOLATION: Grade token should be safety type")
                        elif 'response_rate' in claim.endpoint:
                            validation_issues.append(f"Grade claim has response_rate endpoint: {claim.endpoint}")
                            print(f"    ❌ VIOLATION: Grade claim has response_rate endpoint")
                        else:
                            print(f"    ✅ VALID: Grade token properly classified as safety")
                    else:
                        # Non-grade text should be able to have response_rate
                        if 'response_rate' in claim.proposition and claim.type == 'effect_size':
                            print(f"    ✅ VALID: Non-grade text properly classified as response_rate")
                        elif 'response_rate' in claim.proposition and claim.type != 'effect_size':
                            validation_issues.append(f"Non-grade response_rate classified as {claim.type}")
                            print(f"    ❌ VIOLATION: Non-grade response_rate has wrong type")
            else:
                print(f"  ❌ Claimizer failed: {claim_result.error_message}")
                validation_issues.append(f"Claimizer failed for text: {test_text}")
        
        if validation_issues:
            print(f"\n❌ GRADE TOKEN VALIDATION ISSUES:")
            for issue in validation_issues:
                print(f"  - {issue}")
            return False
        else:
            print(f"\n✅ PASS: All grade token validation rules working correctly")
            return True
    
    def run_test(self):
        """Run all tests."""
        print("🧪 SAFETY MISCLASSIFICATION BUG TEST")
        print("=" * 80)
        print(f"📄 Paper: {self.paper_id}")
        print(f"📝 Title: {self.title}")
        print("=" * 80)
        
        # Run tests
        tests = [
            ("Safety Classification - Preventing Misclassification", self.test_safety_classification),
            ("Grade Token Validation", self.test_grade_token_validation)
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
    test = SafetyMisclassificationBugTest()
    success = test.run_test()
    
    if success:
        print("\n🎉 SAFETY MISCLASSIFICATION BUG FIXED!")
        print("The Claimizer now properly classifies safety content as safety type with correct endpoints.")
    else:
        print("\n❌ SAFETY MISCLASSIFICATION BUG STILL EXISTS!")
        print("Please review the errors above and implement additional fixes.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
