
from ncfd.ingest.ctgov import CtgovClient

def test_extract_fields_minimal_fixture():
    c = CtgovClient()
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT01234567"},
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Acme Bio"}},
            "designModule": {
                "studyType": "INTERVENTIONAL",
                "phases": ["PHASE3"],
                "enrollmentInfo": {"count": 420}
            },
            "armsInterventionsModule": {
                "interventions": [{"type": "DRUG"}, {"type": "BIOLOGICAL"}]
            },
            "outcomesModule": {
                "primaryOutcomes": [
                    {"measure": "PFS", "timeFrame": "Week 24"},
                    {"measure": "OS"}
                ]
            },
            "statusModule": {
                "overallStatus": "Recruiting",
                "studyFirstPostDateStruct": {"date": "2024-11-01"},
                "lastUpdatePostDateStruct": {"date": "2025-07-15"},
                "primaryCompletionDateStruct": {"date": "2026-03"}
            }
        }
    }
    f = c.extract_fields(study)
    assert f.nct_id == "NCT01234567"
    assert f.sponsor_text == "Acme Bio"
    assert f.phase in ("PHASE3", "Phase 3")
    assert set(f.intervention_types) == {"DRUG", "BIOLOGICAL"}
    assert f.sample_size == 420
    assert f.primary_endpoint_text == "PFS (Week 24); OS"
    assert f.status == "Recruiting"
    assert f.last_update_posted_date.isoformat() == "2025-07-15"
