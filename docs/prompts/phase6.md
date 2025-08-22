Got it—here’s a tight, precision-first implementation of S1–S9 with formulas, inputs, thresholds, failure modes, plus Python-style pseudocode and unit tests using synthetic Study Cards that *intentionally* trip each signal.

I kept the APIs minimal and opinionated so you can drop this into `ncfd/signals/primitives.py` (or parallel) and wire to your `signals(...)` table writer.

---

# Detector specs (what each looks at, how it fires)

### S1 — Endpoint changed (material & late)

* **Inputs (from `trial_versions`)**: `version_id, captured_at, primary_endpoint_text, changes_jsonb, est_primary_completion_date`
* **Algorithm (high-precision)**

  1. Normalize endpoint text → concept id (e.g., {PFS, OS, ORR, PRO, NI/SI flag, timepoint, assessment method}).
  2. Diff consecutive versions.
  3. “Material change” if any of: endpoint concept class changes (e.g., PFS→OS, ORR→PFS), objective→subjective, NI↔SI toggle, primary timepoint shortened/extended ≥25%, blinded→open.
  4. “Late” if change occurs **after trial start** or within **≤180 days of `est_primary_completion_date`** (use whichever is stricter), or explicitly after FPI/LPR if known in `changes_jsonb`.
* **Thresholds**: fire when (material **AND** late). Severity `H` if within 180d of primary completion; otherwise `M`.
* **Failure modes**: registry hygiene edits; clarifications with same estimand; multiple co-primaries pre-specified but posted sequentially.

---

### S2 — Underpowered pivotal (<70% power at claimed Δ)

**We compute power at the *claimed* alternative (or MCID fallback) using actual N/alloc and α. Fire only when inputs are sufficiently known.**

#### A) Two-arm proportions (e.g., ORR)

* **Inputs (Study Card)**: `n_t, n_c, alpha, tail(one/two), assumed_p_c, assumed_delta_abs (p_t - p_c) OR assumed OR`, optional `continuity_correction=False`.
  If only odds ratio θ is given, convert: choose `p_t = θ p_c / (1 - p_c + θ p_c)`.
* **Defaults (only if missing, to keep precision)**:
  `alpha=0.025` one-sided (pivotal norm) or `0.05` two-sided if analysis plan says so; if `assumed_p_c` missing, use *observed control rate from prior phase / historical class prior*—else **no fire**; if Δ missing, use MCID table (indication × endpoint), e.g., ORR MCID = **+12% abs** oncology unless plan states otherwise (still mark as `LowCertInputs=True` and don’t fire unless power <55%).
* **Test statistic & power (normal approx, unpooled SE)**
  Let `Δ = p_t - p_c`, `SE_H1 = sqrt(p_t(1-p_t)/n_t + p_c(1-p_c)/n_c)`.
  Critical value: `zα = Φ^{-1}(1-α)` (one-sided) or `Φ^{-1}(1-α/2)` (two-sided).
  **Power ≈ Φ( |Δ|/SE\_H1 - zα )**.
  (Use continuity correction `-0.5*SE_H1 / sqrt(n_eff)` if you want extra conservatism; default off to avoid over-penalizing.)
* **Fire rule**: if `is_pivotal` and `Power < 0.70` at the *claimed* Δ. If using MCID fallback, require `Power < 0.55` to fire (`severity=M`, `low_cert_inputs=True`).
* **Failure modes**: blinded sample-size re-estimation planned; adaptive enrichment; strong correlation to interim event rates; mis-extracted Δ.

#### B) Time-to-event (e.g., PFS/OS; log-rank / Cox)

* **Inputs**: `alpha, two_sided?, allocation_ratio k=n_t/n_c, planned_events D (or observed_events), HR_alt (θ_alt <1 for benefit)`.
  Optional: `followup_months, accrual_profile` to estimate `D` if not explicit.
* **Defaults**: `alpha=0.05` two-sided unless plan says 0.025 one-sided; if `D` missing and *neither* `events` nor a credible event-fraction model present → **do not fire** (precision-first). If only total N known, you may set rough `D≈0.6·N_total` for chronic symptomatic endpoints **but don’t fire unless power <55%**.
* **Freedman approximation**
  Let `ψ = k/(1+k)^2` (equal alloc → `ψ=0.25`).
  **Power ≈ Φ( sqrt(D·ψ)·|log(HR\_alt)| − z\_{1−α/2} )** (two-sided; use `z_{1−α}` one-sided).
  (Dual view: required events $D_req = (z_{1−α/2}+z_{1−β})^2 / (ψ·(log(HR_alt))^2)$.)
* **Fire rule**: `Power < 0.70` with credible `D`. If `D` is imputed, only fire if `<0.55` and tag `low_cert_inputs=True`.
* **Failure modes**: heavy non-proportional hazards (PH violated), high crossover dilution on OS, informative censoring.

---

### S3 — Subgroup-only win without multiplicity

* **Inputs**: Study Card: overall primary ITT result (estimate & p), subgroup table with `pre_specified?`, `adjusted?`, multiplicity control description.
* **Algorithm**: fire if **(overall ITT non-sig)** *and* **(≥1 subgroup nominal p<0.05)** *and* **(no family-wise control covering that subgroup)** *and* **(subgroup not pre-specified for interaction)**. Increase severity if PR/abstract narrative pivots on that subgroup.
* **Thresholds**: any such subgroup → `severity=H` if highlighted in conclusions; else `M`.
* **Failure modes**: genuine qualitative interaction pre-specified; hierarchical gatekeeping that legitimately unlocks that subgroup; small-n biomarker validation cohorts.

---

### S4 — ITT neutral/neg vs PP positive + dropout asymmetry

* **Inputs**: ITT estimate & p, PP estimate & p, arm-level `dropout_rate`, `protocol_deviation_rate`, `reasons` if present.
* **Algorithm**:

  1. ITT non-sig (or Δ\_ITT ≤ 0 for benefit direction).
  2. PP nominal sig (p<0.05) favoring treatment.
  3. Dropout asymmetry: `|Dropout_t − Dropout_c| ≥ 10%` **and** more exclusions from treatment for outcome-related reasons.
* **Thresholds**: fire if all 3; `severity=H` if asymmetry ≥15% or if unblinded/subjective endpoint.
* **Failure modes**: PP pre-specified for NI margins with rescue meds rules; missing-data handling differs between sets but is justifiable (e.g., tipping point passed but robust).

---

### S5 — Effect size implausible vs class “graveyard”

* **Inputs**: effect size for the primary endpoint; class graveyard meta (distribution of *successful* effect sizes for same modality/target/indication line).
* **Algorithm**: if class is flagged `graveyard=True` and claimed effect size ≥ **P75** (or **P90** for more caution) of historical *winners*, flag plausibility risk. (E.g., NASH F2-F3 biopsy CRN, Alzheimer’s MCI CDR-SB, etc.)
* **Thresholds**: default P75; bump to P90 if Study Card quality high but external replication absent.
* **Failure modes**: new MoA with step-change efficacy; improved endpoint assay; enriched populations.

---

### S6 — Multiple interim looks without alpha spending

* **Inputs**: analysis plan text (number/timing of interims), presence of alpha-spending function (O’Brien-Fleming/Pocock), press/news timeline of “topline” peeks.
* **Algorithm**: if `planned_interims ≥ 2` **and** **no** spending plan or gatekeeping specified **and** claims of nominal p<0.05 at an interim → fire. Also fire if actual peeks exceed plan without alpha re-allocation.
* **Thresholds**: `severity=H` if >2 looks or if predictive enrichment mid-trial changed.
* **Failure modes**: DMC looks with strict firewalls; binding futility only; blinded sample-size re-estimation (BSSR).

---

### S7 — Single-arm pivotal where RCT is standard of evidence

* **Inputs**: `is_pivotal`, design (`single_arm?`), indication line, FDA precedent table (oncology special cases, ultra-rare, dramatic ORR with DoR, etc.).
* **Algorithm**: fire if pivotal & single-arm & indication not in a list of **explicit single-arm-acceptable contexts** (e.g., tumor-agnostic rare with ORR+DoR precedent, or life-threatening ultra-rare with natural history).
* **Thresholds**: `severity=H` outside acceptable list; `M` if borderline.
* **Failure modes**: genuine accelerated approval pathway with strong surrogate + durability.

---

### S8 — p-value cusp/heaping near 0.05

* **Two flavors:**

  1. **Cusp (trial-level)**: primary p in **\[0.045, 0.050]** and either S1 or S3 also fires → flag. (High precision.)
  2. **Heaping (program/sponsor-level statistical test)**: gather all nominal p’s (primary/keys/subgroups) across Study Cards for the program/sponsor. Let `L=[0.045,0.050)`, `R=[0.050,0.055]`. Under smooth density, `P(L)=P(R)`. Test **Binomial(L; n=L+R, p=0.5)** one-sided for excess left mass; require `n≥10`, `p_binom<0.01`, and `count(L) ≥ 2·count(R)`.
* **Inputs**: p-values (+ precision / rounding), list membership (primary/key vs exploratory).
* **Failure modes**: true effects near threshold; rounding to 2 decimals hides 0.051→0.05; multiplicity-adjusted p’s mixed with nominal.

---

### S9 — OS/PFS contradiction (context-aware)

* **Inputs**: PFS HR & p (or median), OS HR & p, events, crossover rate, MoA (early harm plausible?).
* **Algorithm**: if **PFS positive** (p<0.05 or HR<1 with 95% CI<1) but **OS HR ≥ 1.10** (trend to harm) with **≥60% of planned OS events** and **crossover ≤30%** → flag; or if OS median notably worse (≥2 months) without explanation.
* **Thresholds**: `severity=H` if HR\_OS ≥1.20 or harm p<0.10; else `M`.
* **Failure modes**: heavy crossover, post-progression imbalances, immunotherapy delayed separation (PH violation), immature OS.

---

## Shared types (pseudocode)

```python
# primitives.py (pseudocode)

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import math
from statistics import median

@dataclass
class SignalResult:
    fired: bool
    severity: str  # 'H','M','L'
    value: Optional[float] = None  # e.g., computed power or z
    reason: str = ""
    evidence_ids: List[str] = None  # study_id or version_ids
    low_cert_inputs: bool = False

# ---- Helpers ----

def _phi(x: float) -> float:
    # Standard normal CDF (approx ok in pseudocode)
    import mpmath as mp  # or scipy.stats.norm.cdf in real code
    return mp.ncdf(x)

def _z_for(alpha: float, two_sided: bool) -> float:
    # Return critical z
    import mpmath as mp
    a = alpha/2 if two_sided else alpha
    return mp.qfuncinv(a)  # Φ^{-1}(1-α) = qfuncinv(α)

def power_two_proportions(n_t:int, n_c:int, p_c:float, delta_abs:float,
                          alpha:float=0.025, two_sided:bool=False) -> float:
    p_t = max(1e-9, min(1-1e-9, p_c + delta_abs))
    se = math.sqrt(p_t*(1-p_t)/n_t + p_c*(1-p_c)/n_c)
    if se == 0: return 0.0
    z_alpha = _z_for(alpha, two_sided)
    return float(_phi(abs(delta_abs)/se - z_alpha))

def power_logrank(events:int, hr_alt:float, alloc_ratio:float=1.0,
                  alpha:float=0.05, two_sided:bool=True) -> float:
    if events is None or events <= 0 or hr_alt <= 0:
        return 0.0
    psi = (alloc_ratio)/(1+alloc_ratio)**2
    z_alpha = _z_for(alpha, two_sided)
    return float(_phi(math.sqrt(events*psi)*abs(math.log(hr_alt)) - z_alpha))
```

---

## Detectors (pseudocode)

```python
# ---- S1 ----
def S1_endpoint_changed(trial_versions: List[Dict[str, Any]]) -> SignalResult:
    # Expect each: {version_id, captured_at, primary_endpoint_text, changes_jsonb, est_primary_completion_date}
    def to_concept(txt:str) -> Dict[str,str]:
        # very rough concept mapping
        t = txt.lower()
        concept = {}
        concept["class"] = "os" if "overall survival" in t else \
                           "pfs" if ("progression-free" in t or "pfs" in t) else \
                           "orr" if ("objective response" in t or "orr" in t) else "other"
        concept["timepoint"] = "12m" if "12 month" in t or "12-month" in t else \
                               "24m" if "24" in t else "unspecified"
        concept["ni"] = "ni" if "non-inferior" in t or "noninferior" in t else "si"
        concept["blinded"] = "open" if "open-label" in t else "blinded"
        return concept

    if len(trial_versions) < 2:
        return SignalResult(False, "L", reason="single version")
    fired=False; sev="M"; ev=[]
    for a,b in zip(trial_versions, trial_versions[1:]):
        ca, cb = to_concept(a["primary_endpoint_text"] or ""), to_concept(b["primary_endpoint_text"] or "")
        material = (ca["class"] != cb["class"]) or (ca["ni"] != cb["ni"]) or (ca["blinded"] != cb["blinded"]) \
                   or (ca["timepoint"] != cb["timepoint"])
        late = (b["captured_at"] >= a.get("trial_start","2100-01-01")) or \
               (b["est_primary_completion_date"] and \
                (b["est_primary_completion_date"] - b["captured_at"]).days <= 180)
        if material and late:
            fired=True; ev += [a["version_id"], b["version_id"]]
            if (b["est_primary_completion_date"] and
                (b["est_primary_completion_date"] - b["captured_at"]).days <= 180):
                sev="H"
    return SignalResult(fired, sev if fired else "L",
                        reason="Material endpoint change late in registry",
                        evidence_ids=list(dict.fromkeys(ev)))

# ---- S2 ----
def S2_underpowered_pivotal(card: Dict[str,Any]) -> SignalResult:
    if not card.get("is_pivotal", False):
        return SignalResult(False,"L",reason="not pivotal")
    ap = card.get("analysis_plan", {})
    # branch: proportions vs TTE
    if card.get("primary_type") == "proportion":
        n_t, n_c = card["arms"]["t"]["n"], card["arms"]["c"]["n"]
        alpha = ap.get("alpha", 0.025 if ap.get("one_sided", True) else 0.05)
        two_sided = not ap.get("one_sided", True)
        p_c = ap.get("assumed_p_c")
        delta = ap.get("assumed_delta_abs")
        low_cert=False
        if p_c is None:
            p_c = card.get("historical_control_rate")
            if p_c is None:
                return SignalResult(False,"L",reason="missing control rate")
        if delta is None:
            delta = card.get("mcid_abs", 0.12)  # oncology ORR default
            low_cert=True
        pw = power_two_proportions(n_t, n_c, p_c, delta, alpha, two_sided)
        fired = (pw < 0.70 and not low_cert) or (pw < 0.55 and low_cert)
        sev = "H" if pw < 0.55 else "M"
        return SignalResult(fired, sev if fired else "L", value=pw,
                            reason=f"power={pw:.2f} at Δ={delta:.3f}, p_c={p_c:.3f}",
                            evidence_ids=[card["study_id"]], low_cert_inputs=low_cert)

    elif card.get("primary_type") == "tte":
        alpha = ap.get("alpha", 0.05)
        two_sided = ap.get("two_sided", True)
        hr_alt = ap.get("hr_alt")
        events = ap.get("planned_events") or card.get("events_observed")
        low_cert=False
        if hr_alt is None:
            return SignalResult(False,"L",reason="missing HR_alt")
        if events is None:
            if card.get("N_total"):
                events = int(0.6*card["N_total"]); low_cert=True
            else:
                return SignalResult(False,"L",reason="missing events")
        k = ap.get("alloc_ratio", card["arms"]["t"]["n"]/card["arms"]["c"]["n"])
        pw = power_logrank(events, hr_alt, k, alpha, two_sided)
        fired = (pw < 0.70 and not low_cert) or (pw < 0.55 and low_cert)
        sev = "H" if pw < 0.55 else "M"
        return SignalResult(fired, sev if fired else "L", value=pw,
                            reason=f"power={pw:.2f} at HR_alt={hr_alt:.2f}, events={events}",
                            evidence_ids=[card["study_id"]], low_cert_inputs=low_cert)
    return SignalResult(False,"L",reason="unsupported primary_type")

# ---- S3 ----
def S3_subgroup_only_no_multiplicity(card: Dict[str,Any]) -> SignalResult:
    prim = card["primary_result"]["ITT"]
    if prim["p"] < 0.05:
        return SignalResult(False,"L",reason="overall ITT significant")
    flagged = []
    for sg in card.get("subgroups", []):
        if sg["p"] < 0.05 and not sg.get("adjusted", False) and not sg.get("pre_specified_interaction", False):
            flagged.append(sg["name"])
    if flagged:
        sev = "H" if card.get("narrative_highlights_subgroup", False) else "M"
        return SignalResult(True, sev, reason=f"Subgroup-only wins: {flagged}",
                            evidence_ids=[card["study_id"]])
    return SignalResult(False,"L",reason="no unadjusted subgroup-only wins")

# ---- S4 ----
def S4_itt_vs_pp_dropout(card: Dict[str,Any]) -> SignalResult:
    itt, pp = card["primary_result"]["ITT"], card["primary_result"].get("PP")
    if not pp: return SignalResult(False,"L",reason="no PP set")
    drop_t, drop_c = card["arms"]["t"]["dropout"], card["arms"]["c"]["dropout"]
    asym = abs(drop_t - drop_c)
    cond = (itt["p"] >= 0.05 or itt["estimate"] <= 0) and (pp["p"] < 0.05 and pp["estimate"] > 0) and (asym >= 0.10)
    sev = "H" if asym >= 0.15 or card.get("endpoint_subjective_unblinded", False) else "M"
    if cond:
        return SignalResult(True, sev, value=asym, reason=f"Dropout asym={asym:.2f}",
                            evidence_ids=[card["study_id"]])
    return SignalResult(False,"L",reason="no ITT/PP contradiction with asymmetry")

# ---- S5 ----
def S5_implausible_vs_graveyard(card: Dict[str,Any], class_meta:Dict[str,Any]) -> SignalResult:
    if not class_meta.get("graveyard", False):
        return SignalResult(False,"L",reason="class not graveyard")
    eff = card["primary_result"]["effect_size"]
    p75 = class_meta["winners_pctl"].get("p75")
    if p75 is None: return SignalResult(False,"L",reason="no pctl data")
    if eff >= p75:
        sev = "H" if eff >= class_meta["winners_pctl"].get("p90", float("inf")) else "M"
        return SignalResult(True, sev, value=eff, reason=f"effect {eff:.3f} ≥ P75 {p75:.3f}",
                            evidence_ids=[card["study_id"]])
    return SignalResult(False,"L",reason="effect within plausible range")

# ---- S6 ----
def S6_many_interims_no_spending(card: Dict[str,Any]) -> SignalResult:
    ap = card.get("analysis_plan", {})
    looks = ap.get("planned_interims", 0)
    spending = ap.get("alpha_spending", None)
    extra_peeks = card.get("actual_peeks", 0) - looks
    if looks >= 2 and not spending:
        return SignalResult(True, "H", reason="≥2 interims without alpha spending",
                            evidence_ids=[card["study_id"]])
    if extra_peeks > 0 and not ap.get("reallocated_alpha", False):
        return SignalResult(True, "M", reason="extra data peeks without alpha reallocation",
                            evidence_ids=[card["study_id"]])
    return SignalResult(False,"L",reason="interim control adequate")

# ---- S7 ----
def S7_single_arm_where_rct_standard(card: Dict[str,Any], rct_required:bool) -> SignalResult:
    if not card.get("is_pivotal", False): return SignalResult(False,"L",reason="not pivotal")
    if not card.get("single_arm", False): return SignalResult(False,"L",reason="not single-arm")
    if rct_required:
        return SignalResult(True,"H",reason="Pivotal single-arm in setting where RCT is standard",
                            evidence_ids=[card["study_id"]])
    return SignalResult(False,"L",reason="single-arm acceptable per precedent")

# ---- S8 ----
def S8_pvalue_cusp_or_heaping(card: Dict[str,Any], program_pvals: List[float]=None) -> SignalResult:
    p = card["primary_result"]["ITT"]["p"]
    cusp = (0.045 <= p <= 0.050)
    if cusp:
        return SignalResult(True, "M", value=p, reason="primary p in [0.045,0.050]",
                            evidence_ids=[card["study_id"]])
    # Heaping (program-level)
    if program_pvals and len([x for x in program_pvals if 0.045 <= x <= 0.055]) >= 10:
        L = sum(1 for x in program_pvals if 0.045 <= x < 0.050)
        R = sum(1 for x in program_pvals if 0.050 <= x <= 0.055)
        n = L + R
        if n >= 10 and L >= 2*R:
            # one-sided binomial tail P(X>=L | n, 0.5)
            from math import comb
            pval = sum(comb(n,k) for k in range(L,n+1)) / (2**n)
            if pval < 0.01:
                return SignalResult(True,"H", value=pval, reason=f"heaping L={L}, R={R}, p={pval:.4g}")
    return SignalResult(False,"L",reason="no cusp/heaping")

# ---- S9 ----
def S9_os_pfs_contradiction(card: Dict[str,Any]) -> SignalResult:
    pfs = card.get("pfs", {})
    os  = card.get("os", {})
    if not pfs or not os: return SignalResult(False,"L",reason="missing endpoints")
    pfs_pos = (pfs.get("p",1) < 0.05) or (pfs.get("hr",1.0) < 1 and pfs.get("ci95_upper",1.01) < 1)
    os_harm = (os.get("hr",1.0) >= 1.10) and (os.get("events_frac",0) >= 0.60) and (os.get("p",1.0) < 0.20)
    low_xover = (os.get("crossover_rate",0.0) <= 0.30)
    if pfs_pos and os_harm and low_xover:
        sev = "H" if os.get("hr",1.0) >= 1.20 else "M"
        return SignalResult(True, sev, reason=f"PFS positive but OS HR={os['hr']:.2f} with {int(100*os['events_frac'])}% events and low crossover",
                            evidence_ids=[card["study_id"]])
    return SignalResult(False,"L",reason="no clear OS/PFS contradiction")
```

---

## Unit tests (synthetic Study Cards)

> Drop these into `tests/test_signals_primitives_synth.py`. They’re self-contained and each is crafted to trip the signal.

```python
# tests/test_signals_primitives_synth.py (pseudocode / pytest-like)

from ncfd.signals.primitives import *
import datetime as dt

def make_version(vid, txt, cap, pc):
    return dict(version_id=vid, primary_endpoint_text=txt,
                captured_at=cap, est_primary_completion_date=pc, trial_start=pc - dt.timedelta(days=540))

def test_S1_trips_on_late_material_change():
    pc = dt.date(2026,1,1)
    v1 = make_version("v1", "Primary: PFS at 12 months, superiority, blinded", dt.date(2025,1,1), pc)
    v2 = make_version("v2", "Primary: Overall Survival at 24 months, superiority, open-label", dt.date(2025,10,5), pc)
    res = S1_endpoint_changed([v1,v2])
    assert res.fired and res.severity == "H"

def test_S2_proportions_underpowered_at_claimed_delta():
    card = {
      "study_id":"S2a",
      "is_pivotal": True,
      "primary_type": "proportion",
      "arms": {"t":{"n":90,"dropout":0.12}, "c":{"n":90,"dropout":0.05}},
      "analysis_plan": {"alpha":0.025, "one_sided":True, "assumed_p_c":0.20, "assumed_delta_abs":0.08},
      "historical_control_rate":0.20
    }
    res = S2_underpowered_pivotal(card)
    assert res.fired and res.value < 0.70

def test_S2_tte_underpowered_with_events():
    card = {
      "study_id":"S2b",
      "is_pivotal": True,
      "primary_type":"tte",
      "arms":{"t":{"n":250,"dropout":0.10}, "c":{"n":250,"dropout":0.09}},
      "analysis_plan":{"alpha":0.05, "two_sided":True, "hr_alt":0.80, "planned_events":140, "alloc_ratio":1.0},
    }
    res = S2_underpowered_pivotal(card)
    assert res.fired  # power ~ <0.70 with 140 events @ HR=0.8

def test_S3_subgroup_only_no_multiplicity():
    card = {
      "study_id":"S3",
      "primary_result":{"ITT":{"estimate":0.02,"p":0.12}},
      "subgroups":[
        {"name":"Region A","p":0.03,"adjusted":False,"pre_specified_interaction":False},
        {"name":"Age<65","p":0.20,"adjusted":False,"pre_specified_interaction":False},
      ],
      "narrative_highlights_subgroup": True
    }
    res = S3_subgroup_only_no_multiplicity(card)
    assert res.fired and res.severity == "H"

def test_S4_itt_pp_contradiction_with_dropout_asymmetry():
    card = {
      "study_id":"S4",
      "primary_result":{
        "ITT":{"estimate":0.00,"p":0.40},
        "PP":{"estimate":0.15,"p":0.02}
      },
      "arms":{"t":{"n":150,"dropout":0.22}, "c":{"n":150,"dropout":0.06}},
      "endpoint_subjective_unblinded": True
    }
    res = S4_itt_vs_pp_dropout(card)
    assert res.fired and res.severity == "H"

def test_S5_implausible_vs_graveyard():
    card = {"study_id":"S5", "primary_result":{"effect_size":0.35}}
    class_meta = {"graveyard":True, "winners_pctl":{"p75":0.30,"p90":0.40}}
    res = S5_implausible_vs_graveyard(card, class_meta)
    assert res.fired and res.severity == "M"

def test_S6_many_interims_no_spending():
    card = {"study_id":"S6","analysis_plan":{"planned_interims":2},"actual_peeks":2}
    res = S6_many_interims_no_spending(card)
    assert res.fired and res.severity == "H"

def test_S7_single_arm_where_rct_standard():
    card = {"study_id":"S7","is_pivotal":True,"single_arm":True}
    res = S7_single_arm_where_rct_standard(card, rct_required=True)
    assert res.fired and res.severity == "H"

def test_S8_cusp_primary():
    card = {"study_id":"S8","primary_result":{"ITT":{"p":0.0479}}}
    res = S8_pvalue_cusp_or_heaping(card)
    assert res.fired and res.severity == "M"

def test_S8_heaping_program_level():
    pvals = [0.031,0.12,0.046,0.048,0.049,0.049,0.049,0.052,0.053,0.054,0.054,0.10]
    card = {"study_id":"S8b","primary_result":{"ITT":{"p":0.10}}}
    res = S8_pvalue_cusp_or_heaping(card, program_pvals=pvals)
    assert res.fired and res.severity == "H"

def test_S9_os_pfs_contradiction():
    card = {
      "study_id":"S9",
      "pfs":{"hr":0.70,"ci95_upper":0.95,"p":0.03},
      "os":{"hr":1.18,"p":0.12,"events_frac":0.65,"crossover_rate":0.20}
    }
    res = S9_os_pfs_contradiction(card)
    assert res.fired and res.severity == "M"
```

---

## Notes on wiring & storage

* Each detector returns a `SignalResult`. Your caller can map to `signals(trial_id, S_id, value, severity, evidence_span, source_study_id)` by:

  * `value` → numeric summary (e.g., power, dropout asymmetry, OS HR).
  * `evidence_span` → store the specific Study Card spans/fields used (in your extraction layer).
  * `source_study_id` → `study_id` from the card (registry, PR, abstract).
* For S2, persist the exact inputs used: `{alpha, two_sided, n_t, n_c, p_c, delta_abs | hr_alt, events, alloc_ratio, low_cert_inputs}` so audits are easy.
* Freeze features at **T−14d** before catalyst windows as you specified.

---

## Quick MCID & class metadata stubs (for now)

* ORR MCID oncology (non-curative): **12% absolute**
* PFS HR\_alt typical powering: **0.75–0.80**
* OS HR\_alt typical powering: **0.75–0.80**
* Use your class library to replace these with table lookups; until then, keep `low_cert_inputs=True` whenever defaults are used and tighten the fire threshold.

---

If you want, I can adapt this to your existing module layout (`signals/primitives.py`, `tests/test_signals_primitives.py`) and call the right DB writers—just say the word and I’ll inline the glue.
