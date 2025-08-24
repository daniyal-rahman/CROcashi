#!/usr/bin/env python3
"""
Test script for study card generation using OpenAI API directly.
This bypasses LangExtract to test if the issue is with the library or the API.
"""

import os
import sys
import json
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai import OpenAI
from ncfd.extract.validator import validate_card

def test_openai_direct():
    """Test study card generation using OpenAI API directly."""
    print("🚀 Testing OpenAI API Direct Integration")
    print("=" * 70)
    
    # Check if required environment variables are set
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment")
        return False
    
    print(f"✅ OpenAI API key found: {api_key[:10]}...")
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Test document content
    doc_content = """
    Novartis Reports Positive Results from Atrasentan Phase 2 Trial
    
    Basel, Switzerland - Novartis today announced positive results from a Phase 2 study 
    evaluating Atrasentan in patients with proteinuric glomerular diseases.
    
    The study met its primary endpoint with a statistically significant reduction in 
    proteinuria of 45.2% compared to baseline (p<0.001). The trial enrolled 120 patients 
    and demonstrated a favorable safety profile with no serious adverse events.
    
    "These results support the potential of Atrasentan as a novel treatment for patients 
    with proteinuric glomerular diseases," said Dr. John Smith, Head of Development.
    
    The company plans to initiate Phase 3 development in 2025.
    """
    
    # Create the prompt for study card extraction
    prompt = f"""
    Extract a study card from the following clinical trial document. 
    Return only valid JSON that matches the study card schema.
    
    Document:
    {doc_content}
    
    Extract all available information including:
    - Document metadata
    - Trial information (phase, indication, etc.)
    - Primary endpoints with evidence
    - Results with effect sizes and p-values
    - Sample sizes and populations
    - Any limitations or missing information
    
    Return only the JSON object, no other text.
    """
    
    try:
        print("📤 Sending request to OpenAI...")
        
        # Call OpenAI API directly
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a clinical trial data extraction specialist. Extract structured study information and return only valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        # Extract the response content
        study_card_text = response.choices[0].message.content.strip()
        
        print("📥 Received response from OpenAI")
        print(f"Response length: {len(study_card_text)} characters")
        
        # Try to parse as JSON
        try:
            study_card = json.loads(study_card_text)
            print("✅ Successfully parsed JSON response")
            
            # Validate against schema
            try:
                validate_card(study_card, is_pivotal=False)
                print("✅ Study card validation passed")
                
                # Show key extracted information
                print(f"\n🎯 Extracted Study Card:")
                print(f"   - Document: {study_card.get('doc', {}).get('title', 'N/A')}")
                print(f"   - Trial Phase: {study_card.get('trial', {}).get('phase', 'N/A')}")
                print(f"   - Indication: {study_card.get('trial', {}).get('indication', 'N/A')}")
                
                if 'results' in study_card and 'primary' in study_card['results']:
                    primary_results = study_card['results']['primary']
                    if primary_results:
                        result = primary_results[0]
                        print(f"   - Primary Endpoint: {result.get('endpoint', 'N/A')}")
                        if 'effect_size' in result and result['effect_size']:
                            effect = result['effect_size']
                            print(f"   - Effect Size: {effect.get('value', 'N/A')} {effect.get('metric', '')}")
                        if 'p_value' in result:
                            print(f"   - P-value: {result['p_value']}")
                
                print(f"   - Coverage Level: {study_card.get('coverage_level', 'N/A')}")
                
                # Save to file for inspection
                output_file = "openai_direct_study_card.json"
                with open(output_file, 'w') as f:
                    json.dump(study_card, f, indent=2)
                print(f"\n💾 Study card saved to: {output_file}")
                
                return True
                
            except Exception as validation_error:
                print(f"❌ Study card validation failed: {validation_error}")
                return False
                
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON response: {e}")
            print(f"Raw response: {study_card_text[:500]}...")
            return False
            
    except Exception as e:
        print(f"❌ OpenAI API call failed: {e}")
        return False

def main():
    """Main test execution."""
    print("🧪 OpenAI Direct API Integration Test")
    print("=" * 70)
    
    # Run the test
    success = test_openai_direct()
    
    if success:
        print("\n🎉 Test completed successfully!")
        print("   OpenAI API integration is working directly.")
        print("   The issue is with LangExtract library compatibility.")
    else:
        print("\n❌ Test failed!")
        print("   Check the error messages above for issues.")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
