Here’s a clean, end-to-end implementation plan you can follow. It embeds all design specs (schema, prompts, validators/DB guardrails, examples, runbooks) and uses Alembic + Docker + Postgres exactly as you work today.

---

# 0) Goals & Acceptance

**Goal:** Populate a strict “Study Card” JSON for each document (PR/Abstract/Paper/Registry/FDA) using Gemini via LangExtract, with evidence spans for every numeric/claim and an explicit `coverage_level` ∈ {high,med,low} + rationale.
**Accept if (pivotal trials):** card contains (a) primary endpoint, (b) total N, (c) ITT/PP status of primary analysis, and (d) either effect size or p-value for the primary endpoint; otherwise reject at write-time.

---

# 1) File Layout (add to your repo)

```
src/ncfd/extract/
  study_card.schema.json            # JSON Schema (below)
  validator.py                      # JSON + pivotal guard validation (below)
  lanextract_adapter.py             # Glue for LangExtract (below)
  prompts/
    study_card_prompts.md           # System + task prompts (below)
tests/
  test_study_card_guardrails.py     # E2E smoke / golden tests (step 9)
ncfd/alembic/versions/
  <new>_study_card_guardrails.py    # PG trigger to enforce pivotal reqs (below)
scripts/
  study_card_smoke.sql              # SQL to prove the trigger (step 8)
```

---

# 2) Study Card JSON Schema (authoritative spec)

Create `src/ncfd/extract/study_card.schema.json`:

```json
{ "$schema":"https://json-schema.org/draft/2020-12/schema",
  "$id":"https://ncfd/schema/study_card.schema.json",
  "title":"Study Card","type":"object",
  "required":["doc","trial","primary_endpoints","populations","arms","results","coverage_level"],
  "properties":{
    "doc":{"type":"object","required":["doc_type","title","year","url","source_id"],
      "properties":{"doc_type":{"enum":["PR","Abstract","Paper","Registry","FDA"]},
        "title":{"type":"string"},"year":{"type":"integer"},"url":{"type":"string"},
        "source_id":{"type":"string"},"oa_status":{"type":"string"},"citation":{"type":"string"}}},
    "trial":{"type":"object","required":["nct_id","phase","indication","is_pivotal"],
      "properties":{"nct_id":{"type":"string"},"phase":{"type":"string"},"indication":{"type":"string"},
        "is_pivotal":{"type":"boolean"},"sponsor_company_id":{"type":["integer","null"]},
        "sponsor_text":{"type":["string","null"]},"est_primary_completion_date":{"type":["string","null"]},
        "status":{"type":["string","null"]}}},
    "primary_endpoints":{"type":"array","minItems":1,"items":{"type":"object","required":["name"],
      "properties":{"name":{"type":"string"},"timepoint":{"type":["string","null"]},
        "definition":{"type":["string","null"]},"evidence":{"$ref":"#/$defs/EvidenceArray"}}}},
    "secondary_endpoints":{"type":"array","items":{"type":"object","required":["name"],
      "properties":{"name":{"type":"string"},"timepoint":{"type":["string","null"]},
        "evidence":{"$ref":"#/$defs/EvidenceArray"}}}},
    "populations":{"type":"object","required":["itt","pp"],
      "properties":{"itt":{"type":"object","properties":{"defined":{"type":"boolean"},
          "text":{"type":["string","null"]},"evidence":{"$ref":"#/$defs/EvidenceArray"}}},
        "pp":{"type":"object","properties":{"defined":{"type":"boolean"},
          "text":{"type":["string","null"]},"evidence":{"$ref":"#/$defs/EvidenceArray"}}},
        "analysis_primary_on":{"enum":["ITT","PP","mITT",null]},
        "dropouts_overall_pct":{"type":["number","null"]},
        "missing_data_imputation":{"type":["string","null"]},
        "evidence":{"$ref":"#/$defs/EvidenceArray"}}},
    "arms":{"type":"array","minItems":1,"items":{"type":"object","required":["label","n"],
      "properties":{"label":{"type":"string"},"n":{"type":"integer"},"dose":{"type":["string","null"]},
        "evidence":{"$ref":"#/$defs/EvidenceArray"}}}},
    "sample_size":{"type":"object","required":["total_n"],
      "properties":{"total_n":{"type":"integer"},"evidence":{"$ref":"#/$defs/EvidenceArray"}}},
    "results":{"type":"object","required":["primary"],
      "properties":{"primary":{"type":"array","minItems":1,"items":{"$ref":"#/$defs/ResultItem"}},
        "secondary":{"type":"array","items":{"$ref":"#/$defs/ResultItem"}},
        "interim_looks":{"type":"array","items":{"type":"object",
          "properties":{"number":{"type":["integer","null"]},"alpha_spent":{"type":["number","null"]},
            "stopping_reason":{"type":["string","null"]},"evidence":{"$ref":"#/$defs/EvidenceArray"}}}},
        "subgroups":{"type":"array","items":{"type":"object","required":["name"],
          "properties":{"name":{"type":"string"},"effect_size":{"$ref":"#/$defs/EffectSize"},
            "p_value":{"type":["number","null"]},"multiplicity_adjusted":{"type":["boolean","null"]},
            "evidence":{"$ref":"#/$defs/EvidenceArray"}}}}}},
    "protocol_changes":{"type":"array","items":{"type":"object",
      "properties":{"change":{"type":"string"},"when":{"type":["string","null"]},
        "post_LPR":{"type":["boolean","null"]},"evidence":{"$ref":"#/$defs/EvidenceArray"}}}},
    "contradictions":{"type":"array","items":{"type":"object",
      "properties":{"type":{"enum":["OS_vs_PFS","primary_vs_subgroup","other"]},
        "description":{"type":"string"},"evidence":{"$ref":"#/$defs/EvidenceArray"}}}},
    "signals":{"type":"array","items":{"type":"object",
      "properties":{"id":{"enum":["S1","S2","S3","S4","S5","S6","S7","S8","S9"]},
        "evidence":{"$ref":"#/$defs/EvidenceArray"},"rationale":{"type":"string"}}}},
    "coverage_level":{"enum":["high","med","low"]},
    "coverage_rationale":{"type":"string"},
    "extraction_audit":{"type":"object",
      "properties":{"missing_fields":{"type":"array","items":{"type":"string"}},
        "assumptions":{"type":"array","items":{"type":"string"}}}}
  },
  "$defs":{
    "EvidenceArray":{"type":"array","items":{"$ref":"#/$defs/Evidence"}},
    "Evidence":{"type":"object","required":["loc"],
      "properties":{"loc":{"type":"object","required":["scheme"],
        "properties":{"scheme":{"enum":["page_paragraph","char_offsets"]},
          "page":{"type":["integer","null"]},"paragraph":{"type":["integer","null"]},
          "start":{"type":["integer","null"]},"end":{"type":["integer","null"]}}},
        "text_preview":{"type":["string","null"],"maxLength":300}}},
    "EffectSize":{"type":"object",
      "properties":{"metric":{"enum":["HR","OR","RR","MD","SMD","Δmean","Δ%","ResponderDiff","Other"]},
        "value":{"type":["number","null"]},"ci_low":{"type":["number","null"]},"ci_high":{"type":["number","null"]},
        "ci_level":{"type":["number","null"]},"timepoint":{"type":["string","null"]},
        "direction_favors":{"enum":["treatment","control",null]},"evidence":{"$ref":"#/$defs/EvidenceArray"}}},
    "ResultItem":{"type":"object","required":["endpoint"],
      "properties":{"endpoint":{"type":"string"},"effect_size":{"$ref":"#/$defs/EffectSize"},
        "p_value":{"type":["number","null"]},"adjusted_p_value":{"type":["number","null"]},
        "multiplicity_adjusted":{"type":["boolean","null"]},"population":{"enum":["ITT","PP","mITT",null]},
        "success_declared":{"type":["boolean","null"]},"evidence":{"$ref":"#/$defs/EvidenceArray"}}}
  }
}
```

**Design rules embedded in schema usage**

* **Every numeric/claim** must carry at least one `evidence` span.
* Doc types: `PR | Abstract | Paper | Registry | FDA`.
* Signals S1–S9 are pluggable; fill only with explicit textual support.

---

# 3) Coverage Rubric (used by model + validator)

* **high**: **all** present w/ evidence → primary endpoint; total N (+ arms); **analysis\_primary\_on** (ITT/PP/mITT); numeric **effect\_size.value** **or** **p\_value** for primary.
* **med**: exactly one of the above is missing or ambiguous.
* **low**: ≥2 missing or text is promotional/ambiguous.

Put this text at top of `prompts/study_card_prompts.md` so Gemini returns consistent `coverage_level` + `coverage_rationale`.

---

# 4) LangExtract (Gemini) Prompts

Create `src/ncfd/extract/prompts/study_card_prompts.md` with:

**(a) System header (prepend):**

```
You are Google Gemini used via LangExtract to populate a strict JSON schema called "Study Card".
Return ONLY valid JSON conforming to the provided schema. No comments or prose.

Rules:
- Extract ONLY what the text supports; do not invent values.
- For EVERY numeric or claim (N, per-arm n, endpoints, effect sizes, CIs, p-values, ITT/PP selection, dropouts, imputation, success/failure statements, protocol changes), attach ≥1 evidence span using:
  page_paragraph: {"scheme":"page_paragraph","page":<1-based>,"paragraph":<1-based>}
  or char_offsets: {"scheme":"char_offsets","start":<0-based>,"end":<exclusive>}
- If conflicts, prefer PRIMARY endpoint and ITT unless PP is explicitly primary. Record uncertainty in extraction_audit and reduce coverage_level.
- Compute coverage_level using the rubric provided and include coverage_rationale.
```

**(b) Task body (include or reference schema):**

```
SCHEMA: (embed the minified JSON Schema)

INPUT:
{
  "doc": {"doc_type":"<PR|Abstract|Paper|Registry|FDA>","title":"...","year":2024,"url":"...","source_id":"..."},
  "trial_hint": {"nct_id":"NCT...","phase":"3","indication":"..."},
  "chunks": [{"page":1,"paragraph":1,"start":0,"end":312,"text":"..."}, ...]
}

INSTRUCTIONS:
- Prefer page_paragraph spans when available; else char_offsets.
- Extract primary/secondary endpoints; sample size (total + per arm); populations (ITT/PP/mITT), dropouts, imputation; results (effect sizes, CIs, p-values, multiplicity); interim looks & alpha spending; subgroups & multiplicity; protocol changes (flag post_LPR if stated); contradictions (OS vs PFS etc.).
- Set success_declared for primary endpoint only if text explicitly says met/not met.
- Populate signals S1–S9 only when explicitly supported; include rationale and evidence.
- Populate extraction_audit.missing_fields and .assumptions.
- Output MUST validate.
```

**(c) Doc-type suffixes:**

* PR: likely `coverage_level="low"` or “med” unless numerics present.
* Abstract: capture numerics; multiplicity often absent—note in audit.
* Paper: pull HR/CI/p & alpha handling from methods/results; ITT as primary unless text contradicts.

---

# 5) Python Validator (schema + pivotal gate)

Create `src/ncfd/extract/validator.py`:

```python
from __future__ import annotations
import json, jsonschema, importlib.resources as r

_schema = json.loads(r.files("ncfd.extract").joinpath("study_card.schema.json").read_text())

def validate_card(card: dict, is_pivotal: bool) -> None:
    jsonschema.validate(card, _schema)

    missing = []
    # primary endpoint
    if not card.get("primary_endpoints"):
        missing.append("primary_endpoints")
    # sample size total N
    total_n = ((card.get("sample_size") or {}).get("total_n"))
    if total_n is None:
        missing.append("sample_size.total_n")
    # ITT/PP selection for primary analysis
    if not (card.get("populations") or {}).get("analysis_primary_on"):
        missing.append("populations.analysis_primary_on")
    # effect OR p for primary
    ok = False
    for r0 in (card.get("results") or {}).get("primary", []):
        eff = (r0.get("effect_size") or {}).get("value")
        p = r0.get("p_value")
        if eff is not None or p is not None:
            ok = True; break
    if not ok:
        missing.append("results.primary.(effect_size.value OR p_value)")

    if is_pivotal and missing:
        raise ValueError(f"PivotalStudyMissingFields: {', '.join(missing)}")
```

---

# 6) Postgres Guardrails (Alembic trigger)

Create `ncfd/alembic/versions/<new>_study_card_guardrails.py`:

```python
"""study card pivotal guardrails"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "0098ee120718"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""
    CREATE OR REPLACE FUNCTION enforce_pivotal_study_card()
    RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
      is_piv bool;
      card jsonb;
      total_n int;
      primary_count int;
      has_effect_or_p bool := false;
    BEGIN
      SELECT is_pivotal INTO is_piv FROM trials WHERE trial_id = NEW.trial_id;
      IF NOT is_piv THEN RETURN NEW; END IF;

      card := NEW.extracted_jsonb;

      SELECT COALESCE(jsonb_array_length(card->'primary_endpoints'),0)
      INTO primary_count;
      IF primary_count = 0 THEN
        RAISE EXCEPTION 'PivotalStudyMissingFields: primary_endpoints';
      END IF;

      total_n := (card #>> '{sample_size,total_n}')::int;
      IF total_n IS NULL THEN
        RAISE EXCEPTION 'PivotalStudyMissingFields: sample_size.total_n';
      END IF;

      IF card #>> '{populations,analysis_primary_on}' IS NULL THEN
        RAISE EXCEPTION 'PivotalStudyMissingFields: populations.analysis_primary_on';
      END IF;

      has_effect_or_p := EXISTS (
        SELECT 1
        FROM jsonb_array_elements(card->'results'->'primary') AS it(item)
        WHERE (it.item #>> '{effect_size,value}') IS NOT NULL
           OR (it.item #>> '{p_value}') IS NOT NULL
      );
      IF NOT has_effect_or_p THEN
        RAISE EXCEPTION 'PivotalStudyMissingFields: results.primary.(effect_size.value OR p_value)';
      END IF;

      RETURN NEW;
    END $$;

    DROP TRIGGER IF EXISTS trg_enforce_pivotal_study_card ON studies;
    CREATE TRIGGER trg_enforce_pivotal_study_card
      BEFORE INSERT OR UPDATE OF extracted_jsonb ON studies
      FOR EACH ROW
      EXECUTE FUNCTION enforce_pivotal_study_card();

    CREATE INDEX IF NOT EXISTS idx_studies_extracted_jsonb
      ON studies USING gin (extracted_jsonb jsonb_path_ops);
    """)

def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_pivotal_study_card ON studies;")
    op.execute("DROP FUNCTION IF EXISTS enforce_pivotal_study_card();")
    op.execute("DROP INDEX IF EXISTS idx_studies_extracted_jsonb;")
```

**Run (Docker + Alembic):**

```bash
make db_up && make db_wait
alembic revision -m "study card pivotal guardrails"  # paste code above into the new file
make migrate_up
```

---

# 7) LangExtract Adapter (Gemini) & Persistence

Create/extend `src/ncfd/extract/lanextract_adapter.py`:

```python
from __future__ import annotations
import os, json
from .validator import validate_card

def build_payload(doc_meta: dict, chunks: list[dict], trial_hint: dict) -> dict:
    return {"doc": doc_meta, "trial_hint": trial_hint, "chunks": chunks}

def run_langextract(client, prompt_text: str, payload: dict) -> dict:
    # client is your Gemini wrapper; must return raw JSON string
    msg = prompt_text + "\nINPUT:\n" + json.dumps(payload, ensure_ascii=False)
    out = client.generate_json(msg)
    card = json.loads(out)
    validate_card(card, is_pivotal=bool(card.get("trial",{}).get("is_pivotal")))
    return card
```

**Where to call it (integration points):**

* After doc ingest (`document_ingest.py`) and study row create, build `chunks` and `doc_meta`, pass with `trial_hint` from `trials` / `trial_versions`.
* On success, persist:

```sql
UPDATE studies
SET extracted_jsonb = :card::jsonb,
    coverage_level = (:card::jsonb #>> '{coverage_level}')::text
WHERE study_id = :study_id;
```

If the trigger raises, catch and log to `studies.notes_md` or failure log, and mark for manual review.

---

# 8) E2E Smoke via psql (prove guard works)

Create `scripts/study_card_smoke.sql`:

```sql
-- Seed trial as pivotal
INSERT INTO trials (trial_id, nct_id, sponsor_text, phase, indication, is_pivotal, status)
VALUES (9001, 'NCTDUMMY', 'Acme', '3', 'COPD', true, 'completed')
ON CONFLICT (trial_id) DO NOTHING;

-- Failing insert: missing effect OR p
INSERT INTO studies (study_id, trial_id, doc_type, citation, year, url, oa_status, extracted_jsonb, coverage_level)
VALUES (7001, 9001, 'PR', 'Acme PR', 2024, 'https://x', 'open',
'{"doc":{"doc_type":"PR","title":"x","year":2024,"url":"x","source_id":"s"},
  "trial":{"nct_id":"NCTDUMMY","phase":"3","indication":"COPD","is_pivotal":true},
  "primary_endpoints":[{"name":"E1"}],
  "populations":{"analysis_primary_on":"ITT","itt":{"defined":true}},
  "arms":[{"label":"A","n":100},{"label":"B","n":100}],
  "sample_size":{"total_n":200},
  "results":{"primary":[{"endpoint":"E1"}]},
  "coverage_level":"low"}'::jsonb,
'low');

-- Passing insert
INSERT INTO studies (study_id, trial_id, doc_type, citation, year, url, oa_status, extracted_jsonb, coverage_level)
VALUES (7002, 9001, 'Abstract', 'Conf Abs', 2025, 'https://y', 'open',
'{"doc":{"doc_type":"Abstract","title":"y","year":2025,"url":"y","source_id":"s2"},
  "trial":{"nct_id":"NCTDUMMY","phase":"3","indication":"COPD","is_pivotal":true},
  "primary_endpoints":[{"name":"E1","evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":1}}]}],
  "populations":{"analysis_primary_on":"ITT","itt":{"defined":true,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":1}}]}},
  "arms":[{"label":"A","n":120,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]},
          {"label":"B","n":120,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]}],
  "sample_size":{"total_n":240,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]},
  "results":{"primary":[{"endpoint":"E1","p_value":0.012,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":3}}]}]},
  "coverage_level":"high"}'::jsonb,
'high');

SELECT study_id, coverage_level,
       extracted_jsonb #>> '{results,primary,0,p_value}' AS p
FROM studies WHERE trial_id=9001;
```

**Run:**

```bash
make db_up && make db_wait && make migrate_up
psql "$PSQL_DSN" -f scripts/study_card_smoke.sql
```

---

# 9) Test Fixtures (examples + golden JSON)

Include the three examples as **golden** fixtures to prove prompt behavior.

## (a) PR input & expected output (med)

**Input payload (condensed):**

```json
{
  "doc":{"doc_type":"PR","title":"Acme reports Phase 3 TOPAZ results of AX-101 in COPD","year":2024,"url":"https://acme.com/pr/topaz","source_id":"pr_topaz_2024"},
  "trial_hint":{"nct_id":"NCT12345678","phase":"3","indication":"COPD"},
  "chunks":[
    {"page":1,"paragraph":2,"start":0,"end":180,"text":"The Phase 3 TOPAZ study met its primary endpoint, showing a statistically significant reduction in annualized exacerbation rate with AX-101 vs placebo."},
    {"page":1,"paragraph":3,"start":181,"end":360,"text":"TOPAZ enrolled 842 patients randomized 1:1 (AX-101 n=421; placebo n=421) across 120 sites."}
  ]
}
```

**Expected card (excerpt; schema-valid):**

```json
{
  "doc":{"doc_type":"PR","title":"Acme reports Phase 3 TOPAZ results of AX-101 in COPD","year":2024,"url":"https://acme.com/pr/topaz","source_id":"pr_topaz_2024"},
  "trial":{"nct_id":"NCT12345678","phase":"3","indication":"COPD","is_pivotal":true},
  "primary_endpoints":[{"name":"Annualized COPD exacerbation rate vs placebo",
    "evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2},"text_preview":"met its primary endpoint"}]}],
  "populations":{"itt":{"defined":true,"text":"Randomized 1:1, assumed ITT","evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":3}}]},
                 "pp":{"defined":false,"text":null,"evidence":[]},
                 "analysis_primary_on":"ITT"},
  "arms":[{"label":"AX-101","n":421,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":3}}]},
          {"label":"Placebo","n":421,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":3}}]}],
  "sample_size":{"total_n":842,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":3}}]},
  "results":{"primary":[{"endpoint":"Annualized exacerbation rate","population":"ITT",
                         "success_declared":true,"p_value":null,
                         "effect_size":{"metric":"Other","value":null,"evidence":[]},
                         "evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]}]},
  "coverage_level":"med",
  "coverage_rationale":"Primary endpoint and N present; no numeric effect or p-value.",
  "extraction_audit":{"missing_fields":["results.primary[0].effect_size.value","results.primary[0].p_value","multiplicity"],"assumptions":["Assumed ITT due to randomized 1:1 language."]}
}
```

## (b) Abstract input & expected output (high)

**Input (condensed):**

```json
{
  "doc":{"doc_type":"Abstract","title":"BRIGHT-1: Phase 3 trial of BX-12 in psoriasis","year":2025,"url":"https://conf.org/abs/BRIGHT1","source_id":"abs_bright1_2025"},
  "trial_hint":{"nct_id":"NCT87654321","phase":"3","indication":"Plaque psoriasis"},
  "chunks":[
    {"page":1,"paragraph":1,"start":0,"end":240,"text":"Methods: Adults... randomized 2:1 to BX-12 or placebo; primary endpoint PASI-75 at Week 16 (ITT)."},
    {"page":1,"paragraph":2,"start":241,"end":520,"text":"Results: n=660 (BX-12 n=440; placebo n=220). PASI-75 achieved by 68% vs 35% (Δ=33%; p<0.001)."}
  ]
}
```

**Expected (excerpt):**

```json
{
  "doc":{"doc_type":"Abstract","title":"BRIGHT-1: Phase 3 trial of BX-12 in psoriasis","year":2025,"url":"https://conf.org/abs/BRIGHT1","source_id":"abs_bright1_2025"},
  "trial":{"nct_id":"NCT87654321","phase":"3","indication":"Plaque psoriasis","is_pivotal":true},
  "primary_endpoints":[{"name":"PASI-75 at Week 16","timepoint":"Week 16",
    "evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":1}}]}],
  "populations":{"itt":{"defined":true,"text":"ITT","evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":1}}]},
                 "pp":{"defined":false,"text":null,"evidence":[]},
                 "analysis_primary_on":"ITT"},
  "arms":[{"label":"BX-12","n":440,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]},
          {"label":"Placebo","n":220,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]}],
  "sample_size":{"total_n":660,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]},
  "results":{"primary":[{"endpoint":"PASI-75 at Week 16","population":"ITT","success_declared":true,
                         "effect_size":{"metric":"Δ%","value":33.0,"direction_favors":"treatment",
                           "evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]},
                         "p_value":0.001,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]}]},
  "coverage_level":"high",
  "coverage_rationale":"Primary endpoint, N, ITT, and effect size with p-value present.",
  "extraction_audit":{"missing_fields":["CI bounds","multiplicity adjustment"],"assumptions":[]}
}
```

## (c) Paper input & expected output (high)

**Input (condensed):**

```json
{
  "doc":{"doc_type":"Paper","title":"EMERALD: Phase 3 randomized trial of EMR-201 in metastatic CRC","year":2023,"url":"https://doi.org/10.1000/emerald","source_id":"paper_emerald"},
  "trial_hint":{"nct_id":"NCT00000001","phase":"3","indication":"mCRC"},
  "chunks":[
    {"page":2,"paragraph":3,"start":0,"end":300,"text":"Primary endpoint was progression-free survival (PFS) per blinded independent review at Week 24; ITT was primary analysis population."},
    {"page":5,"paragraph":2,"start":0,"end":300,"text":"A total of 720 patients were randomized 1:1 (EMR-201 n=360; control n=360)."},
    {"page":8,"paragraph":1,"start":0,"end":300,"text":"PFS: HR 0.82 (95% CI 0.70–0.96), p=0.012 (stratified log-rank, alpha=0.025)."},
    {"page":10,"paragraph":4,"start":0,"end":300,"text":"Overall survival at interim: HR 0.95 (95% CI 0.80–1.12), p=0.54; no alpha spent."}
  ]
}
```

**Expected (excerpt):**

```json
{
  "doc":{"doc_type":"Paper","title":"EMERALD: Phase 3 randomized trial of EMR-201 in metastatic CRC","year":2023,"url":"https://doi.org/10.1000/emerald","source_id":"paper_emerald"},
  "trial":{"nct_id":"NCT00000001","phase":"3","indication":"mCRC","is_pivotal":true},
  "primary_endpoints":[{"name":"PFS per blinded independent review","timepoint":"Week 24",
    "evidence":[{"loc":{"scheme":"page_paragraph","page":2,"paragraph":3}}]}],
  "populations":{"itt":{"defined":true,"text":"ITT was primary analysis population",
    "evidence":[{"loc":{"scheme":"page_paragraph","page":2,"paragraph":3}}]},
    "pp":{"defined":false,"text":null,"evidence":[]},
    "analysis_primary_on":"ITT"},
  "arms":[{"label":"EMR-201","n":360,"evidence":[{"loc":{"scheme":"page_paragraph","page":5,"paragraph":2}}]},
          {"label":"Control","n":360,"evidence":[{"loc":{"scheme":"page_paragraph","page":5,"paragraph":2}}]}],
  "sample_size":{"total_n":720,"evidence":[{"loc":{"scheme":"page_paragraph","page":5,"paragraph":2}}]},
  "results":{"primary":[{"endpoint":"PFS","population":"ITT","success_declared":true,
                         "effect_size":{"metric":"HR","value":0.82,"ci_low":0.70,"ci_high":0.96,"ci_level":95,"direction_favors":"treatment",
                           "evidence":[{"loc":{"scheme":"page_paragraph","page":8,"paragraph":1}}]},
                         "p_value":0.012,"multiplicity_adjusted":true,
                         "evidence":[{"loc":{"scheme":"page_paragraph","page":8,"paragraph":1}}]}],
             "secondary":[{"endpoint":"OS (interim)","population":"ITT","success_declared":false,
                           "effect_size":{"metric":"HR","value":0.95,"ci_low":0.80,"ci_high":1.12,"ci_level":95,
                             "evidence":[{"loc":{"scheme":"page_paragraph","page":10,"paragraph":4}}]},
                           "p_value":0.54,"evidence":[{"loc":{"scheme":"page_paragraph","page":10,"paragraph":4}}]}],
             "interim_looks":[{"number":1,"alpha_spent":0.0,"evidence":[{"loc":{"scheme":"page_paragraph","page":10,"paragraph":4}}]}]},
  "coverage_level":"high",
  "coverage_rationale":"All pivotal requirements present with explicit numerics and evidence."
}
```

---

# 10) Ingestion/Workflow Steps (how it runs)

1. **Doc ingest → chunking**

   * In `ingest/document_ingest.py`, emit `chunks` with `page`, `paragraph`, `start`, `end`, `text` (keep 1-based page/paragraph; 0-based char offsets).
   * Build `doc_meta` and `trial_hint` from `studies` + `trials/trial_versions`.

2. **Call LangExtract (Gemini)**

   * Load `prompts/study_card_prompts.md` → prepend System header → append schema note.
   * `run_langextract(client, prompt_text, payload)` → returns `card`.

3. **Validate + persist**

   * `validate_card(card, is_pivotal=card['trial']['is_pivotal'])`.
   * `UPDATE studies SET extracted_jsonb=:card::jsonb, coverage_level = (:card::jsonb #>> '{coverage_level}')`.

4. **DB guardrails**

   * Alembic trigger blocks nonconforming cards for pivotal trials (prevents bad writes).

5. **Signals (optional now, ready later)**

   * If `card.signals[]` present, map to `signals` table with `evidence_span` and `source_study_id`.

---

# 11) Runbook (Makefile-style)

```bash
# Start DB, run migrations
make db_up && make db_wait && make migrate_up

# Quick schema unit test (Python validator)
pytest -q tests/test_study_card_guardrails.py

# Smoke trigger in SQL (should show one failure, one success)
psql "$PSQL_DSN" -f scripts/study_card_smoke.sql
```

---

# 12) Design Notes (precision-first)

* Prefer **ITT** for primary unless text explicitly states PP/mITT primary.
* Treat **PR** claims as low evidence unless numerics provided.
* Mark `multiplicity_adjusted=true` only when alpha control is explicitly stated (e.g., stratified log-rank alpha=0.025).
* Record **protocol\_changes** and `post_LPR` when amendments happen after last patient randomized.
* **Contradictions**: capture OS vs PFS direction conflicts when present.
* **Evidence** is mandatory for all numerics/claims; use `page_paragraph` wherever possible.
* **Coverage** is a model output but auditable via `coverage_rationale` and `extraction_audit`.

---

If you want, I can also add a tiny pytest that feeds the three goldens through `validator.validate_card` and asserts the Postgres trigger behavior.
