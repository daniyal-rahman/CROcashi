"""
Test Analysis Claim Extractor functionality.
"""

import pytest
from src.ncfd.extract.generators.analysis_claim_extractor import AnalysisClaimExtractor


def test_extract_regex_hints():
    """Test regex hint extraction."""
    extractor = AnalysisClaimExtractor()
    
    text = """
    In mild AD patients (MMSE ≥20), nominal p=0.041 was observed.
    Post-hoc analysis showed significant results in the per-protocol population.
    Interaction p=0.29 was not significant.
    """
    
    hints = extractor.extract_regex_hints(text)
    
    assert len(hints.p_values) > 0
    assert len(hints.nominal_phrases) > 0
    assert len(hints.post_hoc_phrases) > 0
    assert len(hints.subgroup_cues) > 0
    assert len(hints.analysis_sets) > 0
    assert len(hints.interaction_tests) > 0


def test_s3_signal_with_analysis_claims():
    """Test S3 signal with analysis claims."""
    from src.ncfd.signals.primitives import S3_subgroup_only_no_multiplicity
    
    # Mock analysis claims data
    card = {
        'analysis_claims': [
            {
                'overall_result': {'effect': 'NS', 'p_value': 0.23},
                'subgroup': {'label': 'Mild AD (MMSE ≥20)', 'prespecified': False},
                'subgroup_result': {'p_value': 0.041, 'adjusted': False, 'is_nominal': True, 'effect': 'FavoursTx'},
                'analysis_set': 'ITT',
                'source_id': 'doc_1'
            }
        ]
    }
    
    result = S3_subgroup_only_no_multiplicity(card)
    
    assert result.fired == True
    assert result.severity == "M"
    assert "Mild AD" in result.reason


def test_s3_signal_no_claims():
    """Test S3 signal with no analysis claims."""
    from src.ncfd.signals.primitives import S3_subgroup_only_no_multiplicity
    
    card = {'analysis_claims': []}
    
    result = S3_subgroup_only_no_multiplicity(card)
    
    assert result.fired == False
    assert result.reason == "No subgroup-only wins detected"


def test_g2_gate_logic():
    """Test G2 gate with S3 and nominal patterns."""
    from src.ncfd.signals.gates import _evaluate_g2
    from src.ncfd.signals.primitives import SignalResult
    
    # Mock fired signals
    fired_signals = {
        'S3': SignalResult(
            fired=True,
            severity="M",
            reason="Subgroup-only wins detected: Mild AD",
            evidence_ids=["doc_1_nominal"]
        ),
        'S4': SignalResult(fired=False, severity="L", reason="No S4")
    }
    
    result = _evaluate_g2(fired_signals)
    
    assert result.fired == True
    assert result.gate_id == "G2"
    assert "S3" in result.supporting_signals
    assert result.lr_used == 6.0


if __name__ == "__main__":
    pytest.main([__file__])
