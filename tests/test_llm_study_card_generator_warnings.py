"""
Test to reproduce and investigate LLMStudyCardGenerator warnings.

This test reproduces the issue where the LLM returns no meaningful data
or field_quotes, causing warning messages.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any, List

from src.ncfd.extract.generators.study_card_generator import LLMStudyCardGenerator
from src.ncfd.extract.models.evidence_field import EvidenceField


class TestLLMStudyCardGeneratorWarnings:
    """Test cases for LLMStudyCardGenerator warning scenarios."""
    
    @pytest.fixture
    def generator(self):
        """Create a test generator instance."""
        return LLMStudyCardGenerator()
    
    @pytest.fixture
    def sample_doc_text(self):
        """Sample document text that should contain methodology information."""
        return """
        This is a randomized, double-blind, placebo-controlled study to evaluate the efficacy and safety of 
        Drug X in patients with mild-to-moderate Alzheimer's disease. The study will enroll 200 patients 
        randomized 1:1 to receive either Drug X or placebo for 24 weeks. The primary endpoint is the 
        change from baseline in ADAS-Cog11 score at 24 weeks. Efficacy analyses will be performed on 
        the intent-to-treat population. The study will use a two-sided test with alpha level of 0.05.
        """
    
    @pytest.fixture
    def empty_doc_text(self):
        """Empty or irrelevant document text."""
        return "This document contains no methodology information."
    
    @pytest.fixture
    def trial_context(self):
        """Sample trial context."""
        return {
            "trial_id": "TEST001",
            "disease": "Alzheimer's disease",
            "intervention": "Drug X"
        }
    
    @pytest.mark.asyncio
    async def test_successful_extraction(self, generator, sample_doc_text, trial_context):
        """Test successful extraction with meaningful data."""
        # Mock successful LLM response
        mock_response = {
            "study_card_data": {
                "design_archetype": "Randomized Controlled Trial",
                "is_blinded": True,
                "analysis_set": "Intent-to-Treat",
                "population_description": "Patients with mild-to-moderate Alzheimer's disease",
                "primary_endpoint": "Change from baseline in ADAS-Cog11 score at 24 weeks",
                "alpha_level": 0.05,
                "is_one_sided": False
            },
            "field_quotes": [
                {
                    "field_name": "design_archetype",
                    "value": "Randomized Controlled Trial",
                    "evidence_quote": "This is a randomized, double-blind, placebo-controlled study",
                    "confidence": 0.9
                },
                {
                    "field_name": "primary_endpoint",
                    "value": "Change from baseline in ADAS-Cog11 score at 24 weeks",
                    "evidence_quote": "The primary endpoint is the change from baseline in ADAS-Cog11 score at 24 weeks",
                    "confidence": 0.95
                }
            ]
        }
        
        with patch.object(generator, '_extract_study_card_with_llm', return_value=mock_response):
            result = await generator.process({
                "raw_doc_text": sample_doc_text,
                "doc_id": "test_doc_001",
                "trial_context": trial_context
            })
            
            assert result["success"] is True
            assert result["study_card"] is not None
            assert len(result["field_quotes"]) == 2
            assert result["error_message"] is None
    
    @pytest.mark.asyncio
    async def test_no_meaningful_data_warning(self, generator, empty_doc_text, trial_context):
        """Test the warning when LLM returns no meaningful data."""
        # Mock LLM response with empty study_card_data
        mock_response = {
            "study_card_data": {},  # Empty data
            "field_quotes": [
                {
                    "field_name": "some_field",
                    "value": "some_value",
                    "evidence_quote": "some quote",
                    "confidence": 0.8
                }
            ]
        }
        
        with patch.object(generator, '_extract_study_card_with_llm', return_value=mock_response):
            with patch.object(generator.logger, 'warning') as mock_warning:
                result = await generator.process({
                    "raw_doc_text": empty_doc_text,
                    "doc_id": "test_doc_002",
                    "trial_context": trial_context
                })
                
                # Should trigger the "no meaningful data" warning
                warning_calls = [call[0][0] for call in mock_warning.call_args_list]
                assert any("LLM returned no meaningful LLMStudyCardGenerator data" in warning for warning in warning_calls)
                
                # The generator should return success=True because it has field_quotes, 
                # but the study_card will be None due to empty study_card_data
                assert result["success"] is True
                assert result["study_card"] is not None  # StudyCard object is created even with empty data
                assert len(result["field_quotes"]) == 1
    
    @pytest.mark.asyncio
    async def test_no_field_quotes_warning(self, generator, sample_doc_text, trial_context):
        """Test the warning when LLM returns no field_quotes."""
        # Mock LLM response with empty field_quotes
        mock_response = {
            "study_card_data": {
                "design_archetype": "Randomized Controlled Trial",
                "primary_endpoint": "Change from baseline in ADAS-Cog11 score at 24 weeks"
            },
            "field_quotes": []  # Empty field_quotes
        }
        
        with patch.object(generator, '_extract_study_card_with_llm', return_value=mock_response):
            with patch.object(generator.logger, 'warning') as mock_warning:
                result = await generator.process({
                    "raw_doc_text": sample_doc_text,
                    "doc_id": "test_doc_003",
                    "trial_context": trial_context
                })
                
                # Should trigger the "no field_quotes" warning
                warning_calls = [call[0][0] for call in mock_warning.call_args_list]
                assert any("LLM returned no field_quotes" in warning for warning in warning_calls)
                
                # Should still return success=True since we have meaningful data
                assert result["success"] is True
                assert result["study_card"] is not None
                assert len(result["field_quotes"]) == 0
    
    @pytest.mark.asyncio
    async def test_both_warnings(self, generator, empty_doc_text, trial_context):
        """Test both warnings occurring together."""
        # Mock LLM response with both empty data and empty field_quotes
        mock_response = {
            "study_card_data": {},  # Empty data
            "field_quotes": []  # Empty field_quotes
        }
        
        with patch.object(generator, '_extract_study_card_with_llm', return_value=mock_response):
            with patch.object(generator.logger, 'warning') as mock_warning:
                result = await generator.process({
                    "raw_doc_text": empty_doc_text,
                    "doc_id": "test_doc_004",
                    "trial_context": trial_context
                })
                
                # Should trigger both warnings
                warning_calls = [call[0][0] for call in mock_warning.call_args_list]
                assert any("LLM returned no meaningful LLMStudyCardGenerator data" in warning for warning in warning_calls)
                assert any("LLM returned no field_quotes" in warning for warning in warning_calls)
                
                # Should return success=False
                assert result["success"] is False
                assert result["study_card"] is None
                assert "LLM returned empty response" in result["error_message"]
    
    @pytest.mark.asyncio
    async def test_malformed_field_quotes(self, generator, sample_doc_text, trial_context):
        """Test handling of malformed field_quotes (e.g., LLM returns numbers instead of objects)."""
        # Mock LLM response with malformed field_quotes
        mock_response = {
            "study_card_data": {
                "design_archetype": "Randomized Controlled Trial",
                "primary_endpoint": "Change from baseline in ADAS-Cog11 score at 24 weeks"
            },
            "field_quotes": [42, "invalid", {"field_name": "valid_field", "value": "valid_value", "evidence_quote": "valid quote", "confidence": 0.8}]  # Mixed valid/invalid
        }
        
        with patch.object(generator, '_extract_study_card_with_llm', return_value=mock_response):
            with patch.object(generator.logger, 'error') as mock_error:
                result = await generator.process({
                    "raw_doc_text": sample_doc_text,
                    "doc_id": "test_doc_005",
                    "trial_context": trial_context
                })
                
                # Should log errors for malformed quote data
                error_calls = [call[0][0] for call in mock_error.call_args_list]
                assert any("Quote data is not a dictionary" in error for error in error_calls)
                
                # Should still process valid quotes
                assert result["success"] is True
                assert len(result["field_quotes"]) == 1  # Only the valid one
    
    @pytest.mark.asyncio
    async def test_numeric_evidence_quote_warning(self, generator, sample_doc_text, trial_context):
        """Test the warning when LLM returns numeric values in evidence_quote field."""
        # Mock LLM response with numeric evidence_quote values
        mock_response = {
            "study_card_data": {
                "design_archetype": "Randomized Controlled Trial",
                "primary_endpoint": "Change from baseline in ADAS-Cog11 score at 24 weeks"
            },
            "field_quotes": [
                {
                    "field_name": "design_archetype",
                    "value": "Randomized Controlled Trial",
                    "evidence_quote": 37.0,  # Numeric value instead of text
                    "confidence": 0.9
                },
                {
                    "field_name": 2017.0,  # Numeric field_name instead of string
                    "value": "Change from baseline in ADAS-Cog11 score at 24 weeks",
                    "evidence_quote": 2.0,  # Another numeric value
                    "confidence": 0.95
                },
                {
                    "field_name": "analysis_set",
                    "value": "Intent-to-Treat",
                    "evidence_quote": "Efficacy analyses were performed on the intent-to-treat population",  # Valid text
                    "confidence": 0.85
                }
            ]
        }
        
        with patch.object(generator, '_extract_study_card_with_llm', return_value=mock_response):
            with patch.object(generator.logger, 'warning') as mock_warning:
                result = await generator.process({
                    "raw_doc_text": sample_doc_text,
                    "doc_id": "test_doc_007",
                    "trial_context": trial_context
                })
                
                # Should log warnings for numeric evidence_quote values and field_name
                warning_calls = [call[0][0] for call in mock_warning.call_args_list]
                assert any("Malformed evidence_quote with numeric value '37.0'" in warning for warning in warning_calls)
                assert any("Malformed field_name with non-string value '2017.0'" in warning for warning in warning_calls)
                assert any("Full LLM response for debugging:" in warning for warning in warning_calls)
                
                # Should still process the valid quote
                assert result["success"] is True
                assert len(result["field_quotes"]) == 1  # Only the valid one with text evidence_quote
                assert result["field_quotes"][0].field_name == "analysis_set"
    
    @pytest.mark.asyncio
    async def test_json_parsing_failure(self, generator, sample_doc_text, trial_context):
        """Test handling of JSON parsing failures."""
        # Mock LLM response that fails JSON parsing
        mock_response = "This is not valid JSON"
        
        with patch.object(generator, '_extract_study_card_with_llm', return_value=mock_response):
            with patch.object(generator.logger, 'error') as mock_error:
                result = await generator.process({
                    "raw_doc_text": sample_doc_text,
                    "doc_id": "test_doc_006",
                    "trial_context": trial_context
                })
                
                # Should log JSON parsing errors
                error_calls = [call[0][0] for call in mock_error.call_args_list]
                # The JSON parsing error might be logged at different levels, let's check for any error
                assert len(error_calls) > 0
                
                # Should return success=False due to extraction failure
                assert result["success"] is False
                assert result["study_card"] is None
                assert "LLM LLMStudyCardGenerator extraction failed" in result["error_message"]


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
