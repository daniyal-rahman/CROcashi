# Catalyst windows + TUI

You’re building a precision‑first “near‑certain failure” detector. Below is a **product+frontend spec** with **concrete inference logic**, **ranking rules**, **component structure**, **data contracts**, and a **minimal TUI code skeleton** that plugs into your Postgres/DuckDB stack.

---

## 1) Catalyst window inference logic

**Goal:** infer an actionable readout window for each pivotal trial using:

* `trials.est_primary_completion_date` (EPCD)
* PR / abstract hints from `studies` (+ extracted fields in Study Cards)
* Per‑sponsor historical slip factor

### 1.1 Inputs

* `trials`: `trial_id, nct_id, sponsor_company_id, sponsor_text, phase, is_pivotal, est_primary_completion_date, status`
* `studies`: PR/Abstract rows with `doc_type in {PR, Abstract}` and `extracted_jsonb` (from LangExtract) containing any of:

  * `readout.expected_date` (ISO date if explicit)
  * `readout.bucket` (one of: {month, quarter, half, year, conference})
  * `readout.month|quarter|half|year`
  * `readout.conference{name, year, start_date, end_date}`
  * `quoted_text`, `evidence_spans[]`, `url`
* `sponsor_slip_stats`: per `company_id`, empirics from history

  * `mean_slip_days`, `p10_days`, `p90_days`, `n_events`, `updated_at`
  * (default fallback if unknown sponsor)

### 1.2 Anchors & certainty

Define **candidate windows** with a certainty weight `w ∈ [0,1]`:

1. **EPCD base anchor** `A_epcd`

   * Window: `[EPCD − 14d, EPCD + 28d]` (reporting lag skewed later)
   * Weight: `w_epcd = 0.4` (if recent EPCD version; reduce if stale)

2. **Exact‑date PR** `A_date`

   * e.g., “topline on Nov 3, 2025”
   * Window: `[date − 1d, date + 2d]`
   * `w_date = 0.95`

3. **Conference PR/abstract** `A_conf`

   * “results at **ESMO 2025**” with known `start/end`
   * Window: `[conf_start − 2d (embargo), conf_end + 1d]`
   * `w_conf = 0.8` (increase to 0.9 if embargo‑style journal noted)

4. **Quarter/Half/Year buckets** `A_bucket`

   * `Qx YYYY` → fiscal‑agnostic map (Q1: Jan–Mar, …)
   * `H1 YYYY` / `H2 YYYY` → 6‑month halves
   * `BY END OF YYYY` → Dec 01–Dec 31
   * `w_bucket = 0.6`

> **Recency boost:** multiply `w` by `min(1.0, 0.5 + 0.5·exp(−age_days/180))` using the newest hint per class.

### 1.3 Slip application

Compute slip **shift** and **widening** from sponsor stats:

* `shift_days = clamp(mean_slip_days, −30, +75)`
* `widen_days = max(0, (p90_days − p10_days)/2)` (cap at 45)
* Apply to any anchor window `[s,e]` → `[s + shift − widen_pad, e + shift + widen_pad]`, where `widen_pad = min(14, widen_days)`

### 1.4 Window fusion

From all candidate windows `Wi` with weights `wi` (after slip):

* Compute **intersection** `W∩` of top‑2 highest‑weight anchors if they overlap; else **weighted union** minimizing span length (`argmin span` with coverage of high‑weight windows).
* **Certainty**: `certainty = 1 − sigmoid(span_days/30) · (1 − w_best)` clipped to `[0,1]`.
* If **status ∈ {Completed, Terminated}** and label already exists, mark `certainty=1`, `window=[label.event_date,label.event_date]`.

### 1.5 Output

`catalysts` record per trial:
`(trial_id, window_start, window_end, certainty, sources[])`, where `sources` includes `{anchor_type, raw_text, study_id, url}`.

---

## 2) Ranking: P\_fail then proximity

Create **rank key**:
`key = (−p_fail, proximity_score, −certainty)`

* `p_fail`: from latest `scores` (select most recent `run_id` per `trial_id`).
* `proximity_score`: days until **window\_mid** if `window_end ≥ today`, else large positive penalty (deprioritize past windows). Use:
  `proximity_score = max(0, (window_mid − today).days)`
  If window already open (today within window), use `0`.
* Ties: higher `certainty`, then later `phase` (III > II/III > II), then lexicographic ticker.

---

## 3) Data layer & contracts

### 3.1 Tables / views

```sql
-- Slip stats (materialized from label history)
CREATE TABLE IF NOT EXISTS sponsor_slip_stats (
  company_id BIGINT PRIMARY KEY,
  mean_slip_days INT NOT NULL,
  p10_days INT NOT NULL,
  p90_days INT NOT NULL,
  n_events INT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Latest score per trial
CREATE VIEW v_latest_scores AS
SELECT DISTINCT ON (trial_id)
  trial_id, run_id, p_fail, logit_post, sum_log_lr
FROM scores
ORDER BY trial_id, run_id DESC;

-- Dashboard feed: trials with catalyst window
CREATE VIEW v_trial_catalysts AS
SELECT t.trial_id, t.nct_id, t.phase, t.is_pivotal,
       c.window_start, c.window_end, c.certainty,
       s.p_fail,
       array_remove(array[CASE WHEN g1.fired_bool THEN 'G1' END,
                            CASE WHEN g2.fired_bool THEN 'G2' END,
                            CASE WHEN g3.fired_bool THEN 'G3' END,
                            CASE WHEN g4.fired_bool THEN 'G4' END], NULL) AS gates
FROM trials t
JOIN v_latest_scores s USING (trial_id)
JOIN catalysts c USING (trial_id)
LEFT JOIN LATERAL (
  SELECT fired_bool FROM gates WHERE trial_id=t.trial_id AND g_id='G1'
) g1 ON TRUE
LEFT JOIN LATERAL (
  SELECT fired_bool FROM gates WHERE trial_id=t.trial_id AND g_id='G2'
) g2 ON TRUE
LEFT JOIN LATERAL (
  SELECT fired_bool FROM gates WHERE trial_id=t.trial_id AND g_id='G3'
) g3 ON TRUE
LEFT JOIN LATERAL (
  SELECT fired_bool FROM gates WHERE trial_id=t.trial_id AND g_id='G4'
) g4 ON TRUE
WHERE t.is_pivotal IS TRUE;
```

### 3.2 App contracts (Pydantic‑ish)

```python
class EvidenceSpan(TypedDict):
    study_id: int
    source_type: Literal["PR","Abstract","Registry","FDA","Paper"]
    url: str
    quote: str
    page: int | None

class WhyGate(TypedDict):
    gate_id: Literal["G1","G2","G3","G4"]
    fired: bool
    lr_used: float | None
    rationale: str
    supporting_spans: list[EvidenceSpan]

class CatalystItem(TypedDict):
    trial_id: int
    nct_id: str
    ticker: str
    phase: str
    window_start: date
    window_end: date
    certainty: float
    p_fail: float
    gates: list[str]

class BacktestPoint(TypedDict):
    k: int
    precision: float

class BacktestPayload(TypedDict):
    curve: list[BacktestPoint]  # Precision@K for K=1..Kmax
    misses: list[dict]  # false negatives/positives with brief reason
```

---

## 4) TUI design (Textual)

**Views**

1. **Dashboard** (default)

   * **DataTable**: columns `[Ticker, Phase, Window, D‑to‑Mid, P_fail, Gates]`
   * Sort: `P_fail desc, proximity asc`
   * Filter bar: `[Only Open Windows] [≥ P_fail τ] [Phase filter] [Ticker search]`
   * Keybindings: `Enter=Why`, `B=Backtest`, `/=Search`, `F=Filters`, `R=Refresh`
2. **Why drawer** (modal right panel)

   * Header: trial title (Ticker · NCT · Phase)
   * Sections per Gate (chips: G1..G4, fired highlighted)
   * Evidence spans list with **open link** action
3. **Backtest** tab

   * ASCII **Precision\@K** chart (K=1..10)
   * Miss list table: `[Date, Ticker, NCT, P_fail@freeze, Outcome, Reason]`

**Empty states**: no catalysts, no misses, etc.

---

## 5) Minimal code skeleton

> **Deps:** `pip install textual rich psycopg[binary] pydantic duckdb`

### 5.1 Catalyst inference (`src/ncfd/catalyst/infer.py`)

```python
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Literal, NamedTuple

# ---------------------------- Models ----------------------------

@dataclass
class SlipStats:
    mean_slip_days: int
    p10_days: int
    p90_days: int

@dataclass
class StudyHint:
    kind: Literal["exact_date","conference","quarter","half","year","freeform"]
    start: date
    end: date
    weight: float
    raw_text: str
    study_id: int
    url: str | None = None

@dataclass
class CatalystWindow:
    start: date
    end: date
    certainty: float
    sources: list[StudyHint]

# ---------------------------- Parsing helpers ----------------------------

_QMAP = {1: (1,3), 2: (4,6), 3: (7,9), 4: (10,12)}
_HALF_MAP = {1: (1,6), 2: (7,12)}
_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"], start=1)}

MONTH_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(\d{4})\b", re.I)
QUARTER_RE = re.compile(r"\bQ([1-4])\s*(20\d{2})\b", re.I)
HALF_RE = re.compile(r"\bH([12])\s*(20\d{2})\b", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\b")

# ---------------------------- Core logic ----------------------------

def _apply_slip(s: date, e: date, slip: SlipStats) -> tuple[date,date]:
    shift = max(-30, min(75, slip.mean_slip_days))
    pad = min(14, max(0, (slip.p90_days - slip.p10_days)//2))
    return (s + timedelta(days=shift - pad), e + timedelta(days=shift + pad))

def _w_recency(weight: float, hint_age_days: int) -> float:
    from math import exp
    return weight * min(1.0, 0.5 + 0.5*exp(-hint_age_days/180))

def _fuse(windows: list[tuple[date,date,float,StudyHint]]) -> CatalystWindow:
    # pick top-2 by weight
    windows = sorted(windows, key=lambda w: w[2], reverse=True)
    s1,e1,w1,h1 = windows[0]
    if len(windows) == 1:
        span = (e1 - s1).days
        certainty = max(0.0, min(1.0, 1 - (span/30) * (1 - w1)))
        return CatalystWindow(s1,e1,certainty,[h1])
    s2,e2,w2,h2 = windows[1]
    # intersect if overlap
    inter_s = max(s1,s2)
    inter_e = min(e1,e2)
    if inter_s <= inter_e:
        span = (inter_e - inter_s).days
        best_w = max(w1,w2)
        certainty = max(0.0, min(1.0, 1 - (span/30) * (1 - best_w)))
        return CatalystWindow(inter_s, inter_e, certainty, [h1,h2])
    # else weighted union preferring shorter
    union_s = min(s1,s2); union_e = max(e1,e2)
    span = (union_e - union_s).days
    best_w = max(w1,w2)
    certainty = max(0.0, min(1.0, 1 - (span/45) * (1 - best_w)))
    return CatalystWindow(union_s, union_e, certainty, [h1,h2])

def infer_window(
    epcd: date,
    epcd_version_age_days: int,
    hints: Iterable[tuple[StudyHint, int]],  # (hint, age_days)
    slip: SlipStats,
) -> CatalystWindow:
    # Anchor 1: EPCD base
    base_s, base_e = epcd - timedelta(days=14), epcd + timedelta(days=28)
    base_s, base_e = _apply_slip(base_s, base_e, slip)
    w_epcd = _w_recency(0.4, epcd_version_age_days)
    candidates: list[tuple[date,date,float,StudyHint]] = []
    base_hint = StudyHint("freeform", base_s, base_e, w_epcd, raw_text="EPCD base", study_id=0)
    candidates.append((base_s, base_e, w_epcd, base_hint))

    # Anchors from hints
    for hint, age_days in hints:
        s,e = _apply_slip(hint.start, hint.end, slip)
        candidates.append((s,e, _w_recency(hint.weight, age_days), hint))

    return _fuse(candidates)
```

### 5.2 Ranking & proximity (`src/ncfd/catalyst/rank.py`)

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import date

@dataclass
class Ranked:
    trial_id: int
    ticker: str
    phase: str
    window_start: date
    window_end: date
    certainty: float
    p_fail: float
    gates: list[str]

    def key(self, today: date) -> tuple[float,int,float,str]:
        mid = self.window_start + (self.window_end - self.window_start)/2
        days_to_mid = max(0, (mid - today).days) if self.window_end >= today else 9999
        return (-self.p_fail, days_to_mid, -self.certainty, self.ticker)

def sort_rank(items: list[Ranked], today: date) -> list[Ranked]:
    return sorted(items, key=lambda r: r.key(today))
```

### 5.3 Backtest (`src/ncfd/catalyst/backtest.py`)

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from collections import defaultdict

@dataclass
class Label:
    trial_id: int
    event_date: date
    primary_outcome_success: bool  # False => failure

@dataclass
class Snapshot:
    trial_id: int
    date: date
    p_fail: float

# Evaluate Precision@K by freezing 14d pre-event

def precision_at_k(snapshots: list[Snapshot], labels: list[Label], Kmax: int = 10):
    by_trial = defaultdict(list)
    for s in snapshots:
        by_trial[s.trial_id].append(s)

    curve = []
    misses = []
    for lab in labels:
        freeze_day = lab.event_date - timedelta(days=14)
        snaps = [s for s in by_trial[lab.trial_id] if s.date == freeze_day]
        if not snaps:
            misses.append({"trial_id": lab.trial_id, "reason": "no snapshot", "date": lab.event_date})
            continue
        # In practice you'd rank universe on freeze_day; here assume `rank_on(freeze_day)` produced a list
        pass  # placeholder: integrate with sort_rank over all trials available on freeze_day

    # Stub: return empty curve until integrated
    for k in range(1, Kmax+1):
        curve.append({"k": k, "precision": 0.0})
    return {"curve": curve, "misses": misses}
```

### 5.4 TUI skeleton (`app/tui.py`)

```python
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header, Footer, Static
from textual.containers import Horizontal
from textual.reactive import reactive
from datetime import date

class TrialsTable(DataTable):
    def on_mount(self):
        self.cursor_type = "row"
        self.add_columns("Ticker","Phase","Window","D-to-Mid","P_fail","Gates")

class WhyDrawer(Static):
    visible = reactive(False)
    def show_for(self, trial_id: int):
        # TODO: load gate rationales + evidence spans (links)
        self.update(f"[b]Why[/b] for trial {trial_id}\n\n- G1: …\n- Evidence: …")
        self.visible = True

class BacktestView(Static):
    def show_curve(self, payload):
        ascii_plot = "\n".join([f"K={p['k']:2d} | {'#'*int(p['precision']*20)}" for p in payload['curve']])
        self.update("Precision@K\n" + ascii_plot)

class CatalystTUI(App):
    CSS = """
    Screen { layout: horizontal; }
    TrialsTable { width: 75%; }
    #why { width: 25%; border: solid green; }
    """
    BINDINGS = [
        ("b","backtest","Backtest"),
        ("r","refresh","Refresh"),
        ("enter","why","Why")
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            self.table = TrialsTable()
            yield self.table
            self.drawer = WhyDrawer(id="why")
            yield self.drawer
        yield Footer()

    def on_mount(self):
        # TODO: query DB for initial ranked list
        rows = [
            ("ABCD","III","2025-10-01 → 2025-10-20", 40, 0.92, "G1,G3"),
        ]
        for r in rows:
            self.table.add_row(*map(str, r))

    def action_why(self):
        row = self.table.cursor_row
        if row is not None:
            # TODO: map row -> trial_id
            self.drawer.show_for(trial_id=123)

    def action_backtest(self):
        # Swap view to a simple backtest panel (or push a new screen)
        bt = BacktestView()
        payload = {"curve": [{"k":1,"precision":0.8},{"k":3,"precision":0.67}], "misses": []}
        bt.show_curve(payload)
        self.push_screen(bt)

if __name__ == "__main__":
    CatalystTUI().run()
```

---

## 6) Integration notes

* **Source of truth** for gate evidence: `gates` + `signals` joined to `studies` via `source_study_id`; surface `evidence_span` + `url` in the drawer.
* **Ticker**: from robust mapping (companies ↔ securities); prefer listed parent via your resolver.
* **Freeze policy (backtest)**: use snapshot at `label.event_date − 14d` (already in your scoring plan). Persist a daily `universe` view or derive on the fly from versioned `catalysts`.
* **Performance**: materialize `v_trial_catalysts` monthly and re‑compute daily deltas; the TUI can hit a single `SELECT … ORDER BY p_fail DESC, proximity ASC LIMIT 200`.

---

## 7) QA checklist (succinct)

* [ ] Hint parser recognizes exact dates, Qx, Hx, year, conference tokens.
* [ ] Slip factors applied and capped; unknown sponsor falls back to default.
* [ ] Certainty increases when windows shrink via overlapping anchors.
* [ ] Ranking respects `P_fail` first, then proximity, then certainty.
* [ ] Drawer shows clickable evidence links with quotes.
* [ ] Backtest honors T−14 freeze and reports Precision\@K + miss list.

---

**Next steps**: wire DB queries, flesh out `backtest.precision_at_k` using real freeze‑day universes, and plug evidence spans into the drawer. This skeleton is deliberately minimal but drop‑in with your repo layout.
