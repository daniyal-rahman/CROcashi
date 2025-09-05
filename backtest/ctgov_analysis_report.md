# CTGov Discovery & Public Company Wiring Backtest Analysis

## 📊 **Executive Summary**

**Date**: September 3, 2025  
**Trials Analyzed**: 4  
**Stage**: CTGov Discovery + Public US Filter  

### Key Findings
- **NCT ID Coverage**: 50% (2/4 trials have NCT IDs)
- **Sponsor Information**: 0% (no sponsor data found)
- **Phase Information**: 25% (1/4 trials have phase data)
- **Indication Coverage**: 50% (2/4 trials have indication data)
- **Public US Sponsor Rate**: 0% (no public US sponsors identified)

## 🔍 **Detailed Analysis**

### 1. Trial Discovery Metrics

| Metric | Count | Coverage |
|--------|-------|----------|
| Total Trials Discovered | 4 | 100% |
| Trials with NCT ID | 2 | 50% |
| Trials with Phase Info | 1 | 25% |
| Trials with Indication | 2 | 50% |
| Trials with Completion Date | 2 | 50% |

### 2. Public Company Wiring Analysis

**Critical Issue**: **0% sponsor information coverage**

This indicates a major gap in the CTGov discovery pipeline:
- No sponsor information is being extracted from trial data
- Cannot perform public US company filtering
- Cannot wire trials to public companies for analysis

### 3. Data Quality Issues

#### Missing NCT IDs (2 trials)
- **File Index 2**: Trial version v1_2020 (captured 2020-05-15)
- **File Index 3**: Trial version v2_2023 (captured 2023-06-01)

These appear to be trial version snapshots rather than complete trial records.

#### Missing Sponsor Information (4 trials)
- **NCT04388254**: Cassava trial - no sponsor data
- **MOCK_HIGH_RISK_001**: Mock trial - no sponsor data
- **File Index 2**: Trial version - no sponsor data
- **File Index 3**: Trial version - no sponsor data

#### Missing Phase Information (3 trials)
- Only 1 trial has phase information
- Critical for filtering Phase 2b/3 trials

## 🚨 **Critical Issues Identified**

### 1. **Sponsor Information Gap**
- **Impact**: Cannot identify public US companies
- **Root Cause**: Sponsor field not being extracted from CTGov data
- **Action Required**: Fix sponsor extraction in CTGov ingestion pipeline

### 2. **Trial Version Handling**
- **Impact**: Duplicate trials and incomplete data
- **Root Cause**: Trial versions not properly consolidated
- **Action Required**: Implement trial version deduplication logic

### 3. **Data Completeness**
- **Impact**: Low coverage across all fields
- **Root Cause**: Incomplete CTGov data extraction
- **Action Required**: Enhance CTGov data extraction pipeline

## 📈 **Trial Version Analysis**

### Detected Trial Versions
1. **v1_2020** (captured 2020-05-15)
   - Primary endpoint: ADAS-Cog11 mean change over 6 months
   - Estimated completion: 2021-05-15

2. **v2_2023** (captured 2023-06-01)
   - Primary endpoint: ADAS-Cog11 mean change over 6 months
   - Estimated completion: 2023-12-01
   - No late changes detected

### Endpoint Changes Detected
- **NCT04388254**: Endpoint change claim detected
  - Claim: "endpoint: ADAS-Cog11 mean change over 6 months"
  - Type: design_fact
  - Evidence: No evidence spans provided

## 🎯 **Recommendations**

### Immediate Actions (Priority 1)
1. **Fix Sponsor Extraction**
   - Add sponsor field extraction to CTGov ingestion
   - Implement company database lookup
   - Add public US company identification logic

2. **Implement Trial Deduplication**
   - Consolidate trial versions into single records
   - Track version history properly
   - Maintain data lineage

3. **Enhance Data Extraction**
   - Improve phase information extraction
   - Add completion date extraction
   - Ensure NCT ID coverage

### Short-term Actions (Priority 2)
1. **Add Company Database Integration**
   - Connect to SEC company database
   - Implement CIK lookup
   - Add exchange information

2. **Implement Public US Filter**
   - Add filter logic for public US companies
   - Track filter pass/fail rates
   - Monitor filter effectiveness

3. **Add Data Quality Monitoring**
   - Track field coverage over time
   - Alert on data quality issues
   - Monitor extraction pipeline health

### Long-term Actions (Priority 3)
1. **Real-time CTGov Monitoring**
   - Monitor for new trial registrations
   - Track trial updates and changes
   - Implement automated ingestion

2. **Advanced Company Matching**
   - Fuzzy matching for company names
   - Handle company name variations
   - Track company ownership changes

## 🔧 **Technical Implementation**

### Required Database Schema Updates
```sql
-- Add sponsor information to trials table
ALTER TABLE trials ADD COLUMN sponsor_name TEXT;
ALTER TABLE trials ADD COLUMN sponsor_cik CHAR(10);
ALTER TABLE trials ADD COLUMN is_public_us BOOLEAN;
ALTER TABLE trials ADD COLUMN exchange VARCHAR(10);

-- Add trial version tracking
CREATE TABLE trial_versions (
    version_id SERIAL PRIMARY KEY,
    trial_id INTEGER REFERENCES trials(trial_id),
    version_timestamp TIMESTAMP,
    changes_jsonb JSONB
);
```

### Required Code Changes
1. **CTGov Ingestion Pipeline**
   - Add sponsor field extraction
   - Implement company lookup
   - Add version tracking

2. **Company Database Integration**
   - Add SEC company API integration
   - Implement CIK lookup
   - Add exchange information

3. **Public US Filter**
   - Add filter logic
   - Track filter metrics
   - Monitor filter performance

## 📊 **Success Metrics**

### Target Coverage Rates
- **NCT ID Coverage**: >95%
- **Sponsor Information**: >90%
- **Phase Information**: >95%
- **Indication Coverage**: >95%
- **Public US Sponsor Rate**: >80%

### Monitoring KPIs
- **Discovery Rate**: New trials discovered per day
- **Data Quality Score**: Average field coverage
- **Filter Pass Rate**: Percentage passing public US filter
- **Processing Time**: Time from discovery to analysis

## 🎯 **Next Steps**

1. **Immediate**: Fix sponsor extraction in CTGov pipeline
2. **This Week**: Implement trial version deduplication
3. **Next Week**: Add company database integration
4. **Next Month**: Deploy enhanced CTGov monitoring

---

**Status**: 🔴 **Critical Issues Found** - Immediate action required for sponsor extraction and data quality improvements.
