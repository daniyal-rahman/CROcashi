"""
Unit tests for EntityPack methods.

Tests the new get_must_link_terms() and get_cannot_link_terms() methods
to ensure they work correctly with PolicyEngine and Guardrails.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.ncfd.entities.schema import EntityPack, CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo, RegistryInfo, PublisherInfo, DateRangeInfo


def test_entity_pack_methods():
    """Test EntityPack methods for terms extraction."""
    
    # Test 1: Basic must-link terms
    entity_pack = EntityPack(
        entity_id='test_trial',
        company=CompanyInfo(canonical='Test Company', aliases=['TC', 'TestCorp']),
        asset=AssetInfo(canonical='test_drug', aliases=['TD', 'TestDrug']),
        mechanism=MechanismInfo(targets=['target1', 'target2']),
        indications=IndicationInfo(primary=['Disease A'], synonyms=['Illness A', 'Condition A']),
        registries=RegistryInfo(nct_ids=['NCT123456', 'NCT789012']),
        publishers=PublisherInfo(sponsor_strings=['Test Company Inc']),
        date_ranges=DateRangeInfo(active_since=2020)
    )
    
    must_link_terms = entity_pack.get_must_link_terms()
    
    # Should include all asset terms
    assert 'test_drug' in must_link_terms
    assert 'TD' in must_link_terms
    assert 'TestDrug' in must_link_terms
    
    # Should include all company terms
    assert 'Test Company' in must_link_terms
    assert 'TC' in must_link_terms
    assert 'TestCorp' in must_link_terms
    
    # Should include all NCT IDs
    assert 'NCT123456' in must_link_terms
    assert 'NCT789012' in must_link_terms
    
    # Should include indication terms
    assert 'Disease A' in must_link_terms
    assert 'Illness A' in must_link_terms
    assert 'Condition A' in must_link_terms
    
    # Should include mechanism targets
    assert 'target1' in must_link_terms
    assert 'target2' in must_link_terms
    
    # Should not include publisher strings (not typically used for must-link)
    assert 'Test Company Inc' not in must_link_terms
    
    # Verify we have the expected number of terms
    expected_count = 3 + 3 + 2 + 3 + 2  # asset + company + nct + indication + mechanism
    assert len(must_link_terms) == expected_count
    
    # Test 2: Should-link terms
    should_link_terms = entity_pack.get_should_link_terms()
    
    # Should include general clinical trial terms
    assert 'clinical trial' in should_link_terms
    assert 'randomized' in should_link_terms
    assert 'placebo' in should_link_terms
    assert 'efficacy' in should_link_terms
    assert 'safety' in should_link_terms
    assert 'endpoint' in should_link_terms
    
    # Should include indication-related terms (Alzheimer example)
    alzheimer_pack = EntityPack(
        entity_id='alzheimer_test',
        company=CompanyInfo(canonical='Test Company', aliases=[]),
        asset=AssetInfo(canonical='test_drug', aliases=[]),
        mechanism=MechanismInfo(targets=[]),
        indications=IndicationInfo(primary=['Alzheimer Disease'], synonyms=[]),
        registries=RegistryInfo(nct_ids=[]),
        publishers=PublisherInfo(sponsor_strings=[]),
        date_ranges=DateRangeInfo(active_since=2020)
    )
    
    alzheimer_should_terms = alzheimer_pack.get_should_link_terms()
    assert 'dementia' in alzheimer_should_terms
    assert 'cognitive' in alzheimer_should_terms
    assert 'memory' in alzheimer_should_terms
    assert 'neurodegenerative' in alzheimer_should_terms
    
    # Verify we have a reasonable number of should-link terms (at least the general clinical trial terms)
    assert len(should_link_terms) >= 10
    
    # Test 3: Cannot-link terms
    cannot_link_terms = entity_pack.get_cannot_link_terms()
    
    # Should include common oncology terms
    assert 'cancer' in cannot_link_terms
    assert 'tumor' in cannot_link_terms
    assert 'carcinoma' in cannot_link_terms
    assert 'oncology' in cannot_link_terms
    assert 'chemotherapy' in cannot_link_terms
    assert 'metastasis' in cannot_link_terms
    
    # Should not include non-oncology terms
    assert 'alzheimer' not in cannot_link_terms
    assert 'diabetes' not in cannot_link_terms
    assert 'hypertension' not in cannot_link_terms
    
    # Verify we have a reasonable number of oncology terms
    assert len(cannot_link_terms) >= 15
    
    # Test 4: Simufilam example
    simufilam_pack = EntityPack(
        entity_id='simufilam_trial',
        company=CompanyInfo(canonical='Cassava Sciences', aliases=['Cassava', 'CS']),
        asset=AssetInfo(canonical='simufilam', aliases=['PTI-125', 'PTI125']),
        mechanism=MechanismInfo(targets=['filamin A', 'FLNA', 'amyloid-beta']),
        indications=IndicationInfo(primary=['Alzheimer Disease'], synonyms=['AD', 'Alzheimer']),
        registries=RegistryInfo(nct_ids=['NCT123456']),
        publishers=PublisherInfo(sponsor_strings=['Cassava Sciences Inc']),
        date_ranges=DateRangeInfo(active_since=2020)
    )
    
    simufilam_terms = simufilam_pack.get_must_link_terms()
    expected_terms = ['simufilam', 'PTI-125', 'PTI125', 'Cassava Sciences', 'Cassava', 'CS', 'NCT123456', 'Alzheimer Disease', 'AD', 'Alzheimer', 'filamin A', 'FLNA', 'amyloid-beta']
    
    for term in expected_terms:
        assert term in simufilam_terms, f"Expected term '{term}' not found in must_link_terms"
    
    # Verify no unexpected terms
    assert 'Cassava Sciences Inc' not in simufilam_terms  # publisher string
    
    # Verify count
    assert len(simufilam_terms) == len(expected_terms)
    
    print("✅ All EntityPack method tests passed!")


if __name__ == '__main__':
    test_entity_pack_methods()