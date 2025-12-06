-- ============================================================================
-- INDICATION HEAT ANALYSIS: Trial Starts Per Year Per Indication
-- Analyzing where money is flowing and where companies are retreating
-- ============================================================================

-- Query 1: Trial Starts Per Indication Per Year (2018-2024)
-- ============================================================================
DROP TABLE IF EXISTS temp_indication_yearly_counts;
CREATE TEMP TABLE temp_indication_yearly_counts AS
SELECT
    d.disease_name as indication,
    EXTRACT(YEAR FROM ct.start_date) as year,
    COUNT(DISTINCT ct.trial_id) as trial_starts,
    COUNT(DISTINCT CASE WHEN ct.phase_numeric = 1 THEN ct.trial_id END) as phase1_count,
    COUNT(DISTINCT CASE WHEN ct.phase_numeric = 2 THEN ct.trial_id END) as phase2_count,
    COUNT(DISTINCT CASE WHEN ct.phase_numeric = 3 THEN ct.trial_id END) as phase3_count
FROM clinical_trials ct
INNER JOIN trial_diseases td ON ct.trial_id = td.trial_id
INNER JOIN diseases d ON td.disease_id = d.disease_id
WHERE ct.start_date IS NOT NULL
    AND ct.start_date >= '2018-01-01'
    AND ct.start_date <= '2024-12-31'
    AND ct.deleted_at IS NULL
    AND td.deleted_at IS NULL
    AND d.deleted_at IS NULL
GROUP BY d.disease_name, EXTRACT(YEAR FROM ct.start_date);

-- Create index for faster aggregation
CREATE INDEX idx_temp_indication ON temp_indication_yearly_counts(indication);

-- Query 2: Calculate Year-over-Year Growth Rates
-- ============================================================================
DROP TABLE IF EXISTS temp_yoy_growth;
CREATE TEMP TABLE temp_yoy_growth AS
WITH yearly_totals AS (
    SELECT
        indication,
        year,
        trial_starts,
        LAG(trial_starts, 1) OVER (PARTITION BY indication ORDER BY year) as prev_year_starts
    FROM temp_indication_yearly_counts
)
SELECT
    indication,
    year,
    trial_starts,
    prev_year_starts,
    CASE
        WHEN prev_year_starts > 0 THEN
            ROUND(((trial_starts::numeric - prev_year_starts::numeric) / prev_year_starts::numeric * 100), 2)
        ELSE NULL
    END as yoy_growth_pct
FROM yearly_totals
WHERE year >= 2019; -- Need previous year for comparison

-- Query 3: Overall Indication Statistics (2018-2024)
-- ============================================================================
DROP TABLE IF EXISTS temp_indication_stats;
CREATE TEMP TABLE temp_indication_stats AS
SELECT
    indication,
    SUM(trial_starts) as total_trials,
    SUM(CASE WHEN year >= 2020 THEN trial_starts ELSE 0 END) as trials_2020_2024,
    SUM(CASE WHEN year BETWEEN 2018 AND 2019 THEN trial_starts ELSE 0 END) as trials_2018_2019,
    SUM(CASE WHEN year >= 2022 THEN trial_starts ELSE 0 END) as trials_recent_3yr,
    AVG(trial_starts) as avg_yearly_trials,
    MAX(year) as last_year_with_trials,
    MIN(year) as first_year_with_trials
FROM temp_indication_yearly_counts
GROUP BY indication
HAVING SUM(trial_starts) >= 10; -- Focus on indications with meaningful activity

-- Query 4: Calculate Momentum Score
-- ============================================================================
-- Momentum = weighted average of recent YoY growth + recent absolute volume
DROP TABLE IF EXISTS temp_momentum_scores;
CREATE TEMP TABLE temp_momentum_scores AS
WITH recent_growth AS (
    SELECT
        indication,
        AVG(yoy_growth_pct) FILTER (WHERE year >= 2022) as avg_growth_2022_2024,
        AVG(yoy_growth_pct) FILTER (WHERE year >= 2020) as avg_growth_2020_2024
    FROM temp_yoy_growth
    GROUP BY indication
),
recent_volume AS (
    SELECT
        indication,
        SUM(trial_starts) FILTER (WHERE year >= 2022) as volume_2022_2024,
        SUM(trial_starts) FILTER (WHERE year >= 2020) as volume_2020_2024
    FROM temp_indication_yearly_counts
    GROUP BY indication
)
SELECT
    s.indication,
    s.total_trials,
    s.trials_2020_2024,
    s.trials_recent_3yr,
    rv.volume_2022_2024,
    rg.avg_growth_2022_2024,
    rg.avg_growth_2020_2024,
    -- Momentum score: 60% weight on recent growth, 40% on volume
    ROUND(
        (COALESCE(rg.avg_growth_2022_2024, 0) * 0.6) +
        (COALESCE(rv.volume_2022_2024, 0) * 0.4)
    , 2) as momentum_score
FROM temp_indication_stats s
LEFT JOIN recent_growth rg ON s.indication = rg.indication
LEFT JOIN recent_volume rv ON s.indication = rv.indication
WHERE s.total_trials >= 20; -- Focus on more significant indications

-- Query 5: Top 20 Hottest Indications (Highest Growth)
-- ============================================================================
SELECT
    indication,
    total_trials,
    trials_recent_3yr,
    volume_2022_2024,
    avg_growth_2022_2024 as avg_growth_pct,
    momentum_score
FROM temp_momentum_scores
WHERE avg_growth_2022_2024 > 0
ORDER BY avg_growth_2022_2024 DESC, volume_2022_2024 DESC
LIMIT 20;

-- Query 6: Top 20 Coldest Indications (Biggest Decline)
-- ============================================================================
SELECT
    indication,
    total_trials,
    trials_recent_3yr,
    volume_2022_2024,
    avg_growth_2022_2024 as avg_growth_pct,
    momentum_score
FROM temp_momentum_scores
WHERE avg_growth_2022_2024 < 0
ORDER BY avg_growth_2022_2024 ASC, total_trials DESC
LIMIT 20;

-- Query 7: Phase Distribution Analysis - Are companies moving up or down?
-- ============================================================================
WITH phase_trends AS (
    SELECT
        indication,
        year,
        trial_starts,
        phase1_count,
        phase2_count,
        phase3_count,
        ROUND(phase1_count::numeric / NULLIF(trial_starts, 0) * 100, 1) as pct_phase1,
        ROUND(phase2_count::numeric / NULLIF(trial_starts, 0) * 100, 1) as pct_phase2,
        ROUND(phase3_count::numeric / NULLIF(trial_starts, 0) * 100, 1) as pct_phase3
    FROM temp_indication_yearly_counts
),
phase_shifts AS (
    SELECT
        indication,
        AVG(pct_phase3) FILTER (WHERE year >= 2022) as avg_pct_phase3_recent,
        AVG(pct_phase3) FILTER (WHERE year BETWEEN 2018 AND 2020) as avg_pct_phase3_early,
        AVG(pct_phase2) FILTER (WHERE year >= 2022) as avg_pct_phase2_recent,
        AVG(pct_phase2) FILTER (WHERE year BETWEEN 2018 AND 2020) as avg_pct_phase2_early,
        SUM(trial_starts) FILTER (WHERE year >= 2022) as recent_volume
    FROM phase_trends
    GROUP BY indication
    HAVING SUM(trial_starts) >= 30
)
SELECT
    indication,
    recent_volume,
    ROUND(avg_pct_phase3_recent, 1) as phase3_pct_recent,
    ROUND(avg_pct_phase3_early, 1) as phase3_pct_early,
    ROUND(avg_pct_phase3_recent - avg_pct_phase3_early, 1) as phase3_shift,
    ROUND(avg_pct_phase2_recent, 1) as phase2_pct_recent,
    ROUND(avg_pct_phase2_early, 1) as phase2_pct_early,
    ROUND(avg_pct_phase2_recent - avg_pct_phase2_early, 1) as phase2_shift
FROM phase_shifts
WHERE ABS(avg_pct_phase3_recent - avg_pct_phase3_early) > 5 -- Meaningful shift
ORDER BY ABS(avg_pct_phase3_recent - avg_pct_phase3_early) DESC
LIMIT 30;

-- Query 8: COVID-19 Specific Analysis
-- ============================================================================
SELECT
    year,
    trial_starts,
    phase1_count,
    phase2_count,
    phase3_count
FROM temp_indication_yearly_counts
WHERE indication ILIKE '%covid%' OR indication ILIKE '%coronavirus%' OR indication ILIKE '%sars-cov%'
ORDER BY year;

-- Query 9: Oncology Trends (Cancer indications)
-- ============================================================================
WITH oncology_totals AS (
    SELECT
        year,
        SUM(trial_starts) as total_oncology_trials,
        SUM(phase1_count) as phase1,
        SUM(phase2_count) as phase2,
        SUM(phase3_count) as phase3
    FROM temp_indication_yearly_counts
    WHERE indication ILIKE '%cancer%'
        OR indication ILIKE '%carcinoma%'
        OR indication ILIKE '%lymphoma%'
        OR indication ILIKE '%leukemia%'
        OR indication ILIKE '%melanoma%'
        OR indication ILIKE '%sarcoma%'
        OR indication ILIKE '%myeloma%'
        OR indication ILIKE '%tumor%'
    GROUP BY year
)
SELECT
    year,
    total_oncology_trials,
    phase1,
    phase2,
    phase3,
    ROUND(phase1::numeric / NULLIF(total_oncology_trials, 0) * 100, 1) as pct_phase1,
    ROUND(phase2::numeric / NULLIF(total_oncology_trials, 0) * 100, 1) as pct_phase2,
    ROUND(phase3::numeric / NULLIF(total_oncology_trials, 0) * 100, 1) as pct_phase3
FROM oncology_totals
ORDER BY year;

-- Query 10: Autoimmune/Inflammatory Trends
-- ============================================================================
WITH autoimmune_totals AS (
    SELECT
        year,
        SUM(trial_starts) as total_autoimmune_trials,
        SUM(phase1_count) as phase1,
        SUM(phase2_count) as phase2,
        SUM(phase3_count) as phase3
    FROM temp_indication_yearly_counts
    WHERE indication ILIKE '%arthritis%'
        OR indication ILIKE '%lupus%'
        OR indication ILIKE '%crohn%'
        OR indication ILIKE '%colitis%'
        OR indication ILIKE '%psoriasis%'
        OR indication ILIKE '%sclerosis%'
        OR indication ILIKE '%autoimmune%'
    GROUP BY year
)
SELECT
    year,
    total_autoimmune_trials,
    phase1,
    phase2,
    phase3,
    ROUND(phase1::numeric / NULLIF(total_autoimmune_trials, 0) * 100, 1) as pct_phase1,
    ROUND(phase2::numeric / NULLIF(total_autoimmune_trials, 0) * 100, 1) as pct_phase2,
    ROUND(phase3::numeric / NULLIF(total_autoimmune_trials, 0) * 100, 1) as pct_phase3
FROM autoimmune_totals
ORDER BY year;

-- Query 11: Year-by-Year Heatmap Data for Top 30 Indications by Total Volume
-- ============================================================================
WITH top_indications AS (
    SELECT indication
    FROM temp_indication_stats
    ORDER BY total_trials DESC
    LIMIT 30
)
SELECT
    ti.indication,
    COALESCE(y2018.trial_starts, 0) as y2018,
    COALESCE(y2019.trial_starts, 0) as y2019,
    COALESCE(y2020.trial_starts, 0) as y2020,
    COALESCE(y2021.trial_starts, 0) as y2021,
    COALESCE(y2022.trial_starts, 0) as y2022,
    COALESCE(y2023.trial_starts, 0) as y2023,
    COALESCE(y2024.trial_starts, 0) as y2024,
    stats.total_trials
FROM top_indications ti
LEFT JOIN temp_indication_stats stats ON ti.indication = stats.indication
LEFT JOIN (SELECT indication, trial_starts FROM temp_indication_yearly_counts WHERE year = 2018) y2018 ON ti.indication = y2018.indication
LEFT JOIN (SELECT indication, trial_starts FROM temp_indication_yearly_counts WHERE year = 2019) y2019 ON ti.indication = y2019.indication
LEFT JOIN (SELECT indication, trial_starts FROM temp_indication_yearly_counts WHERE year = 2020) y2020 ON ti.indication = y2020.indication
LEFT JOIN (SELECT indication, trial_starts FROM temp_indication_yearly_counts WHERE year = 2021) y2021 ON ti.indication = y2021.indication
LEFT JOIN (SELECT indication, trial_starts FROM temp_indication_yearly_counts WHERE year = 2022) y2022 ON ti.indication = y2022.indication
LEFT JOIN (SELECT indication, trial_starts FROM temp_indication_yearly_counts WHERE year = 2023) y2023 ON ti.indication = y2023.indication
LEFT JOIN (SELECT indication, trial_starts FROM temp_indication_yearly_counts WHERE year = 2024) y2024 ON ti.indication = y2024.indication
ORDER BY stats.total_trials DESC;

-- Query 12: High-Momentum Emerging Indications (Low historical volume but high recent growth)
-- ============================================================================
WITH emerging AS (
    SELECT
        s.indication,
        s.trials_2018_2019,
        s.trials_recent_3yr,
        m.avg_growth_2022_2024,
        m.volume_2022_2024,
        ROUND(s.trials_recent_3yr::numeric / NULLIF(s.trials_2018_2019, 0), 2) as recent_vs_baseline_ratio
    FROM temp_indication_stats s
    INNER JOIN temp_momentum_scores m ON s.indication = m.indication
    WHERE s.trials_2018_2019 BETWEEN 5 AND 50  -- Had some but not massive baseline
        AND s.trials_recent_3yr > s.trials_2018_2019 -- Growing
        AND m.avg_growth_2022_2024 > 10  -- Strong recent growth
)
SELECT
    indication,
    trials_2018_2019 as baseline_volume,
    trials_recent_3yr as recent_volume,
    volume_2022_2024 as volume_2022_2024,
    avg_growth_2022_2024 as avg_growth_pct,
    recent_vs_baseline_ratio as growth_multiple
FROM emerging
ORDER BY avg_growth_2022_2024 DESC, recent_vs_baseline_ratio DESC
LIMIT 20;
