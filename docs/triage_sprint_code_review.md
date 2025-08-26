# Triage Sprint Code Review — Critical Issues Report

Scope: Table mismatches and missing tables are out of scope. Focus is on duplicate functionality and critical bugs only.

## High-Severity Findings

- Unified orchestrator imports non-existent base class
  - File: `src/ncfd/pipeline/unified_orchestrator.py`
  - Issue: `from .orchestrator import PipelineOrchestrator` imports a class that does not exist anywhere in `src/ncfd/pipeline/orchestrator.py` (only `CROcashiOrchestrator` is defined). Any reference to `PipelineOrchestrator` will break at import time.
  - Risk: Hard import error prevents module initialization; orchestrator unusable.
  - Suggested fix: Remove the unused import or implement a real `PipelineOrchestrator` if intended.

- Incorrect argument order in page-based extraction adapter
  - File: `src/ncfd/extract/lanextract_adapter.py`
  - Function: `extract_study_card_from_document_pages`
  - Lines: ~498-499
  - Issue: Returns `extract_study_card_from_document(doc_meta, chunks, trial_hint)` but the signature is `extract_study_card_from_document(document_text: str, document_metadata: Dict[str, Any], trial_context: Optional[Dict[str, Any]] = None, ...)`. The first argument should be document text (string), but `doc_meta` (dict) is passed; the second is metadata (dict) but `chunks` (list) is passed.
  - Risk: Type/validation error at runtime; extraction always fails or misbehaves.
  - Suggested fix: Either adjust `extract_study_card_from_document` to accept `(text, metadata, ...)` and join `chunks` into text, or change the call to pass a concatenated text string and the metadata dict in the correct order.

- Hard-coded placeholder IDs in enhanced extractor
  - File: `src/ncfd/catalyst/enhanced_extractor.py`
  - Function: `extract_enhanced_fields`
  - Lines: ~195-197
  - Issue: Calls `basic_extractor.extract_study_card_fields(1, 1, study_data)` using hard-coded `study_id` and `trial_id` values. This contaminates downstream analytics and logs.
  - Risk: Mis-attribution of extracted results; breaks traceability and quality evaluation.
  - Suggested fix: Plumb real `study_id` and `trial_id` or change the basic extractor to accept optional IDs.

- Duplicate, conflicting prompt loaders
  - Files: 
    - `src/ncfd/extract/lanextract_adapter.py` defines `load_prompts()` embedding a minified schema from `study_card.schema.json`.
    - `src/ncfd/extract/prompts/study_card_prompts.py` also defines `load_prompts()` and helpers.
  - Issue: Two independent prompt-loading implementations can diverge (different schema embedding behavior) and increase maintenance risk.
  - Risk: Inconsistent prompts used across code paths; unexpected extraction differences.
  - Suggested fix: Consolidate to a single prompt loader (prefer `src/ncfd/extract/prompts/study_card_prompts.py`) and import it from all call sites.

- Overlapping extraction entry points
  - Files:
    - `src/ncfd/extract/lanextract_adapter.py`: `extract_study_card_from_document` (stable adapter) and `run_langextract()` wrapper.
    - `src/ncfd/pipeline/ingestion.py`: a mock `extract_study_card_from_document(document_path)` used by the ingestion pipeline.
  - Issue: Same-named function in ingestion is a mock returning synthetic data, masking real adapter extraction during pipeline runs.
  - Risk: Tests or runs appear to succeed with synthetic data; hides real extraction failures.
  - Suggested fix: Rename the mock to make it explicit (e.g., `mock_extract_study_card_from_document`) and clearly separate from the adapter; ensure production code uses the adapter.

- Deterministic resolver split across two modules with different return types
  - Files:
    - `src/ncfd/mapping/deterministic.py`: `resolve_company()` returns `Resolution` dataclass.
    - `src/ncfd/mapping/det.py`: wraps deterministic (alias/domain) and regex rules into `DetDecision` and also provides `_det_by_rules()`.
  - Issue: Two “deterministic” flows with different dataclasses (`Resolution` vs `DetDecision`). CLI bridges them by constructing `DetDecision` from the exact deterministic result, but the existence of two types increases confusion and duplication risk.
  - Risk: Inconsistent handling across callers; accidental mixing of types leads to subtle bugs.
  - Suggested fix: Unify on a single deterministic result type and keep regex rules in the same module or a clearly named helper; retain thin wrapper functions only if necessary.

## Additional Notable Risks (medium)

- Multiple catalyst services with overlapping responsibilities
  - Files: `src/ncfd/catalyst/service.py`, `enhanced_service.py`, `comprehensive_service.py`
  - Observation: Three services orchestrate analysis/evaluation of study cards with partial overlaps. While not a direct bug, the duplication increases maintenance load and chances of divergence.
  - Suggestion: Define a shared core interface/abstractions and compose feature sets to reduce duplication.

- SEC LangExtract extractor partially duplicates adapter responsibilities
  - File: `src/ncfd/ingest/sec_langextract.py`
  - Observation: Custom schema, validation, and extraction flows mirror some adapter guarantees. Ensure these do not drift from common validation rules.

## Quick Checks Passed

- `src/ncfd/extract/prompts/study_card_prompts.md` and `study_card_prompts.py` exist; adapter references are present.
- `DocumentIngester` exists and is used by `CROcashiOrchestrator`.

## Suggested Next Steps

1. Remove/replace the broken `PipelineOrchestrator` import in `unified_orchestrator.py`.
2. Correct the argument ordering in `extract_study_card_from_document_pages` or align the callee signature.
3. Replace hard-coded IDs in `enhanced_extractor.py` with real parameters.
4. Consolidate prompt loading to a single implementation.
5. Rename and quarantine the ingestion mock extractor; wire the real adapter for non-test code paths.
6. Plan a consolidation of deterministic result types and modules.