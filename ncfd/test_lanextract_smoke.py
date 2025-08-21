#!/usr/bin/env python3
"""
Smoke test for LangExtract adapter
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_lanextract_import():
    """Test that the lanextract adapter can be imported."""
    try:
        from ncfd.extract.lanextract_adapter import (
            MockGeminiClient,
            load_prompts,
            build_payload,
            run_langextract,
            extract_study_card_from_document
        )
        print("✅ LangExtract adapter imported successfully")
        return True
    except Exception as e:
        print(f"❌ LangExtract adapter import failed: {e}")
        return False

def test_mock_gemini_client():
    """Test the mock Gemini client."""
    try:
        from ncfd.extract.lanextract_adapter import MockGeminiClient
        
        client = MockGeminiClient()
        print(f"✅ Mock Gemini client created: {client.model_name}")
        
        # Test JSON generation
        prompt = "Generate a study card"
        response = client.generate_json(prompt)
        
        # Verify response is valid JSON
        card = json.loads(response)
        assert "doc" in card, "Response should contain 'doc' field"
        assert "trial" in card, "Response should contain 'trial' field"
        
        print("✅ Mock Gemini client generates valid JSON")
        return True
        
    except Exception as e:
        print(f"❌ Mock Gemini client test failed: {e}")
        return False

def test_prompt_loading():
    """Test that prompts can be loaded."""
    try:
        from ncfd.extract.lanextract_adapter import load_prompts
        
        prompts = load_prompts()
        assert "Study Card" in prompts, "Prompts should contain 'Study Card'"
        assert "coverage_level" in prompts, "Prompts should contain coverage information"
        
        print("✅ Prompts loaded successfully")
        print(f"   Length: {len(prompts)} characters")
        return True
        
    except Exception as e:
        print(f"❌ Prompt loading failed: {e}")
        return False

def test_payload_building():
    """Test payload building functionality."""
    try:
        from ncfd.extract.lanextract_adapter import build_payload
        
        doc_meta = {
            "doc_type": "Abstract",
            "title": "Test Study",
            "year": 2024,
            "url": "https://test.com",
            "source_id": "test_001"
        }
        
        chunks = [
            {
                "page": 1,
                "paragraph": 1,
                "start": 0,
                "end": 100,
                "text": "Sample text"
            }
        ]
        
        trial_hint = {
            "nct_id": "NCT12345678",
            "phase": "3",
            "indication": "Test Indication"
        }
        
        payload = build_payload(doc_meta, chunks, trial_hint)
        
        assert "doc" in payload, "Payload should contain 'doc'"
        assert "chunks" in payload, "Payload should contain 'chunks'"
        assert "trial_hint" in payload, "Payload should contain 'trial_hint'"
        assert len(payload["chunks"]) == 1, "Payload should have 1 chunk"
        
        print("✅ Payload building working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Payload building failed: {e}")
        return False

def test_end_to_end_extraction():
    """Test the complete study card extraction workflow."""
    try:
        from ncfd.extract.lanextract_adapter import extract_study_card_from_document
        
        # Test data
        doc_meta = {
            "doc_type": "Abstract",
            "title": "Test Study Results",
            "year": 2024,
            "url": "https://test.com/study",
            "source_id": "test_002"
        }
        
        chunks = [
            {
                "page": 1,
                "paragraph": 1,
                "start": 0,
                "end": 200,
                "text": "This study enrolled 200 patients and showed significant results."
            }
        ]
        
        trial_hint = {
            "nct_id": "NCT87654321",
            "phase": "3",
            "indication": "Test Disease"
        }
        
        # Extract study card
        card = extract_study_card_from_document(doc_meta, chunks, trial_hint)
        
        # Verify the card structure
        assert "doc" in card, "Card should contain 'doc'"
        assert "trial" in card, "Card should contain 'trial'"
        assert "coverage_level" in card, "Card should contain 'coverage_level'"
        assert card["coverage_level"] in ["high", "med", "low"], "Coverage level should be valid"
        
        print("✅ End-to-end extraction working correctly")
        print(f"   Coverage level: {card['coverage_level']}")
        return True
        
    except Exception as e:
        print(f"❌ End-to-end extraction failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing LangExtract Adapter")
    print("=" * 40)
    
    tests = [
        test_lanextract_import,
        test_mock_gemini_client,
        test_prompt_loading,
        test_payload_building,
        test_end_to_end_extraction
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All LangExtract adapter tests passed!")
        sys.exit(0)
    else:
        print("❌ Some LangExtract adapter tests failed!")
        sys.exit(1)
