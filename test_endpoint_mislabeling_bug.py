#!/usr/bin/env python3
"""
Test to verify that the endpoint mislabeling bug is fixed.

This test addresses the bug where "14 weeks" and "13.1 months" were incorrectly labeled
as generic "duration" when they should be specific survival endpoints like "median_pfs" and "median_os".

Fixes implemented:
1. In the metric registry, map "median PFS/TTP" → median_pfs/median_ttp; "OS" → median_os
2. In Claimizer, when the sentence contains "PFS/TTP/OS", set endpoint accordingly; never fall back to generic duration
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


class EndpointMislabelingBugTest:
    """Test to verify that the endpoint mislabeling bug is fixed."""
    
    def __init__(self):
        self.paper_id = "pmc:PMC2978916"
        self.title = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
    
    def get_test_spans(self):
        """Get test spans with survival endpoints that were being mislabeled."""
        test_spans = [
            # This span contains the problematic pattern: "Median PFS was 14 weeks"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Median PFS was 14 weeks.",
                section="Results",
                char_start=700,
                char_end=800,
                confidence=0.90
            ),
            # Additional test case: "Median OS was 13.1 months"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Median OS was 13.1 months.",
                section="Results",
                char_start=800,
                char_end=900,
                confidence=0.90
            ),
            # Test case: "TTP was 8 weeks"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="TTP was 8 weeks.",
                section="Results",
                char_start=900,
                char_end=1000,
                confidence=0.85
            ),
            # Test case: "Progression-free survival was 12 weeks"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Progression-free survival was 12 weeks.",
                section="Results",
                char_start=1000,
                char_end=1100,
                confidence=0.85
            ),
            # Control case: "Treatment duration was 6 months"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Treatment duration was 6 months.",
                section="Results",
                char_start=1100,
                char_end=1200,
                confidence=0.80
            )
        ]
        return test_spans
    
    def test_survival_endpoint_detection(self):
        """Test that survival endpoints are properly detected and labeled."""
        print("🧪 TESTING SURVIVAL ENDPOINT DETECTION - PREVENTING MISLABELING")
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
                
                # Analyze the claims to check for endpoint mislabeling
                endpoint_mislabeling_issues = []
                survival_endpoints_found = 0
                generic_duration_found = 0
                
                for i, claim in enumerate(claims):
                    print(f"\n  Claim {i+1}: {claim.proposition}")
                    print(f"    Type: {claim.type}")
                    print(f"    Value: {claim.value}")
                    print(f"    Units: {claim.units}")
                    print(f"    Endpoint: {claim.endpoint}")
                    print(f"    span_ids: {claim.span_ids}")
                    
                    # Check for survival endpoints
                    if claim.endpoint in ['median_pfs', 'median_ttp', 'median_os']:
                        survival_endpoints_found += 1
                        print(f"    ✅ SURVIVAL: Properly labeled as {claim.endpoint}")
                        
                        # Verify the endpoint matches the content
                        if 'PFS' in claim.proposition or 'progression' in claim.proposition:
                            if claim.endpoint != 'median_pfs':
                                endpoint_mislabeling_issues.append(f"Claim {i+1} ({claim.proposition}) has PFS content but wrong endpoint: {claim.endpoint}")
                                print(f"    ❌ MISLABELING: PFS content has wrong endpoint")
                        elif 'TTP' in claim.proposition:
                            if claim.endpoint != 'median_ttp':
                                endpoint_mislabeling_issues.append(f"Claim {i+1} ({claim.proposition}) has TTP content but wrong endpoint: {claim.endpoint}")
                                print(f"    ❌ MISLABELING: TTP content has wrong endpoint")
                        elif 'OS' in claim.proposition or 'survival' in claim.proposition:
                            if claim.endpoint != 'median_os':
                                endpoint_mislabeling_issues.append(f"Claim {i+1} ({claim.proposition}) has OS content but wrong endpoint: {claim.endpoint}")
                                print(f"    ❌ MISLABELING: OS content has wrong endpoint")
                    
                    # Check for generic duration (should only be for non-survival time)
                    elif claim.endpoint == 'duration':
                        generic_duration_found += 1
                        # Verify this is NOT survival content
                        if any(survival_term in claim.proposition.lower() for survival_term in ['pfs', 'ttp', 'os', 'progression', 'survival']):
                            endpoint_mislabeling_issues.append(f"Claim {i+1} ({claim.proposition}) has survival content but labeled as duration")
                            print(f"    ❌ MISLABELING: Survival content labeled as duration")
                        else:
                            print(f"    ✅ DURATION: Properly labeled as duration (non-survival)")
                    
                    # Check for mislabeled survival content
                    if any(survival_term in claim.proposition.lower() for survival_term in ['pfs', 'ttp', 'os', 'progression', 'survival']):
                        if claim.endpoint == 'duration':
                            endpoint_mislabeling_issues.append(f"Claim {i+1} ({claim.proposition}) has survival content but labeled as duration")
                            print(f"    ❌ MISLABELING: Survival content labeled as duration")
                        elif claim.endpoint not in ['median_pfs', 'median_ttp', 'median_os']:
                            endpoint_mislabeling_issues.append(f"Claim {i+1} ({claim.proposition}) has survival content but wrong endpoint: {claim.endpoint}")
                            print(f"    ❌ MISLABELING: Survival content has wrong endpoint")
                
                # Summary of findings
                print(f"\n🔍 SURVIVAL ENDPOINT ANALYSIS:")
                print("-" * 50)
                print(f"Survival endpoints found: {survival_endpoints_found}")
                print(f"Generic duration claims found: {generic_duration_found}")
                
                if endpoint_mislabeling_issues:
                    print(f"\n❌ ENDPOINT MISLABELING ISSUES FOUND:")
                    for issue in endpoint_mislabeling_issues:
                        print(f"  - {issue}")
                    return False
                else:
                    print(f"\n✅ NO ENDPOINT MISLABELING ISSUES FOUND")
                
                print(f"\n✅ PASS: Survival endpoint detection working correctly")
                return True
            else:
                print("\n❌ FAILURE: No claims generated!")
                return False
        else:
            print(f"❌ Error: {claim_result.error_message}")
            return False
    
    def test_specific_endpoint_mapping(self):
        """Test that specific survival terms map to correct endpoints."""
        print("\n🎯 TESTING SPECIFIC ENDPOINT MAPPING")
        print("-" * 50)
        
        # Test the specific rule: survival terms must map to specific endpoints, not generic duration
        test_cases = [
            ("Median PFS was 14 weeks", "median_pfs"),
            ("Median OS was 13.1 months", "median_os"),
            ("TTP was 8 weeks", "median_ttp"),
            ("Progression-free survival was 12 weeks", "median_pfs"),
            ("Overall survival was 18 months", "median_os"),
            ("Treatment duration was 6 months", "duration")  # Control case - should be duration
        ]
        
        mapping_issues = []
        
        for test_text, expected_endpoint in test_cases:
            print(f"\nTesting: '{test_text}'")
            print(f"Expected endpoint: {expected_endpoint}")
            
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
                    print(f"    Endpoint: {claim.endpoint}")
                    
                    # Check the mapping
                    if claim.endpoint == expected_endpoint:
                        print(f"    ✅ CORRECT: Endpoint matches expected")
                    else:
                        mapping_issues.append(f"Text '{test_text}' mapped to {claim.endpoint}, expected {expected_endpoint}")
                        print(f"    ❌ INCORRECT: Endpoint {claim.endpoint} != expected {expected_endpoint}")
            else:
                print(f"  ❌ Claimizer failed: {claim_result.error_message}")
                mapping_issues.append(f"Claimizer failed for text: {test_text}")
        
        if mapping_issues:
            print(f"\n❌ ENDPOINT MAPPING ISSUES:")
            for issue in mapping_issues:
                print(f"  - {issue}")
            return False
        else:
            print(f"\n✅ PASS: All endpoint mappings working correctly")
            return True
    
    def run_test(self):
        """Run all tests."""
        print("🧪 ENDPOINT MISLABELING BUG TEST")
        print("=" * 80)
        print(f"📄 Paper: {self.paper_id}")
        print(f"📝 Title: {self.title}")
        print("=" * 80)
        
        # Run tests
        tests = [
            ("Survival Endpoint Detection - Preventing Mislabeling", self.test_survival_endpoint_detection),
            ("Specific Endpoint Mapping", self.test_specific_endpoint_mapping)
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
    test = EndpointMislabelingBugTest()
    success = test.run_test()
    
    if success:
        print("\n🎉 ENDPOINT MISLABELING BUG FIXED!")
        print("The Claimizer now properly labels survival endpoints as median_pfs, median_ttp, and median_os.")
    else:
        print("\n❌ ENDPOINT MISLABELING BUG STILL EXISTS!")
        print("Please review the errors above and implement additional fixes.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
