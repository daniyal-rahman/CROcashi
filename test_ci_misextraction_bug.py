#!/usr/bin/env python3
"""
Test to verify that the CI mis-extraction bug is fixed.

This test addresses the bug where "95%" from "95% CI" was incorrectly extracted
as a response rate value, when it should be extracted as confidence interval bounds.

Fixes implemented:
1. Add CI guard: if "95% CI" (or "CI") is within ±10 tokens, treat the % as ci_level and forbid using it as value
2. Update Claimizer to populate ci_lower=3.4, ci_upper=39.6 for the ORR claim and not emit a separate 95% effect
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


class CIMisExtractionBugTest:
    """Test to verify that the CI mis-extraction bug is fixed."""
    
    def __init__(self):
        self.paper_id = "pmc:PMC2978916"
        self.title = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
    
    def get_test_spans(self):
        """Get test spans with the specific CI pattern that was causing mis-extraction."""
        test_spans = [
            # This span contains the problematic pattern: "The ORR was 15.8% (95% CI: 3.4-39.6)."
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="The ORR was 15.8% (95% CI: 3.4-39.6).",
                section="Results",
                char_start=100,
                char_end=200,
                confidence=0.95
            ),
            # Additional test case: "Response rate was 25% with 90% CI: 15-35%"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Response rate was 25% with 90% CI: 15-35%",
                section="Results",
                char_start=200,
                char_end=300,
                confidence=0.90
            )
        ]
        return test_spans
    
    def test_ci_guard(self):
        """Test that the CI guard prevents mis-extraction of CI levels as effect values."""
        print("🧪 TESTING CI GUARD - PREVENTING MIS-EXTRACTION")
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
                
                # Analyze the claims to check for CI mis-extraction
                ci_mis_extraction_issues = []
                orr_claim_found = False
                orr_ci_found = False
                
                for i, claim in enumerate(claims):
                    print(f"\n  Claim {i+1}: {claim.proposition}")
                    print(f"    Type: {claim.type}")
                    print(f"    Value: {claim.value}")
                    print(f"    Units: {claim.units}")
                    print(f"    CI Lower: {claim.ci_lower}")
                    print(f"    CI Upper: {claim.ci_upper}")
                    print(f"    span_ids: {claim.span_ids}")
                    
                    # Check for ORR claim
                    if 'response_rate' in claim.proposition and claim.value == 15.8:
                        orr_claim_found = True
                        if claim.ci_lower == 3.4 and claim.ci_upper == 39.6:
                            orr_ci_found = True
                            print(f"    ✅ ORR claim with proper CI bounds")
                        else:
                            print(f"    ❌ ORR claim missing CI bounds")
                    
                    # Check for mis-extracted 95% claim
                    if claim.value == 95.0 and claim.units == 'percent':
                        ci_mis_extraction_issues.append(f"Claim {i+1} incorrectly extracted 95% as effect value")
                        print(f"    ❌ MIS-EXTRACTION: 95% should not be extracted as effect value")
                    
                    # Check for mis-extracted 90% claim
                    if claim.value == 90.0 and claim.units == 'percent':
                        ci_mis_extraction_issues.append(f"Claim {i+1} incorrectly extracted 90% as effect value")
                        print(f"    ❌ MIS-EXTRACTION: 90% should not be extracted as effect value")
                
                # Summary of findings
                print(f"\n🔍 CI MIS-EXTRACTION ANALYSIS:")
                print("-" * 50)
                
                if ci_mis_extraction_issues:
                    print(f"❌ CI MIS-EXTRACTION ISSUES FOUND:")
                    for issue in ci_mis_extraction_issues:
                        print(f"  - {issue}")
                    return False
                else:
                    print(f"✅ NO CI MIS-EXTRACTION ISSUES FOUND")
                
                if orr_claim_found:
                    if orr_ci_found:
                        print(f"✅ ORR claim properly extracted with CI bounds (3.4-39.6)")
                    else:
                        print(f"❌ ORR claim missing CI bounds")
                        return False
                else:
                    print(f"❌ ORR claim not found")
                    return False
                
                print(f"\n✅ PASS: CI guard working correctly - no mis-extraction of CI levels")
                return True
            else:
                print("\n❌ FAILURE: No claims generated!")
                return False
        else:
            print(f"❌ Error: {claim_result.error_message}")
            return False
    
    def test_confidence_interval_extraction(self):
        """Test that confidence intervals are properly extracted and associated with claims."""
        print("\n🔧 TESTING CONFIDENCE INTERVAL EXTRACTION")
        print("-" * 50)
        
        test_spans = self.get_test_spans()
        
        # Test Claimizer
        claimizer = Claimizer()
        
        claim_result = claimizer.process({
            'evidence_spans': test_spans
        })
        
        if claim_result.success:
            claims = claim_result.output.get('claims', [])
            
            # Look for claims with confidence intervals
            claims_with_ci = [c for c in claims if c.ci_lower is not None and c.ci_upper is not None]
            
            print(f"Claims with confidence intervals: {len(claims_with_ci)}")
            
            for claim in claims_with_ci:
                print(f"  {claim.proposition}: {claim.value}{claim.units} (CI: {claim.ci_lower}-{claim.ci_upper})")
            
            # Check that ORR claim has proper CI
            orr_claims = [c for c in claims if 'response_rate' in c.proposition and c.value == 15.8]
            if orr_claims:
                orr_claim = orr_claims[0]
                if orr_claim.ci_lower == 3.4 and orr_claim.ci_upper == 39.6:
                    print(f"✅ ORR claim has proper CI: {orr_claim.ci_lower}-{orr_claim.ci_upper}")
                    return True
                else:
                    print(f"❌ ORR claim has incorrect CI: {orr_claim.ci_lower}-{orr_claim.ci_upper}")
                    return False
            else:
                print(f"❌ ORR claim not found")
                return False
        
        return False
    
    def run_test(self):
        """Run all tests."""
        print("🧪 CI MIS-EXTRACTION BUG TEST")
        print("=" * 80)
        print(f"📄 Paper: {self.paper_id}")
        print(f"📝 Title: {self.title}")
        print("=" * 80)
        
        # Run tests
        tests = [
            ("CI Guard - Preventing Mis-extraction", self.test_ci_guard),
            ("Confidence Interval Extraction", self.test_confidence_interval_extraction)
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
    test = CIMisExtractionBugTest()
    success = test.run_test()
    
    if success:
        print("\n🎉 CI MIS-EXTRACTION BUG FIXED!")
        print("The Claimizer now properly handles confidence intervals without mis-extracting CI levels.")
    else:
        print("\n❌ CI MIS-EXTRACTION BUG STILL EXISTS!")
        print("Please review the errors above and implement additional fixes.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
