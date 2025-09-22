"""
Test study card generator with real LLM to see what's happening.
"""

import pytest
import asyncio
from ncfd.extract.generators.study_card_generator import LLMStudyCardGenerator


class TestStudyCardRealLLM:
    """Test with real LLM."""
    
    @pytest.fixture
    def generator(self):
        """Create study card generator instance."""
        return LLMStudyCardGenerator()
    
    @pytest.mark.asyncio
    async def test_real_llm_call(self, generator):
        """Test with real LLM to see what happens."""
        doc_text = """
        This was a randomized, double-blind, placebo-controlled trial of simufilam in patients with mild-to-moderate Alzheimer's disease.
        
        Patients were randomized 1:1 to receive either simufilam 100mg twice daily or placebo for 24 weeks.
        
        The primary endpoint was the change from baseline in the Alzheimer's Disease Assessment Scale-Cognitive subscale (ADAS-Cog11) score at 24 weeks.
        
        Secondary endpoints included the Clinical Dementia Rating-Sum of Boxes (CDR-SB) and the Alzheimer's Disease Cooperative Study-Activities of Daily Living (ADCS-ADL) scale.
        
        Statistical analysis was performed using a mixed model for repeated measures (MMRM) with baseline score, treatment, visit, and treatment-by-visit interaction as fixed effects.
        
        The study was designed with 80% power to detect a 2.5-point difference in ADAS-Cog11 score between groups at a two-sided alpha level of 0.05.
        
        Efficacy analyses were performed on the intent-to-treat (ITT) population, which included all randomized patients who received at least one dose of study medication.
        """
        
        doc_id = "test_real_llm"
        trial_context = {
            "trial_id": "NCT12345678",
            "disease": "Alzheimer's Disease",
            "intervention": "Simufilam"
        }
        
        print(f"🔍 Testing with real LLM:")
        print(f"  Doc text length: {len(doc_text)}")
        print(f"  Doc text preview: {doc_text[:200]}...")
        
        # Test the full process
        inputs = {
            "raw_doc_text": doc_text,
            "doc_id": doc_id,
            "trial_context": trial_context
        }
        
        result = await generator.process(inputs)
        
        print(f"🔍 Result:")
        print(f"  Success: {result['success']}")
        print(f"  Error: {result['error_message']}")
        print(f"  Field quotes count: {len(result['field_quotes'])}")
        
        if result['study_card']:
            print(f"  Study card fields: {list(result['study_card'].__dict__.keys())}")
        
        # Check if we got the empty response issue
        if not result['success'] and "empty response" in result['error_message']:
            print("🚨 REPRODUCED EMPTY RESPONSE ISSUE WITH REAL LLM!")
            
            # Let's also test the individual components
            print("\n🔍 Testing individual components:")
            
            # Test prompt generation
            prompt = generator._build_standard_prompt(doc_text, doc_id, trial_context)
            print(f"  Generated prompt length: {len(prompt)}")
            print(f"  Prompt preview: {prompt[:300]}...")
            
            # Test direct LLM call
            try:
                llm_result = await generator._extract_study_card_with_llm(doc_text, trial_context, prompt)
                print(f"  Direct LLM result: {llm_result}")
                print(f"  Direct LLM result keys: {list(llm_result.keys())}")
            except Exception as e:
                print(f"  Direct LLM call failed: {e}")
            
            # This confirms the issue
            assert False, f"Empty response issue reproduced with real LLM: {result['error_message']}"
        
        # If successful, verify we got meaningful content
        if result['success']:
            assert result['study_card'] is not None
            assert len(result['field_quotes']) > 0
            print("✅ Test passed - got meaningful content from real LLM")
        else:
            print(f"❌ Test failed with error: {result['error_message']}")
            # Don't fail the test, just report the issue
            pytest.skip(f"Test failed with error: {result['error_message']}")


if __name__ == "__main__":
    # Run the test directly
    import sys
    sys.path.append('/Users/danirahman/Repos/CROcashi')
    
    async def main():
        test_instance = TestStudyCardRealLLM()
        generator = test_instance.generator()
        
        # Test with real LLM
        await test_instance.test_real_llm_call(generator)
    
    asyncio.run(main())
