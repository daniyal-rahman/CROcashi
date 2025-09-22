"""
Debug the exact flow of the study card generator to find where the prompt is lost.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from ncfd.extract.generators.study_card_generator import LLMStudyCardGenerator


class TestStudyCardDebugFlow:
    """Debug the exact flow."""
    
    @pytest.fixture
    def generator(self):
        """Create study card generator instance."""
        return LLMStudyCardGenerator()
    
    @pytest.mark.asyncio
    async def test_debug_execute_with_retry_flow(self, generator):
        """Debug the _execute_with_retry flow."""
        doc_text = "This is a randomized controlled trial of simufilam in patients with Alzheimer's disease."
        doc_id = "test_123"
        trial_context = {
            "trial_id": "NCT12345678",
            "disease": "Alzheimer's Disease",
            "intervention": "Simufilam"
        }
        
        # Mock the _extract_with_llm method to see what parameters it receives
        async def mock_extract_with_llm(doc_text_param, trial_context_param, prompt_param):
            print(f"🔍 _extract_with_llm called with:")
            print(f"  doc_text: {doc_text_param[:50]}...")
            print(f"  trial_context: {trial_context_param}")
            print(f"  prompt: {prompt_param[:100] if prompt_param else 'None'}...")
            print(f"  prompt type: {type(prompt_param)}")
            print(f"  prompt length: {len(prompt_param) if prompt_param else 'None'}")
            
            # Return empty result to simulate the issue
            return {}
        
        with patch.object(generator, '_extract_with_llm', side_effect=mock_extract_with_llm):
            result = await generator._execute_with_retry(doc_text, doc_id, trial_context)
            print(f"Result: {result}")
    
    @pytest.mark.asyncio
    async def test_debug_build_standard_prompt(self, generator):
        """Debug the _build_standard_prompt method."""
        doc_text = "This is a randomized controlled trial of simufilam in patients with Alzheimer's disease."
        doc_id = "test_123"
        trial_context = {
            "trial_id": "NCT12345678",
            "disease": "Alzheimer's Disease",
            "intervention": "Simufilam"
        }
        
        # Test the method directly
        prompt = generator._build_standard_prompt(doc_text, doc_id, trial_context)
        
        print(f"🔍 _build_standard_prompt result:")
        print(f"  prompt type: {type(prompt)}")
        print(f"  prompt length: {len(prompt)}")
        print(f"  prompt preview: {prompt[:200]}...")
        
        assert prompt is not None
        assert len(prompt) > 0
        assert isinstance(prompt, str)
    
    @pytest.mark.asyncio
    async def test_debug_extract_study_card_with_llm_direct(self, generator):
        """Debug _extract_study_card_with_llm directly."""
        doc_text = "This is a randomized controlled trial of simufilam in patients with Alzheimer's disease."
        trial_context = {
            "trial_id": "NCT12345678",
            "disease": "Alzheimer's Disease",
            "intervention": "Simufilam"
        }
        test_prompt = "This is a test prompt for debugging."
        
        # Mock the LLM call
        async def mock_call_llm(*args, **kwargs):
            print(f"🔍 call_llm called with:")
            print(f"  args: {args}")
            print(f"  kwargs: {kwargs}")
            
            # Check messages parameter
            if 'messages' in kwargs:
                messages = kwargs['messages']
                print(f"  messages: {messages}")
                if messages and len(messages) > 0:
                    content = messages[0].get('content', '')
                    print(f"  content: {content[:100]}...")
                    print(f"  content type: {type(content)}")
                    print(f"  content length: {len(content)}")
            
            return AsyncMock(content={})
        
        with patch.object(generator, 'call_llm', side_effect=mock_call_llm):
            result = await generator._extract_study_card_with_llm(doc_text, trial_context, test_prompt)
            print(f"Result: {result}")


if __name__ == "__main__":
    # Run the tests directly
    import sys
    sys.path.append('/Users/danirahman/Repos/CROcashi')
    
    async def main():
        test_instance = TestStudyCardDebugFlow()
        generator = test_instance.generator()
        
        # Test each method
        await test_instance.test_debug_build_standard_prompt(generator)
        await test_instance.test_debug_extract_study_card_with_llm_direct(generator)
        await test_instance.test_debug_execute_with_retry_flow(generator)
    
    asyncio.run(main())
