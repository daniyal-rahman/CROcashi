# tests/test_ingest_phase_filter.py
import pytest

ALLOWED = {"PHASE2", "PHASE3", "PHASE2_PHASE3"}

# Replace with your real function that builds the rows that get bulk-inserted.
# e.g., build_trial_rows(studies: list[dict]) -> list[dict]
from ncfd.ingest.ctgov import build_trial_rows  

def st(phase):
    # shape matches what your extractor consumes
    return {
        "protocolSection": {
            "designModule": {
                "phases": [phase]  # your _is_phase_2_or_3 looks here
            }
        }
    }

def test_builder_excludes_phase1_and_emits_only_allowed():
    studies = [
        st("PHASE1"),
        st("PHASE2"),
        st("PHASE3"),
        st("PHASE2_PHASE3"),
    ]

    rows = build_trial_rows(studies)

    # no PHASE1 rows should be constructed at all
    row_phases = {r["phase"] for r in rows}  # or r.phase if ORM objects
    assert "PHASE1" not in row_phases

    # everything emitted should be in the allowlist your DB accepts
    assert row_phases.issubset(ALLOWED), row_phases
