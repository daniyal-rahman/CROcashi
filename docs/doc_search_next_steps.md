
---

# High-level take

* **Accurate diagnosis.** Your biggest blockers are: (1) no staging schema for raw docs, (2) empty `pubs.py` and `asset_backstop.py`, (3) alias/normalization gap, and (4) glue code not wiring discover→fetch→parse→extract→link→materialize.
* **Non-obvious risk:** overloading `Study` to act as both staging and normalized storage will paint you into a corner. Bring back a **raw → staging → normalized** split or you’ll keep fighting schema mismatches.

---

# Minimal target design (what “done” looks like)

**Flow:** discover URLs → fetch → parse → extract entities (LangExtract) → link (trial/asset/company) → materialize `studies` (normalized) with provenance.

**Storage layers**

* **Staging (raw)**: `documents`, `document_text_pages`, `document_tables`, `document_citations`
* **Entity/Link**: `document_entities`, `document_links`
* **Normalized**: `studies` (what you already have), `assets`, `asset_aliases`, `asset_ownership`

**Provenance everywhere:** every normalized `study` row references its `doc_id` + exact evidence spans.

---

# Create the missing tables (lean DDL you can paste into a migration)

```sql
-- Raw/staging
CREATE TABLE documents (
  doc_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_type       TEXT CHECK (source_type IN ('PR','IR','SEC','Registry','Abstract','Poster','Paper','FDA','Patent')),
  url               TEXT,
  url_hash          TEXT UNIQUE,
  published_at      TIMESTAMPTZ,
  discovered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  fetched_at        TIMESTAMPTZ,
  mime_type         TEXT,
  title             TEXT,
  doi               TEXT,
  pmid              TEXT,
  pmcid             TEXT,
  nct_id            TEXT,
  sponsor_text      TEXT,
  status            TEXT CHECK (status IN ('discovered','fetched','parsed','failed')) NOT NULL DEFAULT 'discovered',
  error_text        TEXT,
  storage_path      TEXT,              -- where the bytes live (S3/MinIO/local)
  text_hash         TEXT               -- hash of extracted fulltext for dedupe
);

CREATE INDEX ON documents ((lower(coalesce(doi,''))));
CREATE INDEX ON documents ((lower(coalesce(pmid,''))));
CREATE INDEX ON documents ((lower(coalesce(pmcid,''))));
CREATE INDEX ON documents ((lower(coalesce(nct_id,''))));
CREATE INDEX ON documents (published_at);

CREATE TABLE document_text_pages (
  doc_id   UUID REFERENCES documents(doc_id) ON DELETE CASCADE,
  page_no  INT,
  text     TEXT,
  PRIMARY KEY (doc_id, page_no)
);

CREATE TABLE document_tables (
  doc_id     UUID REFERENCES documents(doc_id) ON DELETE CASCADE,
  table_idx  INT,
  caption    TEXT,
  data_jsonb JSONB,
  PRIMARY KEY (doc_id, table_idx)
);

CREATE TABLE document_citations (
  doc_id   UUID REFERENCES documents(doc_id) ON DELETE CASCADE,
  id_type  TEXT CHECK (id_type IN ('doi','pmid','pmcid','nct')),
  id_value TEXT,
  is_primary BOOLEAN DEFAULT FALSE,
  UNIQUE (id_type, id_value),
  PRIMARY KEY (doc_id, id_type, id_value)
);

-- Entities & Links
CREATE TABLE document_entities (
  doc_id     UUID REFERENCES documents(doc_id) ON DELETE CASCADE,
  entity_type TEXT CHECK (entity_type IN (
    'asset_code','inn','generic','company','ticker','nct','endpoint','indication','moa','target'
  )),
  value       TEXT,
  norm_value  TEXT,
  span_start  INT,
  span_end    INT,
  confidence  NUMERIC,
  PRIMARY KEY (doc_id, entity_type, value, span_start)
);

CREATE TABLE document_links (
  doc_id        UUID REFERENCES documents(doc_id) ON DELETE CASCADE,
  trial_id      INT REFERENCES trials(trial_id),
  asset_id      INT REFERENCES assets(asset_id),
  company_id    INT REFERENCES companies(company_id),
  confidence    NUMERIC CHECK (confidence BETWEEN 0 AND 1),
  heuristics    JSONB,   -- which HP-* fired, scores
  evidence_json JSONB,   -- quoted spans, regex hits, table refs
  PRIMARY KEY (doc_id, coalesce(trial_id,0), coalesce(asset_id,0), coalesce(company_id,0))
);

-- Alias system
CREATE TABLE asset_aliases (
  asset_alias_id SERIAL PRIMARY KEY,
  asset_id       INT REFERENCES assets(asset_id),
  alias          TEXT NOT NULL,
  alias_type     TEXT CHECK (alias_type IN ('inn','internal_code','generic','brand','misspelling','db_id')),
  source         TEXT,
  UNIQUE (lower(alias))
);
```

> Keep your existing `studies` table as the **normalized** target; don’t rename. It should reference `doc_id` for provenance.

---

# Fill the empty modules (contracts you can implement)

## `src/ncfd/ingest/pubs.py`

**Purpose:** Pull legal literature metadata + OA fulltext.

**Functions (plain contracts):**

```python
def search_pubmed(query: str, since: str|None=None) -> list[PubRecord]: ...
def fetch_pmc_fulltext(pmcid: str) -> RetrievedDoc: ...
def crossref_meta(doi: str) -> CrossrefMeta: ...
def unpaywall_oa(doi: str) -> OARecord: ...
def europe_pmc_search(query: str) -> list[PubRecord]: ...
```

**Behavior:**

* Always write/merge into `documents` (one row per DOI/PMID/PMCID).
* If OA fulltext found, store bytes to object store and split into `document_text_pages`.
* Upsert `document_citations` (doi/pmid/pmcid/nct).
* Return `doc_id`s for downstream parse.

## `src/ncfd/mapping/asset_backstop.py`

**Purpose:** Attribute **academia-sponsored** or ambiguous trials to the public issuer via **asset evidence**.

**Inputs:** `doc_entities` (asset\_code/inn/generic), `document_citations` (NCT), `PR/8-K` text, `assets` & `asset_aliases`.

**Algorithm:**

1. Resolve `asset_code`/`inn` → `asset_id` via `asset_aliases`. If none, **create** asset + alias (type `internal_code` or `inn`) with evidence.
2. Look up `asset_ownership` timeline; if none, search SEC 8-Ks (Item 1.01) and PRs in the same `doc_id` set for licensing/assignment cues; create `asset_ownership` edges with `evidence_url`.
3. If a **CT.gov NCT** appears in PR/8-K alongside the asset code, create a `document_links` row linking `doc_id` → `trial_id` (via NCT) **and** `company_id` (owner at the doc’s `published_at` date). Set confidence with a simple rubric: exact NCT + asset\_code + company match = 0.95; asset\_code + sponsor mention = 0.8; inn-only = 0.6.
4. Emit a **link decision** object with reasons (store in `document_links.heuristics/evidence_json`).

---

# Wire up the workflow (one page “glue”)

**`document_ingest.py` should orchestrate:**

1. **discover()** → enqueue candidate URLs/IDs into `documents` with `status='discovered'`.
2. **fetch()** → download bytes, set `fetched_at`, write `storage_path`, extract text/pages.
3. **parse()** → light HTML/PDF parse; collect obvious IDs (DOI/PMID/PMCID/NCT); fill `document_citations`.
4. **extract\_entities()** (LangExtract) → fill `document_entities` with spans + confidences.
5. **link()** → run `linking_heuristics.py` (HP-1..HP-4) + `asset_backstop.py`; write `document_links`.
6. **materialize()** → for documents that describe a trial analysis (PR/abstract/posted results/paper), build or update a **normalized** `studies` row (`extracted_jsonb`, `notes_md`, `coverage_level`) *with* `doc_id` provenance.

> Keep each step **idempotent** (reruns don’t duplicate) and **resume-able** by `status`.

---

# Make the half-done pieces “real”

### Linking heuristics (HP-1..HP-4)

If you already have labels, make them concrete:

* **HP-1 (Exact ID match)**: NCT in doc ↔ `trials.nct_id` (confidence 0.99).
* **HP-2 (Asset code × Company domain)**: asset\_code + company IR/PR domain (0.9).
* **HP-3 (INN/generic × indication × sponsor text)**: co-occurrence within window (0.7–0.85).
* **HP-4 (Table numbers pattern)**: ORR/HR numerics matching CT.gov posted results or abstracts (0.8).

Combine with a simple **max-confidence** or a calibrated small logistic model. Anything <0.75 → review queue.

---

# Test plan (fast, meaningful)

**Unit**

* `pubs.search/fetch`: given a DOI with OA, creates `documents` + `document_text_pages`.
* `asset_backstop`: PR mentioning `AB-123` + `NCT…` links → creates `asset`, `asset_alias`, `asset_ownership`, and `document_links` with confidence ≥0.9.
* `linking_heuristics`: synthetic docs to trigger HP-1..HP-4.

**Integration (happy path)**

* Seed one trial (NCT…), one PR, one abstract. Run `document_ingest.run_all()`. Expect: `documents` 2 rows, `document_entities` filled, one `document_links` linking both docs to same `trial_id`, one `studies` row materialized with `doc_id` provenance.

**Regression**

* Rerun same pipeline; assert no duplicate rows (idempotence).

---

# Short “5 things” to do next (in order)

1. **Migrations:** add the staging + alias tables above.
2. **Implement `pubs.py`** with PubMed/OpenAlex→Unpaywall→PMC path; write to staging.
3. **Finish `asset_aliases` + normalizer** (seed with INN + internal codes from existing PRs).
4. **Implement `asset_backstop.py`** (the 4-step algorithm).
5. **Connect**: make `document_ingest` call discover→fetch→parse→extract→link→materialize; update `orchestrator.py` to run this flow with a `run_id`.

When those five land, your literature ingestion stops being “paperware” and becomes a working pipeline you can feed into Study Cards, signals, and gates.

Short answer: **don’t wipe.** Your current architecture is sound enough to reach everything you outlined. What’s blocking you isn’t the design—it’s a few **missing layers** and **empty glue modules**. Do a surgical refactor (“strangler-fig” approach), not a rebuild.

Here’s how I’d think about it.

---

## Verdict

* **Keep:** overall repo structure, `document_ingest` orchestrator, `orchestrator.py`, `Study` (as the **normalized** table), `Asset`, `AssetOwnership`, config, the existing linking heuristics framework.
* **Add (not replace):** a **raw/staging layer** for documents, an **asset alias** system, and two missing modules (`pubs.py`, `asset_backstop.py`).
* **Avoid:** rewriting the world or renaming `Study`. Treat it as the *target materialized view* fed by staging.

---

## Why not wipe?

* You already have the **right boundaries** (ingest → extract → link → normalize). The failure mode is **missing tables + empty modules**, not a broken mental model.
* A wipe will set you back to re-deciding things you’ve already decided (schemas, orchestration, config). The **delta to green** is small: add staging + finish two modules + wire.

---

## What must change (non-negotiable)

1. **Split storage tiers**
   Add a proper **staging schema** (raw `documents`, `document_text_pages`, `document_tables`, `document_citations`, `document_entities`, `document_links`). Keep `Study` as normalized.
   → This eliminates your current “Study is doing too much” mismatch.

2. **Implement the two empty modules**

   * `ingest/pubs.py` for PubMed/OpenAlex→Unpaywall→PMC (legal OA path).
   * `mapping/asset_backstop.py` to attribute academia-sponsored/ambiguous trials via asset codes/INN and 8-K/PR evidence.

3. **Asset alias system**
   Create `asset_aliases` and a normalization routine (INN, internal codes, brand, db IDs). This unlocks reliable asset-company linking and future patent joins.

4. **Wire the pipeline end-to-end**
   Make `document_ingest` actually run: discover → fetch → parse → extract (LangExtract) → link (heuristics + backstop) → **materialize** (`Study`) with provenance pointers back to `doc_id`.

---

## When should you **consider** a wipe?

Only if ≥2 of these are true after the fixes above:

* The orchestrator is **non-idempotent** or stateful in a way that can’t be untangled (e.g., global singletons, side-effects everywhere).
* Code is **circularly coupled** (ingest calls extract which calls ingest, etc.) and refactoring breaks half the repo.
* Tests can’t be made to run deterministically because of hardcoded network calls or hidden globals you can’t stub.
* The `Study` model is forked in multiple incompatible shapes across the codebase and migrations would be destructive.

In practice, you likely won’t hit these if you add the staging layer and keep `Study` as the normalized sink.

---

## Keep vs Replace — quick matrix

| Area                                                         | Keep            | Replace/Add | Why                                                              |
| ------------------------------------------------------------ | --------------- | ----------- | ---------------------------------------------------------------- |
| Orchestrator (`document_ingest`, `pipeline/orchestrator.py`) | ✅               | —           | Good skeleton; just wire steps & idempotency.                    |
| `Study`, `Asset`, `AssetOwnership`                           | ✅               | —           | Correct normalized targets; keep as sink.                        |
| Staging schema                                               | —               | ✅ Add       | Needed for raw bytes, pages, tables, citations, entities, links. |
| `ingest/pubs.py`                                             | —               | ✅ Implement | Core OA intake path (PubMed/PMC/Unpaywall).                      |
| `mapping/asset_backstop.py`                                  | —               | ✅ Implement | Asset→company attribution via PR/8-K/NCT.                        |
| Linking heuristics                                           | ✅               | ➕ Tune      | HP-1..HP-4 are a good start; persist evidence + scores.          |
| Asset aliases                                                | —               | ✅ Add       | Normalizes INN/internal codes/brands; enables robust linking.    |
| Tests                                                        | ✅ (files exist) | ➕ Expand    | Add idempotence + integration tests for full flow.               |

---

## “Go/No-Go” checkpoints (use this to keep yourself honest)

After each checkpoint, if you can’t get the green checks, **reassess** before adding more code.

1. **Schema cutover**

   * ✅ Staging tables exist; `Study` untouched; migrations apply cleanly; re-runs idempotent.

2. **Happy-path ingest** (one trial, one PR, one abstract)

   * ✅ `documents` populated → text/pages stored → `document_entities` extracted (LangExtract) → `document_links` created → **one `Study` row** materialized with `doc_id` provenance.

3. **Resolver confidence**

   * ✅ Asset code + NCT in PR maps to the same `trial_id` and the correct `company_id` via backstop; confidence ≥0.9.

4. **Re-run safety**

   * ✅ Running the same pipeline again produces **no duplicates**; only timestamps update.

If you hit 4/4, your current architecture is confirmed viable.

---

## Guardrails so this doesn’t regress

* **Provenance first:** every normalized row must point back to a `doc_id` and evidence spans (page/offset).
* **Run lineage:** tag all writes with a `run_id`; store artifacts under that.
* **Idempotent writes:** upserts keyed by hashes (`url_hash`, `text_hash`) and natural IDs (DOI/PMID/PMCID/NCT).
* **Config-driven:** no hardcoded domains or query strings; keep them in `config.yaml`.
* **Contract tests:** tiny fixtures for PR/abstract/paper that must pass end-to-end in CI.

---

## TL;DR plan

1. Add staging tables + `asset_aliases`.
2. Implement `pubs.py` (OA path) and `asset_backstop.py` (asset→company linking).
3. Wire `document_ingest` so it truly runs discover→fetch→parse→extract→link→materialize.
4. Prove idempotence & provenance with a 1-trial integration test.
5. Only consider a wipe if you cannot meet the four checkpoints above.

If you want, I can draft the exact Alembic migration and the function stubs for `pubs.py` and `asset_backstop.py` so you can drop them in and start running the happy path today.
