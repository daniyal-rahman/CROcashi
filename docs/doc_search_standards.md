
---


# What “literature” means here

For us, “literature” isn’t just journal papers. It’s the **set of primary sources** that can contain the facts you need about a trial/asset:

1. ClinicalTrials.gov (registry + version history + posted results)
2. Company communications (press releases/IR pages, SEC 8-K/10-K/10-Q)
3. Conference abstracts/posters (ASCO/AACR/ESMO, etc.)
4. Peer-reviewed papers and preprints (PubMed, PubMed Central, Europe PMC, bioRxiv/medRxiv)
5. Regulatory docs (FDA review memos/AdCom briefing books when public)
6. (Optionally) Patents/assignments to understand ownership chain

Each of these can independently confirm endpoints, N/arms, effect sizes, analysis populations (ITT/PP), protocol changes, and timing.

---

# The unit of work

We always search **anchored to a specific trial/asset**:

* **Identifiers:** NCT ID, internal drug code (e.g., AB-123), INN/generic name, sponsor name/ticker, indication keywords, target/MOA.
* We collect these identifiers first (from CT.gov + PRs) and use them to drive all queries.

---

# Three-pass search sprint (precision → expansion → saturation)

## Pass 1 — Precision (fast, must-have docs)

Goal: get the **authoritative** items that almost always exist.

* CT.gov: pull the latest record **and** prior versions (to catch endpoint changes).
* Company site/IR: pull **all** PRs mentioning the asset code/INN; grab SEC 8-Ks that disclose “topline” results.
* Conference portals: search for the asset code/INN; pull abstracts (and posters if public).
* PubMed/Europe PMC: search the asset code/INN + indication; grab **metadata** and **open-access** full text if available (via Unpaywall link).

**Stop condition:** once you have (a) registry record, (b) at least one PR **or** abstract with numerics, you can already populate a minimal Study Card later. Keep going for completeness.

## Pass 2 — Expansion (context & consistency)

Goal: collect documents that **cross-check** and add detail.

* Earlier phase results of the same asset (Phase 1/2) in the same indication.
* **Class-comparators:** recent RCTs with similar MOA/endpoint in the same disease (to set priors).
* Regulatory: search for FDA briefing docs if any (or analogous EMA docs).

**Stop condition:** for a pivotal readout, you want **at least one** item in each bucket: registry, PR/8-K/abstract (with numbers), and **one** class comparator (paper or high-quality abstract) to benchmark plausibility.

## Pass 3 — Saturation (tie up loose ends)

Goal: close gaps and track discrepancies.

* If the PR mentions ITT vs PP but journals don’t—look for posters with tables.
* If the endpoint changed—find **the version** where it changed in CT.gov and note the date.
* If the effect size looks huge—pull 2–3 more class papers to see typical CIs/HRs.
* If something still doesn’t add up, flag a **coverage gap** rather than guessing.

---

# How we actually search (plain English queries)

You’ll run **source-specific** searches with the identifiers:

* **Company PR/IR**: `site:company.com investors OR press "AB-123" OR "INN" "topline" "phase 3" "primary endpoint"`
* **SEC**: 8-K/10-K keyword search: `"AB-123" OR "INN"`, `"topline"`, `"primary endpoint"`, `"NCT01234567"`
* **CT.gov**: exact NCT ID; also search by drug name if the NCT is unknown in early passes
* **Conferences**: portal search with drug code/INN and indication terms
* **PubMed/Europe PMC**: `("AB-123" OR "INN") AND (phase 3 OR randomized) AND ("indication")`
* **Unpaywall**: feed the DOI to discover legal open-access versions
* **Regulatory**: FDA site search with drug/INN/biologic license name; for devices/combos adjust

We record every query string and the date (so searches are reproducible).

---

# Linking & deduping (so one study doesn’t appear 5 times)

* **Primary keys**: DOI, PMID/PMCID, conference abstract ID, CT.gov NCT, PR URL sha256.
* **Fuzzy title match** + author/year when DOI missing.
* **Many-to-one linkage**: multiple docs (PR, abstract, paper) can describe the **same underlying analysis**—we link them to one `trial_id` and (optionally) the same interim/final **timepoint**.
* Keep the **document timeline** (e.g., abstract → PR → journal) so you can see how claims evolved.

---

# Prioritizing documents (signal > noise)

When results conflict, we weigh sources:

1. **Regulatory reviews**
2. **Peer-reviewed RCT paper**
3. **Conference poster/abstract with tables**
4. **Registry posted results**
5. **Company PR/8-K** (good for dates and topline numerics but PR spin is common)

We still **keep** PRs and abstracts; we just **rank** them lower in credibility for analysis later.

---

# Coverage targets & “stop rules”

We don’t crawl forever—set **minimum coverage** to proceed:

**For a pivotal trial:**

* Registry record + version history ✅
* At least one numeric source (PR/8-K **or** abstract/poster **or** posted results) ✅
* At least one **class comparator** for the same endpoint in the same indication ✅

If any of the above is missing after Pass 2, mark **Coverage: Low** and stop (don’t analyze yet). This prevents bad inferences.

---

# What we store before analysis (lightweight but complete)

For **each document** we succeed in fetching:

* **Type** (PR, abstract, paper, registry, FDA)
* **Identity** (DOI/PMID/PMCID/URL/NCT)
* **Provenance** (source, retrieved\_at, query used, content hash)
* **Key fields** we can read even before extraction: endpoint names as text, reported N, arm names, any effect sizes or p-values we can spot, **verbatim quotes** of claims, and **page/figure/table references** if available
* **OA status** and the **best legal link** for full text (PMC/Europe PMC, repository, preprint)
* **Document date** and **what timepoint** it reflects (interim vs final)
* **Linkage** to `trial_id` and `asset_id` (via NCT, drug code/INN, sponsor)

This is enough to hand to extraction later, but it already gives you a **complete breadcrumb trail**.

---

# Handling paywalls legally

* Always try **Unpaywall** first—many papers have an OA repository version.
* If still paywalled, keep **metadata + abstract** and rely on **PR/8-K/posters/registry** for numerics.
* If the only missing piece is a figure/table, often the **conference poster** has the same numbers legally available.
* If you still can’t get the numbers, mark the specific field as a **coverage gap** and move on.

---

# Where patents fit (without analysis yet)

Run a **parallel** “IP sweep” using the asset identifiers:

* Pull **family members** and **assignments** (who owned when).
* Store earliest priority date, assignees, reassignments, and links to SEC Item 1.01 exhibits if the asset was licensed/sold.
* This lets you later answer “who discovered it / who owns it now,” but it doesn’t block literature coverage.

---

# A tiny concrete example (imaginary)

You pick NCT01234567 (AB-123 in metastatic CRC):

1. CT.gov gives you: primary endpoint PFS, N=600, randomized, blinded; you also see an **endpoint changed** in a prior version.
2. Company PR says: “Topline: did not meet OS, trend in PFS; PP showed benefit in biomarker-positive subgroup.”
3. ASCO abstract confirms ORR and lists ITT/PP numerics.
4. PubMed finds a Phase 2 paper from 2 years earlier with a surprising ORR. A comparator paper (anti-EGFR in mCRC) shows typical PFS/OS magnitudes.
5. You store all of that with dates, quotes, and links.
6. Coverage is **High** (registry+numeric+comparator) → ready for extraction/analysis.

---

# What you end up with (artifacts)

* A **document set** per trial/asset with identity, provenance, and quick numerics/quotes.
* A **search log** (queries you ran, when, and what came back).
* A **coverage report** (which buckets are present; what’s missing).
* Clean links to hand off to the extraction step (LangExtract) to populate your structured Study Cards.

That’s the whole literature search phase: **anchor → fetch must-haves → expand just enough to cross-check → stop** once coverage is good, with everything logged so the next stage is deterministic and auditable.
