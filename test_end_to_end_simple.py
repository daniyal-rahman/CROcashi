#!/usr/bin/env python3
"""
Simplified End-to-End Test for Study Card System

This test runs the complete pipeline using the orchestrator and shows:
1. Final fact card/study card output
2. Raw output from the orchestrator
3. Performance metrics
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

from ncfd.extract.orchestrate.late_fusion_orchestrator import LateFusionOrchestrator
from ncfd.extract.models import EvidenceSpan, MethodCard, ResultsFactsheet


class PMC2978916EndToEndTest:
    """End-to-end test using PMC2978916 paper."""
    
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
        self.pocket_context = {
            "disease_area": "oncology",
            "therapeutic_area": "gynecological_cancer",
            "drug_class": "targeted_therapy",
            "mechanism": "endothelin_receptor_antagonist"
        }
    
    def get_evidence_spans(self):
        """Get evidence spans as EvidenceSpan objects."""
        # Test spans with comprehensive data
        test_spans_data = [
            # Methods - Study design
            {
                "span_id": "pmc:PMC2978916#p1:100-200",
                "doc_id": "pmc:PMC2978916",
                "section": "Methods",
                "page": 1,
                "char_start": 100,
                "char_end": 200,
                "text": "This was a single-arm phase 2 study using Gehan's two-stage design.",
                "confidence": 0.95,
                "content_type": "study_design"
            },
            # Methods - Response assessment
            {
                "span_id": "pmc:PMC2978916#p1:200-300",
                "doc_id": "pmc:PMC2978916",
                "section": "Methods",
                "page": 1,
                "char_start": 200,
                "char_end": 300,
                "text": "Response was assessed every 6 weeks using RECIST v1.1 criteria.",
                "confidence": 0.95,
                "content_type": "response_assessment"
            },
            # Methods - Sample size
            {
                "span_id": "pmc:PMC2978916#p1:300-400",
                "doc_id": "pmc:PMC2978916",
                "section": "Methods",
                "page": 1,
                "char_start": 300,
                "char_end": 400,
                "text": "Twenty-two patients were evaluable for analysis.",
                "confidence": 0.90,
                "content_type": "sample_size"
            },
            # Methods - Statistical plan
            {
                "span_id": "pmc:PMC2978916#p1:400-500",
                "doc_id": "pmc:PMC2978916",
                "section": "Methods",
                "page": 1,
                "char_start": 400,
                "char_end": 500,
                "text": "Statistical analysis was performed using Kaplan-Meier method.",
                "confidence": 0.90,
                "content_type": "statistical_plan"
            },
            # Methods - Treatment dosing
            {
                "span_id": "pmc:PMC2978916#p1:500-600",
                "doc_id": "pmc:PMC2978916",
                "section": "Methods",
                "page": 1,
                "char_start": 500,
                "char_end": 600,
                "text": "Atrasentan was administered at 10mg daily.",
                "confidence": 0.85,
                "content_type": "treatment_dosing"
            },
            # Methods - Site information
            {
                "span_id": "pmc:PMC2978916#p1:600-700",
                "doc_id": "pmc:PMC2978916",
                "section": "Methods",
                "page": 1,
                "char_start": 600,
                "char_end": 700,
                "text": "Patients were enrolled at multiple sites across the United States.",
                "confidence": 0.85,
                "content_type": "site_info"
            },
            # Methods - Blinding status
            {
                "span_id": "pmc:PMC2978916#p1:700-800",
                "doc_id": "pmc:PMC2978916",
                "section": "Methods",
                "page": 1,
                "char_start": 700,
                "char_end": 800,
                "text": "This was an open-label study without blinding.",
                "confidence": 0.90,
                "content_type": "blinding_status"
            },
            # Methods - Endpoints
            {
                "span_id": "pmc:PMC2978916#p1:800-900",
                "doc_id": "pmc:PMC2978916",
                "section": "Methods",
                "page": 1,
                "char_start": 800,
                "char_end": 900,
                "text": "Primary endpoint was feasibility and toxicity assessment.",
                "confidence": 0.95,
                "content_type": "endpoints"
            },
            # Results - Response rate
            {
                "span_id": "pmc:PMC2978916#p2:100-200",
                "doc_id": "pmc:PMC2978916",
                "section": "Results",
                "page": 2,
                "char_start": 100,
                "char_end": 200,
                "text": "The ORR was 15.8% (95% CI: 3.4-39.6).",
                "confidence": 0.95,
                "content_type": "efficacy_results"
            },
            # Results - Survival
            {
                "span_id": "pmc:PMC2978916#p2:200-300",
                "doc_id": "pmc:PMC2978916",
                "section": "Results",
                "page": 2,
                "char_start": 200,
                "char_end": 300,
                "text": "Median PFS was 14 weeks and OS was 13.1 months.",
                "confidence": 0.90,
                "content_type": "survival_results"
            },
            # Results - Safety
            {
                "span_id": "pmc:PMC2978916#p2:300-400",
                "doc_id": "pmc:PMC2978916",
                "section": "Results",
                "page": 2,
                "char_start": 300,
                "char_end": 400,
                "text": "Grade 3+ AEs occurred in 25% of patients.",
                "confidence": 0.85,
                "content_type": "safety_results"
            },
            # Results - Discontinuations
            {
                "span_id": "pmc:PMC2978916#p2:400-500",
                "doc_id": "pmc:PMC2978916",
                "section": "Results",
                "page": 2,
                "char_start": 400,
                "char_end": 500,
                "text": "Treatment discontinuations due to AEs: 12%.",
                "confidence": 0.85,
                "content_type": "safety_results"
            },
            # Results - Response criteria
            {
                "span_id": "pmc:PMC2978916#p2:500-600",
                "doc_id": "pmc:PMC2978916",
                "section": "Results",
                "page": 2,
                "char_start": 500,
                "char_end": 600,
                "text": "Response assessment used RECIST v1.1 criteria.",
                "confidence": 0.90,
                "content_type": "response_criteria"
            },
            # Results - Assessment cadence
            {
                "span_id": "pmc:PMC2978916#p2:600-700",
                "doc_id": "pmc:PMC2978916",
                "section": "Results",
                "page": 2,
                "char_start": 600,
                "char_end": 700,
                "text": "Patients were assessed every 6 weeks for response.",
                "confidence": 0.90,
                "content_type": "assessment_cadence"
            },
            # Results - Numeric results
            {
                "span_id": "pmc:PMC2978916#p2:700-800",
                "doc_id": "pmc:PMC2978916",
                "section": "Results",
                "page": 2,
                "char_start": 700,
                "char_end": 800,
                "text": "The median response duration was 8.5 weeks.",
                "confidence": 0.85,
                "content_type": "numeric_results"
            },
            # Results - Additional safety
            {
                "span_id": "pmc:PMC2978916#p2:800-900",
                "doc_id": "pmc:PMC2978916",
                "section": "Results",
                "page": 2,
                "char_start": 800,
                "char_end": 900,
                "text": "Most common AEs were fatigue and nausea.",
                "confidence": 0.80,
                "content_type": "safety_results"
            },
            # Discussion - Limitations
            {
                "span_id": "pmc:PMC2978916#p3:100-200",
                "doc_id": "pmc:PMC2978916",
                "section": "Discussion",
                "page": 3,
                "char_start": 100,
                "char_end": 200,
                "text": "The study was limited by small sample size and single-arm design.",
                "confidence": 0.80,
                "content_type": "limitations"
            }
        ]
        
        # Convert spans to EvidenceSpan objects
        evidence_spans = []
        for span_data in test_spans_data:
            span = EvidenceSpan(
                doc_id=span_data["doc_id"],
                quote=span_data["text"],
                section=span_data["section"],
                page=None,  # Don't include page to avoid span_id format issues
                char_start=span_data["char_start"],
                char_end=span_data["char_end"],
                confidence=span_data["confidence"]
            )
            evidence_spans.append(span)
        
        return evidence_spans
    
    def test_complete_pipeline(self):
        """Test the complete pipeline using the orchestrator."""
        print("🧪 COMPREHENSIVE END-TO-END TEST")
        print("=" * 80)
        print(f"📄 Paper: {self.paper_id}")
        print(f"📝 Title: {self.title}")
        
        # Get evidence spans
        evidence_spans = self.get_evidence_spans()
        print(f"📊 Input spans: {len(evidence_spans)}")
        print("=" * 80)
        
        # Initialize orchestrator
        print("🔧 Initializing orchestrator...")
        orchestrator = LateFusionOrchestrator()
        
        # Get pipeline status
        config = orchestrator.get_pipeline_status()
        print("📊 Pipeline Configuration:")
        for key, value in config.items():
            print(f"  {key}: {value}")
        
        # Run pipeline
        print(f"\n🚀 Running pipeline with {len(evidence_spans)} spans...")
        start_time = time.time()
        
        pipeline_result = orchestrator.process_pipeline(
            evidence_spans=evidence_spans,
            trial_context=self.trial_context,
            design_json=self.design_json,
            pocket_context=self.pocket_context
        )
        
        total_time = time.time() - start_time
        
        print(f"\n⏱️  Total pipeline execution time: {total_time:.2f}s")
        print(f"✅ Pipeline success: {pipeline_result.get('success', False)}")
        
        if pipeline_result.get('success', False):
            # Show pipeline output
            output = pipeline_result.get("output", {})
            print("\n📊 PIPELINE OUTPUT:")
            print("=" * 50)
            
            # Artifacts
            artifacts = output.get("artifacts", {})
            print(f"📦 Total artifacts: {len(artifacts)}")
            
            # Method cards
            method_cards = artifacts.get("method_cards", [])
            print(f"📋 Method cards: {len(method_cards)}")
            if method_cards:
                print("\n📋 METHOD CARD OUTPUT:")
                print("=" * 30)
                method_card = method_cards[0]
                print(json.dumps(method_card, indent=2, default=str))
            
            # Results factsheets
            results_factsheets = artifacts.get("results_factsheets", [])
            print(f"\n📊 Results factsheets: {len(results_factsheets)}")
            if results_factsheets:
                print("📊 RESULTS FACTSHEET OUTPUT:")
                print("=" * 30)
                results_factsheet = results_factsheets[0]
                print(json.dumps(results_factsheet, indent=2, default=str))
            
            # Claims
            claims = artifacts.get("claims", [])
            print(f"\n💬 Claims: {len(claims)}")
            if claims:
                print("💬 CLAIMS OUTPUT (first 3):")
                print("=" * 30)
                for i, claim in enumerate(claims[:3]):
                    print(f"Claim {i+1}:")
                    print(json.dumps(claim, indent=2, default=str))
                    print()
            
            # Gates
            gates = artifacts.get("gates", [])
            print(f"\n🚪 Gates: {len(gates)}")
            if gates:
                print("🚪 GATES OUTPUT (first 2):")
                print("=" * 30)
                for i, gate in enumerate(gates[:2]):
                    print(f"Gate {i+1}:")
                    print(json.dumps(gate, indent=2, default=str))
                    print()
            
            # Execution stats
            stats = output.get("execution_stats", {})
            print(f"\n📈 EXECUTION STATISTICS:")
            print("=" * 30)
            print(json.dumps(stats, indent=2, default=str))
            
            # Warnings
            warnings = output.get("warnings", [])
            if warnings:
                print(f"\n⚠️  WARNINGS:")
                print("=" * 30)
                for warning in warnings:
                    print(f"  - {warning}")
            
            # Summary
            print(f"\n🎯 PIPELINE SUMMARY:")
            print("=" * 30)
            print(f"  ✅ Pipeline: PASS")
            print(f"  📦 Artifacts generated: {len(artifacts)}")
            print(f"  📋 Method cards: {len(artifacts.get('method_cards', []))}")
            print(f"  📊 Results factsheets: {len(artifacts.get('results_factsheets', []))}")
            print(f"  💬 Claims: {len(artifacts.get('claims', []))}")
            print(f"  🚪 Gates: {len(artifacts.get('gates', []))}")
            print(f"  ⏱️  Total time: {total_time:.2f}s")
            
            # Save results
            self.save_results(pipeline_result, total_time)
            
            return True
        else:
            print(f"❌ Pipeline failed: {pipeline_result.get('error_message', 'Unknown error')}")
            
            # Show error details
            if pipeline_result.get('errors'):
                print("📊 Errors:")
                for error in pipeline_result.get('errors', []):
                    print(f"  - {error}")
            
            if pipeline_result.get('output'):
                print("📊 Error Output:")
                print(json.dumps(pipeline_result.get('output'), indent=2, default=str))
            
            return False
    
    def save_results(self, pipeline_result, total_time):
        """Save test results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save pipeline results
        pipeline_output = {
            "success": pipeline_result.get('success', False),
            "output": pipeline_result.get("output", {}) if pipeline_result.get('success', False) else None,
            "error": pipeline_result.get('error_message', 'Unknown error') if not pipeline_result.get('success', False) else None,
            "execution_time": total_time,
            "timestamp": timestamp,
            "paper_id": self.paper_id,
            "title": self.title,
            "input_spans": 17
        }
        
        with open(f"test_pipeline_results_{timestamp}.json", "w") as f:
            json.dump(pipeline_output, f, indent=2, default=str)
        
        print(f"\n💾 Results saved:")
        print(f"  - Pipeline results: test_pipeline_results_{timestamp}.json")
    
    def run_test(self):
        """Run the end-to-end test."""
        return self.test_complete_pipeline()


def main():
    """Run the end-to-end test."""
    test = PMC2978916EndToEndTest()
    success = test.run_test()
    
    if success:
        print("\n🎉 END-TO-END TEST PASSED!")
        print("The Study Card system is working correctly.")
    else:
        print("\n❌ END-TO-END TEST FAILED!")
        print("Please review the errors above.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
