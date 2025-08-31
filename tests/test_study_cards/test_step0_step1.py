"""
Tests for Steps 0 and 1 Implementation

Tests the project scaffolding and span triage functionality.
"""

import pytest
from src.ncfd.extract.workers.retriever import Retriever
from src.ncfd.extract.models import DocumentCard, EvidenceSpan
from src.ncfd.utils.study_card_utils import (
    generate_span_id, generate_claim_id, generate_gate_id,
    validate_span_coordinates, normalize_units
)


class TestStep0ProjectScaffolding:
    """Test Step 0: Project scaffolding (shared contracts)."""
    
    def test_id_generation(self):
        """Test ID generation functions."""
        # Test span ID generation
        span_id = generate_span_id("pmid:12345", "Methods", 0, 150)
        assert span_id == "pmid:12345#sec:Methods:char0-150"
        assert "pmid:12345" in span_id
        assert "#sec:Methods:char0-150" in span_id
        
        # Test span ID with page context
        span_id_with_page = generate_span_id("pmid:12345", "Methods", 0, 150, page=1)
        assert span_id_with_page == "pmid:12345#sec:Methods:char0-150:p1"
        
        # Test claim ID generation
        claim_id = generate_claim_id()
        assert claim_id.startswith("claim_")
        assert len(claim_id.split("_")) == 4  # claim_timestamp_hash
        
        # Test gate ID generation
        gate_id = generate_gate_id("g1")
        assert gate_id.startswith("gate_g1_")
        assert "g1" in gate_id
    
    def test_id_validation(self):
        """Test ID validation functions."""
        # Test span coordinate validation
        assert validate_span_coordinates(1, 0, 100) is True
        assert validate_span_coordinates(1, 100, 0) is False  # end < start
        assert validate_span_coordinates(0, 0, 100) is False  # page < 1
        assert validate_span_coordinates(1, -1, 100) is False  # start < 0
    
    def test_unit_normalization(self):
        """Test unit normalization functions."""
        # Test volume conversions
        assert normalize_units(1000, "ul", "ml") == 1.0
        assert normalize_units(1, "l", "ml") == 1000.0
        
        # Test weight conversions
        assert normalize_units(1000, "ug", "mg") == 1.0
        assert normalize_units(1, "g", "mg") == 1000.0
        
        # Test same unit conversion
        assert normalize_units(100, "mg", "mg") == 100.0
        
        # Test invalid conversion
        assert normalize_units(100, "invalid", "mg") is None


class TestStep1SpanTriage:
    """Test Step 1: Span Triage & Index (cheap retrieval)."""
    
    def test_retriever_initialization(self):
        """Test Retriever worker initialization."""
        retriever = Retriever(max_span_length=300, min_confidence=0.8)
        
        assert retriever.name == "Retriever"
        assert retriever.version == "1.0.0"
        assert retriever.max_span_length == 300
        assert retriever.min_confidence == 0.8
    
    def test_retriever_input_validation(self):
        """Test Retriever input validation."""
        retriever = Retriever()
        
        # Valid inputs
        valid_inputs = {
            "trial_context": {
                "disease": "Heart Failure",
                "intervention": "Gene Therapy",
                "trial_id": "NCT12345"
            }
        }
        assert retriever._validate_inputs(valid_inputs) is True
        
        # Invalid inputs
        invalid_inputs = {
            "trial_context": "not_a_dict"
        }
        assert retriever._validate_inputs(invalid_inputs) is False
        
        missing_inputs = {}
        assert retriever._validate_inputs(missing_inputs) is False
    
    def test_document_retrieval(self):
        """Test document retrieval functionality."""
        retriever = Retriever()
        
        trial_context = {
            "disease": "Heart Failure",
            "intervention": "AAV Gene Therapy",
            "trial_id": "NCT12345",
            "study_type": "RCT"
        }
        
        documents = retriever._retrieve_documents(trial_context, "2020-2024")
        
        assert len(documents) == 1
        doc = documents[0]
        
        assert isinstance(doc, DocumentCard)
        assert doc.doc_id == "ctgov:NCT12345"
        assert doc.disease == "Heart Failure"
        assert doc.intervention == "AAV Gene Therapy"
        assert doc.study_type == "RCT"
        assert doc.year == 2023
    
    def test_evidence_span_extraction(self):
        """Test evidence span extraction."""
        retriever = Retriever()
        
        # Create a test document
        doc = DocumentCard(
            doc_id="pmid:12345",
            doc_type="Paper",
            title="Test Study",
            year=2023
        )
        doc.add_fulltext_ref(1, 0, 500, "text")
        doc.add_fulltext_ref(2, 0, 600, "text")
        
        # Extract spans
        spans = retriever._extract_spans_from_document(doc)
        
        assert len(spans) > 0
        for span in spans:
            assert isinstance(span, EvidenceSpan)
            assert span.doc_id == "pmid:12345"
            assert span.confidence > 0.0
            assert len(span.quote) <= retriever.max_span_length
    
    def test_span_filtering(self):
        """Test span filtering based on quality criteria."""
        retriever = Retriever(max_span_length=400, min_confidence=0.7)
        
        # Create test spans
        spans = []
        
        # High quality span
        good_span = EvidenceSpan(
            span_id="test#p1:0-100",
            doc_id="test",
            page=1,
            char_start=0,
            char_end=100,
            quote="This is a high-quality methods section with detailed methodology information.",
            section="Methods",
            confidence=0.9
        )
        spans.append(good_span)
        
        # Low confidence span
        low_conf_span = EvidenceSpan(
            span_id="test#p1:100-200",
            doc_id="test",
            page=1,
            char_start=100,
            char_end=200,
            quote="This is a low confidence span.",
            section="Results",
            confidence=0.5
        )
        spans.append(low_conf_span)
        
        # Filter spans
        filtered = retriever._filter_spans(spans)
        
        assert len(filtered) == 1
        assert filtered[0].span_id == "test#p1:0-100"
    
    def test_low_quality_span_detection(self):
        """Test detection of low-quality spans."""
        retriever = Retriever()
        
        # Test various low-quality indicators
        low_quality_spans = [
            "Page 1 of the document",
            "Figure 2 shows the results",
            "See Table 1 for details",
            "Reference [1]",
            "Supplementary material",
            "12345 67890 11111",  # Mostly numbers
            "Short",  # Too short
        ]
        
        for text in low_quality_spans:
            span = EvidenceSpan(
                span_id="test#p1:0-100",
                doc_id="test",
                page=1,
                char_start=0,
                char_end=len(text),
                quote=text,
                section="Methods",
                confidence=0.8
            )
            
            assert retriever._is_low_quality_span(span) is True
    
    def test_retriever_execution(self):
        """Test complete Retriever execution."""
        retriever = Retriever()
        
        inputs = {
            "trial_context": {
                "disease": "Heart Failure",
                "intervention": "Gene Therapy",
                "trial_id": "NCT12345"
            },
            "date_window": "2020-2024"
        }
        
        result = retriever.execute(inputs)
        
        assert result.success is True
        assert "document_cards" in result.output
        assert "evidence_spans" in result.output
        assert len(result.output["document_cards"]) > 0
        assert len(result.output["evidence_spans"]) > 0
        
        # Check metadata
        assert result.metadata["documents_retrieved"] > 0
        assert result.metadata["spans_extracted"] > 0
        assert result.metadata["date_window"] == "2020-2024"


class TestIntegration:
    """Test integration between Steps 0 and 1."""
    
    def test_end_to_end_workflow(self):
        """Test end-to-end workflow from retrieval to span creation."""
        retriever = Retriever()
        
        # Execute retrieval
        inputs = {
            "trial_context": {
                "disease": "Heart Failure",
                "intervention": "AAV Gene Therapy",
                "trial_id": "NCT12345"
            }
        }
        
        result = retriever.execute(inputs)
        assert result.success is True
        
        # Verify document cards
        doc_cards = result.output["document_cards"]
        assert len(doc_cards) > 0
        
        doc = doc_cards[0]
        assert doc.doc_id.startswith("ctgov:")
        assert doc.disease == "Heart Failure"
        assert doc.intervention == "AAV Gene Therapy"
        
        # Verify evidence spans
        spans = result.output["evidence_spans"]
        assert len(spans) > 0
        
        for span in spans:
            # Check span ID format
            assert "#p" in span.span_id
            assert ":" in span.span_id
            assert "-" in span.span_id
            
            # Check span quality
            assert span.confidence >= retriever.min_confidence
            assert len(span.quote) <= retriever.max_span_length
            assert span.quote.strip() != ""
            
            # Check provenance
            assert hasattr(span, 'created_at')
            assert hasattr(span, 'created_by')
            assert hasattr(span, 'input_hash')
    
    def test_span_coordinate_validation(self):
        """Test that all generated spans have valid coordinates."""
        retriever = Retriever()
        
        inputs = {
            "trial_context": {
                "disease": "Heart Failure",
                "intervention": "Gene Therapy",
                "trial_id": "NCT12345"
            }
        }
        
        result = retriever.execute(inputs)
        assert result.success is True
        
        spans = result.output["evidence_spans"]
        
        for span in spans:
            # Validate coordinates
            assert validate_span_coordinates(
                span.page, span.char_start, span.char_end
            ) is True
            
            # Validate span ID format
            expected_format = f"{span.doc_id}#p{span.page}:{span.char_start}-{span.char_end}"
            assert span.span_id == expected_format
