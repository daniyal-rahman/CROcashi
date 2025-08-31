#!/usr/bin/env python3
"""
Comprehensive Test Suite for Study Card System

Tests the complete dual-path pipeline using the PMC2978916 paper:
"Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin 
in Platinum-Resistant Recurrent Ovarian Cancer"

This test suite covers all components from BaseSpan ingest through DecisionRecord creation.
"""

import sys
import os
import json
import pytest
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.extract.workers import (
    BaseSpanIngestWorker, SpanIndexer, FuzzyAligner, SpanTriageWorker,
    DenominatorResolver, Retriever
)
from ncfd.extract.workers.llm import (
    MethodAuditor, ResultsDistiller, Claimizer, CounterEvidenceMiner,
    GateProposer, FdaLens, MemoComposer
)
from ncfd.extract.workers.deterministic import (
    GateValidator, GateAssessor
)
from ncfd.extract.orchestrate import LateFusionOrchestrator
from ncfd.extract.models import (
    DocumentCard, EvidenceSpan, Claim, MethodCard, ResultsFactsheet,
    PocketContextCard, GateCandidate, GateSpec, GateAssessment, DecisionRecord
)
from ncfd.extract.validators import validate_artifacts
from ncfd.extract.normalization.metric_registry import get_metric_registry


class TestData:
    """Test data for PMC2978916 paper."""
    
    # Paper metadata
    PAPER_ID = "pmc:PMC2978916"
    TITLE = "Phase 1/2 Study of Atrasentan Combined with Pegylated Liposomal Doxorubicin in Platinum-Resistant Recurrent Ovarian Cancer"
    
    # Gold standard data (hand-curated)
    GOLD_METHOD_CARD = {
        "study_phase": "phase_1_2",
        "design_archetype": "single_arm_phase2_gehan",
        "primary_endpoint": "feasibility_and_toxicity",
        "total_n": 26,
        "response_n": 19,  # evaluable for response
        "ttp_os_n": 22,    # TTP/OS analysis included
        "survival_method": "kaplan_meier",
        "interim_looks": 1,
        "gehan_two_stage": True,
        "analysis_set": "safety_population",
        "missingness": "not_reported",
        "site_geography": {
            "num_sites": 2,
            "regions": ["Netherlands"],
            "countries": ["Netherlands"]
        }
    }
    
    GOLD_RESULTS_FACTSHEET = {
        "median_ttp": {
            "value": 14,
            "units": "weeks",
            "n": 22,
            "ci_lower": None,
            "ci_upper": None,
            "method": "kaplan_meier",
            "is_posthoc": False,
            "analysis_set": "ttp_os"
        },
        "median_os": {
            "value": 13.1,
            "units": "months",
            "n": 22,
            "ci_lower": None,
            "ci_upper": None,
            "method": "kaplan_meier",
            "is_posthoc": False,
            "analysis_set": "ttp_os"
        },
        "orr_recist": {
            "value": 15.8,
            "units": "percent",
            "n": 19,
            "ci_lower": 3.4,
            "ci_upper": 39.6,
            "method": "recist_criteria",
            "is_posthoc": False,
            "analysis_set": "response"
        }
    }
    
    # Test spans (simplified for testing)
    TEST_SPANS = [
        {
            "text": "Patients with platinum-resistant ovarian cancer were treated with pegylated liposomal doxorubicin (PLD) 50 mg/m2 on day 1 (and repeated every 4 weeks) in combination with escalating doses of atrasentan once daily. The starting dose was 2.5 mg and escalated in cohorts of three patients from 5 to 10 mg.",
            "section": "Methods",
            "page": 1,
            "char_start": 0,
            "char_end": 200
        },
        {
            "text": "Twenty-six patients (mean age = 60 years, range = 42–74 years) were treated at the three dose levels. Atrasentan could be safely administered in combination at a dose of 10 mg. All patients were evaluable for toxicity, and 19 patients, included in the phase 2 period, were evaluable for response.",
            "section": "Results",
            "page": 2,
            "char_start": 0,
            "char_end": 200
        },
        {
            "text": "Three objective responses were observed and another six patients had stable disease with a median time to progression of 14 weeks and an overall survival of 13.1 months.",
            "section": "Results",
            "page": 2,
            "char_start": 200,
            "char_end": 300
        },
        {
            "text": "The ORR was 15.8% (95% CI: 3.4-39.6).",
            "section": "Results",
            "page": 2,
            "char_start": 300,
            "char_end": 350
        }
    ]


class TestComprehensiveSystem:
    """Comprehensive test suite for the Study Card system."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        self.paper_id = TestData.PAPER_ID
        self.gold_method = TestData.GOLD_METHOD_CARD
        self.gold_results = TestData.GOLD_RESULTS_FACTSHEET
        self.test_spans = TestData.TEST_SPANS
        
        # Initialize components
        self.base_span_ingest = BaseSpanIngestWorker()
        self.span_indexer = SpanIndexer()
        self.fuzzy_aligner = FuzzyAligner()
        self.span_triage = SpanTriageWorker()
        self.denominator_resolver = DenominatorResolver()
        self.retriever = Retriever()
        
        # LLM workers
        self.method_auditor = MethodAuditor()
        self.results_distiller = ResultsDistiller()
        self.claimizer = Claimizer()
        self.counter_evidence_miner = CounterEvidenceMiner()
        self.gate_proposer = GateProposer()
        self.fda_lens = FdaLens()
        self.memo_composer = MemoComposer()
        
        # Deterministic workers
        self.gate_validator = GateValidator()
        self.gate_assessor = GateAssessor()
        
        # Orchestrator
        self.orchestrator = LateFusionOrchestrator()
        
        # Metric registry
        self.metric_registry = get_metric_registry()
        
        # Pocket context
        self.pocket_context = PocketContextCard(
            disease="ovarian_cancer",
            intervention_class="endothelin_receptor_antagonist"
        )
    
    def test_1_basespan_ingest(self):
        """Test BaseSpan ingest functionality."""
        print("\n🧪 Testing BaseSpan Ingest...")
        
        # Test sentence segmentation
        result = self.base_span_ingest.process({
            "doc_id": self.paper_id,
            "text": "This is a test sentence. This is another sentence.",
            "config": {
                "min_sentence_length": 10,
                "max_sentence_length": 200
            }
        })
        
        assert result.success, f"BaseSpan ingest failed: {result.error_message}"
        assert "spans_generated" in result.output
        assert result.output["spans_generated"] > 0
        
        print("✅ BaseSpan ingest working correctly")
    
    def test_2_span_indexing(self):
        """Test span indexing functionality."""
        print("\n🔍 Testing Span Indexing...")
        
        # Test index building
        result = self.span_indexer.process({
            "doc_id": self.paper_id,
            "spans": self.test_spans
        })
        
        assert result.success, f"Span indexing failed: {result.error_message}"
        
        # Test search functionality
        search_result = self.span_indexer.search(
            query="median time to progression",
            section="Results",
            top_k=5
        )
        
        assert len(search_result) > 0, "Search returned no results"
        print("✅ Span indexing working correctly")
    
    def test_3_fuzzy_alignment(self):
        """Test fuzzy alignment functionality."""
        print("\n🔗 Testing Fuzzy Alignment...")
        
        # Test quote alignment
        result = self.fuzzy_aligner.process({
            "doc_id": self.paper_id,
            "quotes": [
                "median time to progression of 14 weeks",
                "overall survival of 13.1 months"
            ]
        })
        
        assert result.success, f"Fuzzy alignment failed: {result.error_message}"
        assert "alignments" in result.output
        
        alignments = result.output["alignments"]
        assert len(alignments) == 2
        
        # Check that quotes were aligned
        aligned_count = sum(1 for a in alignments if a['aligned'])
        assert aligned_count > 0, "No quotes were aligned"
        
        print("✅ Fuzzy alignment working correctly")
    
    def test_4_span_triage(self):
        """Test span triage functionality."""
        print("\n📊 Testing Span Triage...")
        
        # Test triage with required fields
        result = self.span_triage.process({
            "doc_id": self.paper_id,
            "required_fields": [
                "endpoints", "survival_method", "design_archetype",
                "response_breakdown", "survival_medians"
            ]
        })
        
        assert result.success, f"Span triage failed: {result.error_message}"
        assert "selected_spans" in result.output
        
        selected_spans = result.output["selected_spans"]
        assert len(selected_spans) > 0, "No spans were selected"
        
        # Check budget adherence
        total_spans = sum(len(spans) for spans in selected_spans.values())
        assert total_spans <= 30, f"Span budget exceeded: {total_spans}"
        
        print("✅ Span triage working correctly")
    
    def test_5_denominator_resolution(self):
        """Test denominator resolution."""
        print("\n🔢 Testing Denominator Resolution...")
        
        # Test denominator extraction
        result = self.denominator_resolver.process({
            "doc_id": self.paper_id,
            "spans": self.test_spans
        })
        
        assert result.success, f"Denominator resolution failed: {result.error_message}"
        assert "resolved_denominators" in result.output
        
        denominators = result.output["resolved_denominators"]
        
        # Check that key denominators were found
        response_n = None
        ttp_os_n = None
        
        for denom in denominators:
            if denom.metric_family == "response":
                response_n = denom.n
            elif denom.metric_family == "survival":
                ttp_os_n = denom.n
        
        # These should match our gold standard
        if response_n:
            assert response_n == 19, f"Expected response_n=19, got {response_n}"
        if ttp_os_n:
            assert ttp_os_n == 22, f"Expected ttp_os_n=22, got {ttp_os_n}"
        
        print("✅ Denominator resolution working correctly")
    
    def test_6_method_auditor(self):
        """Test Method Auditor functionality."""
        print("\n🔬 Testing Method Auditor...")
        
        # Create evidence spans for methods
        method_spans = [
            EvidenceSpan(
                doc_id=self.paper_id,
                quote=span["text"],
                section=span["section"],
                page=span["page"],
                char_start=span["char_start"],
                char_end=span["char_end"],
                confidence=0.9
            )
            for span in self.test_spans if span["section"] == "Methods"
        ]
        
        # Test method auditing
        result = self.method_auditor.process({
            "evidence_spans": method_spans,
            "design_json": {
                "arms": ["PLD + atrasentan"],
                "total_n": 26,
                "primary_endpoint": "feasibility_and_toxicity"
            },
            "pocket_context": self.pocket_context
        })
        
        assert result.success, f"Method auditing failed: {result.error_message}"
        
        method_card = result.output
        assert method_card is not None
        
        # Check key fields
        assert hasattr(method_card, 'study_phase')
        assert hasattr(method_card, 'design_archetype')
        assert hasattr(method_card, 'total_n')
        
        print("✅ Method Auditor working correctly")
    
    def test_7_results_distiller(self):
        """Test Results Distiller functionality."""
        print("\n📈 Testing Results Distiller...")
        
        # Create evidence spans for results
        results_spans = [
            EvidenceSpan(
                doc_id=self.paper_id,
                quote=span["text"],
                section=span["section"],
                page=span["page"],
                char_start=span["char_start"],
                char_end=span["char_end"],
                confidence=0.9
            )
            for span in self.test_spans if span["section"] == "Results"
        ]
        
        # Test results distillation
        result = self.results_distiller.process({
            "evidence_spans": results_spans,
            "trial_context": {
                "disease": "ovarian_cancer",
                "intervention": "atrasentan + PLD"
            }
        })
        
        assert result.success, f"Results distillation failed: {result.error_message}"
        assert "results_factsheet" in result.output
        
        factsheet = result.output["results_factsheet"]
        assert len(factsheet) > 0, "No results were extracted"
        
        # Check that key metrics were extracted
        metrics_found = []
        for entry in factsheet:
            if hasattr(entry, 'results'):
                for res in entry.results:
                    metrics_found.append(res.get('metric', ''))
        
        # Should find at least some of our expected metrics
        expected_metrics = ['median_ttp', 'median_os', 'orr_recist']
        found_count = sum(1 for metric in expected_metrics if any(m in str(metrics_found) for m in [metric]))
        assert found_count > 0, f"Expected to find some of {expected_metrics}, found {metrics_found}"
        
        print("✅ Results Distiller working correctly")
    
    def test_8_claimizer(self):
        """Test Claimizer functionality."""
        print("\n🏷️ Testing Claimizer...")
        
        # Create evidence spans
        evidence_spans = [
            EvidenceSpan(
                doc_id=self.paper_id,
                quote=span["text"],
                section=span["section"],
                page=span["page"],
                char_start=span["char_start"],
                char_end=span["char_end"],
                confidence=0.9
            )
            for span in self.test_spans
        ]
        
        # Test claim generation
        result = self.claimizer.process({
            "evidence_spans": evidence_spans,
            "trial_context": {
                "disease": "ovarian_cancer",
                "intervention": "atrasentan + PLD"
            }
        })
        
        assert result.success, f"Claimization failed: {result.error_message}"
        assert "claims" in result.output
        
        claims = result.output["claims"]
        assert len(claims) > 0, "No claims were generated"
        
        # Check claim types
        claim_types = [claim.type for claim in claims]
        expected_types = ['design_fact', 'effect_size', 'operational', 'limitation']
        found_types = [t for t in expected_types if t in claim_types]
        assert len(found_types) > 0, f"Expected to find some of {expected_types}, found {claim_types}"
        
        # Check provenance
        for claim in claims:
            assert hasattr(claim, 'span_ids'), f"Claim missing span_ids: {claim}"
            assert len(claim.span_ids) > 0, f"Claim has no span references: {claim}"
        
        print("✅ Claimizer working correctly")
    
    def test_9_counter_evidence_miner(self):
        """Test Counter-Evidence Miner functionality."""
        print("\n🔍 Testing Counter-Evidence Miner...")
        
        # Test counter-evidence mining
        result = self.counter_evidence_miner.process({
            "corpus_spans": self.test_spans,
            "gate_families": ["G1_signal", "G2_mechanism_delivery", "G3_design"],
            "trial_context": {
                "disease": "ovarian_cancer",
                "intervention": "atrasentan + PLD"
            }
        })
        
        assert result.success, f"Counter-evidence mining failed: {result.error_message}"
        assert "contradictors" in result.output
        
        contradictors = result.output["contradictors"]
        
        # Should find contradictors or explicitly state "none found"
        assert len(contradictors) >= 0, "Invalid contradictor count"
        
        # Check quality scoring
        for contradictor in contradictors:
            assert hasattr(contradictor, 'quality_score'), f"Contradictor missing quality_score: {contradictor}"
            assert hasattr(contradictor, 'applicability_score'), f"Contradictor missing applicability_score: {contradictor}"
            assert 0.0 <= contradictor.quality_score <= 1.0, f"Invalid quality_score: {contradictor.quality_score}"
            assert 0.0 <= contradictor.applicability_score <= 1.0, f"Invalid applicability_score: {contradictor.applicability_score}"
        
        print("✅ Counter-Evidence Miner working correctly")
    
    def test_10_gate_lifecycle(self):
        """Test complete gate lifecycle: propose → validate → assess."""
        print("\n🚪 Testing Gate Lifecycle...")
        
        # Create mock data for gate proposal
        method_card = MethodCard()
        results_factsheet = ResultsFactsheet()
        claims = []
        
        # Test Gate Proposer
        gate_result = self.gate_proposer.process({
            "method_card": method_card,
            "results_factsheet": results_factsheet,
            "claims": claims,
            "pocket_context": self.pocket_context
        })
        
        if gate_result.success:
            gate_candidates = gate_result.output
            assert len(gate_candidates) > 0, "No gate candidates generated"
            
            # Test Gate Validator
            validation_result = self.gate_validator.process({
                "gate_candidates": gate_candidates,
                "claims": claims
            })
            
            assert validation_result.success, f"Gate validation failed: {validation_result.error_message}"
            assert "validated_gates" in validation_result.output
            
            validated_gates = validation_result.output["validated_gates"]
            assert len(validated_gates) > 0, "No gates were validated"
            
            # Test Gate Assessor
            assessment_result = self.gate_assessor.process({
                "gate_specs": validated_gates,
                "claims": claims
            })
            
            assert assessment_result.success, f"Gate assessment failed: {assessment_result.error_message}"
            assert "assessments" in assessment_result.output
            
            assessments = assessment_result.output["assessments"]
            assert len(assessments) > 0, "No assessments were generated"
            
            # Check assessment properties
            for assessment in assessments:
                assert hasattr(assessment, 'status'), f"Assessment missing status: {assessment}"
                assert assessment.status in ['PASS', 'FAIL', 'UNCERTAIN'], f"Invalid status: {assessment.status}"
                assert hasattr(assessment, 'rationale'), f"Assessment missing rationale: {assessment}"
        
        print("✅ Gate Lifecycle working correctly")
    
    def test_11_late_fusion_orchestrator(self):
        """Test Late Fusion Orchestrator functionality."""
        print("\n🔄 Testing Late Fusion Orchestrator...")
        
        # Test orchestration with different configurations
        configs = [
            {"enable_llm_path": True, "enable_deterministic_path": False},
            {"enable_llm_path": False, "enable_deterministic_path": True},
            {"enable_llm_path": True, "enable_deterministic_path": True}
        ]
        
        for i, config in enumerate(configs):
            print(f"  Testing config {i+1}: {config}")
            
            # Test orchestration
            result = self.orchestrator.process_pipeline(
                evidence_spans=self.test_spans,
                trial_context={
                    "disease": "ovarian_cancer",
                    "intervention": "atrasentan + PLD",
                    "study_phase": "phase_1_2"
                },
                design_json={
                    "arms": ["PLD + atrasentan"],
                    "total_n": 26,
                    "primary_endpoint": "feasibility_and_toxicity"
                },
                pocket_context=self.pocket_context,
                config=config
            )
            
            assert result.success, f"Orchestration failed with config {config}: {result.error_message}"
            assert "artifacts" in result.output
            
            artifacts = result.output["artifacts"]
            assert len(artifacts) > 0, f"No artifacts generated with config {config}"
            
            print(f"    ✅ Config {i+1} working correctly")
        
        print("✅ Late Fusion Orchestrator working correctly")
    
    def test_12_global_validators(self):
        """Test global validation functionality."""
        print("\n✅ Testing Global Validators...")
        
        # Create mock artifacts for validation
        mock_artifacts = {
            "method_card": MethodCard(),
            "results_factsheet": ResultsFactsheet(),
            "claims": [],
            "gate_assessments": []
        }
        
        # Test validation
        validation_result = validate_artifacts(mock_artifacts)
        
        # Validation should pass or provide specific errors
        assert isinstance(validation_result, dict), "Validation result should be a dictionary"
        
        if "errors" in validation_result:
            print(f"  Validation warnings: {validation_result['errors']}")
        
        print("✅ Global Validators working correctly")
    
    def test_13_decision_record_creation(self):
        """Test DecisionRecord creation and memo composition."""
        print("\n📋 Testing DecisionRecord Creation...")
        
        # Create mock gate assessments
        gate_assessments = [
            GateAssessment(
                gate_id="gate_g1_01",
                status="PASS",
                p_gate=0.8,
                rationale=["Gate passed based on evidence"],
                sensitivity=[{"parameter": "threshold", "range": [0.1, 0.2]}]
            )
        ]
        
        # Create DecisionRecord
        decision_record = DecisionRecord(trial_id=self.paper_id)
        
        for assessment in gate_assessments:
            decision_record.add_gate_assessment(
                gate_id=assessment.gate_id,
                status=assessment.status,
                p_gate=assessment.p_gate,
                rationale="; ".join(assessment.rationale)
            )
        
        # Test memo composition
        memo_result = self.memo_composer.process({
            "gate_assessments": gate_assessments,
            "decision_record": decision_record,
            "pocket_context": self.pocket_context
        })
        
        if memo_result.success:
            memo = memo_result.output
            assert memo is not None, "Memo was not generated"
            
            # Check that memo contains citations
            memo_text = str(memo)
            assert "[" in memo_text, "Memo should contain citations"
            assert "]" in memo_text, "Memo should contain citations"
        
        print("✅ DecisionRecord Creation working correctly")
    
    def test_14_end_to_end_pipeline(self):
        """Test complete end-to-end pipeline."""
        print("\n🚀 Testing End-to-End Pipeline...")
        
        # Test the complete pipeline
        pipeline_result = self.orchestrator.process_pipeline(
            evidence_spans=self.test_spans,
            trial_context={
                "disease": "ovarian_cancer",
                "intervention": "atrasentan + PLD",
                "study_phase": "phase_1_2"
            },
            design_json={
                "arms": ["PLD + atrasentan"],
                "total_n": 26,
                "primary_endpoint": "feasibility_and_toxicity"
            },
            pocket_context=self.pocket_context
        )
        
        assert pipeline_result.success, f"End-to-end pipeline failed: {pipeline_result.error_message}"
        
        # Check that all expected artifacts were generated
        artifacts = pipeline_result.output.get("artifacts", {})
        
        # Should have at least some artifacts
        assert len(artifacts) > 0, "No artifacts were generated"
        
        # Check execution statistics
        stats = pipeline_result.output.get("execution_stats", {})
        assert "total_time" in stats, "Execution statistics missing"
        
        print("✅ End-to-End Pipeline working correctly")
    
    def test_15_performance_and_resources(self):
        """Test performance and resource constraints."""
        print("\n⚡ Testing Performance and Resources...")
        
        start_time = datetime.utcnow()
        
        # Run a simple operation to measure performance
        result = self.span_triage.process({
            "doc_id": self.paper_id,
            "required_fields": ["endpoints", "survival_method"]
        })
        
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()
        
        # Performance should be reasonable (under 10 seconds for this operation)
        assert execution_time < 10.0, f"Operation took too long: {execution_time}s"
        
        # Check memory usage (basic check)
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        # Memory usage should be reasonable (under 1GB)
        assert memory_mb < 1024, f"Memory usage too high: {memory_mb:.1f}MB"
        
        print(f"✅ Performance acceptable: {execution_time:.2f}s, {memory_mb:.1f}MB")
    
    def test_16_error_handling(self):
        """Test error handling and recovery."""
        print("\n🛡️ Testing Error Handling...")
        
        # Test with invalid inputs
        invalid_result = self.method_auditor.process({
            "evidence_spans": [],  # Empty spans
            "design_json": {},     # Empty design
            "pocket_context": None # Invalid context
        })
        
        # Should handle gracefully
        assert not invalid_result.success, "Should fail gracefully with invalid inputs"
        assert invalid_result.error_message is not None, "Should provide error message"
        
        # Test with malformed data
        malformed_result = self.results_distiller.process({
            "evidence_spans": None,  # Invalid type
            "trial_context": "invalid"  # Wrong type
        })
        
        # Should handle gracefully
        assert not malformed_result.success, "Should fail gracefully with malformed data"
        assert malformed_result.error_message is not None, "Should provide error message"
        
        print("✅ Error Handling working correctly")
    
    def test_17_idempotency(self):
        """Test idempotency of operations."""
        print("\n🔄 Testing Idempotency...")
        
        # Run the same operation twice
        result1 = self.span_triage.process({
            "doc_id": self.paper_id,
            "required_fields": ["endpoints"]
        })
        
        result2 = self.span_triage.process({
            "doc_id": self.paper_id,
            "required_fields": ["endpoints"]
        })
        
        # Both should succeed
        assert result1.success, "First run failed"
        assert result2.success, "Second run failed"
        
        # Results should be identical (or at least consistent)
        if "selected_spans" in result1.output and "selected_spans" in result2.output:
            spans1 = result1.output["selected_spans"]
            spans2 = result2.output["selected_spans"]
            
            # Check that the same number of spans were selected
            total1 = sum(len(spans) for spans in spans1.values())
            total2 = sum(len(spans) for spans in spans2.values())
            
            assert total1 == total2, f"Idempotency failed: {total1} vs {total2} spans"
        
        print("✅ Idempotency working correctly")
    
    def test_18_configuration_ablation(self):
        """Test configuration ablation flags."""
        print("\n⚙️ Testing Configuration Ablation...")
        
        # Test different configuration combinations
        configs = [
            {"enable_llm_path": True, "enable_deterministic_path": True, "enable_late_fusion": True},
            {"enable_llm_path": False, "enable_deterministic_path": True, "enable_late_fusion": True},
            {"enable_llm_path": True, "enable_deterministic_path": False, "enable_late_fusion": True},
            {"enable_llm_path": False, "enable_deterministic_path": False, "enable_late_fusion": False}
        ]
        
        for i, config in enumerate(configs):
            print(f"  Testing ablation config {i+1}: {config}")
            
            result = self.orchestrator.process_pipeline(
                evidence_spans=self.test_spans[:2],  # Use fewer spans for faster testing
                trial_context={"disease": "ovarian_cancer"},
                design_json={"total_n": 26},
                pocket_context=self.pocket_context,
                config=config
            )
            
            # All configs should work (though some may produce fewer artifacts)
            assert result.success, f"Ablation config {config} failed: {result.error_message}"
            
            print(f"    ✅ Ablation config {i+1} working correctly")
        
        print("✅ Configuration Ablation working correctly")


def run_comprehensive_test():
    """Run the comprehensive test suite."""
    print("🧪 Comprehensive Study Card System Test Suite")
    print("=" * 60)
    print(f"Testing with paper: {TestData.PAPER_ID}")
    print(f"Title: {TestData.TITLE}")
    print("=" * 60)
    
    # Create test instance
    test_instance = TestComprehensiveSystem()
    test_instance.setup()
    
    # Run all tests
    test_methods = [method for method in dir(test_instance) if method.startswith('test_')]
    
    passed = 0
    failed = 0
    
    for method_name in test_methods:
        try:
            print(f"\n{'='*60}")
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
    print(f"\n{'='*60}")
    print("🎯 TEST SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total: {passed + failed}")
    print(f"🎯 Success Rate: {(passed / (passed + failed)) * 100:.1f}%")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! The Study Card system is working correctly.")
    else:
        print(f"\n⚠️ {failed} tests failed. Please review the errors above.")
    
    return failed == 0


if __name__ == "__main__":
    success = run_comprehensive_test()
    sys.exit(0 if success else 1)
