# Literature Queue Specification

## Overview
This document specifies the global trial queue management system for PubMed literature processing, including prioritization policies and periodic reprioritization.

## Queue Structure

### Trial States
- **active**: Currently being processed for literature
- **stopped**: Early stopping criteria met
- **parked**: Temporarily paused (low priority)
- **promoted**: High-risk signal confirmed, moved to review

### Queue Priority Calculation
```
priority = 0.55 * best_S_Rge2 + 0.25 * time_to_catalyst_weight + 0.15 * uncertainty + 0.05 * max_expected_utility_next_doc
```

### Priority Components

#### 1. Best S Score Among R≥2 (55% weight)
- **S3**: 0.70+ (high shortability)
- **S2**: 0.45+ (medium shortability)
- **S1**: 0.20+ (low shortability)
- **S0**: <0.20 (no shortability)

#### 2. Time to Catalyst Weight (25% weight)
- **<6 months**: 1.0 (urgent)
- **6-12 months**: 0.8 (high priority)
- **12-18 months**: 0.6 (medium priority)
- **>18 months**: 0.4 (low priority)

#### 3. Uncertainty (15% weight)
- **High uncertainty**: 1.0 (needs more data)
- **Medium uncertainty**: 0.6 (moderate information)
- **Low uncertainty**: 0.2 (well-characterized)

#### 4. Expected Utility (5% weight)
- **High utility**: 1.0 (likely to change decision)
- **Medium utility**: 0.5 (moderate impact)
- **Low utility**: 0.1 (minimal impact)

## Queue Management

### Daily Operations

#### 1. Queue Refresh (6:00 AM UTC)
- Recalculate priorities for all active trials
- Update trial_lit_state with latest metrics
- Reorder queue based on new priorities

#### 2. Batch Processing (8:00 AM - 6:00 PM UTC)
- Process top N trials from queue
- Respect daily quotas and rate limits
- Update trial states after processing

#### 3. Queue Maintenance (8:00 PM UTC)
- Clean up completed trials
- Archive parked trials older than 30 days
- Generate daily queue statistics

### Weekly Operations

#### 1. Drift Sampling (Monday 9:00 AM UTC)
- Randomly select 5-10% of parked trials
- Deep-dive analysis to estimate miss rate
- Recalibrate thresholds if needed

#### 2. Threshold Review (Wednesday 2:00 PM UTC)
- Analyze R/S scoring consistency
- Adjust thresholds in rs_config.yaml
- Update queue parameters

### Monthly Operations

#### 1. Performance Review (1st of month)
- Analyze queue throughput and efficiency
- Review early stopping rule effectiveness
- Optimize queue parameters

#### 2. Backfill Operations (15th of month)
- Update MeSH and substance dictionaries
- Expand asset alias lists
- Re-score borderline documents

## Queue Policies

### Trial Promotion Rules
```python
def should_promote_trial(trial):
    # Immediate promotion
    if has_R3S3(trial):
        return True
    
    # Two independent high-risk signals
    if count_R3S2_R2S3(trial) >= 2:
        return True
    
    return False
```

### Trial Parking Rules
```python
def should_park_trial(trial):
    # All R3 documents are low-risk
    if all_R3_are_S0_S1(trial) and best_risk_doc_is_R_le_1(trial):
        return True
    
    # Low shortability and no promising abstracts
    if best_S_Rge2(trial) <= S1 and no_promising_abstracts_remain(trial):
        return True
    
    return False
```

### Early Stopping Rules
```python
def should_stop_trial(trial):
    # Plateau detection
    if plateau_detected(trial):
        return True
    
    # High confidence decision
    if p_short(trial) >= theta_high:
        return True
    
    # Low probability of shortability
    if p_short(trial) <= theta_low:
        return True
    
    return False
```

## Queue Metrics

### Performance Metrics
- **Throughput**: trials processed per day
- **Efficiency**: documents per trial before decision
- **Accuracy**: % of promoted trials that are actually high-risk
- **Speed**: average time from discovery to decision

### Quality Metrics
- **Miss rate**: % of parked trials that should have been promoted
- **False positive rate**: % of promoted trials that are low-risk
- **R/S consistency**: inter-annotator agreement on R/S scores

### Cost Metrics
- **API calls per trial**: PubMed E-utilities usage
- **Storage per trial**: text content and metadata size
- **Processing time**: CPU and memory usage per trial

## Configuration

### Queue Settings
```yaml
queue:
  daily_quota: 50  # trials processed per day
  batch_size: 10   # trials processed per batch
  refresh_interval: 3600  # seconds between priority updates
  
  priorities:
    best_s_weight: 0.55
    catalyst_weight: 0.25
    uncertainty_weight: 0.15
    utility_weight: 0.05
  
  thresholds:
    theta_high: 0.80
    theta_low: 0.20
    plateau_epsilon: 0.03
    delta_min: 0.05
```

### Time Windows
```yaml
timing:
  catalyst_windows:
    urgent: 6      # months
    high: 12       # months
    medium: 18     # months
    low: 24        # months
  
  processing_hours:
    start: "08:00"  # UTC
    end: "18:00"    # UTC
    timezone: "UTC"
```

## Monitoring & Alerting

### Queue Health Checks
- **Queue depth**: Alert if >100 trials waiting
- **Processing rate**: Alert if <10 trials/day
- **Error rate**: Alert if >5% trials fail

### Performance Alerts
- **Priority drift**: Alert if priorities change dramatically
- **Threshold violations**: Alert if early stopping rules trigger unexpectedly
- **Resource exhaustion**: Alert if approaching daily quotas

### Quality Alerts
- **Miss rate spike**: Alert if >10% trials parked incorrectly
- **R/S inconsistency**: Alert if inter-annotator agreement <80%
- **Processing delays**: Alert if trials wait >7 days
