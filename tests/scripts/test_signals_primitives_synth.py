"""
Synthetic unit tests for S1-S9 signal primitives.

Tests crafted to trip each signal as specified in phase6.md.
"""

import datetime as dt
from ncfd.signals.primitives import (
    S1_endpoint_changed,
    S2_underpowered_pivotal,
    S3_subgroup_only_no_multiplicity,
    S4_itt_vs_pp_dropout,
    S5_implausible_vs_graveyard,
    S6_many_interims_no_spending,
    S7_single_arm_where_rct_standard,
    S7b_randomized_withdrawal_after_OLE,
    S8_pvalue_cusp_or_heaping,
    S9_os_pfs_contradiction
)
from ncfd.signals.study_card_mapper import build_study_card


def test_S1_trips_on_late_material_change():
    """Test S1 fires on late material endpoint change."""
    pc = dt.date(2026, 1, 1)
    v1 = dict(
        version_id="v1", 
        primary_endpoint_text="PFS at 12 months, superiority, blinded",
        captured_at=dt.date(2025, 1, 1), 
        est_primary_completion_date=pc
    )
    v2 = dict(
        version_id="v2", 
        primary_endpoint_text="Overall Survival at 24 months, superiority, open-label",
        captured_at=dt.date(2025, 10, 5), 
        est_primary_completion_date=pc
    )
    res = S1_endpoint_changed([v1, v2])
    assert res.fired and res.severity == "H"


def test_S1_does_not_fire_on_early_change():
    """Test S1 does not fire on early changes."""
    pc = dt.date(2026, 1, 1)
    v1 = dict(
        version_id="v1", 
        primary_endpoint_text="PFS at 12 months, superiority, blinded",
        captured_at=dt.date(2025, 1, 1), 
        est_primary_completion_date=pc
    )
    v2 = dict(
        version_id="v2", 
        primary_endpoint_text="Overall Survival at 24 months, superiority, open-label",
        captured_at=dt.date(2025, 1, 15),  # Early change
        est_primary_completion_date=pc
    )
    res = S1_endpoint_changed([v1, v2])
    assert not res.fired


def test_S2_underpowered_proportions_low_power():
    """Test S2 fires on underpowered proportions."""
    card = {
        "study_id": "X",
        "is_pivotal": True,
        "primary_type": "proportion",
        "arms": {"t": {"n": 90, "dropout": 0.12}, "c": {"n": 90, "dropout": 0.05}},
        "analysis_plan": {
            "alpha": 0.025, 
            "one_sided": True, 
            "assumed_p_c": 0.20, 
            "assumed_delta_abs": 0.08
        },
        "historical_control_rate": 0.20
    }
    res = S2_underpowered_pivotal(card)
    assert res.fired and res.value < 0.70


def test_S2_underpowered_tte_low_power():
    """Test S2 fires on underpowered time-to-event."""
    card = {
        "study_id": "Y",
        "is_pivotal": True,
        "primary_type": "tte",
        "arms": {"t": {"n": 250, "dropout": 0.10}, "c": {"n": 250, "dropout": 0.09}},
        "analysis_plan": {
            "alpha": 0.05, 
            "two_sided": True, 
            "hr_alt": 0.80, 
            "planned_events": 140, 
            "alloc_ratio": 1.0
        },
    }
    res = S2_underpowered_pivotal(card)
    assert res.fired  # power ~ <0.70 with 140 events @ HR=0.8


def test_S2_does_not_fire_on_non_pivotal():
    """Test S2 does not fire on non-pivotal trials."""
    card = {
        "study_id": "Z",
        "is_pivotal": False,  # Not pivotal
        "primary_type": "proportion",
        "arms": {"t": {"n": 90}, "c": {"n": 90}},
        "analysis_plan": {"alpha": 0.025, "assumed_p_c": 0.20, "assumed_delta_abs": 0.08}
    }
    res = S2_underpowered_pivotal(card)
    assert not res.fired


def test_S3_subgroup_only_no_multiplicity():
    """Test S3 fires on subgroup-only wins without multiplicity control."""
    card = {
        "study_id": "S3",
        "primary_result": {"ITT": {"estimate": 0.02, "p": 0.12}},
        "subgroups": [
            {"name": "Region A", "p": 0.03, "adjusted": False, "pre_specified_interaction": False},
            {"name": "Age<65", "p": 0.20, "adjusted": False, "pre_specified_interaction": False},
        ],
        "narrative_highlights_subgroup": True
    }
    res = S3_subgroup_only_no_multiplicity(card)
    assert res.fired and res.severity == "H"


def test_S3_does_not_fire_on_itt_significant():
    """Test S3 does not fire when ITT is significant."""
    card = {
        "study_id": "S3b",
        "primary_result": {"ITT": {"estimate": 0.15, "p": 0.02}},  # Significant ITT
        "subgroups": [
            {"name": "Region A", "p": 0.03, "adjusted": False, "pre_specified_interaction": False},
        ]
    }
    res = S3_subgroup_only_no_multiplicity(card)
    assert not res.fired


def test_S4_itt_vs_pp_dropout_asymmetry():
    """Test S4 fires on ITT/PP contradiction with dropout asymmetry."""
    card = {
        "study_id": "S4",
        "primary_result": {
            "ITT": {"estimate": 0.00, "p": 0.40},
            "PP": {"estimate": 0.15, "p": 0.02}
        },
        "arms": {"t": {"n": 150, "dropout": 0.22}, "c": {"n": 150, "dropout": 0.06}},
        "endpoint_subjective_unblinded": True
    }
    res = S4_itt_vs_pp_dropout(card)
    assert res.fired and res.severity == "H"


def test_S4_does_not_fire_without_pp():
    """Test S4 does not fire without PP results."""
    card = {
        "study_id": "S4b",
        "primary_result": {
            "ITT": {"estimate": 0.00, "p": 0.40}
            # No PP results
        },
        "arms": {"t": {"n": 150, "dropout": 0.22}, "c": {"n": 150, "dropout": 0.06}}
    }
    res = S4_itt_vs_pp_dropout(card)
    assert not res.fired


def test_S4_does_not_fire_without_dropout_asymmetry():
    """Test S4 does not fire without sufficient dropout asymmetry."""
    card = {
        "study_id": "S4c",
        "primary_result": {
            "ITT": {"estimate": 0.00, "p": 0.40},
            "PP": {"estimate": 0.15, "p": 0.02}
        },
        "arms": {"t": {"n": 150, "dropout": 0.08}, "c": {"n": 150, "dropout": 0.06}},  # Small asymmetry
    }
    res = S4_itt_vs_pp_dropout(card)
    assert not res.fired


def test_S5_implausible_vs_graveyard():
    """Test S5 fires on implausible effect size vs graveyard."""
    card = {
        "study_id": "S5",
        "primary_result": {"ITT": {"estimate": 0.45}},  # Very high effect
        "indication": "metastatic_breast_cancer"
    }
    graveyard_data = {
        "metastatic_breast_cancer": {
            "p95_effect_size": 0.35,
            "p99_effect_size": 0.50
        }
    }
    res = S5_implausible_vs_graveyard(card, graveyard_data)
    assert res.fired and res.severity == "M"


def test_S5_does_not_fire_within_graveyard():
    """Test S5 does not fire when effect size is within graveyard range."""
    card = {
        "study_id": "S5b",
        "primary_result": {"ITT": {"estimate": 0.25}},  # Reasonable effect
        "indication": "metastatic_breast_cancer"
    }
    graveyard_data = {
        "metastatic_breast_cancer": {
            "p95_effect_size": 0.35,
            "p99_effect_size": 0.50
        }
    }
    res = S5_implausible_vs_graveyard(card, graveyard_data)
    assert not res.fired


def test_S6_many_interims_no_spending():
    """Test S6 fires on many interims without alpha spending."""
    card = {
        "study_id": "S6",
        "analysis_plan": {
            "planned_interims": 4,  # Many interims
            # No alpha_spending_function specified
        }
    }
    res = S6_many_interims_no_spending(card)
    assert res.fired and res.severity == "M"  # 4 interims = M severity, 5+ = H severity


def test_S6_does_not_fire_with_alpha_spending():
    """Test S6 does not fire when alpha spending is specified."""
    card = {
        "study_id": "S6b",
        "analysis_plan": {
            "planned_interims": 4,
            "alpha_spending_function": "O'Brien-Fleming"  # Alpha spending specified
        }
    }
    res = S6_many_interims_no_spending(card)
    assert not res.fired


def test_S7_single_arm_where_rct_standard():
    """Test S7 fires on single arm where RCT is required."""
    card = {
        "study_id": "S7",
        "single_arm": True,
        "indication": "metastatic_breast_cancer"
    }
    rct_required_data = {
        "metastatic_breast_cancer": {
            "rct_required": True,
            "strict_requirement": True
        }
    }
    res = S7_single_arm_where_rct_standard(card, rct_required_data)
    assert res.fired and res.severity == "H"


def test_S7_does_not_fire_when_rct_not_required():
    """Test S7 does not fire when RCT is not required for indication."""
    card = {
        "study_id": "S7b",
        "single_arm": True,
        "indication": "rare_disease"
    }
    rct_required_data = {
        "rare_disease": {
            "rct_required": False
        }
    }
    res = S7_single_arm_where_rct_standard(card, rct_required_data)
    assert not res.fired


def test_S7b_randomized_withdrawal_after_OLE():
    """Test S7b fires on randomized-withdrawal after OLE design."""
    card = {
        "study_id": "S7b",
        "design_archetype": "randomized_withdrawal_after_OLE",
        "is_pivotal": True
    }
    
    res = S7b_randomized_withdrawal_after_OLE(card)
    assert res.fired and res.severity == "M"
    assert "Randomized-withdrawal after OLE" in res.reason


def test_S7b_does_not_fire_when_not_pivotal():
    """Test S7b does not fire when study is not pivotal."""
    card = {
        "study_id": "S7b_neg",
        "design_archetype": "randomized_withdrawal_after_OLE",
        "is_pivotal": False
    }
    
    res = S7b_randomized_withdrawal_after_OLE(card)
    assert not res.fired
    assert "No RW after OLE design bias" in res.reason


def test_S7b_does_not_fire_on_standard_design():
    """Test S7b does not fire on standard RCT design."""
    card = {
        "study_id": "S7b_std",
        "design_archetype": "rct_phase3",
        "is_pivotal": True
    }
    
    res = S7b_randomized_withdrawal_after_OLE(card)
    assert not res.fired
    assert "No RW after OLE design bias" in res.reason


def test_S8_pvalue_cusp():
    """Test S8 fires on p-value cusp without multiplicity adjustment."""
    card = {
        "study_id": "S8",
        "primary_result": {"ITT": {"p": 0.045}},  # P-value in cusp
        "analysis_plan": {
            # No multiplicity_adjustment specified
        }
    }
    res = S8_pvalue_cusp_or_heaping(card)
    assert res.fired and res.severity == "M"


def test_S8_pvalue_heaping():
    """Test S8 fires on p-value heaping at common thresholds."""
    card = {
        "study_id": "S8b",
        "primary_result": {"ITT": {"p": 0.051}},
        "subgroups": [
            {"name": "Region A", "p": 0.049},
            {"name": "Age<65", "p": 0.052},
            {"name": "Male", "p": 0.048}
        ]
    }
    res = S8_pvalue_cusp_or_heaping(card)
    assert res.fired  # Multiple p-values near 0.05


def test_S8_does_not_fire_with_multiplicity_adjustment():
    """Test S8 does not fire when multiplicity adjustment is used."""
    card = {
        "study_id": "S8c",
        "primary_result": {"ITT": {"p": 0.045}},
        "analysis_plan": {
            "multiplicity_adjustment": "Bonferroni"
        }
    }
    res = S8_pvalue_cusp_or_heaping(card)
    assert not res.fired


def test_S9_os_pfs_contradiction():
    """Test S9 fires on OS/PFS contradiction."""
    card = {
        "study_id": "S9",
        "results": [
            {"metric": "os_hr", "value": 1.15},  # OS HR > 1.0
            {"metric": "pfs_hr", "value": 0.75},  # PFS HR < 0.8
            {"metric": "os_events", "value": 75}  # OS events >= 50
        ],
        "events_observed": 75
    }
    res = S9_os_pfs_contradiction(card)
    assert res.fired and res.severity == "M"


def test_S9_does_not_fire_without_contradiction():
    """Test S9 does not fire without OS/PFS contradiction."""
    card = {
        "study_id": "S9b",
        "results": [
            {"metric": "os_hr", "value": 0.95},  # OS HR < 1.0
            {"metric": "pfs_hr", "value": 0.75},  # PFS HR < 0.8
            {"metric": "os_events", "value": 75}
        ]
    }
    res = S9_os_pfs_contradiction(card)
    assert not res.fired


def test_study_card_mapper_basic():
    """Test basic Study Card mapping."""
    method_card = {
        "primary_endpoint": "ORR_RECIST",
        "is_pivotal": True,
        "design_archetype": "single_arm_phase2_gehan",
        "alpha_level": 0.025,
        "is_one_sided": True,
        "blinding_level": "none_open_label"
    }
    
    results_factsheet = {
        "results": [
            {"metric": "orr_recist", "value": 15.8, "units": "percent"}
        ]
    }
    
    claims = [
        {"type": "design_fact", "proposition": "blinding: open-label"},
        {"type": "design_fact", "proposition": "interim_design: Gehan"}
    ]
    
    card = build_study_card("test_doc", method_card, results_factsheet, claims)
    
    assert card["study_id"] == "test_doc"
    assert card["is_pivotal"] == True
    assert card["single_arm"] == True
    assert card["primary_type"] == "proportion"
    assert card["analysis_plan"]["alpha"] == 0.025
    assert card["analysis_plan"]["one_sided"] == True
    assert card["analysis_plan"]["planned_interims"] == 1  # From Gehan claim
