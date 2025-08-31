#!/usr/bin/env python3
"""
Test to verify that the MethodCard design inconsistencies bug is fixed.

This test addresses the bug where MethodCard had gehan_two_stage=False and 
interim_looks='unknown' while the input span said "Gehan's two-stage".

Fixes implemented:
1. Add a rule: presence of "Gehan" ⇒ design_archetype='single_arm_phase2_gehan', gehan_two_stage=True, interim_looks=1
2. Make this a must-fill; if "Gehan" span exists and fields aren't set, FAIL
3. Add validation for primary endpoint conflicts with trial_context
4. Emit warnings[] on mismatch and surface in the test summary
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

from ncfd.extract.models import EvidenceSpan, MethodCard, PocketContextCard
from ncfd.extract.workers.llm.method_auditor import MethodAuditor


class MethodCardDesignInconsistenciesBugTest:
    """Test to verify that the MethodCard design inconsistencies bug is fixed."""
    
    def __init__(self):
        self.paper_id = "pmc:PMC2978916"
        self.title = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
    
    def get_test_spans(self):
        """Get test spans with Gehan design information."""
        test_spans = [
            # This span contains the problematic pattern: "Gehan's two-stage design"
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="The study used Gehan's two-stage design for phase 2 evaluation.",
                section="Methods",
                char_start=400,
                char_end=500,
                confidence=0.95
            ),
            # Additional context about the design
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Interim analysis was planned after the first stage.",
                section="Methods",
                char_start=500,
                char_end=600,
                confidence=0.90
            ),
            # Primary endpoint information
            EvidenceSpan(
                doc_id="pmc:PMC2978916",
                quote="Primary endpoint was ORR using RECIST criteria.",
                section="Methods",
                char_start=600,
                char_end=700,
                confidence=0.95
            )
        ]
        return test_spans
    
    def get_design_json(self):
        """Get design JSON with conflicting primary endpoint."""
        return {
            "primary_endpoint": "feasibility_and_toxicity",  # This conflicts with paper spans
            "arms": ["single_arm"],
            "n": 25
        }
    
    def get_pocket_context(self):
        """Get pocket context card."""
        return PocketContextCard(
            disease="ovarian_cancer",
            intervention_class="targeted_therapy",
            mechanism_of_action="endothelin_receptor_antagonist"
        )
    
    def test_gehan_design_detection(self):
        """Test that Gehan design is properly detected and enforced."""
        print("🧪 TESTING GEHAN DESIGN DETECTION - PREVENTING INCONSISTENCIES")
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
                
                # Analyze the MethodCard for Gehan design consistency
                design_inconsistencies = []
                
                print(f"\n🔍 GEHAN DESIGN ANALYSIS:")
                print("-" * 50)
                print(f"gehan_two_stage: {method_card.gehan_two_stage}")
                print(f"design_archetype: {method_card.design_archetype}")
                print(f"interim_looks: {method_card.interim_looks}")
                print(f"primary_endpoint: {method_card.primary_endpoint}")
                print(f"warnings: {method_card.warnings}")
                
                # Check Gehan design must-fill rule
                if not method_card.gehan_two_stage:
                    design_inconsistencies.append("gehan_two_stage is False despite 'Gehan' in spans")
                    print(f"    ❌ INCONSISTENCY: gehan_two_stage=False")
                else:
                    print(f"    ✅ gehan_two_stage=True")
                
                if method_card.design_archetype != 'single_arm_phase2_gehan':
                    design_inconsistencies.append(f"design_archetype is '{method_card.design_archetype}', expected 'single_arm_phase2_gehan'")
                    print(f"    ❌ INCONSISTENCY: design_archetype='{method_card.design_archetype}'")
                else:
                    print(f"    ✅ design_archetype='single_arm_phase2_gehan'")
                
                if method_card.interim_looks != 1:
                    design_inconsistencies.append(f"interim_looks is {method_card.interim_looks}, expected 1 for Gehan design")
                    print(f"    ❌ INCONSISTENCY: interim_looks={method_card.interim_looks}")
                else:
                    print(f"    ✅ interim_looks=1")
                
                # Check for warnings about primary endpoint conflict
                endpoint_warnings = [w for w in method_card.warnings if 'endpoint' in w.lower()]
                if endpoint_warnings:
                    print(f"    ✅ Primary endpoint conflict warnings found: {len(endpoint_warnings)}")
                    for warning in endpoint_warnings:
                        print(f"      - {warning}")
                else:
                    print(f"    ⚠️  No primary endpoint conflict warnings found")
                
                # Summary of findings
                if design_inconsistencies:
                    print(f"\n❌ GEHAN DESIGN INCONSISTENCIES FOUND:")
                    for inconsistency in design_inconsistencies:
                        print(f"  - {inconsistency}")
                    return False
                else:
                    print(f"\n✅ NO GEHAN DESIGN INCONSISTENCIES FOUND")
                
                print(f"\n✅ PASS: Gehan design detection working correctly")
                return True
            else:
                print("\n❌ FAILURE: No MethodCard generated!")
                return False
        else:
            print(f"❌ Error: {method_result.error_message}")
            return False
    
    def test_primary_endpoint_conflict_validation(self):
        """Test that primary endpoint conflicts are properly validated and warned."""
        print("\n🚨 TESTING PRIMARY ENDPOINT CONFLICT VALIDATION")
        print("-" * 50)
        
        # Test with conflicting endpoints
        test_spans = self.get_test_spans()
        design_json = self.get_design_json()  # Has "feasibility_and_toxicity"
        pocket_context = self.get_pocket_context()
        
        method_auditor = MethodAuditor()
        
        method_result = method_auditor.process({
            'evidence_spans': test_spans,
            'design_json': design_json,
            'pocket_context': pocket_context
        })
        
        if method_result.success:
            method_card = method_result.output.get('method_card')
            
            print(f"Paper primary endpoint: {method_card.primary_endpoint}")
            print(f"Trial context primary endpoint: {design_json['primary_endpoint']}")
            
            # Check for conflict warnings
            conflict_warnings = [w for w in method_card.warnings if 'endpoint' in w.lower() and 'mismatch' in w.lower()]
            
            if conflict_warnings:
                print(f"✅ Primary endpoint conflict warnings found:")
                for warning in conflict_warnings:
                    print(f"  - {warning}")
                
                # Verify that paper spans override trial context
                if method_card.primary_endpoint == 'ORR_RECIST':
                    print(f"✅ Paper spans correctly override trial context")
                    return True
                else:
                    print(f"❌ Paper spans did not override trial context")
                    return False
            else:
                print(f"❌ No primary endpoint conflict warnings found")
                return False
        else:
            print(f"❌ MethodAuditor failed: {method_result.error_message}")
            return False
    
    def test_gehan_must_fill_rule(self):
        """Test that the Gehan must-fill rule is enforced."""
        print("\n📋 TESTING GEHAN MUST-FILL RULE")
        print("-" * 50)
        
        # Test with Gehan span
        gehan_span = EvidenceSpan(
            doc_id="test",
            quote="This study used Gehan's two-stage design.",
            section="Methods",
            char_start=100,
            char_end=200,
            confidence=0.9
        )
        
        design_json = {"arms": ["single_arm"], "n": 25}
        pocket_context = self.get_pocket_context()
        
        method_auditor = MethodAuditor()
        
        method_result = method_auditor.process({
            'evidence_spans': [gehan_span],
            'design_json': design_json,
            'pocket_context': pocket_context
        })
        
        if method_result.success:
            method_card = method_result.output.get('method_card')
            
            print(f"Gehan span: '{gehan_span.quote}'")
            print(f"gehan_two_stage: {method_card.gehan_two_stage}")
            print(f"design_archetype: {method_card.design_archetype}")
            print(f"interim_looks: {method_card.interim_looks}")
            
            # Check must-fill rule
            if method_card.gehan_two_stage and method_card.design_archetype == 'single_arm_phase2_gehan' and method_card.interim_looks == 1:
                print(f"✅ Gehan must-fill rule enforced correctly")
                return True
            else:
                print(f"❌ Gehan must-fill rule not enforced")
                return False
        else:
            print(f"❌ MethodAuditor failed: {method_result.error_message}")
            return False
    
    def run_test(self):
        """Run all tests."""
        print("🧪 METHODCARD DESIGN INCONSISTENCIES BUG TEST")
        print("=" * 80)
        print(f"📄 Paper: {self.paper_id}")
        print(f"📝 Title: {self.title}")
        print("=" * 80)
        
        # Run tests
        tests = [
            ("Gehan Design Detection - Preventing Inconsistencies", self.test_gehan_design_detection),
            ("Primary Endpoint Conflict Validation", self.test_primary_endpoint_conflict_validation),
            ("Gehan Must-Fill Rule", self.test_gehan_must_fill_rule)
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
    test = MethodCardDesignInconsistenciesBugTest()
    success = test.run_test()
    
    if success:
        print("\n🎉 METHODCARD DESIGN INCONSISTENCIES BUG FIXED!")
        print("The MethodCard now properly enforces Gehan design rules and validates endpoint conflicts.")
    else:
        print("\n❌ METHODCARD DESIGN INCONSISTENCIES BUG STILL EXISTS!")
        print("Please review the errors above and implement additional fixes.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
