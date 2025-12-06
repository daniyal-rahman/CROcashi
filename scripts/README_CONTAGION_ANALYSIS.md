# Clinical Trial Failure Contagion Analysis

## Overview

This analysis examines "failure contagion" - whether one company's clinical trial termination predicts other companies terminating trials in the same indication within 12 months.

**Key Finding**: 60% of trial terminations lead to competitor terminations in the same indication within a year, driven by scientific validation signals, competitive intelligence, and funding cascades.

## Files in this Analysis

### 1. Main SQL Analysis Script
**File**: `failure_contagion_analysis.sql` (15KB)
- Complete PostgreSQL analysis code
- Creates temp tables: `termination_events`, `contagion_pairs`, `indication_contagion_rates`
- Generates all statistics, case studies, and temporal trends
- **Usage**: `psql -d biotech_kg -f failure_contagion_analysis.sql > results.txt`

### 2. Full Analysis Report
**File**: `failure_contagion_report.md` (28KB)
- Comprehensive methodology documentation
- Detailed case studies (Glioblastoma, COVID-19, Multiple Myeloma)
- Top 20 indications and companies analysis
- Strategic recommendations for biopharma companies and investors
- Limitations and caveats
- **Best for**: Deep dive into findings, academic/research use, internal strategy docs

### 3. Executive Summary
**File**: `failure_contagion_executive_summary.md` (14KB)
- High-level findings and implications
- Case study highlights
- Strategic recommendations
- Quick decision frameworks
- **Best for**: Board presentations, investor updates, executive briefings

### 4. Key Statistics Quick Reference
**File**: `contagion_key_statistics.md` (7.7KB)
- All key numbers in bullet format
- Quick lookup tables
- Decision frameworks
- Red flags and green flags checklists
- **Best for**: Due diligence, quick assessments, decision-making support

### 5. Summary Statistics Generator
**File**: `contagion_summary_stats.sql` (3.2KB)
- Quick summary queries (requires temp tables from main analysis)
- Generates compact output for presentations
- **Usage**: Run after `failure_contagion_analysis.sql` in same session

## How to Use This Analysis

### Option 1: Run the Full Analysis (Fresh Data)

```bash
# Run the main SQL analysis (takes 1-2 minutes)
psql -d biotech_kg -f scripts/failure_contagion_analysis.sql > contagion_results.txt

# Optionally run summary stats (in same psql session)
psql -d biotech_kg -f scripts/contagion_summary_stats.sql
```

This will:
- Analyze all 4,255+ terminations from 2010-2025
- Identify 9,473 contagion pairs
- Generate all statistics and case studies
- Save detailed output to `contagion_results.txt`

### Option 2: Read the Pre-Generated Reports

If you just need the findings (no need to re-run SQL):

1. **For quick overview**: Read `failure_contagion_executive_summary.md`
2. **For specific numbers**: Use `contagion_key_statistics.md` as reference
3. **For deep analysis**: Read `failure_contagion_report.md`

### Option 3: Customize the Analysis

Modify `failure_contagion_analysis.sql` to:
- Change the contagion window (currently 12 months)
- Focus on specific therapeutic areas
- Analyze different time periods
- Add new metrics (e.g., geography, trial size)

Example customizations:

```sql
-- Change contagion window to 6 months
AND te2.termination_date <= te1.termination_date + INTERVAL '6 months'

-- Focus on oncology only
AND d.disease_name LIKE '%cancer%' OR d.disease_name LIKE '%carcinoma%'

-- Analyze only 2020-2024
WHERE te1.termination_date BETWEEN '2020-01-01' AND '2024-12-31'
```

## Key Findings Summary

### Overall Metrics
- **4,255 terminations** analyzed (2010-2025)
- **9,473 contagion pairs** identified
- **60.7% peak contagion rate** (2022)
- **~6 months** average time to follower termination

### Top Contagion Indications
1. Colorectal Cancer (98%)
2. Atopic Dermatitis (97%)
3. Pancreatic Cancer (96%)
4. Acute Myeloid Leukemia (95%)
5. Multiple Myeloma (94%)

### Top Bellwether Companies
1. Pfizer (224 followers from 34 terminations)
2. Novartis (214 followers from 46 terminations)
3. AstraZeneca (170 followers from 38 terminations)
4. Bristol-Myers Squibb (151 followers from 33 terminations)
5. Boehringer Ingelheim (150 followers from 15 terminations)

### Phase Analysis
- **Phase 2** accounts for 70% of all contagion (5,686 of 9,473 follower events)
- Phase 2 is the critical juncture for competitive dynamics

## Database Schema Requirements

The analysis uses these tables from `biotech_kg`:

```
clinical_trials
  - trial_id (uuid)
  - nct_id
  - status (terminated, withdrawn, completed, etc.)
  - start_date, completion_date, primary_completion_date
  - phase, why_stopped

trial_sponsors
  - trial_id (uuid)
  - entity_id (uuid, references companies)
  - entity_type ('company')
  - sponsor_role ('lead_sponsor')

companies
  - company_id (uuid)
  - name

trial_diseases
  - trial_id (uuid)
  - disease_id (uuid)

diseases
  - disease_id (uuid)
  - disease_name
```

## Use Cases

### For Biotech Companies
- **Portfolio planning**: Identify high-risk indications before committing late-stage investment
- **Competitive intelligence**: Monitor bellwether company terminations in your therapeutic areas
- **Go/no-go decisions**: Use contagion data to inform Phase 2→3 decisions
- **Investor communications**: Proactively address competitive landscape concerns

### For Investors (VC, Public Markets)
- **Due diligence**: Assess contagion risk during investment evaluation
- **Portfolio monitoring**: Track competitor terminations in portfolio companies' indications
- **Early warning**: 6-month lead time between competitor failure and potential portfolio impact
- **Valuation**: Adjust valuations based on indication-level contagion risk

### For Pharma Business Development
- **In-licensing**: Identify acquisition opportunities from contagion-driven exits
- **Target prioritization**: Focus on low-contagion indications with better risk/reward
- **Partnership strategy**: Address competitive landscape in partnership negotiations

### For Academic/Policy Research
- **Industry dynamics**: Study competitive behavior in pharmaceutical R&D
- **Innovation patterns**: Understand how scientific information spreads
- **Resource allocation**: Identify indications with systemic challenges requiring new approaches

## Limitations

1. **Causation vs. Correlation**: Analysis shows correlation, not proven causation
2. **COVID-19 Outlier**: Pandemic represents 31% of contagion events, may overstate typical rates
3. **Termination Date Proxy**: Uses completion dates as proxy for termination decision dates
4. **Heterogeneous Reasons**: Not all terminations are "failures" (some are strategic, enrollment-driven)
5. **Disease Matching**: Requires exact disease_id match, may miss semantic similarities

See full report for detailed discussion of limitations.

## Citation

If using this analysis in publications or presentations, please cite:

```
Clinical Trial Failure Contagion Analysis
Database: biotech_kg PostgreSQL (37,341+ trials)
Analysis Date: December 2025
Time Period: 2010-2025
Methodology: 12-month contagion window, lead sponsor terminations
```

## Contact & Questions

For questions about:
- **Data access**: Contact database administrator for biotech_kg credentials
- **Methodology**: See detailed methodology section in `failure_contagion_report.md`
- **Custom analysis**: Modify SQL scripts or create derived analyses

## Version History

- **v1.0** (Dec 2025): Initial comprehensive analysis
  - 4,255 terminations analyzed
  - 9,473 contagion pairs identified
  - Case studies: Glioblastoma, COVID-19, Multiple Myeloma
  - Strategic recommendations for companies and investors

## Next Steps / Future Enhancements

Potential extensions of this analysis:

1. **Mechanism-level contagion**: Do PD-1 inhibitor failures predict other PD-1 failures across indications?
2. **Geographic analysis**: Does contagion differ by region (US vs. EU vs. Asia)?
3. **Company size effects**: Do small biotech terminations trigger different responses than Big Pharma?
4. **Trial design factors**: Do biomarker-selected trials show different contagion patterns?
5. **Financial market impact**: Correlation with stock price movements post-termination?
6. **Predictive modeling**: Machine learning model to predict contagion risk?

Contributions and extensions welcome!
