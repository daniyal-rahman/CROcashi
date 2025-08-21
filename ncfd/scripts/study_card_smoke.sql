-- Study Card Guardrails Smoke Test
-- This script tests the pivotal study card validation trigger

-- Seed trial as pivotal
INSERT INTO trials (trial_id, nct_id, sponsor_text, phase, indication, is_pivotal, status)
VALUES (9001, 'NCTDUMMY', 'Acme', '3', 'COPD', true, 'completed')
ON CONFLICT (trial_id) DO NOTHING;

-- Test 1: Failing insert - missing effect OR p-value
-- This should raise an exception due to missing pivotal requirements
INSERT INTO studies (study_id, trial_id, doc_type, citation, year, url, oa_status, extracted_jsonb, coverage_level)
VALUES (7001, 9001, 'PR', 'Acme PR', 2024, 'https://x', 'open',
'{"doc":{"doc_type":"PR","title":"x","year":2024,"url":"x","source_id":"s"},
  "trial":{"nct_id":"NCTDUMMY","phase":"3","indication":"COPD","is_pivotal":true},
  "primary_endpoints":[{"name":"E1"}],
  "populations":{"analysis_primary_on":"ITT","itt":{"defined":true}},
  "arms":[{"label":"A","n":100},{"label":"B","n":100}],
  "sample_size":{"total_n":200},
  "results":{"primary":[{"endpoint":"E1"}]},
  "coverage_level":"low"}'::jsonb,
'low');

-- Test 2: Passing insert - all pivotal requirements met
-- This should succeed
INSERT INTO studies (study_id, trial_id, doc_type, citation, year, url, oa_status, extracted_jsonb, coverage_level)
VALUES (7002, 9001, 'Abstract', 'Conf Abs', 2025, 'https://y', 'open',
'{"doc":{"doc_type":"Abstract","title":"y","year":2025,"url":"y","source_id":"s2"},
  "trial":{"nct_id":"NCTDUMMY","phase":"3","indication":"COPD","is_pivotal":true},
  "primary_endpoints":[{"name":"E1","evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":1}}]}],
  "populations":{"analysis_primary_on":"ITT","itt":{"defined":true,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":1}}]}},
  "arms":[{"label":"A","n":120,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]},
          {"label":"B","n":120,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]}],
  "sample_size":{"total_n":240,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]},
  "results":{"primary":[{"endpoint":"E1","p_value":0.012,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":3}}]}]},
  "coverage_level":"high"}'::jsonb,
'high');

-- Test 3: Non-pivotal trial - should not trigger validation
INSERT INTO trials (trial_id, nct_id, sponsor_text, phase, indication, is_pivotal, status)
VALUES (9002, 'NCTDUMMY2', 'Acme', '1', 'COPD', false, 'completed')
ON CONFLICT (trial_id) DO NOTHING;

INSERT INTO studies (study_id, trial_id, doc_type, citation, year, url, oa_status, extracted_jsonb, coverage_level)
VALUES (7003, 9002, 'PR', 'Phase 1 PR', 2024, 'https://z', 'open',
'{"doc":{"doc_type":"PR","title":"z","year":2024,"url":"z","source_id":"s3"},
  "trial":{"nct_id":"NCTDUMMY2","phase":"1","indication":"COPD","is_pivotal":false},
  "primary_endpoints":[{"name":"E1"}],
  "coverage_level":"low"}'::jsonb,
'low');

-- Verify results
SELECT study_id, coverage_level,
       extracted_jsonb #>> '{results,primary,0,p_value}' AS p_value,
       extracted_jsonb #>> '{sample_size,total_n}' AS total_n,
       extracted_jsonb #>> '{populations,analysis_primary_on}' AS analysis_population
FROM studies 
WHERE trial_id IN (9001, 9002)
ORDER BY study_id;

-- Check trial information
SELECT trial_id, nct_id, is_pivotal, phase, indication
FROM trials 
WHERE trial_id IN (9001, 9002)
ORDER BY trial_id;

-- Expected results:
-- study_id | coverage_level | p_value | total_n | analysis_population
-- 7001     | (should fail) | NULL    | 200     | ITT
-- 7002     | high          | 0.012   | 240     | ITT  
-- 7003     | low           | NULL    | NULL    | NULL
