#!/usr/bin/env python3
"""
Test script for literature pulling and study card generation using OpenAI.
This tests the complete pipeline using the Novartis Atrasentan trial with GPT-4o.
"""

import os
import sys
import json
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.extract.lanextract_adapter import StudyCardAdapter, extract_study_card_from_document
from ncfd.extract.validator import validate_card

def simulate_literature_discovery(nct_id: str, drug_name: str) -> list:
    """Simulate discovering literature for a trial."""
    print(f"🔍 Simulating literature discovery for {nct_id} ({drug_name})")
    
    discovered_docs = [
        {
            "doc_type": "Abstract",
            "title": f"Phase 2 Study of {drug_name} in Proteinuric Glomerular Diseases",
            "year": 2024,
            "url": "https://example.com/abstract/12345",
            "source_id": "ASCO2024_12345",
            "publisher": "ASCO Annual Meeting",
            "oa_status": "open"
        },
        {
            "doc_type": "PR",
            "title": f"Novartis Reports Positive Results from {drug_name} Phase 2 Trial",
            "year": 2024,
            "url": "https://example.com/pr/67890",
            "source_id": "NOVARTIS_PR_67890",
            "publisher": "Novartis Press Release",
            "oa_status": "open"
        }
    ]
    
    print(f"   📚 Found {len(discovered_docs)} documents")
    for doc in discovered_docs:
        print(f"      - {doc['doc_type']}: {doc['title'][:60]}...")
    
    return discovered_docs

def simulate_document_content(doc: dict, nct_id: str, drug_name: str) -> str:
    """Simulate document content for testing."""
    if doc["doc_type"] == "Abstract":
        return f"""
        Phase 2 Study of {drug_name} in Proteinuric Glomerular Diseases
        
        Background: Proteinuric glomerular diseases represent a significant unmet medical need.
        
        Methods: This open-label, basket study enrolled 120 patients with proteinuric glomerular diseases.
        Patients received {drug_name} 0.75 mg daily for 12 weeks. Primary endpoint was change in 
        proteinuria from baseline to week 12. Secondary endpoints included eGFR change and safety.
        
        Results: Mean change in proteinuria was -45.2% (95% CI: -52.1% to -38.3%, p<0.001).
        Mean eGFR change was +2.1 mL/min/1.73m². Most common adverse events were peripheral 
        edema (15%) and headache (12%). No serious adverse events were reported.
        
        Conclusion: {drug_name} demonstrated significant proteinuria reduction with acceptable 
        safety profile in patients with proteinuric glomerular diseases.
        """
    
    else:  # PR
        return f"""
        Novartis Reports Positive Results from {drug_name} Phase 2 Trial
        
        Basel, Switzerland - Novartis today announced positive results from a Phase 2 study 
        evaluating {drug_name} in patients with proteinuric glomerular diseases.
        
        The study met its primary endpoint with a statistically significant reduction in 
        proteinuria of 45.2% compared to baseline (p<0.001). The trial enrolled 120 patients 
        and demonstrated a favorable safety profile with no serious adverse events.
        
        "These results support the potential of {drug_name} as a novel treatment for patients 
        with proteinuric glomerular diseases," said Dr. John Smith, Head of Development.
        
        The company plans to initiate Phase 3 development in 2025.
        """

def test_study_card_generation_openai():
    """Test the complete study card generation workflow using OpenAI."""
    print("🚀 Testing Literature Pulling and Study Card Generation (OpenAI)")
    print("=" * 70)
    
    # Test parameters
    nct_id = "NCT04573920"
    drug_name = "Atrasentan"
    trial_context = {
        "nct_id": nct_id,
        "phase": "PHASE2",
        "indication": "Proteinuric Glomerular Diseases",
        "is_pivotal": False
    }
    
    try:
        # Step 1: Simulate literature discovery
        discovered_docs = simulate_literature_discovery(nct_id, drug_name)
        
        # Step 2: Process each document and generate study cards
        study_cards = []
        
        for i, doc in enumerate(discovered_docs):
            print(f"\n📄 Processing document {i+1}/{len(discovered_docs)}: {doc['doc_type']}")
            
            # Simulate document content
            doc_content = simulate_document_content(doc, nct_id, drug_name)
            
            # Prepare document metadata
            doc_metadata = {
                "doc_type": doc["doc_type"],
                "title": doc["title"],
                "year": doc["year"],
                "url": doc["url"],
                "source_id": doc["source_id"]
            }
            
            try:
                # Generate study card using existing LangExtract system
                study_card = extract_study_card_from_document(
                    document_text=doc_content,
                    document_metadata=doc_metadata,
                    trial_context=trial_context
                )
                
                # Validate against schema
                try:
                    validate_card(study_card, is_pivotal=trial_context.get('is_pivotal', False))
                    validation_passed = True
                except Exception as validation_error:
                    validation_passed = False
                    validation_error_msg = str(validation_error)
                
                if validation_passed:
                    print(f"   ✅ Study card generated successfully")
                    print(f"   📊 Coverage level: {study_card.get('coverage_level', 'unknown')}")
                    
                    # Show key extracted information
                    if 'results' in study_card and 'primary' in study_card['results']:
                        primary_results = study_card['results']['primary']
                        if primary_results:
                            result = primary_results[0]
                            print(f"   🎯 Primary endpoint: {result.get('endpoint', 'N/A')}")
                            if 'effect_size' in result:
                                effect = result['effect_size']
                                print(f"   📈 Effect size: {effect.get('value', 'N/A')} {effect.get('metric', '')}")
                            if 'p_value' in result:
                                print(f"   📊 P-value: {result['p_value']}")
                    
                    study_cards.append(study_card)
                else:
                    print(f"   ❌ Study card validation failed: {validation_error_msg}")
                    
            except Exception as e:
                print(f"   ❌ Failed to generate study card: {e}")
                continue
        
        # Step 3: Summary
        print(f"\n📋 Summary")
        print(f"   📚 Documents processed: {len(discovered_docs)}")
        print(f"   ✅ Study cards generated: {len(study_cards)}")
        
        if study_cards:
            print(f"\n🎯 Sample Study Card Structure:")
            sample_card = study_cards[0]
            print(f"   - Document: {sample_card['doc']['title'][:50]}...")
            print(f"   - Trial: {sample_card['trial']['nct_id']} ({sample_card['trial']['phase']})")
            print(f"   - Coverage: {sample_card.get('coverage_level', 'unknown')}")
            
            # Save sample to file for inspection
            output_file = "sample_study_card_openai.json"
            with open(output_file, 'w') as f:
                json.dump(sample_card, f, indent=2)
            print(f"   💾 Sample study card saved to: {output_file}")
        
        return len(study_cards) > 0
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def main():
    """Main test execution."""
    print("🧪 Literature Pulling and Study Card Generation Test (OpenAI)")
    print("=" * 70)
    
    # Check if required environment variables are set
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment")
        return False
    
    print(f"✅ OpenAI API key found: {api_key[:10]}...")
    
    # Run the test
    success = test_study_card_generation_openai()
    
    if success:
        print("\n🎉 Test completed successfully!")
        print("   The literature pulling and study card generation pipeline is working with OpenAI.")
        print("   Next steps: Create database tables and integrate with CT.gov pipeline.")
    else:
        print("\n❌ Test failed!")
        print("   Check the error messages above for issues.")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
