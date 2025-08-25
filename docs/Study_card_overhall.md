
# 1) Core data objects (“cards”) & substructure

Think of each object as **small, composable, auditable**. Every numeric claim must point to a source span.

**A. DocumentCard (source-of-truth)**

* `doc_id` (e.g., `pmid:`, `doi:`, `ctgov:NCT…`, `pr:…`, `sec:8-K …`)
* `meta` (year, venue, study\_type, disease, intervention, route, dose\_units, region)
* `fulltext_refs[]` (page→char ranges, figure/table ids)
* `concepts[]` (MeSH/UMLS/CT.gov vocab you already use)

**B. EvidenceSpan**

* `span_id`, `doc_id`, `loc` (page, char\_start, char\_end), `quote` (≤400 chars)
* `section` (Methods/Results/Table/Figure/Protocol/SAP)
* `confidence` (OCR/parse quality)

**C. Claim (atomic, testable)**

* `claim_id`, `doc_id`, `span_ids[]`
* `type` (design\_fact | effect\_size | prevalence | assay\_cutoff | pkpd | operational | limitation)
* `proposition` (plain English)
* `value` (+ `ci`, `p`, `units`, `timepoint`, `set`: ITT/mITT/PP, `n_events`, `denominator`)
* `population` (key inclusions/exclusions summary)
* `intervention` (vector/route/dose; normalization note if converted)
* `quality_score`, `applicability_score`, `stance` (supports/contradicts/neutral)

**D. MethodCard (derived from Methods; the “non-obvious” bits)**

* `estimand` (population + endpoint + intercurrent policy + summary measure)
* `alpha_structure` (one-/two-sided, multiplicity plan, hierarchy/gatekeeping)
* `interim` (looks, timing, spending function; SSR? stop rules?)
* `analysis_set` (ITT/mITT/PP; stratification factors used in primary model)
* `missingness` (MAR/MNAR cues; imputation; tipping-point done?)
* `endpoint_ascertainment` (CEC vs local; blinded?)
* `protocol_features` (run-in, enrichment, crossover/rescue)
* `assay_thresholds[]` (e.g., NAb cutoff, assay type/units)
* `dose_exposure_rationale` (how dose → target engagement)
* `site_geography` (#sites, regions; dispersion flag)
* `design_risks[]` (free-text tags)
* `provenance_anchors[]` (span\_ids)

**E. ResultsFactsheet (facts only, normalized)**

* Array of items, each with:

  * `metric` (HR | OR | RR | Δmean | response\_rate)
  * `value` (plus `ci`, `p`, `direction`), `log_metric` (e.g., log-HR), `timepoint`
  * `analysis_set`, `population_slice` (if subgroup), `is_posthoc` (bool), `flags[]` (e.g., “nominal p”, “as-treated wins; ITT neutral”)
  * `span_ids[]`

**F. PocketContextCard (zoom-out guardrails)**

* 10–12 bullets: disease event volatility, typical MCID, regulator preferences, intervention class quirks (e.g., no redose for AAV), common pitfalls, minimal plausible effect size.

**G. GateCandidate / GateSpec**

* `gate_id`, `proposition` (necessary condition)
* `decision_rule` (falsifiable; numeric thresholds or crisp boolean)
* `measurables[]`:

  * `name`, `compute` (how to aggregate claims), `threshold` (e.g., `>=0.40`), `claim_ids[]`
* `dependencies[]` (other gates/subgates)
* `counter_claims[]` (top 1–3)
* `fda_next` (what would increase confidence next study)
* `confidence` (0–1), `notes`

**H. GateAssessment**

* `gate_id`, `status` (PASS/FAIL/UNCERTAIN)
* `p_gate` (if you choose to quantify), `rationale` (sentence list with claim\_ids)
* `sensitivity[]` (1–2 knobs that move it, e.g., eligible\_fraction 30–60%)
* `audit` (who/when/version/spans)

**I. DecisionRecord**

* `trial_id`, `gates[]` with statuses/probs
* `posterior_success` (if quantified), `combination_rule` (AND; any penalties noted)
* `coverage_gaps[]` (missing evidence that would be decision-moving)
* `links` (to memo, plots), `audit`

---

# 2) LLM “workers”: contracts (inputs → outputs) & responsibilities

**1) Retriever/Triage (cheap, non-LLM optional)**

* **Input:** trial context + date window.
* **Output:** `DocumentCard[]` (IDs + minimal meta) + initial `EvidenceSpan[]`.
* **Guarantees:** spans come with page/char anchors; no free-text summaries.

**2) Method Auditor (reasoning model)**

* **Input:** `design_json` (from your basic extractor), Methods/Protocol/SAP spans, `PocketContextCard`.
* **Output:** `MethodCard`.
* **Validators:** Must fill `estimand`, `alpha_structure`, `interim`, `missingness`, `endpoint_ascertainment`; each scalar tied to ≥1 span\_id. If implied, mark `"inferred_from_span": true`.

**3) Results Distiller (classifier + normalizer)**

* **Input:** Results/Abstract/Tables spans.
* **Output:** `ResultsFactsheet`.
* **Validators:** Every numeric must have units, set, timepoint, and a span\_id. Label each source sentence `{fact|posthoc|spin|limitation|subgroup}`; gates may only consume `fact` (or must justify using `posthoc`).

**4) Counter-Evidence Miner (targeted retrieval + small LLM)**

* **Input:** same corpus, negation patterns (e.g., “no difference”, “failed to”, “null”).
* **Output:** `Claim[]` of contradicting evidence with span\_ids.
* **Validators:** Require at least one high-quality contradictor per gate family.

**5) Gate Proposer (reasoning model)**

* **Input:** `MethodCard + ResultsFactsheet + PocketContextCard + top Claims`.
* **Output:** 3–5 `GateCandidate`.
* **Constraints:** Each gate must have ≥2 measurables, each measurable maps to claim\_ids and has a numeric threshold or boolean rule. Vague words (“generally”, “may”) are disallowed unless paired with a measurable.

**6) Post-Gate Validator (rule-based LLM or deterministic)**

* **Input:** `GateCandidate[]`.
* **Output:** `GateSpec[]` (rewritten or rejected with reasons).
* **Checks:** numeric thresholds present; computations feasible with available claims; counter-claims included; dependencies explicit; spans resolve.

**7) Gate Assessor (light reasoning + math)**

* **Input:** `GateSpec[] + Claims`.
* **Output:** `GateAssessment[]` (PASS/FAIL/UNCERTAIN + rationale), optional `p_gate`.
* **Behavior:** Deterministic where possible (e.g., compute eligible\_fraction from prevalence claims). Only use LLM to stitch rationale sentences (each cites claim\_ids).

**8) FDA Lens (optional; reasoning model)**

* **Input:** `MethodCard + GateAssessments + coverage_gaps`.
* **Output:** 2–3 additional GateSpecs framed as “what an FDA reviewer would need next,” each with measurable rule.

**9) Memo Composer (reasoning but provenance-locked)**

* **Input:** `GateAssessments + DecisionRecord scaffold`.
* **Output:** 1-pager narrative; every sentence includes `[claim_id]` bracket or a `span_id`.

---

# 3) End-to-end information flow (no code, just contracts)

1. **Docs in →** `DocumentCard` + `EvidenceSpan` (triage)
2. **Design JSON (basic extractor) →** **Method Auditor** ⇒ `MethodCard`
3. **Results spans →** **Results Distiller** ⇒ `ResultsFactsheet`
4. **Negation pass →** **Counter-Evidence Miner** ⇒ contradicting `Claim[]`
5. **Cards + Factsheet + Context →** **Gate Proposer** ⇒ `GateCandidate[]`
6. **Candidates →** **Post-Validator** ⇒ `GateSpec[]`
7. **Specs + Claims →** **Gate Assessor** ⇒ `GateAssessment[]`
8. **Assessments →** **DecisionRecord** (combine; AND-rule now, fancy combos later)
9. **Everything →** **Memo Composer** (prose with citations)

At each hop, you persist the *outputs* (immutable) and attach **lineage** (parent ids + hash of inputs) so you can replay/debug.

---

# 4) Minimal data management (enough to be safe & auditable)

**IDs & versioning**

* IDs: `doc_id`, `span_id` = `{doc_id}#p{page}:{start}-{end}`; `claim_id` = short ULID.
* **Immutability:** `DocumentCard`, `EvidenceSpan`, and original `Claim` are immutable; downstream objects carry `input_hash` for lineage.
* **Revisions:** If a card is regenerated, create a new row with `rev=N`, keep the prior for audit.

**Normalization registries (non-LLM)**

* `units_map` (vg/DRP/GC; dose normalizer with provenance note)
* `endpoint_map` (synonyms → canonical endpoint; e.g., “HF hosp” → “time-to-first HF hospitalization”)
* `assay_map` (titer assay types; cutoff comparability flags)
* `stats_map` (model aliases; e.g., “Cox proportional hazards” → `cox_ph`)

**Indices**

* Text/Vector index over spans for retrieval (BM25 + embedding).
* B-tree/GIN over `claim.type`, `intervention.vector`, `endpoint`, `disease`.

**States**

* Each artifact has `status` (draft → validated → frozen). Gates only accept **validated** upstream artifacts.

**Provenance & lineage**

* Store PDF hash, page count, parser version.
* Every numeric field points to `span_ids[]`. Memo prints clickable anchors.

**Conflict resolution**

* When multiple claims report same metric, aggregate with weights = `quality * applicability * recency`. Persist both raw and aggregated values; Gate Assessor must state which aggregation it used.

---

# 5) What truly needs a reasoning model (and why)

* **MethodCard** reconstruction (estimand, multiplicity, intercurrent events, adjudication) — cross-sentential, hidden in footnotes.
* **Assay harmonization** (titers/units) — needs explanation + comparability notes.
* **Gate proposal** — turning facts into **falsifiable** necessary conditions with measurable thresholds.
* **Counter-argument selection** — picking the strongest contradictors (not just any negation).
* **Narrative** — stitching rationale sentences with claim citations (factsheet → prose).

Everything else (IDs, numeric extraction, unit conversions, threshold checks) should be deterministic or small models.

---

# 6) Guardrails that keep you accurate (zoom-in + zoom-out)

* **Closed-book by default:** LLMs only see retrieved spans + PocketContextCard. No global web context.
* **Span requirement:** Every numeric in MethodCard/ResultsFactsheet/GateAssessment must reference ≥1 span\_id.
* **Post-Gate validator:** Rejects any gate without ≥2 measurables, numeric thresholds, or missing claim links.
* **Coverage gaps:** Each DecisionRecord lists the top 3 missing facts that would move a gate from FAIL→PASS (prevents shortsightedness).
* **Sensitivity stub:** Always compute a 2-knob table (e.g., vary two measurables most influential for G1/G2).

---

# 7) Sanity checklist for each artifact (what a reviewer AI needs)

* **MethodCard:** estimand present; alpha/multiplicity explicit; intercurrent + missingness policies stated; adjudication status clear.
* **ResultsFactsheet:** ITT values for primary endpoint present; subgroup flags explicit; post-hoc marked; numeric normalized.
* **GateSpec:** necessary condition wording; numeric rule; measurables computable; counter-claims listed; FDA-next articulated.
* **GateAssessment:** PASS/FAIL/UNCERTAIN justified with sentence-level citations; deterministic calculations shown.
* **DecisionRecord:** combination rule stated; dependencies/penalties (if any) disclosed; coverage gaps listed.

---

# 8) Files Slated for Overhaul

Based on the current implementation analysis, the following files are associated with the study card generation → gate generation pipeline and are slated for overhaul to align with the new architecture:

## Core Study Card Files:
- **`src/ncfd/extract/study_card.schema.json`** - JSON schema for study cards
- **`src/ncfd/extract/prompts/study_card_prompts.md`** - LLM prompts for extraction  
- **`src/ncfd/extract/prompts/study_card_prompts.py`** - Python wrapper for prompts
- **`src/ncfd/extract/lanextract_adapter.py`** - Main extraction adapter using LangExtract

## Study Card Processing:
- **`src/ncfd/pipeline/processing.py`** - StudyCardProcessor for enrichment and validation
- **`src/ncfd/pipeline/ingestion.py`** - Document ingestion pipeline with study card extraction
- **`src/ncfd/pipeline/workflow.py`** - End-to-end workflow orchestrating study card → signals → gates

## Study Card Analysis & Evaluation:
- **`src/ncfd/catalyst/extractor.py`** - Field extraction from study cards
- **`src/ncfd/catalyst/evaluator.py`** - Automatic study card evaluation
- **`src/ncfd/catalyst/comprehensive_service.py`** - Comprehensive study card analysis service

## Signals & Gates (Study Card → Gate Generation):
- **`src/ncfd/signals/primitives.py`** - Signal primitives S1-S9 that consume study card data
- **`src/ncfd/signals/gates.py`** - Gate logic G1-G4 that combines signals
- **`src/ncfd/scoring/score.py`** - Scoring system using gates and likelihood ratios

## Database Models & Migrations:
- **`src/ncfd/db/models.py`** - Database models for studies, signals, gates, scores
- **`alembic/versions/20250121_create_studies_table_and_guardrails.py`** - Studies table creation
- **`alembic/versions/20250124_create_signals_gates_scores_tables.py`** - Signals/gates/scores tables
- **`alembic/versions/cb8dbc1fff5f_enhance_study_card_schema_phase2.py`** - Study card schema enhancements

## Testing & Validation:
- **`tests/test_study_card_guardrails.py`** - Study card validation tests
- **`scripts/demo_testing_validation.py`** - Demo scripts for study card generation
- **`scripts/test_e2e_full_pipeline.py`** - End-to-end pipeline testing

## Overhaul Rationale:
The current implementation has several architectural issues that need to be addressed:

1. **Mixed Responsibilities**: Current files mix study card extraction, processing, and signal generation
2. **Inconsistent Data Flow**: Study cards flow through multiple processing layers without clear contracts
3. **Limited Evidence Tracking**: Current evidence spans are basic and don't support the new granular approach
4. **Rigid Schema**: Current study card schema doesn't support the new composable card structure
5. **Tight Coupling**: Signals and gates are tightly coupled to the current study card format

## Migration Strategy:
1. **Phase 1**: Create new data structures (DocumentCard, EvidenceSpan, Claim, MethodCard, etc.)
2. **Phase 2**: Implement new LLM workers with clear contracts
3. **Phase 3**: Migrate existing study card data to new format
4. **Phase 4**: Update signals and gates to use new data structures
5. **Phase 5**: Deprecate old implementation and remove legacy code

---

awesome — here’s a clean, “contracts-first” description of each LLM worker: what it does, what it consumes/produces, how to implement it (prompt style, guardrails, hyperparams), and how it fails. No code — just the ops manual you can hand to anyone wiring this up.

# 0) Global principles (apply to all workers)

* **Closed-book by default:** models only see retrieved spans + the Pocket Context Card (10–12 bullets). No web, no hidden priors.
* **Every numeric → provenance:** any number the model emits must carry `span_id` links (page/char or table cell).
* **Determinism:** temperature 0–0.2, top\_p ≤ 0.3; prefer greedy where possible. Enable seeds if supported.
* **Output contracts:** strict JSON shape per artifact (you already defined Cards). If a field is “inferred”, include `inferred_from_span_id`.
* **Validation before handoff:** each worker runs a local schema + logic check; if fails, return a machine-readable error with what to fix (don’t silently “guess”).
* **Zoom-in vs Zoom-out:** always pass the Pocket Context Card along with spans so the model keeps the bigger goal but cannot invent facts.

---

# 1) Retriever / Triage (can be non-LLM; include here for completeness)

**Job:** Find candidate documents & extract minimal high-quality spans to feed other workers.

* **Inputs:** trial context (disease, MOA, vector/route/dose band, endpoint), date window.
* **Outputs:** `DocumentCard[]` with metadata; `EvidenceSpan[]` (Methods, Results, Tables) with page/char anchors.
* **Implementation:** hybrid BM25+embedding; filter by year/study type. Dedup by DOI/PMID/NCT/PR.
* **Guardrails:** prefer PDF text over HTML; reject low-OCR-quality pages; cap spans at \~400 chars.

*Failure modes:* over-broad (low precision) → mitigate with entity filters (serotype/route), and a “must contain tokens” list per gate family.

---

# 2) Method Auditor (reasoning model)

**Job:** Read Methods/Protocol/SAP spans + basic design JSON; reconstruct what’s NOT explicit: estimand, multiplicity, intercurrent events, missingness, adjudication, dose-→exposure rationale, etc. Output a **MethodCard**.

* **Inputs:** `design_json` (arms/N/endpoints), Methods/Protocol/SAP `EvidenceSpan[]`, Pocket Context Card.
* **Outputs:** `MethodCard` (estimand, alpha\_structure, interim/spending, analysis\_set, missingness, endpoint\_ascertainment, protocol\_features, assay\_thresholds, dose\_exposure\_rationale, site\_geography, design\_risks\[], provenance\_anchors\[]).
* **Implementation:**

  * **Prompt style:** “auditor” voice; ask for explicit quotes; if implied, mark `inferred_from_span_id`.
  * **Constraints:** forbid unverifiable claims; require ≥1 `span_id` per scalar; if unknown, emit `"unknown"` (don’t guess).
  * **Hyperparams:** larger “thinking” model; temp 0–0.1; max tokens sized to accept \~6–10 spans per pass.
  * **Chunking:** feed Methods in ranked chunks; stop early once all required fields are filled.
* **QC/Validation:** ensure all required keys present; alpha sums to 0.05 (or justified); ITT/mITT/PP clarity; interim plan internally consistent.

*Failure modes:* misses hidden footnotes; confuses co-primary hierarchy. Mitigation: add a tiny **follow-up pass** that asks the model to verify “alpha/multiplicity consistency” against the quoted spans.

---

# 3) Results Distiller (classifier + normalizer)

**Job:** Separate **facts** from **spin** in Results; extract standardized effect metrics (HR/OR/RR/Δ), CI, p, set (ITT/mITT/PP), timepoint; tag post-hoc & subgroups. Output a **ResultsFactsheet**.

* **Inputs:** Results/Abstract/Tables `EvidenceSpan[]`.
* **Outputs:** array of `{metric, value, ci, p, analysis_set, timepoint, population_slice, is_posthoc, flags[], span_ids[]}`, plus normalized `log_metric` where applicable.
* **Implementation:**

  * **Prompt style:** “extract only numbers; label each source sentence {fact|posthoc|subgroup|spin|limitation}.”
  * **Constraints:** no derived math beyond simple transforms (e.g., HR→logHR); every row must cite a span.
  * **Models:** medium model is fine; temp 0.1.
* **QC/Validation:** enforce units and set (ITT default); reject if “nominal p” without test family.

*Failure modes:* double-counts the same result from abstract & body; mitigate with dedup key (endpoint+set+timepoint).

---

# 4) Counter-Evidence Miner (targeted)

**Job:** Actively search the same corpus for the best **contradicting** evidence for each potential gate family (negation, null results, caveats).

* **Inputs:** gate families of interest (G1 signal, G2 mechanism/delivery, G3 design), `DocumentCard[]`.
* **Outputs:** `Claim[]` with `stance="contradicts"` and high `quality_score/applicability_score`.
* **Implementation:**

  * **Retrieval:** pattern queries (“no difference”, “failed to”, “neutral”, “did not meet”).
  * **LLM:** small model to extract atomic claims + spans; temp 0.
* **QC:** must return ≥1 strong contradictor per family, or explicit “none found” with search strings tried.

*Failure modes:* cherry-picks weak contradictors; mitigate with a quality threshold and require top-N by study design + N.

---

# 5) Gate Proposer (reasoning model)

**Job:** Convert MethodCard + ResultsFactsheet (+ Pocket Context) into 3–5 **necessary** gates with **falsifiable numeric rules** and compute-from-claims measurables. Output **GateCandidates**.

* **Inputs:** `MethodCard`, `ResultsFactsheet`, `Claim[]` (top supportive), `Claim[]` (counter), Pocket Context Card.
* **Outputs:** `GateCandidate[]` with `{proposition, decision_rule, measurables[name, compute, threshold, claim_ids], dependencies[], counter_claims[], fda_next, confidence}`.
* **Implementation:**

  * **Prompt style:** “necessary, not nice-to-have; numeric thresholds; measurables must be computable from listed claims; include 1–2 strong counters.”
  * **Constraints:** ≥2 measurables per gate; no ‘and/or’; no vague adjectives without a threshold.
  * **Model:** larger reasoning model; temp 0.1–0.2.
* **QC:** reject gates lacking numeric rules or missing `claim_ids`; require a “why this is necessary” one-liner.

*Failure modes:* proposes attractive but unfalsifiable gates (“robust efficacy”). Mitigation: validator (next worker) bounces them.

---

# 6) Post-Gate Validator (rule-enforcer; can be LLM or deterministic)

**Job:** Enforce the gate rubric, rewrite minor issues, or reject. Promote **GateCandidate → GateSpec**.

* **Inputs:** `GateCandidate[]`, referenced `Claim[]`.
* **Outputs:** `GateSpec[]` (or a list of rejections with reasons).
* **Implementation:**

  * **Deterministic checks:** presence of thresholds; measurables point to existing claims; computations feasible (e.g., `median(vg_per_cell)` when those claims exist).
  * **Optional LLM:** only to rewrite awkward wording into canonical form; temp 0.
* **QC:** every measurable has a computation & threshold; include at least one counter-claim; dependencies enumerated.

*Failure modes:* passes a gate that can’t be computed; mitigate with a “dry-run compute” stub against current claims.

---

# 7) Gate Assessor (light reasoning + math)

**Job:** Evaluate each **GateSpec** deterministically where possible (compute measurables from claims) and set **PASS/FAIL/UNCERTAIN**, optionally compute `p_gate`. Output **GateAssessment**.

* **Inputs:** `GateSpec[]`, all `Claim[]` referenced.
* **Outputs:** `GateAssessment[]` with `{status, p_gate?, rationale(sentences with claim_ids), sensitivity[]}`.
* **Implementation:**

  * **Flow:** aggregate claims (weights = quality*applicability*recency), compute measurables → apply decision rules.
  * **LLM use:** only for the natural-language **rationale**; each sentence must carry claim ids.
  * **Numbers:** done by deterministic code outside the LLM; the model just explains.
  * **Model:** small model (or template) for rationale; temp 0–0.2.
* **QC:** show the intermediate numbers used (eligible\_fraction, vg/cell median, etc.) + spans.

*Failure modes:* rationale drifts beyond the numbers; mitigate with a “provenance required” checker that rejects sentences without claim refs.

---

# 8) FDA Lens (optional add-on; reasoning)

**Job:** From a reviewer’s perspective, name the 2–3 **missing** elements that would most increase confidence **next study**, and turn them into future-facing gates.

* **Inputs:** `MethodCard`, `GateAssessment[]`, `coverage_gaps[]`.
* **Outputs:** `GateSpec[]` (future gates) with precise data asks (e.g., “biopsy vg/cell ≥ T in ≥70% of pts”).
* **Implementation:** large model; temp 0.2; prompt insists on **measurable** asks only.
* **QC:** each suggested gate must be satisfiable/measurable in a future protocol/SAP.

*Failure modes:* asks for impossible data; mitigate with a feasibility checklist (biopsy optional? surrogate accepted?).

---

# 9) Memo Composer (reasoning, provenance-locked)

**Job:** Produce the one-pager: gate statuses, the AND logic, sensitivity snapshot, top 2 counters, and coverage gaps — every sentence cites claims/spans.

* **Inputs:** `GateAssessment[]`, `DecisionRecord` scaffold, Pocket Context Card.
* **Outputs:** Markdown memo; an index mapping bracketed refs → `claim_id`/`span_id`.
* **Implementation:** medium/large model; temp 0.2; strict “every sentence must carry at least one citation” rule.
* **QC:** automatic checker verifies bracketed refs in every sentence and resolves to known ids.

*Failure modes:* pretty prose without anchors; mitigate with hard failure if a sentence lacks a reference.

---

## Model sizing & routing (practical guidance)

* **Large (reasoning-heavy):** Method Auditor, Gate Proposer, FDA Lens, Memo Composer (if very nuanced).
* **Medium:** Results Distiller.
* **Small / deterministic:** Counter-Evidence Miner (after retrieval), Post-Gate Validator (mostly rules), Gate Assessor (math + small LLM for prose).

## Parallelism & ordering

* Don’t parallelize Methods ↔ Results on MVP; do **Methods first**, then Results Distiller.
* Counter-Evidence Miner can run in parallel with Results Distiller.
* Proposer → Validator → Assessor must be sequential.

## Caching & idempotency

* Cache by `(trial_id, doc_hashes, prompt_version)`; if inputs unchanged, reuse outputs.
* Version every prompt; store `input_hash` on each artifact for lineage.

## Evaluation & acceptance

* **Per-worker unit tests:** synthetic docs where the answer is known (e.g., multiplicity examples).
* **Human spot checks:** 5–10% of artifacts, especially MethodCards and GateSpecs.
* **End-to-end acceptance:** a memo must (1) include all gates, (2) show numeric checks, (3) cite sources sentence-by-sentence, (4) include a 2-knob sensitivity table, (5) list 3 coverage gaps.

---

### TL;DR

* Use **one heavy “auditor”** to reconstruct Methods truth, a **distiller** to sanitize Results, a **proposer+validator** pair to create **falsifiable gates**, a mostly **deterministic assessor** to decide PASS/FAIL, and an **FDA lens** for forward-looking asks — all stitched by a memo composer that **cites every sentence**.
* Keep models **closed-book**, **provenance-locked**, and **deterministic**; push all arithmetic out of the LLMs; enforce numeric thresholds and claim links in gates; and always render a small sensitivity snapshot so reviewers see levers, not vibes.
