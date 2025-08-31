#!/usr/bin/env python3
"""
Test script for the new dual-path pipeline implementing Steps 4 and 5 from the Study Card Overhaul.

This script demonstrates:
1. Step 4: Claimizer v0 - converting spans into atomic, testable Claim objects
2. Step 5: Counter-Evidence Miner - finding contradicting evidence for gate families
3. Late fusion orchestrator with dual-path processing
4. Global validators for provenance, units, and section constraints
"""

import json
import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ncfd.extract.orchestrate import LateFusionOrchestrator
from ncfd.extract.workers.llm.claimizer import Claimizer
from ncfd.extract.workers.llm.counter_evidence_miner import CounterEvidenceMiner
from ncfd.extract.workers.deterministic.gate_validator import GateValidator
from ncfd.extract.workers.deterministic.gate_assessor import GateAssessor
from ncfd.extract.models import (
    EvidenceSpan, MethodCard, ResultsFactsheet, Claim, 
    GateCandidate, GateSpec, GateAssessment
)
from ncfd.extract.validators import validate_all_artifacts

def create_test_spans_for_steps_4_5():
    """Create evidence spans that will test Steps 4 and 5 functionality."""
    
    # Paper metadata
    doc_id = "pmc:PMC2978916"
    
    # Spans that will generate claims for Step 4
    spans = [
        # Design facts (will become design_fact claims)
        EvidenceSpan(
            doc_id=doc_id,
            quote="This was a single-center, open-label, two-stage phase 2 study.",
            section="Methods",
            page=1,
            char_start=0,
            char_end=100,
            confidence=0.9
        ),
        EvidenceSpan(
            doc_id=doc_id,
            quote="The study used a Gehan two-stage design with one interim look after stage 1.",
            section="Methods",
            page=1,
            char_start=100,
            char_end=200,
            confidence=0.9
        ),
        EvidenceSpan(
            doc_id=doc_id,
            quote="Blinding was not performed.",
            section="Methods",
            page=1,
            char_start=200,
            char_end=250,
            confidence=0.9
        ),
        
        # Effect sizes (will become effect_size claims)
        EvidenceSpan(
            doc_id=doc_id,
            quote="Overall response rate was 15.8% (3/19 patients).",
            section="Results",
            page=2,
            char_start=0,
            char_end=100,
            confidence=0.9
        ),
        EvidenceSpan(
            doc_id=doc_id,
            quote="Median time to progression was 14 weeks.",
            section="Results",
            page=2,
            char_start=100,
            char_end=200,
            confidence=0.9
        ),
        EvidenceSpan(
            doc_id=doc_id,
            quote="Overall survival was 13.1 months.",
            section="Results",
            page=2,
            char_start=200,
            char_end=300,
            confidence=0.9
        ),
        
        # Prevalence (will become prevalence claims)
        EvidenceSpan(
            doc_id=doc_id,
            quote="Adverse events included nausea, vomiting, and mucositis.",
            section="Results",
            page=2,
            char_start=300,
            char_end=400,
            confidence=0.9
        ),
        EvidenceSpan(
            doc_id=doc_id,
            quote="Twenty-six patients were treated at the three dose levels.",
            section="Results",
            page=2,
            char_start=400,
            char_end=500,
            confidence=0.9
        ),
        
        # Limitations (will become limitation claims)
        EvidenceSpan(
            doc_id=doc_id,
            quote="Sample size was limited due to the single-arm phase 2 design.",
            section="Methods",
            page=1,
            char_start=500,
            char_end=600,
            confidence=0.9
        ),
        EvidenceSpan(
            doc_id=doc_id,
            quote="This was an exploratory study with post-hoc subgroup analyses.",
            section="Methods",
            page=1,
            char_start=600,
            char_end=700,
            confidence=0.9
        ),
        
        # Contradicting evidence for Step 5
        EvidenceSpan(
            doc_id=doc_id,
            quote="No significant difference in progression-free survival was observed.",
            section="Results",
            page=2,
            char_start=700,
            char_end=800,
            confidence=0.9
        ),
        EvidenceSpan(
            doc_id=doc_id,
            quote="The study failed to meet its primary endpoint of improved response rate.",
            section="Results",
            page=2,
            char_start=800,
            char_end=900,
            confidence=0.9
        ),
        EvidenceSpan(
            doc_id=doc_id,
            quote="Safety concerns limited the maximum tolerated dose.",
            section="Results",
            page=2,
            char_start=900,
            char_end=1000,
            confidence=0.9
        )
    ]
    
    return doc_id, spans

def create_test_gate_candidates():
    """Create test gate candidates for validation and assessment."""
    
    gate_candidates = [
        GateCandidate(
            gate_id="G1_efficacy_signal",
            proposition="Primary efficacy signal demonstrates clinical benefit",
            decision_rule="ORR >= 15% AND median_OS >= 12 months",
            measurables=[
                {
                    "name": "overall_response_rate",
                    "compute": "proportion(positive_response)",
                    "threshold": ">= 0.15",
                    "claim_ids": ["pmc:PMC2978916#claim_0"]
                },
                {
                    "name": "median_overall_survival",
                    "compute": "median(survival_values)",
                    "threshold": ">= 12",
                    "claim_ids": ["pmc:PMC2978916#claim_1"]
                }
            ],
            dependencies=[],
            counter_claims=["pmc:PMC2978916#contradict_G1_signal_0"],
            fda_next="Larger phase 3 study with control arm",
            confidence=0.7,
            notes="Primary efficacy gate for regulatory approval"
        ),
        GateCandidate(
            gate_id="G2_safety_profile",
            proposition="Safety profile is acceptable for continued development",
            decision_rule="Dose_limiting_toxicity < 20% AND no_grade4_events",
            measurables=[
                {
                    "name": "dose_limiting_toxicity_rate",
                    "compute": "proportion(dose_limiting)",
                    "threshold": "< 0.20",
                    "claim_ids": ["pmc:PMC2978916#claim_2"]
                },
                {
                    "name": "grade4_event_count",
                    "compute": "count(grade4_events)",
                    "threshold": "= 0",
                    "claim_ids": ["pmc:PMC2978916#claim_3"]
                }
            ],
            dependencies=[],
            counter_claims=["pmc:PMC2978916#contradict_G2_mechanism_delivery_0"],
            fda_next="Comprehensive safety monitoring in phase 2b",
            confidence=0.8,
            notes="Safety gate for dose escalation"
        )
    ]
    
    return gate_candidates

def test_step_4_claimizer():
    """Test Step 4: Claimizer v0 - converting spans into atomic, testable Claim objects."""
    print("\n🔍 Testing Step 4: Claimizer v0")
    print("=" * 50)
    
    # Create test spans
    doc_id, spans = create_test_spans_for_steps_4_5()
    
    # Initialize Claimizer
    claimizer = Claimizer()
    
    # Process spans
    result = claimizer.process({
        'evidence_spans': spans
    })
    
    if result.success:
        claims = result.output['claims']
        print(f"✅ Successfully generated {len(claims)} claims")
        
        # Display claim details
        for i, claim in enumerate(claims):
            print(f"\nClaim {i+1}:")
            print(f"  Type: {claim.type}")
            print(f"  Proposition: {claim.proposition}")
            print(f"  Stance: {claim.stance}")
            print(f"  Quality Score: {claim.quality_score:.2f}")
            print(f"  Applicability Score: {claim.applicability_score:.2f}")
            print(f"  Span IDs: {len(claim.span_ids)}")
        
        # Validate claims
        print(f"\n🔍 Validating {len(claims)} claims...")
        is_valid, errors = validate_all_artifacts(claims)
        
        if is_valid:
            print("✅ All claims passed validation")
        else:
            print(f"❌ Validation failed with {len(errors)} errors:")
            for error in errors:
                print(f"  - {error}")
        
        return claims
    else:
        print(f"❌ Claimizer failed: {result.error_message}")
        return []

def test_step_5_counter_evidence_miner():
    """Test Step 5: Counter-Evidence Miner - finding contradicting evidence."""
    print("\n🔍 Testing Step 5: Counter-Evidence Miner")
    print("=" * 50)
    
    # Create test spans
    doc_id, spans = create_test_spans_for_steps_4_5()
    
    # Initialize Counter Evidence Miner
    miner = CounterEvidenceMiner()
    
    # Process spans
    result = miner.process({
        'corpus_spans': spans,
        'gate_families': ['G1_signal', 'G2_mechanism_delivery', 'G3_design'],
        'existing_claims': []
    })
    
    if result.success:
        contradicting_claims = result.output['contradicting_claims']
        search_summaries = result.output['search_summaries']
        validation_results = result.output['validation_results']
        
        print(f"✅ Successfully found contradicting evidence for {len(contradicting_claims)} gate families")
        
        # Display results by family
        for family, claims in contradicting_claims.items():
            print(f"\n{family}:")
            print(f"  Found {len(claims)} contradicting claims")
            
            for i, claim in enumerate(claims):
                print(f"    Claim {i+1}: {claim.proposition}")
                print(f"      Quality: {claim.quality_score:.2f}, Applicability: {claim.applicability_score:.2f}")
        
        # Display search summaries
        print(f"\n🔍 Search Summaries:")
        for family, summary in search_summaries.items():
            print(f"  {family}: {summary['contradicting_spans_found']} spans found, {summary['final_contradictors']} final contradictors")
            if summary.get('no_contradictors_found'):
                print(f"    No contradictors found. Search strings tried: {summary.get('search_strings_tried', [])}")
        
        # Display validation results
        print(f"\n✅ Validation Results:")
        for family, validation in validation_results.items():
            status = "✅ SUFFICIENT" if validation['sufficient'] else "❌ INSUFFICIENT"
            print(f"  {family}: {status} - {validation['search_summary']}")
        
        return contradicting_claims
    else:
        print(f"❌ Counter Evidence Miner failed: {result.error_message}")
        return {}

def test_gate_validator():
    """Test the Gate Validator worker."""
    print("\n🔍 Testing Gate Validator")
    print("=" * 50)
    
    # Create test gate candidates
    gate_candidates = create_test_gate_candidates()
    
    # Initialize Gate Validator
    validator = GateValidator()
    
    # Process candidates
    result = validator.process({
        'gate_candidates': gate_candidates,
        'referenced_claims': []  # Empty for this test
    })
    
    if result.success:
        gate_specs = result.output['gate_specs']
        rejected_gates = result.output['rejected_gates']
        
        print(f"✅ Successfully validated {len(gate_specs)} gates")
        print(f"❌ Rejected {len(rejected_gates)} gates")
        
        # Display validation results
        for i, spec in enumerate(gate_specs):
            print(f"\nValidated Gate {i+1}: {spec.gate_id}")
            print(f"  Proposition: {spec.proposition}")
            print(f"  Measurables: {len(spec.measurables)}")
        
        if rejected_gates:
            print(f"\nRejected Gates:")
            for rejection in rejected_gates:
                print(f"  {rejection['candidate'].gate_id}: {rejection['reasons']}")
        
        return gate_specs
    else:
        print(f"❌ Gate Validator failed: {result.error_message}")
        return []

def test_gate_assessor():
    """Test the Gate Assessor worker."""
    print("\n🔍 Testing Gate Assessor")
    print("=" * 50)
    
    # Create test gate specs (simplified for testing)
    gate_specs = [
        GateSpec(
            gate_id="test_gate_1",
            proposition="Test gate for assessment",
            decision_rule="value >= 10",
            measurables=[
                {
                    "name": "test_measurable",
                    "compute": "median(test_values)",
                    "threshold": ">= 10",
                    "claim_ids": ["test_claim_1"]
                }
            ],
            dependencies=[],
            counter_claims=[],
            fda_next="",
            confidence=0.8,
            notes="Test gate"
        )
    ]
    
    # Create test claims
    test_claims = [
        Claim(
            claim_id="test_claim_1",
            doc_id="test:doc1",
            span_ids=["test:doc1#span1"],
            type="effect_size",
            proposition="Test claim with value 15",
            stance="supports",
            value=15.0,
            units="count",
            quality_score=0.9,
            applicability_score=0.8
        )
    ]
    
    # Initialize Gate Assessor
    assessor = GateAssessor()
    
    # Process specs
    result = assessor.process({
        'gate_specs': gate_specs,
        'claims': test_claims
    })
    
    if result.success:
        assessments = result.output['gate_assessments']
        summary = result.output['assessment_summary']
        
        print(f"✅ Successfully assessed {len(assessments)} gates")
        print(f"Summary: {summary}")
        
        # Display assessment details
        for assessment in assessments:
            print(f"\nAssessment for {assessment.gate_id}:")
            print(f"  Status: {assessment.status}")
            print(f"  Rationale: {assessment.rationale}")
        
        return assessments
    else:
        print(f"❌ Gate Assessor failed: {result.error_message}")
        return []

def test_late_fusion_orchestrator():
    """Test the complete Late Fusion Orchestrator."""
    print("\n🔍 Testing Late Fusion Orchestrator")
    print("=" * 50)
    
    # Create test data
    doc_id, spans = create_test_spans_for_steps_4_5()
    
    # Initialize orchestrator
    orchestrator = LateFusionOrchestrator()
    
    # Test pipeline configuration
    print("Pipeline Configuration:")
    config = orchestrator.get_pipeline_status()
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    # Test pipeline processing
    print(f"\nRunning pipeline with {len(spans)} spans...")
    
    result = orchestrator.process_pipeline(
        evidence_spans=spans,
        trial_context={'disease': 'ovarian_cancer'},
        design_json={},
        pocket_context=None
    )
    
    if result['success']:
        print("✅ Pipeline completed successfully")
        print(f"Execution time: {result['execution_time']:.2f}s")
        
        # Display summary
        summary = result.get('summary', {})
        print(f"\nPipeline Summary:")
        print(f"  Total artifacts: {summary.get('total_artifacts', 0)}")
        print(f"  Method cards: {summary.get('method_cards', 0)}")
        print(f"  Results factsheets: {summary.get('results_factsheets', 0)}")
        print(f"  Claims: {summary.get('claims', 0)}")
        
        # Display any warnings
        if result.get('warnings'):
            print(f"\nWarnings:")
            for warning in result['warnings']:
                print(f"  - {warning}")
        
        return result
    else:
        print("❌ Pipeline failed")
        if result.get('errors'):
            print("Errors:")
            for error in result['errors']:
                print(f"  - {error}")
        return result

def test_ablation_flags():
    """Test the ablation flags for backtesting."""
    print("\n🔍 Testing Ablation Flags")
    print("=" * 50)
    
    # Test LLM path only
    print("Testing LLM path only...")
    llm_only_config = {
        'enable_llm_path': True,
        'enable_deterministic_path': False,
        'enable_late_fusion': True
    }
    
    orchestrator_llm_only = LateFusionOrchestrator(llm_only_config)
    config_llm = orchestrator_llm_only.get_pipeline_status()
    print(f"  LLM path enabled: {config_llm['llm_path_enabled']}")
    print(f"  Deterministic path enabled: {config_llm['deterministic_path_enabled']}")
    print(f"  LLM workers: {config_llm['llm_workers']}")
    print(f"  Deterministic workers: {config_llm['deterministic_workers']}")
    
    # Test deterministic path only
    print("\nTesting deterministic path only...")
    deterministic_only_config = {
        'enable_llm_path': False,
        'enable_deterministic_path': True,
        'enable_late_fusion': True
    }
    
    orchestrator_det_only = LateFusionOrchestrator(deterministic_only_config)
    config_det = orchestrator_det_only.get_pipeline_status()
    print(f"  LLM path enabled: {config_det['llm_path_enabled']}")
    print(f"  Deterministic path enabled: {config_det['deterministic_path_enabled']}")
    print(f"  LLM workers: {config_det['llm_workers']}")
    print(f"  Deterministic workers: {config_det['deterministic_workers']}")
    
    # Test late fusion disabled
    print("\nTesting late fusion disabled...")
    no_fusion_config = {
        'enable_llm_path': True,
        'enable_deterministic_path': True,
        'enable_late_fusion': False
    }
    
    orchestrator_no_fusion = LateFusionOrchestrator(no_fusion_config)
    config_no_fusion = orchestrator_no_fusion.get_pipeline_status()
    print(f"  Late fusion enabled: {config_no_fusion['late_fusion_enabled']}")

def main():
    """Run all tests for the dual-path pipeline."""
    print("🚀 Testing Dual-Path Pipeline with Steps 4 and 5")
    print("=" * 80)
    
    # Test individual components
    claims = test_step_4_claimizer()
            contradicting_claims = test_step_5_counter_evidence_miner()
    gate_specs = test_gate_validator()
    assessments = test_gate_assessor()
    
    # Test complete orchestrator
    pipeline_result = test_late_fusion_orchestrator()
    
    # Test ablation flags
    test_ablation_flags()
    
    # Summary
    print("\n" + "=" * 80)
    print("🎉 Dual-Path Pipeline Testing Complete!")
    print(f"   - Claims generated: {len(claims)}")
    print(f"   - Contradicting evidence families: {len(contradicting_claims)}")
    print(f"   - Gates validated: {len(gate_specs)}")
    print(f"   - Gates assessed: {len(assessments)}")
    print(f"   - Pipeline success: {pipeline_result.get('success', False)}")
    
    # Save results to files
    print("\n💾 Saving test results...")
    
    try:
        # Save claims
        with open("test_claims.json", "w") as f:
            json.dump([claim.to_dict() for claim in claims], f, indent=2, default=str)
        print("   - Claims saved to test_claims.json")
    except Exception as e:
        print(f"   - Warning: Could not save claims: {e}")
    
    try:
        # Save pipeline results
        with open("test_pipeline_results.json", "w") as f:
            json.dump(pipeline_result, f, indent=2, default=str)
        print("   - Pipeline results saved to test_pipeline_results.json")
    except Exception as e:
        print(f"   - Warning: Could not save pipeline results: {e}")
    
    print("\n✨ All tests completed! Check the output files for detailed results.")

if __name__ == "__main__":
    main()
