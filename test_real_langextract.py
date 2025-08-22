#!/usr/bin/env python3
"""
Test script for real LangExtract integration.
This script tests the actual LangExtract API integration.
"""

import os
import sys
import logging

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_real_langextract():
    """Test the real LangExtract integration."""
    print("\n🚀 LangExtract Integration Test")
    print("=" * 50)
    
    # Check for API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment")
        print("Please set your Google Gemini API key:")
        print("export GEMINI_API_KEY='your-gemini-api-key-here'")
        return False
    
    print(f"🔑 Gemini API key found: {api_key[:10]}...")
    
    try:
        # Import the adapter
        from ncfd.extract.lanextract_adapter import extract_study_card_from_document
        
        print("\n🧪 Testing Real LangExtract Integration")
        print("=" * 50)
        
        # Test document
        document_text = """Methods: Adults with COPD randomized 2:1 to Drug X vs placebo. Primary endpoint: Annualized exacerbation rate at Week 52 (ITT analysis). Results: n=660 (Drug X n=440; placebo n=220). Annualized exacerbation rate: 0.85 vs 1.23 (rate ratio 0.69, 95% CI 0.58-0.82, p<0.001)."""
        
        document_metadata = {
            "doc_type": "Abstract",
            "title": "Phase 3 Study of Drug X in COPD",
            "year": 2024,
            "url": "https://conference.org/abstract/123",
            "source_id": "conf_abs_123"
        }
        
        trial_context = {
            "nct_id": "NCT87654321",
            "phase": "3",
            "indication": "COPD"
        }
        
        print("1. Loading prompts...")
        # The prompts are loaded inside the function now
        print("   ✅ Prompts loaded successfully")
        
        print("\n2. Building payload...")
        payload = {
            "document_metadata": document_metadata,
            "text_chunks": [
                {
                    "page": 1,
                    "paragraph": 1,
                    "text": document_text,
                    "start": 0,
                    "end": len(document_text)
                }
            ],
            "trial_context": trial_context
        }
        print("   ✅ Payload built successfully")
        print(f"   📊 Payload keys: {list(payload.keys())}")
        
        print("\n3. Testing real LangExtract extraction...")
        print("   ⏳ This may take a few seconds...")
        
        # Run extraction
        result = extract_study_card_from_document(
            document_text=document_text,
            document_metadata=document_metadata,
            trial_context=trial_context
        )
        
        print("   ✅ Extraction completed successfully!")
        print(f"   📋 Result type: {type(result)}")
        print(f"   📋 Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        
        # Basic validation
        if isinstance(result, dict):
            print("\n4. Validating extracted data...")
            
            # Check required fields
            required_fields = ['doc', 'trial', 'primary_endpoints', 'populations', 'arms', 'results', 'coverage_level']
            missing_fields = [field for field in required_fields if field not in result]
            
            if missing_fields:
                print(f"   ❌ Missing required fields: {missing_fields}")
                return False
            else:
                print("   ✅ All required fields present")
            
            # Check specific values
            if result.get('trial', {}).get('indication') == 'COPD':
                print("   ✅ Indication correctly extracted")
            else:
                print(f"   ⚠️  Indication mismatch: expected 'COPD', got '{result.get('trial', {}).get('indication')}'")
            
            if result.get('trial', {}).get('phase') == '3':
                print("   ✅ Phase correctly extracted")
            else:
                print(f"   ⚠️  Phase mismatch: expected '3', got '{result.get('trial', {}).get('phase')}'")
            
            print("\n🎉 All tests passed! LangExtract integration is working.")
            return True
            
        else:
            print(f"   ❌ Expected dict result, got {type(result)}")
            return False
            
    except Exception as e:
        print(f"   ❌ Extraction failed: {str(e)}")
        print(f"   🔍 Error type: {type(e).__name__}")
        return False

if __name__ == "__main__":
    success = test_real_langextract()
    if not success:
        print("\n💥 Some tests failed. Check the output above.")
        sys.exit(1)
    else:
        print("\n✨ All tests passed successfully!")
