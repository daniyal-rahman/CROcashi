"""
Test with comprehensive logging to debug where data is being lost.
"""

import pytest
import asyncio
from ncfd.extract.generators.study_card_generator import LLMStudyCardGenerator


class TestStudyCardDebugLogging:
    """Test with comprehensive logging to debug data loss."""
    
    @pytest.fixture
    def generator(self):
        """Create study card generator instance."""
        return LLMStudyCardGenerator()
    
    @pytest.mark.asyncio
    async def test_debug_with_realistic_data(self, generator):
        """Test with realistic data and comprehensive logging."""
        # Use realistic methodology text
        doc_text = """
        STUDY DESIGN AND METHODS
        
        This was a randomized, double-blind, placebo-controlled, parallel-group study designed to evaluate the efficacy and safety of simufilam in patients with mild-to-moderate Alzheimer's disease.
        
        PATIENT POPULATION
        
        Patients were eligible for inclusion if they were aged 50-85 years, had a diagnosis of probable Alzheimer's disease according to the National Institute of Neurological and Communicative Disorders and Stroke-Alzheimer's Disease and Related Disorders Association criteria, had a Mini-Mental State Examination score of 12-26, and had a reliable caregiver.
        
        RANDOMIZATION AND BLINDING
        
        Patients were randomized 1:1 to receive either simufilam 100mg twice daily or matching placebo for 24 weeks. Randomization was stratified by baseline MMSE score (12-18 vs 19-26) and geographic region.
        
        The study was double-blind, with patients, investigators, and study staff unaware of treatment assignment. Study medication was provided in identical-appearing capsules.
        
        PRIMARY ENDPOINT
        
        The primary efficacy endpoint was the change from baseline in the Alzheimer's Disease Assessment Scale-Cognitive subscale (ADAS-Cog11) score at 24 weeks.
        
        STATISTICAL ANALYSIS
        
        Statistical analysis was performed using a mixed model for repeated measures (MMRM) approach. The model included baseline score, treatment group, visit, treatment-by-visit interaction, and stratification factors as fixed effects.
        
        ANALYSIS POPULATIONS
        
        Efficacy analyses were performed on the intent-to-treat (ITT) population, which included all randomized patients who received at least one dose of study medication and had at least one post-baseline assessment.
        """
        
        doc_id = "test_debug_logging"
        trial_context = {
            "trial_id": "NCT12345678",
            "disease": "Alzheimer's Disease",
            "intervention": "Simufilam",
            "phase": "Phase 2"
        }
        
        print(f"🔍 TESTING WITH COMPREHENSIVE LOGGING:")
        print(f"   Doc text length: {len(doc_text)}")
        print(f"   Doc text preview: {doc_text[:200]}...")
        print(f"   Trial context: {trial_context}")
        
        inputs = {
            "raw_doc_text": doc_text,
            "doc_id": doc_id,
            "trial_context": trial_context
        }
        
        # Enable debug logging
        import logging
        logging.getLogger("ncfd.extract.generators.study_card_generator").setLevel(logging.INFO)
        logging.getLogger("ncfd.llm.base_worker").setLevel(logging.INFO)
        
        result = await generator.process(inputs)
        
        print(f"\n🔍 FINAL RESULT:")
        print(f"   Success: {result['success']}")
        print(f"   Error: {result['error_message']}")
        print(f"   Field quotes count: {len(result['field_quotes'])}")
        
        if result['study_card']:
            study_card = result['study_card']
            print(f"   Study card fields populated:")
            for field_name in ['design_archetype', 'primary_endpoint', 'population_description', 'analysis_set']:
                value = getattr(study_card, field_name, None)
                if value:
                    print(f"     {field_name}: {value}")
        
        # Check for issues
        if not result['success']:
            if "empty response" in result['error_message']:
                print(f"\n🚨 EMPTY RESPONSE ISSUE DETECTED!")
                print(f"   This means the LLM returned data but it was zeroed out in post-processing")
            else:
                print(f"\n❌ OTHER ERROR: {result['error_message']}")
        else:
            print(f"\n✅ SUCCESS!")
            print(f"   Generated {len(result['field_quotes'])} field quotes")
    
    @pytest.mark.asyncio
    async def test_debug_with_minimal_data(self, generator):
        """Test with minimal data to see what happens."""
        # Minimal text that should still contain some methodology
        doc_text = """
        This was a randomized controlled trial of simufilam in patients with Alzheimer's disease.
        The primary endpoint was change in ADAS-Cog11 score at 24 weeks.
        Analysis was performed on the intent-to-treat population.
        """
        
        doc_id = "test_minimal_debug"
        trial_context = {
            "trial_id": "NCT12345678",
            "disease": "Alzheimer's Disease",
            "intervention": "Simufilam"
        }
        
        print(f"🔍 TESTING WITH MINIMAL DATA:")
        print(f"   Doc text: {doc_text}")
        
        inputs = {
            "raw_doc_text": doc_text,
            "doc_id": doc_id,
            "trial_context": trial_context
        }
        
        result = await generator.process(inputs)
        
        print(f"\n🔍 MINIMAL DATA RESULT:")
        print(f"   Success: {result['success']}")
        print(f"   Error: {result['error_message']}")
        print(f"   Field quotes count: {len(result['field_quotes'])}")


if __name__ == "__main__":
    # Run the tests directly
    import sys
    sys.path.append('/Users/danirahman/Repos/CROcashi')
    
    async def main():
        test_instance = TestStudyCardDebugLogging()
        generator = test_instance.generator()
        
        # Test with comprehensive logging
        await test_instance.test_debug_with_realistic_data(generator)
        await test_instance.test_debug_with_minimal_data(generator)
    
    asyncio.run(main())
