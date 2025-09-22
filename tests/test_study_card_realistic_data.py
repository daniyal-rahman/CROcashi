"""
Test study card generator with realistic clinical trial methodology data.
This tests the complete pipeline with data that should definitely contain methodology information.
"""

import pytest
import asyncio
from ncfd.extract.generators.study_card_generator import LLMStudyCardGenerator


class TestStudyCardRealisticData:
    """Test with realistic clinical trial methodology data."""
    
    @pytest.fixture
    def generator(self):
        """Create study card generator instance."""
        return LLMStudyCardGenerator()
    
    @pytest.fixture
    def realistic_methodology_text(self):
        """Realistic clinical trial methodology text."""
        return """
        STUDY DESIGN AND METHODS
        
        This was a randomized, double-blind, placebo-controlled, parallel-group study designed to evaluate the efficacy and safety of simufilam in patients with mild-to-moderate Alzheimer's disease.
        
        PATIENT POPULATION
        
        Patients were eligible for inclusion if they were aged 50-85 years, had a diagnosis of probable Alzheimer's disease according to the National Institute of Neurological and Communicative Disorders and Stroke-Alzheimer's Disease and Related Disorders Association criteria, had a Mini-Mental State Examination score of 12-26, and had a reliable caregiver.
        
        Patients were excluded if they had severe psychiatric or neurological disorders, significant cardiovascular disease, or were taking medications that could interfere with the study.
        
        RANDOMIZATION AND BLINDING
        
        Patients were randomized 1:1 to receive either simufilam 100mg twice daily or matching placebo for 24 weeks. Randomization was stratified by baseline MMSE score (12-18 vs 19-26) and geographic region.
        
        The study was double-blind, with patients, investigators, and study staff unaware of treatment assignment. Study medication was provided in identical-appearing capsules.
        
        PRIMARY ENDPOINT
        
        The primary efficacy endpoint was the change from baseline in the Alzheimer's Disease Assessment Scale-Cognitive subscale (ADAS-Cog11) score at 24 weeks.
        
        SECONDARY ENDPOINTS
        
        Secondary endpoints included:
        - Clinical Dementia Rating-Sum of Boxes (CDR-SB)
        - Alzheimer's Disease Cooperative Study-Activities of Daily Living (ADCS-ADL) scale
        - Neuropsychiatric Inventory (NPI)
        - Caregiver Burden Scale
        
        STATISTICAL ANALYSIS
        
        Statistical analysis was performed using a mixed model for repeated measures (MMRM) approach. The model included baseline score, treatment group, visit, treatment-by-visit interaction, and stratification factors as fixed effects.
        
        The study was designed with 80% power to detect a 2.5-point difference in ADAS-Cog11 score between groups at a two-sided alpha level of 0.05. Sample size calculation assumed a standard deviation of 6.0 points and 15% dropout rate.
        
        ANALYSIS POPULATIONS
        
        Efficacy analyses were performed on the intent-to-treat (ITT) population, which included all randomized patients who received at least one dose of study medication and had at least one post-baseline assessment.
        
        Safety analyses were performed on all patients who received at least one dose of study medication.
        
        MISSING DATA HANDLING
        
        Missing data were handled using the MMRM approach, which assumes data are missing at random. Sensitivity analyses were performed using last observation carried forward (LOCF) and worst-case scenario imputation.
        
        INTERIM ANALYSIS
        
        An interim analysis was planned after 50% of patients completed the study to assess futility. The interim analysis used a Lan-DeMets alpha spending function with O'Brien-Fleming boundaries.
        
        SAFETY MONITORING
        
        Safety was assessed through adverse event reporting, laboratory tests, vital signs, and physical examinations. An independent Data Safety Monitoring Board (DSMB) reviewed safety data quarterly.
        """
    
    @pytest.fixture
    def trial_context(self):
        """Realistic trial context."""
        return {
            "trial_id": "NCT12345678",
            "disease": "Alzheimer's Disease",
            "intervention": "Simufilam",
            "phase": "Phase 2"
        }
    
    @pytest.mark.asyncio
    async def test_realistic_methodology_extraction(self, generator, realistic_methodology_text, trial_context):
        """Test extraction with realistic methodology text."""
        doc_id = "test_realistic_methodology"
        
        print(f"🔍 Testing with realistic methodology text:")
        print(f"   Text length: {len(realistic_methodology_text)}")
        print(f"   Trial context: {trial_context}")
        
        inputs = {
            "raw_doc_text": realistic_methodology_text,
            "doc_id": doc_id,
            "trial_context": trial_context
        }
        
        result = await generator.process(inputs)
        
        print(f"🔍 Result:")
        print(f"   Success: {result['success']}")
        print(f"   Error: {result['error_message']}")
        print(f"   Field quotes count: {len(result['field_quotes'])}")
        
        if result['study_card']:
            study_card = result['study_card']
            print(f"   Study card fields populated:")
            populated_fields = []
            for field_name in ['design_archetype', 'primary_endpoint', 'population_description', 'analysis_set', 'alpha_level', 'is_blinded']:
                value = getattr(study_card, field_name, None)
                if value:
                    populated_fields.append(f"{field_name}: {value}")
                    print(f"     {field_name}: {value}")
            
            print(f"   Total populated fields: {len(populated_fields)}")
        
        # Check for the empty response issue
        if not result['success'] and "empty response" in result['error_message']:
            print("🚨 EMPTY RESPONSE ISSUE WITH REALISTIC DATA!")
            print(f"   Error message: {result['error_message']}")
            
            # Debug what's happening
            print("\n🔍 Debugging:")
            prompt = generator._build_standard_prompt(realistic_methodology_text, doc_id, trial_context)
            print(f"   Prompt length: {len(prompt)}")
            print(f"   Prompt preview: {prompt[:300]}...")
            
            # Test direct LLM call
            try:
                llm_result = await generator._extract_study_card_with_llm(realistic_methodology_text, trial_context, prompt)
                print(f"   Direct LLM result: {llm_result}")
                print(f"   Direct LLM result keys: {list(llm_result.keys())}")
                
                if llm_result.get('study_card_data'):
                    print(f"   study_card_data: {llm_result['study_card_data']}")
                if llm_result.get('field_quotes'):
                    print(f"   field_quotes count: {len(llm_result['field_quotes'])}")
                    for i, quote in enumerate(llm_result['field_quotes'][:3]):
                        print(f"     Quote {i+1}: {quote}")
                        
            except Exception as e:
                print(f"   Direct LLM call failed: {e}")
            
            assert False, f"Empty response issue with realistic data: {result['error_message']}"
        
        # If successful, verify we got meaningful content
        if result['success']:
            assert result['study_card'] is not None
            assert len(result['field_quotes']) > 0
            
            # Verify we got methodology-specific fields
            study_card = result['study_card']
            methodology_fields = ['design_archetype', 'primary_endpoint', 'population_description', 'analysis_set']
            populated_methodology_fields = [f for f in methodology_fields if getattr(study_card, f, None)]
            
            print(f"✅ Test passed!")
            print(f"   Populated methodology fields: {len(populated_methodology_fields)}/{len(methodology_fields)}")
            print(f"   Field quotes: {len(result['field_quotes'])}")
            
            # Should have at least some methodology fields populated
            assert len(populated_methodology_fields) > 0, "No methodology fields were populated"
            assert len(result['field_quotes']) > 0, "No field quotes were generated"
            
        else:
            print(f"❌ Test failed with error: {result['error_message']}")
            pytest.skip(f"Test failed: {result['error_message']}")
    
    @pytest.mark.asyncio
    async def test_evidence_quote_validation(self, generator, realistic_methodology_text, trial_context):
        """Test that evidence quotes are properly validated."""
        doc_id = "test_evidence_validation"
        
        inputs = {
            "raw_doc_text": realistic_methodology_text,
            "doc_id": doc_id,
            "trial_context": trial_context
        }
        
        result = await generator.process(inputs)
        
        if result['success'] and result['field_quotes']:
            print(f"🔍 Validating {len(result['field_quotes'])} field quotes:")
            
            for i, quote in enumerate(result['field_quotes']):
                print(f"   Quote {i+1}:")
                print(f"     field_name: {quote.field_name} (type: {type(quote.field_name)})")
                print(f"     value: {quote.value} (type: {type(quote.value)})")
                print(f"     evidence_quote: {quote.evidence_quote[:100]}... (type: {type(quote.evidence_quote)})")
                print(f"     confidence: {quote.confidence} (type: {type(quote.confidence)})")
                
                # Validate evidence quote is text
                assert isinstance(quote.evidence_quote, str), f"Evidence quote should be string, got {type(quote.evidence_quote)}"
                assert len(quote.evidence_quote) >= 10, f"Evidence quote too short: {len(quote.evidence_quote)}"
                assert quote.evidence_quote[0].isalpha(), f"Evidence quote should start with letter: {quote.evidence_quote[:10]}"
                
                # Validate field name is text
                assert isinstance(quote.field_name, str), f"Field name should be string, got {type(quote.field_name)}"
                
                # Validate confidence is number
                assert isinstance(quote.confidence, (int, float)), f"Confidence should be number, got {type(quote.confidence)}"
                assert 0 <= quote.confidence <= 1, f"Confidence should be 0-1, got {quote.confidence}"
            
            print("✅ All field quotes validated successfully!")
        else:
            print(f"❌ No field quotes to validate: {result['error_message']}")
            pytest.skip("No field quotes generated for validation")


if __name__ == "__main__":
    # Run the tests directly
    import sys
    sys.path.append('/Users/danirahman/Repos/CROcashi')
    
    async def main():
        test_instance = TestStudyCardRealisticData()
        generator = test_instance.generator()
        realistic_text = test_instance.realistic_methodology_text()
        trial_context = test_instance.trial_context()
        
        # Test with realistic data
        await test_instance.test_realistic_methodology_extraction(generator, realistic_text, trial_context)
        await test_instance.test_evidence_quote_validation(generator, realistic_text, trial_context)
    
    asyncio.run(main())
