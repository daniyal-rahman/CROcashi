-- Debug the pivotal study guardrails
-- Check the current trial data
SELECT trial_id, nct_id, is_pivotal, phase, indication, status
FROM trials 
WHERE trial_id IN (9999, 9998, 9997)
ORDER BY trial_id;

-- Check if there are any existing trials with the same NCT ID
SELECT trial_id, nct_id, is_pivotal, phase, indication, status
FROM trials 
WHERE nct_id LIKE '%TEST%' OR nct_id LIKE '%999%'
ORDER BY trial_id;

-- Try to force update the trial to be pivotal
UPDATE trials 
SET is_pivotal = true, 
    phase = '3', 
    indication = 'Test Disease',
    status = 'completed'
WHERE trial_id = 9999;

-- Check the updated trial
SELECT trial_id, nct_id, is_pivotal, phase, indication, status
FROM trials 
WHERE trial_id = 9999;

-- Now try to insert a study that should fail the guardrails
INSERT INTO studies (study_id, trial_id, doc_type, citation, year, url, oa_status, extracted_jsonb, coverage_level)
VALUES (9997, 9999, 'PR', 'Test PR Fail', 2024, 'https://test.com/fail', 'open',
'{"doc":{"doc_type":"PR","title":"Test Fail","year":2024,"url":"https://test.com/fail","source_id":"test_fail"},
  "trial":{"nct_id":"NCTTEST999","phase":"3","indication":"Test Disease","is_pivotal":true},
  "primary_endpoints":[{"name":"Test Endpoint"}],
  "coverage_level":"low"}'::jsonb,
'low');

-- Check if the trigger function is working by looking at the function definition
SELECT pg_get_functiondef(oid) 
FROM pg_proc 
WHERE proname = 'enforce_pivotal_study_card';
