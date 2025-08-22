-- Check database structure for Study Card system
\dt studies
\dt trials
\d studies
\d trials

-- Check if the trigger function exists
SELECT proname, prosrc FROM pg_proc WHERE proname = 'enforce_pivotal_study_card';

-- Check if the trigger exists
SELECT trigger_name, event_manipulation, event_object_table 
FROM information_schema.triggers 
WHERE trigger_name = 'trg_enforce_pivotal_study_card';

-- Check current data
SELECT study_id, trial_id, doc_type, coverage_level FROM studies LIMIT 5;
SELECT trial_id, nct_id, is_pivotal, phase FROM trials LIMIT 5;
