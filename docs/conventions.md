# Study Card System Conventions

This document defines standardized conventions for the Study Card System to ensure consistency across all extracted data.

## Endpoint Synonyms Map

### Primary Endpoints
- `TTP` ≈ `PFS` (context-specific - use TTP for time-to-progression, PFS for progression-free survival)
- `overall survival` → `median_os` (median overall survival)
- `response` → `orr_recist` (overall response rate by RECIST criteria)
- `CA-125 response` → `ca125_response` (CA-125 biomarker response)

### Secondary Endpoints
- `time to progression` → `median_ttp` (median time to progression)
- `progression-free survival` → `median_pfs` (median progression-free survival)
- `disease control rate` → `dcr_recist` (disease control rate by RECIST)
- `duration of response` → `median_dor` (median duration of response)

## Units Mapping

### Time Units
- **TTP/PFS**: Always emit `weeks` if reported that way, convert to `weeks` if in months
- **OS**: Use `months` unless paper explicitly uses another unit
- **Response duration**: Use `weeks` for short durations, `months` for longer

### Response Units
- **Percentages**: Always use `percent` (not %)
- **Counts**: Use `count` for absolute numbers
- **Ratios**: Use `ratio` for hazard ratios, odds ratios, etc.

### Standard Conversions
- 1 month = 4.33 weeks
- 1 year = 12 months
- 1 cycle = typically 3-4 weeks (context-dependent)

## Analysis Set Vocabulary

### Standard Analysis Sets
- `intent_to_treat` - Intent-to-treat population
- `per_protocol` - Per-protocol population  
- `safety` - Safety population
- `efficacy` - Efficacy population
- `not_specified` - When paper doesn't define analysis sets

### Analysis Set Rules
- If not named, use `not_specified` and carry **denominators** per endpoint
- Never default to "ITT" unless explicitly stated
- Record actual denominators used for each endpoint
- Distinguish between "evaluable" and "enrolled" populations

## Section Names Normalization

### Methods Sections
- `Patients and Methods` → `Methods`
- `Study Design` → `Methods`
- `Statistics` → `Methods`
- `Statistical Analysis` → `Methods`

### Results Sections  
- `Results` → `Results`
- `Efficacy Results` → `Results`
- `Safety Results` → `Results`
- `Assessment of Response` → `Results`

### Tables and Figures
- `Table 1` → `Table`
- `Figure 1` → `Figure`
- `Supplementary Table S1` → `Table`

## Metric Enum Values

### Required Metrics (ResultsFactsheet)
- `median_os` - Median overall survival
- `median_ttp` - Median time to progression  
- `median_pfs` - Median progression-free survival
- `orr_recist` - Overall response rate (RECIST)
- `ca125_response` - CA-125 response rate
- `os_fixed_time` - OS at fixed timepoint
- `pfs_fixed_time` - PFS at fixed timepoint
- `response_rate` - General response rate

### Metric Rules
- Use exact enum values - no ad-hoc metrics like `survival_rate` or `os_rate`
- `timepoint` is **for fixed-time rates only** - reject if provided with `median_*` metrics
- Every numeric must have `units` and ≥1 `span_id`

## Blinding Enum Values

### Blinding Levels
- `none_open_label` - No blinding, open label
- `single_blind` - Single blind (investigator or patient)
- `double_blind` - Double blind
- `not_reported` - Blinding not specified

## Statistics Methods

### Common Statistical Methods
- `Kaplan-Meier` - Kaplan-Meier survival analysis
- `Gehan` - Gehan two-stage design
- `Cox` - Cox proportional hazards
- `Log-rank` - Log-rank test
- `Fisher` - Fisher's exact test
- `Chi-square` - Chi-square test

## Assessment Criteria

### RECIST Criteria
- `RECIST 1.0` - Response Evaluation Criteria in Solid Tumors v1.0
- `RECIST 1.1` - Response Evaluation Criteria in Solid Tumors v1.1
- `iRECIST` - Immune RECIST for immunotherapy

### CA-125 Criteria
- `GCIG` - Gynecological Cancer InterGroup criteria
- `Rustin` - Rustin criteria for CA-125 progression

## Validation Rules

### Hard Validation Rules
- Reject any artifact containing `"Field("` substrings
- Every numeric in ResultsFactsheet must have `units` and ≥1 `span_id`
- `metric` must be from the enum (no ad-hoc values)
- `timepoint` is for fixed-time rates only
- MethodCard objects are real objects (not JSON strings)
- Use `analysis_denominators` instead of faking ITT/PP when undefined
