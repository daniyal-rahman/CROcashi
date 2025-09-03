"""
Tests for deterministic synthesis module.
"""

import pytest
from unittest.mock import Mock, patch
from pydantic import ValidationError

from ncfd.synthesis.evidence_constrained_synthesis import (
    DeterministicSynthesizer, 
    SynthesisError, 
    SynthesisDoc,
    Ref,
    Sentence,
    GPT5ThinkingHook
)
from ncfd.db.models import Trial, Study
from ncfd.signals.gates import GateResult
from ncfd.signals.scoring import ScoreResult


@pytest.fixture
def mock_trial():
    """Create a mock trial."""
    trial = Mock(spec=Trial)
    trial.trial_id = "test_trial_001"
    trial.nct_id = "NCT01234567"
    trial.phase = "3"
    trial.indication = "Advanced Non-Small Cell Lung Cancer"
    return trial


@pytest.fixture
def mock_study_cards():
    """Create mock study cards."""
    cards = []
    
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
        "evidence_spans": {
            "primary_endpoint": "p2",
            "n_total": "p3"
        }
    }
    cards.append(registry_card)
    
    # Paper card
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
    cards.append(paper_card)
    
    return cards


@pytest.fixture
def mock_gates():
    """Create mock gates with fired G1."""
    gates = {
        "G1": GateResult(
            id="G1",
            fired=True,
            supporting_signals=["S1", "S2"],
            lr_used=3.5,
            rationale="Endpoint changed and underpowered"
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
    return gates


@pytest.fixture
def mock_score():
    """Create mock score."""
    return ScoreResult(
        trial_id="test_trial_001",
        run_id="test_run_001",
        prior_pi=0.65,
        logit_prior=-0.62,
        sum_log_lr=1.25,
        logit_post=0.63,
        p_fail=0.85,
        stop_rule_applied=None
    )


@pytest.fixture
def synthesizer():
    """Create synthesizer instance."""
    return DeterministicSynthesizer()


class TestDeterministicSynthesizer:
    """Test the deterministic synthesizer."""
    
    def test_load_default_config(self, synthesizer):
        """Test loading default configuration."""
        assert synthesizer.config is not None
        assert "primary_endpoint" in synthesizer.config.field_precedence
        assert "G1" in synthesizer.config.gate_templates
        assert synthesizer.config.gpt5_threshold == 0.85
    
    def test_validate_early_stopping_no_study_cards(self, synthesizer, mock_trial, mock_gates, mock_score):
        """Test validation fails with no study cards."""
        with pytest.raises(SynthesisError, match="No study cards found"):
            synthesizer._validate_early_stopping_requirements([], mock_gates, mock_score)
    
    def test_validate_early_stopping_no_fired_gates(self, synthesizer, mock_trial, mock_study_cards, mock_score):
        """Test validation fails with no fired gates."""
        gates = {
            "G1": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text=""),
            "G2": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text=""),
            "G3": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text=""),
            "G4": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text="")
        }
        
        with pytest.raises(SynthesisError, match="No gates fired"):
            synthesizer._validate_early_stopping_requirements(mock_study_cards, gates, mock_score)
    
    def test_resolve_field_with_precedence(self, synthesizer, mock_study_cards):
        """Test field resolution with precedence."""
        val, study_id, span = synthesizer._resolve_field_with_precedence(
            mock_study_cards, "primary_endpoint", ["Registry", "Paper", "PR", "Abstract"]
        )
        
        assert val == "Overall Survival"
        assert study_id == "registry_001"
        assert span == "p2"
    
    def test_resolve_field_not_found(self, synthesizer, mock_study_cards):
        """Test field resolution when field not found."""
        val, study_id, span = synthesizer._resolve_field_with_precedence(
            mock_study_cards, "nonexistent_field", ["Registry", "Paper", "PR", "Abstract"]
        )
        
        assert val is None
        assert study_id is None
        assert span is None
    
    def test_build_overview_section(self, synthesizer, mock_trial, mock_study_cards):
        """Test overview section building."""
        sentences = synthesizer._build_overview_section(mock_trial, mock_study_cards)
        
        assert len(sentences) == 1
        assert "NCT01234567" in sentences[0].text
        assert "Advanced Non-Small Cell Lung Cancer" in sentences[0].text
        assert len(sentences[0].refs) >= 1
    
    def test_build_design_section(self, synthesizer, mock_study_cards):
        """Test design section building."""
        sentences = synthesizer._build_design_section(mock_study_cards)
        
        assert len(sentences) >= 1
        # Should have primary endpoint and sample size
        endpoint_found = any("Overall Survival" in s.text for s in sentences)
        n_found = any("500 patients" in s.text for s in sentences)
        assert endpoint_found or n_found
    
    def test_build_results_section(self, synthesizer, mock_study_cards):
        """Test results section building."""
        sentences = synthesizer._build_results_section(mock_study_cards)
        
        assert len(sentences) == 1
        assert "HR 0.75" in sentences[0].text
        assert "p-value 0.003" in sentences[0].text
        assert len(sentences[0].refs) >= 1
    
    def test_build_red_flags_section_with_fired_gates(self, synthesizer, mock_gates, mock_study_cards):
        """Test red flags section with fired gates."""
        sentences = synthesizer._build_red_flags_section(mock_gates, mock_study_cards)
        
        assert len(sentences) == 1
        assert "Alpha-Meltdown" in sentences[0].text
    
    def test_build_red_flags_section_no_fired_gates(self, synthesizer, mock_study_cards):
        """Test red flags section with no fired gates."""
        gates = {
            "G1": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text=""),
            "G2": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text=""),
            "G3": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text=""),
            "G4": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text="")
        }
        
        sentences = synthesizer._build_red_flags_section(gates, mock_study_cards)
        
        assert len(sentences) == 1
        assert "No co-dependent gates fired" in sentences[0].text
    
    def test_build_posterior_section(self, synthesizer, mock_score):
        """Test posterior section building."""
        sentences = synthesizer._build_posterior_section(mock_score)
        
        assert len(sentences) == 1
        assert "0.850" in sentences[0].text
        assert "0.650" in sentences[0].text
    
    def test_build_posterior_section_with_stop_override(self, synthesizer):
        """Test posterior section with stop override."""
        score = ScoreResult(
            prior_pi=0.65,
            logit_prior=-0.62,
            sum_log_lr=1.25,
            logit_post=0.63,
            p_fail=0.97,
            stop_override=0.97
        )
        
        sentences = synthesizer._build_posterior_section(score)
        
        assert len(sentences) == 1
        assert "Stop rule applied" in sentences[0].text
        assert "0.970" in sentences[0].text
    
    def test_should_trigger_gpt5_hook_above_threshold(self, synthesizer):
        """Test GPT-5 hook triggering above threshold."""
        score = ScoreResult(
            prior_pi=0.65,
            logit_prior=-0.62,
            sum_log_lr=1.25,
            logit_post=0.63,
            p_fail=0.90,  # Above 0.85 threshold
            stop_override=None
        )
        
        assert synthesizer._should_trigger_gpt5_hook(score) is True
    
    def test_should_trigger_gpt5_hook_below_threshold(self, synthesizer):
        """Test GPT-5 hook not triggering below threshold."""
        score = ScoreResult(
            prior_pi=0.65,
            logit_prior=-0.62,
            sum_log_lr=1.25,
            logit_post=0.63,
            p_fail=0.80,  # Below 0.85 threshold
            stop_override=None
        )
        
        assert synthesizer._should_trigger_gpt5_hook(score) is False
    
    def test_generate_success(self, synthesizer, mock_trial, mock_study_cards, mock_gates, mock_score):
        """Test successful synthesis generation."""
        doc = synthesizer.generate(mock_trial, mock_study_cards, mock_gates, mock_score)
        
        assert isinstance(doc, SynthesisDoc)
        assert doc.trial_id == "test_trial_001"
        assert doc.nct_id == "NCT01234567"
        assert doc.gpt5_hook_triggered is True  # P_fail=0.85 >= 0.85 threshold
        assert "overview" in doc.sections
        assert "design" in doc.sections
        assert "results" in doc.sections
        assert "red_flags" in doc.sections
        assert "posterior" in doc.sections
        assert "coverage_gaps" in doc.sections
        assert "sources" in doc.sections
    
    def test_generate_fails_no_study_cards(self, synthesizer, mock_trial, mock_gates, mock_score):
        """Test generation fails with no study cards."""
        with pytest.raises(SynthesisError, match="No study cards found"):
            synthesizer.generate(mock_trial, [], mock_gates, mock_score)
    
    def test_generate_fails_no_fired_gates(self, synthesizer, mock_trial, mock_study_cards, mock_score):
        """Test generation fails with no fired gates."""
        gates = {
            "G1": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text=""),
            "G2": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text=""),
            "G3": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text=""),
            "G4": GateResult(fired=False, supporting_s_ids=[], lr_used=1.0, rationale_text="")
        }
        
        with pytest.raises(SynthesisError, match="No gates fired"):
            synthesizer.generate(mock_trial, mock_study_cards, gates, mock_score)


class TestGPT5ThinkingHook:
    """Test the GPT-5 thinking hook."""
    
    def test_trigger_thinking_analysis(self):
        """Test GPT-5 thinking analysis trigger."""
        hook = GPT5ThinkingHook()
        
        result = hook.trigger_thinking_analysis(
            trial_id="test_trial_001",
            nct_id="NCT01234567",
            indication="Advanced Non-Small Cell Lung Cancer",
            p_fail=0.90
        )
        
        assert isinstance(result, dict)
        assert result["trial_id"] == "test_trial_001"
        assert result["nct_id"] == "NCT01234567"
        assert result["gpt5_p_fail"] is None  # Not implemented yet


class TestSynthesisDoc:
    """Test the synthesis document model."""
    
    def test_synthesis_doc_creation(self):
        """Test creating a synthesis document."""
        doc = SynthesisDoc(
            trial_id="test_trial_001",
            nct_id="NCT01234567",
            text="Test synthesis text",
            sections={},
            citations=[],
            quality={},
            audit={},
            gpt5_hook_triggered=False
        )
        
        assert doc.trial_id == "test_trial_001"
        assert doc.nct_id == "NCT01234567"
        assert doc.gpt5_hook_triggered is False
    
    def test_synthesis_doc_with_gpt5_triggered(self):
        """Test synthesis document with GPT-5 triggered."""
        doc = SynthesisDoc(
            trial_id="test_trial_001",
            nct_id="NCT01234567",
            text="Test synthesis text",
            sections={},
            citations=[],
            quality={},
            audit={},
            gpt5_hook_triggered=True
        )
        
        assert doc.gpt5_hook_triggered is True


class TestRef:
    """Test the reference model."""
    
    def test_ref_creation(self):
        """Test creating a reference."""
        ref = Ref(
            study_id="study_001",
            field_path="primary_endpoint",
            span="p2"
        )
        
        assert ref.study_id == "study_001"
        assert ref.field_path == "primary_endpoint"
        assert ref.span == "p2"
    
    def test_ref_without_span(self):
        """Test creating a reference without span."""
        ref = Ref(
            study_id="study_001",
            field_path="primary_endpoint"
        )
        
        assert ref.span is None


class TestSentence:
    """Test the sentence model."""
    
    def test_sentence_creation(self):
        """Test creating a sentence."""
        ref = Ref(study_id="study_001", field_path="primary_endpoint", span="p2")
        sentence = Sentence(
            text="Primary endpoint: Overall Survival",
            refs=[ref]
        )
        
        assert sentence.text == "Primary endpoint: Overall Survival"
        assert len(sentence.refs) == 1
        assert sentence.refs[0].study_id == "study_001"
