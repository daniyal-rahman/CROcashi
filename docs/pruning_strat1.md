
# 1) Retrieval & Storage Policy (the money-savers)

**Stage A — Catalog only (free/cheap)**

* Pull **PMIDs + minimal metadata** (title, journal, date, article type) via E-utilities.
* Store just this row (no abstract, no PDF).
* Compute a **U0 utility score** from metadata; keep top-K per trial in the *doc\_candidates* queue.

**Stage B — Abstracts only (still cheap)**

* Fetch **abstract text** for candidates promoted by U0.
* Compute **U1 utility score** from abstract keywords/regex (RCT, “Phase 3”, “statistically significant”, “did not meet primary endpoint”, N=, HR, ORR, p=, CI, NCT ID mention).
* If U1 < τ\_abstract → **drop** (keep only citation row).
* If U1 ≥ τ\_abstract → eligible for LLM summary pass (Tier-2).

**Stage C — Full text (rare)**

* Only fetch **open-access** PDFs (PMC/Unpaywall) when (i) U1 is high **and** (ii) the LLM asks for it (see §3 “pull-on-demand”).
* **Never store paywalled PDFs.** Store DOI/URL + abstract + extracted spans.
* For OA PDFs, **store normalized text only** (no PDF file), compressed, content-addressed (sha256). Set **TTL=90d** for non-candidates; keep only features/evidence after TTL.

**Dedup & caching**

* Key on (DOI|PMID|sha256).
* Cache LLM outputs by `(sha256_text, prompt_version)`.
* If a doc is reused across trials, you pay **once**.

**Net effect:** you’ll keep **citations + abstracts** for most docs; only a small fraction ever trigger OA full-text pulls; almost none keep the PDF blob.

---

# 2) Cheap Utility Scoring (before any LLM)

## U0: metadata-only (0–1)

* Article type boost: RCT > Clinical Trial > Review > Letter/Editorial.
* Recency boost: within ±18 months of catalyst.
* Journal tier proxy: simple whitelist/regex or venue keyword buckets.
* Title tokens: “phase 3”, “randomized”, “double-blind”, “primary endpoint”, “NCT0”.
* Penalize: animal/preclinical keywords, protocols, corrigenda.

## U1: abstract-based (0–1)

* Strong positive signals: “did not meet primary”, “no significant difference”, “failed to…”, “terminated for futility”, “confidence interval crossed 1.0”, “hazard ratio \~1”, “subgroup only significance”.
* Strong negative signals (robust): “met primary endpoint”, “statistically significant improvement”, “coprimary endpoints met”, “key secondary endpoints met”.
* Structural cues: presence of **N** (“n=”, “N=”, “patients”), randomization/masking strings, comparator words, endpoint names.

A dead simple Python skeleton you can drop into `lit/score.py`:

```python
import re
def score_metadata(title:str, article_type:str, year:int, catalyst_year:int)->float:
    t = title.lower()
    s = 0.0
    if "phase 3" in t or "phase iii" in t: s += 0.25
    if "random" in t: s += 0.20
    if "double-blind" in t or "double blind" in t: s += 0.10
    if "nct0" in t: s += 0.10
    if article_type.lower() in {"randomized controlled trial","clinical trial"}: s += 0.20
    # recency (±18m)
    if abs(year - catalyst_year) <= 1: s += 0.15
    return max(0.0, min(1.0, s))

_NEG = re.compile(r"(did not meet|no (?:significant|statistical) (?:difference|benefit)|failed to|non-?significant|ns[,\. ]|futility)", re.I)
_POS = re.compile(r"(met (?:the )?primary endpoint|statistically significant|significant improvement|superior(?:ity)?)", re.I)
_N = re.compile(r"\b(?:n\s*=\s*\d{2,4}|patients?\s+\d{2,4})\b", re.I)
_STRUCT = re.compile(r"(randomi[sz]ed|double[-\s]?blind|placebo|active comparator)", re.I)

def score_abstract(abstract:str)->float:
    s = 0.0
    if _NEG.search(abstract): s += 0.45
    if _POS.search(abstract): s += 0.00  # robust signal lowers short-utility
    if _N.search(abstract): s += 0.15
    if _STRUCT.search(abstract): s += 0.10
    # keep in [0,1]
    return max(0.0, min(1.0, s))
```

Use thresholds like `τ_abstract = 0.35–0.45` to keep only abstracts that *might* matter.

---

# 3) Periodic LLM Eval + Early Stopping (SPRT-style)

Maintain a trial-level posterior `P(short)`. After **every M docs** (e.g., M=3 abstracts or 1 OA text), run a **cheap LLM aggregator** on *summaries only* (not raw PDFs):

**Stop when:**

* `P(short) ≥ θ_high` (e.g., 0.80): **promote** trial to deep dive / write-up; or
* `P(short) ≤ θ_low` (e.g., 0.20): **park** trial 90 days; or
* **Plateau:** |ΔP| < ε for 2 consecutive evals (ε=0.03) **and** the next top doc’s expected utility < δ (δ=0.05) → **stop**.

**Pull-on-demand rule:** The LLM can request “need full text for Doc X to check endpoint definition/analysis set.” Only then fetch OA text; otherwise keep abstracts.

This makes the LLM your *budgeted reviewer*, not a PDF vacuum.

---

# 4) Global Queue Re-prioritization

Every evaluation, recompute trial priority:

```
priority = w1 * time_to_catalyst_weight   # sooner gets higher
         + w2 * P(short) * uncertainty    # explore if uncertain & promising
         + w3 * Umax_next_doc             # bang-for-buck next doc
```

* `uncertainty ≈ P*(1-P)` or entropy.
* `Umax_next_doc` = top remaining doc’s U1.
  Trials bubble up/down without you touching knobs.

---

**Defaults to keep burn low**

* `K0` (abstracts pulled per trial initially): 5–8
* `M` (docs per LLM eval): 3
* `TAU_ABS`: 0.40
* `THIGH/TLOW`: 0.80 / 0.20
* `DELTA_MIN`: 0.05

---

# 7) Budgets & Guards

```yaml
lit_budget:
  max_abstracts_per_trial_first_pass: 8
  max_abstracts_total_per_trial: 20
  allow_oa_fulltext_per_trial: 2
  tier2_llm_tokens_per_eval: 2_000      # summaries only
  eval_every_docs: 3

retention:
  store_pdf_files: false                 # text only for OA
  non_candidate_fulltext_ttl_days: 90
  always_keep: ["citations", "abstracts", "evidence_spans", "scores"]
```

* **Drift monitor:** randomly deep-dive 5–10% of “parked/low-U1” decisions to ensure you aren’t missing sleepers.
* **Compression:** gzip/zstd your `fulltext_text`; it’s tiny vs PDFs.
* **No embedding glut:** embed **only** docs that pass U1 or that LLM explicitly calls for.

---

# 8) What this practically achieves

* \~**70–85% of docs never fetch full text**; you keep only citations/abstracts.
* LLM runs are **small and periodic**, operating on **summaries**, not raw PDFs.
* The outer trial queue constantly **reprioritizes** toward the best expected gain per dollar.
* Storage footprint is controlled by **text-only OA + TTL**; paid PDFs are link-only.

---

# 9) Implementation Plan

## Overview
This document outlines a 7-phase implementation plan to replace the existing smart stopping system with the new pruning strategy. The implementation will be built incrementally, allowing for testing and validation at each stage.

## Phase 1: Core Infrastructure (Week 1)

### 1.1 Create New Utility Scoring Module
**File**: `src/ncfd/ingest/literature_scoring.py`

```python
class LiteratureScorer:
    def score_metadata(self, title: str, article_type: str, year: int, catalyst_year: int) -> float
    def score_abstract(self, abstract: str) -> float
    def compute_uncertainty(self, p_short: float) -> float
    def calculate_trial_priority(self, trial_data: dict) -> float
```

### 1.2 Create Document Queue Management
**File**: `src/ncfd/ingest/document_queue.py`

```python
class DocumentQueue:
    def __init__(self, config: dict)
    def add_trial_candidates(self, trial_id: str, candidates: List[Document])
    def get_next_trial_batch(self, batch_size: int) -> List[str]
    def update_trial_priority(self, trial_id: str, new_priority: float)
    def mark_trial_complete(self, trial_id: str, status: str)
```

### 1.3 Create LLM Evaluation Engine
**File**: `src/ncfd/ingest/llm_evaluator.py`

```python
class LLMEvaluator:
    def __init__(self, config: dict, llm_client)
    def evaluate_trial_batch(self, trial_id: str, doc_summaries: List[dict]) -> EvaluationResult
    def should_stop_evaluation(self, trial_id: str, current_posterior: float) -> StopDecision
    def request_full_text(self, doc_id: str, reason: str) -> bool
```

## Phase 2: Replace Smart PubMed Client (Week 2)

### 2.1 Overhaul `smart_pubmed.py`
**Changes**:
- Remove existing early stopping logic
- Implement three-stage retrieval:
  - Stage A: Metadata-only (PMID + basic info)
  - Stage B: Abstract fetching for high-U0 candidates
  - Stage C: Full-text only when LLM requests it

### 2.2 Update `pubs.py`
**Changes**:
- Integrate with new scoring system
- Implement U0/U1 utility scoring
- Add document queue management
- Remove old literature ingestion logic

## Phase 3: Document Pipeline Integration (Week 3)

### 3.1 Update `document_ingest.py`
**Changes**:
- Add document queue integration
- Implement three-stage processing
- Add LLM evaluation hooks
- Update status tracking for new workflow

### 3.2 Create New Pipeline Stages
**File**: `src/ncfd/ingest/literature_pipeline.py`

```python
class LiteraturePipeline:
    def stage_a_metadata_only(self, trial_id: str) -> List[Document]
    def stage_b_abstract_evaluation(self, candidates: List[Document]) -> List[Document]
    def stage_c_full_text_on_demand(self, doc_id: str) -> Optional[Document]
    def run_llm_evaluation(self, trial_id: str) -> EvaluationResult
```

## Phase 4: Configuration & Budget Management (Week 4)

### 4.1 Update Configuration Files
**File**: `config/literature_config.yaml`

```yaml
literature_ingestion:
  budget:
    max_abstracts_per_trial_first_pass: 8
    max_abstracts_total_per_trial: 20
    allow_oa_fulltext_per_trial: 2
    tier2_llm_tokens_per_eval: 2000
    eval_every_docs: 3
  
  thresholds:
    tau_abstract: 0.40
    theta_high: 0.80
    theta_low: 0.20
    delta_min: 0.05
  
  retention:
    store_pdf_files: false
    non_candidate_fulltext_ttl_days: 90
    always_keep: ["citations", "abstracts", "evidence_spans", "scores"]
```

### 4.2 Create Budget Monitor
**File**: `src/ncfd/ingest/budget_monitor.py`

```python
class BudgetMonitor:
    def __init__(self, config: dict)
    def check_budget_limits(self, trial_id: str, operation: str) -> bool
    def track_usage(self, trial_id: str, operation: str, cost: float)
    def get_trial_budget_status(self, trial_id: str) -> BudgetStatus
```

## Phase 5: Database Schema Updates (Week 5)

### 5.1 Create New Tables
**Migration**: `alembic/versions/xxx_add_literature_scoring.py`

```sql
-- Trial evaluation tracking
CREATE TABLE trial_evaluations (
    evaluation_id SERIAL PRIMARY KEY,
    trial_id INTEGER REFERENCES trials(trial_id),
    evaluation_round INTEGER NOT NULL,
    p_short_posterior NUMERIC(5,4),
    documents_evaluated INTEGER,
    stop_decision TEXT,
    llm_tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Document utility scores
CREATE TABLE document_utilities (
    doc_id INTEGER REFERENCES documents(doc_id),
    u0_metadata_score NUMERIC(5,4),
    u1_abstract_score NUMERIC(5,4),
    evaluation_round INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (doc_id, evaluation_round)
);

-- Trial priority queue
CREATE TABLE trial_priority_queue (
    trial_id INTEGER REFERENCES trials(trial_id),
    priority_score NUMERIC(10,6),
    last_updated TIMESTAMP DEFAULT NOW(),
    status TEXT DEFAULT 'active',
    PRIMARY KEY (trial_id)
);
```

## Phase 6: Integration & Testing (Week 6)

### 6.1 Update Main Orchestrator
**File**: `src/ncfd/pipeline/orchestrator.py`
**Changes**:
- Replace `_run_literature_review_pipeline` with new system
- Integrate document queue management
- Add LLM evaluation scheduling
- Update pipeline statistics

### 6.2 Create Test Suite
**File**: `tests/test_literature_scoring.py`
**Tests**:
- Utility scoring accuracy
- Queue prioritization logic
- LLM evaluation integration
- Budget enforcement

### 6.3 End-to-End Testing
**File**: `tests/test_literature_pipeline.py`
**Tests**:
- Complete pipeline workflow
- Three-stage document processing
- LLM-driven stopping decisions
- Budget compliance

## Phase 7: Monitoring & Optimization (Week 7)

### 7.1 Create Monitoring Dashboard
**File**: `src/ncfd/monitoring/literature_monitor.py`

```python
class LiteratureMonitor:
    def get_pipeline_metrics(self) -> Dict[str, Any]
    def get_budget_utilization(self) -> Dict[str, Any]
    def get_trial_evaluation_stats(self) -> Dict[str, Any]
    def generate_optimization_recommendations(self) -> List[str]
```

### 7.2 Implement Drift Monitoring
**File**: `src/ncfd/ingest/drift_monitor.py`

```python
class DriftMonitor:
    def __init__(self, config: dict)
    def sample_parked_trials(self, sample_rate: float = 0.05) -> List[str]
    def deep_dive_trial(self, trial_id: str) -> DriftAnalysis
    def update_thresholds_if_needed(self, analysis: DriftAnalysis)
```

## Implementation Order

1. **Week 1**: Core scoring and queue infrastructure
2. **Week 2**: Replace Smart PubMed client
3. **Week 3**: Document pipeline integration
4. **Week 4**: Configuration and budget management
5. **Week 5**: Database schema updates
6. **Week 6**: Integration and testing
7. **Week 7**: Monitoring and optimization

## Key Benefits of This Approach

1. **Cost Control**: 70-85% reduction in full-text storage
2. **Intelligent Prioritization**: Trials automatically bubble up/down based on promise
3. **LLM Efficiency**: Small, focused evaluations instead of PDF processing
4. **Adaptive Learning**: System learns from evaluation results
5. **Budget Enforcement**: Hard limits prevent runaway costs

## Migration Strategy

1. **Parallel Implementation**: Build new system alongside existing one
2. **Feature Flags**: Use configuration to switch between old/new systems
3. **Gradual Rollout**: Start with subset of trials
4. **Rollback Plan**: Keep old system as fallback during transition
