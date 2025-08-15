

You are helping build a precision-first “near-certain failure” detector for US-listed biotech pivotal trials. We want only a few, very high-confidence red flags—not broad coverage. Constraints & definitions:

**Scope & ethics**

- Focus on US-traded issuers (NASDAQ/NYSE/NYSE American; optional OTCQX/QB). Exclude CN/HK exchanges.
    
- No piracy: use PubMed/OpenAlex/PMC/Europe PMC/Unpaywall, company PRs, SEC filings (8-K/10-K/10-Q), ClinicalTrials.gov, FDA docs, open conference abstracts/posters. Patents via USPTO/assignment & INPADOC family data.
    
- Database: Postgres (metadata + JSONB), object storage for raw docs; DuckDB for analytics. Use LangExtract to fill structured “Study Cards” with evidence spans.
    

**Entity mapping**

- Trials come from ClinicalTrials.gov with full **version history**.
    
- Robust sponsor→ticker mapping: (1) deterministic via SEC CIK, exchange whitelist, subsidiary→parent; (2) probabilistic resolver (name/domain/alias) with high precision; (3) **asset-based backstop** (asset codes/INN mapped to listed issuer via PRs/8-Ks) to catch academia-sponsored trials.
    

**Core objects (schemas simplified)**

- `trials(trial_id, nct_id, sponsor_company_id?, sponsor_text, phase, indication, is_pivotal, primary_endpoint_text, est_primary_completion_date, status)`
    
- `trial_versions(trial_id, version_id, captured_at, raw_jsonb, primary_endpoint_text, sample_size, analysis_plan_text, changes_jsonb)`
    
- `studies(study_id, trial_id, asset_id?, doc_type{PR|Abstract|Paper|Registry|FDA}, citation, year, url, oa_status, extracted_jsonb, notes_md, coverage_level)`
    
- **Study Card (extracted_jsonb)** includes: primary/secondary endpoints, N/arms, effect sizes + CIs, p-values, ITT/PP, dropouts, imputation, subgroup info, protocol changes, quotes with page/line spans, citations.
    
- `signals(trial_id, S_id, value, severity, evidence_span, source_study_id)`
    
- `gates(trial_id, G_id, fired_bool, supporting_S_ids[], lr_used, rationale_text)`
    
- `scores(trial_id, run_id, prior_pi, logit_prior, sum_log_lr, logit_post, p_fail)`
    
- `assets(asset_id, names_jsonb{inn, internal_codes[], generic[], cas, unii, chembl_id, drugbank_id}, modality, target, moa)`
    
- `asset_ownership(asset_id, company_id, start_date, end_date, source, evidence_url)`
    
- `patents(patent_id, asset_id, family_id, jurisdiction, number, earliest_priority_date, assignees[], inventors[], status)`
    
- `patent_assignments(assignment_id, patent_id, assignor, assignee, exec_date, type, source_url)`
    
- `labels(trial_id, event_date, primary_outcome_success_bool, price_move_5d, label_source_url)`
    
- `catalysts(trial_id, window_start, window_end, certainty, sources[])`
    

**Signals (primitive)**  
S1 endpoint changed; S2 underpowered pivotal (<70% power at claimed Δ); S3 subgroup-only win without multiplicity; S4 ITT neutral/neg vs PP positive + dropout asymmetry; S5 effect size >75th percentile of wins in a “class graveyard”; S6 multiple interim looks w/o alpha spending; S7 single-arm where RCT is standard; S8 p-value cusp 0.045–0.050; S9 OS/PFS contradiction (context-dependent).

**Gates (co-dependent)**

- G1 Alpha-Meltdown = S1 & S2
    
- G2 Analysis-Gaming = S3 & S4
    
- G3 Plausibility = S5 & (S7 | S6)
    
- G4 p-Hacking = S8 & (S1 | S3)
    

**Scoring (traceable)**

- Prior failure rate π0 from historical pivotal readouts (our universe).
    
- Posterior via log-odds using calibrated **likelihood ratios (LRs)** mainly for **gates** (dominant), small/zero for primitives.
    
- Stop rules: e.g., endpoint switched after LPR; PP-only success with >20% missing ITT; unblinded subjective primary where blinding feasible → set P_fail≈0.97.
    
- Freeze features at T-14 days pre-readout; evaluate Precision@K (K=1–3), hit-rate for P_fail≥τ, median 5-day move; keep coverage % and miss audits.
    

---
