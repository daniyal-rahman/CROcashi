"""
Signal primitives for trial failure detection.

This module implements the 9 core signal primitives (S1-S9) that detect
various red flags in clinical trial data. Each signal is designed to be
high-precision and focused on specific failure patterns.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
import math
from datetime import datetime, date, timedelta
import json

# Type aliases for clarity
StudyCard = Dict[str, Any]
TrialVersion = Dict[str, Any]
ClassMetadata = Dict[str, Any]


@dataclass
class SignalResult:
    """Result of a signal evaluation."""
    fired: bool
    severity: str  # 'H', 'M', 'L'
    value: Optional[float] = None  # e.g., computed power or z-score
    reason: str = ""
    evidence_ids: Optional[List[str]] = None  # study_id or version_ids
    low_cert_inputs: bool = False
    metadata: Optional[Dict[str, Any]] = None  # Additional signal-specific data


# ---- Helper Functions ----

def _phi(x: float) -> float:
    """Standard normal CDF approximation."""
    # Simple approximation - in production, use scipy.stats.norm.cdf
    if x < -8.0:
        return 0.0
    if x > 8.0:
        return 1.0
    
    # Abramowitz and Stegun approximation
    b1 = 0.31938153
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429
    p = 0.2316419
    c = 0.39894228
    
    if x >= 0.0:
        t = 1.0 / (1.0 + p * x)
        return 1.0 - c * math.exp(-x * x / 2.0) * t * (t * (t * (t * (t * b5 + b4) + b3) + b2) + b1)
    else:
        t = 1.0 / (1.0 - p * x)
        return c * math.exp(-x * x / 2.0) * t * (t * (t * (t * (t * b5 + b4) + b3) + b2) + b1)


def _z_for(alpha: float, two_sided: bool) -> float:
    """Return critical z-value for given alpha."""
    a = alpha / 2 if two_sided else alpha
    # Inverse of standard normal CDF
    # For common values, use lookup table
    if a == 0.025:
        return 1.96
    elif a == 0.05:
        return 1.645
    elif a == 0.01:
        return 2.326
    else:
        # Use approximation for other values
        # In production, use scipy.stats.norm.ppf
        return -_phi_inv(a)


def _phi_inv(p: float) -> float:
    """Inverse of standard normal CDF approximation."""
    if p < 0.5:
        return -_phi_inv(1 - p)
    
    # Approximation for p >= 0.5
    c0 = 2.515517
    c1 = 0.802853
    c2 = 0.010328
    d1 = 1.432788
    d2 = 0.189269
    d3 = 0.001308
    
    t = math.sqrt(-2 * math.log(1 - p))
    return t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t * t * t)


def power_two_proportions(n_t: int, n_c: int, p_c: float, delta_abs: float,
                         alpha: float = 0.025, two_sided: bool = False) -> float:
    """Calculate power for two-proportion test."""
    p_t = max(1e-9, min(1 - 1e-9, p_c + delta_abs))
    se = math.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
    if se == 0:
        return 0.0
    
    z_alpha = _z_for(alpha, two_sided)
    return float(_phi(abs(delta_abs) / se - z_alpha))


def power_logrank(events: int, hr_alt: float, alloc_ratio: float = 1.0,
                 alpha: float = 0.05, two_sided: bool = True) -> float:
    """Calculate power for log-rank test using Freedman approximation."""
    if events is None or events <= 0 or hr_alt <= 0:
        return 0.0
    
    psi = (alloc_ratio) / (1 + alloc_ratio) ** 2
    z_alpha = _z_for(alpha, two_sided)
    return float(_phi(math.sqrt(events * psi) * abs(math.log(hr_alt)) - z_alpha))


def _normalize_endpoint_text(text: str) -> Dict[str, str]:
    """Normalize endpoint text to extract key concepts."""
    if not text:
        return {"class": "unknown", "timepoint": "unspecified", "ni": "unknown", "blinded": "unknown"}
    
    t = text.lower()
    concept = {}
    
    # Endpoint class
    if "overall survival" in t or "os" in t:
        concept["class"] = "os"
    elif "progression-free" in t or "pfs" in t:
        concept["class"] = "pfs"
    elif "objective response" in t or "orr" in t:
        concept["class"] = "orr"
    elif "progression" in t:
        concept["class"] = "pfs"
    elif "response" in t:
        concept["class"] = "orr"
    else:
        concept["class"] = "other"
    
    # Timepoint
    if "12 month" in t or "12-month" in t or "12m" in t:
        concept["timepoint"] = "12m"
    elif "24" in t or "24m" in t:
        concept["timepoint"] = "24m"
    elif "6" in t or "6m" in t:
        concept["timepoint"] = "6m"
    else:
        concept["timepoint"] = "unspecified"
    
    # Non-inferiority vs Superiority
    if "non-inferior" in t or "noninferior" in t or "ni" in t:
        concept["ni"] = "ni"
    elif "superior" in t or "superiority" in t:
        concept["ni"] = "si"
    else:
        concept["ni"] = "unknown"
    
    # Blinding
    if "open-label" in t or "open label" in t:
        concept["blinded"] = "open"
    elif "blinded" in t or "blind" in t:
        concept["blinded"] = "blinded"
    else:
        concept["blinded"] = "unknown"
    
    return concept


def _is_material_change(concept_a: Dict[str, str], concept_b: Dict[str, str]) -> bool:
    """Determine if endpoint change is material."""
    return (concept_a["class"] != concept_b["class"] or
            concept_a["ni"] != concept_b["ni"] or
            concept_a["blinded"] != concept_b["blinded"] or
            concept_a["timepoint"] != concept_b["timepoint"])


def _is_late_change(version: TrialVersion, est_completion: Optional[date]) -> bool:
    """Determine if change occurred late in trial."""
    if not est_completion:
        return False
    
    captured = version.get("captured_at")
    if not captured:
        return False
    
    # Convert to date if datetime
    if isinstance(captured, datetime):
        captured = captured.date()
    
    days_to_completion = (est_completion - captured).days
    return days_to_completion <= 180


# ---- Signal Primitives ----

def S1_endpoint_changed(trial_versions: List[TrialVersion]) -> SignalResult:
    """
    S1: Endpoint changed (material & late).
    
    Detects when primary endpoint changes materially after trial start
    or within 180 days of estimated completion.
    """
    if len(trial_versions) < 2:
        return SignalResult(False, "L", reason="single version")
    
    fired = False
    sev = "M"
    evidence = []
    
    # Sort by captured_at to ensure chronological order
    sorted_versions = sorted(trial_versions, key=lambda v: v.get("captured_at", datetime.min))
    
    for i in range(len(sorted_versions) - 1):
        version_a = sorted_versions[i]
        version_b = sorted_versions[i + 1]
        
        concept_a = _normalize_endpoint_text(version_a.get("primary_endpoint_text", ""))
        concept_b = _normalize_endpoint_text(version_b.get("primary_endpoint_text", ""))
        
        material = _is_material_change(concept_a, concept_b)
        late = _is_late_change(version_b, version_b.get("est_primary_completion_date"))
        
        if material and late:
            fired = True
            evidence.extend([str(version_a.get("version_id")), str(version_b.get("version_id"))])
            
            # Check if within 180 days of completion for high severity
            if late:
                sev = "H"
    
    if fired:
        return SignalResult(
            fired=True,
            severity=sev,
            reason="Material endpoint change late in registry",
            evidence_ids=list(dict.fromkeys(evidence))
        )
    
    return SignalResult(False, "L", reason="no material late changes")


def S2_underpowered_pivotal(card: StudyCard) -> SignalResult:
    """
    S2: Underpowered pivotal (<70% power at claimed Δ).
    
    Detects trials with insufficient statistical power for their
    claimed treatment effect.
    """
    if not card.get("is_pivotal", False):
        return SignalResult(False, "L", reason="not pivotal")
    
    ap = card.get("analysis_plan", {})
    
    # Branch: proportions vs time-to-event
    if card.get("primary_type") == "proportion":
        n_t = card.get("arms", {}).get("t", {}).get("n")
        n_c = card.get("arms", {}).get("c", {}).get("n")
        
        if not n_t or not n_c:
            return SignalResult(False, "L", reason="missing sample sizes")
        
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
        
        power = power_two_proportions(n_t, n_c, p_c, delta, alpha, two_sided)
        fired = (power < 0.70 and not low_cert) or (power < 0.55 and low_cert)
        sev = "H" if power < 0.55 else "M"
        
        return SignalResult(
            fired=fired,
            severity=sev if fired else "L",
            value=power,
            reason=f"power={power:.2f} at Δ={delta:.3f}, p_c={p_c:.3f}",
            evidence_ids=[str(card.get("study_id", ""))],
            low_cert_inputs=low_cert,
            metadata={
                "alpha": alpha,
                "two_sided": two_sided,
                "n_t": n_t,
                "n_c": n_c,
                "p_c": p_c,
                "delta_abs": delta,
                "low_cert_inputs": low_cert
            }
        )
    
    elif card.get("primary_type") == "tte":
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
        
        k = ap.get("alloc_ratio", card.get("arms", {}).get("t", {}).get("n", 1) / 
                   max(card.get("arms", {}).get("c", {}).get("n", 1), 1))
        
        power = power_logrank(events, hr_alt, k, alpha, two_sided)
        fired = (power < 0.70 and not low_cert) or (power < 0.55 and low_cert)
        sev = "H" if power < 0.55 else "M"
        
        return SignalResult(
            fired=fired,
            severity=sev if fired else "L",
            value=power,
            reason=f"power={power:.2f} at HR_alt={hr_alt:.2f}, events={events}",
            evidence_ids=[str(card.get("study_id", ""))],
            low_cert_inputs=low_cert,
            metadata={
                "alpha": alpha,
                "two_sided": two_sided,
                "hr_alt": hr_alt,
                "events": events,
                "alloc_ratio": k,
                "low_cert_inputs": low_cert
            }
        )
    
    return SignalResult(False, "L", reason="unsupported primary_type")


def S3_subgroup_only_no_multiplicity(card: StudyCard) -> SignalResult:
    """
    S3: Subgroup-only win without multiplicity control.
    
    Detects when a trial fails overall but claims success in subgroups
    without proper multiplicity adjustment.
    """
    prim = card.get("primary_result", {}).get("ITT", {})
    if prim.get("p", 1.0) < 0.05:
        return SignalResult(False, "L", reason="overall ITT significant")
    
    flagged = []
    for sg in card.get("subgroups", []):
        if (sg.get("p", 1.0) < 0.05 and 
            not sg.get("adjusted", False) and 
            not sg.get("pre_specified_interaction", False)):
            flagged.append(sg.get("name", "unnamed"))
    
    if flagged:
        sev = "H" if card.get("narrative_highlights_subgroup", False) else "M"
        return SignalResult(
            fired=True,
            severity=sev,
            reason=f"Subgroup-only wins: {', '.join(flagged)}",
            evidence_ids=[str(card.get("study_id", ""))],
            metadata={"flagged_subgroups": flagged}
        )
    
    return SignalResult(False, "L", reason="no unadjusted subgroup-only wins")


def S4_itt_vs_pp_dropout(card: StudyCard) -> SignalResult:
    """
    S4: ITT neutral/neg vs PP positive + dropout asymmetry.
    
    Detects when per-protocol analysis shows positive results but
    ITT analysis doesn't, with asymmetric dropout patterns.
    """
    itt = card.get("primary_result", {}).get("ITT", {})
    pp = card.get("primary_result", {}).get("PP")
    
    if not pp:
        return SignalResult(False, "L", reason="no PP set")
    
    drop_t = card.get("arms", {}).get("t", {}).get("dropout", 0)
    drop_c = card.get("arms", {}).get("c", {}).get("dropout", 0)
    asym = abs(drop_t - drop_c)
    
    # Check conditions: ITT non-sig, PP sig, dropout asymmetry
    cond = (itt.get("p", 1.0) >= 0.05 or itt.get("estimate", 0) <= 0) and \
           (pp.get("p", 1.0) < 0.05 and pp.get("estimate", 0) > 0) and \
           (asym >= 0.10)
    
    sev = "H" if asym >= 0.15 or card.get("endpoint_subjective_unblinded", False) else "M"
    
    if cond:
        return SignalResult(
            fired=True,
            severity=sev,
            value=asym,
            reason=f"Dropout asym={asym:.2f}",
            evidence_ids=[str(card.get("study_id", ""))],
            metadata={
                "itt_p": itt.get("p"),
                "itt_estimate": itt.get("estimate"),
                "pp_p": pp.get("p"),
                "pp_estimate": pp.get("estimate"),
                "dropout_t": drop_t,
                "dropout_c": drop_c,
                "asymmetry": asym
            }
        )
    
    return SignalResult(False, "L", reason="no ITT/PP contradiction with asymmetry")


def S5_implausible_vs_graveyard(card: StudyCard, class_meta: ClassMetadata) -> SignalResult:
    """
    S5: Effect size implausible vs class "graveyard".
    
    Detects when claimed effect sizes are implausibly high compared
    to historical successful trials in the same class.
    """
    if not class_meta.get("graveyard", False):
        return SignalResult(False, "L", reason="class not graveyard")
    
    eff = card.get("primary_result", {}).get("effect_size")
    if eff is None:
        return SignalResult(False, "L", reason="missing effect size")
    
    p75 = class_meta.get("winners_pctl", {}).get("p75")
    if p75 is None:
        return SignalResult(False, "L", reason="no pctl data")
    
    if eff >= p75:
        p90 = class_meta.get("winners_pctl", {}).get("p90", float("inf"))
        sev = "H" if eff >= p90 else "M"
        return SignalResult(
            fired=True,
            severity=sev,
            value=eff,
            reason=f"effect {eff:.3f} ≥ P75 {p75:.3f}",
            evidence_ids=[str(card.get("study_id", ""))],
            metadata={
                "effect_size": eff,
                "p75_threshold": p75,
                "p90_threshold": p90
            }
        )
    
    return SignalResult(False, "L", reason="effect within plausible range")


def S6_many_interims_no_spending(card: StudyCard) -> SignalResult:
    """
    S6: Multiple interim looks without alpha spending.
    
    Detects trials with multiple interim analyses but no alpha
    spending plan or gatekeeping.
    """
    ap = card.get("analysis_plan", {})
    looks = ap.get("planned_interims", 0)
    spending = ap.get("alpha_spending")
    extra_peeks = card.get("actual_peeks", 0) - looks
    
    if looks >= 2 and not spending:
        return SignalResult(
            fired=True,
            severity="H",
            reason="≥2 interims without alpha spending",
            evidence_ids=[str(card.get("study_id", ""))],
            metadata={
                "planned_interims": looks,
                "alpha_spending": spending,
                "actual_peeks": card.get("actual_peeks", 0)
            }
        )
    
    if extra_peeks > 0 and not ap.get("reallocated_alpha", False):
        return SignalResult(
            fired=True,
            severity="M",
            reason="extra data peeks without alpha reallocation",
            evidence_ids=[str(card.get("study_id", ""))],
            metadata={
                "planned_interims": looks,
                "actual_peeks": card.get("actual_peeks", 0),
                "extra_peeks": extra_peeks
            }
        )
    
    return SignalResult(False, "L", reason="interim control adequate")


def S7_single_arm_where_rct_standard(card: StudyCard, rct_required: bool) -> SignalResult:
    """
    S7: Single-arm pivotal where RCT is standard of evidence.
    
    Detects when single-arm trials are used in settings where
    randomized controlled trials are the standard.
    """
    if not card.get("is_pivotal", False):
        return SignalResult(False, "L", reason="not pivotal")
    
    if not card.get("single_arm", False):
        return SignalResult(False, "L", reason="not single-arm")
    
    if rct_required:
        return SignalResult(
            fired=True,
            severity="H",
            reason="Pivotal single-arm in setting where RCT is standard",
            evidence_ids=[str(card.get("study_id", ""))],
            metadata={"rct_required": rct_required}
        )
    
    return SignalResult(False, "L", reason="single-arm acceptable per precedent")


def S8_pvalue_cusp_or_heaping(card: StudyCard, program_pvals: Optional[List[float]] = None) -> SignalResult:
    """
    S8: p-value cusp/heaping near 0.05.
    
    Detects individual p-values near 0.05 or systematic heaping
    across a program/sponsor.
    """
    p = card.get("primary_result", {}).get("ITT", {}).get("p", 1.0)
    cusp = (0.045 <= p <= 0.050)
    
    if cusp:
        return SignalResult(
            fired=True,
            severity="M",
            value=p,
            reason="primary p in [0.045,0.050]",
            evidence_ids=[str(card.get("study_id", ""))],
            metadata={"p_value": p, "cusp_range": [0.045, 0.050]}
        )
    
    # Heaping (program-level)
    if program_pvals and len([x for x in program_pvals if 0.045 <= x <= 0.055]) >= 10:
        L = sum(1 for x in program_pvals if 0.045 <= x < 0.050)
        R = sum(1 for x in program_pvals if 0.050 <= x <= 0.055)
        n = L + R
        
        if n >= 10 and L >= 2 * R:
            # One-sided binomial tail P(X>=L | n, 0.5)
            pval = sum(math.comb(n, k) for k in range(L, n + 1)) / (2 ** n)
            if pval < 0.01:
                return SignalResult(
                    fired=True,
                    severity="H",
                    value=pval,
                    reason=f"heaping L={L}, R={R}, p={pval:.4g}",
                    evidence_ids=[str(card.get("study_id", ""))],
                    metadata={
                        "left_count": L,
                        "right_count": R,
                        "total_count": n,
                        "binomial_p": pval
                    }
                )
    
    return SignalResult(False, "L", reason="no cusp/heaping")


def S9_os_pfs_contradiction(card: StudyCard) -> SignalResult:
    """
    S9: OS/PFS contradiction (context-aware).
    
    Detects when PFS shows benefit but OS shows harm or no benefit,
    accounting for crossover and event maturity.
    """
    pfs = card.get("pfs", {})
    os = card.get("os", {})
    
    if not pfs or not os:
        return SignalResult(False, "L", reason="missing endpoints")
    
    # PFS positive: p < 0.05 or HR < 1 with 95% CI < 1
    pfs_pos = (pfs.get("p", 1) < 0.05) or \
               (pfs.get("hr", 1.0) < 1 and pfs.get("ci95_upper", 1.01) < 1)
    
    # OS harm: HR ≥ 1.10 with ≥60% events and p < 0.20
    os_harm = (os.get("hr", 1.0) >= 1.10) and \
              (os.get("events_frac", 0) >= 0.60) and \
              (os.get("p", 1.0) < 0.20)
    
    # Low crossover: ≤30%
    low_xover = (os.get("crossover_rate", 0.0) <= 0.30)
    
    if pfs_pos and os_harm and low_xover:
        sev = "H" if os.get("hr", 1.0) >= 1.20 else "M"
        return SignalResult(
            fired=True,
            severity=sev,
            reason=f"PFS positive but OS HR={os.get('hr', 1.0):.2f} with {int(100*os.get('events_frac', 0))}% events and low crossover",
            evidence_ids=[str(card.get("study_id", ""))],
            metadata={
                "pfs_hr": pfs.get("hr"),
                "pfs_p": pfs.get("p"),
                "pfs_ci95_upper": pfs.get("ci95_upper"),
                "os_hr": os.get("hr"),
                "os_p": os.get("p"),
                "os_events_frac": os.get("events_frac"),
                "crossover_rate": os.get("crossover_rate")
            }
        )
    
    return SignalResult(False, "L", reason="no clear OS/PFS contradiction")


# ---- Convenience Functions ----

def evaluate_all_signals(card: StudyCard, trial_versions: Optional[List[TrialVersion]] = None,
                        class_meta: Optional[ClassMetadata] = None,
                        program_pvals: Optional[List[float]] = None,
                        rct_required: bool = True) -> Dict[str, SignalResult]:
    """Evaluate all signals for a given study card."""
    results = {}
    
    # S1: Endpoint changed (requires trial versions)
    if trial_versions:
        results["S1"] = S1_endpoint_changed(trial_versions)
    
    # S2: Underpowered pivotal
    results["S2"] = S2_underpowered_pivotal(card)
    
    # S3: Subgroup-only win without multiplicity
    results["S3"] = S3_subgroup_only_no_multiplicity(card)
    
    # S4: ITT vs PP dropout
    results["S4"] = S4_itt_vs_pp_dropout(card)
    
    # S5: Implausible vs graveyard (requires class metadata)
    if class_meta:
        results["S5"] = S5_implausible_vs_graveyard(card, class_meta)
    
    # S6: Many interims no spending
    results["S6"] = S6_many_interims_no_spending(card)
    
    # S7: Single-arm where RCT standard
    results["S7"] = S7_single_arm_where_rct_standard(card, rct_required)
    
    # S8: p-value cusp/heaping
    results["S8"] = S8_pvalue_cusp_or_heaping(card, program_pvals)
    
    # S9: OS/PFS contradiction
    results["S9"] = S9_os_pfs_contradiction(card)
    
    return results


def get_fired_signals(results: Dict[str, SignalResult]) -> Dict[str, SignalResult]:
    """Get only the signals that fired."""
    return {k: v for k, v in results.items() if v.fired}


def get_high_severity_signals(results: Dict[str, SignalResult]) -> Dict[str, SignalResult]:
    """Get only high severity signals."""
    return {k: v for k, v in results.items() if v.fired and v.severity == "H"}
