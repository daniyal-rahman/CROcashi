Got it. Here’s a concrete, end-to-end gameplay focused on **company PR/IR** + **ASCO/AACR/ESMO** abstracts, with storage exactly in **parity** with your staging spec. I’ve kept your precision-first bias, previous regex/normalization notes, DDL for assets, high-precision link heuristics, dedup, and a QA checklist. No SEC/CT.gov ingestion steps (you’ve got those), but we’ll still **emit candidate links** into `document_links` and show how you’d later promote them.

---

# Step-by-step gameplay

## 0) Wire-up & repos (where things live)

* `ncfd/src/ncfd/ingest/pubs.py`
  Discovery + fetch + parse for **PR/IR** and **conference abstracts** (AACR / ASCO journal supplements / ESMO Annals).
* `ncfd/src/ncfd/extract/aliases.py`
  Regexes + normalization: **asset codes**, **INNs/generics**, UNII/ChEMBL/DrugBank IDs, span capture.
* `ncfd/src/ncfd/mapping/asset_backstop.py`
  Asset resolution + **high-precision heuristics** → writes to `document_links` (staging) and, when threshold met, to `study_assets_xref` / `trial_assets_xref` (if you choose to promote).
* `ncfd/src/ncfd/storage/{s3.py,fs.py}`
  Hashing to `sha256`, upload, return `storage_uri`.
* `ncfd/src/ncfd/db/models.py` (or new alembic migration)
  DDL for **staging tables** below + **assets** schema (aliases, ownership), plus indexes.

---

## 1) Storage management (strict parity with your spec)

### 1.1 Object storage (truth for raw files)

* **What**: store original **PDFs/HTML/posters/images** exactly as fetched.
* **Key**: `s3://<bucket>/docs/{sha256}/{filename}`
* **Why**: dedupe by content hash; immutable provenance; re-parse anytime.

**Implementation notes**

* Compute `sha256` on raw bytes **before** any transformation.
* Save a “fetch manifest” alongside, e.g., `s3://.../{sha256}/meta.json` with headers, fetch time, HTTP status, robots path, fetcher version.
* Never overwrite same `sha256` key (immutability).

### 1.2 Postgres **staging** (between crawlers and Study Cards)

#### `documents`

* **Columns** (exactly as you described):

  * `doc_id (pk)`
  * `source_type enum` = `PR|IR|Abstract|Paper|Registry|FDA|SEC_8K|Other` *(OK to keep full enum for consistency even if you won’t ingest SEC/Registry here.)*
  * `source_url, publisher, published_at`
  * `storage_uri, content_type, sha256`
  * `oa_status` = `open|green|bronze|closed|unknown`
  * `discovered_at, fetched_at, parsed_at`
  * `status enum` = `discovered|fetched|parsed|indexed|linked|ready_for_card|card_built|error`
  * `error_msg`
  * `crawl_run_id` (optional lineage)

**Indexes**

* `UNIQUE (source_url)` (nullable canonical handling below)
* `INDEX (sha256)`
* `INDEX (published_at)`
* `INDEX (status)`
* `INDEX (source_type, published_at DESC)`

#### `document_text_pages`

* `doc_id (fk)`, `page_no`, `char_count`, `text`
* **Index** `(doc_id, page_no)`
* Store whole page text to enable fast span lookup for evidence anchoring.

#### `document_tables`

* `doc_id (fk)`, `page_no`, `table_idx`, `table_jsonb`, `detector`
* Use `table_jsonb` rows/cols arrays for reproducible parsing (Tika/pdfplumber/camelot/lynx).

#### `document_links` *(coarse linking before Cards)*

* `doc_id (fk)`, `nct_id?`, `asset_id?`, `company_id?`, `link_type`, `confidence (0–1)`
* Multiple rows allowed per doc. Your later “promoter” job collapses to single target(s) above thresholds.

#### `document_entities` *(optional pre-facts cache)*

* `doc_id (fk)`, `ent_type` (`endpoint|n_total|p_value|effect_size|population|subgroup|code`…),
  `value_text`, `value_norm`, `page_no`, `char_start`, `char_end`, `detector`
* Cards **re-verify** spans; this is just for speed.

#### `document_citations`

* `doc_id (fk)`, `doi`, `pmid`, `pmcid`, `crossref_jsonb`, `unpaywall_jsonb`

#### `document_notes`

* `doc_id (fk)`, `notes_md`, `author`, `created_at`, `updated_at`

**Status transitions**

1. `discovered` → 2. `fetched` → 3. `parsed` → 4. `indexed` (text pages/tables ready) →
2. `linked` (document\_links populated) → 6. `ready_for_card` → 7. `card_built`.

**Dedup in staging**

* If a fetch computes an already-seen `sha256`, point new `documents` row to existing `storage_uri`, but **do not** duplicate bytes.
* Prefer one **canonical** row per `source_url`; if a **wire copy** and a **company-site copy** have same text but different urls: keep both `documents`, mark the **company domain** row as canonical in `document_notes` (or add `is_canonical` flag).

---

## 2) Assets model (DDL + normalization you asked for)

### 2.1 Tables

```sql
CREATE TABLE assets (
  asset_id     BIGSERIAL PRIMARY KEY,
  names_jsonb  JSONB NOT NULL DEFAULT '{}'::jsonb, -- {inn, internal_codes[], generic[], cas, unii, chembl_id, drugbank_id, inchikey}
  modality     TEXT,
  target       TEXT,
  moa          TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TYPE asset_alias_type AS ENUM
  ('inn','generic','brand','code','chembl','drugbank','unii','cas','inchikey','other');

CREATE TABLE asset_aliases (
  asset_alias_id BIGSERIAL PRIMARY KEY,
  asset_id       BIGINT REFERENCES assets(asset_id) ON DELETE CASCADE,
  alias          TEXT NOT NULL,
  alias_norm     TEXT NOT NULL,
  alias_type     asset_alias_type NOT NULL,
  source         TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (asset_id, alias_norm, alias_type)
);
CREATE INDEX ix_asset_alias_norm ON asset_aliases(alias_norm);
```

*(If you also want pre-Card promotion paths, keep your earlier `study_assets_xref` / `trial_assets_xref` tables. Otherwise, `document_links` can be the funnel.)*

### 2.2 Normalization (same rules as before)

* **Canonical key precedence**: `InChIKey` (small molecules) > `UNII` (biologics/salts OK) > `ChEMBL ID` > *(fallback)* normalized internal code (only when backed by ≥2 strong co-mentions).
* **`norm_drug_name`**: NFKD → lower → ASCII fold; collapse spaces; strip ®/™ quotes; expand Greek (α→alpha).
* Keep salt forms **separate aliases** unless external ID proves equivalence.
* **Internal codes**: store **both** hyphenated (`AB-123`) and collapsed (`AB123`) forms as aliases.

### 2.3 Regexes (recap)

```python
ASSET_CODE_PATTERNS = [
    r"\b[A-Z]{1,4}-\d{2,5}\b",             # AB-123, XYZ-12345
    r"\b[A-Z]{1,4}\d{2,5}\b",              # AB123
    r"\b[A-Z]{2,5}-[A-Z]{1,3}-\d{2,5}\b",  # BMS-AA-001
    r"\b[A-Z]{1,4}-\d+[A-Z]{1,2}\b",       # AB-123X
]
```

---

## 3) Crawling: **what to pull** & **how**

### 3.1 Company PR/IR

**Discovery**

* Seed from `companies` (US-traded whitelist already in your DB).
* Try common IR bases: `investors.<root>`, `ir.<root>`, `<root>/investors`, `/newsroom`, `/news`, `/press-releases`.
* Pull `robots.txt` once per host; cache `sitemap.xml`; collect `/news`, `/press`, `/media`, `/investors` items.

**Fetch**

* Backoff per host; set `User-Agent` per your `.env`.
* Record `fetched_at`, response headers, `content_type`, raw bytes → compute `sha256` → upload → `storage_uri`.

**Parse**

* HTML: prefer JSON-LD (`NewsArticle`) for `title`, `published_at`, `canonical_url`.
* Extract main body (readability alg.) and capture **PDF links** or hosted **image/PDF posters** too.
* **Emit**:

  * `documents` row
  * `document_text_pages` page 1…N (HTML → treat as single “page 1” or segment by `<p>` every \~3–5k chars)
  * `document_tables` if tables found (rare in PRs)
  * `document_citations` if DOIs appear (rare in PRs)

**Entity pre-extraction (PR/IR)**

* In body text, extract:

  * **Asset codes** (regex above) with spans.
  * **INN/generic names** (dictionary from ChEMBL/INN lists) with spans.
  * Optional: **NCT IDs** (you’ve got mapping later).
* Write to `document_entities` with `ent_type in ('code','generic','inn')`.

**Link proposals (PR/IR)**

* `document_links` candidates:

  * `(doc_id, asset_id=?, link_type='code_in_text'/'inn_in_text', confidence=…)`
  * If an **NCT** is present near the asset mention (±250 chars), also add `(nct_id, link_type='nct_near_asset')`.

### 3.2 Conferences

#### AACR (Proceedings; open)

* Enumerate Proceedings issues (yearly).
* For each abstract page: store HTML (and PDF if offered), parse **abstract number**, **title**, **authors**, **body**, **session**, **keywords**.
* Entities: asset codes, INNs/generics, optional NCT IDs → `document_entities`.
* Insert `documents` (`source_type='Abstract'`, `publisher='AACR / Cancer Research Proceedings'`).

#### ASCO (journal supplements; safe route)

* Track DOIs of **JCO/JCO PO/JCO GO** supplements for meetings.
* Store DOI metadata + abstract text **when open**.
* Insert `documents` (`source_type='Abstract'`, `publisher='ASCO / JCO*'`).
* DO NOT bulk-crawl Meeting Library indexes; store links to official pages if you must reference them.

#### ESMO (Annals of Oncology supplements; open subsets)

* Enumerate supplement issues; ingest abstract pages (and posters only when marked open).
* Insert `documents` (`source_type='Abstract'`, `publisher='ESMO / Annals of Oncology'`).

**Entity & link steps for abstracts**

* Same extraction: codes + INNs (+ optional NCT).
* Add `document_links` candidates as for PR/IR.

---

## 4) Linking heuristics (staging → promotion)

> You said you already handle CT.gov + SEC. Below are **document-local** heuristics that populate `document_links` and, when confidence ≥ τ, let you promote to your final xrefs.

**HP-1 (NCT near asset)**

* If text contains `NCT\d+` **and** an asset code or INN within ±250 chars:
  `document_links`: `(asset_id=?, nct_id=?, link_type='nct_near_asset', confidence=1.00)`.

**HP-2 (Exact intervention name match)**

* *(Optional promotion step if you choose to use your CT.gov cache)*
* If an asset alias\_norm equals a trial intervention name\_norm (exact), set `confidence=0.95`.

**HP-3 (PR publisher bias)**

* If **company-hosted PR** mentions **asset code + INN** together, and no ambiguity (one asset candidate), set `confidence=0.90`.

**HP-4 (Abstract specificity)**

* If an **abstract title** contains code/INN **and** body mentions the **phase** or **indication** matching your trial metadata, set `confidence=0.85`.
* If code present but INN absent **and** code is unique to one asset → `0.85`. If code reused by multiple assets (collision), don’t auto-promote: keep in review queue.

**Conflict rules / downgrades**

* If multiple assets match the same doc with no combo wording → **downgrade by 0.20** each and flag.
* If combo (“+”, “in combination with”, arm labels) detected → allow multiple `asset_id`s for that doc; do **not** downgrade.

**Promotion (optional)**

* Batch job reads `document_links`:

  * If `confidence ≥ 0.95` **or** `1.00`, write `study_assets_xref (confidence, evidence_jsonb)`; if an `nct_id` present, also write `trial_assets_xref`.
  * Else keep as candidates for human review.

---

## 5) Extraction & normalization details

**INN/generic dictionaries**

* Seed from **ChEMBL** names + **WHO INN** lists → build `alias_norm → (type, source)` map.
* On first sighting, if asset unknown:

  * Create `assets` shell row.
  * Insert aliases:

    * `alias_type='inn'|'generic'|'code'|'chembl'|'unii'|'drugbank'` (when known).
  * Backfill `names_jsonb` keys as IDs become available.

**Span capture**

* For every code/name hit, store `{page_no, char_start, char_end, value_text, value_norm, detector='regex|dict'}` in `document_entities`.
* These spans later become **evidence** in Cards.

---

## 6) Dedup logic

**Documents**

* “Same content” if `sha256` equal → point multiple `documents` to one `storage_uri`.
* Prefer **company domain** over wire copies; add a `link_type='duplicate_of'` row in `document_links` to point secondaries at canonical `doc_id` (or store a boolean `is_canonical`).

**Assets**

* **Auto-merge only** when one of:

  1. same `inchikey`, or
  2. same `unii`, or
  3. same `chembl_id`.
* If PR/Abstract explicitly states equivalence **code ↔ INN** for the same molecule, allow merge with that **evidence span** captured.
* Never merge on text fuzziness alone; open a **merge\_candidate** task.

---

## 7) QA checklist (pre-Card, precision-first)

**Identity & aliasing**

* [ ] Two internal **codes** mapped to **different** INNs/IDs → **block & review**.
* [ ] Same INN found under multiple `asset_id`s → create **merge candidate**.
* [ ] Alias\_norm collision across companies with overlapping timelines → flag.

**Document consistency**

* [ ] Multiple NCTs in one doc with single code mention → **do not** promote; review.
* [ ] Abstract indicates **combo** but only one asset linked → flag.
* [ ] Publisher mismatch (wire only; no company post) → keep but mark lower trust.

**Conference ingestion**

* [ ] AACR abstracts parsed fully; embargo notices stripped.
* [ ] ASCO: only journal supplement/full-open content; no bulk Meeting Library crawl.
* [ ] ESMO: only clearly open-access items.

**Staging hygiene**

* [ ] Every `documents` row has `sha256`, `storage_uri`, and a non-empty `document_text_pages`.
* [ ] `status` transitions monotonic; `error_msg` populated on failure.
* [ ] `document_links` confidence distribution monitored; 95th percentile reviewed for false positives.

---

## 8) DDL for **staging** (ready to drop into an Alembic revision)

```sql
-- enums
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'doc_source_type') THEN
    CREATE TYPE doc_source_type AS ENUM ('PR','IR','Abstract','Paper','Registry','FDA','SEC_8K','Other');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'doc_status') THEN
    CREATE TYPE doc_status AS ENUM ('discovered','fetched','parsed','indexed','linked','ready_for_card','card_built','error');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'oa_status') THEN
    CREATE TYPE oa_status AS ENUM ('open','green','bronze','closed','unknown');
  END IF;
END$$;

CREATE TABLE documents (
  doc_id        BIGSERIAL PRIMARY KEY,
  source_type   doc_source_type NOT NULL,
  source_url    TEXT UNIQUE,
  publisher     TEXT,
  published_at  TIMESTAMPTZ,
  storage_uri   TEXT NOT NULL,
  content_type  TEXT,
  sha256        TEXT NOT NULL,
  oa_status     oa_status DEFAULT 'unknown',
  discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  fetched_at    TIMESTAMPTZ,
  parsed_at     TIMESTAMPTZ,
  status        doc_status NOT NULL DEFAULT 'discovered',
  error_msg     TEXT,
  crawl_run_id  TEXT
);
CREATE INDEX ix_documents_sha256       ON documents(sha256);
CREATE INDEX ix_documents_published_at ON documents(published_at);
CREATE INDEX ix_documents_status       ON documents(status);
CREATE INDEX ix_documents_type_date    ON documents(source_type, published_at DESC);

CREATE TABLE document_text_pages (
  doc_id     BIGINT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  page_no    INT NOT NULL,
  char_count INT NOT NULL,
  text       TEXT NOT NULL,
  PRIMARY KEY (doc_id, page_no)
);

CREATE TABLE document_tables (
  doc_id     BIGINT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  page_no    INT NOT NULL,
  table_idx  INT NOT NULL,
  table_jsonb JSONB NOT NULL,
  detector   TEXT,
  PRIMARY KEY (doc_id, page_no, table_idx)
);

CREATE TABLE document_links (
  doc_id     BIGINT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  nct_id     TEXT,
  asset_id   BIGINT REFERENCES assets(asset_id) ON DELETE SET NULL,
  company_id BIGINT REFERENCES companies(company_id) ON DELETE SET NULL,
  link_type  TEXT NOT NULL,
  confidence NUMERIC(3,2) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_doclinks_doc ON document_links(doc_id);
CREATE INDEX ix_doclinks_asset ON document_links(asset_id);
CREATE INDEX ix_doclinks_nct ON document_links(nct_id);

CREATE TABLE document_entities (
  doc_id      BIGINT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  ent_type    TEXT NOT NULL, -- 'endpoint','n_total','p_value','effect_size','population','subgroup','code','inn','generic'
  value_text  TEXT NOT NULL,
  value_norm  TEXT,
  page_no     INT,
  char_start  INT,
  char_end    INT,
  detector    TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_docents_doc ON document_entities(doc_id);
CREATE INDEX ix_docents_type ON document_entities(ent_type);

CREATE TABLE document_citations (
  doc_id          BIGINT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  doi             TEXT,
  pmid            TEXT,
  pmcid           TEXT,
  crossref_jsonb  JSONB,
  unpaywall_jsonb JSONB,
  PRIMARY KEY (doc_id)
);

CREATE TABLE document_notes (
  doc_id     BIGINT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  notes_md   TEXT,
  author     TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (doc_id)
);
```

*(Assets DDL in §2.1 above.)*

---

## 9) Operational plan (jobs & order)

1. **Discover**

   * PR/IR endpoints from company domains; conference issue/supplement indexes.
   * Insert `documents(status='discovered')`.

2. **Fetch**

   * Download, compute `sha256`, upload to S3, set `storage_uri`, `fetched_at`, `content_type`, `oa_status` (if DOI present).
   * Transition → `status='fetched'`.

3. **Parse**

   * HTML/PDF → `document_text_pages` (+ `document_tables` if any).
   * Extract **entities** → `document_entities`.
   * Transition → `status='parsed'`.

4. **Index/link (staging)**

   * Run **asset resolver**:

     * Map codes/INNs → `asset_id`s (create shells + `asset_aliases` if new).
     * Apply HP-1…HP-4 to emit `document_links` with confidence.
   * Transition → `status='linked'`.

5. **Ready for Card**

   * Verify page spans exist for every proposed link; enqueue for Card build.
   * → `ready_for_card` (Cards still re-verify spans).

6. **Monitoring & review**

   * Daily checks on: error rates, top host latencies, `document_links` confidence histogram, alias collisions.

---

## 10) Test checklist (smoke + precision)

* **Regex**: unit tests for `ASSET_CODE_PATTERNS` (true/false positives, hyphen/collapsed).
* **Normalization**: `norm_drug_name` handles Greek, salts, hyphens; round-trip alias\_norm.
* **Span integrity**: each `document_entities` span indexes back to original `document_text_pages`.
* **Linking**: HP-1 produces `confidence=1.00` when NCT±asset within window; conflicts downgrade.
* **Dedup**: two different URLs same `sha256` → one object; staged rows point to same `storage_uri`.

---

## 11) Promotion knobs (optional)

* `τ_strong = 0.95`: auto-promote to `study_assets_xref` (and `trial_assets_xref` if you choose) with `evidence_jsonb` = spans + surrounding text.
* `τ_review = 0.80`: send to human queue; don’t promote.
* Maintain a `link_audit` view summarizing by `link_type`, publisher, confidence, and false-positive adjudications.

---
extra Notes: Conference abstracts (open routes only)

AACR (preferred, open text)

Crawl Cancer Research Proceedings issues for each year; enumerate abstract pages; capture: abstract #, title, authors, body, session, keywords, trial codes/NCTs appearing in text. 
AACR Journals
+1

ASCO

Use ASCO journal supplements (JCO/JCO PO/JCO GO) DOIs to store metadata & abstract text availability; store the DOI/URL and abstract number. Avoid automated scraping of Meeting Library search (respect TOS). 
ASCO
ASCO Publications
+1

ESMO

Prefer Annals of Oncology supplements (open) for abstracts; when ESMO marks resources as open access (e.g., ESMO Asia ePosters/abstracts), you may ingest those pages’ text. 
OncologyPro
ESMO
