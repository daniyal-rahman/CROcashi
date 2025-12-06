-- ============================================================================
-- FAILURE CONTAGION ANALYSIS
-- Analyzing whether one company's trial termination predicts others in the
-- same indication within 12 months
-- ============================================================================

-- Step 1: Create a base table of all terminations with their key attributes
-- ============================================================================

DROP TABLE IF EXISTS termination_events CASCADE;

CREATE TEMP TABLE termination_events AS
SELECT
    ct.trial_id,
    ct.nct_id,
    ct.trial_title,
    ct.phase,
    ct.status,
    ct.start_date,
    ct.primary_completion_date,
    ct.completion_date,
    ct.why_stopped,
    -- Use the earliest available date that represents when the termination occurred
    COALESCE(ct.primary_completion_date, ct.completion_date, ct.status_verified_date) as termination_date,
    ts.entity_id as company_id,
    c.name as company_name,
    td.disease_id,
    d.disease_name
FROM clinical_trials ct
INNER JOIN trial_sponsors ts ON ct.trial_id = ts.trial_id
INNER JOIN companies c ON ts.entity_id = c.company_id
INNER JOIN trial_diseases td ON ct.trial_id = td.trial_id
INNER JOIN diseases d ON td.disease_id = d.disease_id
WHERE
    ct.status IN ('terminated', 'withdrawn')
    AND ct.deleted_at IS NULL
    AND ts.entity_type = 'company'
    AND ts.sponsor_role = 'lead_sponsor'
    AND ts.deleted_at IS NULL
    AND td.deleted_at IS NULL
    AND c.deleted_at IS NULL
    AND d.deleted_at IS NULL
    AND COALESCE(ct.primary_completion_date, ct.completion_date, ct.status_verified_date) IS NOT NULL;

CREATE INDEX idx_term_disease ON termination_events(disease_id, termination_date);
CREATE INDEX idx_term_company ON termination_events(company_id);

-- Check what we have
SELECT
    'Total Termination Events' as metric,
    COUNT(*) as count
FROM termination_events
UNION ALL
SELECT
    'Unique Companies',
    COUNT(DISTINCT company_id)
FROM termination_events
UNION ALL
SELECT
    'Unique Indications',
    COUNT(DISTINCT disease_id)
FROM termination_events
UNION ALL
SELECT
    'Date Range',
    COUNT(*)
FROM termination_events
WHERE termination_date >= '2010-01-01';

-- ============================================================================
-- Step 2: Find Contagion Events
-- For each termination, find other terminations in the same indication by
-- different companies within 12 months
-- ============================================================================

DROP TABLE IF EXISTS contagion_pairs CASCADE;

CREATE TEMP TABLE contagion_pairs AS
SELECT
    te1.trial_id as index_trial_id,
    te1.nct_id as index_nct_id,
    te1.company_id as index_company_id,
    te1.company_name as index_company_name,
    te1.disease_id,
    te1.disease_name,
    te1.termination_date as index_termination_date,
    te1.phase as index_phase,
    te1.why_stopped as index_why_stopped,
    te2.trial_id as follower_trial_id,
    te2.nct_id as follower_nct_id,
    te2.company_id as follower_company_id,
    te2.company_name as follower_company_name,
    te2.termination_date as follower_termination_date,
    te2.phase as follower_phase,
    te2.why_stopped as follower_why_stopped,
    (te2.termination_date - te1.termination_date) as days_between
FROM termination_events te1
INNER JOIN termination_events te2 ON
    te1.disease_id = te2.disease_id
    AND te1.company_id != te2.company_id  -- Different companies
    AND te2.termination_date > te1.termination_date  -- Follower came after
    AND te2.termination_date <= te1.termination_date + INTERVAL '12 months'  -- Within 12 months
WHERE te1.termination_date >= '2010-01-01';  -- Focus on recent data

CREATE INDEX idx_contagion_disease ON contagion_pairs(disease_id);
CREATE INDEX idx_contagion_index_company ON contagion_pairs(index_company_id);

-- Summary statistics
SELECT
    'Total Contagion Pairs Identified' as metric,
    COUNT(*) as count
FROM contagion_pairs
UNION ALL
SELECT
    'Unique Index Trials (First Movers)',
    COUNT(DISTINCT index_trial_id)
FROM contagion_pairs
UNION ALL
SELECT
    'Unique Follower Trials',
    COUNT(DISTINCT follower_trial_id)
FROM contagion_pairs
UNION ALL
SELECT
    'Indications with Contagion',
    COUNT(DISTINCT disease_id)
FROM contagion_pairs;

-- ============================================================================
-- Step 3: Calculate Contagion Rate by Indication
-- What % of terminations lead to follow-on terminations?
-- ============================================================================

DROP TABLE IF EXISTS indication_contagion_rates CASCADE;

CREATE TEMP TABLE indication_contagion_rates AS
WITH indication_stats AS (
    SELECT
        disease_id,
        disease_name,
        COUNT(DISTINCT trial_id) as total_terminations,
        COUNT(DISTINCT company_id) as companies_with_terminations
    FROM termination_events
    WHERE termination_date >= '2010-01-01'
    GROUP BY disease_id, disease_name
    HAVING COUNT(DISTINCT company_id) >= 2  -- Need at least 2 companies to have contagion
),
index_events AS (
    SELECT
        disease_id,
        COUNT(DISTINCT index_trial_id) as index_terminations,
        COUNT(*) as total_follower_events
    FROM contagion_pairs
    GROUP BY disease_id
)
SELECT
    i.disease_id,
    i.disease_name,
    i.total_terminations,
    i.companies_with_terminations,
    COALESCE(idx.index_terminations, 0) as index_terminations,
    COALESCE(idx.total_follower_events, 0) as total_follower_events,
    ROUND(100.0 * COALESCE(idx.index_terminations, 0) / NULLIF(i.total_terminations, 0), 2) as contagion_rate_pct,
    ROUND(COALESCE(idx.total_follower_events, 0)::numeric / NULLIF(idx.index_terminations, 0), 2) as avg_followers_per_index
FROM indication_stats i
LEFT JOIN index_events idx ON i.disease_id = idx.disease_id
ORDER BY idx.index_terminations DESC NULLS LAST, i.total_terminations DESC;

-- Top 20 indications by contagion rate
\echo ''
\echo '============================================================================'
\echo 'TOP 20 INDICATIONS BY CONTAGION RATE'
\echo '(% of terminations that led to follow-on terminations within 12 months)'
\echo '============================================================================'
\echo ''

SELECT
    disease_name,
    total_terminations,
    companies_with_terminations as companies,
    index_terminations as index_events,
    total_follower_events as followers,
    contagion_rate_pct as contagion_pct,
    avg_followers_per_index as avg_followers
FROM indication_contagion_rates
WHERE index_terminations > 0
ORDER BY contagion_rate_pct DESC, total_follower_events DESC
LIMIT 20;

-- ============================================================================
-- Step 4: High-Profile Case Studies
-- ============================================================================

\echo ''
\echo '============================================================================'
\echo 'GLIOBLASTOMA TERMINATION TIMELINE'
\echo '============================================================================'
\echo ''

SELECT
    termination_date,
    company_name,
    nct_id,
    phase,
    trial_title,
    why_stopped
FROM termination_events
WHERE disease_name ILIKE '%glioblastoma%'
ORDER BY termination_date, company_name;

\echo ''
\echo '============================================================================'
\echo 'GLIOBLASTOMA CONTAGION PAIRS'
\echo '============================================================================'
\echo ''

SELECT
    index_termination_date,
    index_company_name,
    index_nct_id,
    days_between as days_later,
    follower_company_name,
    follower_nct_id,
    follower_phase
FROM contagion_pairs
WHERE disease_name ILIKE '%glioblastoma%'
ORDER BY index_termination_date, days_between;

\echo ''
\echo '============================================================================'
\echo 'COVID-19 TERMINATION TIMELINE'
\echo '============================================================================'
\echo ''

SELECT
    termination_date,
    company_name,
    nct_id,
    phase,
    trial_title,
    why_stopped
FROM termination_events
WHERE disease_name ILIKE '%covid%' OR disease_name ILIKE '%coronavirus%' OR disease_name ILIKE '%sars-cov%'
ORDER BY termination_date, company_name;

\echo ''
\echo '============================================================================'
\echo 'COVID-19 CONTAGION PAIRS'
\echo '============================================================================'
\echo ''

SELECT
    index_termination_date,
    index_company_name,
    index_nct_id,
    days_between as days_later,
    follower_company_name,
    follower_nct_id
FROM contagion_pairs
WHERE disease_name ILIKE '%covid%' OR disease_name ILIKE '%coronavirus%' OR disease_name ILIKE '%sars-cov%'
ORDER BY index_termination_date, days_between;

\echo ''
\echo '============================================================================'
\echo 'MULTIPLE MYELOMA TERMINATION TIMELINE'
\echo '============================================================================'
\echo ''

SELECT
    termination_date,
    company_name,
    nct_id,
    phase,
    trial_title,
    why_stopped
FROM termination_events
WHERE disease_name ILIKE '%multiple myeloma%'
ORDER BY termination_date, company_name;

\echo ''
\echo '============================================================================'
\echo 'MULTIPLE MYELOMA CONTAGION PAIRS'
\echo '============================================================================'
\echo ''

SELECT
    index_termination_date,
    index_company_name,
    index_nct_id,
    days_between as days_later,
    follower_company_name,
    follower_nct_id,
    follower_phase
FROM contagion_pairs
WHERE disease_name ILIKE '%multiple myeloma%'
ORDER BY index_termination_date, days_between;

-- ============================================================================
-- Step 5: First Mover Analysis
-- Which companies' terminations predict the most follow-on terminations?
-- ============================================================================

\echo ''
\echo '============================================================================'
\echo 'TOP 20 "FIRST MOVER" COMPANIES'
\echo '(Companies whose terminations predict the most follow-on terminations)'
\echo '============================================================================'
\echo ''

SELECT
    index_company_name,
    COUNT(DISTINCT index_trial_id) as index_terminations,
    COUNT(DISTINCT disease_id) as indications_affected,
    COUNT(*) as total_followers,
    ROUND(AVG(days_between), 1) as avg_days_to_follower,
    COUNT(DISTINCT follower_company_id) as unique_follower_companies
FROM contagion_pairs
GROUP BY index_company_name, index_company_id
ORDER BY total_followers DESC
LIMIT 20;

-- ============================================================================
-- Step 6: Indication-Specific Contagion Cascades
-- Find the most dramatic cascade events
-- ============================================================================

\echo ''
\echo '============================================================================'
\echo 'MOST DRAMATIC CONTAGION CASCADES'
\echo '(Single terminations that triggered the most followers)'
\echo '============================================================================'
\echo ''

SELECT
    index_termination_date,
    index_company_name,
    disease_name,
    index_nct_id,
    index_phase,
    COUNT(*) as num_followers,
    ROUND(AVG(days_between), 1) as avg_days_to_follower,
    STRING_AGG(DISTINCT follower_company_name, ', ' ORDER BY follower_company_name) as follower_companies
FROM contagion_pairs
GROUP BY
    index_termination_date,
    index_company_name,
    disease_name,
    index_nct_id,
    index_phase,
    index_trial_id
HAVING COUNT(*) >= 3  -- At least 3 followers
ORDER BY num_followers DESC, index_termination_date DESC
LIMIT 20;

-- ============================================================================
-- Step 7: Temporal Analysis
-- How has contagion changed over time?
-- ============================================================================

\echo ''
\echo '============================================================================'
\echo 'CONTAGION TRENDS BY YEAR'
\echo '============================================================================'
\echo ''

WITH yearly_stats AS (
    SELECT
        EXTRACT(YEAR FROM termination_date) as year,
        COUNT(DISTINCT trial_id) as total_terminations,
        COUNT(DISTINCT company_id) as unique_companies,
        COUNT(DISTINCT disease_id) as unique_indications
    FROM termination_events
    WHERE termination_date >= '2010-01-01'
    GROUP BY EXTRACT(YEAR FROM termination_date)
),
yearly_contagion AS (
    SELECT
        EXTRACT(YEAR FROM index_termination_date) as year,
        COUNT(DISTINCT index_trial_id) as index_events,
        COUNT(*) as follower_events
    FROM contagion_pairs
    GROUP BY EXTRACT(YEAR FROM index_termination_date)
)
SELECT
    ys.year,
    ys.total_terminations,
    COALESCE(yc.index_events, 0) as index_events,
    COALESCE(yc.follower_events, 0) as follower_events,
    ROUND(100.0 * COALESCE(yc.index_events, 0) / NULLIF(ys.total_terminations, 0), 2) as contagion_rate_pct
FROM yearly_stats ys
LEFT JOIN yearly_contagion yc ON ys.year = yc.year
ORDER BY ys.year;

-- ============================================================================
-- Step 8: Phase-Specific Analysis
-- Does contagion differ by trial phase?
-- ============================================================================

\echo ''
\echo '============================================================================'
\echo 'CONTAGION BY TRIAL PHASE'
\echo '============================================================================'
\echo ''

SELECT
    index_phase,
    COUNT(DISTINCT index_trial_id) as index_events,
    COUNT(*) as follower_events,
    COUNT(DISTINCT disease_id) as indications,
    ROUND(AVG(days_between), 1) as avg_days_to_follower
FROM contagion_pairs
WHERE index_phase IS NOT NULL
GROUP BY index_phase
ORDER BY
    CASE
        WHEN index_phase = 'Phase 1' THEN 1
        WHEN index_phase = 'Phase 2' THEN 2
        WHEN index_phase = 'Phase 3' THEN 3
        WHEN index_phase = 'Phase 4' THEN 4
        ELSE 5
    END;

-- ============================================================================
-- Step 9: Export detailed contagion network for specific indications
-- ============================================================================

\echo ''
\echo '============================================================================'
\echo 'DETAILED CONTAGION NETWORK - ALL HIGH-IMPACT INDICATIONS'
\echo '(Indications with 5+ follower events)'
\echo '============================================================================'
\echo ''

SELECT
    cp.disease_name,
    cp.index_termination_date,
    cp.index_company_name,
    cp.index_nct_id,
    cp.index_phase,
    cp.follower_termination_date,
    cp.follower_company_name,
    cp.follower_nct_id,
    cp.follower_phase,
    cp.days_between
FROM contagion_pairs cp
INNER JOIN (
    SELECT disease_id
    FROM contagion_pairs
    GROUP BY disease_id
    HAVING COUNT(*) >= 5
) high_impact ON cp.disease_id = high_impact.disease_id
ORDER BY cp.disease_name, cp.index_termination_date, cp.days_between;
