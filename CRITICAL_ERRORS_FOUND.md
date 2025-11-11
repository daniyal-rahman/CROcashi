# Critical Errors Found in Company Risk Implementation

## 🔴 CRITICAL ERRORS

### 1. Missing Docstring Opening Quote
**Location**: `src/api/routes/company_risk.py:140`

**Problem**: Missing opening triple quotes for docstring.

```python
@router.get("/companies/search", response_model=CompanySearchResponse)
async def search_companies(
    ...
):
    
    Search companies with filters.  # ❌ Missing opening """
```

**Impact**: Syntax error - will prevent module from loading.

---

### 2. Query Count After Modifications
**Location**: `src/api/routes/company_risk.py:211`

**Problem**: Calling `query.count()` after query has been modified with joins and filters. The query object may have been transformed and count() might fail or return incorrect results.

```python
# Query has been modified with joins
query = query.join(...).filter(...)

# Later...
total = query.count()  # ❌ May fail or be incorrect
```

**Impact**: Runtime error or incorrect pagination totals.

---

### 3. Session Access After Service Creation
**Location**: `src/api/routes/company_risk.py:151, 175`

**Problem**: Accessing `service.session` directly in route handler. The session is managed by FastAPI dependency injection and may be closed when accessed.

```python
service: CompanyRiskService = Depends(get_risk_service)
# ...
query = service.session.query(Company)  # ❌ Direct session access
```

**Impact**: Database session errors, connection issues.

---

### 4. Missing Error Handling for Risk Score Calculation
**Location**: `src/api/routes/company_risk.py:193-194`

**Problem**: No error handling when calculating risk scores in search endpoint. If calculation fails for one company, entire search fails.

```python
for company in companies:
    risk_result = service.calculate_company_risk_score(company.company_id)  # ❌ No try/except
    metrics = service.get_company_metrics(company.company_id)  # ❌ No try/except
```

**Impact**: One bad company breaks entire search results.

---

### 5. Inefficient Search Implementation
**Location**: `src/api/routes/company_risk.py:192-208`

**Problem**: Calculating risk scores for ALL companies before filtering by risk_category. Should filter first, then calculate.

```python
for company in companies:
    risk_result = service.calculate_company_risk_score(...)  # ❌ Calculates for all
    if risk_category and risk_result.get('risk_category') != risk_category:
        continue  # ❌ Already calculated, wasted computation
```

**Impact**: Performance degradation, unnecessary database queries.

---

### 6. Missing Distinct After Joins
**Location**: `src/api/routes/company_risk.py:170`

**Problem**: After multiple joins, may get duplicate companies. Missing `.distinct()` call.

```python
query = query.join(...).join(...).filter(...)
# Missing: query = query.distinct()
companies = query.distinct().limit(limit).offset(offset).all()  # ✅ Has distinct here
```

**Impact**: Duplicate companies in results (though distinct is called later, should be earlier).

---

### 7. Potential Type Error in Frontend
**Location**: `frontend/src/components/RiskScoreCard.tsx:54`

**Problem**: Complex calculation in JSX template string may fail if risk_score is undefined.

```typescript
strokeDasharray={`${angle * Math.PI * 80 / 180} 251.2`}
// If riskProfile.risk_score is undefined, angle is NaN
```

**Impact**: Visual rendering errors.

---

### 8. Missing Null Check in PDF Export
**Location**: `frontend/src/utils/pdfExport.ts:19`

**Problem**: Accessing properties that might be undefined without checks.

```typescript
doc.text(`Risk Score: ${riskProfile.risk_score.toFixed(1)} / 100`, 14, 37)
// If risk_score is undefined, toFixed() fails
```

**Impact**: PDF export crashes.

---

## 🟡 MEDIUM PRIORITY ISSUES

### 9. Cache Key Collision Risk
**Location**: `src/services/company_risk_service.py:cache keys`

**Problem**: Cache keys don't include filters, so filtered queries may return cached unfiltered results.

**Impact**: Incorrect cached data returned.

### 10. Missing Validation for UUID Format
**Location**: `src/api/routes/company_risk.py:company_id parameter`

**Problem**: FastAPI validates UUID format, but no custom error message for invalid UUIDs.

**Impact**: Generic 422 error instead of helpful message.

---

## SUMMARY

**Critical Errors Found**: 8
**Medium Issues**: 2

**Total Issues**: 10

