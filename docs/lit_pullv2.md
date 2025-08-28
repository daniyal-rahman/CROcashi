# Checkpoint 1 — Catalog-Only Discovery (U0)

**Goal:** confirm you can discover candidate papers **without** abstracts or PDFs and rank them cheaply.

**You should have**

* A way to search PubMed (or similar) from a trial (NCT id, drug, indication).
* Two tables/collections (or their equivalent):

  * `docs` (one row per paper; pmid/doi/title/journal/year/article\_type/is\_open\_access).
  * `trial_doc_candidates` (link trial↔doc with fields: `stage=0`, `u0` score, `selected=false`).
* A simple U0 (metadata-only) ranking heuristic.

**Do**

* Pick **5 trials** with upcoming/known catalysts.
* For each, run catalog discovery; keep **top-K U0 = 10** per trial.

**Pass if**

* Each trial has ≥5 docs linked; **no abstracts or full texts stored yet**.
* `docs` de-duplicates across trials (the same paper appears once globally, many links).
* U0 produces a **sensible order** (titles with “phase 3 / randomized / NCT0…” bubble up).

---

# Checkpoint 2 — Abstract Stage (U1) + Drop Gate

**Goal:** only pull abstracts for the highest U0, compute U1, and discard low-utility items.

**You should have**

* Abstract storage fields (`abstract_text` or similar) **separate** from `docs`.
* U1 (abstract-based) scorer and a threshold `τ_abstract` (start 0.40).
* Ability to mark a link as `selected=true` or `dropped_reason='low_u1'`.
* `stage` transitions (0→1 when an abstract is fetched).

**Do**

* For those same trials, fetch abstracts for **top-8** U0 per trial.
* Score U1; mark selected vs dropped by threshold.

**Pass if**

* Per trial: **30–60%** of abstracted docs get dropped (low U1). If drop rate <20%, raise threshold; if >70%, lower threshold.
* Abstracts exist **only** for those top-8; others remain metadata-only.
* Links that were dropped keep their citation row but **no abstract text** stored.

---

# Checkpoint 3 — “No PDFs by Default” Guardrail

**Goal:** ensure you are not silently storing full texts/PDFs.

**You should have**

* A config flag or policy: **store\_pdf\_files=false** (text-only if OA is ever fetched).
* Columns/fields for full-text (`fulltext_text/fulltext_sha`) that are **empty** so far.

**Do**

* Inspect storage for all trials processed so far.

**Pass if**

* **Zero** full-text blobs present.
* Storage contains only citation rows and a small set of abstracts.

---

# Checkpoint 4 — Pull-On-Demand Full Text (OA only)

**Goal:** prove you can fetch **one** OA full text when explicitly requested, set TTL, and keep it tiny (text, not PDF).

**You should have**

* A flag on a candidate link like `needs_fulltext=true` (how you set it is up to you).
* Ability to fetch **open-access** normalized text, store as text (no PDF), and set a **TTL (e.g., 90 days)** for non-candidates.

**Do**

* For **one trial**, pick **one** selected abstract and mark it as needing full text.
* Fetch OA text (if not OA, skip and log “paywalled”).

**Pass if**

* Exactly **1 doc** gains `fulltext_text` and a TTL date; **no PDF file** saved.
* If the chosen doc is not OA, the system **refuses** to store the PDF and logs why.

---

# Checkpoint 5 — Periodic Eval & Early-Stop (Simulation)

**Goal:** prove your state machine changes status based on incremental evidence, **before** wiring a real LLM.

**You should have**

* A per-trial state row: `p_short` (start \~0.30), `n_docs_seen`, `status` (active|promoted|parked|stopped), and thresholds `θ_high=0.80`, `θ_low=0.20`.
* A way to record a batch review step (even manual) that updates `p_short` after each **M=3** abstracts.

**Do (manual simulation)**

* For 2 trials, pretend to review 3 abstracts:

  * Trial A: mark them as **negative signals** (“did not meet primary / non-significant”).
  * Trial B: mark them as **positive/robust** (“met primary / significant improvement”).
* After each batch, **manually** adjust `p_short` up/down (e.g., +0.15 for strong negative batch, –0.10 for strong positive batch) and write the new value.

**Pass if**

* Trial A crosses `θ_high` → status becomes **promoted**.
* Trial B drops near/under `θ_low` → status becomes **parked** with a revisit TTL.
* If neither crosses, but two consecutive updates change `p_short` by <0.03 **and** no remaining doc has U1>0.50, set status **stopped** (early stop due to low expected gain).

---

# Checkpoint 6 — Global Re-Prioritization

**Goal:** confirm the outer queue reorders trials by **expected value per cost**, not FIFO.

**You should have**

* A priority formula that includes:

  * time-to-catalyst weight,
  * `p_short * uncertainty` (uncertainty \~ `p*(1-p)`),
  * best remaining `U1` among not-yet-reviewed docs.

**Do**

* Compute priority for your 5 trials after Checkpoint 5 updates.
* Identify which trial surfaces to the top.

**Pass if**

* The trial with **near-term catalyst** and **high p\_short but moderate uncertainty** rises above others.
* A trial that’s **parked** does **not** return to the top unless its revisit TTL has elapsed.

---

# Checkpoint 7 — Budget & Storage Accounting

**Goal:** verify you can see and control spend and storage at a glance.

**You should have**

* Daily counters: abstracts fetched, OA full texts fetched, tokens used (if any), bytes stored.
* Per-trial caps (e.g., max 8 abstracts, max 2 OA full texts).

**Do**

* Review counters for the day you ran the checks.

**Pass if**

* Per-trial and per-day caps were respected.
* Storage footprint is mostly **titles + abstracts**; full-text rows are rare (≤1–2 per trial).
* No paywalled PDFs exist in storage.

---

# Checkpoint 8 — Drift/QA Sampling

**Goal:** ensure the drop gate isn’t hiding valuable items.

**You should have**

* A sampling rule: **review 10%** of items dropped for `low_u1`.

**Do**

* From recently dropped abstracts, randomly pick a few and read them manually.

**Pass if**

* You judge ≥90% of sampled drops as correct “low value.”
* If not, adjust `τ_abstract` or U1 features and re-run Checkpoint 2 on a small batch.

---

## When all 8 pass

You’ve proven:

* discovery without PDFs,
* abstract gating works,
* OA full text is **only** pull-on-demand,
* early stopping shifts trials to **promoted/parked/stopped** states,
* the outer queue **reprioritizes** by expected gain,
* and spend/storage are bounded.

Once these are green, it’s safe to plug in a small LLM summary/eval pass (on **abstract summaries only**) and repeat Checkpoints 5–6 with real outputs.
