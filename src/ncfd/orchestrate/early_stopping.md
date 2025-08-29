# Early Stopping Rules Specification

## Overview
This document specifies the early stopping rules for PubMed literature processing, including threshold-based stopping, plateau detection, and sample rate management.

## Stop Rule Categories

### 1. Threshold-Based Stopping

#### High Confidence Stop (θ_high)
- **Purpose**: Stop when high confidence of shortability
- **Threshold**: p_short ≥ 0.80
- **Rationale**: Sufficient evidence to make decision
- **Action**: Promote trial to review queue

#### Low Confidence Stop (θ_low)
- **Purpose**: Stop when low probability of shortability
- **Threshold**: p_short ≤ 0.20
- **Rationale**: Unlikely to find high-risk signals
- **Action**: Park trial for later review

### 2. Plateau Detection

#### Plateau Stop (ε_plateau)
- **Purpose**: Stop when no meaningful progress
- **Threshold**: |Δp_short| < 0.03 over 2 consecutive evaluations
- **Rationale**: Diminishing returns from additional documents
- **Action**: Stop processing, maintain current decision

#### Utility Plateau (δ_min)
- **Purpose**: Stop when expected utility is low
- **Threshold**: max_expected_utility_next_doc < 0.05
- **Rationale**: Additional documents unlikely to change decision
- **Action**: Stop processing, maintain current decision

### 3. Resource-Based Stopping

#### Document Quota Stop
- **Purpose**: Stop when document limits reached
- **Threshold**: n_docs_seen ≥ max_abstracts_total_per_trial
- **Rationale**: Respect resource constraints
- **Action**: Stop processing, use current evidence

#### Time-Based Stop
- **Purpose**: Stop when processing time exceeds limits
- **Threshold**: processing_time > max_processing_time_hours
- **Rationale**: Prevent pipeline bottlenecks
- **Action**: Stop processing, flag for manual review

## Early Stopping Implementation

### Decision Function
```python
def should_stop_early(trial, config):
    # High confidence stops
    if trial.p_short >= config.theta_high:
        return "promote", "high_confidence"
    
    if trial.p_short <= config.theta_low:
        return "park", "low_confidence"
    
    # Plateau detection
    if plateau_detected(trial, config.plateau_eps):
        if trial.max_expected_utility < config.delta_min:
            return "stop", "utility_plateau"
        else:
            return "stop", "probability_plateau"
    
    # Resource limits
    if trial.n_docs_seen >= config.max_abstracts_total:
        return "stop", "document_quota"
    
    if trial.processing_time > config.max_processing_time:
        return "stop", "time_limit"
    
    return "continue", None
```

### Plateau Detection
```python
def plateau_detected(trial, epsilon):
    if len(trial.p_short_history) < 2:
        return False
    
    recent_changes = [
        abs(trial.p_short_history[i] - trial.p_short_history[i-1])
        for i in range(1, len(trial.p_short_history))
    ]
    
    # Check last 2 consecutive evaluations
    if len(recent_changes) >= 2:
        last_two_changes = recent_changes[-2:]
        return all(change < epsilon for change in last_two_changes)
    
    return False
```

### Expected Utility Calculation
```python
def calculate_expected_utility(trial):
    # Based on current uncertainty and document quality distribution
    if trial.uncertainty < 0.1:
        return 0.01  # Very low uncertainty
    
    if trial.uncertainty < 0.3:
        return 0.05  # Low uncertainty
    
    if trial.uncertainty < 0.6:
        return 0.15  # Medium uncertainty
    
    return 0.25  # High uncertainty
```

## Sample Rate Management

### Adaptive Sampling

#### High Uncertainty Trials
- **Sample rate**: 100% of discovered documents
- **Rationale**: Need comprehensive coverage
- **Threshold**: uncertainty > 0.6

#### Medium Uncertainty Trials
- **Sample rate**: 75% of discovered documents
- **Rationale**: Balance coverage and efficiency
- **Threshold**: 0.3 ≤ uncertainty ≤ 0.6

#### Low Uncertainty Trials
- **Sample rate**: 50% of discovered documents
- **Rationale**: High confidence, selective sampling
- **Threshold**: uncertainty < 0.3

### Quality-Based Sampling

#### High-Risk Documents
- **Sample rate**: 100% (always process)
- **Criteria**: R≥2 and S≥S2
- **Rationale**: Critical for decision making

#### Medium-Risk Documents
- **Sample rate**: 80%
- **Criteria**: R≥1 and S≥S1
- **Rationale**: Important for context

#### Low-Risk Documents
- **Sample rate**: 40%
- **Criteria**: R≤1 or S≤S1
- **Rationale**: Minimal impact on decision

## TTL (Time-to-Live) Management

### Document TTLs

#### Abstract Text
- **TTL**: No expiration (permanent storage)
- **Rationale**: Core content, small storage footprint
- **Action**: Keep indefinitely

#### Full Text (OA)
- **TTL**: 90 days for non-candidates
- **Rationale**: Large storage, limited utility
- **Action**: Auto-delete after TTL

#### Full Text (Candidates)
- **TTL**: No expiration
- **Rationale**: High-value content for promoted trials
- **Action**: Keep indefinitely

### Trial State TTLs

#### Active Trials
- **TTL**: No expiration
- **Rationale**: Currently being processed
- **Action**: Keep until decision made

#### Parked Trials
- **TTL**: 30 days
- **Rationale**: Temporary pause, not permanent
- **Action**: Archive after TTL, flag for review

#### Stopped Trials
- **TTL**: 90 days
- **Rationale**: Decision made, limited utility
- **Action**: Archive after TTL

## Configuration

### Early Stopping Parameters
```yaml
early_stopping:
  thresholds:
    theta_high: 0.80      # High confidence threshold
    theta_low: 0.20       # Low confidence threshold
    plateau_eps: 0.03     # Plateau detection epsilon
    delta_min: 0.05       # Minimum utility threshold
  
  sampling:
    adaptive: true         # Enable adaptive sampling
    base_rate: 0.75       # Base sampling rate
    uncertainty_weights:   # Sampling rate by uncertainty
      high: 1.0           # >0.6: 100%
      medium: 0.75        # 0.3-0.6: 75%
      low: 0.5            # <0.3: 50%
  
  ttl:
    fulltext_non_candidate: 90    # days
    parked_trials: 30             # days
    stopped_trials: 90            # days
    max_processing_time: 24       # hours
```

### Quality Thresholds
```yaml
quality:
  min_abstract_length: 50         # characters
  min_confidence: 0.7            # entity extraction confidence
  required_fields:                # fields required for processing
    - title
    - abstract
    - pmid
    - published_at
```

## Monitoring & Metrics

### Early Stopping Metrics
- **Stop rate**: % of trials stopped early
- **Stop reasons**: distribution of stop reasons
- **False stops**: % of stopped trials that should have continued
- **Processing efficiency**: documents per trial before stop

### Sampling Metrics
- **Sample rate**: actual vs. target sampling rates
- **Coverage quality**: impact of sampling on decision accuracy
- **Resource usage**: storage and processing costs

### TTL Metrics
- **Storage savings**: space freed by TTL expiration
- **Access patterns**: frequency of access to expired content
- **Archive efficiency**: time to archive expired content
