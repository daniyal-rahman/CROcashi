-- Test the pivotal study guardrails
-- First, create a pivotal trial
INSERT INTO trials (trial_id, nct_id, sponsor_text, phase, indication, is_pivotal, status, last_seen_at)
VALUES (9999, 'NCTTEST999', 'Test Sponsor', '3', 'Test Disease', true, 'completed', NOW())
ON CONFLICT (trial_id) DO NOTHING;

-- Test 1: Try to insert a study with missing pivotal requirements (should fail)
-- This should trigger the guardrail and raise an exception
INSERT INTO studies (study_id, trial_id, doc_type, citation, year, url, oa_status, extracted_jsonb, coverage_level)
VALUES (9999, 9999, 'PR', 'Test PR', 2024, 'https://test.com', 'open',
'{"doc":{"doc_type":"PR","title":"Test","year":2024,"url":"https://test.com","source_id":"test"},
  "trial":{"nct_id":"NCTTEST999","phase":"3","indication":"Test Disease","is_pivotal":true},
  "primary_endpoints":[{"name":"Test Endpoint"}],
  "populations":{"itt":{"defined":true}},
  "arms":[{"label":"A","n":100},{"label":"B","n":100}],
  "sample_size":{"total_n":200},
  "results":{"primary":[{"endpoint":"Test Endpoint"}]},
  "coverage_level":"low"}'::jsonb,
'low');

-- Test 2: Insert a study with all pivotal requirements met (should succeed)
INSERT INTO studies (study_id, trial_id, doc_type, citation, year, url, oa_status, extracted_jsonb, coverage_level)
VALUES (9998, 9999, 'Abstract', 'Test Abstract', 2024, 'https://test.com/abs', 'open',
'{"doc":{"doc_type":"Abstract","title":"Test Abstract","year":2024,"url":"https://test.com/abs","source_id":"test_abs"},
  "trial":{"nct_id":"NCTTEST999","phase":"3","indication":"Test Disease","is_pivotal":true},
  "primary_endpoints":[{"name":"Test Endpoint","evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":1}}]}],
  "populations":{"itt":{"defined":true,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":1}}]}},
  "arms":[{"label":"A","n":100,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]},
          {"label":"B","n":100,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]}],
  "sample_size":{"total_n":200,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":2}}]},
  "results":{"primary":[{"endpoint":"Test Endpoint","p_value":0.05,"evidence":[{"loc":{"scheme":"page_paragraph","page":1,"paragraph":3}}]}]},
  "coverage_level":"high"}'::jsonb,
'high');

-- Check results
SELECT study_id, trial_id, doc_type, coverage_level,
       extracted_jsonb #>> '{results,primary,0,p_value}' AS p_value,
       extracted_jsonb #>> '{sample_size,total_n}' AS total_n,
       extracted_jsonb #>> '{populations,analysis_primary_on}' AS analysis_population
FROM studies 
WHERE trial_id = 9999
ORDER BY study_id;

-- Check trial information
SELECT trial_id, nct_id, is_pivotal, phase, indication
FROM trials 
WHERE trial_id = 9999;
