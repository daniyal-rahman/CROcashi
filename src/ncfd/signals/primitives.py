"""
Signal primitives S1-S9 for precision-first failure detection.

Implements the core signal detectors with exact thresholds from phase6.md.
"""

from typing import List, Dict, Any, Optional
import math
from .types import SignalResult


def _phi(x: float) -> float:
    """Standard normal CDF approximation."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _z_for(alpha: float, two_sided: bool) -> float:
    """Invert CDF via binary search (poor-man's quantile)."""
    a = alpha / 2.0 if two_sided else alpha
    lo, hi = -10.0, 10.0
    for _ in range(50):
        mid = (lo + hi) / 2.0
        if 1 - _phi(mid) > a:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def S1_endpoint_changed(trial_versions: List[Dict[str, Any]]) -> SignalResult:
    """
    S1: Endpoint changed (material & late).
    
    Algorithm from phase6.md:
    1. Normalize endpoint text → concept id
    2. Diff consecutive versions  
    3. "Material change" if endpoint concept class changes, objective→subjective, NI↔SI toggle, etc.
    4. "Late" if change occurs after trial start or within ≤180 days of completion
    """
    def to_concept(txt: str) -> Dict[str, str]:
        """Convert endpoint text to concept mapping."""
        t = (txt or "").lower()
        return {
            "class": "os" if "overall survival" in t else
                     "pfs" if ("progression-free" in t or "pfs" in t or "time to progression" in t or "ttp" in t) else
                     "orr" if ("objective response" in t or "orr" in t) else "other",
            "timepoint": "12m" if "12 month" in t or "12-month" in t else
                         "24m" if "24 month" in t or "24-month" in t else "unspecified",
            "ni": "ni" if ("non-inferior" in t or "noninferior" in t) else "si",
            "blinded": "open" if "open-label" in t else "blinded",
        }
    
    if len(trial_versions) < 2:
        return SignalResult(False, "L", reason="single version")

    fired, sev, ev_ids = False, "M", []
    for a, b in zip(trial_versions, trial_versions[1:]):
        ca = to_concept(a.get("primary_endpoint_text", ""))
        cb = to_concept(b.get("primary_endpoint_text", ""))
        
        # Material change detection
        material = (ca["class"] != cb["class"]) or (ca["ni"] != cb["ni"]) or (ca["blinded"] != cb["blinded"]) or (ca["timepoint"] != cb["timepoint"])
        
        # Late change detection
        late = False
        cap_b = b.get("captured_at")
        epc_b = b.get("est_primary_completion_date")
        if cap_b and epc_b:
            try:
                # Convert to datetime if strings
                if isinstance(cap_b, str):
                    from datetime import datetime
                    cap_b = datetime.fromisoformat(cap_b.replace('Z', '+00:00'))
                if isinstance(epc_b, str):
                    from datetime import datetime
                    epc_b = datetime.fromisoformat(epc_b.replace('Z', '+00:00'))
                
                # Calculate days difference
                if hasattr(epc_b, 'date') and hasattr(cap_b, 'date'):
                    days_diff = (epc_b.date() - cap_b.date()).days
                    late = days_diff <= 180
                else:
                    late = (epc_b - cap_b).days <= 180
            except Exception:
                late = False
        
        # Allow explicit late flag
        late = late or bool(b.get("is_late_change"))
        
        if material and late:
            fired = True
            ev_ids += [a.get("version_id"), b.get("version_id")]
            if late:
                sev = "H"
    
    ev_ids = [x for x in ev_ids if x]
    return SignalResult(fired, sev if fired else "L", reason="Material endpoint change late", evidence_ids=list(dict.fromkeys(ev_ids)))


def _power_two_proportions(n_t: int, n_c: int, p_c: float, delta_abs: float, alpha: float = 0.025, two_sided: bool = False) -> float:
    """Power calculation for two proportions (normal approximation)."""
    p_t = max(1e-9, min(1-1e-9, p_c + delta_abs))
    se = math.sqrt(p_t*(1-p_t)/max(n_t,1) + p_c*(1-p_c)/max(n_c,1))
    if se == 0:
        return 0.0
    z_alpha = _z_for(alpha, two_sided)
    return _phi(abs(delta_abs)/se - z_alpha)


def _power_logrank(events: int, hr_alt: float, alloc_ratio: float = 1.0, alpha: float = 0.05, two_sided: bool = True) -> float:
    """Power calculation for log-rank test (Freedman approximation)."""
    if not events or events <= 0 or not hr_alt or hr_alt <= 0:
        return 0.0
    psi = (alloc_ratio)/(1.0 + alloc_ratio)**2
    z_alpha = _z_for(alpha, two_sided)
    return _phi(math.sqrt(events*psi)*abs(math.log(hr_alt)) - z_alpha)


def S2_underpowered_pivotal(card: Dict[str, Any]) -> SignalResult:
    """
    S2: Underpowered pivotal (<70% power at claimed Δ).
    
    Algorithm from phase6.md:
    - Two-arm proportions: normal approximation with unpooled SE
    - Time-to-event: Freedman approximation for log-rank
    - Fire if Power < 0.70 (or < 0.55 if using defaults)
    """
    if not card.get("is_pivotal", False):
        return SignalResult(False, "L", reason="not pivotal")
    
    ap = card.get("analysis_plan", {})
    primary_type = card.get("primary_type")

    if primary_type == "proportion":
        n_t = card.get("arms", {}).get("t", {}).get("n")
        n_c = card.get("arms", {}).get("c", {}).get("n")
        alpha = ap.get("alpha", 0.025 if ap.get("one_sided", True) else 0.05)
        two_sided = not ap.get("one_sided", True)
        p_c = ap.get("assumed_p_c")
        delta = ap.get("assumed_delta_abs")
        low_cert = False
        
        if p_c is None:
            p_c = card.get("historical_control_rate")
            if p_c is None:
                return SignalResult(False, "L", reason="missing control rate")
        
        if delta is None:
            delta = card.get("mcid_abs", 0.12)  # oncology ORR default
            low_cert = True
        
        pw = _power_two_proportions(n_t or 0, n_c or 0, p_c, delta, alpha, two_sided)
        fired = (pw < 0.70 and not low_cert) or (pw < 0.55 and low_cert)
        sev = "H" if pw < 0.55 else "M"
        
        return SignalResult(
            fired, sev if fired else "L", value=pw, 
            reason=f"power={pw:.2f} at Δ={delta:.3f}, p_c={p_c:.3f}", 
            low_cert_inputs=low_cert
        )

    if primary_type == "tte":
        alpha = ap.get("alpha", 0.05)
        two_sided = ap.get("two_sided", True)
        hr_alt = ap.get("hr_alt")
        events = ap.get("planned_events") or card.get("events_observed")
        low_cert = False
        
        if hr_alt is None:
            return SignalResult(False, "L", reason="missing HR_alt")
        
        if events is None:
            if card.get("N_total"):
                events = int(0.6 * card["N_total"])
                low_cert = True
            else:
                return SignalResult(False, "L", reason="missing events")
        
        k = ap.get("alloc_ratio", (card.get("arms", {}).get("t", {}).get("n", 0) / max(card.get("arms", {}).get("c", {}).get("n", 1), 1)))
        pw = _power_logrank(events, hr_alt, k, alpha, two_sided)
        fired = (pw < 0.70 and not low_cert) or (pw < 0.55 and low_cert)
        sev = "H" if pw < 0.55 else "M"
        
        return SignalResult(
            fired, sev if fired else "L", value=pw, 
            reason=f"power={pw:.2f} at HR_alt={hr_alt:.2f}, events={events}", 
            low_cert_inputs=low_cert
        )

    return SignalResult(False, "L", reason="unsupported primary_type")


def S3_subgroup_only_no_multiplicity(card: Dict[str, Any]) -> SignalResult:
    """
    S3: Subgroup-only win without multiplicity.
    
    Algorithm from phase6.md:
    Fire if (overall ITT non-sig) AND (≥1 subgroup nominal p<0.05) AND 
    (no family-wise control covering that subgroup) AND (subgroup not pre-specified for interaction)
    """
    prim = card.get("primary_result", {}).get("ITT")
    if not prim:
        return SignalResult(False, "L", reason="no ITT set")
    
    if prim.get("p") is not None and prim.get("p", 1.0) < 0.05:
        return SignalResult(False, "L", reason="overall ITT significant")
    
    flagged = []
    for sg in card.get("subgroups", []):
        if (sg.get("p") is not None and sg.get("p", 1.0) < 0.05 and 
            not sg.get("adjusted", False) and 
            not sg.get("pre_specified_interaction", False)):
            flagged.append(sg.get("name") or "subgroup")
    
    if flagged:
        sev = "H" if card.get("narrative_highlights_subgroup", False) else "M"
        return SignalResult(True, sev, reason=f"Subgroup-only wins: {flagged}")
    
    return SignalResult(False, "L", reason="no unadjusted subgroup-only wins")


def S4_itt_vs_pp_dropout(card: Dict[str, Any]) -> SignalResult:
    """
    S4: ITT neutral/neg vs PP positive + dropout asymmetry.
    
    Algorithm from phase6.md:
    1. ITT non-sig (or Δ_ITT ≤ 0 for benefit direction)
    2. PP nominal sig (p<0.05) favoring treatment  
    3. Dropout asymmetry: |Dropout_t − Dropout_c| ≥ 10%
    """
    prim = card.get("primary_result", {})
    itt, pp = prim.get("ITT"), prim.get("PP")
    
    if not pp:
        return SignalResult(False, "L", reason="no PP set")
    
    arms = card.get("arms", {})
    drop_t = arms.get("t", {}).get("dropout")
    drop_c = arms.get("c", {}).get("dropout")
    
    if drop_t is None or drop_c is None:
        return SignalResult(False, "L", reason="missing dropout rates")
    
    asym = abs(drop_t - drop_c)
    cond = ((itt.get("p") is None or itt.get("p", 1.0) >= 0.05 or itt.get("estimate", 0.0) <= 0) and 
            (pp.get("p") is not None and pp.get("p", 1.0) < 0.05 and pp.get("estimate", 0.0) > 0) and 
            (asym >= 0.10))
    
    sev = "H" if asym >= 0.15 or card.get("endpoint_subjective_unblinded", False) else "M"
    
    if cond:
        return SignalResult(True, sev, value=asym, reason=f"Dropout asym={asym:.2f}")
    
    return SignalResult(False, "L", reason="no ITT/PP contradiction with asymmetry")


def S5_implausible_vs_graveyard(card: Dict[str, Any], graveyard_data: Dict[str, Any]) -> SignalResult:
    """
    S5: Implausible vs graveyard.
    
    Algorithm from phase6.md:
    Fire if (primary endpoint effect size) > (95th percentile of graveyard for indication)
    """
    primary_result = card.get("primary_result", {}).get("ITT")
    if not primary_result or primary_result.get("estimate") is None:
        return SignalResult(False, "L", reason="no primary result")
    
    estimate = primary_result.get("estimate")
    indication = card.get("indication", "unknown")
    
    # Get graveyard data for this indication
    graveyard = graveyard_data.get(indication, {})
    if not graveyard:
        return SignalResult(False, "L", reason="no graveyard data")
    
    # Get 95th percentile threshold
    p95_threshold = graveyard.get("p95_effect_size")
    if p95_threshold is None:
        return SignalResult(False, "L", reason="no p95 threshold")
    
    # Check if estimate exceeds threshold
    if estimate > p95_threshold:
        sev = "H" if estimate > graveyard.get("p99_effect_size", float('inf')) else "M"
        return SignalResult(True, sev, value=estimate, reason=f"Effect {estimate:.3f} > p95 {p95_threshold:.3f}")
    
    return SignalResult(False, "L", reason="effect size within graveyard range")


def S6_many_interims_no_spending(card: Dict[str, Any]) -> SignalResult:
    """
    S6: Many interims no spending.
    
    Algorithm from phase6.md:
    Fire if (planned_interims ≥ 3) AND (no alpha spending function specified)
    """
    analysis_plan = card.get("analysis_plan", {})
    planned_interims = analysis_plan.get("planned_interims", 0)
    alpha_spending = analysis_plan.get("alpha_spending_function")
    
    if planned_interims >= 3 and not alpha_spending:
        sev = "H" if planned_interims >= 5 else "M"
        return SignalResult(True, sev, value=planned_interims, reason=f"{planned_interims} interims, no alpha spending")
    
    return SignalResult(False, "L", reason="insufficient interims or alpha spending specified")


def S7_single_arm_where_rct_standard(card: Dict[str, Any], rct_required_data: Dict[str, Any]) -> SignalResult:
    """
    S7: Single arm where RCT standard.
    
    Algorithm from phase6.md:
    Fire if (single_arm) AND (indication requires RCT per policy table)
    """
    if not card.get("single_arm", False):
        return SignalResult(False, "L", reason="not single arm")
    
    indication = card.get("indication", "unknown")
    rct_required = rct_required_data.get(indication, {}).get("rct_required", False)
    
    if rct_required:
        sev = "H" if rct_required_data.get(indication, {}).get("strict_requirement", False) else "M"
        return SignalResult(True, sev, reason=f"Single arm but {indication} requires RCT")
    
    return SignalResult(False, "L", reason="single arm acceptable for indication")


def S7b_randomized_withdrawal_after_OLE(card: Dict[str, Any]) -> SignalResult:
    """
    S7b: Randomized-withdrawal after OLE design bias.
    
    Fire if design_archetype contains "randomized_withdrawal" or "OLE" 
    and the study is being used as pivotal evidence.
    """
    design_archetype = card.get("design_archetype", "").lower()
    is_pivotal = card.get("is_pivotal", False)
    
    # Check for RW after OLE patterns
    rw_after_ole = any(phrase in design_archetype for phrase in [
        "randomized_withdrawal", "withdrawal", "ole", "open_label"
    ])
    
    if rw_after_ole and is_pivotal:
        return SignalResult(True, "M", reason="Randomized-withdrawal after OLE used as pivotal evidence")
    
    return SignalResult(False, "L", reason="No RW after OLE design bias")


def S8_pvalue_cusp_or_heaping(card: Dict[str, Any]) -> SignalResult:
    """
    S8: P-value cusp or heaping.
    
    Algorithm from phase6.md:
    Fire if (p-value in [0.04, 0.06]) AND (no multiplicity adjustment) OR
    (multiple p-values cluster at common thresholds)
    """
    primary_result = card.get("primary_result", {}).get("ITT")
    if not primary_result or primary_result.get("p") is None:
        return SignalResult(False, "L", reason="no p-value")
    
    p_value = primary_result.get("p")
    
    # Check for cusp (0.04-0.06)
    if 0.04 <= p_value <= 0.06:
        analysis_plan = card.get("analysis_plan", {})
        if not analysis_plan.get("multiplicity_adjustment"):
            return SignalResult(True, "M", value=p_value, reason=f"P-value cusp {p_value:.3f}, no multiplicity adjustment")
    
    # Check for heaping (multiple p-values at common thresholds)
    all_p_values = []
    if primary_result.get("p"):
        all_p_values.append(primary_result.get("p"))
    
    # Add subgroup p-values
    for sg in card.get("subgroups", []):
        if sg.get("p"):
            all_p_values.append(sg.get("p"))
    
    if len(all_p_values) >= 3:
        # Check for clustering at common thresholds (0.01, 0.05, 0.10)
        common_thresholds = [0.01, 0.05, 0.10]
        for threshold in common_thresholds:
            close_p_values = [p for p in all_p_values if abs(p - threshold) < 0.005]
            if len(close_p_values) >= 2:
                return SignalResult(True, "M", value=len(close_p_values), reason=f"P-value heaping at {threshold}: {len(close_p_values)} values")
    
    return SignalResult(False, "L", reason="no p-value cusp or heaping")


def S9_os_pfs_contradiction(card: Dict[str, Any]) -> SignalResult:
    """
    S9: OS/PFS contradiction.
    
    Algorithm from phase6.md:
    Fire if (OS HR > 1.0) AND (PFS HR < 0.8) AND (OS events ≥ 50)
    """
    # Extract OS and PFS results from claims or results
    results = card.get("results", [])
    os_hr = None
    pfs_hr = None
    os_events = None
    
    for result in results:
        metric = result.get("metric", "").lower()
        if "os" in metric and "hr" in metric:
            os_hr = result.get("value")
        elif "pfs" in metric and "hr" in metric:
            pfs_hr = result.get("value")
        elif "os" in metric and "events" in metric:
            os_events = result.get("value")
    
    # Also check claims for HR values
    claims = card.get("claims", [])
    for claim in claims:
        if claim.get("type") == "effect_size":
            prop = claim.get("proposition", "").lower()
            if "os" in prop and "hr" in prop:
                os_hr = claim.get("value")
            elif "pfs" in prop and "hr" in prop:
                pfs_hr = claim.get("value")
    
    if os_hr is None or pfs_hr is None:
        return SignalResult(False, "L", reason="missing OS or PFS HR")
    
    if os_events is None:
        os_events = card.get("events_observed", 0)
    
    # Check contradiction condition
    if os_hr > 1.0 and pfs_hr < 0.8 and os_events >= 50:
        sev = "H" if os_hr > 1.2 and pfs_hr < 0.7 else "M"
        return SignalResult(True, sev, value=os_hr/pfs_hr, reason=f"OS HR={os_hr:.2f} > 1.0, PFS HR={pfs_hr:.2f} < 0.8")
    
    return SignalResult(False, "L", reason="no OS/PFS contradiction")
