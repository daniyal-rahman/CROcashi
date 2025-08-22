---

# High-risk issues (must fix)

### 1) Storage layer: API/behavior inconsistencies

* **Interface drift.** You call `get_storage_info()` in examples, but your `StorageBackend` interface defines only `get_total_size()`. Either add `get_storage_info()` to the interface or stop using it.
* **Bug in `DocumentIngester.__init__`.** You reference `self.storage_config` before setting it, and call `create_storage_backend(fallback_config)` where `fallback_config` is **undefined**.
* **Dangerous trust of caller hash.** `store(content, sha256, filename, …)` trusts the passed SHA256. If wrong/malicious, dedup breaks and files collide. You must **recompute** the hash server-side and verify equality.
* **Deletion policy can corrupt references.** “Delete oldest files” will remove blobs still referenced by DB rows. Content-addressed stores need **refcounts** or **GC marks** from the DB, not age-based deletion.
* **URI semantics.** Fallback to `file:///tmp/{sha256}` on failure silently de-links content from your CAS. You’ll later try to `retrieve()` by CAS URI and miss. Either **fail hard** or write to a quarantined namespace you can track.

**Minimal fixes**

* Add `compute_sha256(content)` in `store()`; ignore caller hash or compare and reject on mismatch.
* Add a table `objects(hash, bytes, created_at, refcount)` and increment/decrement refs on ingest/promote/cleanup.
* Replace age-based cleanup with “delete when `refcount = 0` and older than X days”.
* Make URIs explicit: `cas://{sha256}/{filename}` and `s3://bucket/key` or `file://…`. No ad-hoc `/tmp` fallbacks.

---

### 2) S3 fallback storyline is incomplete

* You say “seamless” but don’t show **how reads resolve** across tiers. If `store()` picked S3, `retrieve()` must parse the URI and choose the correct backend.
* Concurrency/races: your cleanup may run between `exists()` and `retrieve()`. Use **atomic writes** (temp file + rename) and a **single authoritative index** (DB) for URIs.

**Minimal fixes**

* Implement a `resolve_backend(storage_uri)` router used by `retrieve/exists/get_size/delete`.
* Atomic write pattern:

  1. write to `…/.staging/{sha256}.part`
  2. fsync, rename to final
  3. insert DB row in a transaction

---

### 3) Database trigger for pivotal Study Cards can brick valid inserts

* `jsonb_array_elements(card->'results'->'primary')` **throws** if `results` or `primary` is null. You need `jsonb_typeof()` guards.
* `(card #>> '{sample_size,total_n}')::int` will **raise** on strings like `"842 participants"`.
* Hard failing at `BEFORE INSERT` causes **transaction aborts** on partial cards (PRs/registries). That blocks your pipeline instead of routing to a review queue.

**Minimal fixes**
Use safe checks:

```sql
-- guard array access
EXISTS (
  SELECT 1
  FROM jsonb_array_elements(COALESCE(card->'results'->'primary','[]'::jsonb)) it
  WHERE (it->'effect_size'->>'value') IS NOT NULL
     OR (it->>'p_value') IS NOT NULL
);
-- robust integer parse (strip non-digits)
SELECT NULLIF(regexp_replace(card #>> '{sample_size,total_n}', '\D', '', 'g'), '')::int;
```

And move “hard pivotal requirements” to **application validation**; keep the trigger as a **WARNING log** or insert into a `staging_errors` table, not an exception.

---

### 4) LangExtract/Gemini integration inconsistencies

* **Provider confusion.** Env var suggests OpenAI key (`LANGEXTRACT_API_KEY="your-openai-api-key-here"`), but you claim **Google Gemini**. Ensure credentials align with the model actually used.
* **API surface instability.** You previously called nonexistent methods, now `lx.extract()` works. Good—**freeze a thin adapter** with strict response validation to prevent another silent drift.
* **“Double-encoded JSON” parsers.** You have multiple fragile fallbacks. Better: enforce **“return only valid JSON”** with JSON schema **in the prompt** and **reject non-JSON** early; don’t “repair” aggressively or you’ll ingest hallucinated fields.

**Minimal fixes**

* Enforce a max-strict adapter:

  * Reject if `extraction_text` fails **single-pass** JSON parse.
  * Validate against JSON Schema **and** your pivotal gate before commit.
  * Store raw model text to `studies.raw_extraction_text` for audits.

---

### 5) Heuristics & claims vs reality

* You claim **HP-1..HP-4 implemented**, but HP-2 (“Exact Intervention via CT.gov”) is marked “framework ready”. That’s a contradiction—call it out clearly as **not implemented**.
* Confidence values (1.00, 0.95, 0.90, 0.85) are **made up** here; there’s no calibration experiment shown. Don’t auto-promote on uncalibrated numbers.

**Minimal fixes**

* Put heuristic confidences behind a config flag **set to review-only** until you calibrate on a labeled set.
* Add a `link_audit` table with **true/false** labels and plot precision/recall per heuristic.

---

# Medium-risk issues (should fix)

### Storage config drift

* You use `storage.local` in YAML, `fs` in code. Standardize keys (`storage.local.*`) and validate config at startup (pydantic Settings).

### Study Card schema gaps

* `results.primary` path and types aren’t constrained. Ensure strong typing for `p_value` (number), `effect_size.value` (number), `metric ∈ {HR, OR, RR, Δ%, …}`.
* Evidence spans: define one canonical **location schema** (`{scheme, page, paragraph, char_start, char_end}`), not two half-specified variants.

### Entity extraction & dictionaries

* WHO INN and ChEMBL come with **licensing/versioning** constraints. Persist **source + version + date** fields; otherwise provenance is lost.
* Asset “shell creation” without dedupe rules risks alias explosion. Implement **merge candidates** with a normalized key (INN+target+modality).

### Crawl sources reality check

* “ASCO JCO supplements open access” is often false. Expect **rate limits, paywalls, and ToS**—build polite crawling with robots.txt respect and **manual upload path**.

---

# Low-risk issues (nice to fix)

* Performance claims (100MB/s) are hand-wavey; Python + hashing + fsync will be lower. Publish **real microbenchmarks**.
* “100% test coverage (35/35 tests)” conflates **pass rate** with **coverage**. Add coverage tooling (coverage.py) and report **line/function coverage %**.

---

