#!/usr/bin/env python3
"""
Test script for study card generation using Gemini (LangExtract).
This tests the Gemini integration with the flash model.
"""

import os
import sys
import json
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ncfd.extract.lanextract_adapter import extract_study_card_from_document
from ncfd.extract.validator import validate_card

def test_study_card_generation_gemini():
    """Test study card generation using Gemini."""
    print("🚀 Testing Gemini Study Card Generation")
    print("=" * 70)
    
    # Check if required environment variables are set
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("❌ GEMINI_API_KEY not found in environment")
        return False
    
    print("✅ GEMINI_API_KEY found")
    
    # Test with a simplified document focusing on key trial information
    document_content = {
        "document_metadata": {
            "doc_type": "PR",
            "title": "Novartis Reports Positive Results from Atrasentan Phase 2 Trial",
            "year": 2024,
            "url": "https://example.com/pr/67890",
            "source_id": "NOVARTIS_PR_67890"
        },
        "text_chunks": [
            {
                "page": 1,
                "paragraph": 1,
                "text": "Novartis Reports Positive Results from Atrasentan Phase 2 Trial\n\nBasel, Switzerland - Novartis today announced positive results from a Phase 2 study evaluating Atrasentan in patients with proteinuric glomerular diseases.\n\nThe study met its primary endpoint with a statistically significant reduction in proteinuria of 45.2% compared to baseline (p<0.001). The trial enrolled 120 patients and demonstrated a favorable safety profile with no serious adverse events.\n\nThe study included two treatment arms: Atrasentan 0.75 mg once daily and placebo. Patients were randomized 1:1 and treated for 12 weeks.\n\nThe primary endpoint was percent change in proteinuria from baseline to week 12. The study demonstrated a 45.2% reduction in proteinuria compared to baseline (p<0.001).\n\nA total of 120 patients were enrolled in the study. The treatment was well-tolerated with no serious adverse events reported.",
                "start": 0,
                "end": 1000
            }
        ],
        "trial_context": {
            "nct_id": "NCT04573920",
            "phase": "PHASE2",
            "indication": "Proteinuric Glomerular Diseases",
            "is_pivotal": False
        }
    }
    
    print("📄 Document content prepared:")
    print(f"  - Title: {document_content['document_metadata']['title']}")
    print(f"  - Type: {document_content['document_metadata']['doc_type']}")
    print(f"  - Trial: {document_content['trial_context']['nct_id']}")
    print(f"  - Phase: {document_content['trial_context']['phase']}")
    print(f"  - Text length: {len(document_content['text_chunks'][0]['text'])} characters")
    
    try:
        # Extract study card using Gemini
        print("\n🔍 Extracting study card...")
        study_card = extract_study_card_from_document(
            document_text=document_content['text_chunks'][0]['text'],
            document_metadata=document_content['document_metadata'],
            trial_context=document_content['trial_context']
        )
        
        if study_card:
            print("✅ Study card extracted successfully!")
            print(f"📊 Coverage level: {study_card.get('coverage_level', 'unknown')}")
            print(f"🎯 Primary endpoints: {len(study_card.get('primary_endpoints', []))}")
            print(f"👥 Sample size: {study_card.get('sample_size', {}).get('total_n', 'unknown')}")
            print(f"📈 Results: {len(study_card.get('results', {}).get('primary', []))}")
            
            # Validate the study card
            print("\n🔍 Validating study card...")
            validation_result = validate_card(study_card)
            
            if validation_result.is_valid:
                print("✅ Study card validation passed!")
                print(f"📋 Missing fields: {len(validation_result.missing_fields)}")
                if validation_result.missing_fields:
                    print(f"   - {', '.join(validation_result.missing_fields[:5])}")
                    if len(validation_result.missing_fields) > 5:
                        print(f"   - ... and {len(validation_result.missing_fields) - 5} more")
            else:
                print("❌ Study card validation failed:")
                for error in validation_result.errors:
                    print(f"   - {error}")
            
            return True
        else:
            print("❌ Failed to extract study card")
            return False
            
    except Exception as e:
        print(f"❌ Gemini study card generation failed: {e}")
        return False

def main():
    """Main test execution."""
    print("🧪 Gemini Integration Test")
    print("=" * 70)
    
    # Run the test
    success = test_study_card_generation_gemini()
    
    if success:
        print("\n🎉 Test completed successfully!")
        print("   Gemini integration is working with the flash model.")
    else:
        print("\n❌ Test failed!")
        print("   Check the error messages above for issues.")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
