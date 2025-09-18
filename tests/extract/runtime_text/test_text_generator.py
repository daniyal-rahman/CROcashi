"""
Tests for RuntimeTextGenerator
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from src.ncfd.extract.runtime_text.text_generator import RuntimeTextGenerator
from src.ncfd.extract.runtime_text.api_clients import TextRetrievalResult


class TestRuntimeTextGenerator:
    """Test cases for RuntimeTextGenerator."""
    
    @pytest.fixture
    def generator(self):
        """Create a RuntimeTextGenerator instance for testing."""
        config = {
            "apis": {
                "pubmed": {"rate_limit_per_minute": 60, "timeout_seconds": 30},
                "pmc": {"rate_limit_per_minute": 30, "timeout_seconds": 45},
                "unpaywall": {"rate_limit_per_minute": 100, "timeout_seconds": 20}
            },
            "quality": {
                "min_fulltext_length": 500,
                "min_abstract_length": 100
            },
            "fallback_order": ["pmc", "pubmed", "unpaywall"]
        }
        return RuntimeTextGenerator(config)
    
    @pytest.mark.asyncio
    async def test_generate_text_success(self, generator):
        """Test successful text generation."""
        # Mock document metadata
        doc_metadata = {
            "doc_id": 123,
            "pmid": "12345678",
            "pmcid": "PMC123456",
            "doi": "10.1234/test.doi",
            "title": "Test Document",
            "source_type": "Paper"
        }
        
        # Mock successful PMC retrieval
        mock_result = TextRetrievalResult(
            success=True,
            text="This is a test document with sufficient content for full text processing.",
            source="pmc",
            length=100,
            metadata={"pmcid": "PMC123456", "type": "fulltext"}
        )
        
        with patch.object(generator, '_get_document_metadata', return_value=doc_metadata), \
             patch.object(generator.pmc_client, 'fetch_fulltext', return_value=mock_result):
            
            result = await generator.generate_text("123")
            assert result == "This is a test document with sufficient content for full text processing."
    
    @pytest.mark.asyncio
    async def test_generate_text_fallback(self, generator):
        """Test fallback to different sources."""
        doc_metadata = {
            "doc_id": 123,
            "pmid": "12345678",
            "pmcid": None,  # No PMCID
            "doi": None,    # No DOI
            "title": "Test Document",
            "source_type": "Paper"
        }
        
        # Mock PMC failure, PubMed success
        pmc_failure = TextRetrievalResult(
            success=False,
            text="",
            source="pmc",
            length=0,
            error_message="No PMCID available"
        )
        
        pubmed_success = TextRetrievalResult(
            success=True,
            text="This is an abstract with sufficient content for processing.",
            source="pubmed",
            length=150,
            metadata={"pmid": "12345678", "type": "abstract"}
        )
        
        with patch.object(generator, '_get_document_metadata', return_value=doc_metadata), \
             patch.object(generator.pmc_client, 'fetch_fulltext', return_value=pmc_failure), \
             patch.object(generator.pubmed_client, 'fetch_abstract', return_value=pubmed_success):
            
            result = await generator.generate_text("123")
            assert result == "This is an abstract with sufficient content for processing."
    
    @pytest.mark.asyncio
    async def test_generate_text_no_metadata(self, generator):
        """Test text generation when no metadata is available."""
        with patch.object(generator, '_get_document_metadata', return_value=None):
            result = await generator.generate_text("123")
            assert result == ""
    
    @pytest.mark.asyncio
    async def test_generate_text_all_sources_fail(self, generator):
        """Test when all sources fail."""
        doc_metadata = {
            "doc_id": 123,
            "pmid": "12345678",
            "pmcid": "PMC123456",
            "doi": "10.1234/test.doi",
            "title": "Test Document",
            "source_type": "Paper"
        }
        
        failure_result = TextRetrievalResult(
            success=False,
            text="",
            source="unknown",
            length=0,
            error_message="All sources failed"
        )
        
        with patch.object(generator, '_get_document_metadata', return_value=doc_metadata), \
             patch.object(generator, '_try_source', return_value=failure_result):
            
            result = await generator.generate_text("123")
            assert result == ""
    
    def test_is_text_quality_acceptable(self, generator):
        """Test text quality validation."""
        # Good quality text
        assert generator._is_text_quality_acceptable("This is a long enough text for processing.")
        
        # Too short text
        assert not generator._is_text_quality_acceptable("Short")
        
        # Empty text
        assert not generator._is_text_quality_acceptable("")
        assert not generator._is_text_quality_acceptable("   ")
    
    @pytest.mark.asyncio
    async def test_generate_texts_batch(self, generator):
        """Test batch text generation."""
        doc_ids = ["123", "456", "789"]
        
        # Mock successful generation for all documents
        with patch.object(generator, 'generate_text') as mock_generate:
            mock_generate.side_effect = [
                "Text for doc 123",
                "Text for doc 456", 
                "Text for doc 789"
            ]
            
            results = await generator.generate_texts_batch(doc_ids)
            
            assert len(results) == 3
            assert results["123"] == "Text for doc 123"
            assert results["456"] == "Text for doc 456"
            assert results["789"] == "Text for doc 789"
            assert mock_generate.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__])
