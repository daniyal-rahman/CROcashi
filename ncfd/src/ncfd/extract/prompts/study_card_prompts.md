# Study Card Extraction Prompts

## Coverage Rubric

**high**: **all** present w/ evidence → primary endpoint; total N (+ arms); **analysis_primary_on** (ITT/PP/mITT); numeric **effect_size.value** **or** **p_value** for primary.

**med**: exactly one of the above is missing or ambiguous.

**low**: ≥2 missing or text is promotional/ambiguous.

---

## System Header

You are Google Gemini used via LangExtract to populate a strict JSON schema called "Study Card".
Return ONLY valid JSON conforming to the provided schema. No comments or prose.

Rules:
- Extract ONLY what the text supports; do not invent values.
- For EVERY numeric or claim (N, per-arm n, endpoints, effect sizes, CIs, p-values, ITT/PP selection, dropouts, imputation, success/failure statements, protocol changes), attach ≥1 evidence span using:
  page_paragraph: {"scheme":"page_paragraph","page":<1-based>,"paragraph":<1-based>}
  or char_offsets: {"scheme":"char_offsets","start":<0-based>,"end":<exclusive>}
- If conflicts, prefer PRIMARY endpoint and ITT unless PP is explicitly primary. Record uncertainty in extraction_audit and reduce coverage_level.
- Compute coverage_level using the rubric provided and include coverage_rationale.
- **CRITICAL**: Every numeric field in results.primary must have ≥1 evidence span.

---

## Task Body

SCHEMA: {{SCHEMA_JSON}}

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
- **EVIDENCE REQUIREMENT**: Every numeric claim must have evidence spans.
- Output MUST validate against schema.

---

## Document Type Specific Guidance

### PR (Press Release)
- Likely `coverage_level="low"` or "med" unless numerics present
- Focus on company claims and trial announcements
- Be conservative with success declarations

### Abstract
- Capture numerics when available
- Multiplicity often absent—note in audit
- Look for conference presentation details

### Paper
- Pull HR/CI/p & alpha handling from methods/results
- ITT as primary unless text contradicts
- Focus on statistical rigor and methodology

### Registry
- Focus on trial design and enrollment
- May have limited results data
- Note regulatory context

### FDA
- Emphasize regulatory decisions and safety
- Look for approval/denial language
- Note post-marketing requirements
