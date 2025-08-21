Here’s a tight review—first the highest-risk issues I see, then a deeper breakdown by area, and finally a concrete end-to-end test you can run to verify the whole slice (PR/IR + abstracts → staging → linking) actually works as intended.

---

# TL;DR risk callouts (most important first)

1. **Staging parity drift**
   Your spec says `document_links` is a *coarse* link cache (`doc_id, nct_id?, asset_id?, company_id?, link_type, confidence`)—no evidence JSON stored there. The doc shows `document_links(..., evidence_jsonb)`. That breaks the “staging is lightweight; Cards re-verify spans” rule and muddles responsibilities.

2. **Trial link target**
   Their `trial_assets_xref (nct_id, ...)` uses a **text NCT** instead of your internal `trial_id` FK. That severs referential integrity to `trials`/`trial_versions`, and makes version-aware reasoning (your whole point) brittle.

3. **Assets/aliases modeling**
   `asset_aliases` includes a **`confidence` column** and uses `alias_text` instead of the spec’s `alias`. Aliases are orthogonal facts with provenance, not probabilistic claims. Missing: `source` column and `UNIQUE (asset_id, alias_norm, alias_type)` guard. This will cause duplicate/forked synonym sets and hard-to-debug merges.

4. **Normalization gaps**
   Their `norm_drug_name()` doesn’t collapse whitespace, unify dashes, or return **both** hyphenated and collapsed forms for codes (e.g., “AB-123” & “AB123”). They also lowercase everything; internal codes should remain **UPPER** for exact matching. Expect recall/precision wobbles and code collisions.

5. **Schema drift in staging tables**

   * `document_text_pages` lacks `char_count`.
   * `document_tables` uses `table_no` and adds `table_html`. Your spec uses `table_idx` and `table_jsonb` + `detector`.
   * `document_citations` is `citation_text, citation_type` instead of `doi, pmid, pmcid, crossref_jsonb, unpaywall_jsonb`. That blocks OA gating and DOI workflows.

6. **Heuristic coverage claims vs. reality**
   They claim “HP-1 through HP-4” and “100% tests”, but HP-2 explicitly “requires CT.gov” and is described as “framework ready”—so either HP-2 isn’t actually tested, or tests don’t exercise real matching. Inconsistent status.

7. **Ambiguity controls**
   HP-4 references `code_unique` but doesn’t define **how** uniqueness is established (global alias table? within company? pattern-level?). Without clear disambiguation (and combo detection), you’ll get silent false promotions.

8. **Referential integrity & enums**
   Snippets omit FKs/enums you specified (e.g., `doc_source_type`, `doc_status`, `oa_status`). If those really aren’t present, you’ll lose guardrails; if they are present but undocumented, this doc is misleading.

9. **Object storage contract is underspecified**
   You required `s3://bucket/docs/{sha256}/{filename}` + immutable bytes + `meta.json`. The doc mentions SHA-dedupe but not the **keying scheme** nor immutability rules.

10. **Testing claims**
    “28/28 passing” but no evidence of tests covering: code collisions (same code used by two assets), salt forms vs. base compounds, duplicate PRs (wire vs. company), multi-NCT-single-code PRs, or span index correctness. The claimed coverage looks surface-level.

---

# Deeper review by area

## A) Storage management (parity with your spec)

* **Object store**: No explicit `s3://.../{sha256}/{filename}` key scheme, no `meta.json`, no “never overwrite” rule. Add these or you’ll break dedupe/provenance.
* **documents**: Their sample omits `published_at`, `content_type`, `oa_status`, `discovered_at/fetched_at/parsed_at`, `error_msg`, and `crawl_run_id`. Might be an abbreviated snippet, but the doc should show full parity.
* **document\_text\_pages**: Missing `char_count`. You need this for fast offset sanity checks and span audits.
* **document\_tables**: Spec calls for `{doc_id, page_no, table_idx, table_jsonb, detector}`. They used `table_no` and added `table_html` (large payloads; not needed).
* **document\_citations**: You need `{doi, pmid, pmcid, crossref_jsonb, unpaywall_jsonb}` to later compute OA status and retrieve full text. `citation_text` is not workable.
* **document\_links**: Should **not** carry `evidence_jsonb`. Keep it coarse; let Cards own evidence. (If you keep it here, at least mark it “scratch” and never rely on it for scoring.)

## B) Assets model & normalization

* **DDL drift**: Missing `source` on `asset_aliases` and the **UNIQUE** triplet. Without those, duplicates creep in and merges become manual archaeology.
* **Alias casing**: Lowercasing codes (e.g., “xyz-9999”) is a footgun; keep canonical **UPPER** for codes while providing a folded `alias_norm` for matching.
* **Return both code forms**: For every code mention, you must generate the hyphenated and collapsed forms and store both as aliases.
* **Salts & forms**: The normalization function doesn’t treat salt forms as distinct unless an external ID (UNII/InChIKey) equates them. That rule is absent here.

## C) Linking heuristics

* **HP-2**: Labeled “requires CT.gov”—but you said CT.gov is already done elsewhere. Either wire it in (and test it), or don’t claim HP-2 in “complete” status.
* **Conflict handling**: A flat “−0.20” downgrade may still leave multiple ambiguous links ≥ threshold. Add a **combination guardrail** (e.g., only allow multiple promotions if combo wording present) and a **promotion veto** when ≥2 candidates remain above `τ_strong`.
* **Span evidence**: The doc says “enhanced span capture,” but there’s no explicit assertion that `document_links` candidates *always* have a corresponding `document_entities` span with `(page_no, start, end)`. Make this invariant testable.

## D) Referential integrity

* **trial\_assets\_xref** must FK to `trials(trial_id)`, not a free-text `nct_id`. You lose joins to `trial_versions` otherwise.
* **study\_assets\_xref** / **trial\_assets\_xref** should include `how` and `evidence_jsonb` (per your earlier plan), with FKs and ON DELETE semantics.

## E) Crawling/ethics/ops

* The doc asserts “robust error handling / retry” but gives no details on **robots.txt**, sitemaps, per-host backoff, or canonicalization. This is exactly where “looks pro” can hide brittle logic.

## F) Tests

* No adversarial cases listed (duplicate wire vs. company PR, two assets sharing a code, combo wording “+” / “in combination with”, multi-NCT one-code PR).
* No checks that `sha256` de-dupes objects across different URLs.
* No checks that span offsets in `document_entities` correspond to actual substrings in `document_text_pages`.

---

# Fixes I’d require before sign-off

1. **Make staging match spec** exactly (columns & enums). Move any `evidence_jsonb` out of `document_links`.
2. **Change trial link FK** to `trial_id BIGINT REFERENCES trials(trial_id)` and add a `how TEXT` column.
3. **Asset aliases**: Add `source TEXT`, `UNIQUE (asset_id, alias_norm, alias_type)`, remove `confidence`.
4. **Normalization**:

   * Keep codes uppercase; emit both “AB-123” and “AB123” aliases.
   * Collapse whitespace; normalize hyphens/dashes; don’t flatten salts unless IDs prove equivalence.
5. **Heuristics**: Define `code_unique` explicitly (e.g., one asset has that alias\_norm across all assets). Add promotion veto if ≥2 remain ≥ τ.
6. **Object storage**: Use `s3://bucket/docs/{sha256}/{filename}` + immutable policy + `meta.json`.
7. **Tests**: Add adversarial tests listed below.

---

# End-to-end test you can run now

This is **SEC/CT.gov-free**, exercises PR + Abstract ingestion, extraction, staging, and HP-1/HP-3/HP-4 linking. Use throwaway rows. Adjust table names if your migration differs.

## 0) Preconditions

* Migrations applied with **staging parity** (as in your spec).
* At least one company row exists (e.g., `company_id=101` for “Acme Bio”).

## 1) Seed a minimal asset + aliases

```sql
-- Asset A: AB-123 / INN alpha-interferon
INSERT INTO assets (modality, target, moa, names_jsonb)
VALUES ('biologic', 'IFNAR', 'interferon agonist', '{"inn":"alpha-interferon","internal_codes":["AB-123","AB123"]}')
RETURNING asset_id;  -- suppose -> 501

-- Aliases (note: both code forms, keep alias_norm folded)
INSERT INTO asset_aliases (asset_id, alias, alias_norm, alias_type, source)
VALUES
  (501,'AB-123','ab-123','code','seed'),
  (501,'AB123','ab123','code','seed'),
  (501,'alpha-interferon','alpha interferon','inn','seed');
```

## 2) Insert a PR document (company-hosted) + text page

```sql
-- Pretend these bytes hashed to sha256 = 'deadbeef...'
INSERT INTO documents
(source_type, source_url, publisher, published_at, storage_uri, content_type, sha256, oa_status, status)
VALUES
('PR','https://acmebio.com/news/2025/topline-reads','Acme Bio','2025-08-10',
 's3://ncfd/docs/deadbeef/topline.html','text/html','deadbeef','unknown','fetched')
RETURNING doc_id;  -- say -> 9001

INSERT INTO document_text_pages (doc_id, page_no, char_count, text)
VALUES (9001, 1, 240, 'Acme Bio announces topline from NCT12345678: AB-123 (alpha-interferon) meets primary endpoint...');
```

## 3) Insert an abstract document (AACR/ESMO route) + text

```sql
INSERT INTO documents
(source_type, source_url, publisher, published_at, storage_uri, content_type, sha256, oa_status, status)
VALUES
('Abstract','https://annalsofoncology.org/suppl/2025/12345','Annals of Oncology','2025-09-01',
 's3://ncfd/docs/cafebabe/annals-abstract.html','text/html','cafebabe','open','fetched')
RETURNING doc_id;  -- say -> 9002

-- Title contains code; body mentions phase/indication but no NCT
INSERT INTO document_text_pages (doc_id, page_no, char_count, text)
VALUES
(9002, 1, 200, 'Title: AB-123 in refractory melanoma'),
(9002, 2, 400, 'Phase 3 randomized trial of alpha-interferon in refractory melanoma. Primary endpoint PFS...');
```

## 4) Run your extractor (or simulate) → `document_entities`

*(If your code is wired, run it. Otherwise, insert spans directly to isolate the linker.)*

```sql
-- PR: capture code, INN, and NCT spans (page 1 offsets are illustrative)
INSERT INTO document_entities
(doc_id, ent_type, value_text, value_norm, page_no, char_start, char_end, detector)
VALUES
(9001,'code','AB-123','ab-123',1, 40, 46,'regex'),
(9001,'inn','alpha-interferon','alpha interferon',1, 49, 65,'dict'),
(9001,'nct','NCT12345678','nct12345678',1, 22, 33,'regex');

-- Abstract: code in title, INN + phase in body
INSERT INTO document_entities
(doc_id, ent_type, value_text, value_norm, page_no, char_start, char_end, detector)
VALUES
(9002,'code','AB-123','ab-123',1, 8, 14,'regex'),
(9002,'inn','alpha-interferon','alpha interferon',2, 27, 43,'dict'),
(9002,'phase','Phase 3','phase 3',2, 0, 7,'rule'),
(9002,'indication','melanoma','melanoma',1, 25, 33,'dict');
```

## 5) Run linking heuristics job

* Expect for **PR (doc\_id=9001)**:

  * **HP-1** fires: NCT within ±250 chars of asset → `document_links` row with `link_type='nct_near_asset'`, `confidence=1.00`, `asset_id=501`, `nct_id='NCT12345678'`.
  * **HP-3** may also propose `0.90`, but HP-1 should dominate; ensure dedupe in promoter.

* Expect for **Abstract (doc\_id=9002)**:

  * **HP-4** fires: code in title + (phase OR indication) in body + no ambiguity → row with `link_type='abstract_specificity'`, `confidence=0.85`, `asset_id=501`, `nct_id=NULL`.

**Quick checks**

```sql
SELECT doc_id, link_type, asset_id, nct_id, confidence
FROM document_links
WHERE doc_id IN (9001, 9002)
ORDER BY doc_id, confidence DESC;
```

**Expected**

* `9001 | nct_near_asset | 501 | NCT12345678 | 1.00`
* `9002 | abstract_specificity | 501 | NULL | 0.85`

## 6) Promotion (optional)

Run your promoter with `τ_strong = 0.95`.

**Expected**

* PR link auto-promotes to `study_assets_xref` (and to `trial_assets_xref` **only if** your promoter uses `trial_id`—fix if it uses `nct_id`).

**Verify**

```sql
SELECT * FROM study_assets_xref WHERE asset_id=501;
SELECT * FROM trial_assets_xref WHERE asset_id=501;  -- ensure FK is trial_id, not text
```

## 7) Negative/edge tests

### 7a) Duplicate PR (wire vs company domain)

Insert a second `documents` row for the **same** text but different `source_url` & `sha256` **must be the same** (point to same `storage_uri`). Verify:

```sql
-- Should produce two documents pointing to same storage_uri and sha256
SELECT storage_uri, COUNT(*) FROM documents WHERE sha256='deadbeef' GROUP BY storage_uri;
```

### 7b) Ambiguity downgrade

Seed a second asset with alias `AB-123` (collision):

```sql
INSERT INTO assets (names_jsonb) VALUES ('{"internal_codes":["AB-123"]}') RETURNING asset_id; -- say 502
INSERT INTO asset_aliases (asset_id, alias, alias_norm, alias_type, source)
VALUES (502,'AB-123','ab-123','code','seed');
```

Run heuristics on `doc_id=9002` again.

**Expect**: Two candidates for doc 9002; if **no combo wording**, both confidences should be **downgraded by 0.20** and **neither** should meet `τ_strong`. The promoter should **not** auto-promote and should emit a review item.

```sql
SELECT doc_id, asset_id, link_type, confidence
FROM document_links
WHERE doc_id=9002
ORDER BY confidence DESC;
```

### 7c) Span integrity

Check that every `document_links` row has at least one matching `document_entities` span for the same doc where the `value_norm` equals one of the promoted aliases.

```sql
-- Example assertion query
SELECT l.doc_id, l.asset_id, COUNT(e.*) AS matching_spans
FROM document_links l
LEFT JOIN asset_aliases a
  ON a.asset_id = l.asset_id
LEFT JOIN document_entities e
  ON e.doc_id = l.doc_id
 AND e.value_norm = a.alias_norm
WHERE l.doc_id IN (9001,9002)
GROUP BY 1,2;
```

Expect `matching_spans >= 1` for each link.

---

# Adversarial test additions (add to your suite)

* **Multi-NCT, single code PR**: Ensure HP-1 links only when the code is near a specific NCT; otherwise require review.
* **Combo wording**: “AB-123 + XYZ-001” / “in combination with” → allow multiple promotions; otherwise veto.
* **Hyphen diversity**: Ensure code regex matches `AB–123` (EN-dash) and normalizes to `AB-123`.
* **Salt forms**: “drug HCl” vs base name—should not merge unless UNII/InChIKey says so.
* **Case sensitivity**: Ensure codes are matched case-insensitively but stored **UPPER** as canonical alias.
* **Dedup across HTML/PDF**: Same content in HTML & press-release PDF should share `sha256` only if you hash bytes; confirm you **don’t** (correctly) dedupe cross-format.

---

If you want, I can translate the fixes into a concrete Alembic revision diff (for the staging/aliases/trial\_xref corrections) and a tiny Python test harness that seeds the exact rows above and runs the linker and promoter functions you showed.
