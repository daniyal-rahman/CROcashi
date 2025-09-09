# PubMed Literature Processing Runbook

## Overview
This runbook provides operational procedures for the PubMed literature processing pipeline, including daily cadence, quotas, QA checks, and troubleshooting.

## Daily Operations Schedule

### 6:00 AM UTC - Queue Refresh
**Purpose**: Recalculate priorities and reorder trial queue

**Tasks**:
1. **Priority Recalculation**
   - Update `trial_lit_state` with latest metrics
   - Recalculate queue priorities using R/S scores
   - Reorder queue based on new priorities

2. **Queue Health Check**
   - Verify queue depth (<100 trials)
   - Check for stuck trials (>7 days)
   - Validate priority calculations

**Commands**:
```bash
# Refresh trial priorities
python -m ncfd.pipeline.lit_queue --refresh

# Check queue health
python -m ncfd.monitoring.pipeline_monitor --queue-health
```

**Success Criteria**:
- Queue priorities updated successfully
- No trials stuck >7 days
- Priority calculations within expected ranges

### 8:00 AM - 6:00 PM UTC - Batch Processing
**Purpose**: Process trials from queue according to quotas

**Tasks**:
1. **Batch Selection**
   - Select top N trials from queue (respect daily quota)
   - Verify trial eligibility and resource availability
   - Assign processing resources

2. **Pipeline Execution**
   - Stage U0: Metadata discovery via ESearch/ESummary
   - Stage U1: Abstract processing and R/S scoring
   - Stage OA: Full text fetch for high-priority documents

3. **State Updates**
   - Update trial processing status
   - Record R/S scores and decisions
   - Update queue priorities

**Commands**:
```bash
# Process trial batch
python -m ncfd.pipeline.orchestrator --batch-size 10 --max-trials 50

# Monitor pipeline progress
python -m ncfd.monitoring.pipeline_monitor --live
```

**Success Criteria**:
- Daily quota met (target: 50 trials)
- Pipeline completion rate >95%
- R/S scoring consistency maintained

### 8:00 PM UTC - Queue Maintenance
**Purpose**: Clean up completed trials and generate statistics

**Tasks**:
1. **Trial Cleanup**
   - Archive completed trials (promoted/stopped/parked)
   - Update trial status and metadata
   - Clean up temporary processing files

2. **Statistics Generation**
   - Daily processing summary
   - Queue performance metrics
   - R/S scoring distribution

3. **Resource Cleanup**
   - Release processing resources
   - Archive old documents per TTL
   - Update storage usage metrics

**Commands**:
```bash
# Generate daily report
python -m ncfd.monitoring.pipeline_monitor --daily-report

# Clean up resources
python -m ncfd.pipeline.orchestrator --cleanup
```

**Success Criteria**:
- All completed trials archived
- Daily statistics generated
- Resources cleaned up successfully

## Weekly Operations

### Monday 9:00 AM UTC - Drift Sampling
**Purpose**: Sample parked trials to estimate miss rate

**Tasks**:
1. **Random Selection**
   - Select 5-10% of parked trials randomly
   - Prioritize trials parked >14 days
   - Ensure diverse representation across R/S tiers

2. **Deep-Dive Analysis**
   - Manual review of sampled trials
   - Re-score R/S components if needed
   - Identify potential false negatives

3. **Threshold Calibration**
   - Analyze drift patterns
   - Adjust thresholds in `rs_config.yaml` if needed
   - Update scoring parameters

**Commands**:
```bash
# Select drift sample
python -m ncfd.pipeline.lit_queue --drift-sample --sample-rate 0.08

# Generate drift report
python -m ncfd.monitoring.pipeline_monitor --drift-report
```

**Success Criteria**:
- 5-10% of parked trials sampled
- Drift analysis completed
- Thresholds calibrated if needed

### Wednesday 2:00 PM UTC - Threshold Review
**Purpose**: Analyze R/S scoring consistency and adjust thresholds

**Tasks**:
1. **Scoring Consistency Check**
   - Inter-annotator agreement analysis
   - R/S tier distribution review
   - Component score correlation analysis

2. **Threshold Optimization**
   - Identify optimal tier boundaries
   - Adjust component weights if needed
   - Validate against known outcomes

3. **Configuration Update**
   - Update `rs_config.yaml` with new thresholds
   - Deploy configuration changes
   - Monitor impact on scoring

**Commands**:
```bash
# Analyze scoring consistency
python -m ncfd.scoring.calibrate --consistency-check

# Optimize thresholds
python -m ncfd.scoring.calibrate --optimize-thresholds

# Deploy new config
python -m ncfd.config --update rs_config.yaml
```

**Success Criteria**:
- R/S consistency >80%
- Thresholds optimized
- Configuration deployed successfully

## Monthly Operations

### 1st of Month - Performance Review
**Purpose**: Analyze pipeline performance and optimize parameters

**Tasks**:
1. **Performance Metrics Analysis**
   - Throughput analysis (trials/day)
   - Efficiency metrics (docs/trial)
   - Cost analysis (API calls, storage)

2. **Parameter Optimization**
   - Queue priority weights
   - Early stopping thresholds
   - Sampling rates

3. **Resource Planning**
   - Capacity planning for next month
   - Budget allocation
   - Infrastructure scaling

**Commands**:
```bash
# Generate monthly report
python -m ncfd.monitoring.pipeline_monitor --monthly-report

# Analyze performance trends
python -m ncfd.monitoring.pipeline_monitor --trend-analysis
```

**Success Criteria**:
- Monthly performance report generated
- Parameters optimized
- Resource plan updated

### 15th of Month - Backfill Operations
**Purpose**: Update dictionaries and re-score borderline documents

**Tasks**:
1. **Dictionary Updates**
   - Update MeSH terms database
   - Expand asset alias lists
   - Update substance dictionaries

2. **Document Re-scoring**
   - Identify borderline R/S scores
   - Re-score with updated dictionaries
   - Update trial decisions if needed

3. **Quality Improvement**
   - Analyze scoring improvements
   - Update extraction patterns
   - Optimize entity recognition

**Commands**:
```bash
# Update dictionaries
python -m ncfd.extract.abstract_features --update-dictionaries

# Re-score borderline documents
python -m ncfd.scoring.score --re-score-borderline

# Quality analysis
python -m ncfd.quality.data_quality --analyze-improvements
```

**Success Criteria**:
- Dictionaries updated
- Borderline documents re-scored
- Quality metrics improved

## Quotas and Rate Limits

### Daily Quotas
- **Trials processed**: 50 (configurable)
- **Abstracts fetched**: 1,000 (20 per trial × 50 trials)
- **Full texts fetched**: 100 (2 per trial × 50 trials)
- **API calls**: 5,000 (100 per trial × 50 trials)

### Rate Limits
- **PubMed API**: 8 requests/second (with API key)
- **Processing rate**: 10 trials/hour (during 10-hour window)
- **Storage growth**: 100 MB/day (estimated)

### Resource Constraints
- **Database connections**: Max 20 concurrent
- **Storage capacity**: 10 GB available
- **Processing memory**: 4 GB per trial batch

## QA Checks

### Ingest QA (Daily)
**Metrics to monitor**:
- % of ESummary rows missing abstracts
- Abstract character count distribution
- MeSH/Substances coverage vs asset dictionary hit-rate

**Thresholds**:
- Missing abstracts: <5%
- Empty abstracts: <1%
- MeSH coverage: >80%

**Commands**:
```bash
# Run ingest QA
python -m ncfd.quality.data_quality --ingest-qa

# Check abstract quality
python -m ncfd.quality.data_quality --abstract-quality
```

### Linking QA (Weekly)
**Metrics to monitor**:
- `nct_in_text` precision
- Asset alias collision rate
- Link confidence distribution

**Thresholds**:
- NCT precision: >95%
- Asset collision rate: <2%
- High confidence links: >70%

**Commands**:
```bash
# Run linking QA
python -m ncfd.quality.data_quality --linking-qa

# Check link precision
python -m ncfd.quality.data_quality --link-precision
```

### R/S QA (Weekly)
**Metrics to monitor**:
- Inter-annotator agreement
- R/S tier distribution
- Component score correlation

**Thresholds**:
- R/S agreement: >80%
- Tier distribution: balanced
- Component correlation: >0.7

**Commands**:
```bash
# Run R/S QA
python -m ncfd.quality.data_quality --rs-qa

# Check scoring consistency
python -m ncfd.scoring.calibrate --consistency-check
```

### Cost QA (Daily)
**Metrics to monitor**:
- Abstracts pulled per trial
- OA texts pulled per trial
- API call efficiency

**Thresholds**:
- Abstracts per trial: <20
- OA texts per trial: <2
- API calls per trial: <100

**Commands**:
```bash
# Run cost QA
python -m ncfd.quality.data_quality --cost-qa

# Check API efficiency
python -m ncfd.monitoring.pipeline_monitor --api-efficiency
```

## Troubleshooting

### Common Issues

#### High Queue Depth
**Symptoms**: Queue depth >100 trials
**Causes**: Processing bottleneck, resource exhaustion
**Solutions**:
1. Check processing pipeline status
2. Verify resource availability
3. Increase processing capacity
4. Optimize pipeline efficiency

#### Low Processing Rate
**Symptoms**: <10 trials processed per day
**Causes**: Pipeline failures, API rate limiting
**Solutions**:
1. Check pipeline error logs
2. Verify PubMed API status
3. Review rate limiting configuration
4. Check database connectivity

#### High Error Rate
**Symptoms**: >5% trials fail
**Causes**: API failures, parsing errors, database issues
**Solutions**:
1. Review error logs
2. Check API endpoint health
3. Verify parsing logic
4. Test database connectivity

#### R/S Inconsistency
**Symptoms**: R/S agreement <80%
**Causes**: Threshold drift, component weight issues
**Solutions**:
1. Run drift analysis
2. Recalibrate thresholds
3. Adjust component weights
4. Review scoring logic

### Emergency Procedures

#### Pipeline Failure
1. **Immediate**: Stop pipeline, preserve state
2. **Investigation**: Review logs, identify root cause
3. **Recovery**: Restart pipeline, resume processing
4. **Prevention**: Implement safeguards, update procedures

#### Data Loss
1. **Assessment**: Determine scope of data loss
2. **Recovery**: Restore from backups if available
3. **Reprocessing**: Re-run affected trials
4. **Prevention**: Improve backup procedures

#### API Outage
1. **Detection**: Monitor API health checks
2. **Response**: Pause processing, queue trials
3. **Recovery**: Resume when API available
4. **Prevention**: Implement circuit breakers

## Monitoring and Alerting

### Health Checks
- **Pipeline status**: Every 5 minutes
- **Queue depth**: Every 15 minutes
- **API health**: Every minute
- **Database connectivity**: Every 5 minutes

### Alerts
- **Critical**: Pipeline failure, data loss
- **Warning**: High queue depth, low processing rate
- **Info**: Daily completion, weekly drift

### Escalation
1. **Level 1**: Automated retry (immediate)
2. **Level 2**: On-call engineer (within 30 minutes)
3. **Level 3**: Team lead (within 2 hours)
4. **Level 4**: Management (within 4 hours)

## Documentation and Reporting

### Daily Reports
- Processing summary
- Queue metrics
- Error rates
- Resource usage

### Weekly Reports
- Performance trends
- Quality metrics
- Drift analysis
- Threshold review

### Monthly Reports
- Comprehensive analysis
- Cost analysis
- Capacity planning
- Improvement recommendations

### Runbook Updates
- Update procedures monthly
- Incorporate lessons learned
- Add new troubleshooting steps
- Validate with team
