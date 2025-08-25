Great question! You're absolutely right to be concerned about this. The current filtering logic I showed you is quite simplistic - it's just looking at the sponsor name to categorize them, but it doesn't account for cases where:

1. **NCI/NIH sponsors a trial** but the **underlying drug/asset belongs to a biotech company**
2. **Academic centers sponsor trials** but are **testing biotech/pharma assets**
3. **Government agencies fund trials** but the **intellectual property belongs to private companies**

Let me examine the codebase to see if there's any attempt to capture these underlying asset relationships:

Search files...
Great! I found the answer. Let me search for more specific information about asset-based backstop functionality:

Search files...
Perfect! Now I have a complete picture. Let me check if there are any existing asset-related tables or functionality:

```bash
echo "=== STEP 38: Check for existing asset tables and functionality ===" && psql "$PSQL_DSN" -c "\dt" | grep -i asset
```
Let me check what tables actually exist:

```bash
echo "=== STEP 39: Check all existing tables ===" && psql "$PSQL_DSN" -c "\dt"
```
## 🔍 **Answer: Asset-Based Backstop is PLANNED but NOT YET IMPLEMENTED**

Based on my examination of the codebase, here's what I found:

### ✅ **What EXISTS:**
1. **Basic sponsor categorization** (what we tested) - simple name-based filtering
2. **Database models** for assets in `src/ncfd/db/models.py` (Asset, AssetAlias, TrialAssetsXref, etc.)
3. **Configuration** showing `asset_backstop_enabled: true` in config files
4. **Comprehensive documentation** in `docs/original_spec.md` outlining the asset-based backstop strategy

### ❌ **What's MISSING:**
1. **Asset tables** - The `assets`, `asset_aliases`, `trial_assets_xref` tables don't exist in the database yet
2. **Asset ingestion pipeline** - No code to extract drug codes, INNs, or asset identifiers from trials
3. **Asset ownership mapping** - No system to link assets to their actual owners (biotech companies)
4. **Asset-based backstop logic** - The filtering we tested only looks at sponsor names, not underlying assets

### 🎯 **The Asset-Based Backstop Strategy (From Documentation):**

The system is designed to work in **3 layers**:

1. **Deterministic matching** - Direct sponsor name → company mapping
2. **Probabilistic matching** - Fuzzy name matching with ML
3. **Asset-based backstop** - This is what you're asking about!

**How the Asset Backstop Should Work:**
- Extract **drug codes** (e.g., "AB-123"), **INNs**, **generic names** from trial data
- Link these assets to **biotech companies** via press releases, SEC filings, patents
- When NCI sponsors a trial testing "Drug X" owned by "Biotech Y", attribute the trial to Biotech Y for investment purposes

### 🚧 **Current State:**
- **Phase 1-2**: ✅ Complete (CT.gov ingestion, basic company mapping)
- **Phase 3**: 🚧 Partially implemented (deterministic + probabilistic matching)
- **Phase 3.5**: ❌ Missing (asset-based backstop)

### �� **What Needs to Be Built:**
1. **Asset extraction** from trial descriptions and interventions
2. **Asset ownership database** linking drugs to companies
3. **Asset-based trial attribution** logic
4. **Integration** with the existing filtering system

So to directly answer your question: **No, the current filtering does NOT catch cases where NCI sponsors a trial but the underlying asset belongs to a biotech company.** This is exactly the gap the asset-based backstop is designed to fill, but it hasn't been implemented yet.

The current system would categorize an NCI-sponsored trial as "Government Health Agency" even if it's testing a drug owned by Moderna or BioNTech.


Rev 0009 — Run lineage & artifacts

runs

run_id (text, PK)

started_at, finished_at (timestamptz), status (VARCHAR + CHECK in run_status set)

flow_name (text), config_hash (char(64))

run_artifacts

artifact_id (PK bigserial), run_id (FK → runs, CASCADE)

artifact_type (text), object_store_key (text), meta (jsonb)

Indexes: btree on run_id

Rev 0010 — Secondary indexes & housekeeping

Add / finalize

GIN on studies.extracted_jsonb (if not already)

btree on trials.est_primary_completion_date, trials.sponsor_company_id

trigram GIN on companies.name_norm, company_aliases.alias

Partial uniques on studies.hash and disclosures.text_hash (“unique when not null”)

(Optional) row-update triggers to maintain updated_at on companies / studies

Any late CHECKs once loaders are stable (e.g., ensure phase is not null for pivotal trials)
OPEN AI Langextract has a schema mismatch for some reason.
Lang extract cant find number of arms in a study some times 
The study cards are kinda shit. I think they should have some structure, but also I think that the study card being build right now is way too rudamentary. 
I think the way it needs to be implemented is that lang extract deals will pulling concrete facts from the study like what was dosing how many patients etc., then you have another llm that you feed in abstract, methods and results and then pull trends/ look for red flags and what not. Then you can have a multimodal model attempt to analyze the graphs maybe? But the main issue that I think would run into is that those 3 sections can be very verbose, and so just pulling them isn't going to be enough probs need to filter them down and that way you can do a multipass in parrallel searching for each thing in its own prompt. This way the model doesn't fall victim to the perswasive language of the study and also context rot. 
The other thing I probably have to start thinking about is how to implement early stopping in this so that I dont fry my wallet -- I think you can triage papers before generating study cards, and then if two papers from a trial are really promising, you can traige that trial down in priority, so double sorting.
Might need a second lit review for disease and pathway analysis 
phase might live in diff places in api so might hav to check multiple places not doing that rn
theres a created_at and captured_at which basically do the exact same thing. This needs to be consolidated.



