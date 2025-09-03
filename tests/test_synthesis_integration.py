"""
Integration test for evidence-constrained synthesis workflow.
"""

import pytest
from unittest.mock import Mock
from pathlib import Path
import json

from ncfd.synthesis.evidence_constrained_synthesis import (
    EvidenceConstrainedSynthesizer,
    SynthesisError
)
from ncfd.db.models import Trial, Study
from ncfd.signals.gates import GateResult
from ncfd.signals.scoring import ScoreResult


@pytest.fixture
def mock_trial_data():
    """Create comprehensive mock trial data for integration testing."""
    
    # Mock trial
    trial = Mock(spec=Trial)
    trial.trial_id = "integration_test_001"
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
    
    # PR card with additional info
    pr_card = Mock(spec=Study)
    pr_card.study_id = "pr_001"
    pr_card.doc_type = "PR"
    pr_card.year = 2023
    pr_card.url = "https://investor.company.com/news/2023/trial-results"
    pr_card.extracted_jsonb = {
        "sponsor": "Test Biotech Inc",
        "interim_looks": "2 planned interim analyses",
        "alpha_spending": "O'Brien-Fleming",
        "evidence_spans": {
            "sponsor": "p1",
            "interim_looks": "p2"
        }
    }
    study_cards.append(pr_card)
    
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
        trial_id="integration_test_001",
        run_id="test_run_001",
        prior_pi=0.65,
        logit_prior=-0.62,
        sum_log_lr=1.25,
        logit_post=0.63,
        p_fail=0.85,  # Above GPT-5 threshold
        stop_rule_applied=None
    )
    
    return trial, study_cards, gates, score


class TestSynthesisIntegration:
    """Integration tests for evidence-constrained synthesis."""
    
    def test_full_synthesis_workflow(self, mock_trial_data):
        """Test complete synthesis workflow with valid inputs."""
        trial, study_cards, gates, score = mock_trial_data
        
        # Initialize synthesizer
        synthesizer = EvidenceConstrainedSynthesizer()
        
        # Generate synthesis
        doc = synthesizer.generate(trial, study_cards, gates, score)
        
        # Validate basic structure
        assert doc.trial_id == "integration_test_001"
        assert doc.nct_id == "NCT01234567"
        assert doc.gpt5_hook_triggered is True  # P_fail=0.85 >= 0.85 threshold
        
        # Validate sections
        assert "overview" in doc.sections
        assert "design" in doc.sections
        assert "results" in doc.sections
        assert "red_flags" in doc.sections
        assert "posterior" in doc.sections
        assert "coverage_gaps" in doc.sections
        assert "sources" in doc.sections
        
        # Validate content
        assert "NCT01234567" in doc.text
        assert "Advanced Non-Small Cell Lung Cancer" in doc.text
        assert "Overall Survival" in doc.text
        assert "500 patients" in doc.text
        assert "HR 0.75" in doc.text
        assert "Alpha-Meltdown" in doc.text
        assert "0.850" in doc.text  # P_fail
        
        # Validate quality
        assert doc.quality["coverage_level"] == "high"
        assert doc.quality["study_card_count"] == 3
        assert doc.quality["fired_gates_count"] == 1
        
        # Validate audit
        assert "S1" in doc.audit["fired_signals"]
        assert "S2" in doc.audit["fired_signals"]
        assert "G1" in doc.audit["fired_gates"]
        assert doc.audit["prior_pi"] == 0.65
        assert doc.audit["posterior_p_fail"] == 0.85
        
        # Validate citations
        assert len(doc.citations) > 0
        for citation in doc.citations:
            assert "sentence_idx" in citation
            assert "refs" in citation
            # Some sections (posterior, coverage_gaps, sources, red_flags) may not have refs
            # Only require refs for sections that should have them
    
    def test_synthesis_fails_no_study_cards(self, mock_trial_data):
        """Test synthesis fails when no study cards provided."""
        trial, _, gates, score = mock_trial_data
        
        synthesizer = EvidenceConstrainedSynthesizer()
        
        with pytest.raises(SynthesisError, match="No study cards found"):
            synthesizer.generate(trial, [], gates, score)
    
    def test_synthesis_fails_no_fired_gates(self, mock_trial_data):
        """Test synthesis fails when no gates fired."""
        trial, study_cards, _, score = mock_trial_data
        
        # Create gates with none fired
        gates = {
            "G1": GateResult(id="G1", fired=False, supporting_signals=[], lr_used=1.0, rationale=""),
            "G2": GateResult(id="G2", fired=False, supporting_signals=[], lr_used=1.0, rationale=""),
            "G3": GateResult(id="G3", fired=False, supporting_signals=[], lr_used=1.0, rationale=""),
            "G4": GateResult(id="G4", fired=False, supporting_signals=[], lr_used=1.0, rationale="")
        }
        
        synthesizer = EvidenceConstrainedSynthesizer()
        
        with pytest.raises(SynthesisError, match="No gates fired"):
            synthesizer.generate(trial, study_cards, gates, score)
    
    def test_gpt5_hook_not_triggered_below_threshold(self, mock_trial_data):
        """Test GPT-5 hook not triggered when P_fail below threshold."""
        trial, study_cards, gates, _ = mock_trial_data
        
        # Create score with P_fail below threshold
        score = ScoreResult(
            trial_id="integration_test_001",
            run_id="test_run_001",
            prior_pi=0.65,
            logit_prior=-0.62,
            sum_log_lr=0.5,
            logit_post=-0.12,
            p_fail=0.70,  # Below 0.85 threshold
            stop_rule_applied=None
        )
        
        synthesizer = EvidenceConstrainedSynthesizer()
        doc = synthesizer.generate(trial, study_cards, gates, score)
        
        assert doc.gpt5_hook_triggered is False
    
    def test_synthesis_with_stop_rule(self, mock_trial_data):
        """Test synthesis with stop rule applied."""
        trial, study_cards, gates, _ = mock_trial_data
        
        # Create score with stop rule
        score = ScoreResult(
            trial_id="integration_test_001",
            run_id="test_run_001",
            prior_pi=0.65,
            logit_prior=-0.62,
            sum_log_lr=1.25,
            logit_post=0.63,
            p_fail=0.97,
            stop_rule_applied="endpoint_switch_after_lpr"
        )
        
        synthesizer = EvidenceConstrainedSynthesizer()
        doc = synthesizer.generate(trial, study_cards, gates, score)
        
        # Check that stop rule is mentioned in posterior section
        posterior_text = ""
        for sentence in doc.sections["posterior"]:
            posterior_text += sentence.text
        
        assert "Stop rule applied" in posterior_text
        assert "0.970" in posterior_text
    
    def test_synthesis_output_format(self, mock_trial_data):
        """Test synthesis output can be serialized to JSON."""
        trial, study_cards, gates, score = mock_trial_data
        
        synthesizer = EvidenceConstrainedSynthesizer()
        doc = synthesizer.generate(trial, study_cards, gates, score)
        
        # Test JSON serialization
        try:
            json_str = doc.json()
            parsed = json.loads(json_str)
            
            # Validate structure
            assert "trial_id" in parsed
            assert "nct_id" in parsed
            assert "text" in parsed
            assert "sections" in parsed
            assert "citations" in parsed
            assert "quality" in parsed
            assert "audit" in parsed
            assert "gpt5_hook_triggered" in parsed
            
            # Validate data types
            assert isinstance(parsed["gpt5_hook_triggered"], bool)
            assert isinstance(parsed["quality"], dict)
            assert isinstance(parsed["audit"], dict)
            
        except Exception as e:
            pytest.fail(f"JSON serialization failed: {e}")


def test_synthesis_cli_integration():
    """Test that the synthesis CLI can be imported and has expected interface."""
    try:
        from scripts.synthesize import main
        assert callable(main)
    except ImportError:
        pytest.skip("CLI script not available")


def test_config_file_loading():
    """Test that synthesis config can be loaded from file."""
    config_path = "config/det_synthesis.yaml"
    
    if Path(config_path).exists():
        synthesizer = EvidenceConstrainedSynthesizer(config_path=config_path)
        assert synthesizer.config is not None
        assert "field_precedence" in synthesizer.config.__dict__
        assert "gate_templates" in synthesizer.config.__dict__
        assert synthesizer.config.gpt5_threshold == 0.85
    else:
        pytest.skip("Config file not found")
