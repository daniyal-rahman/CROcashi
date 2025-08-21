I attempted to make an llm checker to do the wiring as an additional option to avoid some of the issues that I was having in problem.md and so I wanted to get something working fast. My understanding is that the current api calls work and whatnot, but they don't write to the db or something similar. I want you to figure out what the issue is and then fix the errors so that it actually writes to the db.

something like this should let you know if it worked or not
PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT00032773 --persist --apply-trial --decider llm

PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --persist --apply-trial --limit 50

psql "$PSQL_DSN" -c "SELECT decision_mode, confidence, nct_id, chosen_company_id, created_at FROM resolver_llm_logs ORDER BY llm_id DESC LIMIT 20;"

