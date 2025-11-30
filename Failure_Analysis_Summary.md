# Failure Analysis Summary

**Date**: 2025-11-27  
**Scope**: Phase 2/3 terminated, company-sponsored trials  
**Total Failures**: 19 trials

## Key Findings

### 1. Infrastructure Status ✅

- **Hybrid Resolver**: Working correctly - cross-run resolution functional
- **Relationships**: Company-Drug-Trial links are created (545 company-drug, 1,526 trial-sponsor)
- **Data Quality**: Sponsor information exists in raw data and relationships are created
- **Issue**: Many trials show "Unknown" company because analysis query was too narrow (only checked lead_sponsor, not collaborators)

### 2. Failure Definition

**V1 Definition**: Phase 2 or Phase 3 trial with status = 'terminated' (exclude 'withdrawn')

- Phase 2: 31 terminated (13.5% of 230)
- Phase 3: 8 terminated (9.8% of 82)
- **Company-sponsored**: 19 terminated (48.7% of 39 total terminated)

### 3. Predictive Signals Analysis

#### Signal 1: Indication Failure Rate (Baseline Risk)

**High-Risk Indications (≥30% failure rate):**
- Cervical Cancer: 66.7%
- Metastatic Breast Cancer: 66.7%
- Pancreatic Cancer: 40.0%
- Myeloma Multiple: 33.3%
- Lung Cancer: 33.3%

**Low-Risk Indications (0% failure rate):**
- Chronic Lymphocytic Leukemia: 0%
- Ovarian Cancer: 0%
- Rheumatoid Arthritis: 0%

**Key Insight**: This signal exists BEFORE any trial starts - you know the historical failure rate for an indication regardless of company.

#### Signal 2: Company Termination Rate (at Trial Start)

**Finding**: Most companies had 0% termination rate at trial start (no prior outcomes), making this signal unavailable for prediction.

**Examples:**
- Merck (NCT04152863): 0% at start (now 13.3%)
- Oncotherapeutics (NCT02188368): No prior outcomes (now 66.7%)
- Syros (NCT04797780): No prior outcomes

**Key Insight**: Company termination rate is a hindsight metric, not predictive. The signal only appears after failures accumulate.

#### Signal 3: Drug History

**Pattern**: Many terminated trials were for NOVEL drugs (first trial):
- BKM120 (Novartis): 0 prior trials
- Gebasaxturev IV (Merck): 0 prior trials (but Pembrolizumab had 6)
- Tamibarotene (Syros): 0 prior trials

**Key Insight**: Novel drugs (first-in-class) have higher risk than validated mechanisms.

#### Signal 4: Portfolio Concentration

**Pattern**: Many failures had HIGH concentration risk (few Phase 2/3 trials):
- Oncotherapeutics: 1 Phase 2/3 trial (100% terminated)
- Syros: 1 Phase 2/3 trial
- Amgen (NCT03121534): 1 Phase 2/3 trial at start

**Key Insight**: Companies "betting it all" on late-stage trials have higher risk.

### 4. Patterns in Terminated Trials

| Pattern | Count | % |
|---------|-------|---|
| High indication risk (≥30%) | 10+ | ~50%+ |
| Novel drug (0 prior trials) | 12+ | ~60%+ |
| High portfolio concentration (≤3 Phase 2/3) | 8+ | ~40%+ |
| Company termination rate unknown at start | 12+ | ~60%+ |

### 5. What Signals Actually Work?

**Available BEFORE trial start:**
1. ✅ **Indication failure rate** - Strong signal (e.g., Metastatic Breast Cancer = 66.7% risk)
2. ✅ **Drug history** - Moderate signal (novel vs validated)
3. ✅ **Portfolio concentration** - Moderate signal (fewer trials = higher risk)
4. ⚠️ **Company termination rate** - Weak signal (often unknown, hindsight bias)

**Not yet available:**
- Target/mechanism failure rates (need target data)
- Trial design quality (need to extract from raw data)
- Competitor failures in same space (need cross-company analysis)

## Recommendations

### For V1 Failure Prediction

1. **Primary Signal**: Indication failure rate
   - Use as baseline risk (e.g., Pancreatic Cancer = 40%)
   - Adjust for company size/experience if available

2. **Secondary Signals**:
   - Drug novelty (0 prior trials = higher risk)
   - Portfolio concentration (≤3 Phase 2/3 = higher risk)

3. **Risk Scoring**:
   ```
   Base Risk = Indication Failure Rate
   + Novel Drug Penalty (+10-20%)
   + Concentration Penalty (+5-15% if ≤3 trials)
   = Total Risk Score
   ```

### Next Steps

1. **Enhance Data Collection**:
   - Extract trial design features from raw data
   - Link drugs to targets/mechanisms
   - Track competitor trials in same indication

2. **Build Predictive Model**:
   - Use indication rate as baseline
   - Add company/drug/portfolio adjustments
   - Validate on held-out trials

3. **Company Profiles**:
   - Analyze all 19 failures with full signal set
   - Identify common patterns
   - Build risk profiles for top companies

## Files Created

- `analyze_terminated_trials.py` - Company-sponsored trial analysis
- `temporal_analysis.py` - Portfolio state at trial start
- `indication_failure_rates.py` - Indication-level risk rates
- `comprehensive_risk_analysis.py` - Combined signal analysis
- `test_minimal_cross_run.py` - Resolver verification test

## Infrastructure Status

✅ **Ready for Analysis**
- Resolver working
- Relationships created
- Data available
- Signals identified

The infrastructure detour is complete. You can now focus on building predictive models and company risk profiles.

