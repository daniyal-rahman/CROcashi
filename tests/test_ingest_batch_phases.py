# tests/test_ingest_batch_phases.py
import sys, runpy
from contextlib import contextmanager
from sqlalchemy import event

SCRIPT_PATH = "scripts/ingest_ctgov.py"
ALLOWED = {"PHASE2", "PHASE3", "PHASE2_PHASE3"}

@contextmanager
def attach_phase_probe():
    from sqlalchemy.engine import Engine
    observed = {"bad_rows": []}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if "INSERT INTO trials" not in statement:
            return
        rows = parameters if isinstance(parameters, list) else [parameters]
        for r in rows:
            if not isinstance(r, dict):
                continue
            # find any "phase*" key, and the matching "nct_id*" if present
            phase = next((str(v) for k, v in r.items() if k.startswith("phase") and v is not None), None)
            nct   = next((str(v) for k, v in r.items() if k.startswith("nct_id") and v is not None), None)
            if phase and phase not in ALLOWED:
                observed["bad_rows"].append({"nct_id": nct, "phase": phase})

    event.listen(Engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield observed
    finally:
        event.remove(Engine, "before_cursor_execute", before_cursor_execute)

def run_ingest_script(argv):
    old_argv = sys.argv[:]
    sys.argv = [SCRIPT_PATH, *argv]
    try:
        runpy.run_path(SCRIPT_PATH, run_name="__main__")
    finally:
        sys.argv = old_argv

def test_no_phase1_inserted(monkeypatch):
    monkeypatch.setenv("CONFIG_PROFILE", "local")
    argv = ["--since", "2025-08-15"]
    with attach_phase_probe() as seen:
        try:
            run_ingest_script(argv)
        except Exception:
            # let us assert on what we captured even if DB throws
            pass
    print(f"[TEST] bad rows: {seen['bad_rows']}")
    assert not seen["bad_rows"], f"Disallowed phases batched: {seen['bad_rows']}"
