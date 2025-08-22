Perfect — let’s lock the gameplan. I’ll give you (1) a robust sponsor→ticker mapping approach (beyond an MVP fuzzy-match), (2) a legal literature/patent ingestion plan with exactly what to store, (3) notes fields you’ll want even if sparsely available, (4) a quick eval of your synthesis approach, and (5) the end-to-end system structure with schemas and scoring “co-dependent gates.”

---

# 1) Robust sponsor → US-listed ticker mapping (avoid HK/China)

**Goal:** deterministically map each trial to a US-traded security when possible, otherwise queue for human review. Do this in *layers*:

## 1.1 Canonical IDs you’ll maintain

* **Company**: `company_id` (your own), `cik`, `lei` (if available), `country_incorp`, `hq_country`.
* **Security**: `security_id`, `ticker`, `exchange` (`NASDAQ`, `NYSE`, `NYSE American`, optional `OTCQX/QB`), `is_adr`.
* **Aliases**: `company_aliases` (from SEC filings, prior names/FKAs, subsidiaries).

## 1.2 Candidate generation (blocking)

* From ClinicalTrials.gov: collect **Lead Sponsor** + **Collaborators** + **Responsible Party** + free text **Sponsor** and **Agency Class**.
* Normalize text (lowercase, strip punctuation/corporate suffixes, collapse whitespace).
* Create blocks:

  * Exact token overlap on 2+ “strong” tokens (e.g., `oncology`, `therapeutics`, unique brand piece).
  * **Website domain** if you can scrape it from PRs/IR (e.g., `acmebio.com` → match to 10-K domain).
  * **Drug code** (e.g., `AB-123`) → later tie to the company via PRs/SEC (see §2 & §3).

## 1.3 Deterministic matches (no ML)

* **SEC CIK search:** If sponsor/collaborator appears verbatim in recent 10-K/10-Q cover pages or the SEC company index → attach `cik`.
* **Subsidiary → parent:** Parse parent-company subsidiary lists (10-K exhibits) to map “X Oncology Ltd.” → Parent CIK.
* **Exchange filter:** Keep only tickers on {NASDAQ, NYSE, NYSE American, (optional OTCQX/QB)}; drop HK/China by exchange and/or by `hq_country in {CN, HK}` if disclosed.
* **ADR rule:** If `is_adr = true` and `hq_country in {CN, HK}` → exclude (your call).

## 1.4 Probabilistic resolver (small ML, high precision)

* For remaining candidates, compute a **match score** from features:

  * Jaro–Winkler / token-set ratio
  * Acronym match (e.g., `ABC Therapeutics, Inc.` ↔ `ABC Tx`)
  * **Address country** similarity (from 10-K header → match to trial country focus, optional)
  * **Domain match** (PR/IR URL vs 10-K)
  * **Drug code co-mention** in PRs (linking asset code to sponsor name)
* Train a logistic model or use `dedupe`/`recordlinkage` with a **high threshold**. Anything in the gray zone goes to a **review queue**.

## 1.5 Asset-based backstop (catches academia-sponsored trials)

* Build an **Asset Map**: `asset_id` with synonyms {internal code, INN, generic name, UNII/CAS, ChEMBL/DrugBank ID}.
* Link **press releases** and **8-Ks** that mention the asset code (e.g., “AB-123 topline readout”) to the **listed company** even if the **CT.gov lead sponsor** is a university.
* If `asset_id` ↔ `company_id` is high-confidence, attribute the trial to that public company for trading purposes, even when sponsor ≠ issuer.

> Result: you’ll cover most public biotechs deterministically; the asset-based backstop picks up “academia sponsor, public-co asset” cases that fuzzy name matching misses.

---

# 2) Legal literature & patent ingestion (no piracy)

## 2.1 Publications & trial docs (what to pull)

* **PubMed / Crossref / OpenAlex** → metadata & DOIs.
* **Unpaywall** → OA links (preprints, accepted manuscripts, repositories).
* **PubMed Central / Europe PMC** → full text where OA.
* **Conference abstracts/posters**: ASCO/AACR/ESMO portals (abstract text; posters where open).
* **Company PRs & SEC filings (8-K, 10-K/Q)** → numerics for endpoints, “topline” claims.
* **ClinicalTrials.gov** → protocol text, version diffs, posted results tables (where available).
* **Regulatory**: FDA review docs/AdCom briefing books (when public).

**Store PDFs/HTML** in object storage; keep **content hashes** and **page/paragraph spans** referenced by your notes.

## 2.2 Patents & ownership trail (what to pull)

* **USPTO assignment data** (chain of title; who owned when; reassignments).
* **Patent families (INPADOC)**: family members across jurisdictions.
* **Earliest priority date** (proxy for discovery vintage).
* **Assignees & inventors**, reassignments (licensing vs acquisition clues).
* **Links from patents to publications/trials** where disclosed (drug codes, INNs).
* **Material agreements**: SEC 8-K Item 1.01 and exhibits (license terms, partners, milestone triggers).

**Use cases:**

* “Who first found it / who owns it now,”
* detect **recent assignments** to shell entities,
* **licensing chains** (academia → startup → publicco),
* **freedom-to-operate** vibes when there’s thicketing.

---

# 3) “Notes” you’ll want on each Study/Trial/Asset (even if sparse)

**Per Study (paper/poster/PR):**

* Extraction coverage status (high/med/low) + missing fields.
* Endpoint definitions (verbatim) + any changes vs protocol.
* ITT vs PP populations; dropout/missingness summary; censoring notes (KM).
* Effect sizes with CIs; imputation method; multiplicity adjustments (Y/N, which).
* **Tone/claim strength** heuristics: cautious vs definitive wording.
* **Data location** (exact table/figure/page) and quote spans for each numeric.
* Known **conflicts/funding**; journal type; **OA status**.
* Reviewer notes: limitations, oddities, site/geography outliers, unexplained discrepancies.

**Per Trial:**

* Randomization/blinding; alpha-spending plan; interim looks; DSMB rules.
* Sample-size rationale (powering target, assumed variance/HR).
* **Endpoint class** (hard vs soft; surrogate vs clinical).
* Registry **version diffs** summary (what changed when).

**Per Asset:**

* Synonyms (internal codes, INN), modality (mAb, TKI, gene, cell), target, MOA.
* **Class priors** (win/fail history in same indication), typical effect sizes.
* **Biological “discount factors”**: target expression heterogeneity, historical tox/black box, blood–brain barrier, PK/PD mismatch, resistance mechanisms.
* **Companion Dx** status (if relevant) and assay validation maturity.
* **CMC/manufacturability** red flags (scale-up history if disclosed).
* **Patent family timeline** + assignments; licensing chain; encumbrances.

---

# 4) Synthesis step — is your approach good?

Yes — with one guardrail.
Instead of classic “RAG,” you’ll do **Evidence-Constrained Synthesis**:

1. **Freeze facts** in structured **Study Cards** (JSON) + spans.
2. Give the **Synthesis LLM** *only* those cards (not raw PDFs).
3. Force it to **cite `study_id.field`** for each claim (you can post-validate that every sentence has a pointer).
4. If a required field is missing (e.g., ITT result), it must output a **coverage gap** line item.

This gets you a coherent narrative that is **fully traceable** and **auditable**, not free-form speculation.

---

# 5) Full structure (end-to-end plan)

## 5.1 Data model (key tables)

**companies**
`company_id, cik, lei, name_canonical, country_incorp, hq_country`

**company\_aliases**
`company_id, alias, source, valid_from, valid_to`

**securities**
`security_id, company_id, ticker, exchange, is_adr, active`

**assets**
`asset_id, names_jsonb{inn, internal_codes[], generic[], cas, unii, chembl_id, drugbank_id}, modality, target, moa`

**asset\_ownership**
`asset_id, company_id, start_date, end_date, source (assignment/8-K/PR), evidence_url`

**trials**
`trial_id, nct_id, phase, indication, is_pivotal, primary_endpoint_text, est_primary_completion_date, status, sponsor_company_id (nullable), sponsor_text, collaborators_text[]`

**trial\_versions**
`trial_id, version_id, captured_at, raw_jsonb, primary_endpoint_text, sample_size, analysis_plan_text, changes_jsonb`

**studies**  *(one row per doc: PR, poster, paper, registry result)*
`study_id, trial_id, asset_id, doc_type, citation, year, url, oa_status, hash, extracted_jsonb (Study Card), notes_md, coverage_level`

**patents**
`patent_id, asset_id, family_id, jurisdiction, number, earliest_priority_date, assignees[], inventors[], status, links_jsonb`

**patent\_assignments**
`assignment_id, patent_id, assignor, assignee, exec_date, record_date, type (sale/license/security), source_url`

**disclosures**
`trial_id, source_type (PR/8-K/Abstract/etc.), url, published_at, text_hash, text`

**signals**  *(primitive S\_i)*
`trial_id, S_id, value, severity, evidence_span, source_study_id, fired_at_run`

**gates**  *(composite G\_j)*
`trial_id, G_id, fired_bool, supporting_S_ids[], lr_used, rationale_text`

**scores**
`trial_id, run_id, prior_pi, logit_prior, sum_log_lr, logit_post, p_fail, timestamp`

**catalysts**
`trial_id, window_start, window_end, certainty, sources[]`

**labels**  *(for backtest)*
`trial_id, event_date, primary_outcome_success_bool, price_move_5d, label_source_url`

---

## 5.2 Pipelines

**Ingestion**

* `ctgov_pull`: daily; save versions; diff to detect endpoint changes.
* `sec_pull`: maintain companies/securities, aliases, FKAs, subsidiary lists.
* `pr_scrape`: company PR/IR for asset codes + readouts.
* `abstract_pull`: ASCO/AACR/ESMO titles/abstracts.
* `pubmed_openalex`: metadata + OA links; fetch OA full text.
* `patent_fetch`: patents + assignments + families.

**Entity Resolution**

* `sponsor_to_company`: deterministic (CIK/exchange) → probabilistic (name/domain) → asset-based backstop → human queue.

**Extraction**

* `study_card_builder`: LangExtract to JSON with spans; coverage rating; store.

**Feature/Signal Detectors (primitive S)**

* S1: endpoint changed post-registration (diff trial\_versions).
* S2: underpowered pivotal (<70% power at claimed Δ; simple z/HR calc).
* S3: subgroup-only win without multiplicity control.
* S4: ITT neutral/neg vs PP pos with dropout asymmetry.
* S5: effect size > 75th percentile of **class priors** in a graveyard MOA/indication.
* S6: multiple interim looks, no alpha-spending language.
* S7: single-arm where RCT standard (weak historical control).
* S8: p-value cusp (0.045–0.050 cluster) in topline.
* S9: OS/PFS contradiction in context.

**Gates (co-dependent)**

* G1 “Alpha-Meltdown”: S1 & S2
* G2 “Analysis-Gaming”: S3 & S4
* G3 “Plausibility”: S5 & (S7 | S6)
* G4 “p-Hacking”: S8 & (S1 | S3)

**Scoring (traceable posterior)**

* Prior `π0` = historical pivotal failure rate for your universe.
* Posterior via log-odds using **calibrated LRs** for gates (dominant) and optional small weights for primitives.
* **Stop rules** override to `P_fail≈0.97` (e.g., endpoint switch after LPR; PP-only with high missing ITT; unblinded subjective primary where blinding feasible).

**Synthesis**

* Input = Study Cards (JSON).
* Output = narrative with **inline references** to `study_id.field`.
* Post-validator ensures every claim has a reference; otherwise mark **coverage gap**.

**Backtest**

* Freeze features T-14 before event.
* Labels from first unblinded readout PR/8-K.
* Metrics: Precision\@K (K=1–3), hit-rate for `P_fail≥τ` (τ high), median 5-day move, coverage %, miss audit.

**UI**

* Top list: trial, ticker, phase, window, **P\_fail**, gates fired.
* “Why” panel: gate(s) + primitives with quotes/spans and links.
* Backtest tab: Precision\@K chart, misses with reason (coverage vs logic).

**Ops**

* Orchestrate with Prefect/Airflow; artifact every run (`run_id`).
* Logs per trial: what fired, evidence spans, URLs.
* Config-driven class priors & LR tables (versioned).

---

# 6) Final notes on “completeness vs precision”

* Your **resolver** + **asset backstop** ensures you don’t lose trials at the sponsor filter.
* Your **evidence-constrained synthesis** gives readable narratives without hallucination.
* Your **gate-based scoring** with calibrated **likelihood ratios** yields the “compound confidence” you wanted — and is fully auditable.

If you want, next we can:

* design the *sponsor→ticker* resolver in detail (feature list + thresholds + a tiny adjudication UI),
* spec the **Study Card** JSON schema for LangExtract, and
* write the math for the **underpower check** (two-arm proportion/HR cases) so you can ship S2 quickly.

Awesome—here’s a tight, pragmatic roadmap plus copy-pasteable prompts so you can spin up parallel LLM “workers.” I’ve split it into:

1. a short **Global Context** block (paste this at the top of every LLM chat),
2. a **work plan** with sequencing + success criteria, and
3. **step-specific prompts** you can hand to different LLMs.

---

# Global Context (paste this first into every LLM you use)

You are helping build a precision-first “near-certain failure” detector for US-listed biotech pivotal trials. We want only a few, very high-confidence red flags—not broad coverage. Constraints & definitions:

**Scope & ethics**

* Focus on US-traded issuers (NASDAQ/NYSE/NYSE American; optional OTCQX/QB). Exclude CN/HK exchanges.
* No piracy: use PubMed/OpenAlex/PMC/Europe PMC/Unpaywall, company PRs, SEC filings (8-K/10-K/10-Q), ClinicalTrials.gov, FDA docs, open conference abstracts/posters. Patents via USPTO/assignment & INPADOC family data.
* Database: Postgres (metadata + JSONB), object storage for raw docs; DuckDB for analytics. Use LangExtract to fill structured “Study Cards” with evidence spans.

**Entity mapping**

* Trials come from ClinicalTrials.gov with full **version history**.
* Robust sponsor→ticker mapping: (1) deterministic via SEC CIK, exchange whitelist, subsidiary→parent; (2) probabilistic resolver (name/domain/alias) with high precision; (3) **asset-based backstop** (asset codes/INN mapped to listed issuer via PRs/8-Ks) to catch academia-sponsored trials.

**Core objects (schemas simplified)**

* `trials(trial_id, nct_id, sponsor_company_id?, sponsor_text, phase, indication, is_pivotal, primary_endpoint_text, est_primary_completion_date, status)`
* `trial_versions(trial_id, version_id, captured_at, raw_jsonb, primary_endpoint_text, sample_size, analysis_plan_text, changes_jsonb)`
* `studies(study_id, trial_id, asset_id?, doc_type{PR|Abstract|Paper|Registry|FDA}, citation, year, url, oa_status, extracted_jsonb, notes_md, coverage_level)`
* **Study Card (extracted\_jsonb)** includes: primary/secondary endpoints, N/arms, effect sizes + CIs, p-values, ITT/PP, dropouts, imputation, subgroup info, protocol changes, quotes with page/line spans, citations.
* `signals(trial_id, S_id, value, severity, evidence_span, source_study_id)`
* `gates(trial_id, G_id, fired_bool, supporting_S_ids[], lr_used, rationale_text)`
* `scores(trial_id, run_id, prior_pi, logit_prior, sum_log_lr, logit_post, p_fail)`
* `assets(asset_id, names_jsonb{inn, internal_codes[], generic[], cas, unii, chembl_id, drugbank_id}, modality, target, moa)`
* `asset_ownership(asset_id, company_id, start_date, end_date, source, evidence_url)`
* `patents(patent_id, asset_id, family_id, jurisdiction, number, earliest_priority_date, assignees[], inventors[], status)`
* `patent_assignments(assignment_id, patent_id, assignor, assignee, exec_date, type, source_url)`
* `labels(trial_id, event_date, primary_outcome_success_bool, price_move_5d, label_source_url)`
* `catalysts(trial_id, window_start, window_end, certainty, sources[])`

**Signals (primitive)**
S1 endpoint changed; S2 underpowered pivotal (<70% power at claimed Δ); S3 subgroup-only win without multiplicity; S4 ITT neutral/neg vs PP positive + dropout asymmetry; S5 effect size >75th percentile of wins in a “class graveyard”; S6 multiple interim looks w/o alpha spending; S7 single-arm where RCT is standard; S8 p-value cusp 0.045–0.050; S9 OS/PFS contradiction (context-dependent).

**Gates (co-dependent)**

* G1 Alpha-Meltdown = S1 & S2
* G2 Analysis-Gaming = S3 & S4
* G3 Plausibility = S5 & (S7 | S6)
* G4 p-Hacking = S8 & (S1 | S3)

**Scoring (traceable)**

* Prior failure rate π0 from historical pivotal readouts (our universe).
* Posterior via log-odds using calibrated **likelihood ratios (LRs)** mainly for **gates** (dominant), small/zero for primitives.
* Stop rules: e.g., endpoint switched after LPR; PP-only success with >20% missing ITT; unblinded subjective primary where blinding feasible → set P\_fail≈0.97.
* Freeze features at T-14 days pre-readout; evaluate Precision\@K (K=1–3), hit-rate for P\_fail≥τ, median 5-day move; keep coverage % and miss audits.

---

# Work plan (sequence + what “done” means)

**Phase 0. Repo scaffold + configs (0.5 day)**

* Create mono-repo structure (`ingestion/`, `resolve/`, `extract/`, `signals/`, `gates/`, `score/`, `backtest/`, `ui/`), `.env`, config YAMLs.
* ✅ Done = repo bootstrapped, env works, CI runs black/ruff/pytest.

**Phase 1. CT.gov ingestion with versioning (1–2 days)**

* Pull trials, persist raw JSON/XML, normalize key fields, store version diffs.
* ✅ Done = `trials` & `trial_versions` populated; endpoint-diffs emitted.

**Phase 2. Companies & securities reference (1 day)**

* Build `companies`, `company_aliases`, `securities` from SEC/CIK + exchange whitelist.
* ✅ Done = up-to-date map of US-traded issuers (NASDAQ/NYSE/NYSE American).

**Phase 3. Sponsor→ticker resolver (deterministic → probabilistic → asset backstop) (2–4 days)**

* Deterministic: CIK/alias/subsidiary→parent; Probabilistic: name/domain model; Asset backstop using PRs/8-Ks & asset codes.
* ✅ Done = ≥95% precision on a labeled sample; unresolved to review queue.

**Phase 4. PR/IR + abstracts ingestion & asset mapping (2 days)**

* Scrape PR/IR; pull ASCO/AACR/ESMO abstracts; extract asset codes & link assets.
* ✅ Done = `studies` rows for PRs/abstracts with basic fields.

**Phase 5. Study Card extraction with LangExtract (2–4 days)**

* Design JSON schema; build extractor prompts; evidence spans; coverage scoring.
* ✅ Done = ≥80% field coverage on a 30-doc sample; evidence spans stored.

**Phase 6. Primitive signal detectors S1–S9 (3–5 days)**

* Implement calculators (incl. underpower calc for proportion/HR cases).
* ✅ Done = unit tests with synthetic cases; signals persisted with spans.

**Phase 7. Gates + LR calibration & scoring (2–4 days)**

* Implement gate logic; initial LR table from small historical set; posterior calc; stop rules.
* ✅ Done = end-to-end P\_fail on current trials; explains math & evidence.

**Phase 8. Backtest harness (3–5 days)**

* Build historical universe, freeze features T-14, label outcomes, compute metrics, miss audit.
* ✅ Done = report with Precision\@K, hit-rate, downside capture, coverage%, miss list.

**Phase 9. Evidence-constrained synthesis (1–2 days)**

* Generate human-readable rationale from Study Cards; enforce references.
* ✅ Done = narratives where each claim cites `study_id.field`; gap list when missing.

**Phase 10. Catalyst clock & dashboard (2–3 days)**

* Infer windows; rank by P\_fail & proximity; Streamlit/Next.js UI.
* ✅ Done = interactive list + “Why” panel + backtest tab.

**Phase 11. Patent & ownership chain (nice-to-have for v1.1) (3–4 days)**

* USPTO/INPADOC ingestion, assignments; `asset_ownership` timelines.
* ✅ Done = display “who discovered/owns now” on asset view.

**Phase 12. Orchestration & logging (ongoing)**

* Prefect flows, retry policy, artifact buckets, run\_id lineage.
* ✅ Done = daily run, artifacts stored, error alerts.

---

# Step-specific prompts (copy-paste; each assumes the Global Context above)

## Step 0 — Repo scaffold

**Prompt:**
“Act as a senior platform engineer. Using the Global Context, propose a minimal repo structure, Python packages, config strategy, and CI. Output: (1) a directory tree, (2) `pyproject.toml` with core deps (requests, pydantic, sqlalchemy, psycopg2, duckdb, prefect, bs4/lxml, fastapi(optional)), (3) `.env.example`, (4) `config.yaml` keys, (5) a Makefile with tasks (`setup`, `db_migrate`, `ingest_ctgov`, `run_all`). Include a short rationale for each directory and list initial unit tests to add.”

---

## Step 1 — CT.gov ingestion & versioning

**Prompt:**
“Act as a data engineer. Design and detail an ingestion job `ctgov_pull` that: (a) fetches ClinicalTrials.gov studies for drug/biologic therapeutics, Ph 2b/3; (b) persists raw JSON/XML per version; (c) normalizes key fields into `trials`; (d) computes `trial_versions` diffs to detect endpoint/sample size/analysis plan changes. Provide: table DDLs, API endpoints used, pagination/updated-since strategy, idempotency, and a unit test plan with synthetic fixtures. Return pseudocode for the job and SQL for upserts.”

---

## Step 2 — Companies & securities reference

**Prompt:**
“Act as a data modeler. Build the `companies`, `company_aliases`, `securities` tables from SEC/CIK & exchange whitelists. Provide DDLs, an ingest plan for CIK/alias/FKA/subsidiary extraction, and logic to maintain active tickers. Include tests to ensure no CN/HK exchanges slip in and that each ticker maps to exactly one `company_id`.”

---

## Step 3 — Sponsor→ticker resolver (full, robust)

**Prompt:**
“Act as an entity-resolution specialist. Using the layered strategy in the Global Context, design the resolver service: deterministic matches (CIK, exact/alias/subsidiary→parent), probabilistic matches (features: Jaro–Winkler, token set ratio, acronym, domain match), and the asset-based backstop using PRs/8-Ks and asset codes. Provide: (1) feature list & weights for a logistic model with a high-precision threshold, (2) matching workflow flowchart including human review queue, (3) adjudication UI spec (fields to display, accept/reject, evidence), (4) evaluation plan with labeled pairs (precision/recall curves, threshold choice). Output JSON of a sample resolver decision including evidence.”

---

## Step 4 — PR/IR + abstracts ingestion & asset mapping

**Prompt:**
“Act as a web data engineer. Specify a crawler to pull company PR/IR pages and ASCO/AACR/ESMO abstracts. Extract asset codes (e.g., AB-123), INN/generic names, and map to `assets`. Provide: normalization of asset synonyms (INN, internal codes, DrugBank/ChEMBL/UNII), DDL for `assets`, and heuristics to attach `asset_id` to `trial_id` and `company_id`. Include deduping logic and a QA checklist (e.g., conflicting codes).”

---

## Step 5 — Study Card extraction with LangExtract

**Prompt:**
“Act as an information extraction designer. Define the Study Card JSON schema (fields listed in Global Context) and author LangExtract prompts that: (a) fill each field, (b) return evidence spans (page/paragraph or character offsets) for every numeric/claim, (c) set `coverage_level ∈ {high,med,low}` with reasons. Provide: 3 example inputs (PR, abstract, paper) and corresponding expected JSON outputs. Include a validator spec that rejects cards missing mandatory fields for pivotal trials (primary endpoint, N, effect size or p-value, ITT/PP status).”

---

## Step 6 — Primitive signal detectors (S1–S9)

**Prompt:**
“Act as a biostat engineer. Implement detectors S1–S9. For S2 (underpowered pivotal), specify formulas for two-arm proportions (ORR) and time-to-event (hazard ratio) with required inputs and reasonable defaults when variance not reported. For S8, describe a statistical test for p-value heaping near 0.05. For each signal: inputs (from Study Cards/versions), algorithm, thresholds, and failure modes. Output: Python-style pseudocode and unit tests using synthetic Study Cards that should trigger each signal.”

---

## Step 7 — Gates, LRs, scoring & stop rules

**Prompt:**
“Act as a decision-science engineer. Implement gates G1–G4 and the posterior probability using log-odds with **likelihood ratios**. Provide: (1) config format for LR tables (per gate), (2) function to compute posterior from prior π0 and fired gates/primitives, (3) clamp/cap logic to avoid blow-ups, (4) stop-rule overrides. Include a worked example: prior 0.65, G1+G3 fired with LR\_G1=3.5, LR\_G3=4.2, primitives ignored; show math to P\_fail. Specify the audit record to store (which gates, evidence spans, LR values, prior/posterior).”

---

## Step 8 — Backtest harness

**Prompt:**
“Act as a quant engineer. Design the backtest pipeline: build a historical universe of US-listed pivotal readouts (2018–2023), freeze features at T-14 days, create labels from first unblinded readout PR/8-K, compute metrics: Precision\@K (K=1–3), hit-rate for P\_fail≥τ, median 5-day move, coverage%, and a miss audit (coverage vs logic). Provide data splits (train 2018–2020, val 2021, test 2022–2023), and scripts to calibrate LR tables from frequencies. Output: a reproducible CLI spec (`backtest run …`) and expected CSV/Parquet artifacts.”

---

## Step 9 — Evidence-constrained synthesis

**Prompt:**
“Act as a technical writer LLM constrained by evidence. Given a set of Study Cards for a trial, write a concise narrative that: (a) summarizes design/endpoint, (b) lists fired signals/gates with references like `[S12.effect_primary]`, (c) states the posterior P\_fail with a one-line rationale, (d) enumerates coverage gaps (missing ITT, unclear multiplicity, etc.). Provide a template, two filled examples (one clean, one messy), and a post-validator spec that asserts every sentence contains at least one `[study_id.field]` reference.”

---

## Step 10 — Catalyst clock & dashboard

**Prompt:**
“Act as a product+frontend engineer. Define logic to infer catalyst windows from `est_primary_completion_date` plus PR/abstract hints and a slip factor per sponsor. Rank list = P\_fail (desc), then proximity. Design a Streamlit (or Next.js) UI: table of trials with ticker/phase/window/P\_fail/gates fired; ‘Why’ drawer with evidence spans & links; Backtest tab with Precision\@K chart and miss list. Provide component structure, data contracts, and minimal code skeleton.”

---

## Step 11 — Patents & ownership chain (v1.1)

**Prompt:**
“Act as an IP data engineer. Specify ingestion for USPTO grants + assignment, and INPADOC family data. Map to `assets` via INN, internal codes, and text mentions. Populate `asset_ownership` timeline (who discovered/owned/licensed when) with evidence URLs (SEC Item 1.01 exhibits/press). Provide DDLs, disambiguation heuristics, and example ownership timelines for 2 hypothetical assets.”

---

## Step 12 — Orchestration, logging, run lineage

**Prompt:**
“Act as an MLOps engineer. Using Prefect, define flows for: `ctgov_pull`, `sec_pull`, `pr_scrape`, `abstract_pull`, `study_card_builder`, `signals_run`, `gates_score`, `rank_list`, `backtest`. Add retries, idempotency, and artifact storage by `run_id`. Provide logging schema (structured JSON) and a minimal Grafana/Loki or ELK setup suggestion. Output a deployment checklist.”

---

If you want, I can also generate starter DDLs and the underpower calculators next so you can begin coding while the “LLM workers” produce their plans.
