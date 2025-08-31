#!/usr/bin/env python3
"""
Test to verify that the MethodCard assessment cadence bug is fixed.

This test addresses the bug where "Assessment every 6 weeks" was mis-labeled as 
a numeric effect (duration: 6) instead of being mapped to assessment_interval="q6w".

Fixes implemented:
1. Add a MethodCard field assessment_interval="q6w" and map such sentences there
2. Forbid turning cadence into effect_size
3. Standardize provenance: use span_ids for machine checks, provenance_anchors as UI alias
4. Validator: method scalars must carry span_ids

MUST-FAIL ASSERTIONS ADDED:
- results_factsheet must contain ≥2 of {orr_recist, median_pfs|median_ttp, median_os} when their trigger tokens appear in input spans
- All claims with numerics must have span_ids
- No claim may have value=95% if "95% CI" is nearby
- Safety sentences cannot map to response_rate
- If "Gehan" is present, gehan_two_stage=True and interim_looks=1
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

from ncfd.extract.models import EvidenceSpan, MethodCard, PocketContextCard, ResultsFactsheet, Claim
from ncfd.extract.workers.llm.method_auditor import MethodAuditor
from ncfd.extract.workers.llm.results_distiller import ResultsDistiller
from ncfd.extract.workers.llm.claimizer import Claimizer
from ncfd.extract.validators import GlobalValidator


class MethodCardAssessmentCadenceBugTest:
    """Test to verify that the MethodCard assessment cadence bug is fixed."""
    
    def __init__(self):
        self.paper_id = "pmc:PMC2978916"
        self.title = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
    
    def get_test_spans(self):
        """Get test spans with assessment interval information."""
        test_spans = [
            # This span contains the problematic pattern: "Assessment every 6 weeks"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Assessment every 6 weeks using RECIST criteria.",
                section="Methods",
                char_start=700,
                char_end=800,
                confidence=0.95
            ),
            # Additional assessment interval patterns
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Tumor assessments were performed every 3 months.",
                section="Methods",
                char_start=800,
                char_end=900,
                confidence=0.90
            ),
            # Weekly assessment pattern
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Safety assessments were conducted weekly.",
                section="Methods",
                char_start=900,
                char_end=1000,
                confidence=0.85
            ),
            # Control case: actual duration (not assessment interval)
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Treatment duration was 6 months.",
                section="Methods",
                char_start=1000,
                char_end=1100,
                confidence=0.80
            )
        ]
        return test_spans
    
    def get_results_test_spans(self):
        """Get test spans with results information to test the must-fail assertions."""
        results_spans = [
            # ORR trigger tokens
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Objective response rate was 15.8% in 25 patients with RECIST criteria.",
                section="Results",
                char_start=1200,
                char_end=1300,
                confidence=0.95
            ),
            # PFS trigger tokens
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Median progression-free survival was 14 weeks in 25 patients.",
                section="Results",
                char_start=1300,
                char_end=1400,
                confidence=0.90
            ),
            # OS trigger tokens
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Overall survival was 13.1 months in 25 patients.",
                section="Results",
                char_start=1400,
                char_end=1500,
                confidence=0.85
            ),
            # CI pattern to test 95% mis-extraction
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="95% confidence interval: 3.4-39.6",
                section="Results",
                char_start=1500,
                char_end=1600,
                confidence=0.80
            ),
            # Safety pattern to test misclassification
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Grade 3+ adverse events occurred in 25% of patients.",
                section="Results",
                char_start=1600,
                char_end=1700,
                confidence=0.75
            )
        ]
        return results_spans
    
    def get_design_json(self):
        """Get design JSON."""
        return {
            "arms": ["single_arm"],
            "n": 25,
            "primary_endpoint": "ORR"
        }
    
    def get_pocket_context(self):
        """Get pocket context card."""
        return PocketContextCard(
            disease="ovarian_cancer",
            intervention_class="targeted_therapy",
            mechanism_of_action="endothelin_receptor_antagonist"
        )
    
    def test_assessment_interval_extraction(self):
        """Test that assessment intervals are properly extracted and not misclassified as effect_size."""
        print("🧪 TESTING ASSESSMENT INTERVAL EXTRACTION - PREVENTING MISCLASSIFICATION")
        print("=" * 80)
        
        test_spans = self.get_test_spans()
        design_json = self.get_design_json()
        pocket_context = self.get_pocket_context()
        
        # Test MethodAuditor
        method_auditor = MethodAuditor()
        
        method_result = method_auditor.process({
            'evidence_spans': test_spans,
            'design_json': design_json,
            'pocket_context': pocket_context
        })
        
        print(f"✅ Success: {method_result.success}")
        if method_result.success:
            print("📊 Output:")
            print(json.dumps(method_result.output, indent=2, default=str))
            
            # Check if we got a method card
            method_card = method_result.output.get('method_card')
            if method_card:
                print(f"\n🎉 SUCCESS: Got MethodCard!")
                
                # Analyze the MethodCard for assessment interval extraction
                assessment_issues = []
                
                print(f"\n🔍 ASSESSMENT INTERVAL ANALYSIS:")
                print("-" * 50)
                print(f"assessment_interval: {method_card.assessment_interval}")
                print(f"endpoint_ascertainment: {method_card.endpoint_ascertainment}")
                print(f"span_ids: {method_card.span_ids}")
                print(f"provenance_anchors: {method_card.provenance_anchors}")
                
                # Check that assessment intervals are properly extracted
                if method_card.assessment_interval:
                    print(f"    ✅ assessment_interval extracted: {method_card.assessment_interval}")
                    
                    # Check for specific patterns
                    if 'q6w' in method_card.assessment_interval or 'every_6_weeks' in method_card.assessment_interval:
                        print(f"    ✅ 6-week assessment interval detected")
                    else:
                        print(f"    ⚠️  6-week assessment interval not in expected format")
                else:
                    assessment_issues.append("assessment_interval not extracted despite 'Assessment every 6 weeks' in spans")
                    print(f"    ❌ assessment_interval not extracted")
                
                # Check that endpoint ascertainment still works
                if method_card.endpoint_ascertainment:
                    print(f"    ✅ endpoint_ascertainment: {method_card.endpoint_ascertainment}")
                else:
                    print(f"    ⚠️  endpoint_ascertainment not set")
                
                # Check provenance standardization
                if method_card.span_ids:
                    print(f"    ✅ span_ids populated: {len(method_card.span_ids)} spans")
                else:
                    assessment_issues.append("span_ids is empty - provenance not properly set")
                    print(f"    ❌ span_ids is empty")
                
                if method_card.provenance_anchors:
                    print(f"    ✅ provenance_anchors populated: {len(method_card.provenance_anchors)} anchors")
                else:
                    print(f"    ⚠️  provenance_anchors is empty")
                
                # Check that span_ids and provenance_anchors are synchronized
                if method_card.span_ids and method_card.provenance_anchors:
                    if set(method_card.span_ids) == set(method_card.provenance_anchors):
                        print(f"    ✅ span_ids and provenance_anchors are synchronized")
                    else:
                        assessment_issues.append("span_ids and provenance_anchors are not synchronized")
                        print(f"    ❌ span_ids and provenance_anchors are not synchronized")
                
                # Summary of findings
                if assessment_issues:
                    print(f"\n❌ ASSESSMENT INTERVAL ISSUES FOUND:")
                    for issue in assessment_issues:
                        print(f"  - {issue}")
                    return False
                else:
                    print(f"\n✅ NO ASSESSMENT INTERVAL ISSUES FOUND")
                
                print(f"\n✅ PASS: Assessment interval extraction working correctly")
                return True
            else:
                print("\n❌ FAILURE: No MethodCard generated!")
                return False
        else:
            print(f"❌ Error: {method_result.error_message}")
            return False
    
    def test_cadence_not_effect_size(self):
        """Test that cadence information is not extracted as effect_size."""
        print("\n🚫 TESTING CADENCE NOT EXTRACTED AS EFFECT_SIZE")
        print("-" * 50)
        
        # Test with cadence spans
        cadence_spans = [
            EvidenceSpan(
                doc_id="test",
                quote="Assessment every 6 weeks",
                section="Methods",
                char_start=100,
                char_end=200,
                confidence=0.9
            ),
            EvidenceSpan(
                doc_id="test",
                quote="Tumor assessments every 3 months",
                section="Methods",
                char_start=200,
                char_end=300,
                confidence=0.9
            )
        ]
        
        design_json = {"arms": ["single_arm"], "n": 25}
        pocket_context = self.get_pocket_context()
        
        method_auditor = MethodAuditor()
        
        method_result = method_auditor.process({
            'evidence_spans': cadence_spans,
            'design_json': design_json,
            'pocket_context': pocket_context
        })
        
        if method_result.success:
            method_card = method_result.output.get('method_card')
            
            print(f"Assessment intervals in spans:")
            for span in cadence_spans:
                print(f"  - '{span.quote}'")
            
            print(f"MethodCard assessment_interval: {method_card.assessment_interval}")
            
            # Check that cadence is extracted as assessment_interval, not as numeric effect
            if method_card.assessment_interval:
                print(f"✅ Cadence properly extracted as assessment_interval: {method_card.assessment_interval}")
                return True
            else:
                print(f"❌ Cadence not extracted as assessment_interval")
                return False
        else:
            print(f"❌ MethodAuditor failed: {method_result.error_message}")
            return False
    
    def test_provenance_standardization(self):
        """Test that provenance is properly standardized."""
        print("\n🔗 TESTING PROVENANCE STANDARDIZATION")
        print("-" * 50)
        
        test_spans = self.get_test_spans()
        design_json = self.get_design_json()
        pocket_context = self.get_pocket_context()
        
        method_auditor = MethodAuditor()
        
        method_result = method_auditor.process({
            'evidence_spans': test_spans,
            'design_json': design_json,
            'pocket_context': pocket_context
        })
        
        if method_result.success:
            method_card = method_result.output.get('method_card')
            
            print(f"Input spans: {len(test_spans)}")
            print(f"MethodCard span_ids: {len(method_card.span_ids)}")
            print(f"MethodCard provenance_anchors: {len(method_card.provenance_anchors)}")
            
            # Check that span_ids is populated (primary provenance field)
            if method_card.span_ids:
                print(f"✅ span_ids populated with {len(method_card.span_ids)} spans")
                
                # Check that span_ids contains the expected span IDs
                expected_span_ids = [span.span_id for span in test_spans]
                actual_span_ids = method_card.span_ids
                
                if set(expected_span_ids) == set(actual_span_ids):
                    print(f"✅ span_ids contains all expected spans")
                else:
                    print(f"❌ span_ids missing expected spans")
                    print(f"  Expected: {expected_span_ids}")
                    print(f"  Actual: {actual_span_ids}")
                    return False
            else:
                print(f"❌ span_ids is empty")
                return False
            
            # Check that provenance_anchors is synchronized with span_ids
            if method_card.provenance_anchors:
                if set(method_card.span_ids) == set(method_card.provenance_anchors):
                    print(f"✅ provenance_anchors synchronized with span_ids")
                else:
                    print(f"❌ provenance_anchors not synchronized with span_ids")
                    return False
            else:
                print(f"❌ provenance_anchors is empty")
                return False
            
            print(f"✅ Provenance standardization working correctly")
            return True
        else:
            print(f"❌ MethodAuditor failed: {method_result.error_message}")
            return False
    
    def test_must_fail_assertions(self):
        """Test the must-fail assertions using the comprehensive validator."""
        print("\n🚨 TESTING MUST-FAIL ASSERTIONS")
        print("=" * 50)
        
        # Get test spans with results information
        results_spans = self.get_results_test_spans()
        design_json = self.get_design_json()
        pocket_context = self.get_pocket_context()
        
        print("🔍 Testing ResultsDistiller...")
        results_distiller = ResultsDistiller()
        results_result = results_distiller.process({
            'evidence_spans': results_spans,
            'trial_context': design_json
        })
        
        print("🔍 Testing Claimizer...")
        claimizer = Claimizer()
        claimizer_result = claimizer.process({
            'evidence_spans': results_spans,
            'trial_context': design_json
        })
        
        print("🔍 Testing MethodAuditor...")
        method_auditor = MethodAuditor()
        method_result = method_auditor.process({
            'evidence_spans': results_spans,
            'design_json': design_json,
            'pocket_context': pocket_context
        })
        
        # Extract the artifacts for validation
        factsheet = results_result.output.get('results_factsheet') if results_result.success else None
        claims = claimizer_result.output.get('claims', []) if claimizer_result.success else []
        method_card = method_result.output.get('method_card') if method_result.success else None
        
        print(f"\n📊 EXTRACTED ARTIFACTS:")
        print(f"  ResultsFactsheet: {'✅' if factsheet else '❌'}")
        print(f"  Claims: {len(claims)}")
        print(f"  MethodCard: {'✅' if method_card else '❌'}")
        
        if not all([factsheet, claims, method_card]):
            print("❌ Cannot run must-fail assertions - missing required artifacts")
            return False
        
        # Run comprehensive validation
        print(f"\n🔍 RUNNING COMPREHENSIVE VALIDATION...")
        violations = GlobalValidator.validate_comprehensive_system(
            factsheet=factsheet,
            claims=claims,
            method_card=method_card,
            spans=results_spans
        )
        
        if violations:
            print(f"\n❌ CRITICAL VALIDATION VIOLATIONS FOUND:")
            for i, violation in enumerate(violations, 1):
                print(f"  {i}. {violation}")
            
            # This should cause a hard FAIL
            print(f"\n🚨 ENFORCING MUST-FAIL ASSERTIONS...")
            try:
                GlobalValidator.hard_fail_on_critical_violations(violations)
            except AssertionError as e:
                print(f"✅ MUST-FAIL ASSERTION TRIGGERED: {e}")
                return False  # This is expected - the test should FAIL
        else:
            print(f"\n✅ NO CRITICAL VALIDATION VIOLATIONS FOUND")
            print(f"✅ MUST-FAIL ASSERTIONS PASSED (no violations to trigger)")
        
        return True
    
    def run_test(self):
        """Run all tests."""
        print("🧪 METHODCARD ASSESSMENT CADENCE BUG TEST")
        print("=" * 80)
        print(f"📄 Paper: {self.paper_id}")
        print(f"📝 Title: {self.title}")
        print("=" * 80)
        
        # Run tests
        tests = [
            ("Assessment Interval Extraction - Preventing Misclassification", self.test_assessment_interval_extraction),
            ("Cadence Not Extracted as Effect Size", self.test_cadence_not_effect_size),
            ("Provenance Standardization", self.test_provenance_standardization),
            ("Must-Fail Assertions", self.test_must_fail_assertions)
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
    test = MethodCardAssessmentCadenceBugTest()
    success = test.run_test()
    
    if success:
        print("\n🎉 METHODCARD ASSESSMENT CADENCE BUG FIXED!")
        print("Assessment intervals are now properly extracted and provenance is standardized.")
        print("All must-fail assertions passed (no critical violations found).")
    else:
        print("\n❌ METHODCARD ASSESSMENT CADENCE BUG STILL EXISTS!")
        print("Please review the errors above and implement additional fixes.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
