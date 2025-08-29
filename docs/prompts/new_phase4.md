---

# PubMed Literature Plan (R/S-driven) — Scope, Files, DB, Flow

## 0) Scope & principles

* **Scope now:** PubMed (titles + abstracts via E-utilities) and **optional** PMC **open-access full text (text only)** when explicitly needed.
* **Do not** fetch or store paywalled PDFs. Store **citations + abstracts** for nearly everything; **OA full-text text** only for a small subset (R3S3 / R3S2).
* **Two independent axes per doc:**

  * **R (Relevance)** to *this* trial/asset/indication/line (R0–R3 tiers).
  * **S (Shortability)** risk signal from claims/numbers (S0–S3 tiers).
* **Per-trial actions** come from the **R×S cell**, not from a single blended score.
* **Outer queue** uses the **best S among R≥2**, time-to-catalyst, and uncertainty to reprioritize trials.

---

## 1) Repo layout (no code yet, just structure)

```
ncfd/
  src/ncfd/ingest/pubmed/
    query_builder.md        # spec for building ESearch queries per trial
    client.md               # spec for batched ESearch/ESummary/EFetch, rate limits, retries
    mapper.md               # mapping PubMed fields → our staging tables
    pipeline.md             # end-to-end steps & state transitions
  src/ncfd/extract/
    abstract_features.md    # regex/heuristics to extract numbers/claims from abstracts
  src/ncfd/score/
    rs_spec.md              # full definition of R and S components, thresholds, ties
    rs_config.yaml          # tunables: thresholds, weights, phrases, effect-size caps
  src/ncfd/orchestrate/
    lit_queue.md            # global trial queue policy & periodic reprioritization
    early_stopping.md       # stop rules (θ_high/θ_low/plateau), sample rates, TTLs
  migrations/               # alembic revisions for new/edited tables (later)
  docs/runbooks/
    pubmed_runbook.md       # ops playbook: daily cadence, quotas, QA checks
```

**Hooks for future sources**
Keep source-agnostic tables and a `source_type` enum that already includes: `PubMed`, `PMC`, `PR`, `Conference`, `SEC`, `Registry`, `FDA`. (We’ll only fill `PubMed`/`PMC` now.)

---

## 2) Database model (suggested tables & columns)

> Format below = **table** → key columns & notes (not SQL). Use your normal naming (snake\_case) and enums.

### 2.1 Document core (source-agnostic; reuse if you already have similar)

* **documents**

  * `doc_id (PK)`
  * `source_type` = `PubMed | PMC | PR | Conference | ...`
  * `publisher` (e.g., “PubMed / NLM”, “PMC”)
  * `published_at` (UTC)
  * `sha256` (of the *normalized text blob* you store; abstracts are tiny)
  * `storage_uri` (object storage path to the normalized text; not PDFs)
  * `status` = `discovered | fetched | parsed | indexed | linked | scored | parked | error`
  * `error_msg`
  * **Indexes:** `(source_type, published_at DESC)`, `(status)`, `(sha256)`

* **document\_citations** (1:1 with documents)

  * `doc_id (FK)`
  * `pmid`, `pmcid`, `doi`
  * `journal`, `volume`, `issue`, `pages`, `article_type`, `pub_year`
  * `mesh_jsonb` (full MeSH terms), `substances_jsonb` (agent names)

* **document\_text** (1:1 with documents; abstracts + optional OA full text)

  * `doc_id (FK)`
  * `abstract_text` (nullable)
  * `fulltext_text` (nullable; **PMC OA text only**)
  * `fulltext_ttl_date` (nullable; set for non-candidates to auto-expire)
  * `char_count_abstract`, `char_count_fulltext`

* **document\_entities** (optional pre-facts cache for speed; from abstracts)

  * `doc_id (FK)`
  * `ent_type` in `{endpoint, effect_size, p_value, ci, hr, rr, orr, n_total, population, subgroup, phase, design, control_type, nct_id, asset_name, moa}`
  * `value_text`, `value_norm`, `char_start`, `char_end`, `detector` (e.g., `regex`)

* **document\_links** (coarse linking to trials/assets; promotion happens elsewhere)

  * `doc_id (FK)`
  * `nct_id` (nullable)
  * `asset_id` (nullable)
  * `company_id` (nullable)
  * `link_type` (e.g., `nct_in_text`, `asset_in_mesh`, `asset_in_text`)
  * `confidence` (0–1)

### 2.2 PubMed-specific metadata (kept separate so other sources stay clean)

* **pubmed\_meta** (1:1 for `source_type=PubMed`)

  * `doc_id (FK)`
  * `pmid` (dup for fast joins), `medline_xml_sha` (hash of raw MEDLINE), `language`, `authors_jsonb`, `affiliations_jsonb`
  * `esummary_jsonb` (for audit), `efetch_header_jsonb` (for audit)

* **pmc\_meta** (1:1 for `source_type=PMC`)

  * `doc_id (FK)`
  * `pmcid`, `license`, `oa_route` (e.g., OA subset), `oai_identifier`

### 2.3 Trial ↔ doc relationship & scoring

* **trial\_doc\_candidates** (many\:many)

  * `trial_id (FK trials)`
  * `doc_id (FK documents)`
  * `stage` = `U0_meta | U1_abstract | OA_fulltext`
  * `selected (bool)` (survived threshold) / `dropped_reason`
  * `notes`

* **doc\_rs\_scores** (one per doc per trial; R/S are trial-specific)

  * `trial_id`, `doc_id` (composite PK)
  * `R_score` (0–1), `R_tier` (R0–R3)
  * `S_score` (0–1), `S_tier` (S0–S3)
  * `R_components_jsonb` (directness, phase, recency, article\_type, human vs animal, line-match)
  * `S_components_jsonb` (direction text hits, effect magnitudes, CI quality, design fragility, safety flags)
  * `decided_at`

* **trial\_lit\_state** (rollup per trial)

  * `trial_id (PK)`
  * `best_S_Rge2` (max S among docs with R≥2)
  * `n_docs_seen`, `n_docs_selected`
  * `p_short` (posterior)
  * `uncertainty`
  * `max_expected_utility_next_doc`
  * `status` = `active | stopped | parked | promoted`
  * `decided_at`

**Indexes to add:**

* `trial_doc_candidates(trial_id, stage)`
* `doc_rs_scores(trial_id, R_tier, S_tier)`
* `trial_lit_state(status, best_S_Rge2 DESC)`

---

## 3) R/S scoring spec (title+abstract)

### 3.1 Relevance R (independent of S)

* **R3:** same asset/INN (or unambiguous alias), same indication/line, **mentions NCT** or is the protocol/results for the exact study; human P2/P3.
* **R2:** same asset & indication but different line; or same MOA/classmate in identical indication; or systematic review/meta including the asset.
* **R1:** same asset preclinical/P1; or classmate human data in indication; general reviews/guidelines.
* **R0:** off-topic.

**R components (examples for `R_components_jsonb`):**

* Directness: `same_asset`, `same_nct`, `same_indication`, `same_lot` (line of therapy).
* Human phase: `P3/P2/P1/preclinical`.
* Recency vs catalyst window (±18 months bonus).
* Article type (RCT/Results > Review > Editorial).
* Population match (adult/peds/biomarker-defined).

### 3.2 Shortability S (independent of R)

* **S3:** explicit failure/futility/non-inferiority miss; ITT non-sig with PP-only win; subgroup/post-hoc only; HR≥\~1.15 with CI mostly unfavorable; discontinuations materially worse.
* **S2:** mixed picture; barely-met primary with key secondary failures; underpowered pivotal; open-label when blinding feasible; multiple interims with weak adjustment.
* **S1:** neutral/low concern; early positive with caveats; surrogate only.
* **S0:** robust success: well-powered primary met + consistent secondaries; strong margins.

**S components:**

* **Direction text hits:** “did not meet primary”, “futility”, “non-inferiority not demonstrated”, “trend only”, “post-hoc”, “subgroup”, “PP not ITT”, “interim”.
* **Effect magnitude (normalized):** HR/OR/RR/Δ/ORR gap → convert to unified unfavorable magnitude; halve weight if CI crosses null or p≈0.05–0.15.
* **Design fragility:** single-arm pivotal, open-label, small N for claim, poor control, multiplicity.
* **Safety:** discontinuations/SAEs vs control.

> **Important:** compute R and S **per (trial, doc)** because relevance depends on the target trial; the same paper can be R2 for one trial and R3 for another.

---

## 4) PubMed pipeline (E-utilities) — states & decisions

### 4.1 Query construction (per trial)

* **Inputs:** trial’s `asset_aliases` (INN, codes), indication keywords/MeSH, line-of-therapy markers, optional NCT id, MOA/class synonyms, catalyst window (±18 months focus).
* **ESearch**: build boolean queries with AND/OR blocks for asset synonyms + indication terms; add `clinicaltrial[PTYP] OR randomized[TIAB]` bias when helpful.
* **Batching:** group up to N trials per cycle; keep per-host budget (see quotas below).

### 4.2 Stage U0 — Metadata discovery (cheap)

* **ESearch** → PMIDs + hit counts.
* **ESummary** (batched) → titles, journal, pub date, article type, human/animal hints.
* **Insert** one `documents` row per PMID (`source_type=PubMed`; `status='discovered'`).
* **document\_citations**: pmid, doi (if present), article\_type, pub\_year, journal, mesh/substances (if available here).
* **trial\_doc\_candidates** rows with `stage='U0_meta'`.
* **(Optional) U0 pre-filter:** drop obvious non-clinical items (protocols, editorials, animal-only) to save the abstract call.

### 4.3 Stage U1 — Abstract fetch (still cheap)

* **EFetch** (batched) to retrieve **abstract text** ONLY for candidates that pass U0.
* Update `document_text.abstract_text` (+ char count).
* **Extract entities** from title+abstract into `document_entities` (NCTs, asset strings, phases, designs, endpoints, numbers).
* **Link proposals** into `document_links`: `nct_in_text`, `asset_in_text`, `asset_in_mesh` with confidence weights.
* **Score R & S:** populate `doc_rs_scores` for `(trial_id, doc_id)` with components JSONBs and tier labels.
* **Decision:**

  * Keep docs with `R≥1` (prefer `R≥2`) and `S≥S1`.
  * Drop or park low-R and S0 items (still keep the citation).

### 4.4 Optional Stage OA — Open-access full text (rare)

* **ELink/pmcid**: if PMC OA exists **and** (R3S3 or R3S2 with ambiguity), fetch **full text (XML/HTML → normalized text)**.
* Store in `document_text.fulltext_text` + set `fulltext_ttl_date` for non-candidates (e.g., now+90d).
* Update `document_entities` with any clarified numbers (endpoint definition, analysis set).

> **Never** store or fetch paywalled PDFs. For paywalled items, keep `doi` + abstract + your extracted spans.

### 4.5 Trial-level control (periodic eval & early stopping)

* Maintain **trial\_lit\_state** with: `best_S_Rge2`, `n_docs_seen`, `p_short`, `uncertainty`, `max_expected_utility_next_doc`.
* **Stop / Park / Promote rules:**

  * **Promote** if there exists **R3S3**, or two independent **(R3S2 / R2S3)**.
  * **Park** if all R3 are S0/S1 and best risk doc is R≤1, **or** `best_S_Rge2 ≤ S1` and no promising abstracts remain.
  * **Plateau:** if two consecutive evaluations change `p_short` by < ε (e.g., 0.03) **and** `max_expected_utility_next_doc < δ` (e.g., 0.05) → stop.
* **Outer queue priority (for which trial to work next):**
  `priority = 0.55 * best_S_Rge2 + 0.25 * time_to_catalyst_weight + 0.15 * uncertainty + 0.05 * max_expected_utility_next_doc`.

---

## 5) Retention, quotas, and cost guards

* **Retention**

  * Keep all **citations** and **abstracts** (they’re small).
  * Keep **OA full-text text** only for **R3S3** and **R3S2** (or for sampled QA); set `fulltext_ttl_date` = now+90 days unless the trial is promoted.
  * Do **not** store PDFs; store normalized text + `sha256`.

* **Quotas (tune in `rs_config.yaml`)**

  * `max_abstracts_per_trial_initial` (e.g., 8)
  * `max_abstracts_total_per_trial` (e.g., 20)
  * `max_oa_fulltexts_per_trial` (e.g., 2)
  * **E-utilities rate caps:** target ≤ 8–10 req/s with key; batch requests; exponential backoff.

* **Sampling & drift**

  * Randomly deep-dive 5–10% of parked decisions to estimate miss rate and recalibrate thresholds.
  * Track confusion matrix for (S tier vs later outcomes) once available.

---

## 6) Hooks for other sources (future, not implemented now)

* **documents.source\_type** already enumerates `PR`, `Conference`, etc.
* **document\_links.link\_type** accepts future link signals like `press_release_asset`, `conference_abstract_nct`.
* **doc\_rs\_scores** stays **source-agnostic**; R/S scoring modules can register **source-specific parsers** later.
* **trial\_lit\_state** aggregator doesn’t care about source—new docs just update the rollup.

---

## 7) QA & monitoring (PubMed-only)

* **Ingest QA**

  * % of ESummary rows missing abstracts (by journal/year).
  * Abstract character counts distribution (to catch empty/HTML-only mishaps).
  * MeSH/Substances coverage vs asset dictionary hit-rate.

* **Linking QA**

  * `nct_in_text` precision: spot-check 20 random high-confidence matches.
  * Asset alias collisions: any doc linking to >1 plausible asset without explicit combo wording → flag.

* **R/S QA**

  * Inter-annotator sanity: manually grade 50 abstracts → compare R/S tiers.
  * Contradictions within R3: presence of both R3S3 and R3S0 → force one clarifying OA pull or mark “needs arbitration”.

* **Cost QA**

  * Abstracts pulled per trial (mean/95p).
  * OA texts pulled per trial (mean/95p).
  * Token use per evaluation (if/when you add LLM summaries).

---

## 8) Runbook (operational cadence)

* **Daily**

  * Build queries per active trial; run ESearch/ESummary; refresh candidates.
  * Pull abstracts for top candidates (respect quotas).
  * Score R/S; update `trial_lit_state`; reprioritize outer queue.
  * OA pulls only when a doc is **R3S3** (or R3S2 and ambiguous).

* **Weekly**

  * Drift sampling on parked trials; review false negatives.
  * Threshold tweaks in `rs_config.yaml` (no code changes).

* **Monthly**

  * Backfill new MeSH/Substances dictionaries; expand asset alias lists.
  * Re-score borderline docs if new evidence appears.

---

## 9) Minimal config (example keys in `src/ncfd/score/rs_config.yaml`)

* `r_tiers: {r3: 0.75, r2: 0.55, r1: 0.35}`
* `s_tiers: {s3: 0.70, s2: 0.45, s1: 0.20}`
* `catalyst_window_months: 18`
* `phrases: {fail_primary: [...], futility: [...], subgroup: [...], pp_not_itt: [...], met_primary: [...]}`
* `effect_size_caps: {hr_bad: 1.50, hr_border: 1.15, orr_gap_bad: -0.20}`
* `quotas: {max_abstracts_initial: 8, max_abstracts_total: 20, max_oa_fulltexts: 2}`
* `stop_rules: {theta_high: 0.80, theta_low: 0.20, plateau_eps: 0.03, delta_min: 0.05}`

---

## 10) What you’ll store (and not store)

* **Always:** a `documents` row + `document_citations` + `document_text.abstract_text` for almost every useful PubMed hit.
* **Sometimes:** `document_text.fulltext_text` (PMC OA only) for a strict minority (R3S3/R3S2 or sampled QA).
* **Never:** paywalled PDFs or whole PMC PDFs; keep normalized text only (audit in `pubmed_meta` / `pmc_meta`).

---

If you want, I can turn this into: (a) an Alembic checklist for each table (column types, indexes), (b) a concrete E-utilities query cookbook for your top five indications, and (c) an R/S examples catalog (10 real PubMed abstracts labeled into R×S cells) so you can calibrate thresholds before writing any code.
