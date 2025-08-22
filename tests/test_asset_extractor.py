"""
Smoke tests for asset extractor module.

These tests verify that the asset extraction functionality works correctly
without requiring a database connection.
"""

import pytest
from ncfd.extract.asset_extractor import (
    norm_drug_name, extract_asset_codes, extract_nct_ids,
    find_nearby_assets, AssetMatch, get_confidence_for_link_type
)


class TestAssetExtractor:
    """Test asset extraction functionality."""
    
    def test_norm_drug_name_basic(self):
        """Test basic drug name normalization."""
        # Test Greek letter expansion
        assert norm_drug_name("α-Tocopherol") == "alpha-tocopherol"
        assert norm_drug_name("β-Carotene") == "beta-carotene"
        assert norm_drug_name("γ-Aminobutyric Acid") == "gamma-aminobutyric acid"
        
        # Test trademark symbol stripping
        assert norm_drug_name("AB-123®") == "ab-123"
        assert norm_drug_name("XYZ-456™") == "xyz-456"
        assert norm_drug_name("Drug Name©") == "drug name"
        
        # Test space normalization
        assert norm_drug_name("  Multiple    Spaces  ") == "multiple spaces"
        
        # Test case normalization
        assert norm_drug_name("MixedCase") == "mixedcase"
    
    def test_norm_drug_name_edge_cases(self):
        """Test edge cases in drug name normalization."""
        # Empty string
        assert norm_drug_name("") == ""
        assert norm_drug_name(None) == ""
        
        # Special characters
        assert norm_drug_name("Drug-Name/With\\Special:Chars") == "drug-name/with\\special:chars"
        
        # Numbers and symbols
        assert norm_drug_name("Drug123!@#$%") == "drug123!@#$%"
    
    def test_extract_asset_codes(self):
        """Test asset code extraction patterns."""
        test_text = """
        Our lead compound AB-123 showed promising results.
        We also tested XYZ-456 and BMS-AA-001.
        The combination with AB123X was effective.
        """
        
        matches = extract_asset_codes(test_text)
        
        # Should find all expected codes
        expected_codes = ["AB-123", "XYZ-456", "BMS-AA-001", "AB123X"]
        found_codes = [match.value_text for match in matches]
        
        for code in expected_codes:
            assert code in found_codes, f"Expected code {code} not found"
        
        # Check that both hyphenated and collapsed forms are created for AB-123
        ab_codes = [m for m in matches if "AB" in m.value_text]
        assert len(ab_codes) >= 2, "Should create both AB-123 and AB123 forms"
        
        # Verify all matches have correct properties
        for match in matches:
            assert match.alias_type == "code"
            assert match.detector == "regex"
            assert match.confidence == 1.0
            assert match.page_no == 1  # Default page number
    
    def test_extract_nct_ids(self):
        """Test NCT ID extraction."""
        test_text = """
        The trial NCT12345678 enrolled 100 patients.
        We also referenced NCT87654321 in our analysis.
        """
        
        matches = extract_nct_ids(test_text)
        
        # Should find both NCT IDs
        expected_ncts = ["NCT12345678", "NCT87654321"]
        found_ncts = [match.value_norm for match in matches]
        
        for nct in expected_ncts:
            assert nct in found_ncts, f"Expected NCT {nct} not found"
        
        # Verify match properties
        for match in matches:
            assert match.alias_type == "nct"
            assert match.detector == "regex"
            assert match.confidence == 1.0
            assert match.value_norm == match.value_text.upper()
    
    def test_find_nearby_assets(self):
        """Test nearby asset detection (HP-1 heuristic)."""
        # Create test asset matches
        asset_matches = [
            AssetMatch("AB-123", "AB-123", "code", 1, 100, 106, "regex"),
            AssetMatch("XYZ-456", "XYZ-456", "code", 1, 200, 206, "regex"),
        ]
        
        nct_matches = [
            AssetMatch("NCT12345678", "NCT12345678", "nct", 1, 150, 158, "regex"),
            AssetMatch("NCT87654321", "NCT87654321", "nct", 2, 300, 308, "regex"),  # Different page
        ]
        
        # Test with default window size (250 chars)
        nearby_pairs = find_nearby_assets(asset_matches, nct_matches)
        
        # AB-123 should be near NCT12345678 (distance = 50 chars)
        # XYZ-456 should be near NCT12345678 (distance = 50 chars)
        # NCT87654321 is on different page, so no matches
        assert len(nearby_pairs) == 2, f"Expected 2 nearby pairs, got {len(nearby_pairs)}"
        
        # Verify the pairs
        asset_texts = [pair[0].value_text for pair in nearby_pairs]
        nct_texts = [pair[1].value_text for pair in nearby_pairs]
        
        assert "AB-123" in asset_texts
        assert "XYZ-456" in asset_texts
        assert "NCT12345678" in nct_texts
    
    def test_find_nearby_assets_different_pages(self):
        """Test that assets on different pages don't match."""
        asset_matches = [
            AssetMatch("AB-123", "AB-123", "code", 1, 100, 106, "regex"),
        ]
        
        nct_matches = [
            AssetMatch("NCT12345678", "NCT12345678", "nct", 2, 150, 158, "regex"),  # Different page
        ]
        
        nearby_pairs = find_nearby_assets(asset_matches, nct_matches)
        assert len(nearby_pairs) == 0, "Assets on different pages should not match"
    
    def test_find_nearby_assets_large_distance(self):
        """Test that assets beyond window size don't match."""
        asset_matches = [
            AssetMatch("AB-123", "AB-123", "code", 1, 100, 106, "regex"),
        ]
        
        nct_matches = [
            AssetMatch("NCT12345678", "NCT12345678", "nct", 1, 500, 508, "regex"),  # 400 chars away
        ]
        
        nearby_pairs = find_nearby_assets(asset_matches, nct_matches, window_size=250)
        assert len(nearby_pairs) == 0, "Assets beyond window size should not match"
    
    def test_get_confidence_for_link_type(self):
        """Test confidence scoring for different link types."""
        # Test known link types
        assert get_confidence_for_link_type('nct_near_asset') == 1.00
        assert get_confidence_for_link_type('code_in_text') == 0.90
        assert get_confidence_for_link_type('inn_in_text') == 0.85
        assert get_confidence_for_link_type('exact_intervention_match') == 0.95
        
        # Test unknown link type (should return base confidence)
        assert get_confidence_for_link_type('unknown_type') == 1.0
        assert get_confidence_for_link_type('unknown_type', base_confidence=0.5) == 0.5
    
    def test_asset_match_dataclass(self):
        """Test AssetMatch dataclass functionality."""
        match = AssetMatch(
            value_text="AB-123",
            value_norm="AB-123",
            alias_type="code",
            page_no=1,
            char_start=100,
            char_end=106,
            detector="regex",
            confidence=0.95
        )
        
        assert match.value_text == "AB-123"
        assert match.value_norm == "AB-123"
        assert match.alias_type == "code"
        assert match.page_no == 1
        assert match.char_start == 100
        assert match.char_end == 106
        assert match.detector == "regex"
        assert match.confidence == 0.95
    
    def test_asset_match_default_confidence(self):
        """Test that AssetMatch has default confidence of 1.0."""
        match = AssetMatch(
            value_text="AB-123",
            value_norm="AB-123",
            alias_type="code",
            page_no=1,
            char_start=100,
            char_end=106,
            detector="regex"
        )
        
        assert match.confidence == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
