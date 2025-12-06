-- Quick summary statistics for failure contagion analysis
-- Run after failure_contagion_analysis.sql

\echo ''
\echo '========================================='
\echo 'FAILURE CONTAGION QUICK SUMMARY'
\echo '========================================='
\echo ''

-- Overall metrics
SELECT
    'OVERALL METRICS' as section,
    '' as metric,
    '' as value;

SELECT
    '' as section,
    'Total termination events (2010+)' as metric,
    COUNT(*)::text as value
FROM termination_events
UNION ALL
SELECT
    '',
    'Contagion pairs identified',
    COUNT(*)::text
FROM contagion_pairs
UNION ALL
SELECT
    '',
    'Indications showing contagion',
    COUNT(DISTINCT disease_id)::text
FROM contagion_pairs
UNION ALL
SELECT
    '',
    'Average contagion rate (2020-2024)',
    ROUND(AVG(contagion_rate_pct), 1)::text || '%'
FROM indication_contagion_rates
WHERE disease_name IN (
    SELECT disease_name
    FROM termination_events
    WHERE EXTRACT(YEAR FROM termination_date) BETWEEN 2020 AND 2024
    GROUP BY disease_name
);

\echo ''
\echo 'TOP 5 CONTAGION INDICATIONS'
\echo ''

SELECT
    SUBSTRING(disease_name, 1, 40) as indication,
    contagion_rate_pct::text || '%' as contagion_rate,
    total_follower_events::text as followers,
    total_terminations::text as total_terms
FROM indication_contagion_rates
WHERE index_terminations > 0
ORDER BY contagion_rate_pct DESC
LIMIT 5;

\echo ''
\echo 'TOP 5 FIRST MOVER COMPANIES'
\echo ''

SELECT
    SUBSTRING(index_company_name, 1, 35) as company,
    COUNT(DISTINCT index_trial_id)::text as index_events,
    COUNT(*)::text as followers,
    COUNT(DISTINCT disease_id)::text as indications
FROM contagion_pairs
GROUP BY index_company_name
ORDER BY COUNT(*) DESC
LIMIT 5;

\echo ''
\echo 'CONTAGION BY PHASE'
\echo ''

SELECT
    index_phase as phase,
    COUNT(DISTINCT index_trial_id)::text as index_events,
    COUNT(*)::text as follower_events,
    ROUND(AVG(days_between), 0)::text || ' days' as avg_time_to_follower
FROM contagion_pairs
WHERE index_phase IS NOT NULL
GROUP BY index_phase
ORDER BY
    CASE
        WHEN index_phase = 'PHASE1' THEN 1
        WHEN index_phase = 'PHASE2' THEN 2
        WHEN index_phase = 'PHASE3' THEN 3
        ELSE 4
    END;

\echo ''
\echo 'YEAR-OVER-YEAR CONTAGION TRENDS'
\echo ''

WITH yearly_stats AS (
    SELECT
        EXTRACT(YEAR FROM termination_date)::int as year,
        COUNT(DISTINCT trial_id) as total_terminations
    FROM termination_events
    WHERE EXTRACT(YEAR FROM termination_date) BETWEEN 2019 AND 2024
    GROUP BY EXTRACT(YEAR FROM termination_date)
),
yearly_contagion AS (
    SELECT
        EXTRACT(YEAR FROM index_termination_date)::int as year,
        COUNT(DISTINCT index_trial_id) as index_events,
        COUNT(*) as follower_events
    FROM contagion_pairs
    WHERE EXTRACT(YEAR FROM index_termination_date) BETWEEN 2019 AND 2024
    GROUP BY EXTRACT(YEAR FROM index_termination_date)
)
SELECT
    ys.year::text,
    ys.total_terminations::text as total_terms,
    COALESCE(yc.index_events, 0)::text as index_events,
    COALESCE(yc.follower_events, 0)::text as followers,
    ROUND(100.0 * COALESCE(yc.index_events, 0) / NULLIF(ys.total_terminations, 0), 1)::text || '%' as contagion_rate
FROM yearly_stats ys
LEFT JOIN yearly_contagion yc ON ys.year = yc.year
ORDER BY ys.year;
