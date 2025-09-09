"""
Test for CA-125 threshold fixes.

This test verifies that:
1. CA-125 "50% reduction" in Methods is captured as methods_detail: assay_threshold, not response_rate
2. The validator correctly identifies missing CA-125 thresholds and can auto-lift them
"""

import pytest
import re
from typing import List, Dict, Any
from src.ncfd.extract.models import EvidenceSpan, MethodCard, Claim
from src.ncfd.extract.workers.llm.claimizer import Claimizer
from src.ncfd.extract.validators.validator_utils import MethodCardValidator


class TestCA125ThresholdFix:
    """Test the CA-125 threshold fixes."""
    
    def test_ca125_threshold_methods_detail_claim(self):
        """Test that CA-125 threshold definitions create methods_detail claims, not response_rate."""
        # Create a test span with CA-125 threshold definition
        span = EvidenceSpan(
            doc_id="test_doc",
            internal_id="test_span_1",
            quote="CA-125 response was defined as a 50% reduction",
            section="Methods",
            char_start=0,
            char_end=50,
            confidence=0.95
        )
        
        # Process with claimizer
        claimizer = Claimizer()
        claims = claimizer._extract_numeric_claims(
            span.quote, span, "methods_detail", "neutral"
        )
        
        # Verify that we get a methods_detail claim for assay_threshold, not response_rate
        ca125_claims = [c for c in claims if 'ca-125' in c.proposition.lower() or 'assay_threshold' in str(c.endpoint).lower()]
        
        assert len(ca125_claims) > 0, "Should create CA-125 threshold claim"
        
        ca125_claim = ca125_claims[0]
        assert ca125_claim.type == "methods_detail", f"Should be methods_detail, got {ca125_claim.type}"
        assert ca125_claim.endpoint == "assay_threshold", f"Should be assay_threshold, got {ca125_claim.endpoint}"
        assert ca125_claim.value == 50.0, f"Should extract 50.0, got {ca125_claim.value}"
        assert ca125_claim.units == "percent", f"Should be percent, got {ca125_claim.units}"
    
    def test_ca125_threshold_no_response_rate_claim(self):
        """Test that CA-125 threshold definitions don't create response_rate claims."""
        # Create a test span with CA-125 threshold definition
        span = EvidenceSpan(
            doc_id="test_doc",
            internal_id="test_span_1",
            quote="CA-125 response was defined as a 50% reduction",
            section="Methods",
            char_start=0,
            char_end=50,
            confidence=0.95
        )
        
        # Process with claimizer
        claimizer = Claimizer()
        claims = claimizer._extract_numeric_claims(
            span.quote, span, "methods_detail", "neutral"
        )
        
        # Verify that we don't get response_rate claims for this pattern
        response_rate_claims = [c for c in claims if c.endpoint == "response_rate"]
        
        assert len(response_rate_claims) == 0, "Should not create response_rate claims for CA-125 threshold definitions"
    
    def test_ca125_threshold_validator_detection(self):
        """Test that the validator correctly detects missing CA-125 thresholds."""
        # Create a MethodCard without CA-125 thresholds
        method_card = MethodCard(
            doc_id="test_doc",
            assay_thresholds=[]  # Empty thresholds
        )
        
        # Create spans with CA-125 threshold definition
        spans = [
            EvidenceSpan(
                doc_id="test_doc",
                internal_id="test_span_1",
                quote="CA-125 response was defined as a 50% reduction",
                section="Methods",
                char_start=0,
                char_end=50,
                confidence=0.95
            )
        ]
        
        # Validate
        is_valid, errors = MethodCardValidator.validate(method_card, spans)
        
        # Should fail validation due to missing CA-125 threshold
        assert not is_valid, "Should fail validation when CA-125 threshold is missing"
        assert any("CA-125 threshold definition found" in error for error in errors), "Should detect missing CA-125 threshold"
    
    def test_ca125_threshold_auto_lift(self):
        """Test that the auto-lift function correctly adds CA-125 thresholds."""
        # Create a MethodCard without CA-125 thresholds
        method_card = MethodCard(
            doc_id="test_doc",
            assay_thresholds=[]  # Empty thresholds
        )
        
        # Create spans with CA-125 threshold definition
        spans = [
            EvidenceSpan(
                doc_id="test_doc",
                internal_id="test_span_1",
                quote="CA-125 response was defined as a 50% reduction",
                section="Methods",
                char_start=0,
                char_end=50,
                confidence=0.95
            )
        ]
        
        # Auto-lift thresholds
        lifted = MethodCardValidator.auto_lift_ca125_thresholds(method_card, spans)
        
        # Should successfully lift
        assert lifted, "Should successfully lift CA-125 thresholds"
        assert len(method_card.assay_thresholds) == 1, "Should add one threshold"
        
        threshold = method_card.assay_thresholds[0]
        assert threshold["assay_type"] == "CA-125", f"Should be CA-125, got {threshold['assay_type']}"
        assert threshold["threshold"] == "50.0", f"Should be 50.0, got {threshold['threshold']}"
        assert threshold["units"] == "percent", f"Should be percent, got {threshold['units']}"
        assert "Auto-lifted from Methods span" in threshold["rationale"], "Should indicate auto-lift"
    
    def test_ca125_threshold_validation_with_existing_threshold(self):
        """Test that validation passes when CA-125 threshold already exists."""
        # Create a MethodCard with CA-125 threshold
        method_card = MethodCard(
            doc_id="test_doc",
            assay_thresholds=[
                {
                    "assay_type": "CA-125",
                    "threshold": "50.0",
                    "units": "percent",
                    "rationale": "Manual entry"
                }
            ]
        )
        
        # Create spans with CA-125 threshold definition
        spans = [
            EvidenceSpan(
                doc_id="test_doc",
                internal_id="test_span_1",
                quote="CA-125 response was defined as a 50% reduction",
                section="Methods",
                char_start=0,
                char_end=50,
                confidence=0.95
            )
        ]
        
        # Validate
        is_valid, errors = MethodCardValidator.validate(method_card, spans)
        
        # Should pass validation since threshold exists
        ca125_errors = [e for e in errors if "CA-125 threshold" in e]
        assert len(ca125_errors) == 0, "Should not have CA-125 threshold errors when threshold exists"
    
    def test_ca125_threshold_auto_lift_no_duplicates(self):
        """Test that auto-lift doesn't create duplicates."""
        # Create a MethodCard with existing CA-125 threshold
        method_card = MethodCard(
            doc_id="test_doc",
            assay_thresholds=[
                {
                    "assay_type": "CA-125",
                    "threshold": "50.0",
                    "units": "percent",
                    "rationale": "Existing entry"
                }
            ]
        )
        
        # Create spans with CA-125 threshold definition
        spans = [
            EvidenceSpan(
                doc_id="test_doc",
                internal_id="test_span_1",
                quote="CA-125 response was defined as a 50% reduction",
                section="Methods",
                char_start=0,
                char_end=50,
                confidence=0.95
            )
        ]
        
        # Auto-lift thresholds
        lifted = MethodCardValidator.auto_lift_ca125_thresholds(method_card, spans)
        
        # Should not lift since threshold already exists
        assert not lifted, "Should not lift when threshold already exists"
        assert len(method_card.assay_thresholds) == 1, "Should not add duplicate threshold"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
