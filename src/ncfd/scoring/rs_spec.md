# R/S Scoring Specification

## Overview
This document defines the R (Relevance) and S (Shortability) scoring system for PubMed literature analysis. R and S are computed independently per (trial, document) pair, with final trial actions determined by the R×S cell.

## R (Relevance) Scoring

### R Tiers and Thresholds

#### R3: High Relevance (0.75+)
**Same asset/INN (or unambiguous alias), same indication/line, mentions NCT or is the protocol/results for the exact study; human P2/P3.**

**Examples**:
- Document explicitly mentions the trial's NCT ID
- Document is the primary results paper for the trial
- Document discusses the exact asset in the exact indication
- Document is a protocol paper for the trial

**R3 Components**:
- `same_asset`: True (exact match or unambiguous alias)
- `same_nct`: True (NCT ID mentioned)
- `same_indication`: True (exact indication match)
- `same_lot`: True (same line of therapy)
- `human_phase`: P2/P3 (human pivotal studies)

#### R2: Medium-High Relevance (0.55-0.74)
**Same asset & indication but different line; or same MOA/classmate in identical indication; or systematic review/meta including the asset.**

**Examples**:
- Same asset in different line of therapy
- Same drug class in identical indication
- Systematic review including the asset
- Meta-analysis with the asset

**R2 Components**:
- `same_asset`: True OR `same_moa_class`: True
- `same_indication`: True
- `same_lot`: False (different line) OR `review_type`: systematic/meta
- `human_phase`: P2/P3 (human studies)

#### R1: Medium Relevance (0.35-0.54)
**Same asset preclinical/P1; or classmate human data in indication; general reviews/guidelines.**

**Examples**:
- Same asset in preclinical or P1 studies
- Same drug class in human studies
- General reviews or guidelines
- Related mechanisms in indication

**R1 Components**:
- `same_asset`: True OR `same_moa_class`: True
- `same_indication`: True OR `related_indication`: True
- `human_phase`: P1/preclinical OR `review_type`: general
- `evidence_strength`: moderate

#### R0: Low Relevance (<0.35)
**Off-topic or minimally related.**

**Examples**:
- Different asset class
- Different indication area
- Animal-only studies
- Unrelated mechanisms

**R0 Components**:
- `same_asset`: False
- `same_indication`: False
- `human_phase`: animal_only OR `evidence_strength`: weak

### R Component Scoring

#### Directness (40% weight)
```python
def score_directness(components):
    score = 0.0
    
    if components.get('same_asset'):
        score += 0.4
    elif components.get('same_moa_class'):
        score += 0.3
    elif components.get('related_moa'):
        score += 0.2
    
    if components.get('same_nct'):
        score += 0.2
    
    if components.get('same_indication'):
        score += 0.2
    elif components.get('related_indication'):
        score += 0.1
    
    return min(score, 1.0)
```

#### Phase Relevance (25% weight)
```python
def score_phase(components):
    phase = components.get('human_phase', 'unknown')
    
    if phase in ['P3', 'P2/3']:
        return 1.0
    elif phase in ['P2', 'P2B']:
        return 0.8
    elif phase == 'P1':
        return 0.6
    elif phase == 'preclinical':
        return 0.4
    elif phase == 'animal_only':
        return 0.1
    else:
        return 0.3
```

#### Recency (20% weight)
```python
def score_recency(pub_date, catalyst_date, window_months=18):
    if not pub_date or not catalyst_date:
        return 0.5
    
    months_diff = abs((pub_date - catalyst_date).days / 30)
    
    if months_diff <= 6:
        return 1.0
    elif months_diff <= 12:
        return 0.9
    elif months_diff <= 18:
        return 0.8
    elif months_diff <= 24:
        return 0.6
    else:
        return 0.4
```

#### Article Type (15% weight)
```python
def score_article_type(components):
    article_type = components.get('article_type', 'unknown')
    
    if article_type in ['RCT', 'Results']:
        return 1.0
    elif article_type in ['Review', 'Meta-analysis']:
        return 0.8
    elif article_type in ['Protocol', 'Case Report']:
        return 0.6
    elif article_type in ['Editorial', 'Commentary']:
        return 0.4
    else:
        return 0.5
```

## S (Shortability) Scoring

### S Tiers and Thresholds

#### S3: High Shortability (0.70+)
**Explicit failure/futility/non-inferiority miss; ITT non-sig with PP-only win; subgroup/post-hoc only; HR≥~1.15 with CI mostly unfavorable; discontinuations materially worse.**

**Examples**:
- Primary endpoint not met
- Trial stopped for futility
- Non-inferiority not demonstrated
- ITT analysis negative, only PP positive
- Post-hoc subgroup analysis only

**S3 Components**:
- `primary_failure`: True
- `futility`: True
- `non_inferiority_miss`: True
- `itt_negative_pp_positive`: True
- `post_hoc_only`: True
- `unfavorable_hr`: ≥1.15 with unfavorable CI

#### S2: Medium-High Shortability (0.45-0.69)
**Mixed picture; barely-met primary with key secondary failures; underpowered pivotal; open-label when blinding feasible; multiple interims with weak adjustment.**

**Examples**:
- Primary endpoint barely met
- Key secondary endpoints failed
- Underpowered study
- Open-label design when blinding possible
- Multiple interim analyses

**S2 Components**:
- `primary_barely_met`: True
- `secondary_failures`: True
- `underpowered`: True
- `design_weakness`: open_label, multiple_interims
- `mixed_results`: True

#### S1: Medium Shortability (0.20-0.44)
**Neutral/low concern; early positive with caveats; surrogate only.**

**Examples**:
- Early positive results with caveats
- Surrogate endpoint only
- Mixed safety signals
- Limited follow-up

**S1 Components**:
- `early_positive`: True
- `surrogate_only`: True
- `mixed_safety`: True
- `limited_followup`: True
- `caveats_present`: True

#### S0: Low Shortability (<0.20)
**Robust success: well-powered primary met + consistent secondaries; strong margins.**

**Examples**:
- Primary endpoint clearly met
- Consistent secondary endpoints
- Well-powered study
- Strong statistical margins

**S0 Components**:
- `primary_met`: True
- `consistent_secondaries`: True
- `well_powered`: True
- `strong_margins`: True
- `robust_results`: True

### S Component Scoring

#### Direction Text Hits (35% weight)
```python
def score_direction_text(components):
    score = 0.0
    
    # High-risk phrases
    if components.get('primary_failure'):
        score += 0.35
    elif components.get('futility'):
        score += 0.30
    elif components.get('non_inferiority_miss'):
        score += 0.25
    
    # Medium-risk phrases
    if components.get('itt_negative_pp_positive'):
        score += 0.20
    elif components.get('post_hoc_only'):
        score += 0.15
    elif components.get('subgroup_analysis'):
        score += 0.10
    
    # Low-risk phrases
    if components.get('interim_analysis'):
        score += 0.05
    elif components.get('open_label'):
        score += 0.05
    
    return min(score, 1.0)
```

#### Effect Magnitude (30% weight)
```python
def score_effect_magnitude(components):
    score = 0.0
    
    # Hazard ratios
    hr = components.get('hazard_ratio')
    if hr:
        if hr >= 1.50:
            score += 0.30
        elif hr >= 1.15:
            score += 0.20
        elif hr >= 1.05:
            score += 0.10
    
    # Response rate gaps
    orr_gap = components.get('orr_gap')
    if orr_gap:
        if orr_gap <= -0.20:
            score += 0.25
        elif orr_gap <= -0.10:
            score += 0.15
        elif orr_gap <= -0.05:
            score += 0.08
    
    # Confidence interval quality
    ci_crosses_null = components.get('ci_crosses_null')
    if ci_crosses_null:
        score *= 0.5  # Halve weight if CI crosses null
    
    return min(score, 1.0)
```

#### Design Fragility (20% weight)
```python
def score_design_fragility(components):
    score = 0.0
    
    if components.get('single_arm_pivotal'):
        score += 0.20
    elif components.get('open_label'):
        score += 0.15
    elif components.get('small_n'):
        score += 0.10
    
    if components.get('poor_control'):
        score += 0.10
    elif components.get('multiplicity_issues'):
        score += 0.10
    
    if components.get('underpowered'):
        score += 0.15
    
    return min(score, 1.0)
```

#### Safety Signals (15% weight)
```python
def score_safety(components):
    score = 0.0
    
    if components.get('discontinuations_worse'):
        score += 0.15
    elif components.get('sae_worse'):
        score += 0.10
    elif components.get('grade_3_4_ae'):
        score += 0.08
    
    if components.get('deaths_worse'):
        score += 0.10
    elif components.get('mortality_signal'):
        score += 0.08
    
    return min(score, 1.0)
```

## R/S Combination Rules

### Trial Actions by R×S Cell

#### R3 × S3: Immediate Promotion
- **Action**: Promote to review queue
- **Rationale**: High relevance + high shortability
- **Priority**: Highest

#### R3 × S2: Conditional Promotion
- **Action**: Fetch full text if ambiguous, then decide
- **Rationale**: High relevance + medium shortability
- **Priority**: High

#### R3 × S1: Keep for Context
- **Action**: Keep in analysis, monitor for changes
- **Rationale**: High relevance + low shortability
- **Priority**: Medium

#### R3 × S0: Low Priority
- **Action**: Keep citation, low processing priority
- **Rationale**: High relevance + no shortability
- **Priority**: Low

#### R2 × S3: High Priority
- **Action**: Process thoroughly, consider promotion
- **Rationale**: Medium relevance + high shortability
- **Priority**: High

#### R2 × S2: Standard Processing
- **Action**: Normal processing priority
- **Rationale**: Medium relevance + medium shortability
- **Priority**: Medium

#### R2 × S1: Low Priority
- **Action**: Process if resources available
- **Rationale**: Medium relevance + low shortability
- **Priority**: Low

#### R1 × S3: Investigate
- **Action**: Process to understand risk context
- **Rationale**: Low relevance + high shortability
- **Priority**: Medium

#### R1 × S2: Minimal Processing
- **Action**: Basic processing only
- **Rationale**: Low relevance + medium shortability
- **Priority**: Low

#### R1 × S1: Skip
- **Action**: Skip processing
- **Rationale**: Low relevance + low shortability
- **Priority**: None

#### R0 × Any: Skip
- **Action**: Skip processing
- **Rationale**: No relevance
- **Priority**: None

## Implementation Notes

### Scoring Consistency
- **Normalization**: All component scores normalized to 0-1 range
- **Weighting**: Component weights sum to 1.0
- **Thresholds**: Tier boundaries are configurable
- **Rounding**: Final scores rounded to 2 decimal places

### Performance Considerations
- **Caching**: R/S scores cached per (trial, doc) pair
- **Batch processing**: Score multiple documents together
- **Early termination**: Stop scoring if R0 or S0 determined early

### Quality Assurance
- **Inter-annotator agreement**: Target >80% for R/S tiers
- **Drift detection**: Monitor score distributions over time
- **Threshold calibration**: Adjust based on outcome data
