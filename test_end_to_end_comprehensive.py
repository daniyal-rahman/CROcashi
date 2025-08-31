#!/usr/bin/env python3
"""
Comprehensive End-to-End Test for Study Card System

This test runs the complete pipeline and shows:
1. Raw output from each agent/worker
2. Final fact card/study card output
3. Detailed execution flow
4. Performance metrics
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
from ncfd.extract.workers.span_triage import SpanTriageWorker as RetrievalTriage
from ncfd.extract.normalization.metric_registry import MetricRegistry as NormalizationRegistry
from ncfd.extract.workers.denominator_resolver import DenominatorResolver
from ncfd.extract.workers.llm.results_distiller import ResultsDistiller
from ncfd.extract.workers.llm.method_auditor import MethodAuditor
from ncfd.extract.workers.llm.claimizer import Claimizer
from ncfd.extract.workers.llm.factsbin_selector import FactsBinSelector
from ncfd.extract.workers.llm.counter_evidence_miner import CounterEvidenceMiner
from ncfd.extract.workers.llm.gate_proposer import GateProposer
from ncfd.extract.workers.deterministic.gate_validator import GateValidator
from ncfd.extract.workers.deterministic.gate_assessor import GateAssessor


class PMC2978916EndToEndTest:
    """End-to-end test using PMC2978916 paper."""
    
    def __init__(self):
        self.paper_id = "pmc:PMC2978916"
        self.title = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
        
        # Test spans with comprehensive data
        self.test_spans = [
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
        
        # Initialize workers
        self.initialize_workers()
    
    def initialize_workers(self):
        """Initialize all workers for testing."""
        print("🔧 Initializing workers...")
        
        self.retrieval_triage = RetrievalTriage()
        self.normalization_registry = NormalizationRegistry()
        self.denominator_resolver = DenominatorResolver()
        self.results_distiller = ResultsDistiller()
        self.method_auditor = MethodAuditor()
        self.claimizer = Claimizer()
        self.factsbin = FactsBinSelector()
        self.counter_evidence_miner = CounterEvidenceMiner()
        self.gate_proposer = GateProposer()
        self.gate_validator = GateValidator()
        self.gate_assessor = GateAssessor()
        
        print("✅ All workers initialized")
    
    def test_individual_workers(self):
        """Test each worker individually and show raw output."""
        print("\n" + "="*80)
        print("🧪 TESTING INDIVIDUAL WORKERS")
        print("="*80)
        
        # 1. Retrieval & Triage
        print("\n1️⃣ RETRIEVAL & TRIAGE")
        print("-" * 40)
        start_time = time.time()
        triage_result = self.retrieval_triage.process({
            "doc_id": self.paper_id,
            "required_fields": ["endpoints", "survival_method", "sample_size"]
        })
        triage_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {triage_time:.2f}s")
        print(f"✅ Success: {triage_result.success}")
        if triage_result.success:
            print("📊 Raw Output:")
            print(json.dumps(triage_result.output, indent=2))
        else:
            print(f"❌ Error: {triage_result.error_message}")
        
        # 2. Normalization Registry
        print("\n2️⃣ NORMALIZATION REGISTRY")
        print("-" * 40)
        start_time = time.time()
        norm_result = self.normalization_registry.process({
            "evidence_spans": self.test_spans,
            "trial_context": self.trial_context
        })
        norm_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {norm_time:.2f}s")
        print(f"✅ Success: {norm_result.success}")
        if norm_result.success:
            print("📊 Raw Output:")
            print(json.dumps(norm_result.output, indent=2))
        else:
            print(f"❌ Error: {norm_result.error_message}")
        
        # 3. Denominator Resolver
        print("\n3️⃣ DENOMINATOR RESOLVER")
        print("-" * 40)
        start_time = time.time()
        denom_result = self.denominator_resolver.process({
            "evidence_spans": self.test_spans,
            "trial_context": self.trial_context
        })
        denom_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {denom_time:.2f}s")
        print(f"✅ Success: {denom_result.success}")
        if denom_result.success:
            print("📊 Raw Output:")
            print(json.dumps(denom_result.output, indent=2))
        else:
            print(f"❌ Error: {denom_result.error_message}")
        
        # 4. Results Distiller
        print("\n4️⃣ RESULTS DISTILLER")
        print("-" * 40)
        start_time = time.time()
        distiller_result = self.results_distiller.process({
            "evidence_spans": self.test_spans,
            "trial_context": self.trial_context
        })
        distiller_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {distiller_time:.2f}s")
        print(f"✅ Success: {distiller_result.success}")
        if distiller_result.success:
            print("📊 Raw Output:")
            print(json.dumps(distiller_result.output, indent=2))
        else:
            print(f"❌ Error: {distiller_result.error_message}")
        
        # 5. Method Auditor
        print("\n5️⃣ METHOD AUDITOR")
        print("-" * 40)
        start_time = time.time()
        auditor_result = self.method_auditor.process({
            "evidence_spans": self.test_spans,
            "design_json": self.design_json,
            "pocket_context": self.pocket_context
        })
        auditor_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {auditor_time:.2f}s")
        print(f"✅ Success: {auditor_result.success}")
        if auditor_result.success:
            print("📊 Raw Output:")
            print(json.dumps(auditor_result.output, indent=2))
        else:
            print(f"❌ Error: {auditor_result.error_message}")
        
        # 6. Claimizer
        print("\n6️⃣ CLAIMIZER")
        print("-" * 40)
        start_time = time.time()
        claimizer_result = self.claimizer.process({
            "evidence_spans": self.test_spans,
            "trial_context": self.trial_context
        })
        claimizer_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {claimizer_time:.2f}s")
        print(f"✅ Success: {claimizer_result.success}")
        if claimizer_result.success:
            print("📊 Raw Output:")
            print(json.dumps(claimizer_result.output, indent=2))
        else:
            print(f"❌ Error: {claimizer_result.error_message}")
        
        # 7. FactsBin
        print("\n7️⃣ FACTSBIN")
        print("-" * 40)
        start_time = time.time()
        factsbin_result = self.factsbin.process({
            "evidence_spans": self.test_spans,
            "claims": claimizer_result.output.get("claims", []) if claimizer_result.success else []
        })
        factsbin_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {factsbin_time:.2f}s")
        print(f"✅ Success: {factsbin_result.success}")
        if factsbin_result.success:
            print("📊 Raw Output:")
            print(json.dumps(factsbin_result.output, indent=2))
        else:
            print(f"❌ Error: {factsbin_result.error_message}")
        
        # 8. Counter-Evidence Miner
        print("\n8️⃣ COUNTER-EVIDENCE MINER")
        print("-" * 40)
        start_time = time.time()
        counter_result = self.counter_evidence_miner.process({
            "evidence_spans": self.test_spans,
            "claims": claimizer_result.output.get("claims", []) if claimizer_result.success else []
        })
        counter_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {counter_time:.2f}s")
        print(f"✅ Success: {counter_result.success}")
        if counter_result.success:
            print("📊 Raw Output:")
            print(json.dumps(counter_result.output, indent=2))
        else:
            print(f"❌ Error: {counter_result.error_message}")
        
        # 9. Gate Proposer
        print("\n9️⃣ GATE PROPOSER")
        print("-" * 40)
        start_time = time.time()
        proposer_result = self.gate_proposer.process({
            "evidence_spans": self.test_spans,
            "claims": claimizer_result.output.get("claims", []) if claimizer_result.success else []
        })
        proposer_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {proposer_time:.2f}s")
        print(f"✅ Success: {proposer_result.success}")
        if proposer_result.success:
            print("📊 Raw Output:")
            print(json.dumps(proposer_result.output, indent=2))
        else:
            print(f"❌ Error: {proposer_result.error_message}")
        
        # 10. Gate Validator
        print("\n🔟 GATE VALIDATOR")
        print("-" * 40)
        start_time = time.time()
        validator_result = self.gate_validator.process({
            "gates": proposer_result.output.get("gates", []) if proposer_result.success else []
        })
        validator_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {validator_time:.2f}s")
        print(f"✅ Success: {validator_result.success}")
        if validator_result.success:
            print("📊 Raw Output:")
            print(json.dumps(validator_result.output, indent=2))
        else:
            print(f"❌ Error: {validator_result.error_message}")
        
        # 11. Gate Assessor
        print("\n1️⃣1️⃣ GATE ASSESSOR")
        print("-" * 40)
        start_time = time.time()
        assessor_result = self.gate_assessor.process({
            "gates": validator_result.output.get("validated_gates", []) if validator_result.success else [],
            "evidence_spans": self.test_spans,
            "claims": claimizer_result.output.get("claims", []) if claimizer_result.success else []
        })
        assessor_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {assessor_time:.2f}s")
        print(f"✅ Success: {assessor_result.success}")
        if assessor_result.success:
            print("📊 Raw Output:")
            print(json.dumps(assessor_result.output, indent=2))
        else:
            print(f"❌ Error: {assessor_result.error_message}")
        
        return {
            "triage": {"result": triage_result, "time": triage_time},
            "normalization": {"result": norm_result, "time": norm_time},
            "denominator": {"result": denom_result, "time": denom_time},
            "distiller": {"result": distiller_result, "time": distiller_time},
            "auditor": {"result": auditor_result, "time": auditor_time},
            "claimizer": {"result": claimizer_result, "time": claimizer_time},
            "factsbin": {"result": factsbin_result, "time": factsbin_time},
            "counter": {"result": counter_result, "time": counter_time},
            "proposer": {"result": proposer_result, "time": proposer_time},
            "validator": {"result": validator_result, "time": validator_time},
            "assessor": {"result": assessor_result, "time": assessor_time}
        }
    
    def test_complete_pipeline(self):
        """Test the complete pipeline using the orchestrator."""
        print("\n" + "="*80)
        print("🚀 TESTING COMPLETE PIPELINE")
        print("="*80)
        
        # Initialize orchestrator
        orchestrator = LateFusionOrchestrator()
        
        print(f"📄 Processing paper: {self.paper_id}")
        print(f"📝 Title: {self.title}")
        print(f"📊 Input spans: {len(self.test_spans)}")
        
        # Run pipeline
        start_time = time.time()
        pipeline_result = orchestrator.process_pipeline(
            evidence_spans=self.test_spans,
            trial_context=self.trial_context,
            design_json=self.design_json,
            pocket_context=self.pocket_context
        )
        total_time = time.time() - start_time
        
        print(f"\n⏱️  Total pipeline execution time: {total_time:.2f}s")
        print(f"✅ Pipeline success: {pipeline_result.success}")
        
        if pipeline_result.success:
            # Show pipeline output
            output = pipeline_result.output
            print("\n📊 PIPELINE OUTPUT:")
            print("=" * 50)
            
            # Artifacts
            artifacts = output.get("artifacts", {})
            print(f"📦 Total artifacts: {len(artifacts)}")
            
            # Method cards
            method_cards = artifacts.get("method_cards", [])
            print(f"📋 Method cards: {len(method_cards)}")
            if method_cards:
                print("📋 METHOD CARD OUTPUT:")
                print(json.dumps(method_cards[0], indent=2))
            
            # Results factsheets
            results_factsheets = artifacts.get("results_factsheets", [])
            print(f"📊 Results factsheets: {len(results_factsheets)}")
            if results_factsheets:
                print("📊 RESULTS FACTSHEET OUTPUT:")
                print(json.dumps(results_factsheets[0], indent=2))
            
            # Claims
            claims = artifacts.get("claims", [])
            print(f"💬 Claims: {len(claims)}")
            if claims:
                print("💬 CLAIMS OUTPUT:")
                print(json.dumps(claims[:3], indent=2))  # Show first 3 claims
            
            # Gates
            gates = artifacts.get("gates", [])
            print(f"🚪 Gates: {len(gates)}")
            if gates:
                print("🚪 GATES OUTPUT:")
                print(json.dumps(gates[:2], indent=2))  # Show first 2 gates
            
            # Execution stats
            stats = output.get("execution_stats", {})
            print(f"\n📈 EXECUTION STATISTICS:")
            print(json.dumps(stats, indent=2))
            
            # Warnings
            warnings = output.get("warnings", [])
            if warnings:
                print(f"\n⚠️  WARNINGS:")
                for warning in warnings:
                    print(f"  - {warning}")
            
            return pipeline_result
        else:
            print(f"❌ Pipeline failed: {pipeline_result.error_message}")
            return pipeline_result
    
    def run_comprehensive_test(self):
        """Run the complete comprehensive test."""
        print("🧪 COMPREHENSIVE END-TO-END TEST")
        print("=" * 80)
        print(f"📄 Paper: {self.paper_id}")
        print(f"📝 Title: {self.title}")
        print(f"📊 Test spans: {len(self.test_spans)}")
        print("=" * 80)
        
        # Test individual workers
        individual_results = self.test_individual_workers()
        
        # Test complete pipeline
        pipeline_result = self.test_complete_pipeline()
        
        # Summary
        print("\n" + "="*80)
        print("🎯 TEST SUMMARY")
        print("="*80)
        
        # Individual worker summary
        print("📊 INDIVIDUAL WORKER RESULTS:")
        total_worker_time = 0
        successful_workers = 0
        
        for worker_name, result_data in individual_results.items():
            result = result_data["result"]
            time_taken = result_data["time"]
            total_worker_time += time_taken
            
            status = "✅ PASS" if result.success else "❌ FAIL"
            print(f"  {worker_name:15} | {status} | {time_taken:6.2f}s")
            
            if result.success:
                successful_workers += 1
        
        print(f"\n📈 WORKER SUMMARY:")
        print(f"  Successful workers: {successful_workers}/{len(individual_results)}")
        print(f"  Total worker time: {total_worker_time:.2f}s")
        print(f"  Average worker time: {total_worker_time/len(individual_results):.2f}s")
        
        # Pipeline summary
        print(f"\n🚀 PIPELINE SUMMARY:")
        if pipeline_result.success:
            print(f"  ✅ Pipeline: PASS")
            output = pipeline_result.output
            artifacts = output.get("artifacts", {})
            print(f"  📦 Artifacts generated: {len(artifacts)}")
            print(f"  📋 Method cards: {len(artifacts.get('method_cards', []))}")
            print(f"  📊 Results factsheets: {len(artifacts.get('results_factsheets', []))}")
            print(f"  💬 Claims: {len(artifacts.get('claims', []))}")
            print(f"  🚪 Gates: {len(artifacts.get('gates', []))}")
        else:
            print(f"  ❌ Pipeline: FAIL")
            print(f"  Error: {pipeline_result.error_message}")
        
        # Save results
        self.save_results(individual_results, pipeline_result)
        
        return pipeline_result.success
    
    def save_results(self, individual_results, pipeline_result):
        """Save test results to files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save individual worker results
        worker_results = {}
        for worker_name, result_data in individual_results.items():
            worker_results[worker_name] = {
                "success": result_data["result"].success,
                "time": result_data["time"],
                "output": result_data["result"].output if result_data["result"].success else None,
                "error": result_data["result"].error_message if not result_data["result"].success else None
            }
        
        with open(f"test_worker_results_{timestamp}.json", "w") as f:
            json.dump(worker_results, f, indent=2, default=str)
        
        # Save pipeline results
        pipeline_output = {
            "success": pipeline_result.success,
            "output": pipeline_result.output if pipeline_result.success else None,
            "error": pipeline_result.error_message if not pipeline_result.success else None,
            "timestamp": timestamp
        }
        
        with open(f"test_pipeline_results_{timestamp}.json", "w") as f:
            json.dump(pipeline_output, f, indent=2, default=str)
        
        print(f"\n💾 Results saved:")
        print(f"  - Worker results: test_worker_results_{timestamp}.json")
        print(f"  - Pipeline results: test_pipeline_results_{timestamp}.json")


def main():
    """Run the comprehensive end-to-end test."""
    test = PMC2978916EndToEndTest()
    success = test.run_comprehensive_test()
    
    if success:
        print("\n🎉 COMPREHENSIVE TEST PASSED!")
        print("All systems are working correctly.")
    else:
        print("\n❌ COMPREHENSIVE TEST FAILED!")
        print("Please review the errors above.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
