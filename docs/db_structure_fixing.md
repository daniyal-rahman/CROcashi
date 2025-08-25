
# What’s Missing (given your spec)

* **Securities & aliases**: `securities` (ticker, exchange, is\_adr), `company_aliases` (FKAs/subsidiaries). Without these you can’t enforce US-exchange filtering.
* **Assets & ownership**: `assets`, `asset_ownership` (company↔asset timeline). Critical for academia-sponsored trials and drilling “who owns what.”
* **Disclosures / catalysts**: `disclosures` (PR/8-K/abstract text+hash) and `catalysts` (window\_start/end, certainty). Right now there’s nowhere to store event clocks or PR bodies.
* **Gates & scores**: `gates` (composite G1–G4 firings, LR used) and `scores` (prior→posterior math, P\_fail). You only have `signals` (primitives).
* **Labels & markets**: `labels` (ground truth outcome, event date) and optional `markets` (cap/price for backtest). Needed for calibration/backtests.
* **Patents**: `patents`, `patent_assignments` (if you want ownership chain v1.1).

# Gaps / Oddities in Existing Tables

**alembic\_version**

* Length is `varchar(32)`. You previously aimed for **≥255**. If you planned that change, it didn’t land.

**companies**

* No **unique/partial-unique** on `cik`; add `UNIQUE (cik) WHERE cik IS NOT NULL`.
* Missing indices for lookup: trigram on `name_norm`, btree on `website_domain`.
* Lacks aliases/subsidiaries (separate table).
* `updated_at` won’t auto-refresh without a trigger.

**trials**

* Good coverage, but missing: `moa`, `target` (even as nullable text), and `sponsor_ticker` (denormalized, optional).
* Consider enum/checks for `phase`, `status`, `allocation`, `masking` to avoid free-text drift.
* Add indexes: `(sponsor_company_id)`, `(est_primary_completion_date)`, `(phase)`.

**trial\_versions**

* `metadata_` name looks accidental (trailing underscore).
* No uniqueness on version content: add `UNIQUE(trial_id, sha256)`.
* Add `(trial_id, captured_at DESC)` index for diffs.
* Consider fields for `results_posted_bool`, `results_first_posted_date` here (you have them on `trials`, but versioning them is useful).

**studies**

* Missing **`asset_id`** (nullable FK) and **`hash`** (content hash) for dedupe.
* No index on `trial_id` (FK doesn’t auto-index): add it.
* `doc_type` is free text; constrain to `{'PR','8-K','Abstract','Poster','Paper','Registry','FDA'}` via CHECK or enum.
* `p_value` (single scalar) is **too narrow** and conflicts with `extracted_jsonb`. Recommend **drop it**; keep numerics inside `extracted_jsonb` with arrays/objects.
* Add GIN on `extracted_jsonb` for targeted queries.
* `object_id` is opaque—if it’s an object-store key, make it `storage_key TEXT` or move to a `documents` table.

**signals**

* `UNIQUE(trial_id, s_id)` means you can’t record **multiple evidences** of the same signal (e.g., S3 from PR *and* abstract). Options:

  * Keep one row per S and add a child table `signal_evidence(signal_id, source_study_id, evidence_span, metadata)`, **or**
  * Drop the unique constraint and allow multiple rows per S with different sources.
* Add index `(trial_id)` (you implicitly rely on it) — right now only PK and the unique composite exist.

# Indices / Constraints You’ll Want

* `CREATE INDEX idx_studies_trial ON studies(trial_id);`
* `CREATE INDEX idx_trials_sponsor_company ON trials(sponsor_company_id);`
* `CREATE INDEX idx_trials_est_pcd ON trials(est_primary_completion_date);`
* `CREATE INDEX idx_companies_name_norm_trgm ON companies USING gin (name_norm gin_trgm_ops);`
* `CREATE INDEX idx_studies_extracted_jsonb ON studies USING gin (extracted_jsonb);`
* `ALTER TABLE trial_versions ADD CONSTRAINT uq_trial_version_sha UNIQUE (trial_id, sha256);`
* CHECKs:

  * `studies.doc_type` in allowed set.
  * `studies.oa_status` / `coverage_level` constrained to enumerations.
  * `trials.phase` constrained to normalized set (e.g., `{'Phase 2','Phase 2/3','Phase 3'}`).

# Concrete DDL Fixups (short list)

```sql
-- Alembic version width (if desired)
ALTER TABLE alembic_version ALTER COLUMN version_num TYPE varchar(255);

-- Studies hygiene
ALTER TABLE studies
  ADD COLUMN hash varchar(64),
  ADD COLUMN asset_id integer,
  ADD CONSTRAINT fk_studies_asset FOREIGN KEY (asset_id) REFERENCES assets(asset_id),
  ADD CONSTRAINT ck_studies_doc_type CHECK (doc_type IN ('PR','8-K','Abstract','Poster','Paper','Registry','FDA'));
CREATE INDEX idx_studies_trial ON studies(trial_id);
CREATE INDEX idx_studies_jsonb ON studies USING gin (extracted_jsonb);

-- Trial versions uniqueness & index
ALTER TABLE trial_versions
  RENAME COLUMN metadata_ TO metadata;
ALTER TABLE trial_versions
  ADD CONSTRAINT uq_trial_version_sha UNIQUE (trial_id, sha256);
CREATE INDEX idx_trial_versions_ts ON trial_versions(trial_id, captured_at DESC);

-- Companies constraints
CREATE UNIQUE INDEX uq_companies_cik ON companies(cik) WHERE cik IS NOT NULL;
CREATE INDEX idx_companies_name_trgm ON companies USING gin (name_norm gin_trgm_ops);

-- Signals evidence (option A: child table)
CREATE TABLE signal_evidence (
  evidence_id bigserial PRIMARY KEY,
  signal_id bigint NOT NULL REFERENCES signals(signal_id) ON DELETE CASCADE,
  source_study_id bigint REFERENCES studies(study_id) ON DELETE SET NULL,
  evidence_span text,
  metadata jsonb DEFAULT '{}'::jsonb
);
-- (Option B: drop unique and allow multiple signals per (trial,s_id))
```

# You likely still need these tables

* `securities(security_id, company_id, ticker, exchange, is_adr, active)`
* `company_aliases(company_id, alias, source, valid_from, valid_to)`
* `assets(...)`, `asset_ownership(asset_id, company_id, start_date, end_date, source, evidence_url)`
* `disclosures(trial_id, source_type, url, published_at, text_hash, text)`
* `catalysts(trial_id, window_start, window_end, certainty, sources[])`
* `gates(trial_id, g_id, fired_bool, supporting_s_ids[], lr_used, rationale_text)`
* `scores(trial_id, run_id, prior_pi, logit_prior, sum_log_lr, logit_post, p_fail, ts)`
* `labels(trial_id, event_date, primary_outcome_success_bool, price_move_5d, label_source_url)`
* (v1.1) `patents(...)`, `patent_assignments(...)`

# TL;DR

* Core primitives are there (`trials`, `trial_versions`, `studies`, `signals`, `companies`), but the **trading layer (securities), decision layer (gates/scores), event layer (catalysts/disclosures), and evaluation layer (labels)** are missing.
* Clean up `studies` (drop single `p_value`, add `hash`, constrain `doc_type`, index JSONB).
* Add uniqueness on `trial_versions`, indexes on common joins, and either allow multi-evidence signals or add a `signal_evidence` table.
* Add company alias/ticker scaffolding so you don’t bleed coverage at the mapping step.

If you want, I can generate a single Alembic revision that adds the missing tables + constraints and migrates column renames without data loss.
