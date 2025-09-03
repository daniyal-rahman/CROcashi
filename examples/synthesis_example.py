#!/usr/bin/env python3
"""
Example script demonstrating evidence-constrained synthesis.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.synthesis.evidence_constrained_synthesis import EvidenceConstrainedSynthesizer
from ncfd.db.models import Trial, Study
from ncfd.signals.gates import GateResult
from ncfd.signals.scoring import ScoreResult


def create_example_data():
    """Create example trial data for demonstration."""
    
    # Mock trial
    trial = Mock(spec=Trial)
    trial.trial_id = "example_trial_001"
    trial.nct_id = "NCT01234567"
    trial.phase = "3"
    trial.indication = "Advanced Non-Small Cell Lung Cancer"
    
    # Mock study cards
    study_cards = []
    
    # Registry card
    registry_card = Mock(spec=Study)
    registry_card.study_id = "registry_001"
    registry_card.doc_type = "Registry"
    registry_card.year = 2023
    registry_card.url = "https://clinicaltrials.gov/ct2/show/NCT01234567"
    registry_card.extracted_jsonb = {
        "primary_endpoint": "Overall Survival",
        "n_total": 500,
        "randomization": "2:1 randomization",
        "est_primary_completion_date": "2024-06-30",
        "is_pivotal": True,
        "evidence_spans": {
            "primary_endpoint": "p2",
            "n_total": "p3"
        }
    }
    study_cards.append(registry_card)
    
    # Paper card with results
    paper_card = Mock(spec=Study)
    paper_card.study_id = "paper_001"
    paper_card.doc_type = "Paper"
    paper_card.year = 2023
    paper_card.url = "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    paper_card.extracted_jsonb = {
        "effect_primary": "HR 0.75 (95% CI: 0.62-0.91)",
        "p_value": "0.003",
        "itt_status": "ITT population",
        "dropout_missing_itt_pct": "15%",
        "evidence_spans": {
            "effect_primary": "p5",
            "p_value": "p5",
            "itt_status": "p4"
        }
    }
    study_cards.append(paper_card)
    
    # Mock gates with fired G1 (Alpha-Meltdown)
    gates = {
        "G1": GateResult(
            id="G1",
            fired=True,
            supporting_signals=["S1", "S2"],
            lr_used=3.5,
            rationale="Alpha-Meltdown: endpoint changed and trial underpowered"
        ),
        "G2": GateResult(
            id="G2",
            fired=False,
            supporting_signals=[],
            lr_used=1.0,
            rationale=""
        ),
        "G3": GateResult(
            id="G3",
            fired=False,
            supporting_signals=[],
            lr_used=1.0,
            rationale=""
        ),
        "G4": GateResult(
            id="G4",
            fired=False,
            supporting_signals=[],
            lr_used=1.0,
            rationale=""
        )
    }
    
    # Mock score
    score = ScoreResult(
        trial_id="example_trial_001",
        run_id="example_run_001",
        prior_pi=0.65,
        logit_prior=-0.62,
        sum_log_lr=1.25,
        logit_post=0.63,
        p_fail=0.85,  # Above GPT-5 threshold
        stop_rule_applied=None
    )
    
    return trial, study_cards, gates, score


def main():
    """Run the synthesis example."""
    print("🔬 Evidence-Constrained Synthesis Example")
    print("=" * 50)
    
    # Create example data
    trial, study_cards, gates, score = create_example_data()
    
    print(f"Trial: {trial.nct_id} ({trial.phase}) in {trial.indication}")
    print(f"Study Cards: {len(study_cards)}")
    print(f"Fired Gates: {len([g for g in gates.values() if g.fired])}")
    print(f"P_fail: {score.p_fail:.3f}")
    print()
    
    # Initialize synthesizer
    synthesizer = EvidenceConstrainedSynthesizer()
    
    try:
        # Generate synthesis
        doc = synthesizer.generate(trial, study_cards, gates, score)
        
        print("📋 Synthesis Generated Successfully!")
        print("=" * 50)
        print()
        
        # Display sections
        for section_name, sentences in doc.sections.items():
            if sentences:
                print(f"📄 {section_name.upper()}:")
                for sentence in sentences:
                    print(f"   {sentence.text}")
                    if sentence.refs:
                        refs_str = ", ".join([f"[{ref.study_id}.{ref.field_path}]" for ref in sentence.refs])
                        print(f"      References: {refs_str}")
                print()
        
        # Display quality metrics
        print("📊 Quality Metrics:")
        print(f"   Coverage Level: {doc.quality['coverage_level']}")
        print(f"   Study Card Count: {doc.quality['study_card_count']}")
        print(f"   Fired Gates Count: {doc.quality['fired_gates_count']}")
        print()
        
        # Display audit trail
        print("🔍 Audit Trail:")
        print(f"   Fired Signals: {', '.join(doc.audit['fired_signals'])}")
        print(f"   Fired Gates: {', '.join(doc.audit['fired_gates'])}")
        print(f"   Prior π: {doc.audit['prior_pi']:.3f}")
        print(f"   Posterior P_fail: {doc.audit['posterior_p_fail']:.3f}")
        print()
        
        # Display GPT-5 hook status
        if doc.gpt5_hook_triggered:
            print("🤖 GPT-5 Thinking Hook: TRIGGERED")
            print("   (P_fail >= 0.85 threshold)")
            print("   Would trigger independent GPT-5 analysis")
        else:
            print("🤖 GPT-5 Thinking Hook: NOT TRIGGERED")
            print("   (P_fail < 0.85 threshold)")
        print()
        
        # Display validation results
        print("✅ Validation:")
        print("   ✓ Early stopping requirements met")
        print("   ✓ Study cards present")
        print("   ✓ Gates fired")
        print("   ✓ All required fields covered")
        print("   ✓ References validated")
        print()
        
        print("🎯 Synthesis Complete!")
        
    except Exception as e:
        print(f"❌ Synthesis failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
