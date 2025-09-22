"""
Debug test to check what prompt is being generated.
"""

import pytest
from ncfd.extract.generators.study_card_generator import LLMStudyCardGenerator


class TestStudyCardDebugPrompt:
    """Debug prompt generation."""
    
    @pytest.fixture
    def generator(self):
        """Create study card generator instance."""
        return LLMStudyCardGenerator()
    
    def test_prompt_generation(self, generator):
        """Test that prompt is generated correctly."""
        doc_text = "This is a randomized controlled trial of simufilam in patients with Alzheimer's disease."
        doc_id = "test_123"
        trial_context = {
            "trial_id": "NCT12345678",
            "disease": "Alzheimer's Disease",
            "intervention": "Simufilam"
        }
        
        # Test the standard prompt method
        prompt = generator._build_standard_prompt(doc_text, doc_id, trial_context)
        
        print(f"Generated prompt length: {len(prompt)}")
        print(f"Generated prompt preview: {prompt[:500]}...")
        
        # Check that prompt contains expected elements
        assert "clinical trial methodology expert" in prompt
        assert "Document Text:" in prompt
        assert "Trial Context:" in prompt
        assert "CRITICAL REQUIREMENTS:" in prompt
        assert "The response will be automatically formatted" in prompt
        
        # Check that it doesn't contain JSON examples
        assert '{"study_card_data":' not in prompt
        assert '"field_quotes": [' not in prompt
        
        print("✅ Prompt generation test passed")
    
    def test_extract_with_llm_prompt_parameter(self, generator):
        """Test that _extract_study_card_with_llm receives the prompt correctly."""
        doc_text = "This is a randomized controlled trial of simufilam in patients with Alzheimer's disease."
        trial_context = {
            "trial_id": "NCT12345678",
            "disease": "Alzheimer's Disease",
            "intervention": "Simufilam"
        }
        
        # Test with a specific prompt
        test_prompt = "This is a test prompt for debugging."
        
        # Mock the LLM call to see what parameters are passed
        import asyncio
        from unittest.mock import patch, AsyncMock
        
        async def mock_call_llm(*args, **kwargs):
            print("🔍 Mock LLM Call Parameters:")
            print(f"  Messages: {args[0] if args else 'None'}")
            print(f"  Temperature: {kwargs.get('temperature', 'None')}")
            print(f"  Max tokens: {kwargs.get('max_tokens', 'None')}")
            print(f"  JSON schema: {kwargs.get('json_schema', 'None')}")
            
            # Check the prompt content
            if args and len(args) > 0 and 'messages' in args[0]:
                messages = args[0]['messages']
                if messages and len(messages) > 0:
                    prompt = messages[0].get('content', '')
                    print(f"  Prompt length: {len(prompt)}")
                    print(f"  Prompt content: {prompt}")
                    
                    # Verify the prompt matches what we expect
                    if prompt == test_prompt:
                        print("  ✅ Prompt matches expected test prompt")
                    else:
                        print(f"  ❌ Prompt mismatch! Expected: {test_prompt}")
                        print(f"  ❌ Got: {prompt}")
            
            # Return empty response
            return AsyncMock(content={})
        
        async def run_test():
            with patch.object(generator, 'call_llm', side_effect=mock_call_llm):
                result = await generator._extract_study_card_with_llm(doc_text, trial_context, test_prompt)
                return result
        
        result = asyncio.run(run_test())
        print(f"Result: {result}")
        
        # Should return empty dict due to mock
        assert result == {}


if __name__ == "__main__":
    # Run the test directly
    import sys
    sys.path.append('/Users/danirahman/Repos/CROcashi')
    
    test_instance = TestStudyCardDebugPrompt()
    generator = test_instance.generator()
    
    # Test prompt generation
    test_instance.test_prompt_generation(generator)
    
    # Test extract with LLM
    test_instance.test_extract_with_llm_prompt_parameter(generator)
