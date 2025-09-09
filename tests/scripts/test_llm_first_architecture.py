"""
Test LLM-first, provenance-second architecture.

Tests the new architecture using PMC2978916 as an example.
"""

import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any, List

from src.ncfd.extract.models.llm_extraction_draft import (
    LLMResultsDraft, LLMMethodDraft, LLMClaimDraft, 
    EvidenceKind, EvidenceStatus
)
from src.ncfd.extract.models import EvidenceSpan, ResultsFactsheet
from src.ncfd.extract.workers.llm.llm_results_drafter import LLMResultsDrafter
from src.ncfd.extract.workers.provenance_backtracer import ProvenanceBacktracer
from src.ncfd.extract.workers.results_finalizer import ResultsFinalizer


class TestLLMFirstArchitecture:
    """Test the LLM-first, provenance-second architecture."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.doc_id = "PMC2978916"
        self.raw_doc_text = """
        Results
        
        Overall response rate was 15.8% (3/19 patients) according to RECIST criteria.
        CA-125 response rate was 21.1% (4/19 patients).
        Median time to progression was 14 weeks.
        Median overall survival was 13.1 months.
        
        Methods
        
        Response was assessed every two cycles using RECIST criteria.
        Using a Gehan two-stage design with one interim analysis.
        Kaplan-Meier method was used for survival analysis.
        """
        
        self.evidence_spans = [
            EvidenceSpan(
                span_id=f"{self.doc_id}#sec:Results:char100-200",
                doc_id=self.doc_id,
                section="Results",
                quote="Overall response rate was 15.8% (3/19 patients)",
                char_start=100,
                char_end=200
            ),
            EvidenceSpan(
                span_id=f"{self.doc_id}#sec:Methods:char300-400",
                doc_id=self.doc_id,
                section="Methods",
                quote="Response was assessed every two cycles using RECIST criteria",
                char_start=300,
                char_end=400
            )
        ]

    def test_llm_results_drafter(self):
        """Test LLM Results Drafter extracts results with verbatim quotes."""
        drafter = LLMResultsDrafter()
        
        result = drafter.process({
            'raw_doc_text': self.raw_doc_text,
            'doc_id': self.doc_id,
            'trial_context': {}
        })
        
        assert result.success
        assert 'results_draft' in result.output
        
        results_draft = result.output['results_draft']
        assert isinstance(results_draft, LLMResultsDraft)
        assert results_draft.doc_id == self.doc_id
        assert len(results_draft.results) > 0
        
        # Check that results have verbatim quotes
        for i, result in enumerate(results_draft.results):
            assert results_draft.verbatim_quotes[i]
            assert results_draft.evidence_status[i] == EvidenceStatus.QUOTED
            assert results_draft.confidence_llm[i] > 0.5

    def test_provenance_backtracer(self):
        """Test Provenance Backtracer finds spans for LLM results."""
        # First create a draft
        drafter = LLMResultsDrafter()
        drafter_result = drafter.process({
            'raw_doc_text': self.raw_doc_text,
            'doc_id': self.doc_id,
            'trial_context': {}
        })
        
        results_draft = drafter_result.output['results_draft']
        
        # Then backtrace
        backtracer = ProvenanceBacktracer()
        result = backtracer.process({
            'llm_extraction_draft': results_draft,
            'raw_doc_text': self.raw_doc_text,
            'evidence_spans': self.evidence_spans
        })
        
        assert result.success
        assert 'llm_extraction_draft' in result.output
        
        backtraced_draft = result.output['llm_extraction_draft']
        assert isinstance(backtraced_draft, LLMResultsDraft)
        
        # Check that some results have resolved spans
        resolved_count = sum(1 for status in backtraced_draft.provenance_status if status == "resolved")
        assert resolved_count > 0

    def test_results_finalizer(self):
        """Test Results Finalizer merges deterministic and LLM results."""
        # Create LLM draft with resolved spans
        drafter = LLMResultsDrafter()
        drafter_result = drafter.process({
            'raw_doc_text': self.raw_doc_text,
            'doc_id': self.doc_id,
            'trial_context': {}
        })
        
        results_draft = drafter_result.output['results_draft']
        
        # Simulate resolved spans
        for i in range(len(results_draft.results)):
            results_draft.span_ids[i] = f"span_{i}"
            results_draft.provenance_status[i] = "resolved"
        
        # Create deterministic results
        deterministic_results = ResultsFactsheet(
            doc_id=self.doc_id,
            results=[
                {
                    'metric': 'orr_recist',
                    'value': 15.8,
                    'units': 'percent',
                    'span_ids': ['deterministic_span_1'],
                    'source': 'deterministic'
                }
            ]
        )
        
        # Finalize
        finalizer = ResultsFinalizer()
        result = finalizer.process({
            'doc_id': self.doc_id,
            'deterministic_results': deterministic_results,
            'llm_results_draft': results_draft,
            'denominators': {}
        })
        
        assert result.success
        assert 'results_factsheet' in result.output
        
        final_factsheet = result.output['results_factsheet']
        assert isinstance(final_factsheet, ResultsFactsheet)
        assert len(final_factsheet.results) > 0
        
        # Check that results have metadata
        for result_row in final_factsheet.results:
            assert 'metadata' in result_row
            assert 'source' in result_row
            assert 'provenance_score' in result_row
            assert 'trust_score' in result_row

    def test_pmc2978916_example(self):
        """Test the complete PMC2978916 example as described in the architecture."""
        # This test verifies the specific PMC2978916 requirements:
        # - ORR 15.8% with quote including "3/19"
        # - CA-125 21.1% with quote including "4/19"  
        # - TTP 14 weeks and OS 13.1 months with quotes
        # - Multi-span provenance (Results + Methods KM span)
        
        drafter = LLMResultsDrafter()
        drafter_result = drafter.process({
            'raw_doc_text': self.raw_doc_text,
            'doc_id': self.doc_id,
            'trial_context': {}
        })
        
        results_draft = drafter_result.output['results_draft']
        
        # Verify expected results are extracted
        metrics = [result.get('metric') for result in results_draft.results]
        assert 'orr_recist' in metrics
        assert 'ca125_response' in metrics
        assert 'median_ttp' in metrics
        assert 'median_os' in metrics
        
        # Verify verbatim quotes contain expected content
        orr_index = metrics.index('orr_recist')
        ca125_index = metrics.index('ca125_response')
        
        orr_quote = results_draft.verbatim_quotes[orr_index]
        ca125_quote = results_draft.verbatim_quotes[ca125_index]
        
        assert "15.8" in orr_quote
        assert "3/19" in orr_quote
        assert "21.1" in ca125_quote
        assert "4/19" in ca125_quote

    def test_denominator_extraction(self):
        """Test denominator extraction from verbatim quotes."""
        finalizer = ResultsFinalizer()
        
        # Test denominator extraction from various quote formats
        test_cases = [
            ("Overall response rate was 15.8% (3/19 patients)", 19),
            ("CA-125 response rate was 21.1% (4/19)", 19),
            ("3 of 19 patients responded", 19),
            ("Response rate was 15.8%", None),  # No denominator
        ]
        
        for quote, expected_denominator in test_cases:
            extracted = finalizer._extract_denominator_from_quote(quote)
            assert extracted == expected_denominator

    def test_trust_scoring(self):
        """Test trust scoring logic."""
        finalizer = ResultsFinalizer()
        
        # Test deterministic result
        det_result = {
            'metric': 'orr_recist',
            'value': 15.8,
            'units': 'percent',
            'source': 'deterministic'
        }
        
        trust_score = finalizer._calculate_trust_score(
            base_trust=1.0,
            provenance_score=1.0,
            confidence_llm=1.0,
            result=det_result
        )
        
        assert trust_score == 1.0
        
        # Test LLM result with lower confidence
        llm_result = {
            'metric': 'orr_recist',
            'value': 15.8,
            'units': 'percent',
            'source': 'llm'
        }
        
        trust_score = finalizer._calculate_trust_score(
            base_trust=0.8,
            provenance_score=0.9,
            confidence_llm=0.8,
            result=llm_result
        )
        
        assert 0.5 < trust_score < 0.8

    def test_numeric_sanity_checks(self):
        """Test numeric sanity checks."""
        finalizer = ResultsFinalizer()
        
        # Test valid ORR
        valid_orr = {'metric': 'orr_recist', 'value': 15.8, 'units': 'percent'}
        sanity = finalizer._check_numeric_sanity(valid_orr)
        assert sanity == 1.0
        
        # Test invalid ORR (over 100%)
        invalid_orr = {'metric': 'orr_recist', 'value': 150.0, 'units': 'percent'}
        sanity = finalizer._check_numeric_sanity(invalid_orr)
        assert sanity < 1.0
        
        # Test wrong units for ORR
        wrong_units = {'metric': 'orr_recist', 'value': 15.8, 'units': 'weeks'}
        sanity = finalizer._check_numeric_sanity(wrong_units)
        assert sanity < 1.0
