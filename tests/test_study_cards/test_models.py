"""
Tests for Study Card Models

Basic tests to verify model functionality.
"""

import pytest
from src.ncfd.extract.models import (
    DocumentCard, EvidenceSpan, Claim, MethodCard, ResultsFactsheet,
    PocketContextCard, GateCandidate, GateSpec, GateAssessment, DecisionRecord
)


class TestDocumentCard:
    """Test DocumentCard model."""
    
    def test_create_document_card(self):
        """Test creating a basic DocumentCard."""
        doc = DocumentCard(
            doc_id="pmid:12345",
            doc_type="Paper",
            title="Test Study",
            year=2023
        )
        
        assert doc.doc_id == "pmid:12345"
        assert doc.doc_type == "Paper"
        assert doc.title == "Test Study"
        assert doc.year == 2023
        assert doc.status == "draft"
    
    def test_add_fulltext_ref(self):
        """Test adding fulltext references."""
        doc = DocumentCard(
            doc_id="pmid:12345",
            doc_type="Paper",
            title="Test Study",
            year=2023
        )
        
        doc.add_fulltext_ref(1, 0, 100, "text")
        assert len(doc.fulltext_refs) == 1
        assert doc.fulltext_refs[0]["page"] == 1
        assert doc.fulltext_refs[0]["start_char"] == 0
        assert doc.fulltext_refs[0]["end_char"] == 100


class TestEvidenceSpan:
    """Test EvidenceSpan model."""
    
    def test_create_evidence_span(self):
        """Test creating a basic EvidenceSpan."""
        span = EvidenceSpan(
            span_id="pmid:12345#p1:0-100",
            doc_id="pmid:12345",
            page=1,
            char_start=0,
            char_end=100,
            quote="This is a test quote.",
            section="Methods",
            confidence=0.9
        )
        
        assert span.span_id == "pmid:12345#p1:0-100"
        assert span.doc_id == "pmid:12345"
        assert span.page == 1
        assert span.quote == "This is a test quote."
        assert span.section == "Methods"
        assert span.confidence == 0.9
    
    def test_quote_length_limit(self):
        """Test that quotes are truncated to 400 characters."""
        long_quote = "x" * 500
        span = EvidenceSpan(
            span_id="test#p1:0-100",
            doc_id="test",
            page=1,
            char_start=0,
            char_end=100,
            quote=long_quote,
            section="Methods",
            confidence=0.9
        )
        
        assert len(span.quote) <= 400
        assert span.quote.endswith("...")


class TestClaim:
    """Test Claim model."""
    
    def test_create_claim(self):
        """Test creating a basic Claim."""
        claim = Claim(
            claim_id="claim_001",
            doc_id="pmid:12345",
            span_ids=["span_001"],
            type="effect_size",
            proposition="Treatment improved survival",
            stance="supports"
        )
        
        assert claim.claim_id == "claim_001"
        assert claim.type == "effect_size"
        assert claim.proposition == "Treatment improved survival"
        assert claim.stance == "supports"
        assert claim.quality_score == 0.5
        assert claim.applicability_score == 0.5
    
    def test_claim_validation(self):
        """Test claim validation."""
        # Valid claim
        valid_claim = Claim(
            claim_id="claim_001",
            doc_id="pmid:12345",
            span_ids=["span_001"],
            type="effect_size",
            proposition="Treatment improved survival",
            stance="supports"
        )
        assert valid_claim.validate() is True
        
        # Invalid claim - missing required fields
        invalid_claim = Claim(
            claim_id="",
            doc_id="pmid:12345",
            span_ids=[],
            type="invalid_type",
            proposition="",
            stance="invalid_stance"
        )
        assert invalid_claim.validate() is False


class TestMethodCard:
    """Test MethodCard model."""
    
    def test_create_method_card(self):
        """Test creating a basic MethodCard."""
        method_card = MethodCard()
        
        method_card.primary_endpoint = "Overall Survival"
        method_card.alpha_level = 0.05
        method_card.analysis_set = "ITT"
        
        assert method_card.primary_endpoint == "Overall Survival"
        assert method_card.alpha_level == 0.05
        assert method_card.analysis_set == "ITT"
    
    def test_add_endpoint(self):
        """Test adding endpoints."""
        method_card = MethodCard()
        
        method_card.add_endpoint("Overall Survival", is_primary=True)
        method_card.add_endpoint("Progression-Free Survival", is_primary=False)
        
        assert method_card.primary_endpoint == "Overall Survival"
        assert "Progression-Free Survival" in method_card.secondary_endpoints


class TestResultsFactsheet:
    """Test ResultsFactsheet model."""
    
    def test_create_results_factsheet(self):
        """Test creating a basic ResultsFactsheet."""
        factsheet = ResultsFactsheet()
        
        factsheet.add_result(
            metric="HR",
            value=0.75,
            ci_lower=0.60,
            ci_upper=0.95,
            p_value=0.02,
            analysis_set="ITT",
            span_ids=["span_001"]
        )
        
        assert len(factsheet.results) == 1
        assert factsheet.results[0]["metric"] == "HR"
        assert factsheet.results[0]["value"] == 0.75
        assert factsheet.results[0]["p_value"] == 0.02


class TestGateModels:
    """Test Gate-related models."""
    
    def test_gate_candidate(self):
        """Test GateCandidate model."""
        candidate = GateCandidate(
            gate_id="gate_001",
            proposition="Efficacy threshold met",
            decision_rule="HR < 0.8 with p < 0.05"
        )
        
        candidate.add_measurable("hr_value", "extract_hr", "< 0.8", ["claim_001"])
        candidate.add_measurable("p_value", "extract_p", "< 0.05", ["claim_002"])
        
        assert candidate.gate_id == "gate_001"
        assert len(candidate.measurables) == 2
        assert candidate.has_numeric_thresholds is True
    
    def test_gate_spec(self):
        """Test GateSpec model."""
        spec = GateSpec(
            gate_id="gate_001",
            proposition="Efficacy threshold met",
            decision_rule="HR < 0.8 with p < 0.05"
        )
        
        spec.add_measurable("hr_value", "extract_hr", "< 0.8", ["claim_001"])
        spec.mark_as_validated()
        
        assert spec.is_validated is True
        assert spec.validation_status == "validated"
    
    def test_gate_assessment(self):
        """Test GateAssessment model."""
        assessment = GateAssessment(
            gate_id="gate_001",
            status="PASS"
        )
        
        assessment.add_rationale("HR of 0.75 meets threshold of < 0.8")
        assessment.add_computed_value("hr_value", 0.75, None, "Extracted HR value")
        
        assert assessment.status == "PASS"
        assert len(assessment.rationale) == 1
        assert "hr_value" in assessment.computed_values


class TestDecisionRecord:
    """Test DecisionRecord model."""
    
    def test_create_decision_record(self):
        """Test creating a basic DecisionRecord."""
        record = DecisionRecord(trial_id="NCT12345")
        
        record.add_gate_assessment("gate_001", "PASS", 0.8, "Gate passed")
        record.add_gate_assessment("gate_002", "FAIL", 0.3, "Gate failed")
        
        assert record.trial_id == "NCT12345"
        assert len(record.gates) == 2
        assert record.decision == "REJECT"  # Should be REJECT since one gate failed
    
    def test_calculate_overall_success(self):
        """Test overall success probability calculation."""
        record = DecisionRecord(trial_id="NCT12345")
        record.combination_rule = "AND"
        
        record.add_gate_assessment("gate_001", "PASS", 0.8)
        record.add_gate_assessment("gate_002", "PASS", 0.9)
        
        overall_success = record.calculate_overall_success()
        assert overall_success == 0.8  # Should be min(0.8, 0.9) for AND rule


class TestPocketContextCard:
    """Test PocketContextCard model."""
    
    def test_create_pocket_context(self):
        """Test creating a basic PocketContextCard."""
        context = PocketContextCard(
            disease="Heart Failure",
            intervention_class="Gene Therapy"
        )
        
        context.add_regulator_preference("Focus on safety endpoints")
        context.add_class_quirk("No redose for AAV")
        
        assert context.disease == "Heart Failure"
        assert context.intervention_class == "Gene Therapy"
        assert len(context.regulator_preferences) == 1
        assert len(context.class_quirks) == 1
    
    def test_high_risk_intervention(self):
        """Test high-risk intervention detection."""
        context = PocketContextCard(
            disease="Cancer",
            intervention_class="Gene Therapy"
        )
        
        assert context.is_high_risk_intervention() is True
        assert context.requires_special_monitoring() is True
