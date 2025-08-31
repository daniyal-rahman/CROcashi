#!/usr/bin/env python3
"""
Simple End-to-End Test for Study Card System

This test runs individual workers and shows their outputs.
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

from ncfd.extract.models import EvidenceSpan, MethodCard, ResultsFactsheet, PocketContextCard
from ncfd.extract.workers.llm.method_auditor import MethodAuditor
from ncfd.extract.workers.llm.results_distiller import ResultsDistiller
from ncfd.extract.workers.llm.claimizer import Claimizer


class PMC2978916SimpleTest:
    """Simple test using PMC2978916 paper."""
    
    def __init__(self):
        self.paper_id = "pmc:PMC2978916"
        self.title = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
        
        # Trial context
        self.trial_context = {
            "disease": "ovarian_cancer",
            "intervention": "atrasentan + PLD",
            "study_phase": "phase_1_2",
            "study_type": "single_arm",
            "primary_endpoint": "feasibility_and_toxicity"
        }
        
        # Design JSON
        self.design_json = {
            "arms": ["PLD + atrasentan"],
            "total_n": 22,
            "primary_endpoint": "feasibility_and_toxicity",
            "study_design": "single_arm_phase2_gehan",
            "gehan_two_stage": True,
            "interim_looks": 1
        }
        
        # Pocket context
        self.pocket_context = PocketContextCard(
            disease="ovarian_cancer",
            intervention_class="targeted_therapy",
            mechanism_of_action="endothelin_receptor_antagonist"
        )
    
    def get_evidence_spans(self):
        """Get evidence spans as EvidenceSpan objects."""
        # Test spans with comprehensive data
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
            # Results - Response rate
            {
                "doc_id": "pmc:PMC2978916",
                "text": "The ORR was 15.8% (95% CI: 3.4-39.6).",
                "section": "Results",
                "char_start": 100,
                "char_end": 200,
                "confidence": 0.95
            },
            # Results - Survival
            {
                "doc_id": "pmc:PMC2978916",
                "text": "Median PFS was 14 weeks and OS was 13.1 months.",
                "section": "Results",
                "char_start": 200,
                "char_end": 300,
                "confidence": 0.90
            },
            # Results - Safety
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
    
    def test_individual_workers(self):
        """Test individual workers."""
        print("🧪 SIMPLE END-TO-END TEST")
        print("=" * 80)
        print(f"📄 Paper: {self.paper_id}")
        print(f"📝 Title: {self.title}")
        
        # Get evidence spans
        evidence_spans = self.get_evidence_spans()
        print(f"📊 Input spans: {len(evidence_spans)}")
        print("=" * 80)
        
        # Test Method Auditor
        print("\n1️⃣ METHOD AUDITOR")
        print("-" * 40)
        method_auditor = MethodAuditor()
        
        methods_spans = [s for s in evidence_spans if s.section.lower() == 'methods']
        print(f"Methods spans: {len(methods_spans)}")
        
        method_result = method_auditor.process({
            'evidence_spans': methods_spans,
            'design_json': self.design_json,
            'pocket_context': self.pocket_context
        })
        
        print(f"✅ Success: {method_result.success}")
        if method_result.success:
            print("📊 Output:")
            print(json.dumps(method_result.output, indent=2, default=str))
        else:
            print(f"❌ Error: {method_result.error_message}")
        
        # Test Results Distiller
        print("\n2️⃣ RESULTS DISTILLER")
        print("-" * 40)
        results_distiller = ResultsDistiller()
        
        results_spans = [s for s in evidence_spans if s.section.lower() == 'results']
        print(f"Results spans: {len(results_spans)}")
        
        results_result = results_distiller.process({
            'evidence_spans': results_spans,
            'trial_context': self.trial_context
        })
        
        print(f"✅ Success: {results_result.success}")
        if results_result.success:
            print("📊 Output:")
            print(json.dumps(results_result.output, indent=2, default=str))
        else:
            print(f"❌ Error: {results_result.error_message}")
        
        # Test Claimizer
        print("\n3️⃣ CLAIMIZER")
        print("-" * 40)
        claimizer = Claimizer()
        
        claim_result = claimizer.process({
            'evidence_spans': evidence_spans,
            'trial_context': self.trial_context
        })
        
        print(f"✅ Success: {claim_result.success}")
        if claim_result.success:
            print("📊 Output:")
            print(json.dumps(claim_result.output, indent=2, default=str))
        else:
            print(f"❌ Error: {claim_result.error_message}")
        
        # Summary
        print(f"\n🎯 TEST SUMMARY:")
        print("=" * 30)
        print(f"  Method Auditor: {'✅ PASS' if method_result.success else '❌ FAIL'}")
        print(f"  Results Distiller: {'✅ PASS' if results_result.success else '❌ FAIL'}")
        print(f"  Claimizer: {'✅ PASS' if claim_result.success else '❌ FAIL'}")
        
        return method_result.success and results_result.success and claim_result.success
    
    def run_test(self):
        """Run the test."""
        return self.test_individual_workers()


def main():
    """Run the test."""
    test = PMC2978916SimpleTest()
    success = test.run_test()
    
    if success:
        print("\n🎉 ALL WORKERS PASSED!")
        print("The Study Card system is working correctly.")
    else:
        print("\n❌ SOME WORKERS FAILED!")
        print("Please review the errors above.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
