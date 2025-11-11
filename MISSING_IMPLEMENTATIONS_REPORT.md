# Missing Implementations Report - Dashboard & Real-World Data

## Critical Issues Found

### 1. ❌ Events NOT Created from Trial Status Changes
**Location**: `src/processing/pipeline.py:_handle_trial_status_update()`

**Problem**: 
- EventService is initialized but never used
- Trial status changes create `TrialStatusHistory` but NOT `Event` records
- Dashboard timeline will be empty because it queries Events table

**Impact**: **CRITICAL** - Dashboard cannot show company timelines

**Fix Required**: Add event creation when status changes

---

### 2. ❌ Regulatory Events NOT Converted to Events
**Location**: `src/processing/pipeline.py` (after RegulatoryEvent creation)

**Problem**:
- RegulatoryEvent entities are created but never converted to unified Events
- EventService has `convert_regulatory_event_to_event()` but it's never called

**Impact**: **CRITICAL** - Regulatory events don't appear in timelines

**Fix Required**: Convert RegulatoryEvents to Events after creation

---

### 3. ❌ No Backfill for Existing Data
**Problem**:
- Database has 76 companies, 205 trials, 305 sponsors
- But 0 events in Events table
- Existing TrialStatusHistory and RegulatoryEvents need to be converted

**Impact**: **HIGH** - Historical data not visible in dashboard

**Fix Required**: Create backfill script

---

### 4. ⚠️ Materialized View Not Refreshed
**Location**: `database/migrations/versions/f1a2b3c4d5e6_add_company_risk_metrics_view.py`

**Problem**:
- Materialized view created but never refreshed
- Risk metrics will be stale or empty

**Impact**: **MEDIUM** - Risk scores may be inaccurate

**Fix Required**: Refresh materialized view after data processing

---

### 5. ⚠️ Missing Event Creation for New Trials
**Location**: `src/processing/pipeline.py` (trial creation)

**Problem**:
- New trials are created but no "trial initiated" event is created

**Impact**: **MEDIUM** - Missing initial trial events

**Fix Required**: Create event when trial is first created

---

## Database Status

```
Companies: 76
Trials: 205
Trial Sponsors: 305
Events: 0  ← CRITICAL: No events!
Companies with trials: 44
```

## Test Results

✅ CompanyRiskService works with real data
✅ Metrics calculation works
✅ Risk score calculation works
❌ Timeline will be empty (no events)

---

## Priority Fixes

1. **IMMEDIATE**: Add event creation in pipeline
2. **IMMEDIATE**: Create backfill script for existing data
3. **HIGH**: Refresh materialized view
4. **MEDIUM**: Add event creation for new trials

