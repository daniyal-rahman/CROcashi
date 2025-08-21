#!/usr/bin/env python3
"""
Simple test for asset extractor module only.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_asset_extractor():
    """Test asset extractor functionality."""
    print("Testing asset extractor...")
    
    try:
        from ncfd.extract.asset_extractor import (
            norm_drug_name, extract_asset_codes, extract_nct_ids,
            find_nearby_assets, AssetMatch, get_confidence_for_link_type
        )
        
        # Test drug name normalization
        print(f"Testing 'α-Tocopherol' -> '{norm_drug_name('α-Tocopherol')}'")
        assert norm_drug_name("α-Tocopherol") == "alpha-tocopherol"
        
        print(f"Testing 'β-Carotene' -> '{norm_drug_name('β-Carotene')}'")
        assert norm_drug_name("β-Carotene") == "beta-carotene"
        
        print(f"Testing 'AB-123®' -> '{norm_drug_name('AB-123®')}'")
        assert norm_drug_name("AB-123®") == "ab-123"
        
        print("  ✅ Drug name normalization: PASSED")
        
        # Test asset code extraction
        test_text = "Our lead compound AB-123 showed promising results with XYZ-456."
        matches = extract_asset_codes(test_text)
        expected_codes = ["AB-123", "XYZ-456"]
        found_codes = [match.value_text for match in matches]
        
        print(f"Found codes: {found_codes}")
        for code in expected_codes:
            assert code in found_codes, f"Expected code {code} not found"
        print("  ✅ Asset code extraction: PASSED")
        
        # Test NCT ID extraction
        test_text = "The trial NCT12345678 enrolled 100 patients."
        matches = extract_nct_ids(test_text)
        assert len(matches) == 1
        assert matches[0].value_norm == "NCT12345678"
        print("  ✅ NCT ID extraction: PASSED")
        
        # Test nearby asset detection
        asset_matches = [
            AssetMatch("AB-123", "AB-123", "code", 1, 100, 106, "regex"),
        ]
        nct_matches = [
            AssetMatch("NCT12345678", "NCT12345678", "nct", 1, 150, 158, "regex"),
        ]
        nearby_pairs = find_nearby_assets(asset_matches, nct_matches)
        assert len(nearby_pairs) == 1
        print("  ✅ Nearby asset detection: PASSED")
        
        # Test confidence scoring
        assert get_confidence_for_link_type('nct_near_asset') == 1.00
        assert get_confidence_for_link_type('code_in_text') == 0.90
        print("  ✅ Confidence scoring: PASSED")
        
        print("  🎉 All asset extractor tests passed!")
        return True
        
    except Exception as e:
        print(f"  ❌ Asset extractor tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_asset_extractor()
    if success:
        print("\n🎉 SUCCESS: Asset extractor is working correctly!")
        sys.exit(0)
    else:
        print("\n❌ FAILURE: Asset extractor has issues!")
        sys.exit(1)
