Got it—here’s a tight, implementation-ready spec + code you can drop into `ncfd/signals/gates.py` and `ncfd/scoring/score.py`, with a clear config format, clamps, stop-rules, and an auditable record.

# 1) Config: LR tables per gate (YAML)

Create `ncfd/config/gate_lrs.yaml`:

```yaml
version: 2025-08-21
config_revision: "gate_lrs.yaml@2025-08-21"

global:
  # Multiplicative LR bounds applied per item before taking logs
  lr_min: 0.25           # floor (winsorize)
  lr_max: 10.0           # cap
  # Logit clamps to avoid numeric blow-ups
  logit_min: -8.0        # ~P=0.0003
  logit_max:  8.0        # ~P=0.9997
  # Prior clamp
  prior_floor: 0.01
  prior_ceil:  0.99

gates:
  G1:
    name: "Alpha-Meltdown"
    definition: "S1 & S2"
    lr: 3.5
    # Optional conditioned LRs if you want to refine by evidence quality, phase, etc.
    by_severity:
      high: 5.0
      medium: 3.5
      low: 2.0

  G2:
    name: "Analysis-Gaming"
    definition: "S3 & S4"
    lr: 3.0

  G3:
    name: "Plausibility"
    definition: "S5 & (S7 | S6)"
    lr: 4.2

  G4:
    name: "p-Hacking"
    definition: "S8 & (S1 | S3)"
    lr: 2.5

primitives:
  # Default approach: primitives contribute ~0 (set to 1.0). You can
  # optionally give small nudges (1.05–1.15) if you later calibrate them.
  default_lr: 1.0
  overrides: {}  # e.g., {S8: 1.10}

stop_rules:
  # If any of these fire, set P_fail = max(P_fail, level) (monotone override)
  endpoint_switched_after_LPR:
    level: 0.97
  pp_only_success_with_missing_itt_gt20:
    level: 0.97
  unblinded_subjective_primary_feasible_blinding:
    level: 0.97
```

# 2) Gates & posterior computation (code)

## `ncfd/signals/gates.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Iterable, Optional, Set

@dataclass
class SignalEvidence:
    S_id: str
    evidence_span: dict  # {source_study_id, quote?, page?, start?, end?}
    severity: Optional[str] = None  # 'low'|'medium'|'high' (optional)

@dataclass
class GateEval:
    gate_id: str
    fired: bool
    supporting_S: List[str]
    supporting_evidence: List[SignalEvidence]
    lr_used: float
    rationale: str

def _has(signals: Set[str], *needed: str) -> bool:
    return all(s in signals for s in needed)

def _has_any(signals: Set[str], *candidates: str) -> bool:
    return any(s in signals for s in candidates)

def evaluate_gates(
    present_signals: Set[str],
    evidence_by_signal: Dict[str, List[SignalEvidence]],
    cfg: dict,
) -> Dict[str, GateEval]:
    """
    present_signals: e.g., {'S1','S2','S5','S7','S8'}
    evidence_by_signal: map S_id -> [SignalEvidence,...]
    cfg: parsed YAML dict for gate LRs
    """
    gcfg = cfg["gates"]
    out: Dict[str, GateEval] = {}

    def choose_lr(gid: str, supports: List[SignalEvidence]) -> float:
        base = gcfg[gid].get("lr", 1.0)
        by_sev = gcfg[gid].get("by_severity", {})
        # If multiple severities, take max to stay precision-first (conservative in our direction)
        if by_sev and supports:
            severities = [e.severity for e in supports if e.severity in by_sev]
            if severities:
                base = max(by_sev[s] for s in severities)
        return float(base)

    # ---- Gate definitions ----
    # G1: Alpha-Meltdown = S1 & S2
    if "G1" in gcfg:
        fired = _has(present_signals, "S1", "S2")
        supports = []
        for sid in ("S1","S2"):
            supports.extend(evidence_by_signal.get(sid, []))
        out["G1"] = GateEval(
            gate_id="G1",
            fired=fired,
            supporting_S=["S1", "S2"] if fired else [],
            supporting_evidence=supports if fired else [],
            lr_used=choose_lr("G1", supports) if fired else 1.0,
            rationale="S1 & S2 present" if fired else "Missing S1 or S2",
        )

    # G2: Analysis-Gaming = S3 & S4
    if "G2" in gcfg:
        fired = _has(present_signals, "S3", "S4")
        supports = []
        for sid in ("S3","S4"):
            supports.extend(evidence_by_signal.get(sid, []))
        out["G2"] = GateEval(
            gate_id="G2",
            fired=fired,
            supporting_S=["S3", "S4"] if fired else [],
            supporting_evidence=supports if fired else [],
            lr_used=choose_lr("G2", supports) if fired else 1.0,
            rationale="S3 & S4 present" if fired else "Missing S3 or S4",
        )

    # G3: Plausibility = S5 & (S7 | S6)
    if "G3" in gcfg:
        fired = "S5" in present_signals and _has_any(present_signals, "S7", "S6")
        supports = []
        for sid in ("S5","S7","S6"):
            supports.extend(evidence_by_signal.get(sid, []))
        out["G3"] = GateEval(
            gate_id="G3",
            fired=fired,
            supporting_S=["S5"] + [s for s in ("S7","S6") if s in present_signals] if fired else [],
            supporting_evidence=supports if fired else [],
            lr_used=choose_lr("G3", supports) if fired else 1.0,
            rationale="S5 & (S7 | S6) present" if fired else "Missing S5 and/or (S7|S6)",
        )

    # G4: p-Hacking = S8 & (S1 | S3)
    if "G4" in gcfg:
        fired = "S8" in present_signals and _has_any(present_signals, "S1", "S3")
        supports = []
        for sid in ("S8","S1","S3"):
            supports.extend(evidence_by_signal.get(sid, []))
        out["G4"] = GateEval(
            gate_id="G4",
            fired=fired,
            supporting_S=["S8"] + [s for s in ("S1","S3") if s in present_signals] if fired else [],
            supporting_evidence=supports if fired else [],
            lr_used=choose_lr("G4", supports) if fired else 1.0,
            rationale="S8 & (S1 | S3) present" if fired else "Missing S8 and/or (S1|S3)",
        )

    return out
```

## `ncfd/scoring/score.py`

```python
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from ncfd.signals.gates import GateEval, SignalEvidence

@dataclass
class StopRuleHit:
    rule_id: str
    level: float
    evidence: List[SignalEvidence]

@dataclass
class ScoreResult:
    prior_pi: float
    logit_prior: float
    sum_log_lr: float
    logit_post: float
    p_fail: float
    gate_evals: Dict[str, GateEval]
    stop_rules_applied: List[StopRuleHit]

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))

def _logistic(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))

def _safe_log_lr(lr: float, lr_min: float, lr_max: float) -> float:
    return math.log(_clamp(lr, lr_min, lr_max))

def apply_stop_rules(
    present_signals: Set[str],
    evidence_by_signal: Dict[str, List[SignalEvidence]],
    cfg: dict,
) -> List[StopRuleHit]:
    hits: List[StopRuleHit] = []
    sr_cfg = cfg.get("stop_rules", {})

    def _maybe(rule_id: str, cond: bool, sigs: List[str]):
        if not cond or rule_id not in sr_cfg:
            return
        ev = []
        for s in sigs:
            ev.extend(evidence_by_signal.get(s, []))
        hits.append(StopRuleHit(rule_id=rule_id, level=float(sr_cfg[rule_id]["level"]), evidence=ev))

    # Endpoint switched post-LPR (we assume S1 encodes endpoint change + a sub-flag you set upstream)
    # If you have a dedicated signal like S1a for "post-LPR", prefer that here.
    _maybe("endpoint_switched_after_LPR", "S1" in present_signals and "S1_post_LPR" in present_signals, ["S1"])

    # PP-only success & ITT missing >20%: assume upstream emits S4 plus S4_gt20_missing
    _maybe("pp_only_success_with_missing_itt_gt20", "S4" in present_signals and "S4_gt20_missing" in present_signals, ["S4"])

    # Unblinded subjective primary where blinding feasible: assume upstream emits S8_subj_unblinded
    _maybe("unblinded_subjective_primary_feasible_blinding", "S8_subj_unblinded" in present_signals, ["S8"])

    return hits

def compute_posterior(
    prior_pi: float,
    gate_evals: Dict[str, GateEval],
    primitive_lrs: Optional[List[float]],
    cfg: dict,
) -> ScoreResult:
    g = cfg["global"]
    pi = _clamp(prior_pi, g["prior_floor"], g["prior_ceil"])
    logit_prior = _logit(pi)

    # Sum log LRs from *fired* gates
    lr_min, lr_max = float(g["lr_min"]), float(g["lr_max"])
    logs: List[float] = []
    for ge in gate_evals.values():
        if ge.fired:
            logs.append(_safe_log_lr(ge.lr_used, lr_min, lr_max))

    # Optionally include primitives (default 1.0 -> log 0). Keep tiny if used later.
    if primitive_lrs:
        for lr in primitive_lrs:
            logs.append(_safe_log_lr(float(lr), lr_min, lr_max))

    sum_log_lr = sum(logs)
    logit_post = _clamp(logit_prior + sum_log_lr, g["logit_min"], g["logit_max"])
    p = _logistic(logit_post)

    return ScoreResult(
        prior_pi=pi,
        logit_prior=logit_prior,
        sum_log_lr=sum_log_lr,
        logit_post=logit_post,
        p_fail=p,
        gate_evals=gate_evals,
        stop_rules_applied=[],
    )

def compute_posterior_with_stops(
    prior_pi: float,
    present_signals: Set[str],
    evidence_by_signal: Dict[str, List[SignalEvidence]],
    gate_evals: Dict[str, GateEval],
    primitive_lrs: Optional[List[float]],
    cfg: dict,
) -> ScoreResult:
    res = compute_posterior(prior_pi, gate_evals, primitive_lrs, cfg)
    hits = apply_stop_rules(present_signals, evidence_by_signal, cfg)
    if hits:
        # Monotone override: no stop rule can *decrease* risk
        forced = max(h.level for h in hits)
        res.p_fail = max(res.p_fail, forced)
    res.stop_rules_applied = hits
    return res
```

# 3) Clamp/cap logic (what’s applied where)

* **LR winsorization (per contributor):** each LR is clamped to `[lr_min, lr_max]` before logging (default `[0.25, 10.0]`).
  Rationale: reduces sensitivity to overconfident calibration and partial dependence among gates.

* **Prior clamp:** `[prior_floor, prior_ceil]` (default `[0.01, 0.99]`) to keep logits finite.

* **Logit clamp:** after summing logs, clamp to `[logit_min, logit_max]` (default `[-8, +8]`) to avoid exploding odds from stacked signals.

All values are in `global` in the YAML.

# 4) Stop-rule overrides (precision-first)

`apply_stop_rules(...)` checks for “hard” conditions and then sets
`P_fail = max(P_fail, level)` with `level ≈ 0.97` by default per your spec.

Examples wired above:

* Endpoint switched **after LPR** (`endpoint_switched_after_LPR`).
* **PP-only** success with **>20% missing ITT** (`pp_only_success_with_missing_itt_gt20`).
* **Unblinded subjective primary** where blinding feasible (`unblinded_subjective_primary_feasible_blinding`).

You can surface these as specific sub-signals upstream (e.g., `S1_post_LPR`, `S4_gt20_missing`, `S8_subj_unblinded`) so the check remains trivial and auditable.

# 5) Worked example (step-by-step math)

Input:

* Prior $\pi_0 = 0.65$
* Fired gates: **G1** and **G3** only
* $\mathrm{LR}_{G1} = 3.5$, $\mathrm{LR}_{G3} = 4.2$
* Primitives ignored (treated as LR=1.0)

Computation:

1. Prior odds
   $O_0 = \frac{\pi_0}{1-\pi_0} = \frac{0.65}{0.35} = 1.857142857...$

2. Combined LR (multiplicative)
   $\mathrm{LR}_{\text{tot}} = 3.5 \times 4.2 = 14.7$

3. Posterior odds
   $O_{\text{post}} = O_0 \times \mathrm{LR}_{\text{tot}} = 1.857142857 \times 14.7 = 27.3$

4. Posterior probability
   $P_{\text{fail}} = \frac{O_{\text{post}}}{1 + O_{\text{post}}} = \frac{27.3}{28.3} \approx 0.96466431$

No clamps bind here (well within bounds), so **$P_{\text{fail}} \approx 0.9647$**.

(Equivalently in logits:
$\text{logit}(\pi_0)=\ln(0.65/0.35)=0.619039$;
$\sum \ln \mathrm{LR}= \ln 3.5 + \ln 4.2 = 1.252763 + 1.435085 = 2.687848$;
$\text{logit}_{\text{post}} = 0.619039 + 2.687848 = 3.306887$;
$\sigma(3.306887)=0.964664$.)

# 6) Audit record (what to store)

Use your existing tables plus one JSON blob for traceability.

**Per-gate rows** (table: `gates`)

* `trial_id`
* `G_id` (`'G1'...'G4'`)
* `fired_bool` (true/false)
* `supporting_S_ids[]` (e.g., `['S1','S2']`)
* `lr_used` (final scalar after any severity selection; before global winsorization)
* `rationale_text` (short one-liner)

**Per-run score row** (table: `scores`)

* `trial_id`
* `run_id`
* `prior_pi`
* `logit_prior`
* `sum_log_lr` (after LR winsorization)
* `logit_post` (after clamp)
* `p_fail`

**Recommended**: add `scores.audit_jsonb` to capture trace details:

```json
{
  "config_revision": "gate_lrs.yaml@2025-08-21",
  "lr_bounds": {"lr_min": 0.25, "lr_max": 10.0},
  "logit_bounds": {"logit_min": -8.0, "logit_max": 8.0},
  "prior": {"raw": 0.65, "clamped": 0.65, "logit": 0.619039},
  "gates": [
    {
      "gate_id": "G1",
      "fired": true,
      "lr_used": 3.5,
      "supporting_S": ["S1","S2"],
      "evidence_spans": [
        {"S_id": "S1", "source_study_id": 123, "quote": "…", "page": 5, "start": 221, "end": 276},
        {"S_id": "S2", "source_study_id": 125, "quote": "…", "page": 2, "start": 77, "end": 132}
      ],
      "rationale": "S1 & S2 present"
    },
    {
      "gate_id": "G3",
      "fired": true,
      "lr_used": 4.2,
      "supporting_S": ["S5","S7"],
      "evidence_spans": [
        {"S_id": "S5", "source_study_id": 131, "quote": "…"},
        {"S_id": "S7", "source_study_id": 131, "quote": "…"}
      ],
      "rationale": "S5 & (S7 | S6) present"
    }
  ],
  "primitives": {
    "used": false,
    "lr_values": []
  },
  "sum_log_lr": 2.687848,
  "logit_post": 3.306887,
  "p_fail": 0.96466431,
  "stop_rules_applied": []
}
```

If you prefer not to alter schema, you can serialize the `gates`/`primitives` detail above into `gates.rationale_text` and `scores.notes_md`—but a dedicated `audit_jsonb` is vastly better for reproducibility.

# 7) Minimal SQL writes (illustrative)

```sql
-- One row per fired gate (example G1, G3)
INSERT INTO gates (trial_id, G_id, fired_bool, supporting_S_ids, lr_used, rationale_text)
VALUES
  ($1, 'G1', true, ARRAY['S1','S2'], 3.5, 'S1 & S2 present'),
  ($1, 'G3', true, ARRAY['S5','S7'], 4.2, 'S5 & (S7|S6) present');

-- Score row
INSERT INTO scores (trial_id, run_id, prior_pi, logit_prior, sum_log_lr, logit_post, p_fail, audit_jsonb)
VALUES
  ($1, $2, 0.65, 0.619039, 2.687848, 3.306887, 0.96466431, $3::jsonb);
```

# 8) Quick unit test sketch

```python
def test_posterior_example(cfg):
    # prior 0.65, G1=3.5, G3=4.2
    from ncfd.signals.gates import GateEval
    ev = {
        "G1": GateEval("G1", True, ["S1","S2"], [], 3.5, ""),
        "G3": GateEval("G3", True, ["S5","S7"], [], 4.2, ""),
        "G2": GateEval("G2", False, [], [], 1.0, ""),
        "G4": GateEval("G4", False, [], [], 1.0, ""),
    }
    res = compute_posterior(0.65, ev, primitive_lrs=None, cfg=cfg)
    assert abs(res.p_fail - 0.96466431) < 1e-6
```

---

This gives you: (1) a clean LR config per gate with global clamps, (2) a posterior function that composes log-odds correctly, (3) robust caps to prevent numeric blow-ups, (4) stop-rules that force high-risk when the “hard” patterns occur, and (5) a complete, replayable audit trail tying gates back to Study Card evidence spans.
