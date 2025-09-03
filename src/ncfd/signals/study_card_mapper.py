"""
Study Card mapper to bridge extraction artifacts to signal inputs.

Maps MethodCard, ResultsFactsheet, and Claims to a Study Card dict
that can be consumed by S1-S4 signal primitives.
"""

from typing import Any, Dict, List
from dataclasses import asdict, is_dataclass


def _to_dict(x):
    """Convert object to dict, handling dataclasses and None."""
    if x is None:
        return {}
    if isinstance(x, dict):
        return x
    if is_dataclass(x):
        return asdict(x)
    # Try attribute mapping for objects
    return {k: getattr(x, k) for k in dir(x) if not k.startswith("_") and not callable(getattr(x, k))}


def build_study_card(doc_id: str, method_card: Any, results_factsheet: Any, claims: List[Any]) -> Dict[str, Any]:
    """
    Build a Study Card dict from extraction artifacts.
    
    Args:
        doc_id: Document identifier
        method_card: MethodCard object/dict
        results_factsheet: ResultsFactsheet object/dict  
        claims: List of Claim objects/dicts
        
    Returns:
        Study Card dict with fields needed by S1-S4 signals
    """
    mc = _to_dict(method_card)
    rf = _to_dict(results_factsheet)
    cl = [_to_dict(c) for c in (claims or [])]

    # Primary type inference from primary endpoint
    primary_endpoint = (mc.get("primary_endpoint") or "").lower()
    primary_type = "proportion" if ("orr" in primary_endpoint or "response" in primary_endpoint) else (
                   "tte" if ("os" in primary_endpoint or "pfs" in primary_endpoint or "ttp" in primary_endpoint or "survival" in primary_endpoint) else "other")

    # Arms and dropout (if present in card/claims; else None)
    arms = {
        "t": {"n": mc.get("n_treatment"), "dropout": mc.get("dropout_t")},
        "c": {"n": mc.get("n_control"), "dropout": mc.get("dropout_c")},
    }

    # Analysis plan hints (alpha, one-sided/two-sided, HR_alt, planned_events)
    analysis_plan = {
        "alpha": mc.get("alpha_level") or 0.05,
        "one_sided": mc.get("is_one_sided") if mc.get("is_one_sided") is not None else False,
        "two_sided": not mc.get("is_one_sided") if mc.get("is_one_sided") is not None else True,
        # Optional placeholders:
        "assumed_p_c": mc.get("assumed_control_rate"),
        "assumed_delta_abs": mc.get("assumed_delta_abs"),
        "hr_alt": mc.get("hr_alt"),
        "planned_events": mc.get("planned_events"),
        "alloc_ratio": mc.get("randomization_ratio", 1.0) or 1.0,
    }

    # Primary result (ITT/PP) - if available
    primary_result = {
        "ITT": {"estimate": mc.get("itt_estimate"), "p": mc.get("itt_p")},
        "PP": {"estimate": mc.get("pp_estimate"), "p": mc.get("pp_p")} if mc.get("pp_p") is not None else None
    }

    # Subgroups (optional, likely empty)
    subgroups = mc.get("subgroups") or []

    # Subjective endpoint & blinding indicator for S4 severity
    endpoint_subjective_unblinded = (("patient-reported" in primary_endpoint) and 
                                   (mc.get("blinding_level") in ("none_open_label", "open_label")))
    
    # Pivotal flag
    is_pivotal = bool(mc.get("is_pivotal", False))
    
    # Single arm detection
    single_arm = bool(mc.get("design_archetype", "").startswith("single_arm"))
    
    # Design archetype detection for S7b
    design_archetype = mc.get("design_archetype", "").lower()

    # Extract additional info from claims
    for claim in cl:
        if claim.get("type") == "design_fact":
            prop = claim.get("proposition", "").lower()
            if "blinding: open-label" in prop:
                analysis_plan["blinding"] = "open"
            elif "interim_design: gehan" in prop:
                analysis_plan["interim_design"] = "gehan"
                analysis_plan["planned_interims"] = 1  # Gehan typically has 1 interim

    card = {
        "study_id": doc_id,
        "is_pivotal": is_pivotal,
        "single_arm": single_arm,
        "design_archetype": design_archetype,  # Added for S7b
        "primary_type": primary_type,
        "arms": arms,
        "analysis_plan": analysis_plan,
        "primary_result": primary_result,
        "subgroups": subgroups,
        "narrative_highlights_subgroup": False,  # Would need to be set from narrative analysis
        "endpoint_subjective_unblinded": endpoint_subjective_unblinded,
        # Helpful extras:
        "historical_control_rate": mc.get("historical_control_rate"),
        "mcid_abs": mc.get("mcid_abs"),
        "N_total": mc.get("number_enrolled") or mc.get("sample_size"),
        "events_observed": mc.get("events_observed"),
    }
    
    return card
